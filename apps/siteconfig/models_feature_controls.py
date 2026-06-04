from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class FeatureToggleDefinition(models.Model):
    """
    Registry of configurable toggles.
    Supports global defaults plus optional per-school overrides.
    """

    class Scope(models.TextChoices):
        GLOBAL = "global", "Global only"
        SCHOOL = "school", "School override allowed"

    key = models.SlugField(max_length=120, unique=True)
    label = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.SCHOOL)
    owner = models.CharField(
        max_length=120,
        blank=True,
        help_text="Team or person responsible for this toggle (e.g. platform, product).",
    )
    source = models.CharField(
        max_length=80,
        blank=True,
        help_text="Origin of the flag (e.g. capability_registry, legacy_backend_flags).",
    )
    default_enabled = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "label", "key"]

    def __str__(self):
        return self.label or self.key


class FeatureToggleState(models.Model):
    """
    Effective toggle values.
    - school=None => global override
    - school=<id> => tenant override
    """

    definition = models.ForeignKey(
        FeatureToggleDefinition,
        on_delete=models.CASCADE,
        related_name="states",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="feature_toggle_states",
        null=True,
        blank=True,
    )
    is_enabled = models.BooleanField(default=False)
    value = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When set, this override is ignored after this time (Phase 10 — 10.2 capability expiry).",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_feature_toggle_states",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "school"],
                name="siteconfig_toggle_state_unique_definition_school",
            )
        ]
        ordering = ["definition__key", "school_id"]

    def __str__(self):
        scope = self.school.slug if self.school_id else "global"
        return f"{self.definition.key} ({scope})"


class TourStep(models.Model):
    """In-app onboarding tour step for a tenant and surface context."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="tour_steps",
        null=True,
        blank=True,
    )
    context = models.CharField(
        max_length=80,
        default="backend_dashboard",
        db_index=True,
        help_text="Tour context key, e.g. backend_dashboard, studio_os.",
    )
    code = models.CharField(
        max_length=80,
        db_index=True,
        help_text="Step id; should match a data-tour attribute when selector is blank.",
    )
    title = models.CharField(max_length=255, blank=True)
    body = models.TextField(
        blank=True,
        help_text="Optional longer copy shown in the tour tooltip.",
    )
    selector = models.CharField(
        max_length=255,
        blank=True,
        help_text="CSS selector for spotlight; defaults to [data-tour='<code>'] when blank.",
    )
    sort_order = models.PositiveIntegerField(default=0)
    roles = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional comma-separated roles (ADMIN, TEACHER, …). Empty = all roles.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["context", "sort_order", "code"]
        unique_together = [("school", "context", "code")]

    def __str__(self):
        return f"{self.context}/{self.code}: {self.title or self.code}"

    def resolved_selector(self) -> str:
        if self.selector:
            return self.selector
        return f"[data-tour='{self.code}']"


class FeatureUsageEvent(models.Model):
    """Feature-usage analytics: track_event(feature_code, school, user)."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="feature_usage_events",
        null=True,
        blank=True,
    )
    feature_code = models.CharField(max_length=80, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feature_usage_events",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "feature_code", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.feature_code} @ {self.created_at}"


class GlobalSupportTicket(models.Model):
    """
    Central support ticket from any tenant; stored in public/shared schema.
    Super-admin command center can filter by tenant, priority, region (metadata.country_code).
    Auto-prioritize by plan (e.g. Powerhouse).
    """

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        WAITING = "WAITING", "Waiting"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="global_support_tickets",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="global_support_tickets_submitted",
    )
    subject = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    internal_notes = models.TextField(
        blank=True,
        default="",
        help_text="Operator-only notes (not shown to tenants); minimize PII.",
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_support_tickets",
        help_text="Super-admin or support agent assigned to this ticket.",
    )
    tags = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="country_code, plan_slug, etc. for regional routing and filters",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    first_response_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the first agent response was recorded; used for SLA response breach.",
    )
    csat_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="1–5 satisfaction after resolution (tenant-submitted).",
    )
    csat_comment = models.TextField(blank=True, default="")
    csat_submitted_at = models.DateTimeField(null=True, blank=True)
    # v4.00.42 — incident linking. linked_to points at a parent incident (one-to-many
    # children grouping). merged_into points at the canonical "kept" ticket when this
    # one is marked a duplicate; both are nullable self-FKs.
    linked_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_children",
        help_text="Parent incident this ticket belongs to.",
    )
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_duplicates",
        help_text="Canonical ticket this one was merged into as a duplicate.",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["school"]),
            models.Index(fields=["-created_at"]),
        ]
        verbose_name = "Global support ticket"
        verbose_name_plural = "Global support tickets"

    def __str__(self):
        return f"{self.school.name}: {self.subject} ({self.status})"


class GlobalSupportTicketReply(models.Model):
    """
    Threaded conversation on a global support ticket (public schema).
    INTERNAL: operators only. SUBMITTER_VISIBLE: also shown to the tenant submitter in portal.
    """

    class Visibility(models.TextChoices):
        INTERNAL = "INTERNAL", "Operators only"
        SUBMITTER_VISIBLE = "SUBMITTER_VISIBLE", "Visible to submitter"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        GlobalSupportTicket,
        on_delete=models.CASCADE,
        related_name="thread_replies",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="global_support_ticket_replies",
    )
    body = models.TextField()
    visibility = models.CharField(
        max_length=24,
        choices=Visibility.choices,
        default=Visibility.INTERNAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["ticket", "created_at"]),
        ]
        verbose_name = "Global support ticket reply"
        verbose_name_plural = "Global support ticket replies"

    def __str__(self):
        return f"Reply on {self.ticket_id}"


class GlobalSupportTicketWebhookEndpoint(models.Model):
    """
    Optional additional HTTP subscribers for global support ticket events (public schema).
    Legacy env SUPPORT_TICKET_WEBHOOK_URL is still honored alongside active rows here.
    """

    name = models.CharField(max_length=120, blank=True, default="")
    url = models.URLField(max_length=500)
    secret = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Optional HMAC secret (same contract as SUPPORT_TICKET_WEBHOOK_SECRET).",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]
        verbose_name = "Global support ticket webhook endpoint"
        verbose_name_plural = "Global support ticket webhook endpoints"

    def __str__(self):
        return self.name or self.url[:80]


def _support_attachment_upload_to(instance, filename: str) -> str:
    """Per-ticket attachment path; UUID directories avoid collisions."""
    return f"support_tickets/{instance.ticket_id}/{filename}"


class GlobalSupportTicketAttachment(models.Model):
    """v4.00.42 — File attached to a global support ticket (image, log, doc).

    Uploaded by either the submitter (via the universal quick-create chip or
    the tenant follow-up form) or by an operator. Visible to the submitter
    when ``visible_to_submitter`` is True.
    """

    class Source(models.TextChoices):
        QUICK_CREATE = "QUICK_CREATE", "Quick-create chip"
        FOLLOW_UP = "FOLLOW_UP", "Tenant follow-up"
        OPERATOR = "OPERATOR", "Operator upload"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        GlobalSupportTicket,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_ticket_attachments",
    )
    file = models.FileField(upload_to=_support_attachment_upload_to, max_length=400)
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True, default="")
    byte_size = models.PositiveIntegerField(default=0)
    source = models.CharField(
        max_length=24,
        choices=Source.choices,
        default=Source.QUICK_CREATE,
    )
    visible_to_submitter = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["ticket", "created_at"]),
        ]
        verbose_name = "Global support ticket attachment"
        verbose_name_plural = "Global support ticket attachments"

    def __str__(self):
        return f"Attachment {self.filename} on {self.ticket_id}"


class SupportOnCallShift(models.Model):
    """v4.00.43 — On-call rotation for the support team.

    A shift covers a half-open window [starts_at, ends_at) for one user. A
    primary shift is used to route new tickets and breach alerts; secondary
    shifts are backups paged when the primary doesn't respond within the
    response-SLA window. Multiple shifts can be active at once (primary +
    backup); helpers prefer the most-recent primary.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_on_call_shifts",
    )
    role_tag = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text="Optional grouping (e.g. 'platform', 'billing').",
    )
    is_primary = models.BooleanField(default=True, db_index=True)
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField(db_index=True)
    notes = models.CharField(max_length=240, blank=True, default="")  # magic-number-allow: charfield-max-length
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-starts_at", "-id"]
        indexes = [
            models.Index(fields=["starts_at", "ends_at"]),
            models.Index(fields=["is_primary", "starts_at"]),
        ]
        verbose_name = "Support on-call shift"
        verbose_name_plural = "Support on-call shifts"

    def __str__(self):
        return f"{self.user_id} {'PRIMARY' if self.is_primary else 'BACKUP'} {self.starts_at:%Y-%m-%d %H:%M}"


class PublicIncident(models.Model):
    """v4.00.43 — Operator-promoted public incident on the status page.

    Operators can promote a ``GlobalSupportTicket`` to a public incident when a
    visible outage or platform issue is acknowledged. The incident has its own
    lifecycle (investigating → identified → monitoring → resolved) and is
    rendered on the unauthenticated ``/status/`` page. Severity is independent
    of the source ticket's priority (the source ticket may stay HIGH while the
    public incident is reported as MAJOR).
    """

    class Severity(models.TextChoices):
        MINOR = "MINOR", "Minor"
        MAJOR = "MAJOR", "Major"
        CRITICAL = "CRITICAL", "Critical"

    class Status(models.TextChoices):
        INVESTIGATING = "INVESTIGATING", "Investigating"
        IDENTIFIED = "IDENTIFIED", "Identified"
        MONITORING = "MONITORING", "Monitoring"
        RESOLVED = "RESOLVED", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_ticket = models.ForeignKey(
        GlobalSupportTicket,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="public_incidents",
    )
    title = models.CharField(max_length=180)  # magic-number-allow: charfield-max-length
    summary = models.TextField(blank=True, default="")
    severity = models.CharField(
        max_length=12, choices=Severity.choices, default=Severity.MINOR
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.INVESTIGATING,
    )
    promoted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promoted_public_incidents",
    )
    started_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        indexes = [
            models.Index(fields=["status", "-started_at"]),
            models.Index(fields=["-started_at"]),
        ]
        verbose_name = "Public incident"
        verbose_name_plural = "Public incidents"

    def __str__(self):
        return f"{self.severity} {self.status}: {self.title}"


class PublicIncidentSubscription(models.Model):
    """v4.00.45+v4.00.49 — Anonymous multi-channel opt-in for public status updates.

    Subscribers receive a notification when a ``PublicIncident`` is created or
    its status changes. Double opt-in: an EMAIL subscriber clicks a confirm
    link before any incident emails ship; non-email channels (SMS / Slack /
    Discord webhook) auto-confirm at subscribe time since possession of the
    target address (phone number, webhook URL) IS the proof of intent.

    v4.00.49 — Added ``channel`` + ``address`` so SMS/Slack/Discord webhook
    targets share the same fan-out pipeline. Each (channel, address) pair is
    unique; an operator who wants both email AND Slack on the same incident
    creates two rows.

    PII boundary: ``email`` + ``address`` are stored verbatim; never logged at
    INFO level. Tokens are stored as opaque 64-char strings.
    """

    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        SLACK = "SLACK", "Slack webhook"
        DISCORD = "DISCORD", "Discord webhook"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.CharField(
        max_length=12,
        choices=Channel.choices,
        default=Channel.EMAIL,
    )
    address = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Phone (E.164) for SMS, webhook URL for Slack/Discord. EMAIL rows mirror the email field here.",
    )
    email = models.EmailField(max_length=240, blank=True, default="")  # magic-number-allow: charfield-max-length
    verification_token = models.CharField(max_length=64, unique=True)
    unsubscribe_token = models.CharField(max_length=64, unique=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
    last_alerted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(fields=["confirmed_at"]),
            models.Index(fields=["unsubscribed_at"]),
            models.Index(fields=["channel"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "address"],
                name="uniq_public_sub_channel_address",
                condition=models.Q(address__gt=""),
            ),
        ]
        verbose_name = "Public incident subscription"
        verbose_name_plural = "Public incident subscriptions"

    def __str__(self):
        return f"{self.get_channel_display()}:{self.destination} ({'live' if self.is_live else 'pending/unsub'})"

    @property
    def is_live(self) -> bool:
        return self.confirmed_at is not None and self.unsubscribed_at is None

    @property
    def destination(self) -> str:
        return self.address or self.email or ""
