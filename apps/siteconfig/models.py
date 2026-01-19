from django.db import models


class SiteSettings(models.Model):
    # Branding
    site_name = models.CharField(max_length=120, default="Gilead School System")
    tagline = models.CharField(max_length=200, blank=True, default="Knowledge • Technology • Excellence")
    logo = models.ImageField(upload_to="branding/", blank=True, null=True)

    # Theme
    primary_color = models.CharField(max_length=20, default="#0d6efd")
    accent_color = models.CharField(max_length=20, default="#198754")
    use_dark_mode = models.BooleanField(default=False)

    # Behavior
    maintenance_mode = models.BooleanField(default=False)

    # Feature toggles ("plugins" MVP)
    enable_parent_portal = models.BooleanField(default=True)
    enable_teacher_portal = models.BooleanField(default=True)
    enable_reports_pdf = models.BooleanField(default=True)

    class DeadlineMode(models.TextChoices):
        TERM_END = "TERM_END", "Term end date"
        CUSTOM_DEADLINE = "CUSTOM_DEADLINE", "Custom deadline"
        PUBLISH_DATE = "PUBLISH_DATE", "Publish date"

    # Analytics defaults
    top_students_default_limit = models.PositiveSmallIntegerField(default=10)
    pass_mark = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    use_promotion_rule_for_pass = models.BooleanField(default=False)
    weak_subject_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    improvement_delta_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    deadline_mode = models.CharField(
        max_length=20,
        choices=DeadlineMode.choices,
        default=DeadlineMode.TERM_END,
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Site Settings"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Integration(models.Model):
    """
    Generic external integration registry (plugin-style).
    Examples:
      - Email (SMTP/SendGrid)
      - SMS (Twilio)
      - Payments (Stripe)
      - Analytics (GA/Sentry)
    """

    PROVIDERS = [
        ("email", "Email"),
        ("sms", "SMS"),
        ("payments", "Payments"),
        ("analytics", "Analytics"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=120)
    provider = models.CharField(max_length=30, choices=PROVIDERS, default="other")
    enabled = models.BooleanField(default=False)

    # store config safely (keys, endpoints, modes) - MVP
    config = models.JSONField(default=dict, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.provider})"

