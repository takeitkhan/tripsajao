"""Scopes and role -> scope mapping (single source of truth for authorization)."""

ALL_SCOPES = [
    "properties:read", "properties:write",
    "pricing:read", "pricing:write",
    "availability:read",
    "dashboard:read",
    "bookings:create", "bookings:read", "bookings:manage",
    "partners:read", "partners:write",
    "payouts:read", "payouts:approve",
    "cms:read", "cms:write",
    "media:read", "media:write",
    "reports:read",
    "customers:read", "customers:manage", "customers:export",
    "staff:manage",
    "business:read", "business:manage",
    "events:read", "events:write", "events:book",
    "event_bookings:read", "event_bookings:manage",
    "vendors:read", "vendors:write",
    "budgets:read", "budgets:write",
    "channel:read", "channel:manage", "channel:book",
    "docs:read",
    "api_keys:manage",
]

# Scopes that may never be granted to a public API key.
PRIVILEGED_SCOPES = {"api_keys:manage", "business:manage", "payouts:approve", "partners:write", "customers:read", "customers:manage", "customers:export", "staff:manage",
                     "vendors:read", "vendors:write", "budgets:read", "budgets:write", "events:write",
                     "event_bookings:read", "event_bookings:manage"}
# Never given to an API key: a key that could mint keys or add staff could take the account over.
KEY_FORBIDDEN_SCOPES = {"api_keys:manage", "staff:manage"}
# Only an ADMIN holds these. They cannot be handed to a staff member, and ADMIN is never restricted.
ADMIN_ONLY_SCOPES = {"api_keys:manage", "staff:manage", "business:manage"}

DEFAULT_API_CLIENT_SCOPES = [
    "properties:read", "pricing:read", "availability:read", "bookings:create", "cms:read", "events:read", "events:book",
]

ROLE_SCOPES: dict[str, frozenset[str]] = {
    "ADMIN": frozenset({"*"}),
    "MANAGER": frozenset(s for s in ALL_SCOPES if s not in {"payouts:approve", "api_keys:manage", "staff:manage", "business:manage"}),
    "STAFF": frozenset({
        "properties:read", "pricing:read", "availability:read", "dashboard:read",
        "bookings:create", "bookings:read", "bookings:manage", "cms:read", "media:read", "docs:read",
        "channel:read", "channel:book", "customers:read", "events:read", "event_bookings:read",
    }),
}
# A super admin helping a tenant can look and edit, but not rotate API credentials or approve money going out.
SUPPORT_BLOCKED_SCOPES = {"api_keys:manage", "payouts:approve", "staff:manage", "business:manage"}
PARTNER_SCOPES = frozenset({"partner:self"})


# What the access screen offers, group by group. Each level lists the full set of scopes it gives (every level includes the ones below it).
PERMISSION_GROUPS: list[dict] = [
    {"key": "reports", "label": "Overview and reports", "levels": [("view", "View", ["reports:read"])]},
    {"key": "board", "label": "Live board", "levels": [("view", "View", ["dashboard:read", "availability:read"])]},
    {"key": "properties", "label": "Properties and rooms", "levels": [("view", "View", ["properties:read"]), ("edit", "Edit", ["properties:read", "properties:write"])]},
    {"key": "pricing", "label": "Pricing", "levels": [("view", "View", ["pricing:read"]), ("edit", "Edit", ["pricing:read", "pricing:write"])]},
    {"key": "bookings", "label": "Bookings", "levels": [("view", "View", ["bookings:read"]), ("take", "Take bookings", ["bookings:read", "bookings:create"]),
                                                      ("manage", "Take, confirm and cancel", ["bookings:read", "bookings:create", "bookings:manage"])]},
    {"key": "customers", "label": "Customers", "levels": [("view", "View", ["customers:read"]), ("manage", "View and edit", ["customers:read", "customers:manage"]),
                                                         ("export", "View, edit and download", ["customers:read", "customers:manage", "customers:export"])]},
    {"key": "events", "label": "Packages and events", "levels": [("view", "View", ["events:read"]), ("edit", "Edit and publish", ["events:read", "events:write"])]},
    {"key": "business", "label": "Business profile", "levels": [("view", "View", ["business:read"])]},
    {"key": "event_bookings", "label": "Event bookings", "levels": [("view", "View", ["event_bookings:read"]), ("manage", "View, confirm payments and cancel", ["event_bookings:read", "event_bookings:manage"])]},
    {"key": "vendors", "label": "Vendors and rates", "levels": [("view", "View", ["vendors:read"]), ("edit", "Edit", ["vendors:read", "vendors:write"])]},
    {"key": "budgets", "label": "Budgets and quotations", "levels": [("view", "View", ["budgets:read"]), ("edit", "Edit", ["budgets:read", "budgets:write"])]},
    {"key": "partners", "label": "Partners", "levels": [("view", "View", ["partners:read"]), ("edit", "Edit", ["partners:read", "partners:write"])]},
    {"key": "payouts", "label": "Payouts", "levels": [("view", "View", ["payouts:read"]), ("approve", "View and approve", ["payouts:read", "payouts:approve"])]},
    {"key": "channel", "label": "Resellers", "levels": [("view", "View", ["channel:read"]), ("sell", "View and sell", ["channel:read", "channel:book"]),
                                                       ("manage", "Manage agreements", ["channel:read", "channel:book", "channel:manage"])]},
    {"key": "cms", "label": "Website content", "levels": [("view", "View", ["cms:read"]), ("edit", "Edit", ["cms:read", "cms:write"])]},
    {"key": "media", "label": "Media library", "levels": [("view", "View", ["media:read"]), ("edit", "Edit", ["media:read", "media:write"])]},
    {"key": "docs", "label": "API documentation", "levels": [("view", "View", ["docs:read"])]},
]
GRANTABLE_SCOPES = frozenset(s for g in PERMISSION_GROUPS for _, _, sc in g["levels"] for s in sc)


def effective_scopes(role: str, permissions: list | None) -> frozenset[str]:
    """What a signed-in user may do. ADMIN: everything. Others: their own list when set, else the role's standard access."""
    if role == "ADMIN":
        return ROLE_SCOPES["ADMIN"]
    if permissions is None:
        return ROLE_SCOPES[role]
    return frozenset(s for s in permissions if s in GRANTABLE_SCOPES)
