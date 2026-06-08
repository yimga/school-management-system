"""KB + LibreOffice office document services (tenant + operator)."""

from __future__ import annotations

import mimetypes
import re
from html.parser import HTMLParser
from pathlib import Path

from django.core.files.base import ContentFile
from django.utils.text import slugify

from apps.portal.document_conversion import (
    convert_odt_to_html,
    convert_to_docx,
    convert_to_pdf,
    portal_tempdir,
)
from apps.portal.document_generation import markdown_to_document
from apps.portal.kb_context import (
    filter_kb_articles_by_school,
    filter_kb_articles_for_host,
    is_operator_help_request,
    published_kb_queryset,
)
from apps.portal.models_kb import HelpAudience, HostedOfficeDocument, KBArticle, KBCategory

OFFICE_UPLOAD_EXTENSIONS = frozenset(
    {
        ".odt",
        ".doc",
        ".docx",
        ".ods",
        ".xls",
        ".xlsx",
        ".csv",
        ".odp",
        ".ppt",
        ".pptx",
        ".rtf",
        ".txt",
    }
)
WRITER_IMPORT_EXTENSIONS = frozenset({".odt", ".doc", ".docx", ".rtf", ".txt", ".html", ".htm"})


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
        if tag.lower() in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = (data or "").strip()
        if text:
            self._chunks.append(text)

    def plain_text(self) -> str:
        joined = " ".join(self._chunks)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        joined = re.sub(r"[ \t]{2,}", " ", joined)
        return joined.strip()


def guess_office_mime(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def validate_office_extension(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in OFFICE_UPLOAD_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type {ext or '(none)'}. "
            f"Allowed: {', '.join(sorted(OFFICE_UPLOAD_EXTENSIONS))}"
        )
    return ext


def office_documents_queryset_for_request(request):
    is_op = is_operator_help_request(request)
    if is_op:
        qs = HostedOfficeDocument.objects.filter(  # tenant-isolation-allow: operator-help-kb-cross-tenant-catalog
            help_audience__in=[HelpAudience.OPERATOR, HelpAudience.BOTH]
        )
    else:
        school = getattr(request, "school", None)
        if school is not None:
            qs = HostedOfficeDocument.objects.filter(
                help_audience__in=[HelpAudience.TENANT, HelpAudience.BOTH],
                school__in=[school, None],
            )
        else:
            qs = HostedOfficeDocument.objects.filter(
                help_audience__in=[HelpAudience.TENANT, HelpAudience.BOTH],
                school__isnull=True,
            )
    return qs.order_by("-updated_at")


def office_documents_for_request(request, *, limit: int = 50):
    return office_documents_queryset_for_request(request)[:limit]


def search_office_documents(queryset, query: str, *, limit: int = 25):
    q = (query or "").strip()
    if not q:
        return []
    return list(queryset.filter(title__icontains=q)[:limit])


def _article_office_scope_compatible(article: KBArticle, office_doc: HostedOfficeDocument) -> bool:
    if article.school_id is None and office_doc.school_id is None:
        return True
    return article.school_id == office_doc.school_id


def link_kb_article_to_office_document(
    article: KBArticle,
    office_doc: HostedOfficeDocument,
) -> None:
    if not _article_office_scope_compatible(article, office_doc):
        raise ValueError("Article and office document must belong to the same school scope.")
    article.linked_office_document = office_doc
    article.save(update_fields=["linked_office_document"])


def unlink_kb_article_office_document(article: KBArticle) -> None:
    article.linked_office_document = None
    article.save(update_fields=["linked_office_document"])


def kb_articles_for_docs_hub(request, *, limit: int = 12):
    base = published_kb_queryset()
    base = filter_kb_articles_for_host(base, is_operator=is_operator_help_request(request))
    base = filter_kb_articles_by_school(base, request)
    return base.select_related("linked_office_document", "category").order_by(
        "-published_at"
    )[:limit]


def build_docs_hub_context(request) -> dict:
    from apps.portal.kb_search import search_kb_articles

    is_op = is_operator_help_request(request)
    query = (request.GET.get("q") or "").strip()
    article_base = filter_kb_articles_by_school(
        filter_kb_articles_for_host(published_kb_queryset(), is_operator=is_op),
        request,
    ).select_related("linked_office_document", "category")
    office_qs = office_documents_queryset_for_request(request)

    if query:
        search_article_hits = search_kb_articles(article_base, query, limit=25)
        search_articles = [row[0] for row in search_article_hits]
        search_office_docs = search_office_documents(office_qs, query, limit=25)
        articles = search_articles
        office_docs = search_office_docs
    else:
        search_article_hits = []
        search_articles = []
        search_office_docs = []
        articles = list(kb_articles_for_docs_hub(request, limit=12))
        office_docs = list(office_documents_for_request(request, limit=25))

    article_count = article_base.count()
    staff_may_link = (
        getattr(request.user, "is_authenticated", False)
        and getattr(request.user, "is_staff", False)
    )
    linkable_articles = []
    if staff_may_link:
        linkable_articles = list(
            KBArticle.objects.exclude(status="ARCHIVED")
            .select_related("linked_office_document")
            .order_by("-updated_at")[:50]
        )
    return {
        "is_operator_help": is_op,
        "featured_articles": articles[:6],
        "recent_articles": articles,
        "office_documents": office_docs,
        "article_count": article_count,
        "office_document_count": office_qs.count(),
        "collabora_enabled": bool((__import__("os").getenv("COLLABORA_BASE_URL") or "").strip()),
        "libreoffice_headless": True,
        "search_query": query,
        "search_article_hits": search_article_hits,
        "search_office_docs": search_office_docs,
        "staff_may_link": staff_may_link,
        "linkable_articles": linkable_articles,
        "all_office_docs_for_link": list(office_qs[:100]) if staff_may_link else [],
    }


def create_hosted_office_document(
    *,
    uploaded_file,
    title: str,
    help_audience: str,
    school,
    created_by,
) -> HostedOfficeDocument:
    validate_office_extension(uploaded_file.name)
    doc = HostedOfficeDocument(
        title=(title or uploaded_file.name).strip()[:200],
        help_audience=help_audience,
        school=school,
        created_by=created_by,
        mime_type=guess_office_mime(uploaded_file.name),
    )
    doc.file.save(uploaded_file.name, uploaded_file, save=True)
    return doc


def office_document_export_bytes(doc: HostedOfficeDocument, target: str) -> tuple[bytes, str, str]:
    if not doc.file:
        raise ValueError("Document has no file")
    path = doc.file.path
    t = (target or "pdf").strip().lower()
    if t == "pdf":
        return convert_to_pdf(path), "application/pdf", f"{doc.title}.pdf"
    if t == "docx":
        return convert_to_docx(path), (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            f"{doc.title}.docx",
        )
    if t == "odt":
        with doc.file.open("rb") as fh:
            return fh.read(), "application/vnd.oasis.opendocument.text", f"{doc.title}.odt"
    raise ValueError(f"Unsupported export target: {target}")


def html_to_plain_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html or "")
    parser.close()
    return parser.plain_text()


def _parse_writer_uploaded_file(uploaded_file) -> tuple[str, str]:
    """Return (plain_text, html) from an uploaded writer document."""
    ext = Path(uploaded_file.name or "").suffix.lower()
    if ext not in WRITER_IMPORT_EXTENSIONS:
        raise ValueError(
            f"Import supports writer formats only: {', '.join(sorted(WRITER_IMPORT_EXTENSIONS))}"
        )

    with portal_tempdir("kb_import_") as tmp_dir:
        src_path = tmp_dir / (uploaded_file.name or "upload.odt")
        with src_path.open("wb") as out:
            for chunk in uploaded_file.chunks():
                out.write(chunk)

        if ext in {".txt"}:
            plain = src_path.read_text(encoding="utf-8", errors="replace")
            html = f"<p>{plain}</p>"
        elif ext in {".html", ".htm"}:
            html = src_path.read_text(encoding="utf-8", errors="replace")
            plain = html_to_plain_text(html)
        else:
            html = convert_odt_to_html(str(src_path))
            plain = html_to_plain_text(html)

    return plain, html


def import_writer_file_to_kb_article(
    *,
    uploaded_file,
    title: str,
    category: KBCategory,
    author,
    help_audience: str,
    school,
    summary: str = "",
) -> KBArticle:
    ext = Path(uploaded_file.name or "").suffix.lower()
    plain, _html = _parse_writer_uploaded_file(uploaded_file)

    article_title = (title or Path(uploaded_file.name).stem).strip()[:200]
    article_summary = (summary or plain[:280]).strip()
    slug_base = slugify(article_title) or "article"

    article = KBArticle(
        category=category,
        title=article_title,
        slug=slug_base,
        summary=article_summary,
        content=plain or article_summary,
        author=author,
        status="PENDING",
        help_audience=help_audience,
        school=school,
        is_global_article=school is None,
    )
    article.save()

    try:
        odt_bytes = markdown_to_document(
            article.content,
            title=article.title,
            output_format="odt",
            engine="auto",
        )
        article.odt_file.save(
            f"{article.slug}.odt",
            ContentFile(odt_bytes),
            save=True,
        )
    except Exception:
        if ext == ".odt":
            uploaded_file.seek(0)
            article.odt_file.save(uploaded_file.name, uploaded_file, save=True)

    return article


def reimport_odt_into_kb_article(
    article: KBArticle,
    *,
    uploaded_file,
    author,
    summary: str = "",
) -> KBArticle:
    """Replace content on an existing article from an edited ODT/DOCX upload (staff round-trip)."""
    ext = Path(uploaded_file.name or "").suffix.lower()
    plain, _html = _parse_writer_uploaded_file(uploaded_file)
    article_summary = (summary or plain[:280] or article.summary or "").strip()
    article.content = plain or article_summary
    if article_summary:
        article.summary = article_summary
    article.status = "UPDATED"
    if author is not None:
        article.author = author
    article.save()

    try:
        odt_bytes = markdown_to_document(
            article.content,
            title=article.title,
            output_format="odt",
            engine="auto",
        )
        article.odt_file.save(
            f"{article.slug}.odt",
            ContentFile(odt_bytes),
            save=True,
        )
    except Exception:
        if ext == ".odt":
            uploaded_file.seek(0)
            article.odt_file.save(uploaded_file.name, uploaded_file, save=True)

    return article


def regenerate_kb_article_odt(article: KBArticle, *, engine: str = "auto") -> bool:
    """Regenerate ``odt_file`` from article markdown/plain content (admin + CLI parity)."""
    body = (article.content or "").strip()
    if not body:
        return False
    try:
        odt_bytes = markdown_to_document(
            body,
            title=article.title,
            output_format="odt",
            engine=engine,
        )
        article.odt_file.save(
            f"{article.slug}.odt",
            ContentFile(odt_bytes),
            save=True,
        )
        return True
    except Exception:
        return False


def resolve_default_help_audience(request) -> str:
    return HelpAudience.OPERATOR if is_operator_help_request(request) else HelpAudience.TENANT
