"""
Views for FAQ and Knowledge Base system
"""

import logging

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.http import require_POST

from apps.platform_runtime.structured_logging import (
    log_exception_with_context,
    request_context_for_log,
)

logger = logging.getLogger(__name__)

from apps.portal.kb_context import (
    filter_by_target_roles,
    filter_faqs_by_region,
    filter_faqs_for_host,
    filter_kb_articles_by_region,
    filter_kb_articles_by_school,
    filter_kb_articles_for_host,
    is_operator_help_request,
    kb_categories_for_request,
    published_kb_queryset,
)

from .models_kb import (
    FAQCategory,
    FAQ,
    HelpAudience,
    KBCategory,
    KBArticle,
    KBComment,
    UserContribution,
)


def _get_kb_region(request):
    """
    Return (country_code, plan_tier) for KB regional filtering.
    From tenant: Policy Registry only (get_effective_policy) for country_code and plan_slug.
    From public: GeoIP country_code; plan_tier None.
    """
    country_code = ""
    plan_tier = ""
    school = getattr(request, "school", None)
    if school:
        try:
            from apps.portal.runtime_helpers import get_policy_for_request

            policy = get_policy_for_request(request)
            country_code = (policy.get("country_code") or "")[:2].upper()
            if not country_code and getattr(school, "compliance_region", None):
                region = school.compliance_region
                if hasattr(region, "country_code"):
                    country_code = (region.country_code or "")[:2].upper()
            plan_tier = (policy.get("plan_slug") or "").strip().lower()
        except (ImportError, AttributeError, TypeError, KeyError):
            ctx = request_context_for_log(request) if request else {}
            log_exception_with_context(
                "portal.views_kb._get_kb_region(tenant): policy/region resolution failed",
                school_id=ctx.get("school_id"),
                tenant_id=ctx.get("tenant_id"),
                actor_id=ctx.get("actor_id"),
                route=ctx.get("route"),
            )
    else:
        try:
            from apps.compliance.access_control import get_country_from_ip

            ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[
                0
            ].strip() or request.META.get("REMOTE_ADDR", "")
            if ip:
                country_code = (get_country_from_ip(ip) or "")[:2].upper()
        except (ImportError, OSError, ConnectionError, AttributeError, TypeError):
            ctx = request_context_for_log(request) if request else {}
            log_exception_with_context(
                "portal.views_kb._get_kb_region(public): GeoIP/country resolution failed",
                school_id=ctx.get("school_id"),
                tenant_id=ctx.get("tenant_id"),
                actor_id=ctx.get("actor_id"),
                route=ctx.get("route"),
            )
    return (country_code or "", plan_tier or "")


def _published_kb_for_request(request):
    country, plan = _get_kb_region(request)
    is_op = is_operator_help_request(request)
    qs = published_kb_queryset()
    qs = filter_kb_articles_for_host(qs, is_operator=is_op)
    qs = filter_kb_articles_by_region(qs, country, plan)
    qs = filter_kb_articles_by_school(qs, request)
    qs = filter_by_target_roles(qs, request)
    from apps.portal.kb_embeddings import filter_kb_queryset_by_locale

    qs = filter_kb_queryset_by_locale(qs)
    return qs


def _approved_faq_for_request(request):
    country, plan = _get_kb_region(request)
    is_op = is_operator_help_request(request)
    qs = FAQ.objects.filter(status="APPROVED")
    qs = filter_faqs_for_host(qs, is_operator=is_op)
    qs = filter_faqs_by_region(qs, country, plan)
    qs = filter_by_target_roles(qs, request)
    return qs

def faq_list(request):
    """Display all FAQs organized by category"""
    category_slug = request.GET.get("category")
    from apps.siteconfig.list_search import (
        apply_bounded_icontains,
        normalize_list_search_query,
    )

    search_query = normalize_list_search_query(request.GET.get("q"))

    faqs = _approved_faq_for_request(request)

    if category_slug:
        faqs = faqs.filter(category__slug=category_slug)

    faqs = apply_bounded_icontains(
        faqs, search_query, "question", "answer", "tags"
    )

    categories = FAQCategory.objects.filter(is_active=True)
    featured_faqs = list(faqs.filter(is_featured=True)[:5])
    popular_faqs = list(faqs.order_by("-view_count")[:5])

    paginator = Paginator(faqs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    q = request.GET.copy()
    q.pop("page", None)
    pagination_extra_query = q.urlencode()

    context = {
        "page_obj": page_obj,
        "is_operator_help": is_operator_help_request(request),
        "categories": categories,
        "featured_faqs": featured_faqs,
        "popular_faqs": popular_faqs,
        "current_category": category_slug,
        "search_query": search_query,
        "pagination_extra_query": pagination_extra_query,
    }
    from apps.portal.operator_kb_render import render_kb_if_operator

    return render_kb_if_operator(
        request,
        portal_template="portal/faq_list.html",
        operator_body_template="portal/operator/faq_list_body.html",
        context=context,
        page_title="FAQ",
    )


def faq_detail(request, faq_id):
    """Display single FAQ with vote options"""
    faq = get_object_or_404(_approved_faq_for_request(request), id=faq_id)
    faq.increment_view_count()

    related_faqs = _approved_faq_for_request(request).filter(category=faq.category).exclude(
        id=faq.id
    )[:5]

    context = {
        "faq": faq,
        "related_faqs": related_faqs,
        "is_operator_help": is_operator_help_request(request),
    }
    from apps.portal.operator_kb_render import render_kb_if_operator

    return render_kb_if_operator(
        request,
        portal_template="portal/faq_detail.html",
        operator_body_template="portal/operator/faq_detail_body.html",
        context=context,
        page_title=faq.question[:80],
        breadcrumb_tail=[
            {
                "label": "FAQ",
                "url": reverse("kb:faq_list"),
                "active": False,
            },
            {"label": faq.question[:60], "url": None, "active": True},
        ],
    )


@require_POST
@login_required
def faq_vote(request, faq_id):
    """Vote on FAQ helpfulness"""
    faq = get_object_or_404(_approved_faq_for_request(request), id=faq_id)
    vote_type = request.POST.get("vote")  # 'helpful' or 'unhelpful'

    if vote_type == "helpful":
        faq.helpful_count += 1
    elif vote_type == "unhelpful":
        faq.unhelpful_count += 1
    else:
        return JsonResponse({"error": "Invalid vote type"}, status=400)

    faq.save()

    # Award points to contributor
    if faq.submitted_by:
        UserContribution.objects.create(
            user=faq.submitted_by,
            contribution_type="HELPFUL_VOTE",
            points=1 if vote_type == "helpful" else 0,
            description=f"Received {vote_type} vote on FAQ: {faq.question[:50]}",
        )

    return JsonResponse(
        {
            "helpful_count": faq.helpful_count,
            "unhelpful_count": faq.unhelpful_count,
            "helpful_percentage": faq.helpful_percentage,
        }
    )


@login_required
def faq_submit(request):
    """Submit a new FAQ"""
    if request.method == "POST":
        category_id = request.POST.get("category")
        question = request.POST.get("question")
        answer = request.POST.get("answer")
        tags = request.POST.get("tags", "")

        if category_id and question and answer:
            category = get_object_or_404(FAQCategory, id=category_id)

            FAQ.objects.create(
                category=category,
                question=question,
                answer=answer,
                tags=tags,
                submitted_by=request.user,
                status="PENDING",
                help_audience=(HelpAudience.OPERATOR if is_operator_help_request(request) else HelpAudience.TENANT),
            )

            # Award points
            UserContribution.objects.create(
                user=request.user,
                contribution_type="FAQ_SUBMIT",
                points=5,
                description=f"Submitted FAQ: {question[:50]}",
            )

            messages.success(
                request, "Thank you! Your FAQ has been submitted for review."
            )
            return redirect("kb:faq_list")
        else:
            messages.error(request, "Please fill in all required fields.")

    categories = FAQCategory.objects.filter(is_active=True)
    context = {
        "categories": categories,
        "is_operator_help": is_operator_help_request(request),
    }
    return render(request, "portal/faq_submit.html", context)


def kb_home(request):
    """Knowledge Base home page"""
    country_code, plan_tier = _get_kb_region(request)
    base = _published_kb_for_request(request)
    featured_articles = base.filter(is_featured=True)[:6]
    recent_articles = base.order_by("-published_at")[:10]
    popular_articles = base.order_by("-view_count")[:10]
    categories = kb_categories_for_request(request, country_code, plan_tier)

    context = {
        "featured_articles": featured_articles,
        "recent_articles": recent_articles,
        "popular_articles": popular_articles,
        "categories": categories,
        "is_operator_help": is_operator_help_request(request),
    }
    from apps.portal.operator_kb_render import render_kb_if_operator

    return render_kb_if_operator(
        request,
        portal_template="portal/kb_home.html",
        operator_body_template="portal/operator/kb_home_body.html",
        context=context,
        page_title="Knowledge base",
    )


def kb_category(request, category_slug):
    """Display articles in a category"""
    category = get_object_or_404(
        filter_by_target_roles(
            KBCategory.objects.filter(is_active=True), request
        ),
        slug=category_slug,
    )

    articles = _published_kb_for_request(request).filter(category=category).order_by(
        "-is_featured", "display_order", "-view_count"
    )

    subcategories = category.subcategories.filter(is_active=True)

    paginator = Paginator(articles, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    q = request.GET.copy()
    q.pop("page", None)
    pagination_extra_query = q.urlencode()

    context = {
        "category": category,
        "page_obj": page_obj,
        "subcategories": subcategories,
        "pagination_extra_query": pagination_extra_query,
        "is_operator_help": is_operator_help_request(request),
    }
    from apps.portal.operator_kb_render import render_kb_if_operator

    return render_kb_if_operator(
        request,
        portal_template="portal/kb_category.html",
        operator_body_template="portal/operator/kb_category_body.html",
        context=context,
        page_title=category.name,
    )


def kb_article(request, article_slug):
    """Display single KB article"""
    article = get_object_or_404(
        _published_kb_for_request(request), slug=article_slug
    )
    article.increment_view_count()

    # Get approved comments
    comments = article.comments.filter(is_approved=True, parent=None).prefetch_related(
        "replies"
    )

    # Related articles
    related_articles = article.related_articles.filter(
        pk__in=_published_kb_for_request(request).values_list("pk", flat=True)
    )[:4]
    if not related_articles.exists():
        related_articles = (
            _published_kb_for_request(request)
            .filter(category=article.category)
            .exclude(id=article.id)[:4]
        )

    context = {
        "article": article,
        "comments": comments,
        "related_articles": related_articles,
        "is_operator_help": is_operator_help_request(request),
    }
    from apps.portal.operator_kb_render import render_kb_if_operator

    return render_kb_if_operator(
        request,
        portal_template="portal/kb_article.html",
        operator_body_template="portal/operator/kb_article_body.html",
        context=context,
        page_title=article.title,
    )


def kb_article_download_odt(request, article_slug):
    """Download KB article as LibreOffice ODT (same visibility as viewing the article)."""
    article = get_object_or_404(
        _published_kb_for_request(request), slug=article_slug
    )
    if not article.odt_file:
        return redirect("kb:kb_article", article_slug=article_slug)
    try:
        f = article.odt_file.open("rb")
        response = FileResponse(f, as_attachment=True, filename=f"{article.slug}.odt")
        response["Content-Type"] = "application/vnd.oasis.opendocument.text"
        return response
    except (OSError, ValueError, TypeError) as e:
        ctx = request_context_for_log(request) if request else {}
        log_exception_with_context(
            "portal.views_kb.kb_article_download_odt: file open/stream failed",
            school_id=ctx.get("school_id"),
            tenant_id=ctx.get("tenant_id"),
            actor_id=ctx.get("actor_id"),
            route=ctx.get("route"),
            extra={"article_slug": article_slug, "error": str(e)},
        )
        logger.warning("kb_article_download_odt failed for %s: %s", article_slug, e)
        return redirect("kb:kb_article", article_slug=article_slug)


def kb_article_download_docx(request, article_slug):
    """Download KB article as Word DOCX (converted from ODT via LibreOffice headless)."""
    article = get_object_or_404(
        _published_kb_for_request(request), slug=article_slug
    )
    if not article.odt_file:
        return redirect("kb:kb_article", article_slug=article_slug)
    import tempfile
    import os
    from .document_service import convert_document

    path = None
    try:
        if hasattr(article.odt_file, "path") and os.path.isfile(article.odt_file.path):
            path = article.odt_file.path
        else:
            with tempfile.NamedTemporaryFile(suffix=".odt", delete=False) as tmp:
                tmp.write(article.odt_file.read())
                path = tmp.name
        docx_bytes = convert_document(path, target="docx", family="writer")
        response = HttpResponse(
            docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = f'attachment; filename="{article.slug}.docx"'
        return response
    except RuntimeError:
        return redirect("kb:kb_article", article_slug=article_slug)
    except (OSError, IOError, ValueError, TypeError):
        ctx = request_context_for_log(request) if request else {}
        log_exception_with_context(
            "portal.views_kb.kb_article_download_docx: document conversion or stream failed",
            school_id=ctx.get("school_id"),
            tenant_id=ctx.get("tenant_id"),
            actor_id=ctx.get("actor_id"),
            route=ctx.get("route"),
            extra={"article_slug": article_slug},
        )
        return redirect("kb:kb_article", article_slug=article_slug)
    finally:
        if path and path != getattr(article.odt_file, "path", None):
            try:
                os.unlink(path)
            except OSError:
                pass


def kb_article_download_pdf(request, article_slug):
    """Download KB article as PDF (converted from ODT via LibreOffice headless). Same visibility as article."""
    article = get_object_or_404(_published_kb_for_request(request), slug=article_slug)
    if not article.odt_file:
        return redirect("kb:kb_article", article_slug=article_slug)
    import tempfile
    import os
    from .document_service import convert_document

    path = None
    try:
        if hasattr(article.odt_file, "path") and os.path.isfile(article.odt_file.path):
            path = article.odt_file.path
        else:
            with tempfile.NamedTemporaryFile(suffix=".odt", delete=False) as tmp:
                tmp.write(article.odt_file.read())
                path = tmp.name
        pdf_bytes = convert_document(path, target="pdf", family="writer")
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{article.slug}.pdf"'
        return response
    except RuntimeError:
        return redirect("kb:kb_article", article_slug=article_slug)
    except (OSError, ValueError, TypeError) as e:
        ctx = request_context_for_log(request) if request else {}
        log_exception_with_context(
            "portal.views_kb.kb_article_download_pdf: document conversion or stream failed",
            school_id=ctx.get("school_id"),
            tenant_id=ctx.get("tenant_id"),
            actor_id=ctx.get("actor_id"),
            route=ctx.get("route"),
            extra={"article_slug": article_slug, "error": str(e)},
        )
        logger.warning("kb_article_download_pdf failed for %s: %s", article_slug, e)
        return redirect("kb:kb_article", article_slug=article_slug)
    finally:
        if path and path != getattr(article.odt_file, "path", None):
            try:
                os.unlink(path)
            except OSError:
                pass


@require_POST
@login_required
def kb_article_vote(request, article_slug):
    """Vote on article helpfulness"""
    article = get_object_or_404(_published_kb_for_request(request), slug=article_slug)
    vote_type = request.POST.get("vote")

    if vote_type == "helpful":
        article.helpful_count += 1
    elif vote_type == "unhelpful":
        article.unhelpful_count += 1
    else:
        return JsonResponse({"error": "Invalid vote type"}, status=400)

    article.save()

    # Award points to author
    if article.author:
        UserContribution.objects.create(
            user=article.author,
            contribution_type="HELPFUL_VOTE",
            points=2 if vote_type == "helpful" else 0,
            description=f"Received {vote_type} vote on article: {article.title[:50]}",
        )

    return JsonResponse(
        {
            "helpful_count": article.helpful_count,
            "unhelpful_count": article.unhelpful_count,
            "helpful_percentage": article.helpful_percentage,
        }
    )


@require_POST
@login_required
def kb_comment_add(request, article_slug):
    """Add a comment to an article"""
    article = get_object_or_404(_published_kb_for_request(request), slug=article_slug)
    comment_text = request.POST.get("comment")
    parent_id = request.POST.get("parent_id")

    if comment_text:
        parent_comment = None
        if parent_id:
            parent_comment = get_object_or_404(KBComment, id=parent_id)

        KBComment.objects.create(
            article=article,
            user=request.user,
            comment=comment_text,
            parent=parent_comment,
            is_approved=False,  # Requires moderation
        )

        # Award points
        UserContribution.objects.create(
            user=request.user,
            contribution_type="COMMENT",
            points=1,
            description=f"Commented on article: {article.title[:50]}",
        )

        messages.success(
            request, "Thank you! Your comment has been submitted for approval."
        )
    else:
        messages.error(request, "Comment cannot be empty.")

    return redirect("kb:kb_article", article_slug=article_slug)


@login_required
def kb_article_submit(request):
    """Submit a new KB article"""
    if request.method == "POST":
        category_id = request.POST.get("category")
        title = request.POST.get("title")
        summary = request.POST.get("summary")
        content = request.POST.get("content")
        difficulty = request.POST.get("difficulty", "BEGINNER")
        tags = request.POST.get("tags", "")

        if category_id and title and summary and content:
            category = get_object_or_404(KBCategory, id=category_id)

            KBArticle.objects.create(
                category=category,
                title=title,
                summary=summary,
                content=content,
                difficulty=difficulty,
                tags=tags,
                author=request.user,
                status="PENDING",
                help_audience=(HelpAudience.OPERATOR if is_operator_help_request(request) else HelpAudience.TENANT),
            )

            # Award points
            UserContribution.objects.create(
                user=request.user,
                contribution_type="ARTICLE_SUBMIT",
                points=20,
                description=f"Submitted article: {title[:50]}",
            )

            messages.success(
                request, "Thank you! Your article has been submitted for review."
            )
            return redirect("kb:kb_home")
        else:
            messages.error(request, "Please fill in all required fields.")

    categories = filter_by_target_roles(KBCategory.objects.filter(is_active=True), request)
    context = {
        "categories": categories,
        "is_operator_help": is_operator_help_request(request),
    }
    return render(request, "portal/kb_article_submit.html", context)


def kb_search(request):
    """Search knowledge base (Move 4 — ranked results via kb_search service)."""
    from apps.siteconfig.list_search import (
        apply_bounded_icontains,
        normalize_list_search_query,
    )

    query = normalize_list_search_query(request.GET.get("q"))
    if not query:
        return redirect("kb:kb_home")
    from apps.portal.kb_search import search_kb_articles

    base_qs = _published_kb_for_request(request)
    persona = (request.GET.get("persona") or "").strip().upper()
    if persona:
        base_qs = base_qs.filter(target_roles__contains=[persona])
    ranked = search_kb_articles(base_qs, query, limit=100)
    # Preserve the legacy QuerySet API for the existing template / paginator,
    # but order by relevance.
    if ranked:
        ids = [a.pk for a, _score in ranked]
        # Postgres `preserve order` trick: use Case/When; cross-db, use a Python sort post-fetch.
        articles = list(base_qs.filter(pk__in=ids))
        position = {pk: i for i, pk in enumerate(ids)}
        articles.sort(key=lambda a: position.get(a.pk, 10_000))
    else:
        articles = apply_bounded_icontains(
            base_qs, query, "title", "summary", "content", "tags"
        )

    faqs = apply_bounded_icontains(
        _approved_faq_for_request(request),
        query,
        "question",
        "answer",
        "tags",
    )

    paginator_articles = Paginator(articles, 10)
    paginator_faqs = Paginator(faqs, 10)

    articles_page = paginator_articles.get_page(request.GET.get("articles_page"))
    faqs_page = paginator_faqs.get_page(request.GET.get("faqs_page"))

    try:
        from apps.portal.help_search_intelligence import log_help_search

        article_count = articles_page.paginator.count if hasattr(articles_page, "paginator") else len(articles)
        log_help_search(
            request,
            query=query,
            result_count=article_count + (faqs_page.paginator.count if hasattr(faqs_page, "paginator") else 0),
        )
    except Exception:
        pass

    context = {
        "query": query,
        "persona": persona,
        "articles_page": articles_page,
        "faqs_page": faqs_page,
        "is_operator_help": is_operator_help_request(request),
    }
    from apps.portal.operator_kb_render import render_kb_if_operator

    return render_kb_if_operator(
        request,
        portal_template="portal/kb_search.html",
        operator_body_template="portal/operator/kb_search_body.html",
        context=context,
        page_title="Search",
    )


@login_required
def user_contributions(request):
    """Display user's contributions and points"""
    contributions = UserContribution.objects.filter(user=request.user)
    total_points = sum(c.points for c in contributions)

    # Count by type
    contribution_stats = {}
    for contrib_type, _ in UserContribution.CONTRIBUTION_TYPES:
        count = contributions.filter(contribution_type=contrib_type).count()
        points = sum(
            c.points for c in contributions.filter(contribution_type=contrib_type)
        )
        contribution_stats[contrib_type] = {"count": count, "points": points}

    # User's FAQs and articles
    user_faqs = FAQ.objects.filter(submitted_by=request.user)
    user_articles = published_kb_queryset().filter(author=request.user)

    context = {
        "total_points": total_points,
        "contribution_stats": contribution_stats,
        "user_faqs": user_faqs,
        "user_articles": user_articles,
        "recent_contributions": contributions[:20],
    }
    return render(request, "portal/user_contributions.html", context)
