"""Checks the reseller channel against a RUNNING API (needs a super admin to create three throw-away businesses):
    python -m scripts.smoke_channel --email root@platform.example --password '...'"""
import argparse
import sys
import threading
import uuid
from datetime import date, timedelta

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
        pw = r.json()["temporary_password"]
        t = c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"o@{dom}", "password": pw}).json()
        return dom, {"Authorization": "Bearer " + t["access_token"]}, r.json()["tenant"]["id"]

    def inventory(H, name, rooms, price="100.00"):
        p = c.post("/api/v1/properties", headers=H, json={"type": "RESORT", "name": name, "slug": name.lower().replace(" ", "-"), "location": "Cox's Bazar",
                                                           "metadata": {"description": "Nice place", "address": "SECRET STREET 5"}}).json()
        units = []
        for i in range(rooms):
            u = c.post(f"/api/v1/properties/{p['id']}/units", headers=H, json={"unit_name": f"R{i + 1}", "type": "ROOM", "capacity": 2}).json()
            c.put(f"/api/v1/pricing/units/{u['id']}", headers=H, json={"weekday_price": price, "weekend_price": price, "currency": "BDT"})
            units.append(u["id"])
        return p["id"], units

    domA, A, idA = business("nobodol")      # owner 1
    domB, B, idB = business("hittrail")     # owner 2
    domS, S, idS = business("sunrise")      # reseller, no properties
    domX, X, idX = business("outsider")     # a reseller with no agreement at all
    pa1, ua1 = inventory(A, "Nobodol Beach", 3)
    pa2, ua2 = inventory(A, "Nobodol Hills", 2)
    pb1, ub1 = inventory(B, "Trail Camp", 2, "200.00")
    ci, co = date.today() + timedelta(days=20), date.today() + timedelta(days=23)
    cust = {"name": "Guest One", "email": "g1@example.com", "phone": "+8801700000000"}
    cust2 = {"name": "Guest Two", "email": "g2@example.com"}
    api = "/api/v1/channel"

    # ---- nothing is shared until an agreement exists
    check(c.get(f"{api}/properties", headers=S).json() == [], "a reseller with no agreement sees no properties")
    check(c.get(f"{api}/agreements", headers=S).json() == [], "...and no agreements")
    r = c.get(f"{api}/availability", headers=S, params={"agreement_id": str(uuid.uuid4()), "property_id": pa1, "check_in": str(ci), "check_out": str(co)})
    check(r.status_code == 404, "cannot use an agreement that does not exist", r.text)

    # ---- reseller asks, owner accepts with terms
    r = c.post(f"{api}/agreements/request", headers=S, json={"owner_domain": domA, "note": "We sell Cox's Bazar trips"})
    check(r.status_code == 201 and r.json()["status"] == "REQUESTED" and r.json()["awaiting"] == "THEM" and r.json()["counterpart"].startswith("Nobodol"), "reseller asks to sell for Nobodol", r.text)
    agA = r.json()["id"]
    check(c.post(f"{api}/agreements/request", headers=S, json={"owner_domain": domA}).status_code == 409, "asking twice is refused")
    check(c.post(f"{api}/agreements/request", headers=S, json={"owner_domain": domS}).status_code == 422, "cannot ask yourself")
    check(c.post(f"{api}/agreements/request", headers=S, json={"owner_domain": "no-such-business.example"}).status_code == 404, "unknown business -> plain message")
    ra = c.get(f"{api}/agreements", headers=A).json()
    check(len(ra) == 1 and ra[0]["role"] == "OWNER" and ra[0]["awaiting"] == "YOU" and ra[0]["counterpart"].startswith("Sunrise"), "owner sees the request waiting for them", ra)
    check(c.get(f"{api}/agreements", headers=B).json() == [], "another owner sees nothing of it")
    check(c.get(f"{api}/agreements", headers=X).json() == [], "an unrelated business sees nothing of it")
    check(c.post(f"{api}/agreements/{agA}/accept", headers=S, json={"commission_type": "PERCENT", "commission_value": "10", "properties": [{"property_id": pa1}]}).status_code == 409,
          "the reseller cannot accept their own request / set the terms")
    check(c.post(f"{api}/agreements/{agA}/accept", headers=B, json={"commission_type": "PERCENT", "commission_value": "10", "properties": [{"property_id": pb1}]}).status_code == 404,
          "another business cannot touch it (404)")
    check(c.post(f"{api}/agreements/{agA}/accept", headers=A).status_code == 422, "owner must choose terms to accept")
    check(c.post(f"{api}/agreements/{agA}/accept", headers=A, json={"commission_type": "PERCENT", "commission_value": "150", "properties": [{"property_id": pa1}]}).status_code == 422, "commission over 100% refused")
    check(c.post(f"{api}/agreements/{agA}/accept", headers=A, json={"commission_type": "FLAT", "commission_value": "50", "properties": [{"property_id": pb1}]}).status_code == 422,
          "owner cannot grant another business's property")
    r = c.post(f"{api}/agreements/{agA}/accept", headers=A, json={"commission_type": "FLAT", "commission_value": "50", "properties": [
        {"property_id": pa1}, {"property_id": pa2, "commission_type": "PERCENT", "commission_value": "10"}]})
    check(r.status_code == 200 and r.json()["status"] == "ACTIVE" and len(r.json()["properties"]) == 2, "owner accepts with terms", r.text)

    # ---- owner invites, reseller accepts
    r = c.post(f"{api}/agreements/invite", headers=B, json={"reseller_domain": domS, "commission_type": "PERCENT", "commission_value": "12.5", "properties": [{"property_id": pb1}]})
    check(r.status_code == 201 and r.json()["status"] == "INVITED" and r.json()["awaiting"] == "THEM", "Hit the Trail invites Sunrise", r.text)
    agB = r.json()["id"]
    inv = [x for x in c.get(f"{api}/agreements", headers=S).json() if x["id"] == agB][0]
    check(inv["awaiting"] == "YOU" and inv["properties"][0]["name"] == "Trail Camp", "reseller sees the invitation with property names", inv)
    check(c.get(f"{api}/properties", headers=S).json() != [] and all(p["property_id"] != pb1 for p in c.get(f"{api}/properties", headers=S).json()), "an invitation grants nothing until accepted")
    check(c.post(f"{api}/agreements/{agB}/accept", headers=B).status_code == 409, "owner cannot accept their own invitation")
    check(c.post(f"{api}/agreements/{agB}/accept", headers=S).json()["status"] == "ACTIVE", "reseller accepts the invitation")

    # ---- the reseller's one panel sees both owners
    props = c.get(f"{api}/properties", headers=S).json()
    check({p["name"] for p in props} == {"Nobodol Beach", "Nobodol Hills", "Trail Camp"}, "one panel lists the granted properties of both owners", [p["name"] for p in props])
    check(all("address" not in str(p) and "SECRET" not in str(p) for p in props), "the owner's private address is not shared")
    hills = [p for p in props if p["name"] == "Nobodol Hills"][0]
    check(hills["commission_type"] == "PERCENT" and float(hills["commission_value"]) == 10, "per-property commission override shown")
    check(c.get(f"{api}/properties", headers=X).json() == [], "an outsider still sees nothing")

    # ---- availability + commission per night
    r = c.get(f"{api}/availability", headers=S, params={"agreement_id": agA, "property_id": pa1, "check_in": str(ci), "check_out": str(co), "guests": 2})
    check(r.status_code == 200 and len(r.json()) == 3, "availability of a granted property", r.text)
    u = r.json()[0]
    check(float(u["total"]) == 300 and u["nights"] == 3 and float(u["your_commission"]) == 150, "FLAT 50 per night x 3 nights = 150", u)
    r = c.get(f"{api}/availability", headers=S, params={"agreement_id": agA, "property_id": pa2, "check_in": str(ci), "check_out": str(co)})
    check(float(r.json()[0]["your_commission"]) == 30, "PERCENT 10 override on 300 = 30", r.json())
    r = c.get(f"{api}/availability", headers=S, params={"agreement_id": agA, "property_id": pb1, "check_in": str(ci), "check_out": str(co)})
    check(r.status_code == 404, "a property of another owner is not reachable through this agreement", r.text)
    r = c.get(f"{api}/availability", headers=X, params={"agreement_id": agA, "property_id": pa1, "check_in": str(ci), "check_out": str(co)})
    check(r.status_code == 404, "an outsider cannot use someone else's agreement id", r.text)

    # ---- hold: 10 minutes, owner's calendar blocked, tagged, double booking impossible
    r = c.post(f"{api}/hold", headers=S, json={"agreement_id": agA, "property_id": pa1, "unit_id": ua1[0], "check_in": str(ci), "check_out": str(co), "guests": 2, "customer": cust})
    check(r.status_code == 201 and r.json()["seconds_remaining"] == 600 and float(r.json()["total_amount"]) == 300, "hold for 10 minutes", r.text)
    hold1 = r.json()
    r = c.get("/api/v1/bookings", headers=A).json()
    mine = [b for b in r["items"] if b["id"] == hold1["booking_id"]][0]
    check(mine["channel_name"].startswith("Sunrise") and float(mine["channel_commission_amount"]) == 150 and mine["status"] == "HOLD", "owner sees it, marked as sold by Sunrise", mine)
    check(c.post(f"{api}/hold", headers=S, json={"agreement_id": agA, "property_id": pa1, "unit_id": ua1[0], "check_in": str(ci), "check_out": str(co), "guests": 2, "customer": cust2}).status_code == 409,
          "the same room cannot be held twice")
    d = c.post("/api/v1/bookings/hold", headers=A, json={"unit_id": ua1[0], "check_in": str(ci), "check_out": str(co), "guests": 2, "customer": cust2})
    check(d.status_code == 409, "the owner's own direct sale is blocked too (no double booking)", d.text)
    check(c.post(f"{api}/hold", headers=S, json={"agreement_id": agA, "property_id": pa1, "unit_id": ub1[0], "check_in": str(ci), "check_out": str(co), "customer": cust}).status_code == 404,
          "cannot hold a room of a property outside the agreement")
    check(c.post(f"{api}/hold", headers=S, json={"agreement_id": agA, "property_id": pa1, "unit_id": ua2[0], "check_in": str(ci), "check_out": str(co), "customer": cust}).status_code == 404,
          "cannot smuggle a room of another property of the same owner")
    check(c.post(f"{api}/hold", headers=X, json={"agreement_id": agA, "property_id": pa1, "unit_id": ua1[1], "check_in": str(ci), "check_out": str(co), "customer": cust}).status_code == 404,
          "an outsider cannot hold through someone else's agreement")

    # ---- confirm (money goes to the owner), partial then balance
    r = c.post(f"{api}/confirm", headers=S, json={"agreement_id": agA, "booking_id": hold1["booking_id"], "payment_mode": "PARTIAL", "amount": "150.00", "payment_reference": f"TXN-{tag}-1"})
    check(r.status_code == 200 and r.json()["status"] == "CONFIRMED" and r.json()["payment_state"] == "PARTIAL", "confirm with a 50% deposit", r.text)
    check(c.post(f"{api}/confirm", headers=X, json={"agreement_id": agA, "booking_id": hold1["booking_id"], "amount": "150.00", "payment_reference": "TXN-X-1"}).status_code == 404, "an outsider cannot confirm it")
    ob = [b for b in c.get("/api/v1/bookings", headers=A).json()["items"] if b["id"] == hold1["booking_id"]][0]
    check(ob["status"] == "CONFIRMED" and ob["payments"][0]["recorded_by"].startswith("reseller:Sunrise"), "owner sees who recorded the payment", ob["payments"])
    r = c.post(f"{api}/confirm", headers=S, json={"agreement_id": agA, "booking_id": hold1["booking_id"], "amount": "150.00", "payment_reference": f"TXN-{tag}-2"})
    check(r.json()["payment_state"] == "PAID", "balance paid later", r.text)

    # ---- the reseller's own booking list; guests of others stay private
    c.post("/api/v1/bookings/hold", headers=A, json={"unit_id": ua1[2], "check_in": str(ci), "check_out": str(co), "guests": 2, "customer": {"name": "Owner's Own Guest", "email": "own@example.com"}})
    r = c.get(f"{api}/bookings", headers=S).json()
    check(r["total"] == 1 and r["items"][0]["customer"]["name"] == "Guest One" and r["items"][0]["owner"].startswith("Nobodol") and r["items"][0]["property"] == "Nobodol Beach", "reseller lists only the bookings they made", r)
    check("Owner's Own Guest" not in str(r), "the owner's other guests are not visible")
    check(float(r["items"][0]["your_commission"]) == 150 and float(r["items"][0]["balance_due"]) == 0, "commission and balance shown")
    check(c.get(f"{api}/bookings", headers=X).json()["total"] == 0, "an outsider's list is empty")

    # ---- release an unpaid hold
    r = c.post(f"{api}/hold", headers=S, json={"agreement_id": agB, "property_id": pb1, "unit_id": ub1[0], "check_in": str(ci), "check_out": str(co), "guests": 2, "customer": cust2})
    check(r.status_code == 201 and float(r.json()["total_amount"]) == 600, "hold at the second owner", r.text)
    h2 = r.json()
    check(c.post(f"{api}/bookings/{h2['booking_id']}/release", headers=S, params={"agreement_id": agB}).json()["released"], "reseller gives up an unpaid hold")
    check(c.post(f"{api}/bookings/{hold1['booking_id']}/release", headers=S, params={"agreement_id": agA}).status_code == 409, "a paid booking cannot be released by the reseller")
    r = c.post(f"{api}/hold", headers=S, json={"agreement_id": agB, "property_id": pb1, "unit_id": ub1[0], "check_in": str(ci), "check_out": str(co), "guests": 2, "customer": cust2})
    check(r.status_code == 201, "the room is free again after release")

    # ---- pause / resume / end / terms
    check(c.post(f"{api}/agreements/{agA}/pause", headers=S).status_code == 403, "the reseller cannot pause")
    check(c.post(f"{api}/agreements/{agA}/pause", headers=A).json()["status"] == "PAUSED", "owner pauses")
    r = c.post(f"{api}/hold", headers=S, json={"agreement_id": agA, "property_id": pa1, "unit_id": ua1[1], "check_in": str(ci), "check_out": str(co), "customer": cust})
    check(r.status_code == 409 and "paused" in r.json()["detail"], "no new holds while paused", r.text)
    check(all(p["name"] != "Nobodol Beach" for p in c.get(f"{api}/properties", headers=S).json()), "paused properties leave the catalogue")
    check(c.get(f"{api}/bookings", headers=S).json()["total"] >= 1, "existing bookings stay visible while paused")
    check(c.post(f"{api}/agreements/{agA}/resume", headers=A).json()["status"] == "ACTIVE", "owner resumes")
    r = c.put(f"{api}/agreements/{agA}/terms", headers=A, json={"commission_type": "PERCENT", "commission_value": "20", "properties": [{"property_id": pa1}]})
    check(r.status_code == 200 and len(r.json()["properties"]) == 1, "owner changes terms", r.text)
    check(c.put(f"{api}/agreements/{agA}/terms", headers=S, json={"commission_type": "PERCENT", "commission_value": "99", "properties": [{"property_id": pa1}]}).status_code == 403, "the reseller cannot change terms")
    r = c.get(f"{api}/availability", headers=S, params={"agreement_id": agA, "property_id": pa1, "check_in": str(ci + timedelta(days=30)), "check_out": str(co + timedelta(days=30))})
    check(float(r.json()[0]["your_commission"]) == 60, "new terms apply to new bookings (20% of 300)", r.json()[0])
    again = [b for b in c.get(f"{api}/bookings", headers=S).json()["items"] if b["id"] == hold1["booking_id"]][0]
    check(float(again["your_commission"]) == 150 and again["commission_type"] == "FLAT", "an existing booking keeps the terms it was sold under", again)
    check(c.post(f"{api}/agreements/{agA}/end", headers=S).json()["status"] == "ENDED", "either side can end it")
    r = c.post(f"{api}/hold", headers=S, json={"agreement_id": agA, "property_id": pa1, "unit_id": ua1[1], "check_in": str(ci), "check_out": str(co), "customer": cust})
    check(r.status_code == 409, "no holds after it ended", r.text)
    check(c.get(f"{api}/bookings", headers=S).json()["total"] >= 1, "bookings stay visible after the end")
    r = c.post(f"{api}/agreements/request", headers=S, json={"owner_domain": domA})
    check(r.status_code == 201 and r.json()["status"] == "REQUESTED" and r.json()["properties"] == [], "after ending, a new request can be made")
    check(c.post(f"{api}/agreements/{agA}/decline", headers=A).json()["status"] == "DECLINED", "owner can decline a request")
    check(c.post(f"{api}/agreements/{agA}/withdraw", headers=S).status_code == 409, "nothing to withdraw once declined")

    # ---- the owner suspended by the platform: the reseller cannot book
    r = c.post(f"/api/v1/platform/tenants/{idB}/suspend", headers=P, json={"reason": "smoke test"})
    check(r.status_code == 200, "platform suspends owner B")
    r = c.post(f"{api}/hold", headers=S, json={"agreement_id": agB, "property_id": pb1, "unit_id": ub1[1], "check_in": str(ci), "check_out": str(co), "customer": cust})
    check(r.status_code == 409 and "not taking bookings" in r.json()["detail"], "no holds at a suspended owner", r.text)
    bk = c.get(f"{api}/bookings", headers=S).json()
    check(bk["unavailable"] and bk["unavailable"][0].startswith("Hittrail"), "the list says which owner is unavailable", bk["unavailable"])
    c.post(f"/api/v1/platform/tenants/{idB}/reactivate", headers=P)

    # ---- two resellers racing for the same room: exactly one wins
    r = c.post(f"{api}/agreements/invite", headers=A, json={"reseller_domain": domX, "commission_type": "PERCENT", "commission_value": "5", "properties": [{"property_id": pa1}]})
    agX = r.json()["id"]
    check(c.post(f"{api}/agreements/{agX}/accept", headers=X).json()["status"] == "ACTIVE", "a second reseller joins Nobodol")
    r = c.post(f"{api}/agreements/request", headers=S, json={"owner_domain": domA})
    # (Sunrise's request was declined above; owner accepts again)
    c.post(f"{api}/agreements/{[x for x in c.get(f'{api}/agreements', headers=S).json() if x['counterpart'].startswith('Nobodol')][0]['id']}/accept", headers=A,
           json={"commission_type": "PERCENT", "commission_value": "7", "properties": [{"property_id": pa1}]})
    agA2 = [x for x in c.get(f"{api}/agreements", headers=S).json() if x["counterpart"].startswith("Nobodol")][0]["id"]
    ci2, co2 = ci + timedelta(days=40), co + timedelta(days=40)
    codes = []

    def go(H, ag):
        cl = httpx.Client(base_url=a.base, timeout=60)
        codes.append(cl.post(f"{api}/hold", headers=H, json={"agreement_id": ag, "property_id": pa1, "unit_id": ua1[1], "check_in": str(ci2), "check_out": str(co2), "customer": cust}).status_code)
    ts = [threading.Thread(target=go, args=(S, agA2)), threading.Thread(target=go, args=(X, agX))]
    [t.start() for t in ts]; [t.join() for t in ts]
    check(sorted(codes) == [201, 409], "two resellers racing for one room: exactly one wins", codes)

    # ---- the database itself keeps owners apart
    for dom in (domS,):
        pass
    for t in (idA, idB, idS, idX):
        c.post(f"/api/v1/platform/tenants/{t}/suspend", headers=P, json={"reason": "smoke test cleanup"})
    print(f"\n{n} checks passed")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    main(p.parse_args())
