"""
Document Library Management Views
Backend UI for admins to upload and manage documents
"""

import os
import tempfile

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, FileResponse
from django.db.models import Q, Count
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods

from apps.accounts.decorators import permission_required
from apps.accounts.models import User
from apps.people.models import StudentProfile, StudentGuardian
from apps.siteconfig.models import SiteSettings
from .models import PortalFeatureItem, FormSignature
from .forms_documents import DocumentUploadForm, SignatureRequestForm
from .document_conversion import convert_to_pdf


@permission_required("settings.manage")
@login_required
def document_library_manage(request):
    """
    Backend UI for managing documents in the Document Library.
    Admin can upload, edit, delete documents.
    """
    site = SiteSettings.get_solo()
    
    # Get all documents
    qs = PortalFeatureItem.objects.filter(feature=PortalFeatureItem.Feature.DOCUMENTS)
    school = getattr(request, "school", None)
    if school is not None:
        qs = qs.filter(school=school)
    documents = qs.select_related("created_by").order_by("-created_at")
    
    # Filter by document type if requested
    doc_type = request.GET.get("type")
    if doc_type:
        documents = documents.filter(document_type=doc_type)
    
    # Search
    search_query = request.GET.get("q")
    if search_query:
        documents = documents.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Stats
    stats = {
        "total": documents.count(),
        "with_files": documents.filter(file__isnull=False).count(),
        "with_links": documents.exclude(link="").count(),
        "requires_signature": documents.filter(requires_signature=True).count(),
        "active": documents.filter(is_active=True).count(),
    }
    
    # Group by type
    by_type = {}
    for doc_type, label in PortalFeatureItem.DocumentType.choices:
        count = documents.filter(document_type=doc_type).count()
        if count > 0:
            by_type[doc_type] = {"label": label, "count": count}
    
    context = {
        "documents": documents,
        "stats": stats,
        "by_type": by_type,
        "document_types": PortalFeatureItem.DocumentType.choices,
        "current_type": doc_type,
        "search_query": search_query,
    }
    
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
    if document_id:
        qs = PortalFeatureItem.objects.filter(
            id=document_id,
            feature=PortalFeatureItem.Feature.DOCUMENTS
        )
        if school is not None:
            qs = qs.filter(school=school)
        document = get_object_or_404(qs)
        # Check permissions
        if not (request.user.is_superuser or document.created_by == request.user):
            messages.error(request, "You don't have permission to edit this document.")
            return redirect("portal:document_library_manage")
    
    form = DocumentUploadForm(request.POST or None, request.FILES or None, instance=document)
    
    if request.method == "POST" and form.is_valid():
        doc = form.save(commit=False)
        if not document:  # New document
            doc.feature = PortalFeatureItem.Feature.DOCUMENTS
            doc.created_by = request.user
        doc.school = school  # Section 25.3: tenant scope for upload path
        doc.save()
        
        messages.success(
            request,
            f"Document '{doc.title}' {'updated' if document else 'uploaded'} successfully."
        )
        return redirect("portal:document_library_manage")
    
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
    school = getattr(request, "school", None)
    qs = PortalFeatureItem.objects.filter(id=document_id, feature=PortalFeatureItem.Feature.DOCUMENTS)
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
    Download a document file (with access control). Section 25.3: tenant-scoped by school when set.
    """
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
    response["Content-Disposition"] = f'inline; filename="{os.path.basename(document.file.name)}"'
    return response


@login_required
def document_download_pdf(request, document_id):
    """
    Convert document (ODT/DOCX) to PDF and serve. Same access as document_download.
    Section 25.3: tenant-scoped by school when set.
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
        messages.info(request, "Convert to PDF is only available for Word (DOCX) or LibreOffice (ODT) files.")
        return redirect("portal:document_download", document_id=document_id)
    path = None
    try:
        if hasattr(document.file, "path") and os.path.isfile(document.file.path):
            path = document.file.path
        else:
            with tempfile.NamedTemporaryFile(suffix=_document_file_extension(document), delete=False) as tmp:
                tmp.write(document.file.read())
                path = tmp.name
        pdf_bytes = convert_to_pdf(path)
        base = os.path.splitext(os.path.basename(document.file.name))[0]
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{base}.pdf"'
        return response
    except RuntimeError:
        messages.error(request, "PDF conversion is not available (LibreOffice may not be installed).")
        return redirect("portal:document_download", document_id=document_id)
    except Exception:
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
        "pending": requests.filter(status=FormSignature.SignatureStatus.PENDING).count(),
        "signed": requests.filter(status=FormSignature.SignatureStatus.SIGNED).count(),
        "expired": requests.filter(status=FormSignature.SignatureStatus.EXPIRED).count(),
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
            f"Signature request created for {signature_request.parent.get_full_name()}."
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
    pending_requests = FormSignature.objects.filter(
        parent=request.user,
        status=FormSignature.SignatureStatus.PENDING,
        student_id__in=student_ids if student_ids else []
    ).select_related("form_document", "student").order_by("-created_at")
    
    # Filter out expired
    from django.utils import timezone
    now = timezone.now()
    pending_requests = [
        req for req in pending_requests
        if not req.is_expired
    ]
    
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
