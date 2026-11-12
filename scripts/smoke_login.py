"""Checks signing in with and without the business domain against a RUNNING API."""
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
    mail = f"same-{tag}@example.com"
    made = []
    for i in (1, 2):
        d = f"lg{i}-{tag}.example"
        r = c.post("/api/v1/platform/tenants", headers=P, json={"name": f"Login {i} {tag}", "domain": d, "admin_name": "Owner", "admin_email": mail})
        check(r.status_code == 201, f"business {i} created", r.text)
        made.append((d, r.json()["temporary_password"]))
    uniq = f"solo-{tag}@example.com"
    d3 = f"lg3-{tag}.example"
    r = c.post("/api/v1/platform/tenants", headers=P, json={"name": f"Login 3 {tag}", "domain": d3, "admin_name": "Solo", "admin_email": uniq})
    pw3 = r.json()["temporary_password"]

    me = lambda tok: c.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + tok}).json()
    r = c.post("/api/v1/auth/login", json={"email": uniq, "password": pw3})
    check(r.status_code == 200 and me(r.json()["access_token"])["tenant_domain"] == d3, "no domain: an e-mail used in one business signs in and shows its domain", r.text)
    check(c.post("/api/v1/auth/login", json={"tenant_domain": "", "email": uniq, "password": pw3}).status_code == 200, "an empty domain counts as no domain")
    check(c.post("/api/v1/auth/login", json={"tenant_domain": d3, "email": uniq, "password": pw3}).status_code == 200, "with the domain it still works")
    r = c.post("/api/v1/auth/login", json={"email": uniq, "password": "wrong-password-1"})
    check(r.status_code == 401 and r.json()["detail"] == "Invalid credentials", "a wrong password is refused like before")
    check(c.post("/api/v1/auth/login", json={"email": f"nobody-{tag}@example.com", "password": "whatever-pass-1"}).status_code == 401, "an unknown e-mail gets the same answer")
    check(c.post("/api/v1/auth/login", json={"email": uniq, "password": pw3, "principal": "partner"}).status_code == 401, "a staff account cannot sign in as a partner")

    # the same e-mail in two businesses
    (d1, p1), (d2, p2) = made
    check(p1 != p2, "the two businesses have different passwords")
    r1 = c.post("/api/v1/auth/login", json={"email": mail, "password": p1})
    r2 = c.post("/api/v1/auth/login", json={"email": mail, "password": p2})
    check(r1.status_code == 200 and me(r1.json()["access_token"])["tenant_domain"] == d1 and r2.status_code == 200 and me(r2.json()["access_token"])["tenant_domain"] == d2,
          "one e-mail in two businesses: the password decides which one", (r1.text, r2.text))
    # make both passwords equal -> must ask for the domain
    A1 = {"Authorization": "Bearer " + r1.json()["access_token"]}
    A2 = {"Authorization": "Bearer " + r2.json()["access_token"]}
    shared = "Shared-Passw0rd-" + tag
    for A_, cur in ((A1, p1), (A2, p2)):
        r = c.post("/api/v1/auth/change-password", headers=A_, json={"current_password": cur, "new_password": shared})
        check(r.status_code in (200, 204), "password changed", r.text)
    r = c.post("/api/v1/auth/login", json={"email": mail, "password": shared})
    check(r.status_code == 409 and "domain" in r.json()["detail"], "the same e-mail and password in two businesses asks for the domain", r.text)
    check(c.post("/api/v1/auth/login", json={"tenant_domain": d2, "email": mail, "password": shared}).status_code == 200, "...and the domain settles it")
    # lockout
    for _ in range(12):
        r = c.post("/api/v1/auth/login", json={"email": f"lock-{tag}@example.com", "password": "bad-password-123"})
    check(r.status_code == 429, "repeated wrong tries without a domain are limited")
    print(f"\n{n} checks passed")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://localhost:8000")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    main(p.parse_args())
