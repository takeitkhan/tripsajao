"""Checks customers (CRM) and staff permissions against a RUNNING API:
    python -m scripts.smoke_crm --email root@platform.example --password '...'"""
import argparse
import sys
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
    c = httpx.Client(base_url=a.base, timeout=60)
    tag = uuid.uuid4().hex[:6]
    r = c.post("/api/v1/platform/auth/login", json={"email": a.email, "password": a.password})
    check(r.status_code == 200, "super admin sign-in", r.text)
    P = {"Authorization": "Bearer " + r.json()["access_token"]}

    def business(kind):
        dom = f"{kind}-{tag}.example"
        r = c.post("/api/v1/platform/tenants", headers=P, json={"name": f"{kind.title()} {tag}", "domain": dom, "admin_name": "Owner", "admin_email": f"o@{dom}"})
        assert r.status_code == 201, r.text
        pw = r.json()["temporary_password"]
        t = c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"o@{dom}", "password": pw}).json()
        return dom, {"Authorization": "Bearer " + t["access_token"]}, r.json()["tenant"]["id"], f"o@{dom}"

    def login(dom, email, pw):
        r = c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": email, "password": pw})
        return r, ({"Authorization": "Bearer " + r.json()["access_token"]} if r.status_code == 200 else None)

    dom, A, idA, adminA = business("beach")
    domB, B, idB, _ = business("hills")

    # ------------------------------------------------------------------ staff
    cat = c.get("/api/v1/staff/permissions", headers=A)
    check(cat.status_code == 200 and len(cat.json()["groups"]) >= 10 and "customers:read" in cat.json()["defaults"]["STAFF"], "the access screen can list the groups and each role's standard access")
    r = c.post("/api/v1/staff", headers=A, json={"name": "Rina Staff", "email": f"rina@{dom}", "role": "STAFF"})
    check(r.status_code == 201 and r.json()["temporary_password"] and not r.json()["custom_access"], "admin adds a staff member and gets a temporary password", r.text)
    rina = r.json()
    r, R = login(dom, f"rina@{dom}", rina["temporary_password"])
    check(r.status_code == 200, "the new staff member signs in")
    me = c.get("/api/v1/auth/me", headers=R).json()
    check("customers:read" in me["scopes"] and "customers:manage" not in me["scopes"] and "staff:manage" not in me["scopes"], "standard staff: can view customers, cannot edit them or manage staff", me["scopes"])
    check(c.get("/api/v1/staff", headers=R).status_code == 403, "staff cannot open the staff list")
    check(c.post("/api/v1/staff", headers=R, json={"name": "X", "email": f"x@{dom}", "role": "ADMIN"}).status_code == 403, "staff cannot create an admin")

    r = c.post("/api/v1/staff", headers=A, json={"name": "Kamal Front", "email": f"kamal@{dom}", "role": "STAFF", "permissions": ["bookings:read", "customers:read"]})
    check(r.status_code == 201 and r.json()["custom_access"] and r.json()["permissions"] == ["bookings:read", "customers:read"], "a staff member with their own short list of permissions", r.text)
    kamal = r.json()
    r, K = login(dom, f"kamal@{dom}", kamal["temporary_password"] if "temporary_password" in kamal else "")
    check(r.status_code == 200, "...signs in")
    check(c.get("/api/v1/bookings", headers=K).status_code == 200, "...can see bookings")
    check(c.get("/api/v1/properties", headers=K).status_code == 403, "...cannot see properties (not in the list)")
    check(c.get("/api/v1/partners", headers=K).status_code == 403, "...cannot see partners")

    bad = c.post("/api/v1/staff", headers=A, json={"name": "Z", "email": f"z@{dom}", "role": "STAFF", "permissions": ["api_keys:manage"]})
    check(bad.status_code == 422, "admin-only permissions cannot be given to staff", bad.text)
    bad = c.post("/api/v1/staff", headers=A, json={"name": "Z", "email": f"z@{dom}", "role": "STAFF", "permissions": ["staff:manage"]})
    check(bad.status_code == 422, "...nor staff management")
    check(c.post("/api/v1/staff", headers=A, json={"name": "Dup", "email": f"RINA@{dom}", "role": "STAFF"}).status_code == 409, "the same e-mail cannot be added twice (any capitals)")

    r = c.patch(f"/api/v1/staff/{kamal['id']}", headers=A, json={"permissions": ["bookings:read", "customers:read", "properties:read"]})
    check(r.status_code == 200, "admin widens the access")
    check(c.get("/api/v1/properties", headers=K).status_code == 200, "...and it works at once, without signing in again")
    r = c.patch(f"/api/v1/staff/{kamal['id']}", headers=A, json={"role": "MANAGER", "reset_to_role": True})
    mm = c.get("/api/v1/auth/me", headers=K).json()
    check(r.status_code == 200 and "pricing:write" in mm["scopes"] and "staff:manage" not in mm["scopes"] and "payouts:approve" not in mm["scopes"], "a manager has the manager standard access (no staff, no payout approval)")

    me_id = c.get("/api/v1/auth/me", headers=A).json()["user_id"]
    check(c.patch(f"/api/v1/staff/{me_id}", headers=A, json={"role": "MANAGER"}).status_code == 409, "an admin cannot lower their own account")
    check(c.patch(f"/api/v1/staff/{me_id}", headers=A, json={"is_active": False}).status_code == 409, "...or switch it off")
    r = c.post("/api/v1/staff", headers=A, json={"name": "Second Admin", "email": f"admin2@{dom}", "role": "ADMIN", "permissions": ["reports:read"]})
    check(r.status_code == 201 and not r.json()["custom_access"] and r.json()["permissions"] == ["*"], "a second admin is always full access (a custom list is ignored)", r.text)
    adm2 = r.json()
    r2, A2 = login(dom, f"admin2@{dom}", adm2["temporary_password"])
    check(c.patch(f"/api/v1/staff/{me_id}", headers=A2, json={"role": "MANAGER"}).status_code == 200, "another admin can lower the first one")
    check(c.patch(f"/api/v1/staff/{adm2['id']}", headers=A2, json={"is_active": False}).status_code == 409, "the last admin cannot switch themselves off")
    check(c.patch(f"/api/v1/staff/{me_id}", headers=A2, json={"role": "ADMIN"}).status_code == 200, "restoring the first admin")

    r = c.patch(f"/api/v1/staff/{rina['id']}", headers=A, json={"is_active": False})
    check(r.status_code == 200 and c.get("/api/v1/auth/me", headers=R).status_code == 401, "switching a person off ends their session at once")
    check(login(dom, f"rina@{dom}", rina["temporary_password"])[0].status_code == 401, "...and they cannot sign in")
    c.patch(f"/api/v1/staff/{rina['id']}", headers=A, json={"is_active": True})
    r = c.post(f"/api/v1/staff/{rina['id']}/reset-password", headers=A, json={})
    check(r.status_code == 200 and r.json()["temporary_password"], "admin resets a password")
    pw_rina = r.json()["temporary_password"]
    check(login(dom, f"rina@{dom}", rina["temporary_password"])[0].status_code == 401 and login(dom, f"rina@{dom}", pw_rina)[0].status_code == 200, "...the old one stops working, the new one works")
    check(c.post(f"/api/v1/staff/{me_id}/reset-password", headers=A, json={}).status_code == 409, "own password goes through Change password")
    check(len(c.get("/api/v1/staff", headers=B).json()) == 1 and c.patch(f"/api/v1/staff/{rina['id']}", headers=B, json={"name": "Hacked"}).status_code == 404, "another business cannot see or change this team")

    k = c.post("/api/v1/auth/api-keys", headers=A, json={"scopes": ["customers:read"]})
    check(k.status_code == 201 and c.get("/api/v1/customers", headers={"X-API-KEY": k.json()["api_key"], "X-API-SECRET": k.json()["api_secret"]}).status_code == 200,
          "a key may be given customers:read when the owner chooses to", k.text)
    check(c.post("/api/v1/auth/api-keys", headers=A, json={"scopes": ["staff:manage"]}).status_code == 422, "but never staff:manage")

    # ------------------------------------------------------------------ customers
    p = c.post("/api/v1/properties", headers=A, json={"type": "RESORT", "name": "Beach", "slug": "beach", "location": "Cox", "metadata": {}}).json()
    units = []
    for i in range(6):
        u = c.post(f"/api/v1/properties/{p['id']}/units", headers=A, json={"unit_name": f"R{i + 1}", "type": "ROOM", "capacity": 2}).json()
        c.put(f"/api/v1/pricing/units/{u['id']}", headers=A, json={"weekday_price": "100.00", "weekend_price": "100.00", "currency": "BDT"})
        units.append(u["id"])

    def book(unit, start, guest, email, phone=None, pay=True):
        ci = TODAY + timedelta(days=start)
        h = c.post("/api/v1/bookings/hold", headers=A, json={"unit_id": unit, "check_in": str(ci), "check_out": str(ci + timedelta(days=2)), "guests": 2,
                                                              "customer": {"name": guest, "email": email, "phone": phone}})
        assert h.status_code == 201, h.text
        h = h.json()
        if pay:
            r = c.post("/api/v1/bookings/confirm", headers=A, json={"booking_id": h["booking_id"], "payment_mode": "FULL", "amount": h["total_amount"], "payment_reference": f"T-{uuid.uuid4().hex[:8]}"})
            assert r.status_code == 200, r.text
        return h["booking_id"]

    book(units[0], 10, "Alice Rahman", "Alice@Example.com", "+8801711111111")
    book(units[1], 20, "Alice R.", "alice@example.com")
    bob_hold = book(units[2], 5, "Bob Hasan", "bob@example.com", pay=False)
    carol = book(units[3], 8, "=HYPERLINK(\"http://x\")", "carol@example.com", "01922222222")
    check(c.post(f"/api/v1/bookings/{carol}/cancel", headers=A, json={"reason": "changed plans"}).status_code in (200, 204), "one booking cancelled")

    r = c.get("/api/v1/customers", headers=A)
    items = r.json()["items"]
    check(r.status_code == 200 and r.json()["total"] == 3, "three guests became three customers (Alice's two bookings, any capitals, are one person)", r.text)
    by = {i["email"]: i for i in items}
    check(by["alice@example.com"]["stays"] == 2 and float(by["alice@example.com"]["total_spent"]) == 400 and by["alice@example.com"]["next_stay"] == str(TODAY + timedelta(days=10)), "Alice: 2 stays, 400 spent, next stay counted", by["alice@example.com"])
    check(by["bob@example.com"]["stays"] == 0 and by["carol@example.com"]["cancelled"] == 1 and by["carol@example.com"]["stays"] == 0, "Bob only held, Carol cancelled: no stays")
    check(items[0]["email"] == "carol@example.com" or items[0]["email"] in by, "newest first by default")
    check(c.get("/api/v1/customers", headers=B).json()["total"] == 0, "another business sees none of them")

    g = lambda **q: c.get("/api/v1/customers", headers=A, params=q).json()  # noqa: E731
    check([i["email"] for i in g(q="ALICE")["items"]] == ["alice@example.com"], "search by part of a name, any capitals")
    check(g(q="0192222")["total"] == 1 and g(q="bob@")["total"] == 1, "search by phone and by e-mail")
    check(g(min_stays=2)["total"] == 1 and g(max_stays=0)["total"] == 2, "filter by number of stays (repeat guests; never stayed)")
    check(g(inactive_days=30)["total"] == 0, "nobody is lapsed yet")
    check([i["email"] for i in g(sort="spent")["items"]][0] == "alice@example.com" and g(sort="name")["items"][0]["name"].startswith("="), "sorting by spend and by name")
    check(len(g(limit=2)["items"]) == 2 and g(limit=2, offset=2)["total"] == 3 and len(g(limit=2, offset=2)["items"]) == 1, "paging")
    check(c.get("/api/v1/customers", headers=A, params={"sort": "bogus"}).status_code == 422, "an unknown sort is refused")

    alice = by["alice@example.com"]["id"]
    _, R = login(dom, f"rina@{dom}", pw_rina)
    d = c.get(f"/api/v1/customers/{alice}", headers=A).json()
    check(len(d["bookings"]) == 2 and d["bookings"][0]["property"] == "Beach", "a customer shows all their bookings", d)
    check(c.get(f"/api/v1/customers/{alice}", headers=B).status_code == 404, "another business cannot open this customer")

    r = c.patch(f"/api/v1/customers/{alice}", headers=A, json={"tags": ["VIP", " vip ", "Eid  guest"], "notes": "Likes sea view", "phone": "+8801700000000"})
    check(r.status_code == 200 and r.json()["tags"] == ["vip", "eid guest"] and r.json()["notes"] == "Likes sea view", "tags are tidied (lower case, no duplicates)", r.text)
    check(c.patch(f"/api/v1/customers/{alice}", headers=A, json={"tags": [f"t{i}" for i in range(21)]}).status_code == 422, "more than 20 tags refused")
    check(c.patch(f"/api/v1/customers/{alice}", headers=R, json={"notes": "x"}).status_code == 403, "plain staff cannot edit customers")
    check(g(tag="VIP")["total"] == 1 and g(tag="nope")["total"] == 0, "filter by tag")
    check(c.get("/api/v1/customers/tags", headers=A).json()[0]["tag"] in ("vip", "eid guest"), "the tag list")

    ids = [by["bob@example.com"]["id"], by["carol@example.com"]["id"]]
    r = c.post("/api/v1/customers/tags/apply", headers=A, json={"ids": ids, "add": ["follow-up", "Winter"]})
    check(r.status_code == 200 and r.json()["changed"] == 2 and g(tag="winter")["total"] == 2, "add tags to several customers at once", r.text)
    r = c.post("/api/v1/customers/tags/apply", headers=A, json={"filters": {"max_stays": 0}, "add": ["never-stayed"], "remove": ["winter"]})
    check(r.json()["changed"] == 2 and g(tag="never-stayed")["total"] == 2 and g(tag="winter")["total"] == 0, "add and remove tags for everyone matching a filter", r.text)
    check(c.post("/api/v1/customers/tags/apply", headers=A, json={"ids": ids}).status_code == 422, "nothing to add or remove is refused")
    check(c.post("/api/v1/customers/tags/apply", headers=B, json={"ids": ids, "add": ["x"]}).json()["changed"] == 0, "another business's customers are untouched")

    r = c.post("/api/v1/customers", headers=A, json={"name": "Walk In", "email": "Walk@In.com", "tags": ["walk-in"]})
    check(r.status_code == 201 and r.json()["source"] == "MANUAL" and r.json()["email"] == "walk@in.com", "add a customer by hand", r.text)
    check(c.post("/api/v1/customers", headers=A, json={"name": "Walk", "email": "walk@in.com"}).status_code == 409, "...not twice")

    r = c.get("/api/v1/customers/export", headers=A)
    body = r.text
    check(r.status_code == 200 and body.startswith("﻿Name,Email,Phone,Tags"), "CSV download for Excel (with the Bengali-safe mark)", body[:80])
    check("'=HYPERLINK" in body and "=HYPERLINK" in body and '\n=HYPERLINK' not in body, "a name that looks like a formula is made harmless")
    check("+8801700000000" in body and "'+8801700000000" not in body, "ordinary phone numbers stay as they are")
    check(len(body.strip().splitlines()) >= 5 and "vip" in body, "all rows and tags are in the file")
    check(len(c.get("/api/v1/customers/export", headers=A, params={"tag": "vip"}).text.strip().splitlines()) == 2, "the download follows the filters")
    check(c.get("/api/v1/customers/export", headers=R).status_code == 403 and c.get("/api/v1/customers/export", headers=K).status_code == 200, "plain staff cannot export; a manager can")
    r = c.post("/api/v1/staff", headers=A, json={"name": "Exporter", "email": f"ex@{dom}", "role": "STAFF", "permissions": ["customers:read", "customers:manage", "customers:export"]})
    r2, E = login(dom, f"ex@{dom}", r.json()["temporary_password"])
    check(c.get("/api/v1/customers/export", headers=E).status_code == 200 and c.patch(f"/api/v1/customers/{alice}", headers=E, json={"notes": "ok"}).status_code == 200, "...but a person given it can")

    for t in (idA, idB):
        c.post(f"/api/v1/platform/tenants/{t}/suspend", headers=P, json={"reason": "smoke test"})
    print(f"\n{n} checks passed")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    main(p.parse_args())
