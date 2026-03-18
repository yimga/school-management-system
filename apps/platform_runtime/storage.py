"""
Internal storage abstraction. Use this instead of direct MEDIA_ROOT or boto3.
Backend is Django DEFAULT_FILE_STORAGE (local filesystem or S3-compatible).

B2 (Master Blueprint): Tenant-prefixed keys, signed URLs, per-tenant buckets.
- Use tenant_media_path() / tenant_static_path() for all tenant-scoped paths.
- get_storage_url() returns backend URL (S3 backends can use signed URLs via custom storage).
- Per-tenant buckets: set AWS_STORAGE_BUCKET_NAME per tenant or use path prefix (tenants/{id}/).
"""

from __future__ import annotations

from typing import Union

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def tenant_media_path(school_id: int | str | None, relative_path: str) -> str:
    """
    Tenant-prefixed key for media. Use for all tenant-uploaded files so isolation and
    per-tenant bucket policies can be applied. Example: tenants/42/uploads/report.pdf
    """
    prefix = "tenants"
    tid = str(school_id) if school_id is not None else "platform"
    path = relative_path.lstrip("/")
    return f"{prefix}/{tid}/{path}" if path else f"{prefix}/{tid}/"


def tenant_static_path(school_id: int | str | None, relative_path: str) -> str:
    """
    Tenant-prefixed key for static-like assets (e.g. generated exports). Example: tenants/42/static/exports/x.pdf
    """
    prefix = "tenants"
    tid = str(school_id) if school_id is not None else "platform"
    path = relative_path.lstrip("/")
    return f"{prefix}/{tid}/static/{path}" if path else f"{prefix}/{tid}/static/"


def get_signed_url(path: str, expires_in: int = 3600) -> str:
    """
    Return a URL for the path, optionally time-limited (signed). When using S3-compatible
    storage with signing enabled, backend.url() may already return signed URLs; otherwise
    returns standard URL. Override in custom storage backend for signed URLs.
    """
    if hasattr(default_storage, "url_with_expiry"):
        return default_storage.url_with_expiry(path, expires_in=expires_in)
    return default_storage.url(path)


def save_to_storage(
    path: str, content: Union[bytes, str], content_type: str | None = None
) -> str:
    """
    Save content to the configured storage backend (local or S3-compatible).
    path: relative path under storage root (e.g. tenants/{school_id}/uploads/file.pdf).
    Returns the path as stored.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return default_storage.save(path, ContentFile(content))


def get_storage_url(path: str) -> str:
    """Return public URL for the path if backend supports it (e.g. S3 signed or public)."""
    return default_storage.url(path)


def delete_from_storage(path: str) -> bool:
    """Delete file at path. Returns True if deleted or missing."""
    if not default_storage.exists(path):
        return True
    default_storage.delete(path)
    return True


def storage_exists(path: str) -> bool:
    """Return True if path exists in storage."""
    return default_storage.exists(path)


def open_storage(path: str, mode: str = "rb"):
    """Open file from storage. Prefer read-only modes."""
    return default_storage.open(path, mode)
