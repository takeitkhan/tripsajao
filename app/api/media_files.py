"""Public file serving for uploaded media. Names are random UUIDs; only known extensions are served, with a fixed content type."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services import media as svc

router = APIRouter(include_in_schema=False)


@router.get("/media/{tenant_id}/{name}")
async def serve(tenant_id: str, name: str):
    p = svc.file_path(tenant_id, name)
    if p is None or not p.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(p, media_type=svc.CONTENT_TYPES[name.rsplit(".", 1)[1]],
                        headers={"Cache-Control": "public, max-age=31536000, immutable", "Content-Disposition": "inline",
                                 "Content-Security-Policy": "default-src 'none'; sandbox", "Cross-Origin-Resource-Policy": "cross-origin"})
