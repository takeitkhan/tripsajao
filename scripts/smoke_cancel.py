"""Checks reseller cancellation and refunds (and the reseller API-key path) against a RUNNING API:
    python -m scripts.smoke_cancel --email root@platform.example --password '...'"""
import argparse
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

TODAY = datetime.now(timezone.utc).date()   # the app counts days in the business time zone, UTC unless set

import httpx

n = 0


def check(cond, msg, extra=None):
    global n
    if not cond:
        print("FAIL:", msg, extra if extra is not None else "")
        sys.exit(1)
    n += 1
    print("  ok ", msg)


def main(a):
    c = httpx.Client(base_url=a.base, timeout=60)
    tag = uuid.uuid4().hex[:6]
    r = c.post("/api/v1/platform/auth/login", json={"email": a.email, "password": a.password})
    check(r.status_code == 200, "super admin sign-in", r.text)
    P = {"Authorization": "Bearer " + r.json()["access_token"]}

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
    for i in range(4):
        u = c.post(f"/api/v1/properties/{p['id']}/units", headers=A, json={"unit_name": f"R{i + 1}", "type": "ROOM", "capacity": 2}).json()
        c.put(f"/api/v1/pricing/units/{u['id']}", headers=A, json={"weekday_price": "100.00", "weekend_price": "100.00", "currency": "BDT"})
        units.append(u["id"])
    api = "/api/v1/channel"
    ag = c.post(f"{api}/agreements/request", headers=S, json={"owner_domain": domA}).json()["id"]
    c.post(f"{api}/agreements/{ag}/accept", headers=A, json={"commission_type": "FLAT", "commission_value": "50", "properties": [{"property_id": p["id"]}]})

    # ---- the reseller's own website: API key with only the two reseller permissions
    k = c.post("/api/v1/auth/api-keys", headers=S, json={"scopes": ["channel:read", "channel:book"]})
    check(k.status_code == 201, "reseller creates an API key for its website", k.text)
    K = {"X-API-KEY": k.json()["api_key"], "X-API-SECRET": k.json()["api_secret"]}
    check(c.get(f"{api}/agreements", headers=K).json()[0]["id"] == ag, "the website finds its agreement with the API key")
    check(len(c.get(f"{api}/properties", headers=K).json()) == 1, "...and the granted property")
    check(c.put(f"{api}/cancellation-policy", headers=K, json={"rules": [{"days_before": 0, "refund_percent": 0}]}).status_code == 403, "the key cannot change anyone's rules (no manage permission)")
    check(c.post(f"{api}/agreements/request", headers=K, json={"owner_domain": domX}).status_code == 403, "the key cannot start agreements")

    def sell(unit, start_in, pay=True):
        ci = TODAY + timedelta(days=start_in)
        h = c.post(f"{api}/hold", headers=K, json={"agreement_id": ag, "property_id": p["id"], "unit_id": unit, "check_in": str(ci), "check_out": str(ci + timedelta(days=3)),
                                                    "guests": 2, "customer": {"name": f"Guest {start_in}", "email": "g@example.com", "phone": "+8801700000000"}})
        assert h.status_code == 201, h.text
        h = h.json()
        if pay:
            r = c.post(f"{api}/confirm", headers=K, json={"agreement_id": ag, "booking_id": h["booking_id"], "payment_mode": "FULL", "amount": h["total_amount"], "payment_reference": f"TXN-{uuid.uuid4().hex[:6]}"})
            assert r.status_code == 200, r.text
        return h["booking_id"]

    b1, b2, b3 = sell(units[0], 20), sell(units[1], 5), sell(units[2], 1)
    b4 = sell(units[3], 30, pay=False)
    check(True, "the website sold three rooms and held a fourth, with the API key only")

    # ---- the refund comes from the owner's rules: default 7+ days 100%, 3+ days 50%, otherwise 0
    def quote(b, H=K):
        return c.get(f"{api}/bookings/{b}/cancel-quote", headers=H, params={"agreement_id": ag})
    q1, q2, q3 = quote(b1).json(), quote(b2).json(), quote(b3).json()
    check(q1["days_before"] == 20 and float(q1["refund_percent"]) == 100 and float(q1["refund_amount"]) == 300 and q1["can_request"], "20 days ahead: full refund of 300", q1)
    check(float(q2["refund_percent"]) == 50 and float(q2["refund_amount"]) == 150, "5 days ahead: 50%, 150", q2)
    check(float(q3["refund_percent"]) == 0 and float(q3["refund_amount"]) == 0 and "No refund" in q3["rule_text"], "1 day ahead: no refund", q3)
    q4 = quote(b4).json()
    check(not q4["can_request"] and "unpaid hold" in q4["why_not"], "an unpaid hold is not cancelled this way", q4)
    check(quote(b1, X).status_code == 404 and quote(b1, A).status_code == 403, "an outsider and the owner cannot use the reseller's quote")
    pol = c.get(f"{api}/cancellation-policy", headers=A).json()
    check(pol["is_default"] and len(pol["rules"]) == 3, "the owner sees the default rules", pol)

    # ---- the owner sets its own rules
    check(c.put(f"{api}/cancellation-policy", headers=A, json={"rules": [{"days_before": 7, "refund_percent": 100}, {"days_before": 7, "refund_percent": 50}]}).status_code == 422, "two rules with the same days refused")
    check(c.put(f"{api}/cancellation-policy", headers=A, json={"rules": [{"days_before": 7, "refund_percent": 120}]}).status_code == 422, "refund over 100% refused")
    r = c.put(f"{api}/cancellation-policy", headers=A, json={"rules": [{"days_before": 14, "refund_percent": 100}, {"days_before": 7, "refund_percent": 50}]})
    check(r.status_code == 200 and not r.json()["is_default"] and r.json()["rules"][0]["days_before"] == 14, "owner saves its own rules", r.text)
    check(float(quote(b1).json()["refund_amount"]) == 300 and float(quote(b2).json()["refund_amount"]) == 0, "new rules apply: 5 days ahead is now no refund", quote(b2).json())
    c.put(f"{api}/cancellation-policy", headers=A, json={"rules": [{"days_before": 14, "refund_percent": 100}, {"days_before": 3, "refund_percent": 50}, {"days_before": 0, "refund_percent": 0}]})

    # ---- ask -> owner confirms with a smaller refund
    r = c.post(f"{api}/bookings/{b1}/cancel-request", headers=K, json={"agreement_id": ag, "reason": "Guest fell ill"})
    check(r.status_code == 201 and r.json()["status"] == "REQUESTED" and float(r.json()["suggested_refund"]) == 300 and r.json()["role"] == "RESELLER", "reseller asks to cancel", r.text)
    cid = r.json()["id"]
    check(c.post(f"{api}/bookings/{b1}/cancel-request", headers=K, json={"agreement_id": ag, "reason": "again"}).status_code == 409, "cannot ask twice")
    check(c.post(f"{api}/bookings/{b1}/cancel-request", headers=K, json={"agreement_id": ag, "reason": "x"}).status_code == 422, "a reason is required")
    check(c.post(f"{api}/bookings/{b1}/cancel-request", headers={**X}, json={"agreement_id": ag, "reason": "hello there"}).status_code in (401, 404), "an outsider cannot ask")
    check(c.get("/api/v1/auth/me", headers=A).json()["channel"]["waiting"] == 1, "the owner's menu badge counts the request")
    ol = c.get(f"{api}/cancellations", headers=A, params={"status": "REQUESTED"}).json()
    check(len(ol) == 1 and ol[0]["role"] == "OWNER" and ol[0]["guest"] == "Guest 20" and ol[0]["counterpart"].startswith("Sunrise") and ol[0]["reason"] == "Guest fell ill", "owner sees the request with guest and reason", ol)
    rl = c.get(f"{api}/cancellations", headers=K).json()
    check(len(rl) == 1 and rl[0]["role"] == "RESELLER" and rl[0]["id"] == cid, "reseller sees its own request", rl)
    check(c.get(f"{api}/cancellations", headers=X).json() == [], "an outsider sees none")
    check(c.post(f"{api}/cancellations/{cid}/confirm", headers=S, json={}).status_code == 404, "the reseller cannot decide (not in its business)")
    check(c.post(f"{api}/cancellations/{cid}/confirm", headers=A, json={"refund_amount": "400.00"}).status_code == 422, "refund above what was paid refused")
    r = c.post(f"{api}/cancellations/{cid}/confirm", headers=A, json={"refund_amount": "250.00", "note": "Goodwill, minus bank fees"})
    check(r.status_code == 200 and r.json()["status"] == "CONFIRMED" and float(r.json()["refund_amount"]) == 250, "owner confirms and refunds 250", r.text)
    ob = [b for b in c.get("/api/v1/bookings", headers=A).json()["items"] if b["id"] == b1][0]
    check(ob["status"] == "CANCELLED", "the booking is cancelled in the owner's calendar", ob["status"])
    check(any(u["unit_id"] == units[0] for u in c.get("/api/v1/bookings/availability", headers=A, params={"property_id": p["id"], "check_in": str(TODAY + timedelta(days=20)), "check_out": str(TODAY + timedelta(days=23))}).json()), "the room is free to sell again")
    mine = [b for b in c.get(f"{api}/bookings", headers=K).json()["items"] if b["id"] == b1][0]
    check(mine["status"] == "CANCELLED" and mine["cancellation"]["status"] == "CONFIRMED" and float(mine["cancellation"]["refund_amount"]) == 250, "the reseller sees it cancelled with the refund", mine)
    check(c.post(f"{api}/cancellations/{cid}/confirm", headers=A, json={}).status_code == 409, "a decided request cannot be decided again")
    check(c.get("/api/v1/auth/me", headers=A).json()["channel"]["waiting"] == 0, "badge goes back to zero")

    # ---- ask -> owner declines -> ask again -> reseller takes it back
    r = c.post(f"{api}/bookings/{b2}/cancel-request", headers=K, json={"agreement_id": ag, "reason": "Changed plans"})
    c2 = r.json()["id"]
    check(r.status_code == 201 and float(r.json()["suggested_refund"]) == 150, "second request, suggested refund 150", r.text)
    check(c.post(f"{api}/cancellations/{c2}/decline", headers=A, json={"note": "x"}).status_code == 422, "a decline needs a reason")
    r = c.post(f"{api}/cancellations/{c2}/decline", headers=A, json={"note": "Peak week, no cancellations"})
    check(r.status_code == 200 and r.json()["status"] == "DECLINED", "owner declines", r.text)
    ob = [b for b in c.get("/api/v1/bookings", headers=A).json()["items"] if b["id"] == b2][0]
    check(ob["status"] == "CONFIRMED", "the booking stays confirmed")
    mine = [b for b in c.get(f"{api}/bookings", headers=K).json()["items"] if b["id"] == b2][0]
    check(mine["cancellation"]["status"] == "DECLINED" and mine["cancellation"]["decision_note"] == "Peak week, no cancellations", "the reseller sees the owner's reason", mine["cancellation"])
    r = c.post(f"{api}/bookings/{b2}/cancel-request", headers=K, json={"agreement_id": ag, "reason": "Guest insists"})
    check(r.status_code == 201, "after a decline the reseller may ask again", r.text)
    c3 = r.json()["id"]
    r = c.post(f"{api}/cancellations/{c3}/withdraw", params={"agreement_id": ag}, headers=K)
    check(r.status_code == 200 and r.json()["status"] == "WITHDRAWN", "reseller takes the request back", r.text)
    check(c.post(f"{api}/cancellations/{c3}/confirm", headers=A, json={}).status_code == 409, "the owner cannot confirm a withdrawn request")

    # ---- a stay that has started cannot be cancelled this way
    import asyncio, asyncpg
    from app.core.config import settings

    async def shift():
        conn = await asyncpg.connect(settings.database_url_migrations.replace("+asyncpg", ""))
        await conn.execute("UPDATE bookings SET check_in = current_date - 1, check_out = current_date + 2 WHERE id = $1::uuid", b3)
        await conn.close()
    asyncio.run(shift())
    r = c.post(f"{api}/bookings/{b3}/cancel-request", headers=K, json={"agreement_id": ag, "reason": "Guest left early"})
    check(r.status_code == 409 and "already started" in r.text, "once the stay has started it cannot be cancelled this way", r.text)

    for t in (idA, idS, idX):
        c.post(f"/api/v1/platform/tenants/{t}/suspend", headers=P, json={"reason": "smoke test"})
    print(f"\n{n} checks passed")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    main(p.parse_args())
