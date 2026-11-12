"""Checks the business profile against a RUNNING API:
    PYTHONPATH=. python scripts/smoke_business.py --email root@platform.example --password '...'"""
import argparse
import sys
import uuid

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
    P = {"Authorization": "Bearer " + c.post("/api/v1/platform/auth/login", json={"email": a.email, "password": a.password}).json()["access_token"]}
    dom = f"biz-{tag}.example"
    r = c.post("/api/v1/platform/tenants", headers=P, json={"name": f"Biz {tag}", "domain": dom, "admin_name": "Owner", "admin_email": f"o@{dom}"})
    A = {"Authorization": "Bearer " + c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"o@{dom}", "password": r.json()["temporary_password"]}).json()["access_token"]}

    g = c.get("/api/v1/business", headers=A).json()
    check(g["name"] == f"Biz {tag}" and not g["complete"] and set(g["missing"]) == {"Business logo", "Owner's photo"} and g["hold_minutes"] == 10 and g["deposit_percent"] == 50,
          "a new business starts with its name, 10-minute holds, 50% deposit and two required items missing", g)
    body = {"name": "Blue Hill Tours", "legal_name": "Blue Hill Tours Ltd", "business_type": "Tour operator", "established_year": 2015, "logo_url": "https://x.test/logo.png",
            "owner_name": "Karim Uddin", "owner_photo": "https://x.test/owner.jpg", "owner_phone": "01711000000", "license_no": "TL-2020-0457", "license_expiry": "2030-06-30",
            "tin": "123456789012", "whatsapp": "01711000000", "office_hours": "Sat-Thu 10am-7pm",
            "bank_accounts": [{"bank_name": "City Bank", "branch": "Gulshan", "account_name": "Blue Hill Tours Ltd", "account_number": "1234567890", "routing_no": "225261725", "is_primary": True}],
            "mfs_accounts": [{"provider": "bKash", "account_type": "Merchant", "number": "01711000000", "account_name": "Blue Hill", "is_primary": True},
                             {"provider": "Nagad", "account_type": "Personal", "number": "01811000000", "show_to_customers": False}],
            "hold_minutes": 15, "event_hold_minutes": 20, "deposit_percent": 30, "terms": "Seats are not transferable.", "cancellation_policy": "Free until 7 days before."}
    for key, label in (("logo_url", "Business logo"), ("owner_photo", "Owner's photo")):
        r = c.put("/api/v1/business", headers=A, json={**body, key: None})
        check(r.status_code == 422 and label in r.json()["detail"], f"saving without the {label.lower()} is refused", r.text)
        check(c.put("/api/v1/business", headers=A, json={**body, key: "  "}).status_code == 422, f"a blank {label.lower()} counts as missing")
    check(c.put("/api/v1/business", headers=A, json={**body, "tin": "12"}).status_code == 422, "a malformed TIN is refused")
    check(c.put("/api/v1/business", headers=A, json={**body, "tin": None, "bin": None}).status_code == 200, "TIN and BIN are optional")
    check(c.put("/api/v1/business", headers=A, json={**body, "bank_accounts": [{**body["bank_accounts"][0]}, {**body["bank_accounts"][0]}]}).status_code == 422, "two main bank accounts are refused")
    check(c.put("/api/v1/business", headers=A, json={**body, "deposit_percent": 0}).status_code == 422, "a 0% deposit is refused")
    r = c.put("/api/v1/business", headers=A, json=body)
    check(r.status_code == 200 and r.json()["complete"] and r.json()["missing"] == [] and r.json()["hold_minutes"] == 15, "a full profile is saved and complete", r.text)
    me = c.get("/api/v1/auth/me", headers=A).json()
    check(me["tenant_name"] == "Blue Hill Tours" and me["tenant_logo"] == "https://x.test/logo.png", "the header name and logo follow the profile")
    check(c.get("/api/v1/cms/company", headers=A).json()["logo_url"] == "https://x.test/logo.png", "Website content > Company shows the same logo")
    # the rules are really used
    ev = c.post("/api/v1/events", headers=A, json={"title": "Trip", "starts_on": "2099-01-10", "price": "100", "seats": 5, "status": "PUBLISHED"}).json()
    k = c.post("/api/v1/auth/api-keys", headers=A, json={"scopes": ["events:read", "events:book", "cms:read"]}).json()
    W = {"X-API-KEY": k["api_key"], "X-API-SECRET": k["api_secret"]}
    h = c.post(f"/api/v1/events/{ev['id']}/hold", headers=W, json={"seats": 1, "customer": {"name": "Guest One", "email": "g@example.com", "phone": "01711223344"}}).json()
    check(h["seconds_remaining"] == 1200, "the event hold time comes from the profile (20 minutes)", h)
    # public view
    pub = c.get("/api/v1/business/public", headers=W)
    j = pub.json()
    check(pub.status_code == 200 and j["name"] == "Blue Hill Tours" and j["license_no"] == "TL-2020-0457" and j["owner_photo"], "a website can read the public profile", pub.text)
    check([x["title"] for x in j["payment_accounts"]] == ["City Bank", "bKash (Merchant)"], "only accounts marked for customers are listed", j["payment_accounts"])
    check("owner_phone" not in j and "owner_email" not in j and "bank_accounts" not in j, "private details are never in the public view")
    check(c.get("/api/v1/business", headers=W).status_code == 403, "a key without business:read cannot read the private profile")
    k2 = c.post("/api/v1/auth/api-keys", headers=A, json={"scopes": ["business:read"]})
    check(k2.status_code in (200, 201), "a key may be given business:read", k2.text)
    R = {"X-API-KEY": k2.json()["api_key"], "X-API-SECRET": k2.json()["api_secret"]}
    check(c.get("/api/v1/business", headers=R).status_code == 200 and c.put("/api/v1/business", headers=R, json=body).status_code == 403, "a read-only key can read the profile but not change it")
    for bad in ("api_keys:manage", "staff:manage"):
        check(c.post("/api/v1/auth/api-keys", headers=A, json={"scopes": [bad]}).status_code == 422, f"no key can ever have {bad}")
    k3 = c.post("/api/v1/auth/api-keys", headers=A, json={"scopes": ["business:read", "business:manage"]}).json()
    check(c.put("/api/v1/business", headers={"X-API-KEY": k3["api_key"], "X-API-SECRET": k3["api_secret"]}, json=body).status_code == 200, "a key given business:manage may save the profile")
    # staff
    st = c.post("/api/v1/staff", headers=A, json={"name": "Manager One", "email": f"m@{dom}", "role": "MANAGER", "password": "Str0ng-Passw0rd!"})
    check(st.status_code in (200, 201), "a manager is added", st.text)
    M = {"Authorization": "Bearer " + c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"m@{dom}", "password": "Str0ng-Passw0rd!"}).json()["access_token"]}
    check(c.get("/api/v1/business", headers=M).status_code == 200 and c.put("/api/v1/business", headers=M, json=body).status_code == 403, "a manager can view but not change it")
    cr = c.get("/api/v1/auth/api-credentials", headers=A).json()
    check(cr["api_key"] == k3["api_key"] and cr["has_secret"] and "business:manage" in cr["scopes"], "the current key and its permissions can be read back", cr)
    check("api_secret" not in cr and "secret_hash" not in str(cr), "the secret is never returned again")
    r = c.put("/api/v1/auth/api-keys/scopes", headers=A, json={"scopes": ["events:read"]})
    check(r.status_code == 200 and r.json()["api_key"] == k3["api_key"] and r.json()["scopes"] == ["events:read"], "permissions can be changed without touching the key", r.text)
    K3 = {"X-API-KEY": k3["api_key"], "X-API-SECRET": k3["api_secret"]}
    check(c.get("/api/v1/events", headers=K3).status_code == 200 and c.get("/api/v1/business", headers=K3).status_code == 403, "...and the old secret still works with the new permissions")
    check(c.put("/api/v1/auth/api-keys/scopes", headers=A, json={"scopes": ["staff:manage"]}).status_code == 422, "forbidden permissions are refused when changing too")
    r = c.post("/api/v1/auth/api-keys/rotate-secret", headers=A)
    check(r.status_code == 200 and r.json()["api_key"] == k3["api_key"] and r.json()["api_secret"] != k3["api_secret"] and r.json()["scopes"] == ["events:read"], "changing the secret keeps key and permissions", r.text)
    check(c.get("/api/v1/events", headers=K3).status_code in (401, 403), "the old secret stops working at once")
    check(c.get("/api/v1/events", headers={"X-API-KEY": k3["api_key"], "X-API-SECRET": r.json()["api_secret"]}).status_code == 200, "the new secret works")
    check(c.get("/api/v1/auth/api-credentials", headers=M).status_code == 403, "a manager cannot see or change credentials")
    d = c.get("/api/v1/docs/module/business", headers=A)
    check(d.status_code == 200 and len(d.json()["endpoints"]) == 3, "the API documentation lists three calls", d.text[:200])
    print(f"\n{n} checks passed")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    main(p.parse_args())
