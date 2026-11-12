from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from app.core.constants import PERMISSION_GROUPS, ROLE_SCOPES, effective_scopes
from app.core.deps import TenantContext, authorize, persist
from app.core.redis import get_redis
from app.core.security import hash_password
from app.models import Role, User
from app.schemas.staff import (PasswordResult, PermissionCatalog, PermissionGroup, PermissionLevel, ResetPassword, StaffCreate, StaffCreated, StaffOut,
                               StaffUpdate)
from app.services.platform import generate_password

router = APIRouter(prefix="/staff", tags=["staff"])


def _out(u: User) -> StaffOut:
    scopes = effective_scopes(u.role.value, u.permissions)
    return StaffOut(id=u.id, name=u.name, email=u.email, role=u.role, is_active=u.is_active, custom_access=u.permissions is not None and u.role != Role.ADMIN,
                    permissions=sorted(scopes), created_at=u.created_at)


async def _user(ctx: TenantContext, user_id: UUID) -> User:
    u = await ctx.session.get(User, user_id)
    if u is None or u.tenant_id != ctx.tenant.id:
        raise HTTPException(404, "User not found")
    return u


async def _other_admins(ctx: TenantContext, user: User) -> int:
    return (await ctx.session.execute(select(func.count()).select_from(User).where(
        User.tenant_id == ctx.tenant.id, User.role == Role.ADMIN, User.is_active.is_(True), User.id != user.id))).scalar_one()


@router.get("/permissions", response_model=PermissionCatalog, summary="What access can be given, group by group")
async def catalog(ctx: TenantContext = Depends(authorize("staff:manage"))):
    return PermissionCatalog(
        groups=[PermissionGroup(key=g["key"], label=g["label"], levels=[PermissionLevel(key=k, label=l, scopes=s) for k, l, s in g["levels"]]) for g in PERMISSION_GROUPS],
        defaults={r: sorted(s) for r, s in ROLE_SCOPES.items() if r != "ADMIN"})


@router.get("", response_model=list[StaffOut], summary="Everyone who can sign in to this business")
async def list_staff(ctx: TenantContext = Depends(authorize("staff:manage"))):
    rows = (await ctx.session.execute(select(User).where(User.tenant_id == ctx.tenant.id).order_by(User.is_active.desc(), User.role, func.lower(User.name)))).scalars().all()
    return [_out(u) for u in rows]


@router.post("", response_model=StaffCreated, status_code=201, summary="Add a staff account")
async def create(body: StaffCreate, ctx: TenantContext = Depends(authorize("staff:manage"))):
    password = body.password or generate_password()
    u = User(tenant_id=ctx.tenant.id, name=body.name.strip(), email=body.email.lower(), role=body.role, password_hash=hash_password(password),
             permissions=None if body.role == Role.ADMIN else body.permissions)
    await persist(ctx.session, u, "Someone with this email already works here")
    return StaffCreated(**_out(u).model_dump(), temporary_password=None if body.password else password)


@router.patch("/{user_id}", response_model=StaffOut, summary="Change a person's name, role, access or switch them off")
async def update(user_id: UUID, body: StaffUpdate, ctx: TenantContext = Depends(authorize("staff:manage"))):
    u = await _user(ctx, user_id)
    me = ctx.principal.user_id
    new_role = body.role or u.role
    will_be_active = u.is_active if body.is_active is None else body.is_active
    if u.id == me and (new_role != Role.ADMIN or not will_be_active):
        raise HTTPException(409, "You cannot lower or switch off your own account. Ask another admin.")
    if u.role == Role.ADMIN and (new_role != Role.ADMIN or not will_be_active) and await _other_admins(ctx, u) == 0:
        raise HTTPException(409, "There must be at least one active admin.")
    if body.name is not None:
        u.name = body.name.strip()
    u.role = new_role
    if new_role == Role.ADMIN or body.reset_to_role:
        u.permissions = None
    elif body.permissions is not None:
        u.permissions = body.permissions
    if body.is_active is not None:
        u.is_active = body.is_active
    await ctx.session.flush()
    return _out(u)


@router.post("/{user_id}/reset-password", response_model=PasswordResult, summary="Give someone a new password (they are signed out everywhere)")
async def reset_password(user_id: UUID, body: ResetPassword, ctx: TenantContext = Depends(authorize("staff:manage"))):
    u = await _user(ctx, user_id)
    if u.id == ctx.principal.user_id:
        raise HTTPException(409, "Use Change password for your own account.")
    password = body.password or generate_password()
    u.password_hash = hash_password(password)
    await ctx.session.flush()
    await get_redis().set(f"pwchanged:{u.id}", str(datetime.now(timezone.utc).timestamp()), ex=30 * 86400)
    return PasswordResult(temporary_password=None if body.password else password)
