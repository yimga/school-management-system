from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.accounts.validators import (
    validate_file_size_10mb,
    validate_kb_attachment_file,
)


class FeedbackSubmission(models.Model):
    class SourceChannel(models.TextChoices):
        IN_APP = "in_app", "In-app feedback center"
        CONTEXTUAL = "contextual", "Contextual page widget"
        HELP_CENTER = "help_center", "Help center"
        KB_ARTICLE = "kb_article", "Knowledge base article"
        FAQ = "faq", "FAQ"
        CONTACT_US = "contact_us", "Contact us"
        SUPPORT_TICKET = "support_ticket", "Support ticket"

    class Category(models.TextChoices):
        GENERAL = "general", "General feedback"
        BUG = "bug", "Bug report"
        FEATURE = "feature", "Feature request"
        WORKFLOW = "workflow", "Workflow pain point"
        ACCESSIBILITY = "accessibility", "Accessibility issue"
        TRAINING = "training", "Training/support request"
        BILLING = "billing", "Billing/payment issue"
        DATA_IMPORT = "data_import", "Data/import issue"
        MOBILE = "mobile", "Mobile usability issue"
        OFFLINE_SYNC = "offline_sync", "Offline sync issue"
        COMMUNICATION = "communication", "Communication issue"
        LOGIN = "login", "Login issue"
        SUGGESTION = "suggestion", "Suggestion"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        NEW = "new", "New"
        TRIAGED = "triaged", "Triaged"
        NEEDS_INFO = "needs_info", "Needs info"
        ACCEPTED = "accepted", "Accepted"
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In progress"
        RELEASED = "released", "Released"
        CLOSED = "closed", "Closed"
        DECLINED = "declined", "Declined"
        DUPLICATE = "duplicate", "Duplicate"
        EXTERNAL_BLOCKED = "external_blocked", "External blocked"

    class PrivacyLevel(models.TextChoices):
        SCHOOL_PRIVATE = "school_private", "Private to school"
        RMC_PRIVATE = "rmc_private", "Visible to RunMyCampus only"
        ANON_PRODUCT = "anon_product", "Share anonymously with product team"
        PUBLIC_CANDIDATE = "public_candidate", "Public roadmap candidate"

    class Sentiment(models.TextChoices):
        POSITIVE = "positive", "Positive"
        NEUTRAL = "neutral", "Neutral"
        NEGATIVE = "negative", "Negative"
        BLOCKED = "blocked", "Blocked"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="feedback_submissions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_submissions",
    )
    role = models.CharField(max_length=32, db_index=True, blank=True)
    category = models.CharField(
        max_length=32, choices=Category.choices, default=Category.GENERAL, db_index=True
    )
    module = models.CharField(max_length=80, blank=True, db_index=True)
    route = models.CharField(max_length=255, blank=True, db_index=True)
    title = models.CharField(max_length=180)
    description = models.TextField()
    sentiment = models.CharField(
        max_length=20, choices=Sentiment.choices, default=Sentiment.NEUTRAL
    )
    severity = models.CharField(
        max_length=20, choices=Severity.choices, default=Severity.MEDIUM, db_index=True
    )
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.NEW, db_index=True
    )
    privacy_level = models.CharField(
        max_length=32,
        choices=PrivacyLevel.choices,
        default=PrivacyLevel.SCHOOL_PRIVATE,
        db_index=True,
    )
    contact_preference = models.CharField(max_length=80, blank=True)
    browser_context = models.JSONField(default=dict, blank=True)
    device_context = models.JSONField(default=dict, blank=True)
    current_action_context = models.JSONField(default=dict, blank=True)
    source_channel = models.CharField(
        max_length=32,
        choices=SourceChannel.choices,
        default=SourceChannel.IN_APP,
        db_index=True,
    )
    source_url = models.CharField(max_length=500, blank=True)
    related_kb_article = models.ForeignKey(
        "portal.KBArticle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_submissions",
    )
    related_faq = models.ForeignKey(
        "portal.FAQ",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_submissions",
    )
    related_support_ticket_id = models.CharField(max_length=64, blank=True, db_index=True)
    related_contact_request_id = models.CharField(max_length=64, blank=True, db_index=True)
    support_escalated = models.BooleanField(default=False, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_feedback_submissions",
    )
    tags = models.JSONField(default=list, blank=True)
    moderation_required = models.BooleanField(default=False)
    visible_to_school = models.BooleanField(default=True)
    duplicate_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicates",
    )
    decision_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "status", "-created_at"]),
            models.Index(fields=["role", "category", "severity"]),
        ]

    def clean(self):
        if self.status == self.Status.DECLINED and not self.decision_reason:
            raise ValidationError({"decision_reason": "Declined feedback requires a reason."})
        if self.role == "STUDENT" and self.privacy_level == self.PrivacyLevel.PUBLIC_CANDIDATE:
            raise ValidationError("Student feedback cannot be public roadmap candidate feedback.")

    def __str__(self):
        return f"{self.title} ({self.category})"


class FeatureRequest(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        TRIAGING = "triaging", "Triaging"
        UNDER_REVIEW = "under_review", "Under review"
        PLANNED = "planned", "Planned"
        IN_DISCOVERY = "in_discovery", "In discovery"
        IN_DEVELOPMENT = "in_development", "In development"
        IN_PILOT = "in_pilot", "In pilot"
        RELEASED = "released", "Released"
        DECLINED = "declined", "Declined"
        DUPLICATE = "duplicate", "Duplicate"
        NEEDS_MORE_INFO = "needs_more_info", "Needs more info"
        EXTERNAL_BLOCKED = "external_blocked", "External blocked"

    class Impact(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        BLOCKING = "blocking", "Blocking adoption"

    class Urgency(models.TextChoices):
        SOMEDAY = "someday", "Someday"
        SOON = "soon", "Soon"
        THIS_TERM = "this_term", "This term"
        IMMEDIATE = "immediate", "Immediate"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="feature_requests",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feature_requests",
    )
    source_feedback = models.ForeignKey(
        FeedbackSubmission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="converted_feature_requests",
    )
    title = models.CharField(max_length=180)
    problem_statement = models.TextField()
    proposed_solution = models.TextField(blank=True)
    current_workaround = models.TextField(blank=True)
    affected_roles = models.JSONField(default=list, blank=True)
    module = models.CharField(max_length=80, blank=True, db_index=True)
    school_type = models.CharField(max_length=80, blank=True)
    region = models.CharField(max_length=80, blank=True, db_index=True)
    impact = models.CharField(max_length=20, choices=Impact.choices, default=Impact.MEDIUM)
    urgency = models.CharField(max_length=20, choices=Urgency.choices, default=Urgency.SOON)
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.SUBMITTED, db_index=True
    )
    vote_count = models.PositiveIntegerField(default=0)
    weighted_score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    roadmap_status = models.CharField(max_length=32, blank=True, db_index=True)
    pilot_interest = models.BooleanField(default=False)
    external_blocker = models.TextField(blank=True)
    duplicate_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicates",
    )
    decision_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-weighted_score", "-created_at"]
        indexes = [
            models.Index(fields=["school", "status", "-created_at"]),
            models.Index(fields=["module", "status"]),
        ]

    def clean(self):
        if self.status == self.Status.DECLINED and not self.decision_reason:
            raise ValidationError({"decision_reason": "Declined feature requests require a reason."})

    def __str__(self):
        return self.title


class FeedbackVote(models.Model):
    class RoleWeight(models.IntegerChoices):
        STUDENT = 1, "Student vote"
        PARENT = 2, "Parent vote"
        TEACHER = 3, "Teacher vote"
        TENANT_ADMIN = 5, "Tenant admin vote"
        STRATEGIC_CUSTOMER = 8, "Strategic customer weight"
        PLATFORM_OPERATOR = 10, "Platform operator weight"

    feature_request = models.ForeignKey(
        FeatureRequest, on_delete=models.CASCADE, related_name="votes"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feedback_votes"
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="feedback_votes",
    )
    role = models.CharField(max_length=32, db_index=True)
    weight = models.PositiveSmallIntegerField(default=1)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("feature_request", "user")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id} -> {self.feature_request_id}"


class FeedbackComment(models.Model):
    feedback = models.ForeignKey(
        FeedbackSubmission,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="comments",
    )
    feature_request = models.ForeignKey(
        FeatureRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_comments",
    )
    body = models.TextField()
    internal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class FeedbackAttachment(models.Model):
    feedback = models.ForeignKey(
        FeedbackSubmission, on_delete=models.CASCADE, related_name="attachments"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    file = models.FileField(
        upload_to="feedback/%Y/%m/",
        validators=[validate_kb_attachment_file, validate_file_size_10mb],
    )
    description = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class FeedbackTriageEvent(models.Model):
    feedback = models.ForeignKey(
        FeedbackSubmission,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="triage_events",
    )
    feature_request = models.ForeignKey(
        FeatureRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="triage_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    action = models.CharField(max_length=64, db_index=True)
    from_status = models.CharField(max_length=32, blank=True)
    to_status = models.CharField(max_length=32, blank=True)
    note = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class RoadmapItem(models.Model):
    class Status(models.TextChoices):
        UNDER_REVIEW = "under_review", "Under Review"
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In Progress"
        PILOT = "pilot", "Pilot"
        RELEASED = "released", "Released"
        DECLINED = "declined", "Declined"
        EXTERNAL_BLOCKED = "external_blocked", "External Blocked"

    title = models.CharField(max_length=180)
    problem = models.TextField()
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.UNDER_REVIEW, db_index=True
    )
    target_module = models.CharField(max_length=80, blank=True, db_index=True)
    affected_roles = models.JSONField(default=list, blank=True)
    source_feedback_count = models.PositiveIntegerField(default=0)
    priority_score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    public_visibility = models.BooleanField(default=False, db_index=True)
    tenant_visibility = models.BooleanField(default=True, db_index=True)
    release_target = models.CharField(max_length=80, blank=True)
    expected_value = models.TextField(blank=True)
    pilot_schools = models.ManyToManyField("schools.School", blank=True, related_name="roadmap_pilots")
    feature_requests = models.ManyToManyField(FeatureRequest, blank=True, related_name="roadmap_items")
    external_blocker = models.TextField(blank=True)
    decision_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "-priority_score", "-created_at"]

    def clean(self):
        if self.status == self.Status.DECLINED and not self.decision_reason:
            raise ValidationError({"decision_reason": "Declined roadmap items require a reason."})

    def __str__(self):
        return self.title


class ReleaseNote(models.Model):
    title = models.CharField(max_length=180)
    summary = models.TextField()
    roadmap_item = models.ForeignKey(
        RoadmapItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="release_notes",
    )
    feature_requests = models.ManyToManyField(FeatureRequest, blank=True, related_name="release_notes")
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    is_public = models.BooleanField(default=False)
    notify_submitters = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return self.title


class SurveyResponse(models.Model):
    class SurveyType(models.TextChoices):
        CSAT = "csat", "CSAT"
        NPS = "nps", "NPS"
        CES = "ces", "Customer Effort Score"
        WORKFLOW = "workflow", "Workflow pulse"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="survey_responses",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="survey_responses",
    )
    role = models.CharField(max_length=32, db_index=True, blank=True)
    survey_type = models.CharField(max_length=20, choices=SurveyType.choices, db_index=True)
    workflow = models.CharField(max_length=80, blank=True, db_index=True)
    score = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    route = models.CharField(max_length=255, blank=True)
    browser_context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["school", "survey_type", "-created_at"])]


class SupportDeflectionEvent(models.Model):
    """Aggregate telemetry for KB deflection (no raw query text)."""

    class Outcome(models.TextChoices):
        SUGGESTED = "suggested", "Articles suggested"
        OPENED = "opened", "User opened article"
        DISMISSED = "dismissed", "User dismissed gate"
        SUBMITTED = "submitted", "Ticket submitted anyway"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="support_deflection_events",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_deflection_events",
    )
    surface = models.CharField(max_length=64, db_index=True, default="support_ticket")
    outcome = models.CharField(max_length=32, choices=Outcome.choices, db_index=True)
    top_score = models.FloatField(default=0)
    article_slug = models.CharField(max_length=120, blank=True)
    query_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    is_operator = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["surface", "-created_at"],
                name="feedback_sd_surface_idx",
            ),
            models.Index(
                fields=["outcome", "-created_at"],
                name="feedback_sd_outcome_idx",
            ),
        ]

    @staticmethod
    def fingerprint(text: str) -> str:
        import hashlib

        normalized = " ".join((text or "").lower().split())[:500]
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


class HelpContentGapTask(models.Model):
    """Operator backlog for repeated zero-result help searches (batch 1354)."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ASSIGNED = "assigned", "Assigned"
        DRAFTED = "drafted", "KB draft created"
        DONE = "done", "Done"

    query_fingerprint = models.CharField(max_length=64, unique=True, db_index=True)
    hit_count = models.PositiveIntegerField(default=1)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="help_content_gap_tasks",
    )
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    note = models.TextField(blank=True)
    kb_draft_article = models.ForeignKey(
        "portal.KBArticle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="content_gap_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-hit_count", "-updated_at"]


class HelpSearchQueryLog(models.Model):
    """Zero-result and deflection analytics (fingerprinted queries)."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="help_search_logs",
    )
    query_fingerprint = models.CharField(max_length=64, db_index=True)
    result_count = models.PositiveSmallIntegerField(default=0)
    is_operator = models.BooleanField(default=False)
    locale = models.CharField(max_length=12, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class SupportAIInteractionReview(models.Model):
    """HITL queue for thumbs-down / failed support AI (no PII payload)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="support_ai_reviews",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_ai_reviews",
    )
    query_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    active_url = models.CharField(max_length=500, blank=True)
    outcome = models.CharField(max_length=64, blank=True)
    thumbs = models.CharField(max_length=16, blank=True)
    language = models.CharField(max_length=12, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    is_operator = models.BooleanField(default=False)
    note = models.TextField(blank=True, help_text="Operator resolution note (no PII).")
    kb_draft_article = models.ForeignKey(
        "portal.KBArticle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hitl_reviews",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @staticmethod
    def fingerprint(text: str) -> str:
        return SupportDeflectionEvent.fingerprint(text)


class SupportAISessionRating(models.Model):
    """Thumbs / stars after support SSE session (batch 1353, fingerprint-only)."""

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="support_ai_session_ratings",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_ai_session_ratings",
    )
    query_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    task_type = models.CharField(max_length=64, blank=True, db_index=True)
    thumbs = models.CharField(max_length=8, blank=True)
    stars = models.PositiveSmallIntegerField(null=True, blank=True)
    active_url = models.CharField(max_length=500, blank=True)
    is_operator = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
