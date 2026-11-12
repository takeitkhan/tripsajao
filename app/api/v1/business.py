from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import TenantContext, authorize
from app.schemas.business import REQUIRED, BusinessIn, BusinessOut, BusinessPublic, PublicAccount

router = APIRouter(prefix="/business", tags=["business"])


def _read(ctx: TenantContext) -> BusinessOut:
    st = ctx.tenant.settings_json or {}
    biz, company = dict(st.get("business", {})), st.get("company", {}) or {}
    data = {**biz, "name": company.get("name") or ctx.tenant.name, "logo_url": company.get("logo_url"),
            "hold_minutes": round(int(st.get("hold_seconds", 600)) / 60) or 1, "event_hold_minutes": round(int(st.get("event_hold_seconds", st.get("hold_seconds", 600))) / 60) or 1,
            "deposit_percent": int(st.get("deposit_percent", 50))}
    out = BusinessOut.model_validate(data)
    out.missing = [label for key, label in REQUIRED.items() if not getattr(out, key)]
    out.complete = not out.missing
    return out


@router.get("", response_model=BusinessOut, summary="Business profile: licence, owner, tax numbers, bank and mobile banking accounts, booking rules")
async def get_business(ctx: TenantContext = Depends(authorize("business:read"))):
    return _read(ctx)


@router.put("", response_model=BusinessOut, summary="Save the business profile (logo and owner's photo are required)")
async def put_business(body: BusinessIn, ctx: TenantContext = Depends(authorize("business:manage"))):
    missing = [label for key, label in REQUIRED.items() if not getattr(body, key)]
    if missing:
        raise HTTPException(422, f"Please add: {', '.join(missing)}")
    st = dict(ctx.tenant.settings_json or {})
    company = {**(st.get("company") or {}), "name": body.name, "logo_url": body.logo_url}
    keep = body.model_dump(mode="json", exclude={"name", "logo_url", "hold_minutes", "event_hold_minutes", "deposit_percent"})
    st.update(company=company, business=keep, hold_seconds=body.hold_minutes * 60, event_hold_seconds=body.event_hold_minutes * 60, deposit_percent=body.deposit_percent)
    ctx.tenant.settings_json = st                                   # reassign -> dirty
    return _read(ctx)


@router.get("/public", response_model=BusinessPublic, summary="What a website may show about the business (no private contact details)")
async def public(ctx: TenantContext = Depends(authorize("cms:read"))):
    st = ctx.tenant.settings_json or {}
    b, c = st.get("business", {}) or {}, st.get("company", {}) or {}
    accounts = [PublicAccount(kind="BANK", title=a["bank_name"], account_name=a.get("account_name"), number=a["account_number"],
                              detail=", ".join(x for x in (a.get("branch"), f"Routing {a['routing_no']}" if a.get("routing_no") else None) if x) or None, is_primary=a.get("is_primary", False))
                for a in b.get("bank_accounts", []) if a.get("show_to_customers", True)]
    accounts += [PublicAccount(kind="MFS", title=f"{a['provider']} ({a.get('account_type', 'Personal')})", account_name=a.get("account_name"), number=a["number"],
                               is_primary=a.get("is_primary", False)) for a in b.get("mfs_accounts", []) if a.get("show_to_customers", True)]
    return BusinessPublic(name=c.get("name") or ctx.tenant.name, legal_name=b.get("legal_name"), logo_url=c.get("logo_url"), tagline=c.get("tagline"),
                          owner_name=b.get("owner_name"), owner_photo=b.get("owner_photo"), license_no=b.get("license_no"), tin=b.get("tin"), bin=b.get("bin"),
                          email=c.get("email"), phone=c.get("phone"), whatsapp=b.get("whatsapp"), website=b.get("website"), address=c.get("address"),
                          office_hours=b.get("office_hours"), currency=c.get("currency"), terms=b.get("terms"), cancellation_policy=b.get("cancellation_policy"),
                          payment_accounts=accounts)
