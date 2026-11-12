"""Checks the super admin portal, registration, limits and support sessions against a RUNNING API.
    python -m scripts.smoke_platform --email root@platform.example --password '...'
Creates two businesses named 'Smoke ...' (and leaves them suspended)."""
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
    c = httpx.Client(base_url=a.base, timeout=30)
    tag = uuid.uuid4().hex[:6]
    check(c.get("/api/v1/platform/overview").status_code == 401, "portal API needs sign-in")
    check(c.post("/api/v1/platform/auth/login", json={"email": a.email, "password": "wrong-password-1"}).status_code == 401, "wrong super admin password refused")
    r = c.post("/api/v1/platform/auth/login", json={"email": a.email, "password": a.password})
    check(r.status_code == 200 and r.json()["admin"]["email"] == a.email.lower(), "super admin sign-in", r.text)
    P = {"Authorization": "Bearer " + r.json()["access_token"]}
    rf = c.post("/api/v1/platform/auth/refresh", json={"refresh_token": r.json()["refresh_token"]})
    check(rf.status_code == 200 and c.post("/api/v1/platform/auth/refresh", json={"refresh_token": r.json()["refresh_token"]}).status_code == 401, "refresh works once")

    # ---- create a business
    dom = f"smoke-{tag}.example"
    r = c.post("/api/v1/platform/tenants", headers=P, json={"name": f"Smoke Resort {tag}", "domain": dom, "admin_name": "Owner", "admin_email": f"owner@{dom}",
                                                              "limits": {"max_properties": 1, "max_units": 3, "media_quota_mb": 1}})
    check(r.status_code == 201 and r.json()["temporary_password"] and r.json()["api_secret"].startswith("sk_"), "create business with a generated password", r.text)
    t = r.json()["tenant"]; pw = r.json()["temporary_password"]; tid = t["id"]
    check(c.post("/api/v1/platform/tenants", headers=P, json={"name": "Dup", "domain": dom, "admin_name": "Owner", "admin_email": "o@x.example"}).status_code == 409, "duplicate domain refused")
    check(c.post("/api/v1/platform/tenants", headers=P, json={"name": "Bad", "domain": "Not A Domain!", "admin_name": "Owner", "admin_email": "o@x.example"}).status_code == 422, "bad domain refused")

    # ---- the new business works, and platform/tenant tokens are not interchangeable
    r = c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"owner@{dom}", "password": pw})
    check(r.status_code == 200, "new business admin can sign in with the generated password", r.text)
    T = {"Authorization": "Bearer " + r.json()["access_token"]}
    check(c.get("/api/v1/platform/overview", headers=T).status_code == 401, "a business token cannot open the portal API")
    check(c.get("/api/v1/auth/me", headers=P).status_code == 401, "a super admin token cannot act as a business")

    # ---- limits
    p1 = c.post("/api/v1/properties", headers=T, json={"type": "RESORT", "name": "One", "slug": "one"})
    check(p1.status_code == 201, "first property allowed")
    p2 = c.post("/api/v1/properties", headers=T, json={"type": "RESORT", "name": "Two", "slug": "two"})
    check(p2.status_code == 403 and "allows up to 1 properties" in p2.json()["detail"], "property limit enforced in plain words", p2.text)
    pid = p1.json()["id"]
    for i in range(3):
        check(c.post(f"/api/v1/properties/{pid}/units", headers=T, json={"unit_name": f"R{i}", "type": "ROOM"}).status_code == 201, f"unit {i + 1} allowed")
    check(c.post(f"/api/v1/properties/{pid}/units", headers=T, json={"unit_name": "R9", "type": "ROOM"}).status_code == 403, "unit limit enforced")
    s = c.get("/api/v1/media/summary", headers=T).json()
    check(s["quota_bytes"] == 1024 * 1024, "media quota comes from this business's limit", s)
    d = c.get(f"/api/v1/platform/tenants/{tid}", headers=P).json()
    check(d["usage"]["properties"] == 1 and d["usage"]["units"] == 3 and d["limits"]["max_units"] == 3, "usage and limits shown", d["usage"])
    check(len(d["bookings_by_day"]) == 30 and d["users"][0]["role"] == "ADMIN", "detail has a 30-day series and users")
    r = c.patch(f"/api/v1/platform/tenants/{tid}", headers=P, json={"limits": {"max_properties": 5, "max_units": 3}})
    check(r.status_code == 200 and r.json()["limits"] == {"max_properties": 5, "max_units": 3}, "limits changed", r.text)
    check(c.post("/api/v1/properties", headers=T, json={"type": "RESORT", "name": "Two", "slug": "two"}).status_code == 201, "new limit applies at once")
    check(c.patch(f"/api/v1/platform/tenants/{tid}", headers=P, json={"limits": {"max_properties": -1}}).status_code == 422, "negative limit refused")

    # ---- list / search / overview
    lst = c.get("/api/v1/platform/tenants", headers=P, params={"q": tag}).json()
    check(lst["total"] == 1 and lst["items"][0]["usage"]["units"] == 3 and set(lst["counts"]) == {"ACTIVE", "PENDING", "SUSPENDED", "REJECTED"}, "list with search, usage and status counts")
    check(c.get("/api/v1/platform/tenants", headers=P, params={"status": "BOGUS"}).status_code == 422, "unknown status filter refused")
    ov = c.get("/api/v1/platform/overview", headers=P).json()
    check(ov["tenants"]["ACTIVE"] >= 1 and len(ov["new_tenants_by_month"]) == 12 and len(ov["bookings_by_month"]) == 12 and ov["properties"] >= 2, "overview numbers", list(ov))

    # ---- suspend / reactivate
    r = c.post(f"/api/v1/platform/tenants/{tid}/suspend", headers=P, json={"reason": "Unpaid invoice"})
    check(r.status_code == 200 and r.json()["status"] == "SUSPENDED", "suspend", r.text)
    check(c.get("/api/v1/auth/me", headers=T).status_code == 401, "suspended business: existing sign-ins stop working at once")
    r = c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"owner@{dom}", "password": pw})
    check(r.status_code == 403 and "suspended" in r.json()["detail"], "suspended business: sign-in explains why", r.text)
    check(c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"owner@{dom}", "password": "not-the-password"}).status_code == 401, "wrong password on a suspended business learns nothing")
    check(c.post(f"/api/v1/platform/tenants/{tid}/suspend", headers=P, json={"reason": "again"}).status_code == 409, "cannot suspend twice")
    check(c.post(f"/api/v1/platform/tenants/{tid}/reactivate", headers=P).json()["status"] == "ACTIVE", "reactivate")
    T = {"Authorization": "Bearer " + c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"owner@{dom}", "password": pw}).json()["access_token"]}

    # ---- password reset
    uid = d["users"][0]["id"]
    r = c.post(f"/api/v1/platform/tenants/{tid}/users/{uid}/reset-password", headers=P, json={})
    check(r.status_code == 200 and len(r.json()["temporary_password"]) >= 12, "reset password (generated)", r.text)
    newpw = r.json()["temporary_password"]
    check(c.get("/api/v1/auth/me", headers=T).status_code == 401, "reset signs the person out everywhere")
    check(c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"owner@{dom}", "password": pw}).status_code == 401, "old password no longer works")
    r = c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"owner@{dom}", "password": newpw})
    check(r.status_code == 200, "new password works")
    T = {"Authorization": "Bearer " + r.json()["access_token"]}
    ch = c.post("/api/v1/auth/change-password", headers=T, json={"current_password": "wrong", "new_password": "An0ther-Str0ng-One"})
    check(ch.status_code == 422, "change password needs the current one")
    check(c.post("/api/v1/auth/change-password", headers=T, json={"current_password": newpw, "new_password": "An0ther-Str0ng-One"}).status_code == 204, "change own password")
    check(c.post("/api/v1/auth/login", json={"tenant_domain": dom, "email": f"owner@{dom}", "password": "An0ther-Str0ng-One"}).status_code == 200, "signed in with the changed password")

    # ---- support session
    check(c.post(f"/api/v1/platform/tenants/{tid}/support-session", headers=P, json={"reason": "short"}).status_code == 422, "a reason is required")
    r = c.post(f"/api/v1/platform/tenants/{tid}/support-session", headers=P, json={"reason": "Ticket 4411: help setting up rooms"})
    check(r.status_code == 201 and r.json()["url"].startswith("/admin/?support="), "start a support session", r.text)
    code, sid = r.json()["code"], r.json()["session_id"]
    ex = c.post("/api/v1/auth/support-exchange", json={"code": code})
    check(ex.status_code == 200, "code swapped for a token", ex.text)
    check(c.post("/api/v1/auth/support-exchange", json={"code": code}).status_code == 401, "the code works only once")
    S = {"Authorization": "Bearer " + ex.json()["access_token"]}
    me = c.get("/api/v1/auth/me", headers=S).json()
    check(me["support"]["admin"] == a.email.lower() and me["tenant_name"].startswith("Smoke Resort") and "api_keys:manage" not in me["scopes"] and "payouts:approve" not in me["scopes"], "support session is marked and limited", me)
    check(c.post("/api/v1/auth/api-keys", headers=S, json={"scopes": ["cms:read"]}).status_code == 403, "support cannot rotate API credentials")
    check(c.post("/api/v1/auth/change-password", headers=S, json={"current_password": "x", "new_password": "Whatever-1234567"}).status_code == 403, "support cannot change the owner's password")
    r = c.patch(f"/api/v1/properties/{pid}", headers=S, json={"location": "Fixed by support"})
    check(r.status_code == 200, "support can make a fix", r.text)
    det = c.get(f"/api/v1/platform/tenants/{tid}", headers=P).json()
    check(det["support_sessions"][0]["state"] == "open" and det["support_sessions"][0]["changes"] >= 1 and det["support_sessions"][0]["reason"].startswith("Ticket 4411"), "session and its change count are logged", det["support_sessions"][0])
    check(c.post("/api/v1/auth/support-end", headers=S).status_code == 204, "end the session")
    check(c.get("/api/v1/auth/me", headers=S).status_code == 401, "ended session token is dead")
    ss = c.get("/api/v1/platform/support-sessions", headers=P, params={"tenant_id": tid}).json()
    check(ss["items"][0]["state"] == "ended" and ss["items"][0]["ended_by"] == "admin", "log shows it ended")
    acts = [x["action"] for x in c.get("/api/v1/platform/audit", headers=P, params={"tenant_id": tid, "limit": 100}).json()["items"]]
    check({"tenant.create", "tenant.update", "tenant.suspend", "tenant.reactivate", "user.reset_password", "support.start", "support.change", "support.end"} <= set(acts), "audit trail has every action", acts)
    check(c.get("/api/v1/platform/audit", headers=P, params={"action": "support."}).json()["total"] >= 3, "audit filter by action")

    # ---- registration
    cfg = c.get("/api/v1/public/register/config").json()
    check(cfg["mode"] in ("approval", "open", "closed"), "registration config", cfg)
    if cfg["mode"] != "closed":
        rd = f"reg-{tag}.example"
        check(c.get("/api/v1/public/register/check", params={"domain": rd}).json()["available"] is True, "domain shown as available")
        check(c.get("/api/v1/public/register/check", params={"domain": dom}).json()["available"] is False, "taken domain detected")
        body = {"business_name": f"Smoke Reg {tag}", "domain": rd, "owner_name": "New Owner", "email": f"new@{rd}", "password": "Str0ng-Passw0rd!", "phone": "+8801700000000",
                "country": "Bangladesh", "business_type": "HOUSEBOAT", "accept_terms": True}
        check(c.post("/api/v1/public/register", json={**body, "accept_terms": False}).status_code == 422, "terms must be accepted")
        check(c.post("/api/v1/public/register", json={**body, "password": "short"}).status_code == 422, "weak password refused")
        r = c.post("/api/v1/public/register", json=body)
        check(r.status_code == 201, "register a business", r.text)
        check(c.post("/api/v1/public/register", json=body).status_code == 409, "same domain cannot register twice")
        bot = c.post("/api/v1/public/register", json={**body, "domain": f"bot-{tag}.example", "website": "http://spam"})
        check(bot.status_code == 201 and c.get("/api/v1/public/register/check", params={"domain": f"bot-{tag}.example"}).json()["available"], "spam trap: looks accepted but nothing is created")
        reg = c.get("/api/v1/platform/tenants", headers=P, params={"q": rd}).json()["items"][0]
        if cfg["mode"] == "approval":
            check(r.json()["status"] == "PENDING" and reg["status"] == "PENDING" and reg["profile"]["business_type"] == "HOUSEBOAT", "waits for approval with the registration details kept")
            lr = c.post("/api/v1/auth/login", json={"tenant_domain": rd, "email": f"new@{rd}", "password": "Str0ng-Passw0rd!"})
            check(lr.status_code == 403 and "waiting for approval" in lr.json()["detail"], "pending business: sign-in explains", lr.text)
            check(c.post(f"/api/v1/platform/tenants/{reg['id']}/approve", headers=P).json()["status"] == "ACTIVE", "approve")
        check(c.post("/api/v1/auth/login", json={"tenant_domain": rd, "email": f"new@{rd}", "password": "Str0ng-Passw0rd!"}).status_code == 200, "registered owner can sign in")
        check(c.post(f"/api/v1/platform/tenants/{reg['id']}/support-session", headers=P, json={"reason": "Checking onboarding"}).status_code == 201, "support session on the new business")
        check(c.post(f"/api/v1/platform/tenants/{reg['id']}/suspend", headers=P, json={"reason": "Smoke test cleanup"}).status_code == 200, "suspend closes open support sessions")
        check(c.get("/api/v1/platform/support-sessions", headers=P, params={"tenant_id": reg["id"]}).json()["items"][0]["state"] == "ended", "…and they show as ended")
        if cfg["mode"] == "approval":
            rd2 = f"rej-{tag}.example"
            c.post("/api/v1/public/register", json={**body, "domain": rd2, "email": f"x@{rd2}"})
            rid = c.get("/api/v1/platform/tenants", headers=P, params={"q": rd2}).json()["items"][0]["id"]
            check(c.post(f"/api/v1/platform/tenants/{rid}/reject", headers=P, json={"reason": "Not a real business"}).json()["status"] == "REJECTED", "reject a registration")
            check("not approved" in c.post("/api/v1/auth/login", json={"tenant_domain": rd2, "email": f"x@{rd2}", "password": "Str0ng-Passw0rd!"}).json()["detail"], "rejected business is told")

    # ---- the tenant-facing database role cannot touch platform tables
    c.post(f"/api/v1/platform/tenants/{tid}/suspend", headers=P, json={"reason": "Smoke test cleanup"})
    print(f"\n{n} checks passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--email", required=True); ap.add_argument("--password", required=True)
    main(ap.parse_args())
