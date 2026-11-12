from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    tenant_domain: Optional[str] = Field(default=None, max_length=255, description="Optional. Only needed when the same e-mail is used in more than one business.")
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    principal: Literal["user", "partner"] = "user"
    model_config = ConfigDict(json_schema_extra={"example": {
        "tenant_domain": "agency.com", "email": "admin@agency.com", "password": "S3cure-passw0rd!", "principal": "user"}})


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class ApiKeyRequest(BaseModel):
    scopes: list[str] = Field(min_length=1)
    model_config = ConfigDict(json_schema_extra={"example": {"scopes": ["properties:read", "availability:read", "bookings:create", "cms:read"]}})


class ApiKeyOut(BaseModel):
    api_key: str
    api_secret: str = Field(description="Shown ONCE. Only a peppered hash is stored.")
    scopes: list[str]


class ApiCredentialsOut(BaseModel):
    api_key: Optional[str] = None
    scopes: list[str]
    has_secret: bool = Field(description="A secret exists. It cannot be shown again; change it to get a new one.")


class MeOut(BaseModel):
    kind: str
    tenant_id: UUID
    user_id: UUID | None = None
    partner_id: UUID | None = None
    role: str | None = None
    scopes: list[str]
    support: dict | None = Field(default=None, description="Set while a super admin is signed in to help this business.")
    tenant_name: str | None = None
    tenant_domain: str | None = None
    tenant_logo: str | None = Field(default=None, description="The business logo address, if one is set.")
    person_name: str | None = Field(default=None, description="Name of the signed-in person.")
    channel: dict | None = Field(default=None, description="Reseller channel: whether this business sells for others, and how many things wait for its answer.")


class ChangePassword(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class SupportExchange(BaseModel):
    code: str = Field(min_length=10, max_length=100)


class SupportToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
