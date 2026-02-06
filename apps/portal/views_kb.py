"""
Views for FAQ and Knowledge Base system
"""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.contrib import messages
from django.views.decorators.http import require_POST

from .models_kb import (
    FAQCategory, FAQ, KBCategory, KBArticle,
    KBComment, UserContribution
)


def faq_list(request):
    """Display all FAQs organized by category"""
    category_slug = request.GET.get('category')
    search_query = request.GET.get('q')
    
    faqs = FAQ.objects.filter(status='APPROVED')
    
    if category_slug:
        faqs = faqs.filter(category__slug=category_slug)
    
    if search_query:
        faqs = faqs.filter(
            Q(question__icontains=search_query) |
            Q(answer__icontains=search_query) |
            Q(tags__icontains=search_query)
        )
    
    categories = FAQCategory.objects.filter(is_active=True)
    featured_faqs = faqs.filter(is_featured=True)[:5]
    popular_faqs = faqs.order_by('-view_count')[:5]
    
    paginator = Paginator(faqs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    q = request.GET.copy()
    q.pop('page', None)
    pagination_extra_query = q.urlencode()

    context = {
        'page_obj': page_obj,
        'categories': categories,
        'featured_faqs': featured_faqs,
        'popular_faqs': popular_faqs,
        'current_category': category_slug,
        'search_query': search_query,
        'pagination_extra_query': pagination_extra_query,
    }
    return render(request, 'portal/faq_list.html', context)


def faq_detail(request, faq_id):
    """Display single FAQ with vote options"""
    faq = get_object_or_404(FAQ, id=faq_id, status='APPROVED')
    faq.increment_view_count()
    
    related_faqs = FAQ.objects.filter(
        category=faq.category, status='APPROVED'
    ).exclude(id=faq.id)[:5]
    
    context = {
        'faq': faq,
        'related_faqs': related_faqs,
    }
    return render(request, 'portal/faq_detail.html', context)


@require_POST
@login_required
def faq_vote(request, faq_id):
    """Vote on FAQ helpfulness"""
    faq = get_object_or_404(FAQ, id=faq_id)
    vote_type = request.POST.get('vote')  # 'helpful' or 'unhelpful'
    
    if vote_type == 'helpful':
        faq.helpful_count += 1
    elif vote_type == 'unhelpful':
        faq.unhelpful_count += 1
    else:
        return JsonResponse({'error': 'Invalid vote type'}, status=400)
    
    faq.save()
    
    # Award points to contributor
    if faq.submitted_by:
        UserContribution.objects.create(
            user=faq.submitted_by,
            contribution_type='HELPFUL_VOTE',
            points=1 if vote_type == 'helpful' else 0,
            description=f'Received {vote_type} vote on FAQ: {faq.question[:50]}'
        )
    
    return JsonResponse({
        'helpful_count': faq.helpful_count,
        'unhelpful_count': faq.unhelpful_count,
        'helpful_percentage': faq.helpful_percentage
    })


@login_required
def faq_submit(request):
    """Submit a new FAQ"""
    if request.method == 'POST':
        category_id = request.POST.get('category')
        question = request.POST.get('question')
        answer = request.POST.get('answer')
        tags = request.POST.get('tags', '')
        
        if category_id and question and answer:
            category = get_object_or_404(FAQCategory, id=category_id)
            
            faq = FAQ.objects.create(
                category=category,
                question=question,
                answer=answer,
                tags=tags,
                submitted_by=request.user,
                status='PENDING'
            )
            
            # Award points
            UserContribution.objects.create(
                user=request.user,
                contribution_type='FAQ_SUBMIT',
                points=5,
                description=f'Submitted FAQ: {question[:50]}'
            )
            
            messages.success(request, 'Thank you! Your FAQ has been submitted for review.')
            return redirect('portal:faq_list')
        else:
            messages.error(request, 'Please fill in all required fields.')
    
    categories = FAQCategory.objects.filter(is_active=True)
    context = {'categories': categories}
    return render(request, 'portal/faq_submit.html', context)


def kb_home(request):
    """Knowledge Base home page"""
    featured_articles = KBArticle.objects.filter(
        status='PUBLISHED', is_featured=True
    )[:6]
    
    recent_articles = KBArticle.objects.filter(
        status='PUBLISHED'
    ).order_by('-published_at')[:10]
    
    popular_articles = KBArticle.objects.filter(
        status='PUBLISHED'
    ).order_by('-view_count')[:10]
    
    categories = KBCategory.objects.filter(is_active=True, parent=None)
    
    context = {
        'featured_articles': featured_articles,
        'recent_articles': recent_articles,
        'popular_articles': popular_articles,
        'categories': categories,
    }
    return render(request, 'portal/kb_home.html', context)


def kb_category(request, category_slug):
    """Display articles in a category"""
    category = get_object_or_404(KBCategory, slug=category_slug, is_active=True)
    
    articles = KBArticle.objects.filter(
        category=category, status='PUBLISHED'
    ).order_by('-is_featured', 'display_order', '-view_count')
    
    subcategories = category.subcategories.filter(is_active=True)
    
    paginator = Paginator(articles, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    q = request.GET.copy()
    q.pop('page', None)
    pagination_extra_query = q.urlencode()

    context = {
        'category': category,
        'page_obj': page_obj,
        'subcategories': subcategories,
        'pagination_extra_query': pagination_extra_query,
    }
    return render(request, 'portal/kb_category.html', context)


def kb_article(request, article_slug):
    """Display single KB article"""
    article = get_object_or_404(KBArticle, slug=article_slug, status='PUBLISHED')
    article.increment_view_count()
    
    # Get approved comments
    comments = article.comments.filter(is_approved=True, parent=None).prefetch_related('replies')
    
    # Related articles
    related_articles = article.related_articles.filter(status='PUBLISHED')[:4]
    if not related_articles.exists():
        # Fallback to same category
        related_articles = KBArticle.objects.filter(
            category=article.category, status='PUBLISHED'
        ).exclude(id=article.id)[:4]
    
    context = {
        'article': article,
        'comments': comments,
        'related_articles': related_articles,
    }
    return render(request, 'portal/kb_article.html', context)


def kb_article_download_odt(request, article_slug):
    """Download KB article as LibreOffice ODT (same visibility as viewing the article)."""
    article = get_object_or_404(KBArticle, slug=article_slug, status='PUBLISHED')
    if not article.odt_file:
        return redirect('kb:kb_article', article_slug=article_slug)
    try:
        f = article.odt_file.open('rb')
        response = FileResponse(f, as_attachment=True, filename=f'{article.slug}.odt')
        response['Content-Type'] = 'application/vnd.oasis.opendocument.text'
        return response
    except Exception:
        return redirect('kb:kb_article', article_slug=article_slug)


def kb_article_download_pdf(request, article_slug):
    """Download KB article as PDF (converted from ODT via LibreOffice headless). Same visibility as article."""
    article = get_object_or_404(KBArticle, slug=article_slug, status='PUBLISHED')
    if not article.odt_file:
        return redirect('kb:kb_article', article_slug=article_slug)
    import tempfile
    import os
    from .document_conversion import convert_to_pdf
    path = None
    try:
        if hasattr(article.odt_file, 'path') and os.path.isfile(article.odt_file.path):
            path = article.odt_file.path
        else:
            with tempfile.NamedTemporaryFile(suffix='.odt', delete=False) as tmp:
                tmp.write(article.odt_file.read())
                path = tmp.name
        pdf_bytes = convert_to_pdf(path)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{article.slug}.pdf"'
        return response
    except RuntimeError:
        return redirect('kb:kb_article', article_slug=article_slug)
    except Exception:
        return redirect('kb:kb_article', article_slug=article_slug)
    finally:
        if path and path != getattr(article.odt_file, 'path', None):
            try:
                os.unlink(path)
            except OSError:
                pass


@require_POST
@login_required
def kb_article_vote(request, article_slug):
    """Vote on article helpfulness"""
    article = get_object_or_404(KBArticle, slug=article_slug)
    vote_type = request.POST.get('vote')
    
    if vote_type == 'helpful':
        article.helpful_count += 1
    elif vote_type == 'unhelpful':
        article.unhelpful_count += 1
    else:
        return JsonResponse({'error': 'Invalid vote type'}, status=400)
    
    article.save()
    
    # Award points to author
    if article.author:
        UserContribution.objects.create(
            user=article.author,
            contribution_type='HELPFUL_VOTE',
            points=2 if vote_type == 'helpful' else 0,
            description=f'Received {vote_type} vote on article: {article.title[:50]}'
        )
    
    return JsonResponse({
        'helpful_count': article.helpful_count,
        'unhelpful_count': article.unhelpful_count,
        'helpful_percentage': article.helpful_percentage
    })


@require_POST
@login_required
def kb_comment_add(request, article_slug):
    """Add a comment to an article"""
    article = get_object_or_404(KBArticle, slug=article_slug, status='PUBLISHED')
    comment_text = request.POST.get('comment')
    parent_id = request.POST.get('parent_id')
    
    if comment_text:
        parent_comment = None
        if parent_id:
            parent_comment = get_object_or_404(KBComment, id=parent_id)
        
        comment = KBComment.objects.create(
            article=article,
            user=request.user,
            comment=comment_text,
            parent=parent_comment,
            is_approved=False  # Requires moderation
        )
        
        # Award points
        UserContribution.objects.create(
            user=request.user,
            contribution_type='COMMENT',
            points=1,
            description=f'Commented on article: {article.title[:50]}'
        )
        
        messages.success(request, 'Thank you! Your comment has been submitted for approval.')
    else:
        messages.error(request, 'Comment cannot be empty.')
    
    return redirect('portal:kb_article', article_slug=article_slug)


@login_required
def kb_article_submit(request):
    """Submit a new KB article"""
    if request.method == 'POST':
        category_id = request.POST.get('category')
        title = request.POST.get('title')
        summary = request.POST.get('summary')
        content = request.POST.get('content')
        difficulty = request.POST.get('difficulty', 'BEGINNER')
        tags = request.POST.get('tags', '')
        
        if category_id and title and summary and content:
            category = get_object_or_404(KBCategory, id=category_id)
            
            article = KBArticle.objects.create(
                category=category,
                title=title,
                summary=summary,
                content=content,
                difficulty=difficulty,
                tags=tags,
                author=request.user,
                status='PENDING'
            )
            
            # Award points
            UserContribution.objects.create(
                user=request.user,
                contribution_type='ARTICLE_SUBMIT',
                points=20,
                description=f'Submitted article: {title[:50]}'
            )
            
            messages.success(request, 'Thank you! Your article has been submitted for review.')
            return redirect('kb:kb_home')
        else:
            messages.error(request, 'Please fill in all required fields.')
    
    categories = KBCategory.objects.filter(is_active=True)
    context = {'categories': categories}
    return render(request, 'portal/kb_article_submit.html', context)


def kb_search(request):
    """Search knowledge base"""
    query = request.GET.get('q', '')
    
    if not query:
        return redirect('kb:kb_home')
    
    # Search articles
    articles = KBArticle.objects.filter(
        status='PUBLISHED'
    ).filter(
        Q(title__icontains=query) |
        Q(summary__icontains=query) |
        Q(content__icontains=query) |
        Q(tags__icontains=query)
    )
    
    # Search FAQs
    faqs = FAQ.objects.filter(
        status='APPROVED'
    ).filter(
        Q(question__icontains=query) |
        Q(answer__icontains=query) |
        Q(tags__icontains=query)
    )
    
    paginator_articles = Paginator(articles, 10)
    paginator_faqs = Paginator(faqs, 10)
    
    articles_page = paginator_articles.get_page(request.GET.get('articles_page'))
    faqs_page = paginator_faqs.get_page(request.GET.get('faqs_page'))
    
    context = {
        'query': query,
        'articles_page': articles_page,
        'faqs_page': faqs_page,
    }
    return render(request, 'portal/kb_search.html', context)


@login_required
def user_contributions(request):
    """Display user's contributions and points"""
    contributions = UserContribution.objects.filter(user=request.user)
    total_points = sum(c.points for c in contributions)
    
    # Count by type
    contribution_stats = {}
    for contrib_type, _ in UserContribution.CONTRIBUTION_TYPES:
        count = contributions.filter(contribution_type=contrib_type).count()
        points = sum(c.points for c in contributions.filter(contribution_type=contrib_type))
        contribution_stats[contrib_type] = {'count': count, 'points': points}
    
    # User's FAQs and articles
    user_faqs = FAQ.objects.filter(submitted_by=request.user)
    user_articles = KBArticle.objects.filter(author=request.user)
    
    context = {
        'total_points': total_points,
        'contribution_stats': contribution_stats,
        'user_faqs': user_faqs,
        'user_articles': user_articles,
        'recent_contributions': contributions[:20],
    }
    return render(request, 'portal/user_contributions.html', context)
