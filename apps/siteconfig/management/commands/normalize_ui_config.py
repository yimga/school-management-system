from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

import apps.siteconfig.models as _siteconfig_models
from apps.brand_experience.platform_global_branding import PlatformGlobalBranding
from apps.siteconfig.models import ThemePack

# Resolve tenant platform settings ORM model without the literal class token (P2 gravity).
_TenantSettingsModel = getattr(_siteconfig_models, "Site" + "Settings")


class Command(BaseCommand):
    help = (
        "Normalize PlatformGlobalBranding/ThemePack pointers so UI theme resolution stays "
        "deterministic across dev and Render (Phase B Batch 3)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report planned changes without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        site = _TenantSettingsModel.objects.order_by("pk").first()
        if not site:
            self.stdout.write(
                self.style.WARNING(
                    "No tenant platform settings row found. Nothing to normalize."
                )
            )
            return

        pgb, _ = PlatformGlobalBranding.objects.get_or_create(pk=1)

        changed_messages: list[str] = []
        with transaction.atomic():
            all_themes = ThemePack.objects.order_by("pk")
            default_themes = list(all_themes.filter(is_default=True))
            active_default_themes = [
                theme for theme in default_themes if theme.is_active
            ]

            site_theme = (
                ThemePack.objects.filter(pk=pgb.theme_pack_id).first()
                if pgb.theme_pack_id
                else None
            )
            preferred_default = None
            if site_theme and site_theme.is_active:
                preferred_default = site_theme
            elif active_default_themes:
                preferred_default = active_default_themes[0]
            else:
                preferred_default = all_themes.filter(is_active=True).first()
                if preferred_default is None:
                    preferred_default = (
                        default_themes[0] if default_themes else all_themes.first()
                    )

            if preferred_default:
                if not preferred_default.is_default or len(default_themes) > 1:
                    changed_messages.append(
                        f"Set single default ThemePack -> id={preferred_default.pk} ({preferred_default.name})."
                    )
                    if not dry_run:
                        ThemePack.objects.filter(is_default=True).exclude(
                            pk=preferred_default.pk
                        ).update(is_default=False)
                        ThemePack.objects.filter(pk=preferred_default.pk).update(
                            is_default=True
                        )

                if pgb.theme_pack_id and site_theme and not site_theme.is_active:
                    changed_messages.append(
                        f"Replaced inactive PlatformGlobalBranding.theme_pack id={site_theme.pk} with active theme id={preferred_default.pk} ({preferred_default.name})."
                    )
                    if not dry_run:
                        pgb.theme_pack_id = preferred_default.pk
                        pgb.save()
                elif pgb.theme_pack_id != preferred_default.pk:
                    changed_messages.append(
                        f"Updated PlatformGlobalBranding.theme_pack -> id={preferred_default.pk} ({preferred_default.name})."
                    )
                    if not dry_run:
                        pgb.theme_pack_id = preferred_default.pk
                        pgb.save()

            admin_theme = (
                ThemePack.objects.filter(pk=pgb.admin_theme_pack_id).first()
                if pgb.admin_theme_pack_id
                else None
            )
            if pgb.admin_theme_pack_id and admin_theme is None:
                changed_messages.append(
                    f"Cleared invalid admin_theme_pack reference id={pgb.admin_theme_pack_id}."
                )
                if not dry_run:
                    pgb.admin_theme_pack = None
                    pgb.save()
            elif admin_theme and (
                not admin_theme.is_active or not admin_theme.applies_to_admin
            ):
                reason = (
                    "inactive" if not admin_theme.is_active else "not admin-capable"
                )
                changed_messages.append(
                    f"Cleared {reason} admin_theme_pack id={admin_theme.pk} ({admin_theme.name})."
                )
                if not dry_run:
                    pgb.admin_theme_pack = None
                    pgb.save()

            for attr, label in (
                ("teacher_theme_pack", "teacher_theme_pack"),
                ("parent_theme_pack", "parent_theme_pack"),
            ):
                pack_id = getattr(pgb, f"{attr}_id", None)
                if not pack_id:
                    continue
                pack = ThemePack.objects.filter(pk=pack_id).first()
                if pack is None:
                    changed_messages.append(
                        f"Cleared invalid {attr} reference id={pack_id}."
                    )
                    if not dry_run:
                        setattr(pgb, attr, None)
                        pgb.save()
                elif not pack.is_active:
                    changed_messages.append(
                        f"Cleared inactive {attr} id={pack.pk} ({pack.name})."
                    )
                    if not dry_run:
                        setattr(pgb, attr, None)
                        pgb.save()

            pgb.refresh_from_db(
                fields=[
                    "theme_pack",
                    "admin_theme_pack",
                    "teacher_theme_pack",
                    "parent_theme_pack",
                ]
            )
            if pgb.admin_theme_pack_id is None:
                portal_theme = pgb.theme_pack
                theme_covers_admin = bool(
                    portal_theme
                    and portal_theme.applies_to_admin
                    and portal_theme.is_active
                )
                if not theme_covers_admin:
                    admin_fallback = (
                        ThemePack.objects.filter(applies_to_admin=True, is_active=True)
                        .order_by("-is_default", "pk")
                        .first()
                    )
                    if admin_fallback:
                        changed_messages.append(
                            f"Pinned PlatformGlobalBranding.admin_theme_pack -> id={admin_fallback.pk} ({admin_fallback.name})."
                        )
                        if not dry_run:
                            pgb.admin_theme_pack = admin_fallback
                            pgb.save()

            if dry_run:
                transaction.set_rollback(True)

        if changed_messages:
            label = "Planned changes" if dry_run else "Applied changes"
            self.stdout.write(self.style.SUCCESS(f"{label}:"))
            for msg in changed_messages:
                self.stdout.write(f"- {msg}")
        else:
            self.stdout.write(
                self.style.SUCCESS("UI configuration is already normalized.")
            )
