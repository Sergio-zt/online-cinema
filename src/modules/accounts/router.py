from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_async_session
from src.modules.accounts.dependencies import (
    get_current_active_user,
    require_roles,
)
from src.modules.accounts.models import User, UserGroupEnum
from src.modules.accounts.schemas import (
    AccessTokenResponse,
    ActivationRequest,
    AdminUpdateUserGroupRequest,
    ChangePasswordRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshTokenRequest,
    ResendActivationRequest,
    TokenResponse,
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserRegisterRequest,
    UserResponse,
)
from src.modules.accounts.service import AccountsService

router = APIRouter(prefix="/accounts", tags=["Accounts & Authentication"])


def get_accounts_service(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AccountsService:
    """Dependency providing AccountsService instance."""
    return AccountsService(session)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user account",
)
async def register(
    data: UserRegisterRequest,
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> User:
    """Register a new user with an email and password, sending an activation link."""
    return await service.register_user(data)


@router.post(
    "/activate",
    response_model=MessageResponse,
    summary="Activate account using token",
)
async def activate_account_post(
    data: ActivationRequest,
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> MessageResponse:
    """Activate user account via POST JSON body with activation token."""
    await service.activate_account(data.token)
    return MessageResponse(message="Account successfully activated.")


@router.get(
    "/activate",
    response_model=MessageResponse,
    summary="Activate account using query parameter token",
)
async def activate_account_get(
    token: Annotated[str, Query(description="Activation token")],
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> MessageResponse:
    """Activate user account via GET link clicked from email."""
    await service.activate_account(token)
    return MessageResponse(message="Account successfully activated.")


@router.post(
    "/resend-activation",
    response_model=MessageResponse,
    summary="Resend account activation token",
)
async def resend_activation(
    data: ResendActivationRequest,
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> MessageResponse:
    """Resend a new activation link if the previous one expired."""
    await service.resend_activation_token(data.email)
    return MessageResponse(
        message="If the account exists and is inactive, a new activation email has been sent."
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive access & refresh tokens",
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> TokenResponse:
    """Authenticate with username (email) and password, returning JWT token pair."""
    return await service.login(form_data.username, form_data.password)


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Get new access token using refresh token",
)
async def refresh_token(
    data: RefreshTokenRequest,
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> AccessTokenResponse:
    """Exchange a valid refresh token for a newly issued access token with shorter TTL."""
    return await service.refresh_access_token(data.refresh_token)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout and invalidate refresh token",
)
async def logout(
    data: RefreshTokenRequest,
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> MessageResponse:
    """Invalidate refresh token so it cannot be used for further sessions."""
    await service.logout(data.refresh_token)
    return MessageResponse(message="Successfully logged out.")


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Change password for authenticated user",
)
async def change_password(
    data: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> MessageResponse:
    """Change user password by confirming the old password and supplying a new one."""
    await service.change_password(current_user, data)
    return MessageResponse(message="Password successfully changed.")


@router.post(
    "/password-reset/request",
    response_model=MessageResponse,
    summary="Request password reset token via email",
)
async def request_password_reset(
    data: PasswordResetRequest,
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> MessageResponse:
    """Send a password reset link to user's registered and active email."""
    await service.request_password_reset(data.email)
    return MessageResponse(
        message="If the email is registered and active, a password reset link has been sent."
    )


@router.post(
    "/password-reset/confirm",
    response_model=MessageResponse,
    summary="Set new password using reset token",
)
async def confirm_password_reset(
    data: PasswordResetConfirmRequest,
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> MessageResponse:
    """Set a new password using the token sent via email without old password."""
    await service.confirm_password_reset(data)
    return MessageResponse(message="Password has been successfully reset.")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """Return profile and metadata of the currently authenticated user."""
    return current_user


@router.put(
    "/me/profile",
    response_model=UserProfileResponse,
    summary="Update current user profile details",
)
async def update_profile(
    data: UserProfileUpdateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> UserProfileResponse:
    """Update profile fields (name, gender, birth date, info)."""
    updated_profile = await service.update_profile(current_user, data)
    return UserProfileResponse.model_validate(updated_profile)


@router.post(
    "/me/avatar",
    response_model=UserProfileResponse,
    summary="Upload user avatar image to MinIO",
)
async def upload_avatar_endpoint(
    file: Annotated[UploadFile, File(description="Avatar image file")],
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> UserProfileResponse:
    """Upload user avatar to MinIO storage and link to user profile."""
    updated_profile = await service.upload_user_avatar(current_user, file)
    return UserProfileResponse.model_validate(updated_profile)


# Administrator-only endpoints
@router.patch(
    "/admin/users/{user_id}/group",
    response_model=UserResponse,
    dependencies=[Depends(require_roles(UserGroupEnum.ADMIN))],
    summary="Change user group (Admin only)",
)
async def admin_change_group(
    user_id: int,
    data: AdminUpdateUserGroupRequest,
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> User:
    """Allow administrators to reassign user group (USER, MODERATOR, ADMIN)."""
    return await service.admin_change_user_group(user_id, data.group_name)


@router.patch(
    "/admin/users/{user_id}/activate",
    response_model=UserResponse,
    dependencies=[Depends(require_roles(UserGroupEnum.ADMIN))],
    summary="Manually activate user account (Admin only)",
)
async def admin_activate_user(
    user_id: int,
    service: Annotated[AccountsService, Depends(get_accounts_service)],
) -> User:
    """Allow administrators to manually activate user accounts."""
    return await service.admin_activate_user(user_id)
