"""School-scoped community discussion forums (batch 1357)."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class CommunityForumCategory(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="forum_categories",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = _("Forum category")
        verbose_name_plural = _("Forum categories")
        constraints = [
            models.UniqueConstraint(
                fields=["school", "slug"],
                name="uniq_forum_category_per_school",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "is_active", "display_order"]),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:120] or "category"
        super().save(*args, **kwargs)


class CommunityForumTopic(models.Model):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="forum_topics",
    )
    category = models.ForeignKey(
        CommunityForumCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="topics",
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    body = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="forum_topics_authored",
    )
    is_pinned = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    reply_count = models.PositiveIntegerField(default=0)
    last_activity_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-last_activity_at"]
        verbose_name = _("Forum topic")
        verbose_name_plural = _("Forum topics")
        constraints = [
            models.UniqueConstraint(
                fields=["school", "slug"],
                name="uniq_forum_topic_slug_per_school",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "last_activity_at"]),
            models.Index(fields=["school", "category", "last_activity_at"]),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:180] or "topic"
            self.slug = base
        super().save(*args, **kwargs)


class CommunityForumReply(models.Model):
    topic = models.ForeignKey(
        CommunityForumTopic,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="forum_replies_authored",
    )
    body = models.TextField()
    is_staff_answer = models.BooleanField(
        default=False,
        help_text=_("Marked when posted by school staff (moderator highlight)."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Forum reply")
        verbose_name_plural = _("Forum replies")
        indexes = [
            models.Index(fields=["topic", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Reply on {self.topic_id}"
