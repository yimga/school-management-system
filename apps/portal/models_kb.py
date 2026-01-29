"""
FAQ and Knowledge Base Models
Supports user-contributed content with moderation workflow
"""
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from .sanitizers import sanitize_html
from apps.accounts.validators import validate_kb_attachment_file, validate_file_size_10mb

User = get_user_model()


class FAQCategory(models.Model):
    """Categories for organizing FAQ items"""
    name = models.CharField(_("Category Name"), max_length=100, unique=True)
    slug = models.SlugField(_("Slug"), max_length=100, unique=True, blank=True)
    description = models.TextField(_("Description"), blank=True)
    icon = models.CharField(_("Icon Class"), max_length=50, blank=True, help_text="CSS icon class (e.g., 'fa-question-circle')")
    display_order = models.PositiveIntegerField(_("Display Order"), default=0, help_text="Lower numbers appear first")
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("FAQ Category")
        verbose_name_plural = _("FAQ Categories")
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class FAQ(models.Model):
    """Frequently Asked Questions with support for user contributions"""
    
    STATUS_CHOICES = [
        ('DRAFT', _('Draft')),
        ('PENDING', _('Pending Review')),
        ('APPROVED', _('Approved')),
        ('REJECTED', _('Rejected')),
        ('ARCHIVED', _('Archived')),
    ]
    
    category = models.ForeignKey(FAQCategory, on_delete=models.CASCADE, related_name='faqs', verbose_name=_("Category"))
    question = models.CharField(_("Question"), max_length=500)
    answer = models.TextField(_("Answer"))
    answer_html = models.TextField(_("Answer (HTML)"), blank=True, help_text="Rich text answer format")
    
    # User contribution tracking
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='submitted_faqs', verbose_name=_("Submitted By"))
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_faqs', verbose_name=_("Reviewed By"))
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='APPROVED')
    rejection_reason = models.TextField(_("Rejection Reason"), blank=True)
    
    # Metadata
    tags = models.CharField(_("Tags"), max_length=500, blank=True, help_text="Comma-separated tags for search")
    view_count = models.PositiveIntegerField(_("View Count"), default=0)
    helpful_count = models.PositiveIntegerField(_("Helpful Count"), default=0)
    unhelpful_count = models.PositiveIntegerField(_("Unhelpful Count"), default=0)
    display_order = models.PositiveIntegerField(_("Display Order"), default=0)
    is_featured = models.BooleanField(_("Is Featured"), default=False, help_text="Featured FAQs appear first")
    
    # Timestamps
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    reviewed_at = models.DateTimeField(_("Reviewed At"), null=True, blank=True)

    class Meta:
        verbose_name = _("FAQ")
        verbose_name_plural = _("FAQs")
        ordering = ['-is_featured', 'display_order', '-view_count']
        indexes = [
            models.Index(fields=['status', 'category']),
            models.Index(fields=['is_featured', '-view_count']),
        ]

    def __str__(self):
        return self.question

    def save(self, *args, **kwargs):
        if self.answer:
            self.answer_html = sanitize_html(self.answer)
        super().save(*args, **kwargs)

    @property
    def helpful_percentage(self):
        """Calculate percentage of helpful votes"""
        total = self.helpful_count + self.unhelpful_count
        if total == 0:
            return 0
        return round((self.helpful_count / total) * 100, 1)

    def increment_view_count(self):
        """Increment view counter"""
        self.view_count += 1
        self.save(update_fields=['view_count'])


class KBCategory(models.Model):
    """Categories for Knowledge Base articles"""
    name = models.CharField(_("Category Name"), max_length=100, unique=True)
    slug = models.SlugField(_("Slug"), max_length=100, unique=True, blank=True)
    description = models.TextField(_("Description"), blank=True)
    icon = models.CharField(_("Icon Class"), max_length=50, blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcategories', verbose_name=_("Parent Category"))
    display_order = models.PositiveIntegerField(_("Display Order"), default=0)
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("KB Category")
        verbose_name_plural = _("KB Categories")
        ordering = ['display_order', 'name']

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def article_count(self) -> int:
        """Published article count for UI badges/lists."""
        try:
            return self.articles.filter(status="PUBLISHED").count()
        except Exception:
            return 0


class KBArticle(models.Model):
    """Knowledge Base articles with detailed how-to guides"""
    
    STATUS_CHOICES = [
        ('DRAFT', _('Draft')),
        ('PENDING', _('Pending Review')),
        ('PUBLISHED', _('Published')),
        ('UPDATED', _('Updated - Pending Review')),
        ('ARCHIVED', _('Archived')),
    ]
    
    DIFFICULTY_CHOICES = [
        ('BEGINNER', _('Beginner')),
        ('INTERMEDIATE', _('Intermediate')),
        ('ADVANCED', _('Advanced')),
    ]
    
    # Basic info
    title = models.CharField(_("Title"), max_length=200)
    slug = models.SlugField(_("Slug"), max_length=200, unique=True, blank=True)
    category = models.ForeignKey(KBCategory, on_delete=models.CASCADE, related_name='articles', verbose_name=_("Category"))
    summary = models.TextField(_("Summary"), max_length=500, help_text="Brief description for listings")
    content = models.TextField(_("Content"), help_text="Detailed article content")
    content_html = models.TextField(_("Content (HTML)"), blank=True)
    
    # Metadata
    difficulty = models.CharField(_("Difficulty Level"), max_length=20, choices=DIFFICULTY_CHOICES, default='BEGINNER')
    estimated_read_time = models.PositiveIntegerField(_("Estimated Read Time (minutes)"), default=5)
    tags = models.CharField(_("Tags"), max_length=500, blank=True)
    related_articles = models.ManyToManyField('self', blank=True, symmetrical=False, verbose_name=_("Related Articles"))
    
    # User contribution tracking
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='kb_articles', verbose_name=_("Author"))
    contributors = models.ManyToManyField(User, blank=True, related_name='kb_contributions', verbose_name=_("Contributors"))
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_articles', verbose_name=_("Reviewed By"))
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    # Engagement metrics
    view_count = models.PositiveIntegerField(_("View Count"), default=0)
    helpful_count = models.PositiveIntegerField(_("Helpful Count"), default=0)
    unhelpful_count = models.PositiveIntegerField(_("Unhelpful Count"), default=0)
    comment_count = models.PositiveIntegerField(_("Comment Count"), default=0)
    
    # Display settings
    is_featured = models.BooleanField(_("Is Featured"), default=False)
    display_order = models.PositiveIntegerField(_("Display Order"), default=0)
    
    # Timestamps
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    published_at = models.DateTimeField(_("Published At"), null=True, blank=True)
    reviewed_at = models.DateTimeField(_("Reviewed At"), null=True, blank=True)

    class Meta:
        verbose_name = _("KB Article")
        verbose_name_plural = _("KB Articles")
        ordering = ['-is_featured', 'display_order', '-view_count']
        indexes = [
            models.Index(fields=['status', 'category']),
            models.Index(fields=['is_featured', '-view_count']),
            models.Index(fields=['-published_at']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        if self.content:
            self.content_html = sanitize_html(self.content)
        super().save(*args, **kwargs)

    @property
    def helpful_percentage(self):
        """Calculate percentage of helpful votes"""
        total = self.helpful_count + self.unhelpful_count
        if total == 0:
            return 0
        return round((self.helpful_count / total) * 100, 1)

    def increment_view_count(self):
        """Increment view counter"""
        self.view_count += 1
        self.save(update_fields=['view_count'])


class KBArticleAttachment(models.Model):
    """Screenshots and attachments for KB articles"""
    
    article = models.ForeignKey(KBArticle, on_delete=models.CASCADE, related_name='attachments', verbose_name=_("Article"))
    title = models.CharField(_("Title"), max_length=200)
    file = models.FileField(
        _("File"),
        upload_to='kb/attachments/%Y/%m/',
        validators=[validate_kb_attachment_file, validate_file_size_10mb],
    )
    file_type = models.CharField(_("File Type"), max_length=50, blank=True, help_text="e.g., image/png, application/pdf")
    file_size = models.PositiveIntegerField(_("File Size (bytes)"), default=0)
    caption = models.TextField(_("Caption"), blank=True)
    display_order = models.PositiveIntegerField(_("Display Order"), default=0)
    is_screenshot = models.BooleanField(_("Is Screenshot"), default=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name=_("Uploaded By"))
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        verbose_name = _("KB Attachment")
        verbose_name_plural = _("KB Attachments")
        ordering = ['display_order', 'created_at']

    def __str__(self):
        return f"{self.article.title} - {self.title}"


class KBComment(models.Model):
    """User comments on KB articles"""
    
    article = models.ForeignKey(KBArticle, on_delete=models.CASCADE, related_name='comments', verbose_name=_("Article"))
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("User"))
    comment = models.TextField(_("Comment"))
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies', verbose_name=_("Parent Comment"))
    is_approved = models.BooleanField(_("Is Approved"), default=False)
    is_helpful = models.BooleanField(_("Is Helpful"), default=False, help_text="Marked by moderators as particularly helpful")
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("KB Comment")
        verbose_name_plural = _("KB Comments")
        ordering = ['-is_helpful', '-created_at']

    def __str__(self):
        return f"{self.user.get_full_name()} on {self.article.title}"


class UserContribution(models.Model):
    """Track user contributions for gamification"""
    
    CONTRIBUTION_TYPES = [
        ('FAQ_SUBMIT', _('FAQ Submitted')),
        ('FAQ_APPROVE', _('FAQ Approved')),
        ('ARTICLE_SUBMIT', _('Article Submitted')),
        ('ARTICLE_APPROVE', _('Article Approved')),
        ('COMMENT', _('Comment Posted')),
        ('HELPFUL_VOTE', _('Helpful Vote')),
        ('EDIT', _('Edit/Update')),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='kb_contributions_log', verbose_name=_("User"))
    contribution_type = models.CharField(_("Contribution Type"), max_length=20, choices=CONTRIBUTION_TYPES)
    points = models.IntegerField(_("Points"), default=0)
    description = models.CharField(_("Description"), max_length=500)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        verbose_name = _("User Contribution")
        verbose_name_plural = _("User Contributions")
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.get_contribution_type_display()}"
