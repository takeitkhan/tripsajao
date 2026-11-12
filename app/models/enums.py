from enum import Enum


class PropertyType(str, Enum):
    HOTEL = "HOTEL"
    RESORT = "RESORT"
    HOUSEBOAT = "HOUSEBOAT"


class UnitType(str, Enum):
    ROOM = "ROOM"
    COTTAGE = "COTTAGE"
    DUPLEX = "DUPLEX"
    CABIN = "CABIN"
    WHOLE_BOAT = "WHOLE_BOAT"   # virtual unit = full-boat charter; conflicts with every cabin


class UnitStatus(str, Enum):
    """Administrative state. BOOKED / ON_HOLD are *derived* per date range from bookings."""
    AVAILABLE = "AVAILABLE"
    MAINTENANCE = "MAINTENANCE"


class Role(str, Enum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    STAFF = "STAFF"


class PartnerType(str, Enum):
    B2B = "B2B"
    MOU = "MOU"


class CommissionType(str, Enum):
    PERCENT = "PERCENT"
    FLAT = "FLAT"


class BookingStatus(str, Enum):
    HOLD = "HOLD"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class LedgerType(str, Enum):
    COMMISSION = "COMMISSION"
    COMMISSION_REVERSAL = "COMMISSION_REVERSAL"
    PAYOUT = "PAYOUT"
    ADJUSTMENT = "ADJUSTMENT"


class PayoutStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    PAID = "PAID"
    REJECTED = "REJECTED"


class CMSType(str, Enum):
    BLOG = "BLOG"
    EVENT = "EVENT"
    GALLERY = "GALLERY"
    PAGE = "PAGE"
    ANNOUNCEMENT = "ANNOUNCEMENT"


class CMSStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class MediaKind(str, Enum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"


class MediaSource(str, Enum):
    UPLOAD = "UPLOAD"        # file stored by us
    EXTERNAL = "EXTERNAL"    # a link, e.g. YouTube / Vimeo
