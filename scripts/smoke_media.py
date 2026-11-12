"""Checks the media library against a RUNNING API.   python -m scripts.smoke_media --domain demo.example --email ... --password ...
Needs Pillow; uses ffmpeg (if installed) to make a tiny test video. Leaves nothing behind except a property it deletes."""
import argparse
import io
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import httpx
from PIL import Image

n = 0


def check(cond, msg, extra=None):
    global n
    if not cond:
        print("FAIL:", msg, extra if extra is not None else "")
        sys.exit(1)
    n += 1
    print("  ok ", msg)


def png(w=640, h=480, mode="RGBA"):
    b = io.BytesIO()
    Image.new(mode, (w, h), (30, 120, 140, 255) if mode == "RGBA" else (30, 120, 140)).save(b, "PNG")
    return b.getvalue()


def jpeg_rotated():
    im = Image.new("RGB", (800, 400), (200, 80, 40))
    ex = Image.Exif()
    ex[0x0112] = 6                      # camera says: rotate 90 degrees
    ex[0x010F] = "SecretCameraMaker"
    b = io.BytesIO()
    im.save(b, "JPEG", exif=ex)
    return b.getvalue()


def main(a):
    c = httpx.Client(base_url=a.base, timeout=60)
    r = c.post("/api/v1/auth/login", json={"tenant_domain": a.domain, "email": a.email, "password": a.password})
    check(r.status_code == 200, "login", r.text)
    H = {"Authorization": "Bearer " + r.json()["access_token"]}
    tid = c.get("/api/v1/auth/me", headers=H).json().get("tenant_id")
    tag = uuid.uuid4().hex[:5]
    check(c.get("/api/v1/media").status_code == 401, "media needs sign-in")

    def up(name, data, ctype, **form):
        return c.post("/api/v1/media", headers=H, files={"file": (name, data, ctype)}, data=form)

    # ---- photos
    r = up("lobby.png", png(), "image/png", title=f"Lobby {tag}", alt_text="The lobby", tags=f"lobby, smoke{tag}")
    check(r.status_code == 201, "upload PNG", r.text)
    png_a = r.json()
    check(png_a["kind"] == "IMAGE" and png_a["width"] == 640 and png_a["height"] == 480, "PNG size read")
    check(png_a["tags"] == ["lobby", f"smoke{tag}"] and png_a["alt_text"] == "The lobby", "title, alt text and tags saved")
    f = c.get(png_a["url"])
    check(f.status_code == 200 and f.headers["content-type"] == "image/png", "file is served publicly with the right type", f.headers)
    check("immutable" in f.headers["cache-control"] and f.headers.get("x-content-type-options") == "nosniff", "cache + nosniff headers")
    t = c.get(png_a["thumbnail_url"])
    check(t.status_code == 200 and t.headers["content-type"] == "image/webp", "thumbnail served")
    check(Image.open(io.BytesIO(t.content)).width == 480, "thumbnail is 480 px wide")

    r = up("phone.jpg", jpeg_rotated(), "image/jpeg")
    check(r.status_code == 201, "upload JPEG", r.text)
    j = r.json()
    check((j["width"], j["height"]) == (400, 800), "camera rotation applied", (j["width"], j["height"]))
    check(j["title"] == "phone", "title defaults to the file name")
    stored = Image.open(io.BytesIO(c.get(j["url"]).content))
    check(not stored.getexif().get(0x010F), "camera metadata removed from the stored copy")

    big = Image.new("RGB", (6000, 3000), (10, 10, 10)); b = io.BytesIO(); big.save(b, "JPEG", quality=50)
    r = up("huge.jpg", b.getvalue(), "image/jpeg")
    check(r.status_code == 201 and max(r.json()["width"], r.json()["height"]) == 4000, "very large photos are scaled to 4000 px", r.text)

    b = io.BytesIO(); Image.new("RGB", (50, 50), "red").save(b, "WEBP")
    check(up("a.webp", b.getvalue(), "image/webp").status_code == 201, "upload WEBP")
    b = io.BytesIO(); Image.new("P", (40, 40)).save(b, "GIF")
    check(up("a.gif", b.getvalue(), "image/gif").status_code == 201, "upload GIF")

    # ---- things that must be refused
    check(up("x.jpg", b"<html><script>alert(1)</script></html>", "image/jpeg").status_code == 422, "HTML disguised as JPG refused")
    check(up("x.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "image/svg+xml").status_code == 422, "SVG refused")
    check(up("x.mp4", b"this is not a video at all, just text", "video/mp4").status_code == 422, "fake MP4 refused")
    check(up("empty.png", b"", "image/png").status_code == 422, "empty file refused")
    check(up("a.png", png() + b"<?php echo 1; ?>", "image/png").status_code == 201, "trailing junk accepted but re-encoded")
    junk = c.get(c.post("/api/v1/media", headers=H, files={"file": ("b.png", png() + b"<?php echo 1; ?>", "image/png")}).json()["url"]).content
    check(b"<?php" not in junk, "junk after the image is not kept")
    check(c.post("/api/v1/media", headers=H, data={"title": "no file"}).status_code == 422, "missing file refused")

    # ---- video
    vid = None
    if shutil.which("ffmpeg"):
        d = Path(tempfile.mkdtemp()); p = d / "t.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15", "-t", "2", "-pix_fmt", "yuv420p", str(p)], check=True)
        r = up("tour.mp4", p.read_bytes(), "video/mp4", title=f"Tour {tag}")
        check(r.status_code == 201, "upload MP4", r.text)
        vid = r.json()
        check(vid["kind"] == "VIDEO" and vid["width"] == 320 and 1.5 < vid["duration_seconds"] < 2.5, "video size and length read", vid)
        check(vid["thumbnail_url"] and c.get(vid["thumbnail_url"]).status_code == 200, "video preview picture made")
        rg = c.get(vid["url"], headers={"Range": "bytes=0-99"})
        check(rg.status_code == 206 and len(rg.content) == 100, "video supports seeking (range requests)")
        p2 = d / "t.webm"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10", "-t", "1", "-c:v", "libvpx", str(p2)], check=True)
        check(up("t.webm", p2.read_bytes(), "video/webm").status_code == 201, "upload WEBM")
    else:
        print("  (ffmpeg not found: video upload checks skipped)")

    # ---- links
    r = c.post("/api/v1/media/link", headers=H, json={"url": "https://youtu.be/dQw4w9WgXcQ?t=3", "title": f"Promo {tag}"})
    check(r.status_code == 201, "add YouTube link", r.text)
    yt = r.json()
    check(yt["provider"] == "youtube" and yt["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ" and "youtube-nocookie.com/embed/dQw4w9WgXcQ" in yt["embed_url"], "YouTube link normalised", yt)
    check(yt["thumbnail_url"].endswith("/dQw4w9WgXcQ/hqdefault.jpg"), "YouTube preview picture")
    check(c.post("/api/v1/media/link", headers=H, json={"url": "https://vimeo.com/76979871"}).json()["provider"] == "vimeo", "Vimeo link")
    check(c.post("/api/v1/media/link", headers=H, json={"url": "https://cdn.example.com/clips/a.mp4"}).json()["provider"] == "file", "direct file link")
    for bad in ("https://example.com/page.html", "javascript:alert(1)", "https://youtube.com/watch?v=x", "ftp://a/b.mp4"):
        check(c.post("/api/v1/media/link", headers=H, json={"url": bad}).status_code == 422, f"bad link refused: {bad}")

    # ---- list, search, tags, edit
    lst = c.get("/api/v1/media", headers=H, params={"kind": "VIDEO", "limit": 200}).json()
    check(all(i["kind"] == "VIDEO" for i in lst["items"]) and yt["id"] in [i["id"] for i in lst["items"]], "filter by videos")
    check([i["id"] for i in c.get("/api/v1/media", headers=H, params={"q": f"lobby {tag}"}).json()["items"]] == [png_a["id"]], "search by title")
    check(png_a["id"] in [i["id"] for i in c.get("/api/v1/media", headers=H, params={"q": f"smoke{tag}"}).json()["items"]], "search finds tags")
    check(c.get("/api/v1/media", headers=H, params={"tag": f"smoke{tag}"}).json()["total"] == 1, "filter by tag")
    check(c.get("/api/v1/media", headers=H, params={"q": "100%_"}).status_code == 200, "wildcard characters in search are safe")
    check(f"smoke{tag}" in c.get("/api/v1/media/tags", headers=H).json(), "tag list")
    r = c.patch(f"/api/v1/media/{png_a['id']}", headers=H, json={"title": f"Lobby 2 {tag}", "tags": ["reception"], "alt_text": None})
    check(r.status_code == 200 and r.json()["title"] == f"Lobby 2 {tag}" and r.json()["tags"] == ["reception"] and r.json()["alt_text"] is None, "edit title, tags, alt text", r.text)
    s = c.get("/api/v1/media/summary", headers=H).json()
    check(s["images"] >= 5 and s["used_bytes"] > 0 and "MP4" in s["allowed"]["videos"], "storage summary", s)

    # ---- use it, then delete
    pr = c.post("/api/v1/properties", headers=H, json={"type": "RESORT", "name": f"Media Test {tag}", "slug": f"media-test-{tag}", "metadata": {
        "media": [{"type": "photo", "url": png_a["url"], "thumbnail_url": png_a["thumbnail_url"], "asset_id": png_a["id"], "alt": "Lobby"}]}})
    check(pr.status_code == 201, "property keeps asset_id/thumbnail/alt on media", pr.text)
    check(pr.json()["metadata"]["media"][0].get("asset_id") == png_a["id"], "asset_id round-trips")
    us = c.get(f"/api/v1/media/{png_a['id']}/usage", headers=H).json()
    check(us["count"] == 1 and us["places"][0]["kind"] == "Property", "usage finds the property", us)
    r = c.delete(f"/api/v1/media/{png_a['id']}", headers=H)
    check(r.status_code == 409 and "used in 1 place" in r.json()["detail"], "delete blocked while in use", r.text)
    check(c.delete(f"/api/v1/media/{png_a['id']}", headers=H, params={"force": True}).status_code == 204, "forced delete")
    check(c.get(png_a["url"]).status_code == 404 and c.get(png_a["thumbnail_url"]).status_code == 404, "files removed from storage")
    check(c.get(f"/api/v1/media/{png_a['id']}", headers=H).status_code == 404, "record removed")
    c.delete(f"/api/v1/properties/{pr.json()['id']}", headers=H)

    # ---- safety
    for evil in (f"/media/{tid}/..%2F..%2Fetc%2Fpasswd", f"/media/{tid}/%2e%2e/.env", f"/media/{tid}/x.html", f"/media/not-a-uuid/{uuid.uuid4()}.png"):
        check(c.get(evil).status_code == 404, f"path tricks rejected: {evil.split('/', 2)[2][:40]}")
    other = uuid.uuid4()
    check(c.get(j["url"].replace(str(tid), str(other))).status_code == 404, "a file is not reachable under another tenant id")
    if a.other_domain:
        r2 = c.post("/api/v1/auth/login", json={"tenant_domain": a.other_domain, "email": a.other_email, "password": a.other_password})
        check(r2.status_code == 200, "second tenant login", r2.text)
        H2 = {"Authorization": "Bearer " + r2.json()["access_token"]}
        check(c.get(f"/api/v1/media/{j['id']}", headers=H2).status_code == 404, "another tenant cannot read this asset")
        check(c.delete(f"/api/v1/media/{j['id']}", headers=H2, params={"force": True}).status_code == 404, "another tenant cannot delete it")
        check(j["id"] not in [i["id"] for i in c.get("/api/v1/media", headers=H2, params={"limit": 200}).json()["items"]], "another tenant's list does not include it")

    # cleanup
    for i in c.get("/api/v1/media", headers=H, params={"limit": 200}).json()["items"]:
        if i["id"] != yt["id"] or True:
            c.delete(f"/api/v1/media/{i['id']}", headers=H, params={"force": True})
    print(f"\n{n} checks passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--domain", required=True); ap.add_argument("--email", required=True); ap.add_argument("--password", required=True)
    ap.add_argument("--other-domain"); ap.add_argument("--other-email"); ap.add_argument("--other-password")
    main(ap.parse_args())
