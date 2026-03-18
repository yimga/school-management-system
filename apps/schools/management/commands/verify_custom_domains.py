"""
Verify custom domains: resolve DNS and set custom_domain_verified (Phase 4 whitelabel).
Run: python manage.py verify_custom_domains
Uses socket.getaddrinfo to check that the custom_domain resolves; optional CNAME check.
§2.4: invalidate_policy_cache wrapped with typed exceptions + logger.debug.
"""

import logging
import socket

from django.core.management.base import BaseCommand

from apps.schools.models import School, SchoolProvisioningEvent

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Verify school custom domains via DNS and set custom_domain_verified."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Only print, do not update."
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        for school in School.objects.exclude(custom_domain="").filter(
            custom_domain__isnull=False
        ):
            domain = (school.custom_domain or "").strip()
            if not domain:
                continue
            try:
                socket.getaddrinfo(domain, 443)
                if not school.custom_domain_verified:
                    if not dry_run:
                        school.custom_domain_verified = True
                        settings_payload = dict(school.settings or {})
                        custom_domain_payload = dict(
                            settings_payload.get("custom_domain") or {}
                        )
                        custom_domain_payload.update(
                            {
                                "hostname": domain,
                                "status": "verified",
                                "verified": True,
                            }
                        )
                        settings_payload["custom_domain"] = custom_domain_payload
                        school.settings = settings_payload
                        school.save(
                            update_fields=[
                                "custom_domain_verified",
                                "settings",
                                "updated_at",
                            ]
                        )
                        try:
                            from apps.policies.policy_registry import (
                                invalidate_policy_cache,
                            )

                            invalidate_policy_cache(school)
                        except (
                            ImportError,
                            AttributeError,
                            TypeError,
                            ValueError,
                        ) as e:
                            logger.debug(
                                "verify_custom_domains invalidate_policy_cache (verified): %s",
                                e,
                            )
                        SchoolProvisioningEvent.log_event(
                            school=school,
                            event_type=SchoolProvisioningEvent.EventType.DOMAIN_VERIFIED,
                            status=SchoolProvisioningEvent.Status.SUCCESS,
                            message=f"Custom domain {domain} verified via DNS resolution.",
                            payload={"hostname": domain},
                        )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"{school.name}: {domain} resolves -> verified"
                        )
                    )
                else:
                    self.stdout.write(f"{school.name}: {domain} already verified")
            except (socket.gaierror, OSError) as e:
                if school.custom_domain_verified:
                    if not dry_run:
                        school.custom_domain_verified = False
                        settings_payload = dict(school.settings or {})
                        custom_domain_payload = dict(
                            settings_payload.get("custom_domain") or {}
                        )
                        custom_domain_payload.update(
                            {
                                "hostname": domain,
                                "status": "unverified",
                                "verified": False,
                            }
                        )
                        settings_payload["custom_domain"] = custom_domain_payload
                        school.settings = settings_payload
                        school.save(
                            update_fields=[
                                "custom_domain_verified",
                                "settings",
                                "updated_at",
                            ]
                        )
                        try:
                            from apps.policies.policy_registry import (
                                invalidate_policy_cache,
                            )

                            invalidate_policy_cache(school)
                        except (
                            ImportError,
                            AttributeError,
                            TypeError,
                            ValueError,
                        ) as e:
                            logger.debug(
                                "verify_custom_domains invalidate_policy_cache (unverified): %s",
                                e,
                            )
                        SchoolProvisioningEvent.log_event(
                            school=school,
                            event_type=SchoolProvisioningEvent.EventType.DOMAIN_UNVERIFIED,
                            status=SchoolProvisioningEvent.Status.WARNING,
                            message=f"Custom domain {domain} no longer resolves.",
                            payload={"hostname": domain},
                        )
                    self.stdout.write(
                        self.style.WARNING(
                            f"{school.name}: {domain} no longer resolves -> unverified"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.NOTICE(
                            f"{school.name}: {domain} does not resolve ({e})"
                        )
                    )
