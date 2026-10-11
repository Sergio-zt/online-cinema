from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables
    with fail-fast production validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_NAME: str = "Online Cinema"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Security
    SECRET_KEY: str = "insecure-dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Documentation credentials
    DOCS_USERNAME: str = "admin"
    DOCS_PASSWORD: str = "cinema_admin"

    # Database (PostgreSQL)
    POSTGRES_SERVER: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "cinema_user"
    POSTGRES_PASSWORD: str = "cinema_password"
    POSTGRES_DB: str = "cinema_db"

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"

    # Object Storage (MinIO)
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_NAME: str = "cinema-avatars"
    MINIO_SECURE: bool = False

    # Email
    SMTP_HOST: str = "mailpit"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = False
    EMAILS_FROM_EMAIL: str = "noreply@onlinecinema.local"
    EMAILS_FROM_NAME: str = "Online Cinema"

    # Stripe
    STRIPE_SECRET_KEY: str = "sk_test_dummy_key"
    STRIPE_WEBHOOK_SECRET: str = "whsec_dummy_key"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def async_database_url(self) -> str:
        """Construct the async PostgreSQL DSN for SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """Fail fast if insecure development defaults are detected in
        non-development environments."""
        if self.ENVIRONMENT.lower() != "development":
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production environments.")

            insecure_key = "insecure-dev-secret-key-change-in-production"
            if not self.SECRET_KEY or self.SECRET_KEY == insecure_key:
                raise ValueError(
                    "SECRET_KEY must be explicitly configured"
                    "with a secure value in production."
                )

            if self.POSTGRES_PASSWORD == "cinema_password":
                raise ValueError(
                    "POSTGRES_PASSWORD must be changed from default in production."
                )

            if self.DOCS_PASSWORD == "cinema_admin":
                raise ValueError(
                    "DOCS_PASSWORD must be changed from default in production."
                )

            if self.MINIO_SECRET_KEY == "minioadmin":
                raise ValueError(
                    "MINIO_SECRET_KEY must be changed from default in production."
                )

            if self.STRIPE_SECRET_KEY == "sk_test_dummy_key":
                raise ValueError("A valid STRIPE_SECRET_KEY is required in production.")

        return self


settings = Settings()
