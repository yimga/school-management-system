from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.siteconfig.models import SiteSettings, ThemePack


class Command(BaseCommand):
    help = (
        "Normalize SiteSettings/ThemePack pointers so UI theme resolution stays "
        "deterministic across dev and Render."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report planned changes without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        site = SiteSettings.objects.order_by("pk").first()
        if not site:
            self.stdout.write(self.style.WARNING("No SiteSettings row found. Nothing to normalize."))
            return

        changed_messages: list[str] = []
        with transaction.atomic():
            default_themes = list(ThemePack.objects.filter(is_default=True).order_by("pk"))

            preferred_default = None
            if site.theme_pack_id and ThemePack.objects.filter(pk=site.theme_pack_id).exists():
                preferred_default = ThemePack.objects.get(pk=site.theme_pack_id)
            elif default_themes:
                preferred_default = default_themes[0]
            else:
                preferred_default = ThemePack.objects.order_by("pk").first()

            if preferred_default:
                if not preferred_default.is_default or len(default_themes) > 1:
                    changed_messages.append(
                        f"Set single default ThemePack -> id={preferred_default.pk} ({preferred_default.name})."
                    )
                    if not dry_run:
                        ThemePack.objects.filter(is_default=True).exclude(pk=preferred_default.pk).update(
                            is_default=False
                        )
                        ThemePack.objects.filter(pk=preferred_default.pk).update(is_default=True)

                if site.theme_pack_id != preferred_default.pk:
                    changed_messages.append(
                        f"Updated SiteSettings.theme_pack -> id={preferred_default.pk} ({preferred_default.name})."
                    )
                    if not dry_run:
                        site.theme_pack_id = preferred_default.pk
                        site.save(update_fields=["theme_pack"])

            if site.admin_theme_pack_id and not ThemePack.objects.filter(pk=site.admin_theme_pack_id).exists():
                changed_messages.append(
                    f"Cleared invalid admin_theme_pack reference id={site.admin_theme_pack_id}."
                )
                if not dry_run:
                    site.admin_theme_pack = None
                    site.save(update_fields=["admin_theme_pack"])

            # If admin theme is implicit and the site theme is not admin-capable, pin a deterministic admin theme.
            site.refresh_from_db(fields=["theme_pack", "admin_theme_pack"])
            if site.admin_theme_pack_id is None:
                site_theme = site.theme_pack
                theme_covers_admin = bool(site_theme and site_theme.applies_to_admin and site_theme.is_active)
                if not theme_covers_admin:
                    admin_fallback = (
                        ThemePack.objects.filter(applies_to_admin=True, is_active=True)
                        .order_by("-is_default", "pk")
                        .first()
                    )
                    if admin_fallback:
                        changed_messages.append(
                            f"Pinned SiteSettings.admin_theme_pack -> id={admin_fallback.pk} ({admin_fallback.name})."
                        )
                        if not dry_run:
                            site.admin_theme_pack = admin_fallback
                            site.save(update_fields=["admin_theme_pack"])

            if dry_run:
                transaction.set_rollback(True)

        if changed_messages:
            label = "Planned changes" if dry_run else "Applied changes"
            self.stdout.write(self.style.SUCCESS(f"{label}:"))
            for msg in changed_messages:
                self.stdout.write(f"- {msg}")
        else:
            self.stdout.write(self.style.SUCCESS("UI configuration is already normalized."))
