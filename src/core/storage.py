import uuid
from typing import BinaryIO

import boto3
from botocore.client import Config

from src.core.config import settings


def get_s3_client() -> boto3.client:
    """Initialize and return a configured S3 client for MinIO."""
    return boto3.client(
        "s3",
        endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket_exists(bucket_name: str = settings.MINIO_BUCKET_NAME) -> None:
    """Ensure that the target S3/MinIO bucket exists, creating it if necessary."""
    s3 = get_s3_client()
    try:
        s3.head_bucket(Bucket=bucket_name)
    except Exception:
        try:
            s3.create_bucket(Bucket=bucket_name)
        except Exception:
            pass


def upload_avatar(
    file_obj: BinaryIO,
    original_filename: str,
    content_type: str,
) -> str:
    """Upload user avatar to MinIO and return the generated object key."""
    ensure_bucket_exists()
    ext = original_filename.rsplit(".", 1)[-1] if "." in original_filename else "png"
    object_key = f"avatars/{uuid.uuid4().hex}.{ext}"

    s3 = get_s3_client()
    s3.upload_fileobj(
        Fileobj=file_obj,
        Bucket=settings.MINIO_BUCKET_NAME,
        Key=object_key,
        ExtraArgs={"ContentType": content_type},
    )
    return object_key
