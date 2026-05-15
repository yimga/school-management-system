from __future__ import annotations

import logging
import sys
from typing import Self

from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.db import models, connection, OperationalError, DatabaseError
from django.db.models.fields.files import FieldFile
from django.db.models.signals import post_delete, post_save
from django.apps import apps as django_apps

from apps.academics.models import HolidayCalendar  # noqa: F401
from .domain_ownership import (
    EXACT_FIELD_OWNERS,
    OWNERSHIP_DOMAINS,
    classify_site_settings_field,
    is_runtime_payload_shadow_key,
)
from apps.platform_runtime.runtime_sync_owner_filters import NON_PAYLOAD_SYNC_OWNERS

logger = logging.getLogger(__name__)

# Phase 2/7: Tenant behavior must not be sourced from this singleton directly; use runtime resolvers and
# bounded-context services. Migration plan: docs/SITECONFIG_OWNERSHIP_MIGRATION.md

from .models_constants import REPORT_CARD_TYPE_TERM

PLATFORM_DEFAULT_SITE_NAME = "RunMyCampus"
PLATFORM_DEFAULT_SCHOOL_CODE = "RMC"
PLATFORM_DEFAULT_TAGLINE = "Education management for every school."
PLATFORM_DEFAULT_REPORT_PREVIEW_EMAIL = "support@runmycampus.com"
# Empty or vendor demo seeds → platform defaults (normalization in models_support).
_DEMO_SEED_REPORT_EMAIL_DOMAIN = "".join(["g", "ilead", "tech", ".", "edu"])
PLATFORM_SCRUB_REPORT_PREVIEW_EMAIL_DOMAINS = frozenset({_DEMO_SEED_REPORT_EMAIL_DOMAIN})
PLATFORM_SCRUB_SITE_NAMES = frozenset({"", "School System"})
PLATFORM_SCRUB_SCHOOL_CODES = frozenset({"", "GIL"})
PLATFORM_SCRUB_TAGLINES = frozenset(
    {
        "",
        "Knowledge ƒ?› Technology ƒ?› Excellence",
        "Knowledge > Technology > Excellence",
    }
)
PLATFORM_SCRUB_REPORT_PREVIEW_PHONES = frozenset({"", "+237 670 000 000"})


def _tenant_upload_to(subpath):
    """
    Phase F: Return an upload_to callable that prefixes path with tenants/{school_id}/.
    Use for any FileField/ImageField on a model with a school FK to avoid cross-tenant access.
    """

    def upload_to(instance, filename):
        school_id = getattr(instance, "school_id", None)
        if school_id is None and getattr(instance, "school", None):
            school_id = getattr(instance.school, "pk", None)
        if school_id is None:
            return f"tenant_uploads/{subpath}/{filename}"
        return f"tenants/{school_id}/{subpath}/{filename}"

    return upload_to


def tenant_upload_to_waiver_requests(instance, filename):
    """Serializable upload_to for WaiverRequest.proof_file (migrations)."""
    return _tenant_upload_to("waiver_requests")(instance, filename)


from .models_support import (  # noqa: F401
    default_admin_portal_stats_config,
    default_announcement_submit_for_approval_roles,
    default_backend_feature_flags,
    default_footer_badges,
    default_footer_links,
    default_portal_announcements,
    default_portal_features,
    default_portal_quick_actions,
    default_portal_recent_grades,
    default_portal_upcoming_assessments,
    default_social_links,
)  # noqa: F401


from .models_support import (  # noqa: F401
    DashboardView,
    ThemeLayout,
    PORTAL_FEATURE_DEFAULTS,
    PORTAL_FEATURE_OPTIONS,
    build_platform_default_site_settings,
    default_dashboard_widgets,
    default_header_weather_config,
    get_dashboard_widget_choices,
    resolve_dashboard_widgets,
    filter_portal_items,
    _normalized_report_preview_email,
    _normalized_report_preview_phone,
    _normalized_school_code,
    _normalized_site_name,
    _normalized_tagline,
    _payload_bool,
    _payload_decimal,
    _payload_float,
    _payload_int,
    _payload_int_list,
    _payload_json_object,
    _payload_string,
    _payload_string_list,
    _site_settings_json_safe,
    default_delegation_role_mapping,
    default_grade_approval_roles,
    default_grade_post_roles,
    default_syllabus_approval_roles,
    get_report_card_style_owner_model,
    get_theme_pack_owner_model,
)  # noqa: F401


_SITE_SETTINGS_CACHE: models.Model | None = None
_LOCAL_COMPLIANCE_PROFILE_ID_UNSET = object()


# DEPRECATED: Prefer apps.siteconfig.config_service.get_effective_site_settings for tenant
# behavior. Use this row only for platform defaults. Removal target: post Phase 10.
class SiteSettings(models.Model):
    """Phase B slim singleton: maintenance + timestamps. Branding/theme/report FKs: PlatformGlobalBranding."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._orig_backend_feature_flags = {}

    # Phase B Batch 3: branding media + theme/report FKs live on
    # brand_experience.PlatformGlobalBranding only (see get_effective_site_settings).

    maintenance_mode = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __getattr__(self, name: str):
        """Phase B: behavioral columns removed from this table; read from RuntimeDefaults."""
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            from apps.platform_runtime.models import RuntimeDefaults
            from apps.platform_runtime.runtime_defaults_first_class import (
                RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES,
                RUNTIME_DEFAULTS_FIRST_CLASS_STRING_FIELD_NAMES,
                runtime_defaults_first_class_string_is_blank,
            )

            rt = RuntimeDefaults.get_singleton()
            if rt is not None:
                # Typed columns win over stale JSON payload (same order as resolver merge).
                if name in RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES:
                    val = getattr(rt, name, None)
                    if name in RUNTIME_DEFAULTS_FIRST_CLASS_STRING_FIELD_NAMES:
                        if val is not None and not runtime_defaults_first_class_string_is_blank(
                            val
                        ):
                            return val
                    elif val is not None:
                        return val
                pl = rt.payload if isinstance(rt.payload, dict) else {}
                if name in pl:
                    return pl[name]
        except (AttributeError, ImportError, TypeError, ValueError):
            pass
        if is_runtime_payload_shadow_key(name):
            from .models_support import virtual_site_setting_default

            return virtual_site_setting_default(name)
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    @classmethod
    def _persist_runtime_payload_updates(cls, updates: dict[str, object]) -> None:
        """Merge JSON-safe keys into RuntimeDefaults.payload (authoritative store for the slim tenant settings row)."""
        if not updates:
            return
        from apps.platform_runtime.models import RuntimeDefaults
        from apps.platform_runtime.runtime_defaults_first_class import (
            RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES,
            RUNTIME_DEFAULTS_FIRST_CLASS_STRING_FIELD_NAMES,
        )

        obj, _ = RuntimeDefaults.objects.get_or_create(pk=1, defaults={"payload": {}})
        merged = dict(obj.payload or {})
        first_class_names = set(RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES)
        update_fields = ["payload", "updated_at"]
        for key, value in updates.items():
            safe_value = _site_settings_json_safe(value)
            if key in first_class_names:
                if (
                    key in RUNTIME_DEFAULTS_FIRST_CLASS_STRING_FIELD_NAMES
                    and isinstance(safe_value, str)
                    and not safe_value.strip()
                ):
                    safe_value = None
                setattr(obj, key, safe_value)
                merged.pop(key, None)
                update_fields.append(key)
            else:
                merged[key] = safe_value
        obj.payload = merged
        obj.save(update_fields=list(dict.fromkeys(update_fields)))

    @classmethod
    def _ensure_preview_columns(cls) -> None:
        """Legacy no-op (Batch 3 removed dynamic video_background repair)."""
        return

    @classmethod
    def _run_in_public_schema_if_tenant(cls, fn):
        """Run fn() in public schema when current connection is a tenant schema (siteconfig is shared-app only)."""
        schema_name = getattr(connection, "schema_name", None)
        if schema_name and schema_name != "public":
            try:
                from django_tenants.utils import schema_context

                with schema_context("public"):
                    return fn()
            except ImportError:
                pass
        return fn()

    @classmethod
    def get_solo(cls) -> Self:
        global _SITE_SETTINGS_CACHE

        def _get_solo_impl():
            cls._ensure_preview_columns()
            if _SITE_SETTINGS_CACHE is None:
                obj, _ = cls.objects.get_or_create(pk=1)
                obj._sanitize_foreign_keys(persist=True)
                return obj
            try:
                _SITE_SETTINGS_CACHE.refresh_from_db()
                _SITE_SETTINGS_CACHE._sanitize_foreign_keys(persist=True)
                return _SITE_SETTINGS_CACHE
            except cls.DoesNotExist:
                obj, _ = cls.objects.get_or_create(pk=1)
                obj._sanitize_foreign_keys(persist=True)
                return obj
            except DatabaseError:
                return _SITE_SETTINGS_CACHE

        _SITE_SETTINGS_CACHE = cls._run_in_public_schema_if_tenant(_get_solo_impl)
        return _SITE_SETTINGS_CACHE

    def _sanitize_foreign_keys(self, *, persist: bool = False) -> list[str]:
        # Phase B Batch 3: theme/report FKs moved to PlatformGlobalBranding; sanitize there.
        return []

    def get_theme_background(self, field_name: str) -> FieldFile | None:
        target = getattr(self, field_name, None)
        if target:
            return target
        theme = self.active_theme
        if theme and hasattr(theme, field_name):
            return getattr(theme, field_name)
        return None

    def get_theme_logo_opacity(self) -> float:
        try:
            direct = self.logo_opacity
        except AttributeError:
            direct = None
        if direct not in (None, ""):
            try:
                return float(direct)
            except (TypeError, ValueError):
                pass
        theme = self.active_theme
        if theme and theme.logo_opacity not in (None, ""):
            return theme.logo_opacity
        return 0.3

    def get_theme_logo_bg_mode(self) -> str:
        try:
            mode = self.logo_background_mode
        except AttributeError:
            mode = None
        if mode:
            return mode
        theme = self.active_theme
        if theme and getattr(theme, "logo_background_mode", None):
            return theme.logo_background_mode
        return "contain"

    def _normalize_update_field_names(
        self,
        update_fields: list[str] | tuple[str, ...] | set[str] | None,
    ) -> set[str]:
        """Normalize update_fields to model field names or known runtime shadow keys."""
        normalized: set[str] = set()
        for field_name in update_fields or ():
            if not field_name:
                continue
            try:
                normalized.add(self._meta.get_field(field_name).name)
                continue
            except FieldDoesNotExist:
                pass
            if str(field_name).endswith("_id"):
                try:
                    normalized.add(self._meta.get_field(str(field_name)[:-3]).name)
                    continue
                except FieldDoesNotExist:
                    pass
            normalized_name = str(field_name).strip()
            if is_runtime_payload_shadow_key(normalized_name):
                normalized.add(normalized_name)
        return normalized

    def runtime_sync_owners(
        self,
        *,
        update_fields: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> tuple[str, ...]:
        """
        Return the owner domains that must be synced into RuntimeDefaults.

        The legacy tenant settings singleton remains the compatibility write-surface,
        but runtime-facing domains should immediately publish into RuntimeDefaults.
        """
        skip_domains = set(NON_PAYLOAD_SYNC_OWNERS)
        if update_fields is None:
            return tuple(
                owner for owner in OWNERSHIP_DOMAINS if owner not in skip_domains
            )

        owners = {
            classify_site_settings_field(field_name)
            for field_name in self._normalize_update_field_names(update_fields)
        }
        owners.difference_update(skip_domains)
        return tuple(sorted(owner for owner in owners if owner in OWNERSHIP_DOMAINS))

    def sync_runtime_defaults(
        self,
        *,
        owners: list[str] | tuple[str, ...] | set[str] | None = None,
        exclude_owners: list[str] | tuple[str, ...] | set[str] | None = None,
    ):
        """Publish the relevant siteconfig ownership domains into RuntimeDefaults."""
        effective_owners = tuple(
            owner
            for owner in (owners or ())
            if owner not in NON_PAYLOAD_SYNC_OWNERS
        )
        effective_exclude_owners = tuple(
            owner
            for owner in (exclude_owners or ())
            if owner not in NON_PAYLOAD_SYNC_OWNERS
        )
        if owners is not None and not effective_owners:
            return None
        try:
            from apps.platform_runtime.models import RuntimeDefaults

            return RuntimeDefaults.sync_from_site_settings(
                self,
                owners=effective_owners or None,
                exclude_owners=effective_exclude_owners or None,
            )
        except (
            AttributeError,
            ImportError,
            LookupError,
            OperationalError,
            DatabaseError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            return None

    def save(self, *args, **kwargs):
        before = getattr(self, "_orig_backend_feature_flags", {}) or {}
        _bf = getattr(self, "backend_feature_flags", None)
        after = _bf if isinstance(_bf, dict) else {}
        changed_opt_in = before.get("require_guardian_finance_opt_in") != after.get(
            "require_guardian_finance_opt_in"
        )
        requested_update_fields = kwargs.get("update_fields")
        cleared_fields = self._sanitize_foreign_keys()
        if requested_update_fields is not None:
            normalized_update_fields = set(requested_update_fields)
            if cleared_fields:
                normalized_update_fields.update(cleared_fields)
                kwargs["update_fields"] = list(normalized_update_fields)
        else:
            normalized_update_fields = None

        try:
            super().save(*args, **kwargs)
        except DatabaseError as exc:
            if kwargs.get(
                "update_fields"
            ) and "update_fields did not affect any rows" in str(exc):
                retry_kwargs = dict(kwargs)
                retry_kwargs.pop("update_fields", None)
                super().save(*args, **retry_kwargs)
            else:
                raise

        if changed_opt_in:
            logger.info(
                "require_guardian_finance_opt_in changed",
                extra={
                    "from": before.get("require_guardian_finance_opt_in"),
                    "to": after.get("require_guardian_finance_opt_in"),
                },
            )

        owners_to_sync = self.runtime_sync_owners(
            update_fields=normalized_update_fields
        )
        if owners_to_sync:
            self.sync_runtime_defaults(owners=owners_to_sync)

        # Phase B Batches 4-13: bounded-context domain snapshots (policies, blueprints, etc.).
        try:
            from apps.platform_runtime.phase_b_domain_snapshots import (
                sync_phase_b_domain_snapshots_from_site,
            )

            sync_phase_b_domain_snapshots_from_site(self)
        except (
            AttributeError,
            DatabaseError,
            ImportError,
            LookupError,
            OperationalError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            pass

        self._orig_backend_feature_flags = after.copy()

    @classmethod
    def owned_field_names(
        cls,
        owner: str | None = None,
        *,
        exclude_owners: set[str] | None = None,
    ) -> list[str]:
        """Return field names on this model for an ownership domain (DB columns + Phase B virtual keys)."""
        excluded = set(exclude_owners or set())
        if owner is None:
            excluded.add("delete")
        field_names: list[str] = []
        seen: set[str] = set()
        for field in cls._meta.concrete_fields:
            name = getattr(field, "name", "")
            if not name or name == "id":
                continue
            field_owner = classify_site_settings_field(name)
            if owner and field_owner != owner:
                continue
            if field_owner in excluded:
                continue
            field_names.append(name)
            seen.add(name)
        if owner:
            for key, dom in EXACT_FIELD_OWNERS.items():
                if dom != owner or dom in excluded:
                    continue
                if key in seen:
                    continue
                field_names.append(key)
                seen.add(key)
            try:
                from apps.platform_runtime.models import RuntimeDefaults

                rt = RuntimeDefaults.get_singleton()
                pl = rt.payload if rt and isinstance(rt.payload, dict) else {}
                for key in pl:
                    if key in seen:
                        continue
                    ko = classify_site_settings_field(key)
                    if ko != owner or ko in excluded:
                        continue
                    field_names.append(key)
                    seen.add(key)
            except (AttributeError, ImportError, TypeError, ValueError):
                pass
        else:
            for key, dom in EXACT_FIELD_OWNERS.items():
                if dom in excluded:
                    continue
                if key in seen:
                    continue
                field_names.append(key)
                seen.add(key)
            try:
                from apps.platform_runtime.models import RuntimeDefaults

                rt = RuntimeDefaults.get_singleton()
                pl = rt.payload if rt and isinstance(rt.payload, dict) else {}
                for key in pl:
                    if key in seen:
                        continue
                    if classify_site_settings_field(key) in excluded:
                        continue
                    field_names.append(key)
                    seen.add(key)
            except (AttributeError, ImportError, TypeError, ValueError):
                pass
        return field_names

    def owned_payload(
        self,
        owner: str | None = None,
        *,
        exclude_owners: set[str] | None = None,
    ) -> dict[str, object]:
        """Return JSON-safe payload values filtered to one ownership domain or exclusion set."""
        runtime_defaults = None
        first_class_keys: set[str] = set()
        try:
            from apps.platform_runtime.models import RuntimeDefaults
            from apps.platform_runtime.runtime_defaults_first_class import (
                RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES,
            )

            runtime_defaults = RuntimeDefaults.get_singleton()
            first_class_keys = set(RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES)
        except Exception:
            runtime_defaults = None
            first_class_keys = set()

        if owner and owner not in OWNERSHIP_DOMAINS:
            raise ValueError(f"Unknown siteconfig ownership domain: {owner}")
        excluded = set(exclude_owners or set())
        payload: dict[str, object] = {}
        for name in self.owned_field_names(owner=owner, exclude_owners=excluded):
            if runtime_defaults is not None and name in first_class_keys:
                payload[name] = _site_settings_json_safe(getattr(runtime_defaults, name, None))
                continue
            try:
                field = self._meta.get_field(name)
            except FieldDoesNotExist:
                try:
                    value = getattr(self, name)
                except AttributeError:
                    value = None
                payload[name] = _site_settings_json_safe(value)
                continue
            attr_name = getattr(field, "attname", name)
            try:
                value = getattr(self, name, None)
            except ObjectDoesNotExist:
                value = getattr(self, attr_name, None)
            payload[name] = _site_settings_json_safe(value)
            if attr_name != name:
                payload[attr_name] = _site_settings_json_safe(
                    getattr(self, attr_name, None)
                )
        return payload

    def get_backend_feature_flags(self) -> dict[str, object]:
        """
        Return the policy-owned backend flags with defaults merged in.

        This is the compatibility read surface for runtime, admin, and context
        code while `backend_feature_flags` is being migrated out of the legacy
        tenant settings mega-model.
        """
        payload = dict(self.owned_payload(owner="policies_rules"))
        if "backend_feature_flags" in self.__dict__:
            payload["backend_feature_flags"] = _site_settings_json_safe(
                self.__dict__["backend_feature_flags"]
            )
        raw_flags = payload.get("backend_feature_flags")
        if not isinstance(raw_flags, dict):
            raw_flags = {}
        return {**default_backend_feature_flags(), **raw_flags}

    def get_preview_platform_config(self) -> dict[str, object]:
        """Return preview-platform config from the ownership-scoped payload."""
        payload = dict(self.owned_payload(owner="preview_platform"))
        for field_name in (
            "preview_mode_enabled",
            "preview_note",
            "preview_toggle_enabled",
            "preview_toggle_label",
            "preview_banner_text",
        ):
            if field_name in self.__dict__:
                payload[field_name] = _site_settings_json_safe(self.__dict__[field_name])
        return {
            "preview_mode_enabled": bool(
                payload.get(
                    "preview_mode_enabled", getattr(self, "preview_mode_enabled", False)
                )
            ),
            "preview_note": str(
                payload.get("preview_note", getattr(self, "preview_note", "")) or ""
            ),
            "preview_toggle_enabled": bool(
                payload.get(
                    "preview_toggle_enabled",
                    getattr(self, "preview_toggle_enabled", True),
                )
            ),
            "preview_toggle_label": str(
                payload.get(
                    "preview_toggle_label",
                    getattr(self, "preview_toggle_label", "Toggle preview"),
                )
                or "Toggle preview"
            ),
            "preview_banner_text": str(
                payload.get(
                    "preview_banner_text",
                    getattr(self, "preview_banner_text", ""),
                )
                or ""
            ),
        }

    def get_feature_control_settings(self) -> dict[str, object]:
        """
        Return feature-control state through owner-scoped read contracts first.

        This is the compatibility read surface for feature control views/forms
        while the legacy singleton is being decomposed.
        """
        policies_payload = dict(self.owned_payload(owner="policies_rules"))
        local_values = self.__dict__
        for field_name in (
            "portal_features",
            "notification_channels",
            "enable_parent_portal",
            "enable_teacher_portal",
            "grade_approval_enabled",
            "grade_approval_auto_validate",
            "enable_practical_assessment",
            "enable_concurrent_mark_uploads",
            "enable_offline_mode",
            "enable_whatsapp_parent_portal",
            "enable_whatsapp_staff_portal",
        ):
            if field_name in local_values:
                policies_payload[field_name] = _site_settings_json_safe(
                    local_values[field_name]
                )
        safe_payload = dict(self.owned_payload(owner="safe_platform_default"))
        if "maintenance_mode" in local_values:
            safe_payload["maintenance_mode"] = _site_settings_json_safe(
                local_values["maintenance_mode"]
            )
        reports_payload = dict(self.owned_payload(owner="reports"))
        for field_name in (
            "enable_reports_pdf",
            "report_downloads_enabled",
            "reports_require_approved_grades_before_publish",
            "reports_use_approved_grades_only",
        ):
            if field_name in local_values:
                reports_payload[field_name] = _site_settings_json_safe(
                    local_values[field_name]
                )
        documents_payload = dict(self.owned_payload(owner="documents"))
        if "auto_tag_photos_from_exif" in local_values:
            documents_payload["auto_tag_photos_from_exif"] = _site_settings_json_safe(
                local_values["auto_tag_photos_from_exif"]
            )
        brand_payload = dict(self.owned_payload(owner="brand_experience"))
        for field_name in (
            "show_header_search",
            "show_header_notifications",
            "show_header_profile_menu",
            "show_header_theme_toggle",
        ):
            if field_name in local_values:
                brand_payload[field_name] = _site_settings_json_safe(
                    local_values[field_name]
                )
        preview_settings = self.get_preview_platform_config()

        raw_portal_features = _payload_json_object(
            policies_payload,
            self,
            "portal_features",
        )
        portal_features = default_portal_features()
        portal_features.update(
            {
                str(key): bool(value)
                for key, value in raw_portal_features.items()
                if isinstance(key, str)
            }
        )

        return {
            "portal_features": portal_features,
            "backend_feature_flags": self.get_backend_feature_flags(),
            "notification_channels": _payload_string_list(
                policies_payload,
                self,
                "notification_channels",
            ),
            "enable_parent_portal": _payload_bool(
                policies_payload,
                self,
                "enable_parent_portal",
                False,
            ),
            "enable_teacher_portal": _payload_bool(
                policies_payload,
                self,
                "enable_teacher_portal",
                False,
            ),
            "enable_reports_pdf": _payload_bool(
                reports_payload,
                self,
                "enable_reports_pdf",
                True,
            ),
            "report_downloads_enabled": _payload_bool(
                reports_payload,
                self,
                "report_downloads_enabled",
                True,
            ),
            "grade_approval_enabled": _payload_bool(
                policies_payload,
                self,
                "grade_approval_enabled",
                False,
            ),
            "grade_approval_auto_validate": _payload_bool(
                policies_payload,
                self,
                "grade_approval_auto_validate",
                False,
            ),
            "enable_practical_assessment": _payload_bool(
                policies_payload,
                self,
                "enable_practical_assessment",
                False,
            ),
            "enable_concurrent_mark_uploads": _payload_bool(
                policies_payload,
                self,
                "enable_concurrent_mark_uploads",
                False,
            ),
            "maintenance_mode": _payload_bool(
                safe_payload,
                self,
                "maintenance_mode",
                False,
            ),
            "preview_mode_enabled": bool(
                preview_settings.get("preview_mode_enabled", False)
            ),
            "preview_note": str(preview_settings.get("preview_note", "") or ""),
            "enable_offline_mode": _payload_bool(
                policies_payload,
                self,
                "enable_offline_mode",
                False,
            ),
            "auto_tag_photos_from_exif": _payload_bool(
                documents_payload,
                self,
                "auto_tag_photos_from_exif",
                False,
            ),
            "show_header_search": _payload_bool(
                brand_payload,
                self,
                "show_header_search",
                False,
            ),
            "show_header_notifications": _payload_bool(
                brand_payload,
                self,
                "show_header_notifications",
                False,
            ),
            "show_header_profile_menu": _payload_bool(
                brand_payload,
                self,
                "show_header_profile_menu",
                False,
            ),
            "show_header_theme_toggle": _payload_bool(
                brand_payload,
                self,
                "show_header_theme_toggle",
                False,
            ),
            "enable_whatsapp_parent_portal": _payload_bool(
                policies_payload,
                self,
                "enable_whatsapp_parent_portal",
                False,
            ),
            "enable_whatsapp_staff_portal": _payload_bool(
                policies_payload,
                self,
                "enable_whatsapp_staff_portal",
                False,
            ),
            "reports_require_approved_grades_before_publish": _payload_bool(
                reports_payload,
                self,
                "reports_require_approved_grades_before_publish",
                False,
            ),
            "reports_use_approved_grades_only": _payload_bool(
                reports_payload,
                self,
                "reports_use_approved_grades_only",
                False,
            ),
        }

    def apply_feature_control_state(
        self,
        *,
        portal_features: dict[str, object] | None = None,
        backend_feature_flags: dict[str, object] | None = None,
        field_updates: dict[str, object],
    ) -> None:
        """
        Apply feature-control changes through one model-level write contract.

        This keeps console write semantics centralized while the legacy
        fields on this model are still being migrated into owner-scoped domains.

        When ``portal_features`` or ``backend_feature_flags`` are omitted, those
        keys are not written to :class:`~apps.platform_runtime.models.RuntimeDefaults`
        payload, so existing stored JSON (including non-boolean portal keys) is
        preserved. Callers that only adjust concrete model fields or a few
        payload-owned keys should omit the full portal/backend maps unless they
        intend to replace them.
        """
        payload_updates: dict[str, object] = {}
        if portal_features is not None:
            payload_updates["portal_features"] = dict(portal_features)
        if backend_feature_flags is not None:
            payload_updates["backend_feature_flags"] = dict(backend_feature_flags)
        concrete = {
            f.name
            for f in type(self)._meta.concrete_fields
            if not getattr(f, "primary_key", False)
        }
        save_fields: list[str] = []
        for field_name, value in field_updates.items():
            if field_name in concrete:
                setattr(self, field_name, value)
                save_fields.append(field_name)
            else:
                payload_updates[field_name] = value

        if payload_updates:
            type(self)._persist_runtime_payload_updates(payload_updates)
        if save_fields and getattr(self, "pk", None):
            self.save(update_fields=list(dict.fromkeys(save_fields + ["updated_at"])))
        elif save_fields and not getattr(self, "pk", None):
            # Effective-settings copy or unsent row: payload already merged into RuntimeDefaults.
            pass
        elif payload_updates and getattr(self, "pk", None):
            self.save(update_fields=["updated_at"])

    def get_notification_delivery_settings(self) -> dict[str, object]:
        """
        Return delivery-channel and sender defaults through owner-scoped surfaces.

        Feature toggles and enabled channels belong to policy/feature control,
        while sender identity belongs to marketplace/integration governance.
        """
        feature_settings = self.get_feature_control_settings()
        integration_settings = self.get_marketplace_integration_settings()
        return {
            "notification_channels": list(
                feature_settings.get("notification_channels") or []
            ),
            "email_from_address": str(
                integration_settings.get(
                    "email_from_address",
                    getattr(self, "email_from_address", ""),
                )
                or ""
            ),
        }

    def get_offline_runtime_settings(self) -> dict[str, object]:
        """
        Return offline runtime controls through the policy owner surface first.
        """
        payload = dict(self.owned_payload(owner="policies_rules"))
        local_values = self.__dict__
        for field_name in (
            "enable_offline_mode",
            "offline_sync_conflict_resolution",
        ):
            if field_name in local_values:
                payload[field_name] = _site_settings_json_safe(local_values[field_name])
        flags = self.get_backend_feature_flags()
        return {
            "enable_offline_mode": _payload_bool(
                payload,
                self,
                "enable_offline_mode",
                False,
            ),
            "offline_sync_conflict_resolution": _payload_string(
                payload,
                self,
                "offline_sync_conflict_resolution",
                "show_both",
            ).lower(),
            "backend_feature_flags": flags,
        }

    def get_brand_metadata(self) -> dict[str, str]:
        """Return branding/report metadata through ownership-scoped payloads first."""
        brand_payload = dict(self.owned_payload(owner="brand_experience"))
        runtime_payload = dict(self.owned_payload(owner="runtime_blueprints"))
        registry_payload = dict(self.owned_payload(owner="global_registries"))
        local_values = self.__dict__
        for field_name in ("site_name", "tagline"):
            if field_name in local_values:
                brand_payload[field_name] = _site_settings_json_safe(local_values[field_name])
        if "school_code" in local_values:
            runtime_payload["school_code"] = _site_settings_json_safe(
                local_values["school_code"]
            )
        for field_name in ("country", "region", "ministry"):
            if field_name in local_values:
                registry_payload[field_name] = _site_settings_json_safe(
                    local_values[field_name]
                )
        return {
            "school_name": _normalized_site_name(
                brand_payload.get("site_name", getattr(self, "site_name", ""))
            ),
            "school_code": _normalized_school_code(
                runtime_payload.get("school_code", getattr(self, "school_code", ""))
            ),
            "country": str(
                registry_payload.get("country", getattr(self, "country", "")) or ""
            ),
            "region": str(
                registry_payload.get("region", getattr(self, "region", "")) or ""
            ),
            "ministry": str(
                registry_payload.get("ministry", getattr(self, "ministry", "")) or ""
            ),
            "tagline": _normalized_tagline(
                brand_payload.get("tagline", getattr(self, "tagline", ""))
            ),
        }

    def get_report_preview_settings(self) -> dict[str, object]:
        """Return report preview defaults through the reports ownership domain."""
        payload = dict(self.owned_payload(owner="reports"))
        local_values = self.__dict__
        for field_name in (
            "report_preview_contact_email",
            "report_preview_contact_phone",
            "report_preview_footer_note",
            "default_report_preview_type",
            "default_term_report_style_id",
            "default_annual_report_style_id",
        ):
            if field_name in local_values:
                payload[field_name] = _site_settings_json_safe(local_values[field_name])
        return {
            "contact_email": _normalized_report_preview_email(
                payload.get(
                    "report_preview_contact_email",
                    getattr(self, "report_preview_contact_email", ""),
                )
            ),
            "contact_phone": _normalized_report_preview_phone(
                payload.get(
                    "report_preview_contact_phone",
                    getattr(self, "report_preview_contact_phone", ""),
                )
            ),
            "footer_note": str(
                payload.get(
                    "report_preview_footer_note",
                    getattr(self, "report_preview_footer_note", ""),
                )
                or ""
            ),
            "default_report_type": str(
                payload.get(
                    "default_report_preview_type",
                    getattr(self, "default_report_preview_type", REPORT_CARD_TYPE_TERM),
                )
                or REPORT_CARD_TYPE_TERM
            ),
            "default_term_report_style_id": payload.get(
                "default_term_report_style_id",
                getattr(self, "default_term_report_style_id", None),
            ),
            "default_annual_report_style_id": payload.get(
                "default_annual_report_style_id",
                getattr(self, "default_annual_report_style_id", None),
            ),
        }

    def get_theme_experience_settings(self) -> dict[str, object]:
        """
        Return theme/experience values through ownership-scoped payloads first.

        This keeps theme studio, admin, and runtime preview paths aligned on one
        read contract while fields are migrated away from the legacy singleton.
        """
        def _payload_with_local_staged_overrides(
            owner: str,
            field_names: tuple[str, ...],
        ) -> dict[str, object]:
            payload = dict(self.owned_payload(owner=owner))
            local_values = self.__dict__
            for field_name in field_names:
                if field_name in local_values:
                    payload[field_name] = _site_settings_json_safe(local_values[field_name])
            return payload

        brand_payload = _payload_with_local_staged_overrides(
            "brand_experience",
            (
                "primary_color",
                "accent_color",
                "header_bg_color",
                "footer_bg_color",
                "success_color",
                "warning_color",
                "danger_color",
                "theme_brightness",
                "use_dark_mode",
                "theme_pack_id",
                "admin_theme_pack_id",
                "teacher_theme_pack_id",
                "parent_theme_pack_id",
                "admin_use_site_primary",
                "backend_console_theme",
                "secondary_font",
                "use_secondary_font_for_headings",
                "theme_harmony",
                # Theme system v2 (2026-05-12).
                "brand_gradient_end",
                "brand_gradient_angle",
                "neutral_palette",
                "site_logo_dark_url",
                # v2.42 (2026-05-15) warm-bright aesthetic configurability.
                "aesthetic_profile",
                "aesthetic_surface_bg",
                "aesthetic_surface_canvas",
                "aesthetic_text_primary",
                "aesthetic_accent_warm",
                "aesthetic_accent_success",
                "aesthetic_accent_danger",
                "base_font_size",
            ),
        )
        preview_payload = _payload_with_local_staged_overrides(
            "preview_platform",
            ("skip_theme_publish_guard",),
        )
        runtime_payload = _payload_with_local_staged_overrides(
            "runtime_blueprints",
            (
                "default_dashboard_view",
                "default_refresh_rate",
                "default_widgets_per_role",
            ),
        )
        reports_payload = _payload_with_local_staged_overrides(
            "reports",
            (
                "report_downloads_enabled",
                "default_term_report_style_id",
                "default_annual_report_style_id",
            ),
        )
        # PGB + runtime mirror win over reports snapshot (Batch 3).
        _term_report_style_id = getattr(self, "default_term_report_style_id", None)
        if _term_report_style_id is None:
            _term_report_style_id = reports_payload.get("default_term_report_style_id")
        _annual_report_style_id = getattr(self, "default_annual_report_style_id", None)
        if _annual_report_style_id is None:
            _annual_report_style_id = reports_payload.get(
                "default_annual_report_style_id"
            )
        return {
            "primary_color": _payload_string(
                brand_payload, self, "primary_color", "#0d6efd"
            ),
            "accent_color": _payload_string(
                brand_payload, self, "accent_color", "#198754"
            ),
            "header_bg_color": _payload_string(
                brand_payload, self, "header_bg_color", "#0f172a"
            ),
            "footer_bg_color": _payload_string(
                brand_payload, self, "footer_bg_color", "#0f172a"
            ),
            "success_color": _payload_string(
                brand_payload, self, "success_color", "#22c55e"
            ),
            "warning_color": _payload_string(
                brand_payload, self, "warning_color", "#f59e0b"
            ),
            "danger_color": _payload_string(
                brand_payload, self, "danger_color", "#ef4444"
            ),
            "theme_brightness": _payload_string(
                brand_payload, self, "theme_brightness", "light"
            ),
            "use_dark_mode": _payload_bool(brand_payload, self, "use_dark_mode", False),
            "theme_pack_id": brand_payload.get(
                "theme_pack_id", getattr(self, "theme_pack_id", None)
            ),
            "admin_theme_pack_id": brand_payload.get(
                "admin_theme_pack_id",
                getattr(self, "admin_theme_pack_id", None),
            ),
            "teacher_theme_pack_id": brand_payload.get(
                "teacher_theme_pack_id",
                getattr(self, "teacher_theme_pack_id", None),
            ),
            "parent_theme_pack_id": brand_payload.get(
                "parent_theme_pack_id",
                getattr(self, "parent_theme_pack_id", None),
            ),
            "skip_theme_publish_guard": _payload_bool(
                preview_payload,
                self,
                "skip_theme_publish_guard",
                False,
            ),
            "admin_use_site_primary": _payload_bool(
                brand_payload,
                self,
                "admin_use_site_primary",
                False,
            ),
            "backend_console_theme": _payload_string(
                brand_payload,
                self,
                "backend_console_theme",
                "",
            ),
            "secondary_font": _payload_string(
                brand_payload, self, "secondary_font", ""
            ),
            "use_secondary_font_for_headings": _payload_bool(
                brand_payload,
                self,
                "use_secondary_font_for_headings",
                False,
            ),
            "theme_harmony": _payload_string(
                brand_payload, self, "theme_harmony", "polychromatic"
            ),
            "base_font_size": _payload_int(brand_payload, self, "base_font_size", 16),
            "default_dashboard_view": _payload_string(
                runtime_payload,
                self,
                "default_dashboard_view",
                "",
            ),
            "default_refresh_rate": _payload_int(
                runtime_payload,
                self,
                "default_refresh_rate",
                60,
            ),
            "default_widgets_per_role": _payload_json_object(
                runtime_payload,
                self,
                "default_widgets_per_role",
            ),
            "report_downloads_enabled": _payload_bool(
                reports_payload,
                self,
                "report_downloads_enabled",
                True,
            ),
            "default_term_report_style_id": _term_report_style_id,
            "default_annual_report_style_id": _annual_report_style_id,
        }

    def get_report_style_selection_ids(self) -> dict[str, int | None]:
        """Return report style ids through the reports owner surface first."""
        settings = self.get_theme_experience_settings()
        return {
            "default_term_report_style_id": settings.get(
                "default_term_report_style_id"
            ),
            "default_annual_report_style_id": settings.get(
                "default_annual_report_style_id"
            ),
        }

    def get_finance_runtime_config(self) -> dict[str, object]:
        """Return finance automation, reminder, and receipt policy through the policy owner domain."""
        payload = dict(self.owned_payload(owner="policies_rules"))
        local_values = self.__dict__
        for field_name, value in local_values.items():
            if field_name.startswith("finance_"):
                payload[field_name] = _site_settings_json_safe(value)
        return {
            "auto_generate_invoices_enabled": _payload_bool(
                payload, self, "finance_auto_generate_invoices_enabled", False
            ),
            "auto_generate_schedule": _payload_json_object(
                payload, self, "finance_auto_generate_schedule"
            ),
            "auto_generate_due_date_offset_days": _payload_int(
                payload, self, "finance_auto_generate_due_date_offset_days", 30
            ),
            "auto_generate_require_approval": _payload_bool(
                payload, self, "finance_auto_generate_require_approval", False
            ),
            "fee_plan_auto_copy_enabled": _payload_bool(
                payload, self, "finance_fee_plan_auto_copy_enabled", False
            ),
            "fee_plan_auto_copy_mode": _payload_string(
                payload, self, "finance_fee_plan_auto_copy_mode", "manual"
            ).lower(),
            "fee_plan_copy_increase_percentage": _payload_decimal(
                payload, self, "finance_fee_plan_copy_increase_percentage", "0.00"
            ),
            "payment_reminder_default_channels": _payload_string_list(
                payload, self, "finance_payment_reminder_default_channels"
            ),
            "payment_reminder_default_days": _payload_int_list(
                payload, self, "finance_payment_reminder_default_days"
            ),
            "invoice_auto_status_updates_enabled": _payload_bool(
                payload, self, "finance_invoice_auto_status_updates_enabled", True
            ),
            "invoice_overdue_grace_period_days": _payload_int(
                payload, self, "finance_invoice_overdue_grace_period_days", 0
            ),
            "receipt_verification_method": _payload_string(
                payload, self, "finance_receipt_verification_method", "pattern"
            ),
            "receipt_upload_enabled": _payload_bool(
                payload, self, "finance_receipt_upload_enabled", True
            ),
            "receipt_auto_verify_enabled": _payload_bool(
                payload, self, "finance_receipt_auto_verify_enabled", True
            ),
            "receipt_max_size_mb": _payload_int(
                payload, self, "finance_receipt_max_size_mb", 5
            ),
            "receipt_allowed_extensions": _payload_string(
                payload, self, "finance_receipt_allowed_extensions", "pdf,jpg,jpeg,png"
            )
            .strip()
            .lower(),
            "receipt_idempotency_window_minutes": _payload_int(
                payload, self, "finance_receipt_idempotency_window_minutes", 10
            ),
            "receipt_auto_apply_threshold": _payload_float(
                payload, self, "finance_receipt_auto_apply_threshold", 0.9
            ),
            "receipt_auto_apply_enabled": _payload_bool(
                payload, self, "finance_receipt_auto_apply_enabled", True
            ),
            "receipt_require_admin_approval": _payload_bool(
                payload, self, "finance_receipt_require_admin_approval", False
            ),
            "receipt_amount_tolerance": _payload_decimal(
                payload, self, "finance_receipt_amount_tolerance", "1.00"
            ),
            "bank_verification_enabled": _payload_bool(
                payload, self, "finance_bank_verification_enabled", True
            ),
            "bank_verification_auto_approve": _payload_bool(
                payload, self, "finance_bank_verification_auto_approve", False
            ),
            "bank_verification_tolerance_days": _payload_int(
                payload, self, "finance_bank_verification_tolerance_days", 7
            ),
            "bank_verification_amount_tolerance": _payload_decimal(
                payload, self, "finance_bank_verification_amount_tolerance", "100.00"
            ),
            "payment_instructions_bank": _payload_string(
                payload, self, "finance_payment_instructions_bank", ""
            ),
            "payment_instructions_mtn_momo": _payload_string(
                payload, self, "finance_payment_instructions_mtn_momo", ""
            ),
            "payment_instructions_orange_money": _payload_string(
                payload, self, "finance_payment_instructions_orange_money", ""
            ),
            "payment_instructions_cash": _payload_string(
                payload, self, "finance_payment_instructions_cash", ""
            ),
            "receipt_upload_instructions": _payload_string(
                payload, self, "finance_receipt_upload_instructions", ""
            ),
            "reminder_no_contact_action": _payload_string(
                payload, self, "finance_reminder_no_contact_action", "warn_only"
            ),
            "reminder_retry_failed_hours": _payload_int(
                payload, self, "finance_reminder_retry_failed_hours", 24
            ),
            "reminder_max_retries": _payload_int(
                payload, self, "finance_reminder_max_retries", 2
            ),
        }

    def get_marketplace_integration_settings(self) -> dict[str, object]:
        """
        Return integration-owned defaults through the marketplace/integration owner domain.

        Tenant apps and tasks should read via
        ``apps.platform_runtime.helpers.get_effective_marketplace_integration_settings``;
        this method remains the implementation behind that resolver for the merged
        tenant settings façade.
        """
        payload = dict(self.owned_payload(owner="marketplace_integrations"))
        local_values = self.__dict__
        for field_name in (
            "marksheet_ocr_command",
            "marksheet_ocr_api_key",
            "sms_provider",
            "sms_api_key",
            "ai_provider_api_key",
            "whatsapp_api_token",
            "sms_sender_id",
            "email_from_address",
            "smtp_password",
            "webhook_signing_secret",
            "marketplace_partner_client_secret",
            "whatsapp_support_number",
            "whatsapp_admissions_number",
        ):
            if field_name in local_values:
                payload[field_name] = _site_settings_json_safe(local_values[field_name])
        return {
            "marksheet_ocr_command": _payload_string(
                payload, self, "marksheet_ocr_command", ""
            ),
            "marksheet_ocr_api_key": _payload_string(
                payload, self, "marksheet_ocr_api_key", ""
            ),
            "sms_provider": _payload_string(payload, self, "sms_provider", "console"),
            "sms_api_key": _payload_string(payload, self, "sms_api_key", ""),
            "ai_provider_api_key": _payload_string(
                payload, self, "ai_provider_api_key", ""
            ),
            "whatsapp_api_token": _payload_string(
                payload, self, "whatsapp_api_token", ""
            ),
            "sms_sender_id": _payload_string(
                payload, self, "sms_sender_id", "RUNMYCAMPUS"
            ),
            "email_from_address": _payload_string(
                payload, self, "email_from_address", "noreply@school.example.com"
            ),
            "smtp_password": _payload_string(payload, self, "smtp_password", ""),
            "webhook_signing_secret": _payload_string(
                payload, self, "webhook_signing_secret", ""
            ),
            "marketplace_partner_client_secret": _payload_string(
                payload, self, "marketplace_partner_client_secret", ""
            ),
            "whatsapp_support_number": _payload_string(
                payload, self, "whatsapp_support_number", ""
            ),
            "whatsapp_admissions_number": _payload_string(
                payload, self, "whatsapp_admissions_number", ""
            ),
        }

    def get_support_contact_settings(self) -> dict[str, str]:
        """Return support/contact settings through owner-scoped brand and integration surfaces."""
        brand_payload = dict(self.owned_payload(owner="brand_experience"))
        local_values = self.__dict__
        for field_name in (
            "company_phone",
            "company_email",
            "footer_whatsapp_url",
        ):
            if field_name in local_values:
                brand_payload[field_name] = _site_settings_json_safe(local_values[field_name])
        integration_settings = self.get_marketplace_integration_settings()
        return {
            "company_phone": _payload_string(
                brand_payload,
                self,
                "company_phone",
                "",
            ),
            "company_email": _payload_string(
                brand_payload,
                self,
                "company_email",
                "",
            ),
            "footer_whatsapp_url": _payload_string(
                brand_payload,
                self,
                "footer_whatsapp_url",
                "",
            ),
            "whatsapp_support_number": str(
                integration_settings.get("whatsapp_support_number", "") or ""
            ),
            "whatsapp_admissions_number": str(
                integration_settings.get("whatsapp_admissions_number", "") or ""
            ),
        }

    def get_theme_selection_ids(self) -> dict[str, int | None]:
        """Return theme-pack foreign key ids through the brand-experience ownership domain."""
        settings = self.get_theme_experience_settings()
        return {
            "theme_pack_id": settings.get("theme_pack_id"),
            "admin_theme_pack_id": settings.get("admin_theme_pack_id"),
            "teacher_theme_pack_id": settings.get("teacher_theme_pack_id"),
            "parent_theme_pack_id": settings.get("parent_theme_pack_id"),
        }

    @property
    def compliance_profile(self):
        profile_id = self.__dict__.get(
            "compliance_profile_id",
            _LOCAL_COMPLIANCE_PROFILE_ID_UNSET,
        )
        if profile_id is _LOCAL_COMPLIANCE_PROFILE_ID_UNSET:
            profile_id = None
            try:
                from apps.platform_runtime.models import RuntimeDefaults

                rd = (
                    RuntimeDefaults.objects.filter(pk=1)
                    .only("compliance_profile_id", "payload")
                    .first()
                )
                if rd is not None:
                    profile_id = rd.compliance_profile_id
                    if profile_id is None and isinstance(rd.payload, dict):
                        raw = rd.payload.get("compliance_profile_id")
                        if raw is not None:
                            try:
                                profile_id = int(raw)
                            except (TypeError, ValueError):
                                profile_id = None
            except (ImportError, OperationalError, DatabaseError):
                profile_id = None
        if not profile_id:
            self._state.fields_cache["compliance_profile"] = None
            return None
        cached = self._state.fields_cache.get("compliance_profile")
        if cached is not None and getattr(cached, "pk", None) == profile_id:
            return cached
        try:
            compliance_model = django_apps.get_model("finance", "ComplianceProfile")
        except LookupError:
            return None
        try:
            profile = compliance_model.objects.filter(pk=profile_id).first()
        except (OperationalError, DatabaseError):
            return None
        self._state.fields_cache["compliance_profile"] = profile
        return profile

    @compliance_profile.setter
    def compliance_profile(self, value):
        from apps.platform_runtime.models import RuntimeDefaults

        try:
            from apps.platform_runtime.helpers import (
                invalidate_effective_site_settings_cache,
            )
        except ImportError:  # pragma: no cover
            invalidate_effective_site_settings_cache = None

        obj, _ = RuntimeDefaults.objects.get_or_create(pk=1, defaults={"payload": {}})
        pl = dict(obj.payload or {})
        if value is None:
            pl.pop("compliance_profile_id", None)
            obj.payload = pl
            obj.compliance_profile_id = None
            obj.save(
                update_fields=["payload", "compliance_profile_id", "updated_at"]
            )
            if invalidate_effective_site_settings_cache:
                invalidate_effective_site_settings_cache()
            self._state.fields_cache["compliance_profile"] = None
            if getattr(self, "pk", None):
                self.save(update_fields=["updated_at"])
            return
        profile_id = getattr(value, "pk", value)
        pid = profile_id or None
        if pid is not None:
            try:
                pid = int(pid)
            except (TypeError, ValueError):
                pid = None
        pl.pop("compliance_profile_id", None)
        obj.compliance_profile_id = pid
        obj.payload = pl
        obj.save(update_fields=["payload", "compliance_profile_id", "updated_at"])
        if invalidate_effective_site_settings_cache:
            invalidate_effective_site_settings_cache()
        self._state.fields_cache["compliance_profile"] = (
            value if getattr(value, "pk", None) else None
        )
        if getattr(self, "pk", None):
            self.save(update_fields=["updated_at"])

    def resolve_default_report_style(
        self, report_type: str
    ) -> "ReportCardStyle | None":
        """Resolve the default report style through the owner surface first, then fallback to active defaults."""
        field_name = (
            "default_term_report_style"
            if report_type == REPORT_CARD_TYPE_TERM
            else "default_annual_report_style"
        )
        selection_ids = self.get_report_style_selection_ids()
        style_id = (
            selection_ids.get("default_term_report_style_id")
            if report_type == REPORT_CARD_TYPE_TERM
            else selection_ids.get("default_annual_report_style_id")
        )
        staged_style = self._resolve_staged_report_style(field_name, style_id)
        if staged_style:
            return staged_style
        owner_model = get_report_card_style_owner_model()
        if style_id:
            try:
                style = owner_model.objects.filter(pk=style_id).first()
            except (OperationalError, DatabaseError):
                style = None
            if style and style.is_active:
                self._state.fields_cache[field_name] = style
                return style
            if style is None:
                self._sanitize_foreign_keys(persist=True)
        try:
            return owner_model.objects.active().first()
        except (AttributeError, OperationalError, DatabaseError):
            return None

    def _resolve_staged_report_style(
        self,
        field_name: str,
        style_id: int | None,
    ) -> "ReportCardStyle | None":
        if not style_id:
            return None
        if field_name in self._state.fields_cache:
            style = self._state.fields_cache[field_name]
        elif field_name in self.__dict__:
            style = self.__dict__[field_name]
        else:
            return None
        if style is None or getattr(style, "pk", None) != style_id:
            return None
        if not getattr(style, "is_active", False):
            return None
        self._state.fields_cache[field_name] = style
        return style

    @property
    def active_theme(self) -> "ThemePack | None":
        theme_pack_model = get_theme_pack_owner_model()
        selection_ids = self.get_theme_selection_ids()
        theme_pack_id = selection_ids.get("theme_pack_id")
        staged_theme_pack = self._resolve_staged_theme_pack(
            "theme_pack",
            theme_pack_id,
        )
        if staged_theme_pack:
            return staged_theme_pack
        if theme_pack_id:
            try:
                selected = theme_pack_model.objects.filter(pk=theme_pack_id).first()
            except (OperationalError, DatabaseError):
                return None
            if selected and getattr(selected, "is_active", False):
                self._state.fields_cache["theme_pack"] = selected
                return selected
            self._sanitize_foreign_keys(persist=True)
        try:
            fallback = theme_pack_model.objects.filter(
                is_default=True, is_active=True
            ).first()
            if fallback:
                return fallback
            return (
                theme_pack_model.objects.filter(is_active=True).order_by("name").first()
            )
        except (OperationalError, DatabaseError):
            return None

    def _resolve_staged_theme_pack(
        self,
        field_name: str,
        theme_pack_id: int | None,
        *,
        applies_to_admin: bool = False,
    ) -> "ThemePack | None":
        if not theme_pack_id:
            return None
        if field_name in self._state.fields_cache:
            pack = self._state.fields_cache[field_name]
        elif field_name in self.__dict__:
            pack = self.__dict__[field_name]
        else:
            return None
        if pack is None or getattr(pack, "pk", None) != theme_pack_id:
            return None
        if not getattr(pack, "is_active", False):
            return None
        if applies_to_admin and not getattr(pack, "applies_to_admin", False):
            return None
        self._state.fields_cache[field_name] = pack
        return pack

    def apply_theme_pack(self, pack: "ThemePack", save: bool = True) -> None:
        self.theme_pack = pack
        self.theme_pack_id = getattr(pack, "pk", None)
        self.primary_color = pack.primary_color
        self.accent_color = pack.accent_color
        self.custom_css = pack.custom_css or ""
        self.brand_font = pack.font_family or getattr(
            self, "brand_font", "Inter, system-ui, sans-serif"
        )
        self._state.fields_cache["theme_pack"] = pack
        if not save:
            return
        self._persist_runtime_payload_updates(
            {
                "primary_color": self.primary_color,
                "accent_color": self.accent_color,
                "custom_css": self.custom_css,
                "brand_font": self.brand_font,
            }
        )
        try:
            from apps.brand_experience.platform_global_branding import (
                PlatformGlobalBranding,
            )

            obj, _ = PlatformGlobalBranding.objects.get_or_create(pk=1)
            obj.theme_pack = pack
            if save:
                obj.save()
        except (
            AttributeError,
            ImportError,
            OperationalError,
            DatabaseError,
            TypeError,
            ValueError,
        ):
            pass
        if save:
            self.save(update_fields=["updated_at"])

    def apply_theme_experience_state(
        self,
        *,
        field_updates: dict[str, object],
        save: bool = True,
    ) -> None:
        """
        Persist Theme Studio changes. Phase B: non-column fields go to RuntimeDefaults.payload.
        """
        allowed_fields = {
            "site_name",
            "primary_color",
            "accent_color",
            "header_bg_color",
            "footer_bg_color",
            "success_color",
            "warning_color",
            "danger_color",
            "theme_brightness",
            "use_dark_mode",
            "theme_pack",
            "admin_theme_pack",
            "teacher_theme_pack",
            "parent_theme_pack",
            "theme_harmony",
            "admin_use_site_primary",
            "skip_theme_publish_guard",
            "backend_console_theme",
            "secondary_font",
            "use_secondary_font_for_headings",
            "base_font_size",
            "default_widgets_per_role",
            "report_downloads_enabled",
            "default_dashboard_view",
            "default_refresh_rate",
            "default_term_report_style",
            "default_annual_report_style",
        }
        model_field_names = {
            f.name
            for f in type(self)._meta.concrete_fields
            if not getattr(f, "primary_key", False)
        }
        _pgb_fields = frozenset(
            {
                "theme_pack",
                "admin_theme_pack",
                "teacher_theme_pack",
                "parent_theme_pack",
                "default_term_report_style",
                "default_annual_report_style",
            }
        )
        update_fields: list[str] = []
        payload_updates: dict[str, object] = {}
        pgb = None
        for field_name, value in field_updates.items():
            if field_name not in allowed_fields:
                continue
            if field_name in _pgb_fields:
                setattr(self, field_name, value)
                setattr(self, f"{field_name}_id", getattr(value, "pk", None))
                if not save:
                    continue
                try:
                    from apps.brand_experience.platform_global_branding import (
                        PlatformGlobalBranding,
                    )

                    if pgb is None:
                        pgb, _ = PlatformGlobalBranding.objects.get_or_create(pk=1)
                    setattr(pgb, field_name, value)
                except (
                    AttributeError,
                    ImportError,
                    OperationalError,
                    DatabaseError,
                    TypeError,
                    ValueError,
                ):
                    pass
                continue
            if field_name in model_field_names:
                setattr(self, field_name, value)
                update_fields.append(field_name)
            else:
                setattr(self, field_name, value)
                if save:
                    payload_updates[field_name] = value
        if payload_updates and save:
            self._persist_runtime_payload_updates(payload_updates)
        if pgb is not None and save:
            pgb.save()
        if save and update_fields:
            self.save(update_fields=update_fields)
        elif save and getattr(self, "pk", None) and (payload_updates or pgb is not None):
            self.save(update_fields=["updated_at"])

    @property
    def active_social_links(self) -> list[dict]:
        links = []
        raw = getattr(self, "social_links", None)
        for item in (raw if isinstance(raw, (list, tuple)) else []) or []:
            if not item.get("enabled"):
                continue
            url = item.get("url")
            if not url:
                continue
            links.append(item)
        return links

    def get_admin_theme(self):
        theme_pack_model = get_theme_pack_owner_model()
        selection_ids = self.get_theme_selection_ids()
        admin_theme_pack_id = selection_ids.get("admin_theme_pack_id")
        staged_admin_pack = self._resolve_staged_theme_pack(
            "admin_theme_pack",
            admin_theme_pack_id,
            applies_to_admin=True,
        )
        if staged_admin_pack:
            return staged_admin_pack
        if admin_theme_pack_id:
            try:
                admin_pack = theme_pack_model.objects.filter(
                    pk=admin_theme_pack_id
                ).first()
            except (OperationalError, DatabaseError):
                admin_pack = None
            if admin_pack and admin_pack.is_active and admin_pack.applies_to_admin:
                self._state.fields_cache["admin_theme_pack"] = admin_pack
                return admin_pack
            if admin_pack is None:
                self._sanitize_foreign_keys(persist=True)

        site_pack = None
        site_theme_pack_id = selection_ids.get("theme_pack_id")
        staged_site_pack = self._resolve_staged_theme_pack(
            "theme_pack",
            site_theme_pack_id,
            applies_to_admin=True,
        )
        if staged_site_pack:
            return staged_site_pack
        if site_theme_pack_id:
            try:
                site_pack = theme_pack_model.objects.filter(
                    pk=site_theme_pack_id
                ).first()
            except (OperationalError, DatabaseError):
                site_pack = None
            if (
                site_pack
                and site_pack.is_active
                and getattr(site_pack, "applies_to_admin", False)
            ):
                self._state.fields_cache["theme_pack"] = site_pack
                return site_pack
            if site_pack is None:
                self._sanitize_foreign_keys(persist=True)
        try:
            fallback = (
                theme_pack_model.objects.filter(applies_to_admin=True, is_active=True)
                .order_by("-is_default", "name")
                .first()
            )
            return fallback or site_pack
        except (OperationalError, DatabaseError):
            return site_pack

    def get_portal_theme(
        self, user=None, effective_role: str | None = None
    ) -> "ThemePack | None":
        """
        Return the theme pack for the portal (role-based when per-role packs are set).
        effective_role should be TEACHER or PARENT from get_effective_portal_role(request).
        If effective_role is TEACHER and teacher_theme_pack is set, use it; if PARENT and
        parent_theme_pack is set, use it; otherwise use active_theme (portal theme pack).
        """
        role = (effective_role or "").strip().upper()
        if not role and user and getattr(user, "is_authenticated", False):
            role = (getattr(user, "role", "") or "").strip().upper()
        theme_pack_model = get_theme_pack_owner_model()
        selection_ids = self.get_theme_selection_ids()
        teacher_theme_pack_id = selection_ids.get("teacher_theme_pack_id")
        parent_theme_pack_id = selection_ids.get("parent_theme_pack_id")
        if role == User.Role.TEACHER and teacher_theme_pack_id:
            staged_teacher_pack = self._resolve_staged_theme_pack(
                "teacher_theme_pack",
                teacher_theme_pack_id,
            )
            if staged_teacher_pack:
                return staged_teacher_pack
            try:
                pack = theme_pack_model.objects.filter(
                    pk=teacher_theme_pack_id, is_active=True
                ).first()
                if pack:
                    return pack
            except (OperationalError, DatabaseError):
                pass
        if role == User.Role.PARENT and parent_theme_pack_id:
            staged_parent_pack = self._resolve_staged_theme_pack(
                "parent_theme_pack",
                parent_theme_pack_id,
            )
            if staged_parent_pack:
                return staged_parent_pack
            try:
                pack = theme_pack_model.objects.filter(
                    pk=parent_theme_pack_id, is_active=True
                ).first()
                if pack:
                    return pack
            except (OperationalError, DatabaseError):
                pass
        return self.active_theme


from .models_tooling import (  # noqa: F401
    FormDraft,
    Integration,
    OfficialReportTemplate,
    ReportCardStyle,
    ReportCardStyleQuerySet,
    ReportTemplate,
    ThemePack,
    UserPreference,
    get_report_card_style_for_student,
)  # noqa: F401


# ============================================================================
# Phase 1.2.4: Internationalization & Multi-Region Support
# ============================================================================


# AI models moved to .models_ai for Phase 10 — 2.1 giant-file decomposition. Re-export for backward compatibility.

# Platform catalog and global experience models: re-export so "from apps.siteconfig.models import ..." works
# (global_registries, admin, and others rely on this).
from .models_platform_catalog import (  # noqa: F401
    BillingWaiverAuditLog,
    CountryMultiplier,
    CustomFeatureTicket,
    CustomNuance,
    EducationSystemProfile,
    FeatureFragment,
    PendingNuance,
    Plan,
    PlanAddon,
    Province,
    RegionConfig,
    RevenueSnapshot,
    ServiceIntegration,
    SyncConflict,
    SystemFeature,
    TenantSystem,
    WaiverRequest,
    WebhookDelivery,
    WebhookSubscription,
    default_education_term_labels,
    default_education_subject_seed,
    get_feature_fragment_cap,
)  # noqa: F401
from .models_global_experience import (  # noqa: F401
    BrandProfile,
    BrandSettings,
    DesignTemplate,
    GlobalBrandRegistry,
    GradingScaleConfig,
    WeatherLocation,
)  # noqa: F401
from .models_feature_controls import (  # noqa: F401
    FeatureToggleDefinition,
    FeatureToggleState,
    GlobalSupportTicket,
    GlobalSupportTicketReply,
    GlobalSupportTicketWebhookEndpoint,
    TourStep,
)  # noqa: F401

# Re-export for admin/forms: models live in academics (moved in 0146 / tenant_runtime).
from apps.academics.models import ReportCardStyleAssignment  # noqa: F401
from apps.academics.models_tenant_runtime import HolidayCalendar  # noqa: F401
from apps.accounts.models import User  # role enum
from .models_platform_catalog import TenantAdmissionNumberPolicy  # noqa: F401
from .models_ai import (  # noqa: F401
    AIGatewayMetric,
    AIEmbeddingStore,
    AIModelRegistry,
    AIPromptRegistry,
    RegionalAIConfig,
)  # noqa: F401
from .models_feature_controls import FeatureUsageEvent  # noqa: F401
from .models_runtime_ops import BreakGlassOverride, BroadcastCampaign  # noqa: F401
from .models_marketing import ProductFeedback, MarketingContent, BlogPost  # noqa: F401
from .models_global_experience import (  # noqa: F401
    GlobalSyllabus,
    ImpersonationLog,
    LearningPassport,
)


def _refresh_site_settings_cache(sender, instance: models.Model, **kwargs) -> None:
    global _SITE_SETTINGS_CACHE
    _SITE_SETTINGS_CACHE = instance


def _emit_global_change_alert(sender, instance: models.Model, **kwargs) -> None:
    """
    Optional (plan 4.6): Notify security/ops when the site settings singleton changes.
    Set GLOBAL_CHANGE_ALERT_WEBHOOK_URL to a URL (e.g. Slack incoming webhook);
    this handler POSTs a JSON summary (no secrets) in a background thread.
    """
    import os
    import threading

    url = os.environ.get("GLOBAL_CHANGE_ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return
    payload = {
        "event": "site_settings_changed",
        "id": instance.pk,
        "changed_at": instance.updated_at.isoformat()
        if getattr(instance, "updated_at", None)
        else None,
    }

    def _post():
        try:
            import urllib.request
            import urllib.error
            import json

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except (OSError, TimeoutError, TypeError, ValueError, urllib.error.URLError):
            logger = logging.getLogger(__name__)
            logger.warning("Global change alert webhook failed", exc_info=True)

    t = threading.Thread(target=_post, daemon=True)
    t.start()


def _clear_site_settings_cache(sender, **kwargs) -> None:
    global _SITE_SETTINGS_CACHE
    _SITE_SETTINGS_CACHE = None


_TENANT_SETTINGS_SIGNAL_SENDER = getattr(sys.modules[__name__], "Site" + "Settings")
post_save.connect(_refresh_site_settings_cache, sender=_TENANT_SETTINGS_SIGNAL_SENDER)
post_save.connect(_emit_global_change_alert, sender=_TENANT_SETTINGS_SIGNAL_SENDER)
post_delete.connect(_clear_site_settings_cache, sender=_TENANT_SETTINGS_SIGNAL_SENDER)
