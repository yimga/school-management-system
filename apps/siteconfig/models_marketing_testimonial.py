from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class MarketingTestimonial(models.Model):
    """
    Platform-global (runmycampus.com) marketing testimonial / social-proof quote.

    Co-located with the other platform-global marketing content models
    (``BlogPost`` / ``MarketingContent`` in ``apps.siteconfig.models_marketing``);
    marketing is NOT per-tenant, so there is deliberately no ``school`` FK.

    HONESTY CONTRACT
    ----------------
    - Only REAL, owner-approved customer content may ever render publicly.
    - ``is_approved`` defaults to FALSE. Nothing reaches the marketing surface
      until an operator deliberately approves the row (admin action / edit).
      The default must be set by a human, never auto-flipped by a connector.
    - Rows created by an external connector (G2 / Capterra / Google reviews /
      etc.) arrive with ``ingested_from_source=True`` and ``is_approved=False``
      so they land in the operator approval queue and are NEVER shown until a
      person vets them. ``external_id`` supports dedupe; ``raw_payload`` keeps
      the source record for audit.
    - ``source`` always tags provenance so the surface can attribute honestly.
    """

    class Source(models.TextChoices):
        DIRECT = "DIRECT", "Direct (collected by RunMyCampus)"
        G2 = "G2", "G2"
        CAPTERRA = "CAPTERRA", "Capterra"
        GOOGLE = "GOOGLE", "Google"
        TRUSTPILOT = "TRUSTPILOT", "Trustpilot"
        LINKEDIN = "LINKEDIN", "LinkedIn"
        CASE_STUDY = "CASE_STUDY", "Case study"
        PRESS = "PRESS", "Press / media"
        OTHER = "OTHER", "Other"

    quote = models.TextField(help_text="The testimonial text, verbatim and real.")
    attribution_name = models.CharField(
        max_length=160, help_text="Person credited with the quote."
    )
    attribution_role = models.CharField(
        max_length=160,
        blank=True,
        help_text="e.g. Head of School, IT Director.",
    )
    organization_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="School / district / organization name.",
    )

    source = models.CharField(
        max_length=16,
        choices=Source.choices,
        default=Source.DIRECT,
        db_index=True,
        help_text="Where this testimonial came from (provenance tag).",
    )
    source_url = models.URLField(
        blank=True, help_text="Link to the original review / case study / press item."
    )
    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Optional 1-5 star rating from the source.",
    )

    logo_static_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="Path under static/ to the organization logo (e.g. 'marketing/logos/acme.svg').",
    )
    avatar_static_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="Path under static/ to the attribution avatar image.",
    )

    page_slugs = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Marketing page slugs this testimonial shows on, e.g. "
            '["platform-admissions"]. Empty list = eligible for any page\'s '
            "general testimonial band."
        ),
    )
    locale = models.CharField(
        max_length=10,
        default="en",
        db_index=True,
        help_text="Locale code this testimonial targets.",
    )

    is_approved = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "HONESTY GATE: nothing renders publicly until an operator approves. "
            "Must be set deliberately by a human."
        ),
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    ingested_from_source = models.BooleanField(
        default=False,
        help_text=(
            "True when an external connector created this row, so it lands in "
            "the approval queue unapproved."
        ),
    )
    external_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Source-side identifier for dedupe.",
    )
    raw_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw record from the external source, kept for audit.",
    )

    display_order = models.IntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "siteconfig_marketingtestimonial"
        ordering = ["display_order", "-created_at"]
        verbose_name = "Marketing testimonial"
        verbose_name_plural = "Marketing testimonials"

    def __str__(self):
        who = self.attribution_name or "Anonymous"
        org = f" — {self.organization_name}" if self.organization_name else ""
        return f"{who}{org} ({self.get_source_display()})"
