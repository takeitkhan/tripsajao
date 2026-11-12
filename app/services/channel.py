"""Reseller channel: agreements between businesses and the one controlled doorway into another business's rooms.

Everything a reseller does inside an owner's business goes through `owner_scope`, which
  1. needs an agreement the reseller can see (row level security hides everyone else's),
  2. needs that agreement ACTIVE, and the owner's business active,
  3. only ever touches properties the owner granted, and only bookings this reseller made.
Money and guest details of the owner's other bookings are never reachable from here."""
from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal, bind_tenant
from app.core.deps import Principal, TenantContext, tenant_by_domain, tenant_by_id
from app.core.redis import get_redis
from app.models import ChannelAgreement, ChannelAgreementProperty, Property
from app.schemas.channel import AgreementOut, AgreementProperty
from app.schemas.platform import clean_domain
from app.services.booking import ChannelSale


async def rate_limit(key: str, maximum: int, seconds: int) -> None:
    r = get_redis()
    n = await r.incr(key)
    if n == 1:
        await r.expire(key, seconds)
    if n > maximum:
        raise HTTPException(429, "Too many attempts. Please try again later.")


async def find_business(session: AsyncSession, domain: str):
    try:
        d = clean_domain(domain)
    except ValueError:
        raise HTTPException(422, "Check the business domain. Use only letters, numbers, dots and hyphens.")
    t = await tenant_by_domain(session, d)
    if t is None:
        raise HTTPException(404, "We could not find an active business with that domain.")
    return t


def side(ctx: TenantContext, ag: ChannelAgreement) -> str:
    return "OWNER" if ag.supplier_tenant_id == ctx.tenant.id else "RESELLER"


async def get_agreement(ctx: TenantContext, agreement_id: UUID, *, as_side: str | None = None) -> ChannelAgreement:
    ag = await ctx.session.get(ChannelAgreement, agreement_id)       # RLS: only agreements this business is a side of
    if ag is None or ctx.tenant.id not in (ag.supplier_tenant_id, ag.reseller_tenant_id):
        raise HTTPException(404, "Agreement not found")
    if as_side and side(ctx, ag) != as_side:
        raise HTTPException(403, "Only the owner of the rooms can do that." if as_side == "OWNER" else "Only the reseller can do that.")
    return ag


async def grants_of(session: AsyncSession, agreement_id: UUID) -> list[ChannelAgreementProperty]:
    return list((await session.execute(select(ChannelAgreementProperty).where(ChannelAgreementProperty.agreement_id == agreement_id))).scalars())


def terms_for(ag: ChannelAgreement, grant: ChannelAgreementProperty) -> tuple[str, Decimal]:
    if grant.commission_type is not None:
        return grant.commission_type, grant.commission_value
    return ag.commission_type, ag.commission_value


def sale_for(ag: ChannelAgreement, grant: ChannelAgreementProperty) -> ChannelSale:
    kind, value = terms_for(ag, grant)
    return ChannelSale(tenant_id=ag.reseller_tenant_id, agreement_id=ag.id, name=ag.reseller_name, commission_type=kind, commission_value=value)


@asynccontextmanager
async def owner_scope(owner_id: UUID, *, required: bool = True):
    """A transaction inside the owner's business. Yields a TenantContext, or None when `required` is False and the owner is not active."""
    session = SessionLocal()
    try:
        tenant = await tenant_by_id(session, str(owner_id))            # only active businesses
        if tenant is None:
            if required:
                raise HTTPException(409, "This business is not taking bookings right now.")
            yield None
            return
        await bind_tenant(session, tenant.id)
        yield TenantContext(session=session, tenant=tenant, principal=Principal("api_client", tenant.id, frozenset()))
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()


async def sellable(ctx: TenantContext, agreement_id: UUID) -> tuple[ChannelAgreement, dict[UUID, ChannelAgreementProperty]]:
    """The reseller's ACTIVE agreement and the properties it covers."""
    ag = await get_agreement(ctx, agreement_id, as_side="RESELLER")
    if ag.status == "PAUSED":
        raise HTTPException(409, f"{ag.supplier_name} has paused selling for now.")
    if ag.status != "ACTIVE":
        raise HTTPException(409, "This agreement is not active.")
    return ag, {g.property_id: g for g in await grants_of(ctx.session, ag.id)}


async def agreement_out(ctx: TenantContext, ag: ChannelAgreement, grants: list[ChannelAgreementProperty] | None = None) -> AgreementOut:
    await ctx.session.refresh(ag)          # server-side timestamps change on update
    me = side(ctx, ag)
    grants = await grants_of(ctx.session, ag.id) if grants is None else grants
    names: dict[UUID, str] = {}
    ids = [g.property_id for g in grants]
    if ids:
        if me == "OWNER":
            names = {i: n for i, n in (await ctx.session.execute(select(Property.id, Property.name).where(Property.id.in_(ids)))).all()}
        else:
            async with owner_scope(ag.supplier_tenant_id, required=False) as oc:
                if oc is not None:
                    names = {i: n for i, n in (await oc.session.execute(select(Property.id, Property.name).where(
                        Property.tenant_id == oc.tenant.id, Property.id.in_(ids)))).all()}
    waiting = {"REQUESTED": "OWNER", "INVITED": "RESELLER"}.get(ag.status)
    return AgreementOut(
        id=ag.id, role=me, counterpart=ag.reseller_name if me == "OWNER" else ag.supplier_name, status=ag.status, initiated_by=ag.initiated_by,
        awaiting=None if waiting is None else ("YOU" if waiting == me else "THEM"),
        commission_type=ag.commission_type, commission_value=ag.commission_value, settlement_mode=ag.settlement_mode, settlement_day=ag.settlement_day,
        note=ag.note, created_at=ag.created_at, updated_at=ag.updated_at,
        properties=[AgreementProperty(property_id=g.property_id, name=names.get(g.property_id, "Removed property"),
                                      commission_type=terms_for(ag, g)[0] or "", commission_value=terms_for(ag, g)[1] or Decimal(0),
                                      is_default=g.commission_type is None) for g in grants])
