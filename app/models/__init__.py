from app.models.base import Base
from app.models.booking import Booking
from app.models.channel import ChannelAgreement, ChannelAgreementProperty, ChannelCancellation, ChannelLedger, ChannelSettlement, ChannelSettlementItem
from app.models.cms import CMSContent
from app.models.crm import Customer
from app.models.enums import *  # noqa: F401,F403
from app.models.media import MediaAsset
from app.models.platform import ContactMessage, PlatformAdmin, PlatformAudit, SupportSession
from app.models.inventory import PricingRule, Property, Unit
from app.models.partners import Partner, PartnerLedger, PayoutRequest
from app.models.tenancy import Tenant, User
from app.models.tours import Budget, EventBooking, Package, TourEvent, Vendor, VendorRate

__all__ = ["Base", "Booking", "ChannelAgreement", "ChannelAgreementProperty", "ChannelCancellation", "ChannelLedger", "ChannelSettlement", "ChannelSettlementItem", "CMSContent", "Customer", "PricingRule", "Property", "Unit",
           "MediaAsset", "ContactMessage", "PlatformAdmin", "PlatformAudit", "SupportSession", "Partner", "PartnerLedger", "PayoutRequest", "Tenant", "User", "Budget", "EventBooking", "Package", "TourEvent", "Vendor", "VendorRate"]

# Tables that carry tenant_id (RLS applied by the migration); `tenants` is keyed on id.
TENANT_TABLES = [t.name for t in Base.metadata.sorted_tables if "tenant_id" in t.c]
