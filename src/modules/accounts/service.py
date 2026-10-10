from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    generate_secure_token,
    get_password_hash,
    verify_password,
)
from src.core.storage import upload_avatar
from src.modules.accounts.models import (
    ActivationToken,
    PasswordResetToken,
    RefreshToken,
    User,
    UserGroup,
    UserGroupEnum,
    UserProfile,
)
from src.modules.accounts.schemas import (
    AccessTokenResponse,
    ChangePasswordRequest,
    PasswordResetConfirmRequest,
    TokenResponse,
    UserProfileUpdateRequest,
    UserRegisterRequest,
)
from src.tasks.email import send_email_task


class AccountsService:
    """Service handling business logic for users, authentication, and credentials."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def register_user(self, data: UserRegisterRequest) -> User:
        """Register a new user, create an empty profile, and dispatch an activation email."""
        # 1. Ensure email uniqueness
        existing_user = await self.session.scalar(
            select(User).where(User.email == data.email)
        )
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email address already exists.",
            )

        # 2. Retrieve default USER role
        user_group = await self.session.scalar(
            select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
        )
        if not user_group:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Default user group not found. System initialization error.",
            )

        # 3. Create user account
        hashed_pwd = get_password_hash(data.password)
        new_user = User(
            email=data.email,
            hashed_password=hashed_pwd,
            is_active=False,
            group_id=user_group.id,
        )
        self.session.add(new_user)
        await self.session.flush()

        # 4. Create empty user profile
        profile = UserProfile(user_id=new_user.id)
        self.session.add(profile)

        # 5. Create 24-hour activation token
        token_str = generate_secure_token()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        activation_token = ActivationToken(
            user_id=new_user.id,
            token=token_str,
            expires_at=expires_at,
        )
        self.session.add(activation_token)
        await self.session.commit()
        await self.session.refresh(new_user, attribute_names=["profile", "group"])

        # 6. Dispatch activation email in background
        activation_link = (
            f"http://localhost:8000/api/v1/accounts/activate?token={token_str}"
        )
        send_email_task.delay(
            to_email=new_user.email,
            subject="Activate your Online Cinema account",
            body_text=(
                f"Welcome! Please activate your account within 24 hours using this link: {activation_link}"
            ),
            body_html=(
                f"<p>Welcome to Online Cinema!</p>"
                f"<p>Please click the link below to activate your account (valid for 24 hours):</p>"
                f'<p><a href="{activation_link}">Activate Account</a></p>'
            ),
        )

        return new_user

    async def activate_account(self, token_str: str) -> None:
        """Activate user account by validating the activation token."""
        query = (
            select(ActivationToken)
            .where(ActivationToken.token == token_str)
            .options(selectinload(ActivationToken.user))
        )
        token_record = await self.session.scalar(query)
        now_utc = datetime.now(timezone.utc)

        if not token_record or token_record.expires_at < now_utc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Activation token is invalid or has expired.",
            )

        user = token_record.user
        user.is_active = True

        # Remove used activation token
        await self.session.delete(token_record)
        await self.session.commit()

    async def resend_activation_token(self, email: str) -> None:
        """Resend a new 24-hour activation token if the account is not yet active."""
        user = await self.session.scalar(select(User).where(User.email == email))
        if not user:
            # Prevent email enumeration by returning successfully
            return

        if user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account is already active.",
            )

        # Delete existing tokens for this user
        await self.session.execute(
            delete(ActivationToken).where(ActivationToken.user_id == user.id)
        )

        # Generate new 24h token
        token_str = generate_secure_token()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        activation_token = ActivationToken(
            user_id=user.id,
            token=token_str,
            expires_at=expires_at,
        )
        self.session.add(activation_token)
        await self.session.commit()

        # Send email
        activation_link = (
            f"http://localhost:8000/api/v1/accounts/activate?token={token_str}"
        )
        send_email_task.delay(
            to_email=user.email,
            subject="New account activation link",
            body_text=(
                f"Here is your new activation link (valid for 24 hours): {activation_link}"
            ),
            body_html=(
                f"<p>Here is your new activation link (valid for 24 hours):</p>"
                f'<p><a href="{activation_link}">Activate Account</a></p>'
            ),
        )

    async def login(self, email: str, password: str) -> TokenResponse:
        """Authenticate user credentials and issue access and refresh tokens."""
        user = await self.session.scalar(select(User).where(User.email == email))
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive. Please activate your account first.",
            )

        # Create token pair
        access_token = create_access_token(subject=user.id)
        refresh_token, expires_at = create_refresh_token(subject=user.id)

        # Store refresh token in database
        refresh_record = RefreshToken(
            user_id=user.id,
            token=refresh_token,
            expires_at=expires_at,
        )
        self.session.add(refresh_record)
        await self.session.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def refresh_access_token(self, refresh_token: str) -> AccessTokenResponse:
        """Validate stored refresh token and generate a new access token."""
        token_record = await self.session.scalar(
            select(RefreshToken).where(RefreshToken.token == refresh_token)
        )
        now_utc = datetime.now(timezone.utc)
        if not token_record or token_record.expires_at < now_utc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token is invalid or expired.",
            )

        try:
            payload = decode_jwt_token(refresh_token)
            if payload.get("type") != "refresh":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type.",
                )
            user_id = int(payload.get("sub", 0))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token signature or expired payload.",
            )

        new_access_token = create_access_token(subject=user_id)
        return AccessTokenResponse(access_token=new_access_token)

    async def logout(self, refresh_token: str) -> None:
        """Revoke refresh token by deleting it from the database."""
        await self.session.execute(
            delete(RefreshToken).where(RefreshToken.token == refresh_token)
        )
        await self.session.commit()

    async def change_password(self, user: User, data: ChangePasswordRequest) -> None:
        """Change password for an authenticated user verifying the old password."""
        if not verify_password(data.old_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Old password does not match.",
            )

        user.hashed_password = get_password_hash(data.new_password)
        # Invalidate all active refresh tokens on password change for security
        await self.session.execute(
            delete(RefreshToken).where(RefreshToken.user_id == user.id)
        )
        await self.session.commit()

    async def request_password_reset(self, email: str) -> None:
        """Generate a password reset token and dispatch email if user exists and is active."""
        user = await self.session.scalar(select(User).where(User.email == email))
        if not user or not user.is_active:
            # Protect against email enumeration
            return

        # Purge any old reset tokens
        await self.session.execute(
            delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )

        token_str = generate_secure_token()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        reset_token = PasswordResetToken(
            user_id=user.id,
            token=token_str,
            expires_at=expires_at,
        )
        self.session.add(reset_token)
        await self.session.commit()

        reset_link = f"http://localhost:8000/api/v1/accounts/password-reset/confirm?token={token_str}"
        send_email_task.delay(
            to_email=user.email,
            subject="Reset your password",
            body_text=f"Use this link to reset your password (valid for 1 hour): {reset_link}",
            body_html=(
                f"<p>You requested a password reset for your Online Cinema account.</p>"
                f'<p><a href="{reset_link}">Reset Password</a></p>'
            ),
        )

    async def confirm_password_reset(self, data: PasswordResetConfirmRequest) -> None:
        """Reset user password using the received reset token."""
        query = (
            select(PasswordResetToken)
            .where(PasswordResetToken.token == data.token)
            .options(selectinload(PasswordResetToken.user))
        )
        token_record = await self.session.scalar(query)
        now_utc = datetime.now(timezone.utc)

        if not token_record or token_record.expires_at < now_utc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password reset token is invalid or expired.",
            )

        user = token_record.user
        user.hashed_password = get_password_hash(data.new_password)

        # Invalidate refresh tokens and delete used reset token
        await self.session.delete(token_record)
        await self.session.execute(
            delete(RefreshToken).where(RefreshToken.user_id == user.id)
        )
        await self.session.commit()

    async def update_profile(
        self, user: User, data: UserProfileUpdateRequest
    ) -> UserProfile:
        """Update profile details for the given user."""
        query = select(UserProfile).where(UserProfile.user_id == user.id)
        profile = await self.session.scalar(query)
        if not profile:
            profile = UserProfile(user_id=user.id)
            self.session.add(profile)

        update_dict = data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(profile, key, value)

        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def upload_user_avatar(self, user: User, file: UploadFile) -> UserProfile:
        """Upload avatar image to S3/MinIO and link key to user profile."""
        allowed_mime_types = ["image/jpeg", "image/png", "image/webp"]
        if file.content_type not in allowed_mime_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only JPEG, PNG, and WebP images are allowed for avatars.",
            )

        object_key = upload_avatar(
            file_obj=file.file,
            original_filename=file.filename or "avatar.png",
            content_type=file.content_type,
        )

        query = select(UserProfile).where(UserProfile.user_id == user.id)
        profile = await self.session.scalar(query)
        if not profile:
            profile = UserProfile(user_id=user.id, avatar=object_key)
            self.session.add(profile)
        else:
            profile.avatar = object_key

        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def admin_change_user_group(
        self, user_id: int, new_role: UserGroupEnum
    ) -> User:
        """Admin functionality to change a user's assigned group."""
        user = await self.session.scalar(
            select(User).where(User.id == user_id).options(selectinload(User.group))
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
            )

        group = await self.session.scalar(
            select(UserGroup).where(UserGroup.name == new_role)
        )
        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Group not found."
            )

        user.group_id = group.id
        await self.session.commit()
        await self.session.refresh(user, attribute_names=["group", "profile"])
        return user

    async def admin_activate_user(self, user_id: int) -> User:
        """Admin functionality to manually activate an account."""
        user = await self.session.scalar(
            select(User).where(User.id == user_id).options(selectinload(User.group))
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
            )

        user.is_active = True
        await self.session.commit()
        await self.session.refresh(user, attribute_names=["group", "profile"])
        return user
