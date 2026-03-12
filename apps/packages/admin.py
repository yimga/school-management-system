from django.contrib import admin

from config.admin import register_platform_admin

from .models import DocumentPack, ExperiencePack, InstalledPackage, PackageChangeLog, PackageVersion


class InstalledPackageAdmin(admin.ModelAdmin):
    list_display = ("package_id", "package_type", "version", "scope", "school", "apply_stage", "reconciliation_status", "is_active", "applied_at")
    list_filter = ("package_type", "scope", "apply_stage", "reconciliation_status", "is_active")
    search_fields = ("package_id", "version", "rollback_token", "school__name")
    ordering = ("-applied_at",)


class PackageVersionAdmin(admin.ModelAdmin):
    list_display = ("package_id", "version", "created_at")
    search_fields = ("package_id", "version", "changelog_summary")
    ordering = ("package_id", "-created_at")


class PackageChangeLogAdmin(admin.ModelAdmin):
    list_display = ("package_id", "version", "action", "mode", "reconciliation_status", "created_at")
    list_filter = ("action", "mode", "reconciliation_status")
    search_fields = ("package_id", "version", "rollback_token")
    ordering = ("-created_at",)


class ExperiencePackAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "theme_pack_id", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "description")
    ordering = ("name", "code")


class DocumentPackAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "description")
    ordering = ("name", "code")


register_platform_admin(InstalledPackage, InstalledPackageAdmin)
register_platform_admin(PackageVersion, PackageVersionAdmin)
register_platform_admin(PackageChangeLog, PackageChangeLogAdmin)
register_platform_admin(ExperiencePack, ExperiencePackAdmin)
register_platform_admin(DocumentPack, DocumentPackAdmin)
