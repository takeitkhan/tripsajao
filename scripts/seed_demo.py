"""Fills a RUNNING system with four demo travel agencies so you can try the whole console.

    docker compose exec api python scripts/seed_demo.py --email <super admin email> --password '<super admin password>'

It creates, through the normal API: the businesses (with logo, owner photo, licence and payment accounts), properties with rooms or
cabins and prices, trip packages, published and draft events, vendors with rates, a budget, sales partners (four of them for
Bengal Trekker), reseller agreements between the agencies, and sample bookings (rooms and event seats, some paid, one waiting
for a payment check). Running it again does nothing for an agency that already exists. Logins are printed at the end and saved
in demo_accounts.txt."""
import argparse
import struct
import sys
import zlib
from datetime import date, timedelta

import httpx

PW = "Demo-Passw0rd!"
TODAY = date.today()
d = lambda k: (TODAY + timedelta(days=k)).isoformat()
FAC = lambda *names: [{"name": n, "icon": i, "type": "lucide"} for n, i in names]
AC, WIFI, VIEW, BATH, FAN, FIRE = ("AC", "wind"), ("Wi-Fi", "wifi"), ("Hill view", "mountain"), ("Attached bath", "bath"), ("Fan", "fan"), ("Bonfire", "flame")


def png(w, h, rgb, rgb2):
    """A small gradient picture, written without any picture library."""
    rows = b"".join(b"\x00" + b"".join(bytes(int(a + (b - a) * (x + y) / (w + h)) for a, b in zip(rgb, rgb2)) for x in range(w)) for y in range(h))
    chunk = lambda t, data: struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


AGENCIES = [
    dict(name="Bengal Trekker", domain="bengaltrekker.example", colors=((20, 90, 80), (120, 190, 150)), owner="Rafiqul Islam", license="TL-2019-0412", tin="123456789012", year=2016,
         phone="01711-100001", bank=("City Bank", "Gulshan", "1203456789"), mfs=("bKash", "01711100001"),
         properties=[
             dict(type="RESORT", name="Sajek Cloud Resort", slug="sajek-cloud-resort", location="Sajek Valley, Rangamati", utype="COTTAGE", n=6, cap=3, wd=3500, we=4800, fac=(VIEW, FIRE, BATH)),
             dict(type="RESORT", name="Bandarban Hill Duplex", slug="bandarban-hill-duplex", location="Nilgiri, Bandarban", utype="DUPLEX", n=4, cap=4, wd=5200, we=6800, fac=(VIEW, AC, WIFI, BATH)),
             dict(type="HOTEL", name="Srimangal Tea Lodge", slug="srimangal-tea-lodge", location="Srimangal, Moulvibazar", utype="ROOM", n=5, cap=2, wd=2200, we=2900, fac=(AC, WIFI, BATH))],
         packages=[
             dict(title="Sajek Valley 3 Days", location="Sajek", days=3, price=5500, trip=["Relax", "Photography"], pickup="Kallyanpur Bus Stand, Dhaka", bus="AC sleeper coach", other=["Chander gari", "Jeep"],
                  stay="Cottages with hill view, 2 nights", days_plan=["Night bus from Dhaka", "Konglak and Ruilui Para, sunset at the helipad", "Morning clouds, return by night bus"]),
             dict(title="Bandarban Nilgiri and Nafakhum 4 Days", location="Bandarban", days=4, price=8900, trip=["Trekking", "Adventure"], pickup="Gabtoli, Dhaka", bus="Non-AC coach", other=["Chander gari", "Boat"],
                  stay="Tribal homestay and one resort night", days_plan=["Dhaka to Bandarban", "Nilgiri and Chimbuk", "Nafakhum waterfall by boat", "Return"])],
         events=[(0, 12, 14, 18, True), (0, 26, 14, 12, True), (1, 40, 14, 10, True), (1, 75, 14, 14, False)],
         vendors=[("RESORT", "Sajek Cloud Resort Partner Desk", "Sajek", [("Cottage", "PER_NIGHT", 3200)]), ("CHANDER_GARI", "Kamal Chander Gari Service", "Sajek", [("Full day Sajek trip", "PER_TRIP", 4500)]),
                  ("RESTAURANT", "Hill Taste Kitchen", "Sajek", [("Lunch", "PER_MEAL", 300), ("Dinner", "PER_MEAL", 350)])],
         partners=[("Sohel Travels", "B2B", "PERCENT", "10"), ("Dhaka Tour Hub", "B2B", "PERCENT", "12"), ("Mizan Ahmed (MoU)", "MOU", "FLAT", "400"), ("Green Path Club (MoU)", "MOU", "PERCENT", "8")]),
    dict(name="Zoom Wild", domain="zoomwild.example", colors=((60, 100, 30), (180, 210, 90)), owner="Tanvir Hasan", license="TL-2020-0877", tin="223456789013", year=2018,
         phone="01711-100002", bank=("Dutch-Bangla Bank", "Khulna", "7102233445"), mfs=("Nagad", "01811100002"),
         properties=[
             dict(type="RESORT", name="Sundarbans Jungle Lodge", slug="sundarbans-jungle-lodge", location="Mongla, Bagerhat", utype="COTTAGE", n=5, cap=3, wd=4200, we=5200, fac=(FAN, BATH, FIRE)),
             dict(type="HOUSEBOAT", name="Bonbibi Houseboat", slug="bonbibi-houseboat", location="Sundarbans, Khulna", utype="CABIN", n=3, cap=2, wd=3800, we=4600, fac=(AC, BATH), whole=14000),
             dict(type="HOTEL", name="Lawachara Forest Rest House", slug="lawachara-rest-house", location="Kamalganj, Moulvibazar", utype="ROOM", n=4, cap=2, wd=2600, we=3400, fac=(FAN, WIFI, BATH))],
         packages=[
             dict(title="Sundarbans Wildlife 3 Days", location="Sundarbans", days=3, price=9800, trip=["Wildlife", "Adventure"], pickup="Sadarghat Launch Terminal, Dhaka", bus="AC coach", other=["Boat", "Trawler"],
                  stay="Cabins on the boat, 2 nights", days_plan=["Dhaka to Mongla, board the boat", "Karamjal and Hiron Point", "Return"]),
             dict(title="Lawachara Rainforest Safari 2 Days", location="Srimangal", days=2, price=4800, trip=["Wildlife", "Relax"], pickup="Kamalapur Railway Station, Dhaka", bus="Train and CNG", other=["CNG"],
                  stay="Forest rest house, 1 night", days_plan=["Train to Srimangal, forest walk", "Bird watching at dawn, return"])],
         events=[(0, 18, 20, 20, True), (0, 50, 20, 16, True), (1, 9, 20, 12, True), (1, 33, 20, 12, False)],
         vendors=[("BOAT", "Mongla River Boats", "Sundarbans", [("Trawler per day", "PER_DAY", 12000)]), ("GUIDE", "Forest Guide Alam", "Sundarbans", [("Guide per day", "PER_DAY", 1500)]),
                  ("RESTAURANT", "Jungle Table", "Mongla", [("Lunch", "PER_MEAL", 280)])],
         partners=[("Wild Wanderers", "B2B", "PERCENT", "11"), ("Nature Club BD (MoU)", "MOU", "PERCENT", "7")]),
    dict(name="BongTrip", domain="bongtrip.example", colors=((20, 70, 130), (110, 180, 230)), owner="Nusrat Jahan", license="TL-2017-0231", tin="323456789014", year=2014,
         phone="01711-100003", bank=("BRAC Bank", "Cox's Bazar", "1501987654"), mfs=("bKash", "01911100003"),
         properties=[
             dict(type="HOTEL", name="Cox's Sea View Hotel", slug="coxs-sea-view-hotel", location="Kolatoli, Cox's Bazar", utype="ROOM", n=8, cap=3, wd=3600, we=5400, fac=(AC, WIFI, BATH, VIEW)),
             dict(type="RESORT", name="Saint Martin Coral Resort", slug="saint-martin-coral-resort", location="Saint Martin Island", utype="COTTAGE", n=5, cap=3, wd=4500, we=6000, fac=(FAN, BATH, VIEW)),
             dict(type="HOUSEBOAT", name="Tanguar Haor Houseboat", slug="tanguar-haor-houseboat", location="Tanguar Haor, Sunamganj", utype="CABIN", n=4, cap=2, wd=3200, we=4200, fac=(FAN, BATH), whole=11000)],
         packages=[
             dict(title="Saint Martin Island 3 Days", location="Saint Martin", days=3, price=7800, trip=["Relax", "Beach"], pickup="Sayedabad, Dhaka", bus="AC sleeper coach", other=["Ship", "Boat"],
                  stay="Coral resort cottages, 2 nights", days_plan=["Dhaka to Teknaf", "Ship to the island, beach and coral", "Return by ship and bus"]),
             dict(title="Tanguar Haor Houseboat 3 Days", location="Sunamganj", days=3, price=6900, trip=["Relax", "Photography"], pickup="Mohakhali, Dhaka", bus="AC coach", other=["Boat"],
                  stay="Houseboat cabins, 2 nights", days_plan=["Dhaka to Sunamganj, board the houseboat", "Lake cruise and Barek Tila", "Return"])],
         events=[(0, 21, 20, 30, True), (0, 55, 20, 26, True), (1, 14, 20, 16, True), (1, 44, 20, 16, False)],
         vendors=[("BOAT", "Haor Boat Service", "Sunamganj", [("Boat per day", "PER_DAY", 9000)]), ("RESORT", "Teknaf Transit Hotel", "Teknaf", [("Room", "PER_NIGHT", 2000)]),
                  ("RESTAURANT", "Sea Pearl Restaurant", "Cox's Bazar", [("Seafood lunch", "PER_MEAL", 450)])],
         partners=[("Sky Holidays", "B2B", "PERCENT", "9"), ("Coastal Agents (MoU)", "MOU", "FLAT", "350")]),
    dict(name="Adventure Trekkers", domain="adventuretrekkers.example", colors=((130, 50, 20), (230, 160, 90)), owner="Imran Hossain", license="TL-2021-1102", tin="423456789015", year=2019,
         phone="01711-100004", bank=("Islami Bank", "Chattogram", "2050112233"), mfs=("Rocket", "01611100004"),
         properties=[
             dict(type="RESORT", name="Bandarban Adventure Camp", slug="bandarban-adventure-camp", location="Thanchi, Bandarban", utype="COTTAGE", n=6, cap=4, wd=2800, we=3600, fac=(FIRE, VIEW, FAN)),
             dict(type="HOTEL", name="Ratargul Swamp Lodge", slug="ratargul-swamp-lodge", location="Gowainghat, Sylhet", utype="ROOM", n=4, cap=2, wd=2400, we=3100, fac=(AC, WIFI, BATH)),
             dict(type="RESORT", name="Kuakata Beach Duplex", slug="kuakata-beach-duplex", location="Kuakata, Patuakhali", utype="DUPLEX", n=3, cap=5, wd=6200, we=7800, fac=(AC, WIFI, BATH, VIEW))],
         packages=[
             dict(title="Keokradong Trek 5 Days", location="Bandarban", days=5, price=12500, trip=["Trekking", "Adventure"], pickup="Kallyanpur, Dhaka", bus="Non-AC coach", other=["Jeep", "Chander gari"],
                  stay="Tents and village huts", days_plan=["Dhaka to Ruma", "Trek to Boga Lake", "Trek to Keokradong", "Descend to Thanchi", "Return"]),
             dict(title="Ratargul and Jaflong 2 Days", location="Sylhet", days=2, price=4200, trip=["Relax", "Photography"], pickup="Kamalapur, Dhaka", bus="AC coach", other=["Boat"],
                  stay="Lodge, 1 night", days_plan=["Dhaka to Sylhet, Ratargul by boat", "Jaflong and Tamabil, return"])],
         events=[(0, 16, 20, 14, True), (0, 48, 20, 14, True), (1, 11, 20, 20, True), (1, 36, 20, 20, False)],
         vendors=[("GUIDE", "Hillman Guide Service", "Bandarban", [("Guide per day", "PER_DAY", 1800), ("Porter per day", "PER_DAY", 1200)]), ("JEEP", "Ruma Jeep Stand", "Bandarban", [("Jeep to Ruma", "PER_TRIP", 6000)]),
                  ("BOAT", "Ratargul Boatmen", "Sylhet", [("Boat", "PER_TRIP", 800)])],
         partners=[("Trail Mates", "B2B", "PERCENT", "10")]),
]
# (reseller, owner, owner's property slugs, commission %)
RESELLING = [("Bengal Trekker", "Zoom Wild", ["sundarbans-jungle-lodge", "bonbibi-houseboat"], "10"), ("Bengal Trekker", "BongTrip", ["saint-martin-coral-resort"], "12"),
             ("Adventure Trekkers", "Bengal Trekker", ["sajek-cloud-resort", "bandarban-hill-duplex"], "8"), ("BongTrip", "Adventure Trekkers", ["bandarban-adventure-camp"], "9")]


class Seeder:
    def __init__(self, base, email, password):
        self.c = httpx.Client(base_url=base, timeout=120)
        r = self.c.post("/api/v1/platform/auth/login", json={"email": email, "password": password})
        if r.status_code != 200:
            sys.exit(f"Super admin sign-in failed: {r.text}")
        self.P = {"Authorization": "Bearer " + r.json()["access_token"]}
        self.accounts = []

    def ok(self, r, what):
        if r.status_code >= 300:
            sys.exit(f"{what} failed ({r.status_code}): {r.text[:400]}")
        return r.json()

    def upload(self, H, data, title):
        r = self.c.post("/api/v1/media", headers=H, files={"file": (title.replace(" ", "-").lower() + ".png", data, "image/png")}, data={"title": title})
        return self.ok(r, f"upload {title}")["url"]

    # ------------------------------------------------------------------ one agency
    def agency(self, a):
        mail = f"admin@{a['domain']}"
        r = self.c.post("/api/v1/platform/tenants", headers=self.P, json={"name": a["name"], "domain": a["domain"], "admin_name": a["owner"], "admin_email": mail})
        fresh = r.status_code == 201
        if fresh:
            tok = self.c.post("/api/v1/auth/login", json={"tenant_domain": a["domain"], "email": mail, "password": r.json()["temporary_password"]}).json()
            self.c.post("/api/v1/auth/change-password", headers={"Authorization": "Bearer " + tok["access_token"]}, json={"current_password": r.json()["temporary_password"], "new_password": PW})
        tok = self.c.post("/api/v1/auth/login", json={"tenant_domain": a["domain"], "email": mail, "password": PW})
        if tok.status_code != 200:
            print(f"- {a['name']}: exists, but its admin password is not the demo one - skipped")
            return None
        A = {"Authorization": "Bearer " + tok.json()["access_token"]}
        a["A"] = A
        tid = next((t["id"] for t in self.c.get("/api/v1/platform/tenants", headers=self.P, params={"q": a["domain"]}).json()["items"] if t["domain"] == a["domain"]), None)
        if tid:                                                  # show these demo businesses on the public website
            self.c.post(f"/api/v1/platform/tenants/{tid}/showcase", headers=self.P, params={"enabled": "true"})
        if not fresh and self.c.get("/api/v1/properties", headers=A).json()["total"] > 0:
            print(f"- {a['name']}: already filled - skipped")
            a["props"] = {p["slug"]: p for p in self.c.get("/api/v1/properties", headers=A, params={"limit": 100}).json()["items"]}
            self.accounts.append((a["name"] + " (admin)", f"/admin/   {mail}   {PW}"))
            return a
        print(f"+ {a['name']}")
        post = lambda path, body, what, **kw: self.ok(self.c.post("/api/v1" + path, headers=A, json=body, **kw), what)
        # business profile
        logo = self.upload(A, png(240, 240, *a["colors"]), f"{a['name']} logo")
        face = self.upload(A, png(240, 300, a["colors"][1], a["colors"][0]), f"{a['owner']} photo")
        self.ok(self.c.put("/api/v1/business", headers=A, json={
            "name": a["name"], "legal_name": f"{a['name']} Ltd", "business_type": "Tour operator", "established_year": a["year"], "logo_url": logo, "owner_name": a["owner"], "owner_photo": face,
            "owner_phone": a["phone"], "owner_email": mail, "license_no": a["license"], "license_expiry": d(900), "tin": a["tin"], "whatsapp": a["phone"], "website": f"https://{a['domain']}",
            "office_hours": "Sat-Thu 10am-7pm", "bank_accounts": [{"bank_name": a["bank"][0], "branch": a["bank"][1], "account_name": f"{a['name']} Ltd", "account_number": a["bank"][2], "is_primary": True}],
            "mfs_accounts": [{"provider": a["mfs"][0], "account_type": "Merchant", "number": a["mfs"][1], "account_name": a["name"], "is_primary": True}],
            "hold_minutes": 10, "event_hold_minutes": 10, "deposit_percent": 50, "terms": "Seats and rooms are confirmed after the payment is checked.",
            "cancellation_policy": "Free cancellation up to 7 days before the trip. After that 50% is kept."}), "business profile")
        # properties, units, prices
        a["props"], a["units"] = {}, {}
        for i, p in enumerate(a["properties"]):
            pic = self.upload(A, png(640, 400, a["colors"][i % 2], a["colors"][(i + 1) % 2]), p["name"])
            prop = post("/properties", {"type": p["type"], "name": p["name"], "slug": p["slug"], "location": p["location"],
                                        "metadata": {"description": f"{p['name']} - {p['location']}", "amenities": FAC(*p["fac"]), "media": [{"type": "photo", "url": pic}]}}, f"property {p['name']}")
            a["props"][p["slug"]] = prop
            us = []
            for k in range(p["n"]):
                layout = {"floor": 1 + k // 3, "row": 0, "col": k % 3} if p["type"] != "HOUSEBOAT" else {"x": 70 + 100 * (k % 2), "y": 30 + 70 * (k // 2), "w": 80, "h": 50}
                name = (f"Cabin {k + 1}" if p["type"] == "HOUSEBOAT" else f"{p['utype'].title()} {k + 1}")
                u = post(f"/properties/{prop['id']}/units", {"unit_name": name, "type": p["utype"], "capacity": p["cap"], "facilities": FAC(*p["fac"]), "layout": layout}, f"unit {name}")
                self.ok(self.c.put(f"/api/v1/pricing/units/{u['id']}", headers=A, json={"weekday_price": str(p["wd"]), "weekend_price": str(p["we"]), "currency": "BDT",
                        "seasonal": {"weekend_days": [4, 5], "rules": [{"name": "Winter peak", "start_date": d(60), "end_date": d(90), "kind": "SURCHARGE_PERCENT", "value": "15"}]}}), "pricing")
                us.append(u["id"])
            if p.get("whole"):
                u = post(f"/properties/{prop['id']}/units", {"unit_name": "Whole boat charter", "type": "WHOLE_BOAT", "capacity": p["cap"] * p["n"]}, "charter unit")
                self.ok(self.c.put(f"/api/v1/pricing/units/{u['id']}", headers=A, json={"weekday_price": str(p["whole"]), "weekend_price": str(int(p["whole"] * 1.25)), "currency": "BDT"}), "charter price")
            a["units"][p["slug"]] = us
        # packages and events
        pk = []
        for i, k in enumerate(a["packages"]):
            cover = self.upload(A, png(800, 450, a["colors"][(i + 1) % 2], a["colors"][i % 2]), k["title"])
            pk.append(post("/packages", {
                "title": k["title"], "summary": f"{k['days']} days in {k['location']}", "location": k["location"], "duration_days": k["days"], "starting_price": str(k["price"]), "is_published": True, "cover_image": cover,
                "description": f"A well-planned {k['days']}-day trip to {k['location']} with a guide, stay and transport.", "pickup_location": k["pickup"], "accommodation": k["stay"], "trip_types": k["trip"], "bus_type": k["bus"],
                "other_transport": k["other"], "health_rules": ["Carry your own medicine", "Drink only boiled or bottled water"], "warnings": ["Mobile network can be weak", "Follow the guide at all times"],
                "essentials": ["Torch", "Rain jacket", "Power bank", "Government ID"], "photos": [cover], "inclusions": ["Guide", "Stay", "Transport", "Breakfast"], "exclusions": ["Personal costs", "Lunch and dinner on the way"],
                "itinerary": [{"day": n + 1, "title": t, "details": "Details are shared with the group before the trip."} for n, t in enumerate(k["days_plan"])]}, f"package {k['title']}"))
        a["events"] = []
        for pi, start, _len, seats, publish in a["events_plan"]:
            k = a["packages"][pi]
            ev = post(f"/packages/{pk[pi]['id']}/events", {"starts_on": d(start), "ends_on": d(start + k["days"] - 1), "seats": seats, "price": str(k["price"]), "publish": publish,
                                                           "payment_methods": [a["mfs"][0], "Bank transfer"]}, f"event {k['title']}")
            a["events"].append(ev)
        # vendors, a budget
        vs = []
        for cat, name, loc, rates in a["vendors"]:
            v = post("/vendors", {"category": cat, "name": name, "location": loc, "phone": "01711000000"}, f"vendor {name}")
            for item, unit, price in rates:
                post(f"/vendors/{v['id']}/rates", {"item": item, "unit": unit, "price": str(price)}, f"rate {item}")
            vs.append((v, rates[0]))
        post("/budgets", {"title": f"{a['packages'][0]['title']} - sample group", "client_name": "Sample client", "people": 6, "margin_percent": "15", "package_id": pk[0]["id"],
                          "lines": [{"label": f"{v['name']} - {r[0]}", "vendor_id": v["id"], "unit": r[1].replace("_", " ").lower(), "qty": "2", "unit_price": str(r[2])} for v, r in vs]}, "budget")
        # partners
        self.accounts.append((a["name"] + " (admin)", f"/admin/   {mail}   {PW}"))
        a["partner_rows"] = []
        for n, (pname, ptype, ctype, cval) in enumerate(a["partners"]):
            em = f"{pname.lower().split(' (')[0].replace(' ', '.')}@partners.example"
            p = post("/partners", {"name": pname, "email": em, "password": PW, "partner_type": ptype, "commission_type": ctype, "commission_value": cval}, f"partner {pname}")
            a["partner_rows"].append(p)
            self.accounts.append((f"{a['name']} partner: {pname}", f"/admin/   {em}   {PW}   (choose Partner)   commission {cval}{'%' if ctype == 'PERCENT' else ' BDT flat'}"))
        return a

    # ------------------------------------------------------------------ sample bookings
    def bookings(self, a):
        A, cust = a["A"], lambda n, i: {"name": n, "email": f"{n.lower().replace(' ', '.')}{i}@guest.example", "phone": f"0171{i:07d}"}
        slug = a["properties"][0]["slug"]
        units = a["units"][slug]
        cookie = {}
        if a["partner_rows"]:
            code = a["partner_rows"][0]["vanity_code"]
            cookie = {"_ref_token": self.c.get(f"/go/{code}", follow_redirects=False).cookies.get("_ref_token") or ""}
        plan = [(0, 7, 9, "Farhana Akter", "FULL", cookie), (1, 14, 16, "Mahmud Hasan", "PARTIAL", {}), (2, 21, 23, "Shirin Sultana", "PARTIAL", cookie), (3, 8, 10, "Jahid Karim", None, {})]
        for ui, ci, co, who, mode, ck in plan:
            if ui >= len(units):
                continue
            r = self.c.post("/api/v1/bookings/hold", headers=A, cookies=ck, json={"unit_id": units[ui], "check_in": d(ci), "check_out": d(co), "guests": 2, "customer": cust(who, ui)})
            if r.status_code != 201:
                continue
            b = r.json()
            if mode:
                amount = b["total_amount"] if mode == "FULL" else b["deposit_amount"]
                self.c.post("/api/v1/bookings/confirm", headers=A, json={"booking_id": b["booking_id"], "payment_mode": mode, "amount": str(amount), "payment_reference": f"DEMO-{a['domain'][:4]}-{ui}"})
        # event seats: confirmed (with a partner), waiting for a payment check, and a fresh hold
        pub = [e for e in a["events"] if e["status"] == "PUBLISHED"]
        if not pub:
            return
        ev = pub[0]
        shot = png(200, 340, (230, 230, 230), (190, 40, 120))
        for who, seats, step, ck in (("Nabil Rahman", 2, "verify", cookie), ("Tania Islam", 3, "submit", {}), ("Sabbir Ahmed", 1, "hold", {})):
            r = self.c.post(f"/api/v1/events/{ev['id']}/hold", headers=A, cookies=ck, json={"seats": seats, "customer": {"name": who, "email": f"{who.lower().replace(' ', '.')}@guest.example", "phone": "01712345678"}})
            if r.status_code != 201 or step == "hold":
                continue
            h = r.json()
            T = {**A, "X-Booking-Token": h["token"]}
            self.c.post(f"/api/v1/event-bookings/status/{h['booking_ref']}/proof", headers=T, files={"file": ("payment.png", shot, "image/png")})
            amount = float(h["total_amount"]) if step == "verify" else float(h["total_amount"]) / 2
            self.c.post(f"/api/v1/event-bookings/status/{h['booking_ref']}/payment", headers=T, json={"method": a["mfs"][0], "amount": f"{amount:.2f}", "trx_id": f"TRX{h['booking_ref'][2:]}", "sender": "01712345678"})
            if step == "verify":
                row = [x for x in self.c.get("/api/v1/event-bookings", headers=A, params={"q": h["booking_ref"]}).json()["items"]][0]
                self.c.post(f"/api/v1/event-bookings/{row['id']}/payments/{row['payments_json'][0]['id']}/verify", headers=A, json={})

    # ------------------------------------------------------------------ resellers
    def resellers(self, by_name):
        for reseller, owner, slugs, pct in RESELLING:
            R, O = by_name.get(reseller), by_name.get(owner)
            if not R or not O:
                continue
            ids = [{"property_id": O["props"][s]["id"]} for s in slugs if s in O["props"]]
            r = self.c.post("/api/v1/channel/agreements/invite", headers=O["A"], json={"reseller_domain": R["domain"], "commission_type": "PERCENT", "commission_value": pct, "properties": ids})
            if r.status_code == 201:
                self.c.post(f"/api/v1/channel/agreements/{r.json()['id']}/accept", headers=R["A"])
                print(f"  reseller: {reseller} sells {owner} ({pct}%)")


def main(a):
    s = Seeder(a.base, a.email, a.password)
    done = {}
    for ag in AGENCIES:
        ag["events_plan"] = ag["events"]
        ag["events"] = []
        res = s.agency(ag)
        if res:
            done[ag["name"]] = res
    fresh = [x for x in done.values() if x.get("units")]
    for x in fresh:
        s.bookings(x)
    s.resellers(done)
    lines = [f"{who}\n    {how}" for who, how in s.accounts]
    text = "Demo accounts (all passwords: " + PW + ")\nSign in at /admin/ - choose Staff or Partner. The business domain is not needed.\n\n" + "\n".join(lines)
    open("demo_accounts.txt", "w").write(text + "\n")
    print("\n" + text)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    main(p.parse_args())
