from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.constants import GRANTABLE_SCOPES
from app.models.enums import Role


def _scopes(v: list[str] | None) -> list[str] | None:
    if v is None:
        return None
    bad = [s for s in v if s not in GRANTABLE_SCOPES]
    if bad:
        raise ValueError(f"These cannot be given to staff: {', '.join(sorted(bad))}")
    return sorted(set(v))


class StaffOut(BaseModel):
    id: UUID
    name: str
    email: str
    role: Role
    is_active: bool
    custom_access: bool = Field(description="True when this person has their own list of permissions instead of the role's standard access")
    permissions: list[str] = Field(description="What this person can do now (scopes). ADMIN shows ['*']")
    created_at: datetime


class StaffCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    role: Role = Role.STAFF
    permissions: list[str] | None = Field(default=None, description="Leave empty for the role's standard access")
    password: str | None = Field(default=None, min_length=10, max_length=200, description="Leave empty to get a generated temporary password")

    _p = field_validator("permissions")(lambda cls, v: _scopes(v))


class StaffUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: Role | None = None
    permissions: list[str] | None = None
    reset_to_role: bool = Field(default=False, description="Drop the custom list and use the role's standard access")
    is_active: bool | None = None

    _p = field_validator("permissions")(lambda cls, v: _scopes(v))


class StaffCreated(StaffOut):
    temporary_password: str | None = None


class ResetPassword(BaseModel):
    password: str | None = Field(default=None, min_length=10, max_length=200)


class PasswordResult(BaseModel):
    temporary_password: str | None


class PermissionLevel(BaseModel):
    key: str
    label: str
    scopes: list[str]


class PermissionGroup(BaseModel):
    key: str
    label: str
    levels: list[PermissionLevel]


class PermissionCatalog(BaseModel):
    groups: list[PermissionGroup]
    defaults: dict[str, list[str]] = Field(description="The standard access of each role")
