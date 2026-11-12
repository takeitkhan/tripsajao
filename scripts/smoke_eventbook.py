"""Checks event bookings (seat holds, manual payment proof, confirmation, partner commission) against a RUNNING API:
    PYTHONPATH=. python scripts/smoke_eventbook.py --email root@platform.example --password '...'"""
import argparse
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx

TODAY = datetime.now(timezone.utc).date()
n = 0


def check(cond, msg, extra=None):
    global n
    if not cond:
        print("FAIL:", msg, extra if extra is not None else "")
        sys.exit(1)
    n += 1
    print("  ok ", msg)


def main(a):
    c = httpx.Client(base_url=a.base, timeout=60, follow_redirects=False)
    tag = uuid.uuid4().hex[:6]
    r = c.post("/api/v1/platform/auth/login", json={"email": a.email, "password": a.password})
    P = {"Authorization": "Bearer " + r.json()["access_token"]}
    dom = f"evb-{tag}.example"
    r = c.post("/api/v1/platform/tenants", headers=P, json={"name": f"Evb {tag}", "domain": dom, "admin_name": "Owner", "admin_email": f"o@{dom}"})
    t = c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"o@{dom}", "password": r.json()["temporary_password"]}).json()
    A = {"Authorization": "Bearer " + t["access_token"]}
    d = lambda k: (TODAY + timedelta(days=k)).isoformat()

    ev = c.post("/api/v1/events", headers=A, json={"title": "Sajek weekend", "starts_on": d(10), "ends_on": d(12), "price": "5000", "seats": 3, "status": "PUBLISHED",
                                                    "payment_methods": ["bKash", "Bank transfer"]}).json()
    draft = c.post("/api/v1/events", headers=A, json={"title": "Hidden", "starts_on": d(10), "price": "100", "seats": 3}).json()
    k = c.post("/api/v1/auth/api-keys", headers=A, json={"scopes": ["events:read", "events:book"]})
    check(k.status_code in (200, 201), "a website key may hold events:book", k.text)
    W = {"X-API-KEY": k.json()["api_key"], "X-API-SECRET": k.json()["api_secret"]}
    for sc in ("api_keys:manage", "staff:manage"):
        check(c.post("/api/v1/auth/api-keys", headers=A, json={"scopes": [sc]}).status_code == 422, f"no key can ever have {sc}")
    me = {"name": "Rafi Ahmed", "email": f"rafi{tag}@example.com", "phone": "01711000000", "guest_names": ["Nadia"]}

    check(c.get(f"/api/v1/events/{ev['slug']}", headers=W).json()["seats_left"] == 3, "a website sees how many seats are left")
    check(c.post(f"/api/v1/events/{draft['id']}/hold", headers=W, json={"seats": 1, "customer": me}).status_code == 404, "a draft event cannot be booked from a website")
    check(c.post(f"/api/v1/events/{ev['id']}/hold", headers=W, json={"seats": 1, "customer": {**me, "phone": "1"}}).status_code == 422, "customer details are required and checked")
    check(c.post(f"/api/v1/events/{ev['id']}/hold", json={"seats": 1, "customer": me}).status_code in (401, 403), "no key, no booking")

    # a partner link is carried into the booking
    pr = c.post("/api/v1/partners", headers=A, json={"name": f"Agent {tag}", "email": f"p{tag}@example.com", "password": "Str0ng-Passw0rd!", "partner_type": "B2B",
                                                      "commission_type": "PERCENT", "commission_value": "10"}).json()
    ref = c.get(f"/go/{pr['vanity_code']}").cookies.get("_ref_token")
    r = c.post(f"/api/v1/events/{ev['id']}/hold", headers=W, cookies={"_ref_token": ref}, json={"seats": 2, "customer": me})
    h = r.json()
    check(r.status_code == 201 and h["total_amount"] == "10000.00" and h["seconds_remaining"] == 600 and h["partner_attributed"] and h["token"] and h["payment_methods"] == ["bKash", "Bank transfer"],
          "step 1: two seats are held for 10 minutes and the partner is attributed", r.text)
    T = {**W, "X-Booking-Token": h["token"]}
    check(c.get(f"/api/v1/events/{ev['slug']}", headers=W).json()["seats_left"] == 1, "held seats are taken off the count straight away")
    r = c.post(f"/api/v1/events/{ev['id']}/hold", headers=W, json={"seats": 2, "customer": me})
    check(r.status_code == 409 and "1 seat left" in r.json()["detail"], "nobody can take more seats than are left", r.text)
    h2 = c.post(f"/api/v1/events/{ev['id']}/hold", headers=W, json={"seats": 1, "customer": {**me, "email": f"other{tag}@example.com"}}).json()
    check(c.post(f"/api/v1/events/{ev['id']}/hold", headers=W, json={"seats": 1, "customer": me}).status_code == 409, "the event is full after the last seat is held")

    # who can see the booking
    ref_ = h["booking_ref"]
    check(c.get(f"/api/v1/event-bookings/status/{ref_}", headers=W).status_code == 404, "the booking is not shown without its token")
    check(c.get(f"/api/v1/event-bookings/status/{ref_}", headers={**W, "X-Booking-Token": "wrong"}).status_code == 404, "...nor with a wrong token")
    s = c.get(f"/api/v1/event-bookings/status/{ref_}", headers=T).json()
    check(s["status"] == "HOLD" and s["balance_due"] == "10000.00" and s["event_title"] == "Sajek weekend", "the customer sees their booking with the token")

    # payment needs a screenshot first
    pay = {"method": "bKash", "amount": "5000", "trx_id": "9XK2L", "sender": "01711000000"}
    check(c.post(f"/api/v1/event-bookings/status/{ref_}/payment", headers=T, json=pay).status_code == 422, "step 3 without a screenshot is refused")
    with open("/tmp/proof.png", "rb") as f:
        r = c.post(f"/api/v1/event-bookings/status/{ref_}/proof", headers=T, files={"file": ("shot.png", f, "image/png")})
    check(r.status_code == 201 and r.json()["url"], "step 2: a payment screenshot is uploaded", r.text)
    check(c.post(f"/api/v1/event-bookings/status/{ref_}/proof", headers=T, files={"file": ("x.txt", b"hello", "text/plain")}).status_code in (415, 422), "something that is not a picture is refused")
    check(c.post(f"/api/v1/event-bookings/status/{ref_}/payment", headers=T, json={**pay, "method": "Cheque"}).status_code == 422, "only the event's payment methods are accepted")
    check(c.post(f"/api/v1/event-bookings/status/{ref_}/payment", headers=T, json={**pay, "amount": "20000"}).status_code == 422, "paying more than is due is refused")
    r = c.post(f"/api/v1/event-bookings/status/{ref_}/payment", headers=T, json=pay)
    check(r.status_code == 200 and r.json()["status"] == "PAYMENT_SUBMITTED" and r.json()["hold_expires_at"] is None and r.json()["payments"][0]["status"] == "SUBMITTED", "step 3: the payment is sent and the seats stay reserved", r.text)
    check(c.post(f"/api/v1/event-bookings/status/{ref_}/payment", headers=T, json=pay).status_code == 409, "a second payment is refused while one waits to be checked")

    # the business side
    check(c.get("/api/v1/event-bookings", headers=W).status_code == 403, "a website key cannot list bookings")
    lst = c.get("/api/v1/event-bookings?status=PAYMENT_SUBMITTED", headers=A).json()
    row = lst["items"][0]
    check(lst["total"] == 1 and row["booking_ref"] == ref_ and row["partner_name"] == f"Agent {tag}" and row["event_title"] == "Sajek weekend" and row["payments_json"][0]["proofs"], "the business sees it with the screenshot and the partner")
    check(c.get(f"/api/v1/event-bookings?q=01711000000", headers=A).json()["total"] == 2, "bookings can be searched by phone number")
    pid = row["payments_json"][0]["id"]
    r = c.post(f"/api/v1/event-bookings/{row['id']}/payments/{pid}/reject", headers=A, json={"reason": "No such transaction"})
    check(r.status_code == 200 and r.json()["status"] == "HOLD" and r.json()["payments_json"][0]["status"] == "REJECTED" and r.json()["hold_expires_at"], "a rejected payment gives the customer a fresh 10 minutes", r.text)
    check(c.post(f"/api/v1/event-bookings/{row['id']}/payments/{pid}/reject", headers=A, json={}).status_code == 409, "a payment is decided only once")
    with open("/tmp/proof.png", "rb") as f:
        c.post(f"/api/v1/event-bookings/status/{ref_}/proof", headers=T, files={"file": ("shot.png", f, "image/png")})
    c.post(f"/api/v1/event-bookings/status/{ref_}/payment", headers=T, json={**pay, "amount": "5000", "trx_id": "NEW1"})
    row = c.get(f"/api/v1/event-bookings/{row['id']}", headers=A).json()
    pid = row["payments_json"][-1]["id"]
    r = c.post(f"/api/v1/event-bookings/{row['id']}/payments/{pid}/verify", headers=A, json={})
    check(r.status_code == 200 and r.json()["status"] == "CONFIRMED" and r.json()["paid_amount"] == "5000.00", "a deposit confirms the booking with the balance still due", r.text)
    led = c.get(f"/api/v1/partners/{pr['id']}/ledger", headers=A)
    bal = sum(float(e["credit"]) - float(e["debit"]) for e in led.json()["entries"])
    check(abs(bal - 500.0) < 0.01, "the partner earns commission on what was really paid (10% of 5000)", led.text[:300])
    # pay the balance
    with open("/tmp/proof.png", "rb") as f:
        c.post(f"/api/v1/event-bookings/status/{ref_}/proof", headers=T, files={"file": ("shot.png", f, "image/png")})
    r = c.post(f"/api/v1/event-bookings/status/{ref_}/payment", headers=T, json={**pay, "amount": "5000", "trx_id": "BAL2"})
    check(r.status_code == 200 and r.json()["status"] == "CONFIRMED", "the balance can be paid later", r.text)
    row = c.get(f"/api/v1/event-bookings/{row['id']}", headers=A).json()
    c.post(f"/api/v1/event-bookings/{row['id']}/payments/{row['payments_json'][-1]['id']}/verify", headers=A, json={})
    led = c.get(f"/api/v1/partners/{pr['id']}/ledger", headers=A).json()
    bal = sum(float(e["credit"]) - float(e["debit"]) for e in led["entries"])
    check(abs(bal - 1000.0) < 0.01, "the full commission is earned once everything is paid", led)
    # cancel
    r = c.post(f"/api/v1/event-bookings/{row['id']}/cancel", headers=A, json={"reason": "Customer asked"})
    check(r.status_code == 200 and r.json()["status"] == "CANCELLED", "a booking can be cancelled")
    led = c.get(f"/api/v1/partners/{pr['id']}/ledger", headers=A).json()
    check(abs(sum(float(e["credit"]) - float(e["debit"]) for e in led["entries"])) < 0.01, "cancelling reverses the partner's commission")
    check(c.get(f"/api/v1/events/{ev['slug']}", headers=W).json()["seats_left"] == 2, "cancelled seats are free again (1 still held by the other guest)")
    check(c.post(f"/api/v1/event-bookings/{row['id']}/cancel", headers=A, json={}).status_code == 200, "cancelling twice is harmless")

    # the hold runs out
    c2 = httpx.Client(base_url=a.base, timeout=60)
    import subprocess, os
    subprocess.run(["psql", os.environ.get("PSQL_URL", "postgresql://propsaas_owner:owner_pw@localhost:5432/propsaas"), "-c",
                    f"UPDATE event_bookings SET hold_expires_at = now() - interval '1 second' WHERE booking_ref = '{h2['booking_ref']}'"], capture_output=True)
    check(c.get(f"/api/v1/events/{ev['slug']}", headers=W).json()["seats_left"] == 3, "a hold that ran out gives its seat back")
    T2 = {**W, "X-Booking-Token": h2["token"]}
    check(c.post(f"/api/v1/event-bookings/status/{h2['booking_ref']}/payment", headers=T2, json=pay).status_code in (410, 422), "an expired hold cannot be paid")
    check(c.get(f"/api/v1/event-bookings/status/{h2['booking_ref']}", headers=T2).json()["status"] == "EXPIRED", "...and shows as expired")

    # customers and isolation
    cu = c.get("/api/v1/customers?q=rafi", headers=A).json()
    check(cu["total"] == 2, "both guests are now customers in the CRM", cu)
    dom2 = f"evb2-{tag}.example"
    r = c.post("/api/v1/platform/tenants", headers=P, json={"name": f"Other {tag}", "domain": dom2, "admin_name": "Owner Two", "admin_email": f"o@{dom2}"})
    check(r.status_code == 201, "second business created", r.text)
    t2 = c.post("/api/v1/auth/login", json={"tenant_domain": dom2, "email": f"o@{dom2}", "password": r.json()["temporary_password"]}).json()
    B = {"Authorization": "Bearer " + t2["access_token"]}
    check(c.get(f"/api/v1/event-bookings/{row['id']}", headers=B).status_code == 404 and c.get("/api/v1/event-bookings", headers=B).json()["total"] == 0, "another business sees none of it")
    d = c.get("/api/v1/docs/module/event_bookings", headers=A)
    check(d.status_code == 200 and len(d.json()["endpoints"]) >= 8, "the API documentation lists the booking calls", d.text[:200])
    print(f"\n{n} checks passed")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    main(p.parse_args())
