from django.contrib import admin

from config.admin import register_tenant_admin
from .models import (
    FeatureRequest,
    FeedbackAttachment,
    FeedbackComment,
    FeedbackSubmission,
    FeedbackTriageEvent,
    FeedbackVote,
    ReleaseNote,
    RoadmapItem,
    SurveyResponse,
)


class FeedbackSubmissionAdmin(admin.ModelAdmin):
    list_display = ("title", "school", "role", "category", "severity", "status", "privacy_level", "created_at")
    list_filter = ("status", "category", "severity", "privacy_level", "role", "school")
    search_fields = ("title", "description", "school__name", "user__username")
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 50
    show_full_result_count = False


class FeatureRequestAdmin(admin.ModelAdmin):
    list_display = ("title", "school", "module", "impact", "urgency", "status", "vote_count", "weighted_score")
    list_filter = ("status", "impact", "urgency", "module", "school")
    search_fields = ("title", "problem_statement", "school__name")
    readonly_fields = ("created_at", "updated_at", "vote_count", "weighted_score")
    list_per_page = 50
    show_full_result_count = False


class RoadmapItemAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "target_module", "priority_score", "tenant_visibility", "public_visibility")
    list_filter = ("status", "tenant_visibility", "public_visibility", "target_module")
    search_fields = ("title", "problem", "expected_value")


class ReleaseNoteAdmin(admin.ModelAdmin):
    list_display = ("title", "published_at", "is_public", "notify_submitters")
    list_filter = ("is_public", "notify_submitters")
    search_fields = ("title", "summary")


class BasicFeedbackAdmin(admin.ModelAdmin):
    list_per_page = 50
    show_full_result_count = False


for model, admin_class in [
    (FeedbackSubmission, FeedbackSubmissionAdmin),
    (FeatureRequest, FeatureRequestAdmin),
    (RoadmapItem, RoadmapItemAdmin),
    (ReleaseNote, ReleaseNoteAdmin),
]:
    register_tenant_admin(model, admin_class)

register_tenant_admin(FeedbackVote, BasicFeedbackAdmin)
register_tenant_admin(FeedbackComment, BasicFeedbackAdmin)
register_tenant_admin(FeedbackAttachment, BasicFeedbackAdmin)
register_tenant_admin(FeedbackTriageEvent, BasicFeedbackAdmin)
register_tenant_admin(SurveyResponse, BasicFeedbackAdmin)
