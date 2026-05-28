from __future__ import annotations

from django.conf import settings
from django.db import models


class ProductFeedback(models.Model):
    """
    Part 4.4: Public-schema feedback/feature requests for roadmap visibility.
    Tag by region and module; status (Planned / In Development / Released); optional upvotes.
    Link from roadmap or feedback form; simple admin for super-admin.

    Legacy (batch 1519): new product voice lives in ``apps.feedback`` (FeatureRequest /
    ReleaseNote). ``siteconfig.views.feedback_roadmap`` redirects to
    ``feedback:product_feedback``; keep this table for historical admin rows only.
    """

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        PLANNED = "PLANNED", "Planned"
        IN_DEVELOPMENT = "IN_DEVELOPMENT", "In Development"
        RELEASED = "RELEASED", "Released"
        WONT_DO = "WONT_DO", "Won't Do"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    region = models.CharField(
        max_length=32,
        blank=True,
        db_index=True,
        help_text="e.g. country code or regional cluster.",
    )
    module = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="e.g. admissions, finance, portal.",
    )
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.SUBMITTED, db_index=True
    )
    upvotes = models.PositiveIntegerField(default=0)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "siteconfig_productfeedback"
        ordering = ["-upvotes", "-created_at"]
        verbose_name = "Product feedback"
        verbose_name_plural = "Product feedback"

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


class MarketingContent(models.Model):
    """
    Plan 4.11: DB-driven content for marketing (CMS-lite). Key-based blobs editable in admin
    without deploy. Use for hero copy, footer, or any marketing snippet; locale optional.
    """

    key = models.CharField(
        max_length=120, db_index=True, help_text="e.g. hero_subheadline, blog_intro"
    )
    content_html = models.TextField(blank=True)
    locale = models.CharField(max_length=10, blank=True, default="", db_index=True)
    content_type = models.CharField(max_length=32, blank=True, default="html")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "siteconfig_marketingcontent"
        unique_together = [["key", "locale"]]
        ordering = ["key", "locale"]
        verbose_name = "Marketing content"
        verbose_name_plural = "Marketing content"

    def __str__(self):
        return f"{self.key} ({self.locale or 'default'})"


class BlogPost(models.Model):
    """
    Plan 4.11: Blog / News for marketing site. CMS-backed; list on /blog/, detail at /blog/<slug>/.
    """

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    excerpt = models.TextField(blank=True)
    body_html = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_published = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "siteconfig_blogpost"
        ordering = ["-published_at", "-created_at"]
        verbose_name = "Blog post"
        verbose_name_plural = "Blog posts"

    def __str__(self):
        return self.title
