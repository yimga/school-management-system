from django.contrib import admin
from config.admin import register_tenant_admin

from .models import DocumentCategory, Event, PortalFeatureItem, PendingGuardianInvite, Announcement, FormSignature, LessonPlan, LessonPlanAttachment
from .models_kb import FAQCategory, FAQ, KBCategory, KBArticle, KBArticleAttachment, KBComment, UserContribution


class DocumentCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent", "order", "is_active")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order", "name")


class PortalFeatureItemAdmin(admin.ModelAdmin):
    list_display = ("title", "feature", "category", "is_active", "created_by", "created_at")
    list_filter = ("feature", "category", "is_active")
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    autocomplete_fields = ("created_by",)
    change_form_template = "admin/portal/portalfeatureitem/change_form.html"


class PendingGuardianInviteAdmin(admin.ModelAdmin):
    list_display = (
        "token",
        "student",
        "invited_email",
        "invited_phone",
        "relationship",
        "preferred_contact",
        "is_claimed",
        "created_at",
    )
    list_filter = ("relationship", "preferred_contact", "claimed_at")
    search_fields = ("token", "invited_email", "invited_phone", "student__last_name", "student__admission_number")
    autocomplete_fields = ("student", "created_by", "guardian_user")
    readonly_fields = ("claimed_at",)


class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "banner_type", "is_active", "is_currently_active", "created_by", "created_at")
    list_filter = ("banner_type", "is_active", "created_at")
    search_fields = ("title", "message")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("created_by",)
    fieldsets = (
        ("Announcement Content", {
            "fields": ("title", "message", "banner_type")
        }),
        ("Display Settings", {
            "fields": ("is_active", "start_date", "end_date")
        }),
        ("Metadata", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    change_form_template = "admin/portal/announcement/change_form.html"


class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "start_at", "end_at", "location", "is_public", "created_at")
    list_filter = ("is_public",)
    search_fields = ("title", "description")
    ordering = ("-start_at",)


# Register all models with tenant admin only
register_tenant_admin(DocumentCategory, DocumentCategoryAdmin)
register_tenant_admin(PortalFeatureItem, PortalFeatureItemAdmin)
register_tenant_admin(Event, EventAdmin)
register_tenant_admin(PendingGuardianInvite, PendingGuardianInviteAdmin)
register_tenant_admin(Announcement, AnnouncementAdmin)


class FormSignatureAdmin(admin.ModelAdmin):
    list_display = ("form_document", "student", "parent", "status", "signed_at", "created_at")
    list_filter = ("status", "form_document", "created_at")
    search_fields = ("form_document__title", "student__admission_number", "parent__username", "parent__email")
    readonly_fields = ("signed_at", "signature_ip", "signature_user_agent", "created_at", "updated_at")
    autocomplete_fields = ("form_document", "student", "parent", "created_by")
    ordering = ("-created_at",)
    
    fieldsets = (
        ("Form & Signer", {
            "fields": ("form_document", "student", "parent")
        }),
        ("Signature Status", {
            "fields": ("status", "signed_at", "expires_at")
        }),
        ("Signature Data", {
            "fields": ("signature_data", "signature_hash", "signed_pdf"),
            "classes": ("collapse",)
        }),
        ("Audit Trail", {
            "fields": ("signature_ip", "signature_user_agent", "reminder_sent_at", "notes"),
            "classes": ("collapse",)
        }),
        ("Metadata", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )


register_tenant_admin(FormSignature, FormSignatureAdmin)


class LessonPlanAttachmentInline(admin.TabularInline):
    model = LessonPlanAttachment
    extra = 0
    fields = ("file", "label", "created_at")


class LessonPlanAdmin(admin.ModelAdmin):
    list_display = ("title", "teacher", "week_start_date", "created_at")
    list_filter = ("week_start_date",)
    search_fields = ("title", "teacher__user__username")
    autocomplete_fields = ("teacher",)
    inlines = [LessonPlanAttachmentInline]
    readonly_fields = ("created_at", "updated_at")


register_tenant_admin(LessonPlan, LessonPlanAdmin)


class FAQCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "display_order", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    ordering = ("display_order", "name")


class FAQAdmin(admin.ModelAdmin):
    list_display = ("question", "category", "status", "is_featured", "view_count", "updated_at")
    list_filter = ("status", "category", "is_featured")
    search_fields = ("question", "answer", "tags")
    ordering = ("-is_featured", "display_order", "-view_count")
    autocomplete_fields = ("submitted_by", "reviewed_by")


class KBCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent", "is_active", "display_order", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    ordering = ("display_order", "name")
    autocomplete_fields = ("parent",)


class KBArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "status", "difficulty", "is_featured", "view_count", "updated_at")
    list_filter = ("status", "difficulty", "category", "is_featured")
    search_fields = ("title", "summary", "content", "tags")
    ordering = ("-is_featured", "display_order", "-view_count")
    autocomplete_fields = ("author", "contributors", "reviewed_by", "related_articles")
    filter_horizontal = ("contributors", "related_articles")


class KBArticleAttachmentAdmin(admin.ModelAdmin):
    list_display = ("title", "article", "is_screenshot", "display_order", "created_at")
    list_filter = ("is_screenshot",)
    search_fields = ("title", "caption", "article__title")
    autocomplete_fields = ("article", "uploaded_by")
    ordering = ("article", "display_order", "-created_at")


class KBCommentAdmin(admin.ModelAdmin):
    list_display = ("article", "user", "is_approved", "is_helpful", "created_at")
    list_filter = ("is_approved", "is_helpful")
    search_fields = ("comment", "article__title", "user__username")
    autocomplete_fields = ("article", "user", "parent")
    ordering = ("-is_helpful", "-created_at")


class UserContributionAdmin(admin.ModelAdmin):
    list_display = ("user", "contribution_type", "points", "created_at")
    list_filter = ("contribution_type",)
    search_fields = ("user__username", "description")
    ordering = ("-created_at",)


register_tenant_admin(FAQCategory, FAQCategoryAdmin)
register_tenant_admin(FAQ, FAQAdmin)
register_tenant_admin(KBCategory, KBCategoryAdmin)
register_tenant_admin(KBArticle, KBArticleAdmin)
register_tenant_admin(KBArticleAttachment, KBArticleAttachmentAdmin)
register_tenant_admin(KBComment, KBCommentAdmin)
register_tenant_admin(UserContribution, UserContributionAdmin)
