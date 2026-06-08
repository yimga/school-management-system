"""Documentation hub — KB articles + LibreOffice office docs (tenant + operator)."""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_http_methods

from apps.portal.kb_context import filter_by_target_roles, is_operator_help_request
from apps.portal.kb_office_service import (
    build_docs_hub_context,
    create_hosted_office_document,
    import_writer_file_to_kb_article,
    office_document_export_bytes,
    reimport_odt_into_kb_article,
    resolve_default_help_audience,
    validate_office_extension,
)
from apps.portal.models_kb import HelpAudience, KBArticle, KBCategory, UserContribution
from apps.portal.operator_kb_render import render_kb_if_operator
from apps.portal.views_office import _doc_for_request

logger = logging.getLogger(__name__)


def _staff_may_reimport_kb(request, article: KBArticle) -> bool:
    if not getattr(request.user, "is_authenticated", False) or not request.user.is_staff:
        return False
    is_op = is_operator_help_request(request)
    school = getattr(request, "school", None)
    if is_op:
        return article.school_id is None or bool(article.is_global_article)
    if school is not None:
        return article.school_id == school.id
    return bool(getattr(request.user, "is_superuser", False))


@login_required
@require_GET
def kb_docs_hub(request):
    ctx = build_docs_hub_context(request)
    return render_kb_if_operator(
        request,
        portal_template="portal/kb_docs_hub.html",
        operator_body_template="portal/operator/kb_docs_hub_body.html",
        context=ctx,
        page_title="Documentation hub",
    )


@login_required
@require_http_methods(["GET", "POST"])
def kb_office_upload(request):
    is_op = is_operator_help_request(request)
    school = getattr(request, "school", None)
    categories = filter_by_target_roles(KBCategory.objects.filter(is_active=True), request)

    if request.method == "POST":
        action = (request.POST.get("action") or "office").strip().lower()
        title = (request.POST.get("title") or "").strip()
        audience = (request.POST.get("help_audience") or resolve_default_help_audience(request)).strip()
        if audience not in HelpAudience.values:
            audience = resolve_default_help_audience(request)

        upload = request.FILES.get("file")
        if not upload:
            messages.error(request, "Choose a file to upload.")
            return redirect("kb:kb_office_upload")

        try:
            if action == "import_kb":
                category_id = request.POST.get("category")
                if not category_id:
                    messages.error(request, "Select a category for KB import.")
                    return redirect("kb:kb_office_upload")
                category = get_object_or_404(KBCategory, id=category_id)
                summary = (request.POST.get("summary") or "").strip()
                article = import_writer_file_to_kb_article(
                    uploaded_file=upload,
                    title=title,
                    category=category,
                    author=request.user,
                    help_audience=audience,
                    school=None if is_op else school,
                    summary=summary,
                )
                UserContribution.objects.create(
                    user=request.user,
                    contribution_type="ARTICLE_SUBMIT",
                    points=25,
                    description=f"Imported ODT article: {article.title[:50]}",
                )
                messages.success(
                    request,
                    f"Imported “{article.title}” as a pending KB article for review.",
                )
                return redirect("kb:kb_docs_hub")

            validate_office_extension(upload.name)
            doc = create_hosted_office_document(
                uploaded_file=upload,
                title=title,
                help_audience=audience,
                school=None if is_op else school,
                created_by=request.user,
            )
            messages.success(request, f"Uploaded office document “{doc.title}”.")
            return redirect("kb:office_document_open", document_id=doc.pk)
        except ValueError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            logger.warning("kb_office_upload failed: %s", exc)
            messages.error(request, "Upload failed. Check file type and try again.")

    ctx = {
        "is_operator_help": is_op,
        "categories": categories,
        "help_audience_choices": HelpAudience.choices,
        "default_audience": resolve_default_help_audience(request),
    }
    return render_kb_if_operator(
        request,
        portal_template="portal/kb_office_upload.html",
        operator_body_template="portal/operator/kb_office_upload_body.html",
        context=ctx,
        page_title="Upload document",
    )


@login_required
@require_GET
def office_document_download(request, document_id: int):
    doc = _doc_for_request(request, document_id)
    target = (request.GET.get("format") or "pdf").strip().lower()
    try:
        payload, content_type, filename = office_document_export_bytes(doc, target)
    except ValueError as exc:
        raise Http404(str(exc)) from exc
    except Exception as exc:
        logger.warning("office_document_download failed doc=%s: %s", document_id, exc)
        raise Http404("Conversion unavailable") from exc
    response = FileResponse(payload, content_type=content_type, as_attachment=True)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_GET
def office_document_preview_pdf(request, document_id: int):
    doc = _doc_for_request(request, document_id)
    try:
        payload, content_type, _filename = office_document_export_bytes(doc, "pdf")
    except Exception as exc:
        logger.warning("office_document_preview_pdf failed doc=%s: %s", document_id, exc)
        raise Http404("Preview unavailable") from exc
    return FileResponse(payload, content_type=content_type, as_attachment=False)


@login_required
@require_http_methods(["POST"])
def kb_article_reimport_odt(request, article_slug: str):
    article = get_object_or_404(
        KBArticle.objects.exclude(status="ARCHIVED"),
        slug=article_slug,
    )
    if not _staff_may_reimport_kb(request, article):
        messages.error(request, "You do not have permission to re-import this article.")
        return redirect("kb:kb_article", article_slug=article.slug)

    upload = request.FILES.get("file")
    if not upload:
        messages.error(request, "Choose an ODT, DOCX, or text file to upload.")
        return redirect("kb:kb_article", article_slug=article.slug)

    try:
        summary = (request.POST.get("summary") or "").strip()
        reimport_odt_into_kb_article(
            article,
            uploaded_file=upload,
            author=request.user,
            summary=summary,
        )
        UserContribution.objects.create(
            user=request.user,
            contribution_type="ARTICLE_SUBMIT",
            points=15,
            description=f"Re-imported ODT for article: {article.title[:50]}",
        )
        messages.success(
            request,
            f"Updated “{article.title}” from your upload — status is pending review.",
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        logger.warning("kb_article_reimport_odt failed slug=%s: %s", article_slug, exc)
        messages.error(request, "Re-import failed. Check file type and try again.")

    return redirect("kb:kb_article", article_slug=article.slug)
