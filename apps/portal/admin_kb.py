"""
Admin interfaces for FAQ and Knowledge Base system
Includes approval workflow for user-contributed content
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from .models_kb import (
    FAQCategory, FAQ, KBCategory, KBArticle,
    KBArticleAttachment, KBComment, UserContribution
)


@admin.register(FAQCategory)
class FAQCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'display_order', 'faq_count', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['display_order', 'name']
    
    def faq_count(self, obj):
        return obj.faqs.filter(status='APPROVED').count()
    faq_count.short_description = _('Published FAQs')


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = [
        'question_short', 'category', 'status', 'submitted_by',
        'view_count', 'helpful_percentage_display', 'is_featured', 'created_at'
    ]
    list_filter = ['status', 'category', 'is_featured', 'created_at']
    search_fields = ['question', 'answer', 'tags']
    readonly_fields = ['view_count', 'helpful_count', 'unhelpful_count', 'created_at', 'updated_at']
    list_editable = ['status', 'is_featured']
    actions = ['approve_faqs', 'reject_faqs', 'feature_faqs']
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('category', 'question', 'answer', 'answer_html', 'tags')
        }),
        (_('Status & Review'), {
            'fields': ('status', 'submitted_by', 'reviewed_by', 'reviewed_at', 'rejection_reason')
        }),
        (_('Display Settings'), {
            'fields': ('is_featured', 'display_order')
        }),
        (_('Engagement Metrics'), {
            'fields': ('view_count', 'helpful_count', 'unhelpful_count'),
            'classes': ('collapse',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def question_short(self, obj):
        return obj.question[:80] + '...' if len(obj.question) > 80 else obj.question
    question_short.short_description = _('Question')
    
    def helpful_percentage_display(self, obj):
        percentage = obj.helpful_percentage
        color = 'green' if percentage >= 70 else 'orange' if percentage >= 50 else 'red'
        return format_html(
            '<span style="color: {};">{} %</span>',
            color, percentage
        )
    helpful_percentage_display.short_description = _('Helpful %')
    
    def approve_faqs(self, request, queryset):
        queryset.update(
            status='APPROVED',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, _('Selected FAQs have been approved.'))
    approve_faqs.short_description = _('Approve selected FAQs')
    
    def reject_faqs(self, request, queryset):
        queryset.update(
            status='REJECTED',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, _('Selected FAQs have been rejected.'))
    reject_faqs.short_description = _('Reject selected FAQs')
    
    def feature_faqs(self, request, queryset):
        queryset.update(is_featured=True)
        self.message_user(request, _('Selected FAQs have been featured.'))
    feature_faqs.short_description = _('Feature selected FAQs')


@admin.register(KBCategory)
class KBCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'slug', 'display_order', 'target_roles_display', 'article_count', 'is_active', 'created_at']
    list_filter = ['is_active', 'parent', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['display_order', 'name']

    def target_roles_display(self, obj):
        roles = obj.target_roles if isinstance(obj.target_roles, list) else []
        return ', '.join(roles) if roles else _('All')
    target_roles_display.short_description = _('Target roles')

    def article_count(self, obj):
        return obj.articles.filter(status='PUBLISHED').count()
    article_count.short_description = _('Published Articles')


class KBArticleAttachmentInline(admin.TabularInline):
    model = KBArticleAttachment
    extra = 1
    fields = ['title', 'file', 'caption', 'is_screenshot', 'display_order']
    readonly_fields = ['file_size']


@admin.register(KBArticle)
class KBArticleAdmin(admin.ModelAdmin):
    list_display = [
        'title_short', 'category', 'status', 'difficulty', 'target_roles_display', 'author',
        'view_count', 'helpful_percentage_display', 'is_featured', 'published_at'
    ]
    list_filter = ['status', 'difficulty', 'category', 'is_featured', 'published_at', 'created_at']

    def target_roles_display(self, obj):
        roles = obj.target_roles if isinstance(obj.target_roles, list) else []
        return ', '.join(roles) if roles else _('All')
    target_roles_display.short_description = _('Target roles')
    search_fields = ['title', 'summary', 'content', 'tags']
    readonly_fields = [
        'slug', 'view_count', 'helpful_count', 'unhelpful_count',
        'comment_count', 'created_at', 'updated_at'
    ]
    list_editable = ['status', 'is_featured']
    filter_horizontal = ['related_articles', 'contributors']
    actions = ['publish_articles', 'archive_articles', 'feature_articles']
    inlines = [KBArticleAttachmentInline]
    
    fieldsets = (
        (_('Basic Information'), {
            'fields': ('title', 'slug', 'category', 'summary', 'content', 'content_html')
        }),
        (_('Metadata'), {
            'fields': ('difficulty', 'estimated_read_time', 'tags', 'related_articles')
        }),
        (_('Authorship'), {
            'fields': ('author', 'contributors', 'reviewed_by', 'reviewed_at')
        }),
        (_('Status & Publishing'), {
            'fields': ('status', 'published_at', 'is_featured', 'display_order')
        }),
        (_('Visibility by role'), {
            'fields': ('target_roles',),
            'description': _('Leave target_roles empty to show to everyone. Use ["PARENT"], ["TEACHER"], or ["PARENT", "TEACHER"] to limit visibility.')
        }),
        (_('Engagement Metrics'), {
            'fields': ('view_count', 'helpful_count', 'unhelpful_count', 'comment_count'),
            'classes': ('collapse',)
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def title_short(self, obj):
        return obj.title[:80] + '...' if len(obj.title) > 80 else obj.title
    title_short.short_description = _('Title')
    
    def helpful_percentage_display(self, obj):
        percentage = obj.helpful_percentage
        color = 'green' if percentage >= 70 else 'orange' if percentage >= 50 else 'red'
        return format_html(
            '<span style="color: {};">{} %</span>',
            color, percentage
        )
    helpful_percentage_display.short_description = _('Helpful %')
    
    def publish_articles(self, request, queryset):
        now = timezone.now()
        queryset.update(
            status='PUBLISHED',
            published_at=now,
            reviewed_by=request.user,
            reviewed_at=now
        )
        self.message_user(request, _('Selected articles have been published.'))
    publish_articles.short_description = _('Publish selected articles')
    
    def archive_articles(self, request, queryset):
        queryset.update(status='ARCHIVED')
        self.message_user(request, _('Selected articles have been archived.'))
    archive_articles.short_description = _('Archive selected articles')
    
    def feature_articles(self, request, queryset):
        queryset.update(is_featured=True)
        self.message_user(request, _('Selected articles have been featured.'))
    feature_articles.short_description = _('Feature selected articles')


@admin.register(KBArticleAttachment)
class KBArticleAttachmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'article', 'file_type', 'file_size_display', 'is_screenshot', 'uploaded_by', 'created_at']
    list_filter = ['is_screenshot', 'file_type', 'created_at']
    search_fields = ['title', 'caption', 'article__title']
    readonly_fields = ['file_size', 'file_type']
    
    def file_size_display(self, obj):
        size_kb = obj.file_size / 1024
        if size_kb < 1024:
            return f'{size_kb:.1f} KB'
        return f'{size_kb/1024:.1f} MB'
    file_size_display.short_description = _('File Size')


@admin.register(KBComment)
class KBCommentAdmin(admin.ModelAdmin):
    list_display = ['comment_short', 'article', 'user', 'is_approved', 'is_helpful', 'created_at']
    list_filter = ['is_approved', 'is_helpful', 'created_at']
    search_fields = ['comment', 'article__title', 'user__username']
    readonly_fields = ['created_at', 'updated_at']
    list_editable = ['is_approved', 'is_helpful']
    actions = ['approve_comments', 'mark_helpful']
    
    def comment_short(self, obj):
        return obj.comment[:100] + '...' if len(obj.comment) > 100 else obj.comment
    comment_short.short_description = _('Comment')
    
    def approve_comments(self, request, queryset):
        queryset.update(is_approved=True)
        self.message_user(request, _('Selected comments have been approved.'))
    approve_comments.short_description = _('Approve selected comments')
    
    def mark_helpful(self, request, queryset):
        queryset.update(is_helpful=True, is_approved=True)
        self.message_user(request, _('Selected comments have been marked as helpful.'))
    mark_helpful.short_description = _('Mark as helpful')


@admin.register(UserContribution)
class UserContributionAdmin(admin.ModelAdmin):
    list_display = ['user', 'contribution_type', 'points', 'description', 'created_at']
    list_filter = ['contribution_type', 'created_at']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'description']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
