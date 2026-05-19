"""
Document Library Management Views
Backend UI for admins to upload and manage documents
"""

import csv
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, FileResponse
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods

from apps.accounts.decorators import permission_required
from apps.accounts.models import User
from apps.packages.models import DocumentPack
from apps.people.models import StudentGuardian
from .document_lifecycle import DOCUMENT_LIFECYCLE_CHOICES
from .models import PortalFeatureItem, FormSignature
from .forms_documents import DocumentUploadForm, SignatureRequestForm
from .document_service import convert_document
from apps.platform_runtime.structured_logging import (
    log_exception_with_context,
    request_context_for_log,
)


def document_library_filtered_queryset(request):
    """
    School-scoped document library queryset with the same GET filters as the manage view.
    """
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    qs = PortalFeatureItem.objects.filter(feature=PortalFeatureItem.Feature.DOCUMENTS)
    school = getattr(request, "school", None)
    if school is not None:
        qs = qs.filter(school=school)
    documents = qs.select_related("created_by").order_by("-created_at")

    doc_type = request.GET.get("type")
    if doc_type:
        documents = documents.filter(document_type=doc_type)

    lifecycle_state = (request.GET.get("lifecycle") or "").strip().lower()
    if lifecycle_state:
        documents = documents.filter(lifecycle_state=lifecycle_state)

    pack_code = (request.GET.get("pack") or "").strip()
    if pack_code:
        documents = documents.filter(document_pack__code=pack_code)

    from apps.portal.document_search import filter_documents_by_search
    from apps.siteconfig.list_search import normalize_list_search_query

    search_query = normalize_list_search_query(request.GET.get("q"))
    return filter_documents_by_search(documents, search_query)


def build_document_library_manage_context(request, *, studio_output_native: bool = False):
    """
    Shared context for document library full page, embed=1 iframe, or Studio Output native pane.
    """
    documents = document_library_filtered_queryset(request)

    doc_type = request.GET.get("type")
    lifecycle_state = (request.GET.get("lifecycle") or "").strip().lower()
    pack_code = (request.GET.get("pack") or "").strip()
    search_query = request.GET.get("q")

    stats = {
        "total": documents.count(),
        "with_files": documents.filter(file__isnull=False).count(),
        "with_links": documents.exclude(link="").count(),
        "requires_signature": documents.filter(requires_signature=True).count(),
        "active": documents.filter(is_active=True).count(),
        "packaged": documents.filter(document_pack__isnull=False).count(),
        "archived": documents.filter(lifecycle_state="archived").count(),
    }

    by_type = {}
    for dt, label in PortalFeatureItem.DocumentType.choices:
        count = documents.filter(document_type=dt).count()
        if count > 0:
            by_type[dt] = {"label": label, "count": count}

    embed = request.GET.get("embed") == "1" or studio_output_native
    document_upload_url = reverse("portal:document_upload") + ("?embed=1" if embed else "")

    try:
        studio_output_url = reverse("studio_os:output")
    except NoReverseMatch:
        studio_output_url = ""
    document_library_form_action = (
        f"{studio_output_url}?pane=documents" if studio_output_native and studio_output_url else ""
    )

    return {
        "documents": documents,
        "stats": stats,
        "by_type": by_type,
        "document_types": PortalFeatureItem.DocumentType.choices,
        "document_packs": DocumentPack.objects.filter(is_active=True).order_by("name"),
        "lifecycle_choices": DOCUMENT_LIFECYCLE_CHOICES,
        "current_type": doc_type,
        "current_lifecycle": lifecycle_state,
        "current_pack": pack_code,
        "search_query": search_query,
        "embed": embed,
        "studio_output_native": studio_output_native,
        "document_upload_url": document_upload_url,
        "document_library_form_action": document_library_form_action,
    }


@permission_required("settings.manage")
@login_required
def document_library_manage(request):
    """
    Backend UI for managing documents in the Document Library.
    When not embedded in Studio, redirect to Studio Output (pane=documents).
    End-user role-aware visibility is enforced by PortalFeatureItem.can_view() when
    serving documents to portal users; this manage view shows all school docs for admins.
    """
    if request.GET.get("embed") != "1":
        return redirect(reverse("studio_os:output") + "?pane=documents")

    documents = document_library_filtered_queryset(request)

    # Export CSV (26.5 list standards)
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="document_library_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )
        w = csv.writer(response)
        w.writerow(
            [
                "title",
                "document_type",
                "lifecycle_state",
                "document_pack",
                "has_file",
                "has_link",
                "requires_signature",
                "is_active",
                "retention_review_at",
                "created_at",
            ]
        )
        for doc in documents[:10000]:
            w.writerow(
                [
                    doc.title or "",
                    doc.get_document_type_display() if doc.document_type else "",
                    doc.lifecycle_state or "",
                    getattr(getattr(doc, "document_pack", None), "code", "") or "",
                    "yes" if doc.file else "no",
                    "yes" if doc.link else "no",
                    "yes" if doc.requires_signature else "no",
                    "yes" if doc.is_active else "no",
                    doc.retention_review_at.isoformat()
                    if doc.retention_review_at
                    else "",
                    doc.created_at.strftime("%Y-%m-%d %H:%M") if doc.created_at else "",
                ]
            )
        return response

    context = build_document_library_manage_context(request, studio_output_native=False)
    return render(request, "portal/document_library_manage.html", context)


@permission_required("settings.manage")
@login_required
@require_http_methods(["GET", "POST"])
def document_upload(request, document_id=None):
    """
    Upload or edit a document.
    """
    document = None
    school = getattr(request, "school", None)
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    if document_id:
        qs = PortalFeatureItem.objects.filter(
            id=document_id, feature=PortalFeatureItem.Feature.DOCUMENTS
        )
        if school is not None:
            qs = qs.filter(school=school)
        document = get_object_or_404(qs)
        # Check permissions
        if not (request.user.is_superuser or document.created_by == request.user):
            messages.error(request, "You don't have permission to edit this document.")
            return redirect("portal:document_library_manage")

    form = DocumentUploadForm(
        request.POST or None, request.FILES or None, instance=document
    )

    if request.method == "POST" and form.is_valid():
        doc = form.save(commit=False)
        if not document:  # New document
            doc.feature = PortalFeatureItem.Feature.DOCUMENTS
            doc.created_by = request.user
        doc.school = school  # Section 25.3: tenant scope for upload path
        doc.save()
        if school and doc.document_pack_id:
            from apps.packages.tenant_pack_install import record_document_pack_usage

            pack_result = record_document_pack_usage(
                school,
                doc.document_pack,
                actor_id=getattr(request.user, "pk", None),
            )
            if not pack_result.get("ok") and not pack_result.get("skipped"):
                log_exception_with_context(
                    "document_upload record_document_pack_usage failed",
                    **request_context_for_log(request),
                    exc_info=False,
                    extra={
                        "document_id": getattr(doc, "pk", None),
                        "errors": pack_result.get("errors"),
                    },
                )

        messages.success(
            request,
            f"Document '{doc.title}' {'updated' if document else 'uploaded'} successfully.",
        )
        # Preserve embed=1 so Studio users stay in Output Studio after save (§5.4)
        base_url = reverse("portal:document_library_manage")
        if request.GET.get("embed") == "1" or request.POST.get("embed") == "1":
            base_url = f"{base_url}?embed=1"
        return redirect(base_url)

    context = {
        "form": form,
        "document": document,
        "is_edit": bool(document),
    }

    return render(request, "portal/document_upload.html", context)


@permission_required("settings.manage")
@login_required
@require_POST
def document_delete(request, document_id):
    """
    Delete a document.
    """
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    school = getattr(request, "school", None)
    qs = PortalFeatureItem.objects.filter(
        id=document_id, feature=PortalFeatureItem.Feature.DOCUMENTS
    )
    if school is not None:
        qs = qs.filter(school=school)
    document = get_object_or_404(qs)

    # Check permissions
    if not (request.user.is_superuser or document.created_by == request.user):
        messages.error(request, "You don't have permission to delete this document.")
        return redirect("portal:document_library_manage")

    title = document.title
    document.delete()

    messages.success(request, f"Document '{title}' deleted successfully.")
    return redirect("portal:document_library_manage")


def _document_file_extension(document):
    """Return lowercased file extension (e.g. '.odt') or ''."""
    if not document.file or not document.file.name:
        return ""
    return os.path.splitext(document.file.name)[1].lower()


def _is_convertible_to_pdf(document):
    """True if the document file is ODT or DOCX and can be converted to PDF by headless."""
    return _document_file_extension(document) in (".odt", ".docx")


@login_required
def document_download(request, document_id):
    """
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    Download a document file (with access control). Section 25.3: tenant-scoped by school when set.
    """
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    qs = PortalFeatureItem.objects.filter(id=document_id)
    school = getattr(request, "school", None)
    if school is not None:
        qs = qs.filter(school=school)
    document = get_object_or_404(qs)

    # Check access
    if not document.can_view(request.user):
        messages.error(request, "You don't have permission to access this document.")
        return redirect("portal:parent_dashboard")

    if not document.file:
        messages.error(request, "This document doesn't have a file attached.")
        return redirect("portal:portal_feature", feature="documents")

    # Serve file (correct content type would require mapping by extension; browser often handles)
    f = document.file.open("rb")
    response = FileResponse(f, content_type="application/octet-stream")
    response["Content-Disposition"] = (
        f'inline; filename="{os.path.basename(document.file.name)}"'
    )
    return response


@login_required
def document_download_pdf(request, document_id):
    """
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    Convert document (ODT/DOCX) to PDF and serve. Same access as document_download.
    Section 25.3: tenant-scoped by school when set.
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    """
    qs = PortalFeatureItem.objects.filter(id=document_id)
    school = getattr(request, "school", None)
    if school is not None:
        qs = qs.filter(school=school)
    document = get_object_or_404(qs)
    if not document.can_view(request.user):
        messages.error(request, "You don't have permission to access this document.")
        return redirect("portal:portal_feature", feature="documents")
    if not document.file:
        messages.error(request, "This document doesn't have a file attached.")
        return redirect("portal:portal_feature", feature="documents")
    if not _is_convertible_to_pdf(document):
        messages.info(
            request,
            "Convert to PDF is only available for Word (DOCX) or LibreOffice (ODT) files.",
        )
        return redirect("portal:document_download", document_id=document_id)
    path = None
    try:
        if hasattr(document.file, "path") and os.path.isfile(document.file.path):
            path = document.file.path
        else:
            with tempfile.NamedTemporaryFile(
                suffix=_document_file_extension(document), delete=False
            ) as tmp:
                tmp.write(document.file.read())
                path = tmp.name
        pdf_bytes = convert_document(path, target="pdf", family="writer")
        base = os.path.splitext(os.path.basename(document.file.name))[0]
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{base}.pdf"'
        return response
    except RuntimeError:
        messages.error(
            request,
            "PDF conversion is not available (LibreOffice may not be installed).",
        )
        return redirect("portal:document_download", document_id=document_id)
    except (OSError, ValueError, TypeError) as e:
        ctx = request_context_for_log(request) if request else {}
        log_exception_with_context(
            "portal.views_documents: PDF conversion failed",
            school_id=ctx.get("school_id"),
            tenant_id=ctx.get("tenant_id"),
            actor_id=ctx.get("actor_id"),
            route=ctx.get("route"),
            extra={"document_id": document_id, "error": str(e)},
        )
        logger.warning("PDF conversion failed for document %s: %s", document_id, e)
        messages.error(request, "PDF conversion failed.")
        return redirect("portal:document_download", document_id=document_id)
    finally:
        if path and path != getattr(document.file, "path", None):
            try:
                os.unlink(path)
            except OSError:
                pass


@permission_required("settings.manage")
@login_required
def signature_requests_manage(request):
    """
    Manage signature requests for forms.
    """
    requests = FormSignature.objects.select_related(
        "form_document", "student", "parent", "created_by"
    ).order_by("-created_at")

    # Filter by status
    status_filter = request.GET.get("status")
    if status_filter:
        requests = requests.filter(status=status_filter)

    # Stats
    stats = {
        "total": requests.count(),
        "pending": requests.filter(
            status=FormSignature.SignatureStatus.PENDING
        ).count(),
        "signed": requests.filter(status=FormSignature.SignatureStatus.SIGNED).count(),
        "expired": requests.filter(
            status=FormSignature.SignatureStatus.EXPIRED
        ).count(),
    }

    context = {
        "requests": requests,
        "stats": stats,
        "status_choices": FormSignature.SignatureStatus.choices,
        "current_status": status_filter,
    }

    return render(request, "portal/signature_requests_manage.html", context)


@permission_required("settings.manage")
@login_required
@require_http_methods(["GET", "POST"])
def signature_request_create(request):
    """
    Create a new signature request for a form.
    """
    form = SignatureRequestForm(request.POST or None, user=request.user)

    if request.method == "POST" and form.is_valid():
        signature_request = form.save(commit=False)
        signature_request.created_by = request.user
        signature_request.save()

        messages.success(
            request,
            f"Signature request created for {signature_request.parent.get_full_name()}.",
        )
        return redirect("portal:signature_requests_manage")

    context = {
        "form": form,
    }

    return render(request, "portal/signature_request_create.html", context)


@login_required
def signature_pending_list(request):
    """
    List pending signature requests for the current user (parent).
    """
    if request.user.role != User.Role.PARENT:
        messages.error(request, "Only parents can sign forms.")
        return redirect("portal:parent_dashboard")

    # Get linked students
    guardian_links = StudentGuardian.objects.filter(guardian_user=request.user)
    student_ids = [link.student_id for link in guardian_links]

    # Get pending signature requests for this parent's children
    pending_requests = (
        FormSignature.objects.filter(
            parent=request.user,
            status=FormSignature.SignatureStatus.PENDING,
            student_id__in=student_ids if student_ids else [],
        )
        .select_related("form_document", "student")
        .order_by("-created_at")
    )

    # Filter out expired
    from django.utils import timezone

    timezone.now()
    pending_requests = [req for req in pending_requests if not req.is_expired]

    context = {
        "pending_requests": pending_requests,
        "guardian_links": guardian_links,
    }

    return render(request, "portal/signature_pending_list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def signature_sign(request, signature_id):
    """
    Sign a form electronically.
    """
    signature_request = get_object_or_404(FormSignature, id=signature_id)

    # Check permissions
    if signature_request.parent != request.user:
        messages.error(request, "You don't have permission to sign this form.")
        return redirect("portal:parent_dashboard")

    if not signature_request.can_sign:
        messages.error(request, "This signature request is no longer valid.")
        return redirect("portal:signature_pending_list")

    if request.method == "POST":
        signature_data = request.POST.get("signature_data")
        if signature_data:
            import hashlib

            signature_hash = hashlib.sha256(signature_data.encode()).hexdigest()

            signature_request.mark_as_signed(signature_data, signature_hash, request)

            messages.success(request, "Form signed successfully!")
            return redirect("portal:signature_pending_list")
        else:
            messages.error(request, "Please provide a signature.")

    context = {
        "signature_request": signature_request,
        "form_document": signature_request.form_document,
        "student": signature_request.student,
    }

    return render(request, "portal/signature_sign.html", context)
