"""PDF storage that works for both docker-compose (shared volume) and Kubernetes (S3/MinIO).

The API stores a PDF under a key and enqueues that key. The worker may run on a
different node, so it must fetch the file from storage rather than assume a shared disk.
"""
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import settings


def _s3_client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL or None,
        aws_access_key_id=settings.S3_ACCESS_KEY or None,
        aws_secret_access_key=settings.S3_SECRET_KEY or None,
        region_name=settings.S3_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> None:
    if settings.STORAGE_BACKEND != "s3":
        Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)
        return
    from botocore.exceptions import ClientError

    client = _s3_client()
    try:
        client.head_bucket(Bucket=settings.S3_BUCKET)
    except ClientError as error:
        if str(error.response.get("Error", {}).get("Code")) not in {"404", "NoSuchBucket", "NotFound"}:
            raise
        try:
            client.create_bucket(Bucket=settings.S3_BUCKET)
        except ClientError as create_error:
            if create_error.response.get("Error", {}).get("Code") != "BucketAlreadyOwnedByYou":
                raise


def save_pdf(document_id: str, contents: bytes) -> str:
    """Store the PDF and return the storage key to hand to the worker."""
    key = f"{document_id}.pdf"
    if settings.STORAGE_BACKEND == "s3":
        _s3_client().put_object(Bucket=settings.S3_BUCKET, Key=key, Body=contents)
    else:
        path = Path(settings.STORAGE_PATH)
        path.mkdir(parents=True, exist_ok=True)
        (path / key).write_bytes(contents)
    return key


@contextmanager
def local_pdf_path(key: str) -> Iterator[str]:
    """Yield a local filesystem path for the stored PDF (downloaded to a temp file for S3)."""
    if settings.STORAGE_BACKEND != "s3":
        yield str(Path(settings.STORAGE_PATH) / key)
        return

    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        _s3_client().download_file(settings.S3_BUCKET, key, tmp_path)
        yield tmp_path
    finally:
        os.unlink(tmp_path)
