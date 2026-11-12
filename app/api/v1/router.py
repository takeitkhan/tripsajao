from fastapi import APIRouter

from app.api.v1 import platform, platform_auth, registration, auth, bookings, cms, dashboard, docs, media, partners, payouts, pricing, properties, reports, channel, channel_money, channel_cancel, customers, staff, packages, tour_events, vendors, budgets, event_bookings, business, showcase, contact

API_PREFIX = "/api/v1"
MODULE_ROUTERS = [m.router for m in (auth, properties, dashboard, pricing, bookings, partners, payouts, cms, media, reports, channel, channel_money, channel_cancel, customers, staff, packages, tour_events, event_bookings, business, vendors, budgets, docs)]

api_router = APIRouter(prefix=API_PREFIX)
for _r in MODULE_ROUTERS:
    api_router.include_router(_r)
# not part of the tenant API documentation (MODULE_ROUTERS): the super admin portal and public registration
for _r in (platform_auth.router, platform.router, registration.router, showcase.router, contact.router):
    api_router.include_router(_r)
