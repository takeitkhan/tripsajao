"""Media library: validating, storing and describing photos and videos.

Safety rules: only formats we can verify are accepted (no SVG, no HTML); photos are re-encoded so hidden
data (GPS, scripts appended to the file) is dropped; videos are checked with ffprobe when it is installed;
files get random names and are served with a fixed content type."""
import asyncio
import io
import json
import os
import re
import shutil
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import Text, cast, func, or_, select

from app.core.config import settings
from app.models import CMSContent, MediaAsset, Property, Tenant, Unit
from app.models.enums import MediaKind, MediaSource
from app.services.limits import limit_of

Image.MAX_IMAGE_PIXELS = 80_000_000          # decompression-bomb guard
ROOT = Path(settings.media_root).resolve()
TMP = ROOT / "_tmp"
THUMB_PX = 480
MAX_SIDE = 4000

IMAGE_TYPES = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp"), "GIF": ("image/gif", "gif")}
VIDEO_TYPES = {"mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm"}
CONTENT_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif", **VIDEO_TYPES}
ALLOWED = {"images": ["JPG", "PNG", "WEBP", "GIF"], "videos": ["MP4", "MOV", "WEBM"]}
FILENAME_RE = re.compile(r"^[0-9a-f-]{36}(_t)?\.(jpg|png|webp|gif|mp4|mov|webm)$")

_HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def init_storage() -> None:
    TMP.mkdir(parents=True, exist_ok=True)


def file_path(tenant_id: str, name: str) -> Path | None:
    if not FILENAME_RE.match(name):
        return None
    try:
        tid = str(uuid.UUID(tenant_id))
    except ValueError:
        return None
    return ROOT / tid / name


def public_url(tenant_id, name: str) -> str:
    return f"{settings.public_api_base_url.rstrip('/')}/media/{tenant_id}/{name}"


# --------------------------------------------------------------------------- external links
def parse_link(raw: str) -> tuple[str, str, str | None, str | None]:
    """-> (canonical_url, provider, embed_url, thumbnail_url)"""
    u = urlparse(raw.strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise HTTPException(422, "Enter a full link that starts with https://")
    host = u.hostname.lower().removeprefix("www.").removeprefix("m.")
    vid = None
    if host == "youtu.be":
        vid = u.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "youtube-nocookie.com"):
        if u.path == "/watch":
            vid = (parse_qs(u.query).get("v") or [None])[0]
        else:
            m = re.match(r"^/(embed|shorts|live|v)/([\w-]{11})", u.path)
            vid = m.group(2) if m else None
    if host in ("youtu.be", "youtube.com", "youtube-nocookie.com"):
        if not vid or not re.fullmatch(r"[\w-]{11}", vid):
            raise HTTPException(422, "That YouTube link does not point to a video.")
        return (f"https://www.youtube.com/watch?v={vid}", "youtube", f"https://www.youtube-nocookie.com/embed/{vid}",
                f"https://img.youtube.com/vi/{vid}/hqdefault.jpg")
    if host == "vimeo.com":
        m = re.match(r"^/(?:channels/[\w-]+/|groups/[\w-]+/videos/)?(\d+)", u.path)
        if not m:
            raise HTTPException(422, "That Vimeo link does not point to a video.")
        return (f"https://vimeo.com/{m.group(1)}", "vimeo", f"https://player.vimeo.com/video/{m.group(1)}", None)
    if re.search(r"\.(mp4|webm|mov|m4v)$", u.path, re.I):
        return raw.strip(), "file", None, None
    raise HTTPException(422, "Use a YouTube or Vimeo link, or a direct link to an .mp4 or .webm file.")


# --------------------------------------------------------------------------- output
def describe(a: MediaAsset) -> dict:
    d = {c: getattr(a, c) for c in ("id", "kind", "source", "title", "alt_text", "original_name", "mime_type", "size_bytes",
                                    "width", "height", "duration_seconds", "created_at")}
    d["tags"] = list(a.tags or [])
    if a.source == MediaSource.UPLOAD:
        d.update(url=public_url(a.tenant_id, a.storage_key), provider="upload", embed_url=None,
                 thumbnail_url=public_url(a.tenant_id, a.thumb_key) if a.thumb_key else None)
    else:
        url, provider, embed, thumb = parse_link(a.external_url)
        d.update(url=url, provider=provider, embed_url=embed, thumbnail_url=thumb)
    return d


# --------------------------------------------------------------------------- processing (blocking; run in threads)
def _process_image(src: Path, dest_dir: Path, asset_id: uuid.UUID) -> dict:
    try:
        with Image.open(src) as im:
            fmt = im.format
            if fmt not in IMAGE_TYPES:
                raise HTTPException(422, "Photos must be JPG, PNG, WEBP or GIF.")
            im.load()
            mime, ext = IMAGE_TYPES[fmt]
            animated = getattr(im, "is_animated", False)
            name = f"{asset_id}.{ext}"
            if fmt == "GIF":
                shutil.copyfile(src, dest_dir / name)      # keep animation; the file was fully decoded above
                w, h = im.size
                thumb_src = im.convert("RGBA")
            else:
                work = ImageOps.exif_transpose(im)          # honour camera rotation, then drop all metadata
                if max(work.size) > MAX_SIDE:
                    work.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
                if fmt == "JPEG" and work.mode not in ("RGB", "L"):
                    work = work.convert("RGB")
                w, h = work.size
                kw = {"quality": 88, "optimize": True} if fmt == "JPEG" else ({"quality": 88} if fmt == "WEBP" else {"optimize": True})
                work.save(dest_dir / name, format=fmt, **kw)
                thumb_src = work
            thumb = thumb_src.copy()
            thumb.thumbnail((THUMB_PX, THUMB_PX), Image.LANCZOS)
            if thumb.mode not in ("RGB", "RGBA"):
                thumb = thumb.convert("RGBA" if "A" in thumb.getbands() else "RGB")
            tname = f"{asset_id}_t.webp"
            thumb.save(dest_dir / tname, format="WEBP", quality=80)
    except HTTPException:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError):
        raise HTTPException(422, "This file is not a valid photo, or it is too large to process.")
    return dict(mime_type=mime, storage_key=name, thumb_key=tname, width=w, height=h, size_bytes=(dest_dir / name).stat().st_size)


def _sniff_video(src: Path) -> str | None:
    head = src.read_bytes()[:16] if src.stat().st_size >= 16 else b""
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if head[4:8] == b"ftyp":
        return "mov" if head[8:12] == b"qt  " else "mp4"
    return None


def _process_video(src: Path, dest_dir: Path, asset_id: uuid.UUID) -> dict:
    ext = _sniff_video(src)
    if not ext:
        raise HTTPException(422, "Videos must be MP4, MOV or WEBM.")
    out = dict(mime_type=VIDEO_TYPES[ext], storage_key=f"{asset_id}.{ext}", thumb_key=None, width=None, height=None, duration_seconds=None)
    if _HAS_FFMPEG:
        import subprocess
        try:
            r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(src)],
                               capture_output=True, timeout=30, check=True)
            info = json.loads(r.stdout)
        except (subprocess.SubprocessError, ValueError):
            raise HTTPException(422, "This video could not be read. Try exporting it again as MP4.")
        vs = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
        if not vs:
            raise HTTPException(422, "No picture was found in this video file.")
        out.update(width=vs.get("width"), height=vs.get("height"))
        try:
            out["duration_seconds"] = round(float(info.get("format", {}).get("duration")), 2)
        except (TypeError, ValueError):
            pass
        tname = f"{asset_id}_t.webp"
        at = min(1.0, (out["duration_seconds"] or 0) / 2)
        try:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", str(src), "-frames:v", "1",
                            "-vf", f"scale='min({THUMB_PX},iw)':-2", "-c:v", "libwebp", "-quality", "80", str(dest_dir / tname)],
                           capture_output=True, timeout=60, check=True)
            if (dest_dir / tname).exists():
                out["thumb_key"] = tname
        except subprocess.SubprocessError:
            pass                                             # a missing preview is fine
    shutil.move(str(src), str(dest_dir / out["storage_key"]))
    out["size_bytes"] = (dest_dir / out["storage_key"]).stat().st_size
    return out


# --------------------------------------------------------------------------- public API of the module
def limits() -> dict:
    return {"image": settings.max_image_mb * 1024 * 1024, "video": settings.max_video_mb * 1024 * 1024}


async def tenant_usage(session, tenant_id) -> int:
    return int((await session.execute(select(func.coalesce(func.sum(MediaAsset.size_bytes), 0)).where(MediaAsset.tenant_id == tenant_id))).scalar_one())


async def store_upload(session, tenant, user_id, up: UploadFile, title: str | None, alt: str | None, tags: list[str]) -> MediaAsset:
    init_storage()
    lim = limits()
    hard_cap = max(lim.values())
    tmp = TMP / f"{uuid.uuid4().hex}.part"
    size = 0
    try:
        with open(tmp, "wb") as f:
            while chunk := await up.read(1024 * 1024):
                size += len(chunk)
                if size > hard_cap:
                    raise HTTPException(413, f"This file is larger than the {settings.max_video_mb} MB limit.")
                await asyncio.to_thread(f.write, chunk)
        if size == 0:
            raise HTTPException(422, "The file is empty.")
        asset_id = uuid.uuid4()
        dest_dir = ROOT / str(tenant.id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        is_video = _sniff_video(tmp) is not None
        if size > (lim["video"] if is_video else lim["image"]):
            raise HTTPException(413, f"This {'video' if is_video else 'photo'} is larger than the "
                                     f"{settings.max_video_mb if is_video else settings.max_image_mb} MB limit.")
        used = await tenant_usage(session, tenant.id)
        if used + size > limit_of(tenant, 'media_quota_mb') * 1024 * 1024:
            raise HTTPException(413, "Your media storage is full. Delete files you no longer use, then try again.")
        meta = await asyncio.to_thread(_process_video if is_video else _process_image, tmp, dest_dir, asset_id)
    finally:
        await up.close()
        tmp.unlink(missing_ok=True)
    stem = os.path.splitext(os.path.basename(up.filename or ""))[0].strip()[:150]
    asset = MediaAsset(id=asset_id, tenant_id=tenant.id, kind=MediaKind.VIDEO if is_video else MediaKind.IMAGE, source=MediaSource.UPLOAD,
                       title=(title or stem or "Untitled").strip()[:200], alt_text=(alt or None), tags=tags,
                       original_name=(os.path.basename(up.filename or "") or None) and os.path.basename(up.filename)[:255],
                       created_by=user_id, **meta)
    session.add(asset)
    await session.flush()
    return asset


def remove_files(asset: MediaAsset) -> None:
    for key in (asset.storage_key, asset.thumb_key):
        if key:
            (ROOT / str(asset.tenant_id) / key).unlink(missing_ok=True)


async def find_usage(session, tenant: Tenant, asset: MediaAsset) -> list[dict]:
    needles = [str(asset.id)] + ([asset.external_url] if asset.external_url else [])
    def like(col):
        return or_(*[cast(col, Text).like("%" + n.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%", escape="\\") for n in needles])
    places: list[dict] = []
    for pid, name in (await session.execute(select(Property.id, Property.name).where(Property.tenant_id == tenant.id, like(Property.metadata_json)))).all():
        places.append({"kind": "Property", "name": name, "id": pid})
    for uid, name, pname in (await session.execute(
            select(Unit.id, Unit.unit_name, Property.name).join(Property, Property.id == Unit.property_id)
            .where(Unit.tenant_id == tenant.id, like(Unit.media_json)))).all():
        places.append({"kind": "Unit", "name": f"{pname} / {name}", "id": uid})
    for cid, title, ctype in (await session.execute(select(CMSContent.id, CMSContent.title, CMSContent.content_type)
                                                     .where(CMSContent.tenant_id == tenant.id, like(CMSContent.payload_json)))).all():
        places.append({"kind": ctype.value.capitalize(), "name": title, "id": cid})
    company = (tenant.settings_json or {}).get("company", {})
    if any(n in json.dumps(company) for n in needles):
        places.append({"kind": "Company", "name": "Business details (logo)", "id": None})
    return places
