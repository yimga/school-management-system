from django.contrib import admin
from config.admin import admin_site

from .models import PortalFeatureItem, PendingGuardianInvite, Announcement, FormSignature
from .models_kb import FAQCategory, FAQ, KBCategory, KBArticle, KBArticleAttachment, KBComment, UserContribution


class PortalFeatureItemAdmin(admin.ModelAdmin):
    list_display = ("title", "feature", "is_active", "created_by", "created_at")
    list_filter = ("feature", "is_active")
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


# Register all models with custom admin site
admin_site.register(PortalFeatureItem, PortalFeatureItemAdmin)
admin_site.register(PendingGuardianInvite, PendingGuardianInviteAdmin)
admin_site.register(Announcement, AnnouncementAdmin)


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


admin_site.register(FormSignature, FormSignatureAdmin)


@admin.register(FAQCategory, site=admin_site)
class FAQCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "display_order", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    ordering = ("display_order", "name")


@admin.register(FAQ, site=admin_site)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("question", "category", "status", "is_featured", "view_count", "updated_at")
    list_filter = ("status", "category", "is_featured")
    search_fields = ("question", "answer", "tags")
    ordering = ("-is_featured", "display_order", "-view_count")
    autocomplete_fields = ("submitted_by", "reviewed_by")


@admin.register(KBCategory, site=admin_site)
class KBCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent", "is_active", "display_order", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    ordering = ("display_order", "name")
    autocomplete_fields = ("parent",)


@admin.register(KBArticle, site=admin_site)
class KBArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "status", "difficulty", "is_featured", "view_count", "updated_at")
    list_filter = ("status", "difficulty", "category", "is_featured")
    search_fields = ("title", "summary", "content", "tags")
    ordering = ("-is_featured", "display_order", "-view_count")
    autocomplete_fields = ("author", "contributors", "reviewed_by", "related_articles")
    filter_horizontal = ("contributors", "related_articles")


@admin.register(KBArticleAttachment, site=admin_site)
class KBArticleAttachmentAdmin(admin.ModelAdmin):
    list_display = ("title", "article", "is_screenshot", "display_order", "created_at")
    list_filter = ("is_screenshot",)
    search_fields = ("title", "caption", "article__title")
    autocomplete_fields = ("article", "uploaded_by")
    ordering = ("article", "display_order", "-created_at")


@admin.register(KBComment, site=admin_site)
class KBCommentAdmin(admin.ModelAdmin):
    list_display = ("article", "user", "is_approved", "is_helpful", "created_at")
    list_filter = ("is_approved", "is_helpful")
    search_fields = ("comment", "article__title", "user__username")
    autocomplete_fields = ("article", "user", "parent")
    ordering = ("-is_helpful", "-created_at")


@admin.register(UserContribution, site=admin_site)
class UserContributionAdmin(admin.ModelAdmin):
    list_display = ("user", "contribution_type", "points", "created_at")
    list_filter = ("contribution_type",)
    search_fields = ("user__username", "description")
    ordering = ("-created_at",)
