"""
File upload validators for security and data integrity.

Validates file types, sizes, and content to prevent malicious uploads.
"""

import os
from decimal import Decimal
from typing import Callable

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils.deconstruct import deconstructible


@deconstructible
class FileTypeValidator:
    """
    Validates uploaded file MIME types and extensions.
    
    Usage:
        image_validator = FileTypeValidator(
            allowed_types=['image/jpeg', 'image/png', 'image/gif'],
            allowed_extensions=['.jpg', '.jpeg', '.png', '.gif'],
            message="Only image files are allowed."
        )
    """
    
    def __init__(
        self,
        allowed_types: list[str] | None = None,
        allowed_extensions: list[str] | None = None,
        message: str | None = None,
    ):
        self.allowed_types = allowed_types or []
        self.allowed_extensions = [ext.lower() for ext in (allowed_extensions or [])]
        self.message = message or "File type not allowed."
    
    def __call__(self, file: UploadedFile):
        """Validate file type and extension."""
        if not file:
            return
        
        # Check extension
        if self.allowed_extensions:
            ext = os.path.splitext(file.name)[1].lower()
            if ext not in self.allowed_extensions:
                raise ValidationError(
                    f"File extension '{ext}' not allowed. Allowed: {', '.join(self.allowed_extensions)}"
                )
        
        # Check MIME type
        if self.allowed_types:
            content_type = getattr(file, 'content_type', None)
            if content_type and content_type not in self.allowed_types:
                raise ValidationError(
                    f"File type '{content_type}' not allowed. Allowed: {', '.join(self.allowed_types)}"
                )
    
    def __eq__(self, other):
        return (
            isinstance(other, FileTypeValidator)
            and self.allowed_types == other.allowed_types
            and self.allowed_extensions == other.allowed_extensions
        )


@deconstructible
class FileSizeValidator:
    """
    Validates uploaded file size.
    
    Usage:
        # Max 5MB
        size_validator = FileSizeValidator(max_size_mb=5)
    """
    
    def __init__(self, max_size_mb: int = 10, message: str | None = None):
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.max_size_mb = max_size_mb
        self.message = message or f"File size must not exceed {max_size_mb}MB."
    
    def __call__(self, file: UploadedFile):
        """Validate file size."""
        if not file:
            return
        
        if file.size > self.max_size_bytes:
            size_mb = round(file.size / (1024 * 1024), 2)
            raise ValidationError(
                f"File size ({size_mb}MB) exceeds maximum allowed ({self.max_size_mb}MB)."
            )
    
    def __eq__(self, other):
        return (
            isinstance(other, FileSizeValidator)
            and self.max_size_bytes == other.max_size_bytes
        )


# Predefined validators for common use cases

validate_pdf_file = FileTypeValidator(
    allowed_types=['application/pdf'],
    allowed_extensions=['.pdf'],
    message="Only PDF files are allowed."
)

validate_image_file = FileTypeValidator(
    allowed_types=['image/jpeg', 'image/png', 'image/jpg', 'image/gif', 'image/webp'],
    allowed_extensions=['.jpg', '.jpeg', '.png', '.gif', '.webp'],
    message="Only image files (JPEG, PNG, GIF, WebP) are allowed."
)

validate_document_file = FileTypeValidator(
    allowed_types=[
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.oasis.opendocument.text',
        'application/vnd.oasis.opendocument.spreadsheet',
    ],
    allowed_extensions=['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.odt', '.ods'],
    message="Only document files (PDF, Word, Excel, or LibreOffice ODT/ODS) are allowed."
)

validate_receipt_file = FileTypeValidator(
    allowed_types=['application/pdf', 'image/jpeg', 'image/png', 'image/jpg'],
    allowed_extensions=['.pdf', '.jpg', '.jpeg', '.png'],
    message="Only PDF or image files are allowed for receipts."
)

validate_grade_import_file = FileTypeValidator(
    allowed_types=[
        'text/csv',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ],
    allowed_extensions=['.csv', '.xls', '.xlsx'],
    message="Only CSV or Excel files are allowed for imports."
)

validate_evidence_file = FileTypeValidator(
    allowed_types=[
        'application/pdf',
        'image/jpeg',
        'image/png',
        'image/jpg',
        'image/gif',
        'image/webp',
        'video/mp4',
        'video/quicktime',
        'video/webm',
    ],
    allowed_extensions=[
        '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.mov', '.webm',
    ],
    message="Only PDF, image, or video files are allowed for evidence."
)

validate_kb_attachment_file = FileTypeValidator(
    allowed_types=[
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.oasis.opendocument.text',
        'application/vnd.oasis.opendocument.spreadsheet',
        'image/jpeg',
        'image/png',
        'image/jpg',
        'image/gif',
        'image/webp',
    ],
    allowed_extensions=[
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.odt', '.ods',
        '.jpg', '.jpeg', '.png', '.gif', '.webp',
    ],
    message="Only PDF, Office (Word/Excel or LibreOffice ODT/ODS), or image files are allowed for attachments."
)

validate_file_size_5mb = FileSizeValidator(max_size_mb=5)
validate_file_size_10mb = FileSizeValidator(max_size_mb=10)
validate_file_size_20mb = FileSizeValidator(max_size_mb=20)
validate_file_size_2mb = FileSizeValidator(max_size_mb=2)
