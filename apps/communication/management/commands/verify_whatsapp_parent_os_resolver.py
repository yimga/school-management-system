"""Wave Q4 (v3.95.2 — 2026-05-26) — WhatsApp Parent OS resolver self-test.

Operators run this on a tenant to confirm the resolver actually finds
Guardians via their phone fields. Reports:

- Which Guardian model fields exist
- Which phone fields contain non-null data
- A round-trip test: pick a Guardian, normalize their phone, look them up
  through ``whatsapp_parent_os_resolvers._find_guardian``, confirm it
  returns the same row.

Usage:
    python manage.py verify_whatsapp_parent_os_resolver --tenant <slug>
    python manage.py verify_whatsapp_parent_os_resolver --tenant <slug> --apply

Without ``--apply`` the command is read-only.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verify the WhatsApp Parent OS resolver against a tenant's Guardian schema."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            required=True,
            help="Tenant slug or PK to test against.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="(Reserved.) Run any auto-correction. Currently no-op.",
        )

    def handle(self, *args, **options):
        tenant = options["tenant"]

        try:
            from apps.schools.models import School  # type: ignore
            school = School.objects.filter(slug=tenant).first() or \
                School.objects.filter(id=tenant).first() if tenant.isdigit() else \
                School.objects.filter(slug=tenant).first()
        except Exception as exc:
            raise CommandError(f"School model unavailable: {exc}")
        if school is None:
            raise CommandError(f"Tenant {tenant!r} not found")

        self.stdout.write(self.style.NOTICE(
            f"=== Verifying WhatsApp Parent OS resolver against tenant={school.slug} ==="
        ))

        try:
            from apps.people.models import StudentGuardian
        except Exception as exc:
            raise CommandError(f"StudentGuardian model unavailable: {exc}")

        # 1. Field discovery
        from apps.communication.whatsapp_parent_os_resolvers import _PHONE_FIELDS
        guardian_fields = {f.name for f in StudentGuardian._meta.get_fields()}
        present = [f for f in _PHONE_FIELDS if f in guardian_fields]
        absent = [f for f in _PHONE_FIELDS if f not in guardian_fields]
        self.stdout.write(f"Guardian fields present from resolver probe: {present}")
        if absent:
            self.stdout.write(self.style.WARNING(
                f"  Fields absent (resolver will skip these): {absent}"
            ))
        if not present:
            self.stdout.write(self.style.ERROR(
                "  No phone fields found! Resolver will never match a Guardian. "
                "Add the field, or extend `_PHONE_FIELDS` in "
                "whatsapp_parent_os_resolvers.py."
            ))
            return

        # 2. Data presence per field (StudentGuardian is tenant-scoped via student)
        qs = StudentGuardian.objects.filter(student__school=school)
        total = qs.count()
        self.stdout.write(f"Tenant has {total} guardians total")
        if total == 0:
            self.stdout.write(self.style.WARNING(
                "  No guardians in tenant — can't run round-trip test."
            ))
            return

        field_counts: dict[str, int] = {}
        for field in present:
            try:
                count = qs.exclude(**{f"{field}__isnull": True}).exclude(
                    **{field: ""}).count()
            except Exception:  # noqa: BLE001
                count = -1  # field exists but query failed
            field_counts[field] = count
        for field, count in field_counts.items():
            marker = self.style.SUCCESS if count > 0 else self.style.WARNING
            self.stdout.write(marker(f"  {field}: {count} non-empty values"))

        # 3. Round-trip test
        from apps.communication.whatsapp_parent_os_resolvers import _find_guardian
        sample = None
        sample_field = None
        for field in present:
            try:
                row = qs.exclude(**{f"{field}__isnull": True}).exclude(
                    **{field: ""}).first()
            except Exception:  # noqa: BLE001
                continue
            if row is not None:
                sample = row
                sample_field = field
                break

        if sample is None:
            self.stdout.write(self.style.WARNING(
                "  No guardians with a phone — can't run round-trip."
            ))
            return

        phone_value = getattr(sample, sample_field, None)
        self.stdout.write(
            f"\nRound-trip test using guardian pk={sample.pk}, "
            f"field={sample_field}, value={phone_value!r}"
        )
        found = _find_guardian(str(school.pk), str(phone_value or ""))
        if found is None:
            self.stdout.write(self.style.ERROR(
                "  FAIL — resolver returned None for a known phone. "
                "Phone normalization may strip a needed format."
            ))
        elif found.pk == sample.pk:
            self.stdout.write(self.style.SUCCESS(
                f"  PASS — resolver returned guardian pk={found.pk} (match)."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"  PARTIAL — resolver returned a DIFFERENT guardian pk={found.pk}. "
                f"Two guardians share this phone? Investigate."
            ))

        self.stdout.write(self.style.NOTICE("=== Done ==="))
