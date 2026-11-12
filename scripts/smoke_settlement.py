"""Checks reseller commission statements and settlement against a RUNNING API on this machine (uses the super admin to create
throw-away businesses, and the database directly to move bookings into the past):
    python -m scripts.smoke_settlement --email root@platform.example --password '...'"""
import argparse
import asyncio
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal

import asyncpg
import httpx

from app.core.config import settings

n = 0


def check(cond, msg, extra=None):
    global n
    if not cond:
        print("FAIL:", msg, extra if extra is not None else "")
        sys.exit(1)
    n += 1
    print("  ok ", msg)


def dsn(url):
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def sql(url, query, *args, tenant=None):
    conn = await asyncpg.connect(dsn(url))
    try:
        if tenant:
            await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant))
        return await conn.fetch(query, *args)
    finally:
        await conn.close()


def run_sql(url, query, *args, tenant=None):
    return asyncio.run(sql(url, query, *args, tenant=tenant))


def main(a):
    c = httpx.Client(base_url=a.base, timeout=60)
    tag = uuid.uuid4().hex[:6]
    r = c.post("/api/v1/platform/auth/login", json={"email": a.email, "password": a.password})
    check(r.status_code == 200, "super admin sign-in", r.text)
    P = {"Authorization": "Bearer " + r.json()["access_token"]}
    owner_url = settings.database_url_migrations

    def business(kind):
        dom = f"{kind}-{tag}.example"
        r = c.post("/api/v1/platform/tenants", headers=P, json={"name": f"{kind.title()} {tag}", "domain": dom, "admin_name": "Owner", "admin_email": f"o@{dom}"})
        assert r.status_code == 201, r.text
        t = c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"o@{dom}", "password": r.json()["temporary_password"]}).json()
        return dom, {"Authorization": "Bearer " + t["access_token"]}, r.json()["tenant"]["id"]

    domA, A, idA = business("nobodol")
    domS, S, idS = business("sunrise")
    domX, X, idX = business("outsider")
    p = c.post("/api/v1/properties", headers=A, json={"type": "RESORT", "name": "Nobodol Beach", "slug": "nb", "location": "Cox's Bazar", "metadata": {"description": "x"}}).json()
    units = []
    for i in range(6):
        u = c.post(f"/api/v1/properties/{p['id']}/units", headers=A, json={"unit_name": f"R{i + 1}", "type": "ROOM", "capacity": 2}).json()
        c.put(f"/api/v1/pricing/units/{u['id']}", headers=A, json={"weekday_price": "100.00", "weekend_price": "100.00", "currency": "BDT"})
        units.append(u["id"])
    api = "/api/v1/channel"
    ag = c.post(f"{api}/agreements/request", headers=S, json={"owner_domain": domA}).json()["id"]
    r = c.post(f"{api}/agreements/{ag}/accept", headers=A, json={"commission_type": "FLAT", "commission_value": "50", "properties": [{"property_id": p["id"]}]})
    check(r.status_code == 200 and r.json()["settlement_mode"] == "MONTHLY" and r.json()["settlement_day"] == 10, "agreement starts as monthly, by the 10th", r.text)

    def sell(unit, nights, start_in):
        ci = date.today() + timedelta(days=start_in)
        h = c.post(f"{api}/hold", headers=S, json={"agreement_id": ag, "property_id": p["id"], "unit_id": unit, "check_in": str(ci), "check_out": str(ci + timedelta(days=nights)),
                                                    "guests": 2, "customer": {"name": f"Guest {unit[:4]}", "email": "g@example.com", "phone": "+8801700000000"}})
        assert h.status_code == 201, h.text
        h = h.json()
        r = c.post(f"{api}/confirm", headers=S, json={"agreement_id": ag, "booking_id": h["booking_id"], "payment_mode": "FULL", "amount": h["total_amount"], "payment_reference": f"TXN-{uuid.uuid4().hex[:6]}"})
        assert r.status_code == 200, r.text
        return h["booking_id"]

    def move_to_past(booking, nights, days_ago):
        run_sql(owner_url, "UPDATE bookings SET check_in = $2, check_out = $3 WHERE id = $1::uuid", booking,
                date.today() - timedelta(days=days_ago + nights), date.today() - timedelta(days=days_ago))

    b1, b2, b3, b4 = (sell(units[i], 3, 30 + 10 * i) for i in range(4))

    # ---- nothing is owed before the guest has checked out
    check(c.get(f"{api}/statements", headers=S).json() == [] and c.get(f"{api}/statements", headers=A).json() == [], "no statement before check-out")
    s = c.get(f"{api}/summary", headers=S).json()
    check(s["as_owner"] == [] and float(s["as_reseller"][0]["upcoming"]) == 600 and float(s["as_reseller"][0]["to_pay"]) == 0, "reseller sees 600 coming after check-out", s)
    s = c.get(f"{api}/summary", headers=A).json()
    check(float(s["as_owner"][0]["upcoming"]) == 600 and s["as_reseller"] == [], "owner sees the same 600 as owed later", s)

    # ---- three guests check out (the fourth stays in the future): one monthly statement
    for b, ago in ((b1, 50), (b2, 48), (b3, 46)):
        move_to_past(b, 3, ago)
    st = c.get(f"{api}/statements", headers=S).json()
    check(len(st) == 1 and st[0]["role"] == "RESELLER" and st[0]["status"] == "DUE" and float(st[0]["amount"]) == 450 and st[0]["mode"] == "MONTHLY", "one monthly statement of 450 (3 x 150)", st)
    t = date.today()
    first = t.replace(day=1)
    check(st[0]["due_date"] == str(first.replace(day=10)) and st[0]["period_end"] == str(first - timedelta(days=1)), "due on the 10th of this month, covering finished months", st[0])
    d = c.get(f"{api}/statements/{st[0]['id']}", headers=S).json()
    check(len(d["lines"]) == 3 and sum(Decimal(x["amount"]) for x in d["lines"]) == Decimal("450.00") and d["lines"][0]["guest_name"].startswith("Guest"), "the statement lists every booking", d["lines"])
    ow = c.get(f"{api}/statements", headers=A).json()
    check(len(ow) == 1 and ow[0]["role"] == "OWNER" and ow[0]["id"] == st[0]["id"] and ow[0]["counterpart"].startswith("Sunrise"), "the owner sees the same statement", ow)
    check(len(c.get(f"{api}/statements", headers=S).json()) == 1, "asking again does not make a second statement")
    check(c.get(f"{api}/statements", headers=X).json() == [] and c.get(f"{api}/statements/{st[0]['id']}", headers=X).status_code == 404, "an outsider sees nothing of it")
    sid = st[0]["id"]

    # ---- who may do what
    check(c.post(f"{api}/statements/{sid}/mark-paid", headers=S, json={"reference": "BK-1"}).status_code == 403, "the reseller cannot say it was paid")
    check(c.post(f"{api}/statements/{sid}/confirm", headers=A).status_code == 403, "the owner cannot confirm receipt")
    check(c.post(f"{api}/statements/{sid}/confirm", headers=S).status_code == 409, "cannot confirm before it is marked paid")
    check(c.post(f"{api}/statements/{sid}/dispute", headers=S, json={"reason": "not received"}).status_code == 409, "cannot dispute before it is marked paid")
    check(c.post(f"{api}/statements/{sid}/mark-paid", headers=X, json={"reference": "BK-1"}).status_code == 404, "an outsider cannot touch it")
    check(c.post(f"{api}/statements/{sid}/mark-paid", headers=A, json={"reference": "x"}).status_code == 422, "a payment reference is required")

    # ---- paid -> disputed -> paid again -> confirmed
    r = c.post(f"{api}/statements/{sid}/mark-paid", headers=A, json={"reference": "BKASH-111", "note": "sent from the office phone"})
    check(r.status_code == 200 and r.json()["status"] == "PAID" and r.json()["paid_reference"] == "BKASH-111", "owner marks it paid", r.text)
    check(c.post(f"{api}/statements/{sid}/mark-paid", headers=A, json={"reference": "BKASH-222"}).status_code == 409, "cannot mark paid twice")
    check(float(c.get(f"{api}/summary", headers=S).json()["as_reseller"][0]["awaiting_confirmation"]) == 450, "summary: 450 waiting for the reseller to confirm")
    r = c.post(f"{api}/statements/{sid}/dispute", headers=S, json={"reason": "Nothing arrived in our account"})
    check(r.status_code == 200 and r.json()["status"] == "DISPUTED" and "Nothing arrived" in r.json()["dispute_reason"], "reseller says it did not arrive", r.text)
    check(c.get(f"{api}/statements/{sid}", headers=A).json()["status"] == "DISPUTED", "the owner sees the dispute")
    check(c.post(f"{api}/statements/{sid}/confirm", headers=S).status_code == 409, "a disputed statement cannot be confirmed until paid again")
    r = c.post(f"{api}/statements/{sid}/mark-paid", headers=A, json={"reference": "BANK-9981"})
    check(r.json()["status"] == "PAID" and r.json()["dispute_reason"] is None and r.json()["paid_reference"] == "BANK-9981", "owner pays again with a new reference", r.text)
    r = c.post(f"{api}/statements/{sid}/confirm", headers=S)
    check(r.status_code == 200 and r.json()["status"] == "CONFIRMED" and r.json()["confirmed_at"], "reseller confirms: settled", r.text)
    check(c.post(f"{api}/statements/{sid}/dispute", headers=S, json={"reason": "changed my mind"}).status_code == 409, "a settled statement is final")
    sm = c.get(f"{api}/summary", headers=A).json()["as_owner"][0]
    check(float(sm["settled"]) == 450 and float(sm["to_pay"]) == 0 and float(sm["upcoming"]) == 150, "owner summary: 450 settled, 150 still to come", sm)

    # ---- a cancelled booking takes its commission back
    r = c.post(f"/api/v1/bookings/{b3}/cancel", headers=A, json={"reason": "guest cancelled"})
    check(r.status_code == 200, "owner cancels an already-accrued booking", r.text)
    sm = c.get(f"{api}/summary", headers=S).json()["as_reseller"][0]
    check(float(sm["unbilled"]) == -150, "a -150 refund of commission waits for the next statement", sm)
    check(len(c.get(f"{api}/statements", headers=S).json()) == 1, "...and does not make a statement by itself")

    # ---- change to per-booking settlement (2 days after check-out); the refund comes off the next statement
    r = c.put(f"{api}/agreements/{ag}/terms", headers=A, json={"commission_type": "FLAT", "commission_value": "50", "properties": [{"property_id": p["id"]}], "settlement_mode": "PER_BOOKING", "settlement_day": 2})
    check(r.status_code == 200 and r.json()["settlement_mode"] == "PER_BOOKING" and r.json()["settlement_day"] == 2, "owner changes to per-booking settlement", r.text)
    check(c.put(f"{api}/agreements/{ag}/terms", headers=A, json={"commission_type": "FLAT", "commission_value": "50", "properties": [{"property_id": p["id"]}], "settlement_mode": "MONTHLY", "settlement_day": 31}).status_code == 422, "monthly day above 28 refused")
    b5 = sell(units[4], 5, 80)
    move_to_past(b5, 5, 10)
    st = c.get(f"{api}/statements", headers=S, params={"status": "DUE"}).json()
    check(len(st) == 1 and float(st[0]["amount"]) == 100 and st[0]["mode"] == "PER_BOOKING", "a per-booking statement: 250 minus the 150 refund = 100", st)
    check(st[0]["overdue"] and st[0]["days_overdue"] == 8 and st[0]["due_date"] == str(date.today() - timedelta(days=8)), "due 2 days after check-out, so 8 days late", st[0])
    d = c.get(f"{api}/statements/{st[0]['id']}", headers=A).json()
    check(sorted(x["kind"] for x in d["lines"]) == ["COMMISSION", "REFUND_OF_COMMISSION"], "its lines show the commission and the refund", d["lines"])
    sm = c.get(f"{api}/summary", headers=A).json()["as_owner"][0]
    check(float(sm["overdue"]) == 100 and float(sm["to_pay"]) == 100, "owner summary: 100 overdue", sm)

    # ---- the super admin sees overdue commission
    r = c.get("/api/v1/platform/channel/overdue", headers=P).json()
    mine = [x for x in r["items"] if x["owner_id"] == idA]
    check(len(mine) == 1 and mine[0]["reseller"].startswith("Sunrise") and mine[0]["days_overdue"] == 8 and float(mine[0]["amount"]) == 100, "super admin sees the overdue statement with both names", mine)
    check(c.get("/api/v1/platform/channel/overdue", headers=A).status_code in (401, 403), "ordinary businesses cannot read that list")

    # ---- the daily sweep does the same work without anyone opening a page
    b6 = sell(units[5], 2, 90)
    move_to_past(b6, 2, 3)
    from app.workers.tasks import channel_statements
    out = channel_statements.run()
    check(out["ledger_rows"] >= 1 and out["statements"] >= 1, "the daily sweep writes commission and makes the statement", out)
    check(len(c.get(f"{api}/statements", headers=A, params={"status": "DUE"}).json()) == 2, "owner now has two statements to pay")
    check(channel_statements.run() == {"ledger_rows": 0, "statements": 0}, "running the sweep again changes nothing")

    # ---- the commission book cannot be edited, and each business sees only its own rows
    app_url = settings.database_url
    for q in ("UPDATE channel_ledger SET amount = 1", "DELETE FROM channel_ledger"):
        try:
            run_sql(app_url, q, tenant=idA)
            check(False, "ledger edit must be refused: " + q)
        except asyncpg.InsufficientPrivilegeError:
            check(True, "the app database user cannot do: " + q)
    check(run_sql(app_url, "SELECT count(*) AS c FROM channel_ledger", tenant=idX)[0]["c"] == 0, "database level: an outsider sees no ledger rows")
    check(run_sql(app_url, "SELECT count(*) AS c FROM channel_settlements", tenant=idX)[0]["c"] == 0, "database level: an outsider sees no statements")
    check(run_sql(app_url, "SELECT count(*) AS c FROM channel_ledger", tenant=idS)[0]["c"] >= 4, "database level: the reseller sees its own ledger rows")
    try:
        run_sql(app_url, "INSERT INTO channel_ledger (agreement_id, supplier_tenant_id, reseller_tenant_id, booking_id, entry_type, amount, currency, event_date, booking_ref, property_name, check_in, check_out) "
                         "VALUES ($1::uuid, $2::uuid, $3::uuid, $4::uuid, 'ACCRUAL', 999, 'BDT', now(), 'X', 'X', now(), now())", ag, idA, idS, str(uuid.uuid4()), tenant=idS)
        check(False, "a reseller must not be able to write ledger rows")
    except asyncpg.PostgresError:
        check(True, "database level: a reseller cannot write commission for itself")

    for t in (idA, idS, idX):
        c.post(f"/api/v1/platform/tenants/{t}/suspend", headers=P, json={"reason": "smoke test"})
    print(f"\n{n} checks passed")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    main(p.parse_args())
