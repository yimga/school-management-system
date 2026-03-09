"""
Internal storage abstraction. Use this instead of direct MEDIA_ROOT or boto3.
Backend is Django DEFAULT_FILE_STORAGE (local filesystem or S3-compatible).
"""
from __future__ import annotations

from typing import Union

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def save_to_storage(path: str, content: Union[bytes, str], content_type: str | None = None) -> str:
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
