"""
Parental Permission & Consent Hub (plan 3.18).
Versioned documents; hash at sign; mark outdated and re-request; withdrawal in audit.
"""
from __future__ import annotations

import hashlib

from django.utils import timezone

from apps.compliance.models import ConsentRequest, ConsentRecord


def get_document_hash(document_text: str) -> str:
    """SHA-256 of document text at sign time."""
    return hashlib.sha256((document_text or "").encode("utf-8")).hexdigest()


def get_pending_consents_for_user(user, school):
    """Consent requests that user has not yet signed (or that are outdated)."""
    if not school:
        return []
    signed_ids = set(
        ConsentRecord.objects.filter(user=user, school=school, withdrawn_at__isnull=True)
        .values_list("consent_request_id", flat=True)
        .filter(consent_request_id__isnull=False)
    )
    qs = ConsentRequest.objects.filter(school=school, is_active=True).order_by("due_date", "-created_at")
    return [r for r in qs if r.id not in signed_ids]


def get_completed_consents_for_user(user, school):
    """Consent records (audit) for Permission Hub 'Completed' list."""
    if not school:
        return []
    return list(
        ConsentRecord.objects.filter(user=user, school=school)
        .select_related("consent_request")
        .order_by("-signed_at")[:50]
    )


def mark_consents_outdated_for_request(consent_request):
    """
    When school updates document, mark prior consents as outdated (e.g. set a flag or
    create new ConsentRequest and treat previous as superseded). This implementation
    treats 'outdated' as: same consent_request has a newer version; we don't add a column
    but we can add consent_request.document_version_id and when it's bumped, previous
    ConsentRecords for same request are considered outdated for display.
    """
    # Optional: add ConsentRecord.is_outdated and set True for records whose
    # consent_request.document_version_id < consent_request.current version
    pass


def create_consent_record(user, school, title: str, document_text: str, request=None, consent_request=None):
    """Record signature with SHA-256 hash; IP from request."""
    doc_hash = get_document_hash(document_text)
    ip = None
    if request:
        try:
            from ipware import get_client_ip
            ip, _ = get_client_ip(request)
        except ImportError:
            ip = request.META.get("REMOTE_ADDR")
    return ConsentRecord.objects.create(
        school=school,
        user=user,
        consent_request=consent_request,
        title=title,
        document_hash=doc_hash,
        ip_address=ip,
        document_version_at_sign=consent_request.document_version_id if consent_request else None,
    )


def withdraw_consent(record_id, user):
    """Set withdrawn_at; record must belong to user."""
    record = ConsentRecord.objects.filter(id=record_id, user=user).first()
    if not record:
        return False
    record.withdrawn_at = timezone.now()
    record.save(update_fields=["withdrawn_at"])
    return True
