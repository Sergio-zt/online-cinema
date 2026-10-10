from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from src.core.security import validate_password_complexity
from src.modules.accounts.models import GenderEnum, UserGroupEnum


class UserRegisterRequest(BaseModel):
    """Schema for user registration request."""

    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def check_password_complexity(cls, value: str) -> str:
        """Validate password strength."""
        validate_password_complexity(value)
        return value


class UserProfileResponse(BaseModel):
    """Schema for displaying user profile information."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar: Optional[str] = None
    gender: Optional[GenderEnum] = None
    date_of_birth: Optional[date] = None
    info: Optional[str] = None


class UserProfileUpdateRequest(BaseModel):
    """Schema for updating user profile fields."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    gender: Optional[GenderEnum] = None
    date_of_birth: Optional[date] = None
    info: Optional[str] = None


class UserResponse(BaseModel):
    """Schema representing user account details."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    is_active: bool
    group_id: int
    created_at: datetime
    updated_at: datetime
    profile: Optional[UserProfileResponse] = None


class ActivationRequest(BaseModel):
    """Schema for account activation via token."""

    token: str


class ResendActivationRequest(BaseModel):
    """Schema for requesting a fresh activation link."""

    email: EmailStr


class LoginRequest(BaseModel):
    """Schema for credentials login."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Schema returning access and refresh JWT pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Schema for exchanging refresh token for a new access token."""

    refresh_token: str


class AccessTokenResponse(BaseModel):
    """Schema returning newly minted access token."""

    access_token: str
    token_type: str = "bearer"


class ChangePasswordRequest(BaseModel):
    """Schema for updating password while knowing the current one."""

    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password_complexity(cls, value: str) -> str:
        """Validate new password strength."""
        validate_password_complexity(value)
        return value


class PasswordResetRequest(BaseModel):
    """Schema for requesting a password reset email."""

    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    """Schema for confirming password reset with received token."""

    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password_complexity(cls, value: str) -> str:
        """Validate new password strength."""
        validate_password_complexity(value)
        return value


class AdminUpdateUserGroupRequest(BaseModel):
    """Schema for administrator updating user role."""

    group_name: UserGroupEnum


class MessageResponse(BaseModel):
    """Generic status message response."""

    message: str
