"""Collabora/WOPI minimal integration for hosted office docs (T4)."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from apps.portal.kb_context import is_operator_help_request
from apps.portal.models_kb import HelpAudience, HostedOfficeDocument


def _collabora_base_url() -> str:
    return (os.getenv("COLLABORA_BASE_URL") or "").strip().rstrip("/")


def _wopi_secret() -> str:
    return (os.getenv("WOPI_SHARED_SECRET") or settings.SECRET_KEY or "").strip()


def _issue_doc_token(doc: HostedOfficeDocument, ttl_seconds: int = 8 * 60 * 60) -> str:
    exp = int(time.time()) + ttl_seconds
    payload = f"{doc.pk}:{exp}"
    sig = hmac.new(_wopi_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def _verify_doc_token(doc: HostedOfficeDocument, token: str) -> bool:
    token = (token or "").strip()
    if not token or "." not in token:
        return False
    exp_raw, sig = token.split(".", 1)
    try:
        exp = int(exp_raw)
    except ValueError:
        return False
    if exp < int(time.time()):
        return False
    payload = f"{doc.pk}:{exp}"
    expected = hmac.new(
        _wopi_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig)


def _doc_for_request(request, document_id: int) -> HostedOfficeDocument:
    doc = get_object_or_404(HostedOfficeDocument, pk=document_id)
    is_op = is_operator_help_request(request)
    if is_op and doc.help_audience not in (HelpAudience.OPERATOR, HelpAudience.BOTH):
        raise Http404("Not found")
    if (not is_op) and doc.help_audience not in (HelpAudience.TENANT, HelpAudience.BOTH):
        raise Http404("Not found")
    school = getattr(request, "school", None)
    if doc.school_id and school and doc.school_id != school.id:
        raise Http404("Not found")
    if doc.school_id and school is None and not is_op:
        raise Http404("Not found")
    return doc


@login_required
@require_GET
def office_document_list(request):
    is_op = is_operator_help_request(request)
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    qs = HostedOfficeDocument.objects.all()
    if is_op:
        qs = qs.filter(help_audience__in=[HelpAudience.OPERATOR, HelpAudience.BOTH])
    else:
        qs = qs.filter(help_audience__in=[HelpAudience.TENANT, HelpAudience.BOTH])
        school = getattr(request, "school", None)
        if school is not None:
            qs = qs.filter(school__in=[school, None])
        else:
            qs = qs.filter(school__isnull=True)
    return render(
        request,
        "portal/office_document_list.html",
        {
            "documents": qs[:100],
            "is_operator_help": is_op,
            "collabora_enabled": bool(_collabora_base_url()),
        },
    )


@login_required
@require_GET
def office_document_open(request, document_id: int):
    doc = _doc_for_request(request, document_id)
    base = _collabora_base_url()
    if not base:
        return render(
            request,
            "portal/office_document_open.html",
            {
                "document": doc,
                "collabora_url": "",
                "error": "Collabora is not configured (COLLABORA_BASE_URL).",
            },
        )
    wopi_src = request.build_absolute_uri(f"/kb/wopi/files/{doc.pk}")
    token = _issue_doc_token(doc)
    collabora_url = (
        f"{base}/browser/6.4.0/cool.html?WOPISrc={quote(wopi_src, safe='')}&access_token={token}"
    )
    return render(
        request,
        "portal/office_document_open.html",
        {"document": doc, "collabora_url": collabora_url, "token": token},
    )


def _extract_access_token(request) -> str:
    return (
        request.GET.get("access_token")
        or request.headers.get("Authorization", "").replace("Bearer ", "")
        or ""
    ).strip()


@csrf_exempt
@require_GET
def wopi_check_file_info(request, document_id: int):
    doc = get_object_or_404(HostedOfficeDocument, pk=document_id)
    token = _extract_access_token(request)
    if not _verify_doc_token(doc, token):
        return JsonResponse({"error": "Invalid token"}, status=403)
    size = doc.file.size if doc.file else 0
    return JsonResponse(
        {
            "BaseFileName": os.path.basename(doc.file.name),
            "Size": size,
            "Version": str(int(doc.updated_at.timestamp() if doc.updated_at else 0)),
            "UserId": "wopi-service",
            "UserFriendlyName": "WOPI Service",
            "SupportsUpdate": True,
            "UserCanWrite": True,
        }
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def wopi_file_contents(request, document_id: int):
    doc = get_object_or_404(HostedOfficeDocument, pk=document_id)
    token = _extract_access_token(request)
    if not _verify_doc_token(doc, token):
        return HttpResponse("Invalid token", status=403)

    if request.method == "GET":
        if not doc.file:
            raise Http404("No file")
        return FileResponse(doc.file.open("rb"), as_attachment=False)

    payload = request.body or b""
    if not payload:
        return HttpResponse("Empty payload", status=400)

    target_name = os.path.basename(doc.file.name or f"doc_{doc.pk}.bin")
    doc.file.save(target_name, ContentFile(payload), save=True)
    return HttpResponse("OK", status=200)
