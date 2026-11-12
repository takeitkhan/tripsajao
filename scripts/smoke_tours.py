"""Checks packages, events, vendors, rates and budgets against a RUNNING API:
    python -m scripts.smoke_tours --email root@platform.example --password '...'"""
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
        pw = r.json()["temporary_password"]
        t = c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"o@{dom}", "password": pw}).json()
        return dom, {"Authorization": "Bearer " + t["access_token"]}, r.json()["tenant"]["id"]

    dom, A, idA = business("trips")
    domB, B, idB = business("other")
    d = lambda k: (TODAY + timedelta(days=k)).isoformat()

    # ------------------------------------------------------------------ packages
    body = {"title": "Sajek Valley 3 days", "summary": "Clouds and hills", "location": "Sajek", "duration_days": 3, "starting_price": "5000.00", "is_published": True,
            "itinerary": [{"day": 1, "title": "Dhaka to Sajek", "details": "Night bus"}, {"day": 2, "title": "Konglak Para"}],
            "inclusions": ["Cottage", " Breakfast ", ""], "exclusions": ["Lunch"]}
    r = c.post("/api/v1/packages", headers=A, json=body)
    check(r.status_code == 201 and r.json()["slug"] == "sajek-valley-3-days" and r.json()["inclusions"] == ["Cottage", "Breakfast"], "a package is saved with a clean web address and tidy lists", r.text)
    pk = r.json()
    check(c.post("/api/v1/packages", headers=A, json=body).status_code == 409, "the same web address twice is refused")
    check(c.post("/api/v1/packages", headers=A, json={**body, "title": "X", "starting_price": "-1"}).status_code == 422, "a negative price is refused")
    draft = c.post("/api/v1/packages", headers=A, json={"title": "Secret Draft", "starting_price": "9000"}).json()
    check(not draft["is_published"], "packages start as drafts")

    # ------------------------------------------------------------------ events from a package
    r = c.post(f"/api/v1/packages/{pk['id']}/events", headers=A, json={"starts_on": d(20)})
    ev = r.json()
    check(r.status_code == 201 and ev["status"] == "PUBLISHED" and ev["ends_on"] == d(22) and ev["price"] == "5000.00" and ev["package_id"] == pk["id"], "one date turns a package into a published event", r.text)
    check(len(ev["itinerary"]) == 2 and ev["inclusions"] == ["Cottage", "Breakfast"], "the itinerary and inclusions are copied across")
    r2 = c.post(f"/api/v1/packages/{pk['id']}/events", headers=A, json={"starts_on": d(20), "price": "5500", "seats": 12, "publish": False})
    check(r2.status_code == 201 and r2.json()["slug"] != ev["slug"] and r2.json()["status"] == "DRAFT" and r2.json()["price"] == "5500.00", "a second event on the same date gets its own address, with its own price and seats", r2.text)
    past = c.post(f"/api/v1/packages/{pk['id']}/events", headers=A, json={"starts_on": d(-30)}).json()
    check(c.post(f"/api/v1/packages/{pk['id']}/events", headers=A, json={"starts_on": d(5), "ends_on": d(2)}).status_code == 422, "an event cannot end before it starts")
    c.patch(f"/api/v1/packages/{pk['id']}", headers=A, json={"title": "Sajek renamed", "starting_price": "6000"})
    check(c.get(f"/api/v1/events/{ev['slug']}", headers=A).json()["title"] == "Sajek Valley 3 days", "editing the package later does not rewrite events already made")
    r = c.patch(f"/api/v1/events/{r2.json()['id']}", headers=A, json={"status": "PUBLISHED"})
    check(r.status_code == 200 and r.json()["published_at"], "a draft event can be published", r.text)
    check(c.patch(f"/api/v1/events/{ev['id']}", headers=A, json={"ends_on": d(10)}).status_code == 422, "changing the end date to before the start is refused")

    # ------------------------------------------------------------------ the full trip format
    full = {"title": "Bandarban Trekking 4 days", "location": "Bandarban", "duration_days": 4, "starting_price": "7500", "is_published": True,
            "description": "Four days in the hills", "pickup_location": "Kallyanpur, Dhaka", "accommodation": "Tents and a resort night",
            "trip_types": ["Trekking", " trekking ", "Adventure"], "bus_type": "AC sleeper coach", "other_transport": ["Chander gari", "Boat", ""],
            "health_rules": ["Carry your own medicine", "Drink boiled water"], "warnings": ["No network after day 2"], "essentials": ["Torch", "Rain jacket"],
            "photos": ["https://img.example/a.jpg", " ", "https://img.example/b.jpg"], "inclusions": ["Guide"], "exclusions": ["Personal costs"]}
    r = c.post("/api/v1/packages", headers=A, json=full)
    fp = r.json()
    check(r.status_code == 201 and fp["pickup_location"] == "Kallyanpur, Dhaka" and fp["trip_types"] == ["Trekking", "trekking", "Adventure"] and fp["other_transport"] == ["Chander gari", "Boat"]
          and fp["photos"] == ["https://img.example/a.jpg", "https://img.example/b.jpg"] and fp["bus_type"] == "AC sleeper coach" and fp["health_rules"][1] == "Drink boiled water", "a package keeps pickup, stay, trip types, bus, transport, health rules, warnings, essentials and photos", r.text)
    r = c.post(f"/api/v1/packages/{fp['id']}/events", headers=A, json={"starts_on": d(30), "seats": 18, "payment_methods": ["bKash", "Nagad", " bKash "], "photos": ["https://img.example/event.jpg"]})
    fe = r.json()
    check(r.status_code == 201 and fe["pickup_location"] == fp["pickup_location"] and fe["essentials"] == ["Torch", "Rain jacket"] and fe["bus_type"] == "AC sleeper coach" and fe["other_transport"] == ["Chander gari", "Boat"]
          and fe["payment_methods"] == ["bKash", "Nagad"] and fe["photos"] == ["https://img.example/event.jpg"] and fe["seats"] == 18, "the event takes everything from the package, plus seats, payment methods and its own photos", r.text)
    r = c.post("/api/v1/events", headers=A, json={"title": "Filled-in form", "starts_on": d(50), "ends_on": d(53), "price": "7800", "seats": 10, "package_id": fp["id"], "status": "PUBLISHED",
                                                  "pickup_location": "Gabtoli", "payment_methods": ["Bank transfer"], "photos": ["https://img.example/c.jpg"], "essentials": ["Torch"], "trip_types": ["Trekking"]})
    check(r.status_code == 201 and r.json()["pickup_location"] == "Gabtoli" and r.json()["payment_methods"] == ["Bank transfer"], "an event form filled from a package can be edited and published in one go", r.text)
    r = c.patch(f"/api/v1/events/{fe['id']}", headers=A, json={"payment_methods": ["Cash"], "warnings": ["Leave early"], "photos": []})
    check(r.json()["payment_methods"] == ["Cash"] and r.json()["warnings"] == ["Leave early"] and r.json()["photos"] == [], "payment methods, warnings and photos can be changed on an event", r.text)
    r = c.patch(f"/api/v1/packages/{fp['id']}", headers=A, json={"pickup_location": "Sayedabad", "other_transport": ["Jeep"]})
    check(r.json()["pickup_location"] == "Sayedabad" and r.json()["other_transport"] == ["Jeep"] and r.json()["trip_types"] == ["Trekking", "trekking", "Adventure"], "a package can be changed one part at a time")

    # ------------------------------------------------------------------ what a website sees
    k = c.post("/api/v1/auth/api-keys", headers=A, json={"scopes": ["events:read"]})
    check(k.status_code == 201, "a public key can be given permission to read events", k.text)
    W = {"X-API-KEY": k.json()["api_key"], "X-API-SECRET": k.json()["api_secret"]}
    pubp = c.get("/api/v1/packages", headers=W).json()
    check(sorted(p["title"] for p in pubp["items"]) == ["Bandarban Trekking 4 days", "Sajek renamed"], "a website sees only published packages", pubp)
    pube = c.get("/api/v1/events", headers=W).json()
    check(sorted(e["status"] for e in pube["items"]) == ["PUBLISHED"] * 4 and past["slug"] not in [e["slug"] for e in pube["items"]], "a website sees only published events that have not ended", pube["total"])
    check(c.get(f"/api/v1/events/{past['slug']}", headers=W).status_code == 200, "...but can open a published event by its address")
    c.patch(f"/api/v1/events/{ev['id']}", headers=A, json={"status": "CLOSED"})
    check(c.get(f"/api/v1/events/{ev['slug']}", headers=W).status_code == 404, "a closed event disappears from the website")
    check(c.get(f"/api/v1/packages/{draft['slug']}", headers=W).status_code == 404, "a draft package cannot be opened by address")
    check(c.post("/api/v1/packages", headers=W, json=body).status_code == 403, "a website cannot create packages")
    for sc in ("api_keys:manage", "staff:manage"):
        check(c.post("/api/v1/auth/api-keys", headers=A, json={"scopes": [sc]}).status_code == 422, f"no key can ever have {sc}")
    check(c.get("/api/v1/vendors", headers=W).status_code == 403 and c.get("/api/v1/budgets", headers=W).status_code == 403, "a website cannot read vendors or budgets")

    # ------------------------------------------------------------------ vendors and rates
    def vendor(cat, name, loc, **kw):
        r = c.post("/api/v1/vendors", headers=A, json={"category": cat, "name": name, "location": loc, "phone": "01711000000", **kw})
        assert r.status_code == 201, r.text
        return r.json()
    resort = vendor("RESORT", "Hill View Resort", "Sajek")
    jeep = vendor("CHANDER_GARI", "Karim Chander Gari", "Sajek")
    cng = vendor("CNG", "Rafiq CNG", "Bandarban")
    check(c.post("/api/v1/vendors", headers=A, json={"category": "SPACESHIP", "name": "x", "location": "y"}).status_code == 422, "an unknown vendor kind is refused")
    r = c.post(f"/api/v1/vendors/{resort['id']}/rates", headers=A, json={"item": "Double cottage", "unit": "PER_NIGHT", "price": "3500"})
    check(r.status_code == 201 and r.json()["price"] == "3500.00", "a rate is added to a vendor", r.text)
    rate_cot = r.json()
    rate_meal = c.post(f"/api/v1/vendors/{resort['id']}/rates", headers=A, json={"item": "Lunch", "unit": "PER_MEAL", "price": "350"}).json()
    rate_jeep = c.post(f"/api/v1/vendors/{jeep['id']}/rates", headers=A, json={"item": "Konglak trip", "unit": "PER_TRIP", "price": "4000"}).json()
    c.post(f"/api/v1/vendors/{cng['id']}/rates", headers=A, json={"item": "Town ride", "unit": "PER_TRIP", "price": "300"})
    check(c.get("/api/v1/vendors/locations", headers=A).json() == ["Bandarban", "Sajek"], "the list of places")
    sj = c.get("/api/v1/vendors", headers=A, params={"location": "sajek"}).json()
    check(sj["total"] == 2 and {v["name"]: v["rate_count"] for v in sj["items"]} == {"Hill View Resort": 2, "Karim Chander Gari": 1}, "vendors by place (any letter case) with their rate counts", sj)
    check(c.get("/api/v1/vendors", headers=A, params={"category": "CNG"}).json()["total"] == 1 and c.get("/api/v1/vendors", headers=A, params={"q": "karim"}).json()["total"] == 1, "filter by kind and search by name")
    found = c.get("/api/v1/rates", headers=A, params={"location": "Sajek", "q": "lunch"}).json()
    check(found["total"] == 1 and found["items"][0]["vendor_name"] == "Hill View Resort" and found["items"][0]["category"] == "RESORT", "rates can be searched across vendors for the calculator", found)
    check(c.get(f"/api/v1/vendors/{resort['id']}", headers=A).json()["rates"][0]["item"] == "Double cottage", "a vendor opens with all of its rates")
    check(c.patch(f"/api/v1/rates/{rate_cot['id']}", headers=A, json={"price": "3800"}).json()["price"] == "3800.00", "a rate can be updated")
    c.patch(f"/api/v1/vendors/{cng['id']}", headers=A, json={"is_active": False})
    check(c.get("/api/v1/rates", headers=A, params={"q": "town"}).json()["total"] == 0, "rates of a switched-off vendor are not offered")
    check(c.get("/api/v1/vendors", headers=B).json()["total"] == 0 and c.get(f"/api/v1/vendors/{resort['id']}", headers=B).status_code == 404
          and c.patch(f"/api/v1/rates/{rate_cot['id']}", headers=B, json={"price": "1"}).status_code == 404, "another business sees none of these vendors or rates")

    # ------------------------------------------------------------------ budget calculator
    lines = [{"label": "Hill View Resort - Double cottage", "vendor_id": resort["id"], "unit": "per night", "qty": "2", "unit_price": "3800"},
             {"label": "Lunch", "vendor_id": resort["id"], "qty": "3", "unit_price": "350", "per_person": True},
             {"label": "Chander gari", "vendor_id": jeep["id"], "qty": "1", "unit_price": "4000"}]
    r = c.post("/api/v1/budgets", headers=A, json={"title": "Sajek for Rahman family", "client_name": "Rahman", "people": 4, "lines": lines, "margin_percent": "15", "package_id": pk["id"]})
    b = r.json()
    # cost = 7600 + 3*350*4 (=4200) + 4000 = 15800; margin 15% = 2370; sell = 18170; per person 4542.50
    check(r.status_code == 201 and b["cost_total"] == "15800.00" and b["margin_amount"] == "2370.00" and b["sell_total"] == "18170.00" and b["sell_per_person"] == "4542.50", "budget totals: lines x people, margin on top, price per person", r.text)
    check([ln["line_total"] for ln in b["lines"]] == ["7600.00", "4200.00", "4000.00"], "each line shows its own total")
    r = c.patch(f"/api/v1/budgets/{b['id']}", headers=A, json={"people": 5, "margin_percent": "10"})
    check(r.json()["cost_total"] == "16850.00" and r.json()["sell_total"] == "18535.00", "changing people or margin works the totals out again", r.text)
    lst = c.get("/api/v1/budgets", headers=A).json()
    check(lst["total"] == 1 and lst["items"][0]["sell_total"] == "18535.00", "the list shows saved totals")
    cp = c.post(f"/api/v1/budgets/{b['id']}/copy", headers=A)
    check(cp.status_code == 201 and cp.json()["title"].endswith("(copy)") and cp.json()["status"] == "DRAFT" and cp.json()["sell_total"] == "18535.00" and cp.json()["id"] != b["id"], "a budget can be copied to start a new one", cp.text)
    check(c.patch(f"/api/v1/budgets/{b['id']}", headers=A, json={"status": "SENT"}).json()["status"] == "SENT", "a budget can be marked as sent")
    check(c.post("/api/v1/budgets", headers=A, json={"title": "x", "lines": [{"label": "bad", "unit_price": "-5"}]}).status_code == 422, "a negative price on a line is refused")
    check(c.post("/api/v1/budgets", headers=A, json={"title": "x", "package_id": str(uuid.uuid4())}).status_code == 404, "a budget cannot point at a package that does not exist")
    check(c.get(f"/api/v1/budgets/{b['id']}", headers=B).status_code == 404 and c.get("/api/v1/budgets", headers=B).json()["total"] == 0, "another business cannot see these budgets")
    c.delete(f"/api/v1/packages/{pk['id']}", headers=A)
    check(c.get(f"/api/v1/budgets/{b['id']}", headers=A).json()["package_id"] is None and c.get(f"/api/v1/events/{ev['slug']}", headers=A).status_code == 200, "deleting a package keeps its budgets and events")

    # ------------------------------------------------------------------ who may do what
    def staff(name, perms):
        r = c.post("/api/v1/staff", headers=A, json={"name": name, "email": f"{name}@{dom}", "role": "STAFF", **({"permissions": perms} if perms is not None else {})})
        t = c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"{name}@{dom}", "password": r.json()["temporary_password"]}).json()
        return {"Authorization": "Bearer " + t["access_token"]}
    plain = staff("plain", None)
    check(c.get("/api/v1/events", headers=plain).status_code == 200 and c.post("/api/v1/packages", headers=plain, json=body).status_code == 403, "standard staff can see events but not publish them")
    check(c.get("/api/v1/vendors", headers=plain).status_code == 403 and c.get("/api/v1/budgets", headers=plain).status_code == 403, "standard staff cannot see vendor rates or budgets (internal costs)")
    seller = staff("seller", ["events:read", "events:write", "budgets:read", "budgets:write", "vendors:read"])
    check(c.post("/api/v1/packages", headers=seller, json={**body, "title": "Own package"}).status_code == 201 and c.get("/api/v1/rates", headers=seller).status_code == 200, "a staff member given events, budgets and vendor view can use them")
    check(c.post("/api/v1/vendors", headers=seller, json={"category": "CNG", "name": "x", "location": "y"}).status_code == 403, "...but cannot add vendors")
    for t in (idA, idB):
        c.post(f"/api/v1/platform/tenants/{t}/suspend", headers=P, json={"reason": "smoke test"})
    print(f"\n{n} checks passed")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    main(p.parse_args())
