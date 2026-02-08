# app/schemas/auth.py
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict
from app.core.organizations import OrganizationRole, OrganizationType
from app.core.roles import Role


class LoginRequest(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


class UserScopeSummary(BaseModel):
    projects_count: int = 0
    disciplines_count: int = 0
    has_custom_scope: bool = False
    status: str = "full"


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    role: Role
    organization_id: Optional[int] = None
    organization_role: Optional[OrganizationRole] = None
    organization: Optional["OrganizationRef"] = None
    is_active: bool
    created_at: Optional[datetime] = None
    scope_summary: Optional[UserScopeSummary] = None

    model_config = ConfigDict(from_attributes=True)


class PaginationResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    count: int
    has_prev: bool
    has_next: bool


class UserListResponse(BaseModel):
    ok: bool = True
    items: List[UserResponse]
    pagination: PaginationResponse


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None
    role: Role = Role.USER
    organization_id: Optional[int] = None
    organization_role: OrganizationRole = OrganizationRole.VIEWER
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[Role] = None
    organization_id: Optional[int] = None
    organization_role: Optional[OrganizationRole] = None
    is_active: Optional[bool] = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class OrganizationRef(BaseModel):
    id: int
    code: str
    name: str
    org_type: OrganizationType
    parent_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


UserResponse.model_rebuild()
