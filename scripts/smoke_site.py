"""Public website checks: pages, featured listings, contact form, super admin controls. Run: PYTHONPATH=. python scripts/smoke_site.py --email ... --password ..."""
import argparse
import sys
import uuid

import httpx

ap = argparse.ArgumentParser(); ap.add_argument("--base", default="http://localhost:8000"); ap.add_argument("--email", required=True); ap.add_argument("--password", required=True)
a = ap.parse_args()
c = httpx.Client(base_url=a.base, timeout=30)
ok = bad = 0


def check(name, cond, extra=""):
    global ok, bad
    ok, bad = ok + bool(cond), bad + (not cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if not cond else ""))


for path, word in (("/", "Trip Sajao"), ("/resorts", "Resort management"), ("/hotels", "Hotel management"), ("/houseboats", "Houseboat management"), ("/events", "Events and tours")):
    r = c.get(path); check(f"page {path}", r.status_code == 200 and word in r.text and "__KIND__" not in r.text)
check("unknown page is 404", c.get("/nothing-here").status_code == 404)
check("health still works", c.get("/healthz").status_code == 200)

for k in ("resort", "hotel", "houseboat", "events"):
    r = c.get("/api/v1/public/showcase", params={"kind": k}); check(f"showcase {k} needs no key", r.status_code == 200 and "items" in r.json())
check("showcase rejects unknown kind", c.get("/api/v1/public/showcase", params={"kind": "spa"}).status_code == 422)
flat = str(c.get("/api/v1/public/showcase", params={"kind": "resort"}).json())
check("showcase leaks no private fields", not any(w in flat for w in ("api_key", "secret", "email", "tenant_id", "customer")))

tok = c.post("/api/v1/platform/auth/login", json={"email": a.email, "password": a.password}).json()["access_token"]
P = {"Authorization": "Bearer " + tok}
t = c.post("/api/v1/platform/tenants", headers=P, json={"name": "Showcase Test " + uuid.uuid4().hex[:6], "domain": f"sc{uuid.uuid4().hex[:8]}.example", "admin_name": "Show Case", "admin_email": f"sc{uuid.uuid4().hex[:6]}@example.com"})
check("create business", t.status_code == 201); tid = t.json()["tenant"]["id"]
check("not featured by default", c.get(f"/api/v1/platform/tenants/{tid}", headers=P).json()["showcase"] is False)
r = c.post(f"/api/v1/platform/tenants/{tid}/showcase", headers=P, params={"enabled": "true"}); check("feature on", r.status_code == 200 and r.json()["showcase"] is True)
check("shown as featured", c.get(f"/api/v1/platform/tenants/{tid}", headers=P).json()["showcase"] is True)
check("featuring needs the super admin", c.post(f"/api/v1/platform/tenants/{tid}/showcase", params={"enabled": "false"}).status_code == 401)
c.post(f"/api/v1/platform/tenants/{tid}/showcase", headers=P, params={"enabled": "false"})

mail = f"visitor{uuid.uuid4().hex[:6]}@example.com"
body = {"name": "Visitor One", "email": mail, "message": "We run a small resort.", "business_type": "resort", "lang": "bn"}
r = c.post("/api/v1/public/contact", json=body); check("contact accepted", r.status_code == 201)
check("contact needs a valid email", c.post("/api/v1/public/contact", json={**body, "email": "nope"}).status_code == 422)
check("contact needs a message", c.post("/api/v1/public/contact", json={**body, "message": ""}).status_code == 422)
r = c.post("/api/v1/public/contact", json={**body, "email": "bot@example.com", "website": "http://spam"}); check("bot honeypot looks accepted", r.status_code == 201)
msgs = c.get("/api/v1/platform/messages", headers=P, params={"limit": 100}).json()
mine = [m for m in msgs["items"] if m["email"] == mail]
check("message reaches the super admin", len(mine) == 1 and mine[0]["status"] == "NEW" and mine[0]["lang"] == "bn")
check("bot message stored nothing", not any(m["email"] == "bot@example.com" for m in msgs["items"]))
check("messages need the super admin", c.get("/api/v1/platform/messages").status_code == 401)
r = c.post(f"/api/v1/platform/messages/{mine[0]['id']}/done", headers=P); check("mark handled", r.status_code == 200 and r.json()["status"] == "DONE")
check("filter handled", all(m["status"] == "DONE" for m in c.get("/api/v1/platform/messages", headers=P, params={"status": "DONE"}).json()["items"]))
codes = [c.post("/api/v1/public/contact", json={**body, "email": mail}).status_code for _ in range(4)]
check("same email is limited", 429 in codes, str(codes))
print(f"\n{ok} passed, {bad} failed"); sys.exit(1 if bad else 0)
