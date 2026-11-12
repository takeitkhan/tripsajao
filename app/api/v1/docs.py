from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import settings
from app.core.deps import TenantContext, authorize
from app.schemas.docs import ModuleDocs, ModuleSummary
from app.services.api_docs import build_module_docs, list_modules

router = APIRouter(prefix="/docs", tags=["docs"])


@router.get("/modules", response_model=list[ModuleSummary], summary="List documentable modules")
async def modules(request: Request, ctx: TenantContext = Depends(authorize("docs:read"))):
    return list_modules(request.app)


@router.get("/module/{module_name}", response_model=ModuleDocs,
            summary="Endpoint specs + cURL / JS (fetch, axios) / Python snippets for one module (feeds the admin 'API Documentation' tab)")
async def module_docs(module_name: str, request: Request, ctx: TenantContext = Depends(authorize("docs:read"))):
    docs = build_module_docs(request.app, module_name.lower(), settings.public_api_base_url)
    if docs is None:
        raise HTTPException(404, "Unknown module")
    return docs
