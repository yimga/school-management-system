"""Reconcile the DECLARED platform seed catalogs against the live database.

Read-only by default. Emits a structured receipt (``--json``) carrying the full,
untruncated missing/extra lists plus a checksum of the manifest the numbers were
measured against.

Relationship to what already exists
-----------------------------------
* ``verify_platform_seed_completeness`` (apps/siteconfig) is the fail-closed
  gate across ~25 catalogs. It answers yes/no. It prints ``missing[:12]``, so
  its evidence line is capped at twelve codes and cannot be counted from.
  This command is the receipt, not a second gate: it reports the whole list.
* ``reconcile_access_catalog`` (apps/accounts) REPAIRS the RBAC catalog by
  replaying data migrations. It writes unconditionally -- there is no dry run --
  and its ``REPAIR_MIGRATIONS`` tuple stops at ``0063``, so it does not replay
  ``0065_support_staff_roles`` and cannot restore the twelve non-teaching-staff
  roles. It also calls ``migration.forwards(...)``, a name ``0065`` does not
  define. Extending it was rejected: it would have meant changing a
  writes-by-default command into one that does not write by default, which
  silently breaks any runbook that calls it.
* ``reconcile_tenant_seed_baseline`` (apps/schools) reconciles per-tenant FIELD
  values, not platform catalog ROWS. Different unit of work.

This command is deliberately not wired into any deploy script, migration,
health check, or CI job. Nothing calls it. Run it by hand.

Safety
------
``--apply`` creates missing catalog rows and nothing else:

* it is opt-in twice -- ``--apply`` prints the exact plan and then REFUSES to
  write unless ``--confirm`` is also passed (exit 2),
* it uses ``get_or_create`` keyed on the natural key, so it never updates,
  never deletes, and never touches a row that already exists -- including a
  row that exists but is deactivated, which is reported as ``inactive`` rather
  than "repaired" by inserting a duplicate,
* it is strictly idempotent: a second run creates zero rows,
* it refuses outright for ``catalog.access_roles``. The authoritative name,
  description and PERMISSION SET for those rows live in migration
  ``accounts/0065_support_staff_roles``. Inserting a permissionless placeholder
  named "Librarian" would turn the audit green while leaving every one of those
  roles granting nothing -- and a role that grants nothing is not inert: it
  changes a request that used to be denied early into one that proceeds and
  fails somewhere else. Seeding rows to make a report go green is how an
  investigation turns a 0-failure suite into a 2-failure one. The remedy for
  that catalog is ``migrate accounts``, and the command says so.

Exit codes
----------
0  no drift (or drift, without ``--strict``)
1  drift, under ``--strict``
2  ``--apply`` used without ``--confirm``; the plan was printed, nothing written
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.siteconfig.seed_catalog_reconciler import build_receipt, diff_catalog

ACCESS_ROLE_REMEDY = (
    "run `manage.py migrate accounts` (rows are seeded by "
    "accounts/0065_support_staff_roles, which carries the names, descriptions "
    "and permission sets this command deliberately will not invent)"
)


def load_catalog_specs() -> list[dict]:
    """Declared catalogs, each pointing at its EXISTING single source of truth.

    Nothing here re-declares a manifest. Every ``rows`` value is imported from
    the module that already owns it, so adding a row there is still the whole
    change and this command cannot drift from the seeders.
    """
    from apps.accounts.models import AccessRole
    from apps.accounts.signals import ROLE_TEMPLATES
    from apps.registries.models import (
        CalendarSystemRegistry,
        EducationLevelRegistry,
        EducationSystemTypeRegistry,
        InstitutionTypeRegistry,
        LocaleRegistry,
    )
    from apps.registries.services import (
        CALENDAR_SYSTEM_SEED_DEFAULTS,
        DEFAULT_EDUCATION_LEVELS,
        DEFAULT_EDUCATION_SYSTEM_TYPES,
        INSTITUTION_TYPE_SEED_DEFAULTS,
        LOCALE_SEED_DEFAULTS,
    )

    role_codes = sorted({code for codes in ROLE_TEMPLATES.values() for code in codes})

    return [
        {
            "key": "registry.institution_types",
            "model": InstitutionTypeRegistry,
            "model_label": "registries.InstitutionTypeRegistry",
            "natural_key": "code",
            "rows": list(INSTITUTION_TYPE_SEED_DEFAULTS),
            "base_filter": {},
            "apply_supported": True,
            "remedy": "",
        },
        {
            "key": "catalog.access_roles",
            "model": AccessRole,
            "model_label": "accounts.AccessRole (school IS NULL)",
            "natural_key": "code",
            # Codes only: ROLE_TEMPLATES maps a User.Role to access-role codes
            # and carries no name/description/permission payload at all.
            "rows": [{"code": code} for code in role_codes],
            "base_filter": {"school__isnull": True},
            "apply_supported": False,
            "remedy": ACCESS_ROLE_REMEDY,
        },
        {
            "key": "registry.education_system_types",
            "model": EducationSystemTypeRegistry,
            "model_label": "registries.EducationSystemTypeRegistry",
            "natural_key": "code",
            "rows": list(DEFAULT_EDUCATION_SYSTEM_TYPES),
            "base_filter": {},
            "apply_supported": True,
            "remedy": "",
        },
        {
            "key": "registry.education_levels",
            "model": EducationLevelRegistry,
            "model_label": "registries.EducationLevelRegistry",
            "natural_key": "code",
            "rows": list(DEFAULT_EDUCATION_LEVELS),
            "base_filter": {},
            "apply_supported": True,
            "remedy": "",
        },
        {
            "key": "registry.locales",
            "model": LocaleRegistry,
            "model_label": "registries.LocaleRegistry",
            "natural_key": "code",
            "rows": list(LOCALE_SEED_DEFAULTS),
            "base_filter": {},
            "apply_supported": True,
            "remedy": "",
        },
        {
            "key": "registry.calendar_systems",
            "model": CalendarSystemRegistry,
            "model_label": "registries.CalendarSystemRegistry",
            "natural_key": "code",
            "rows": list(CALENDAR_SYSTEM_SEED_DEFAULTS),
            "base_filter": {},
            "apply_supported": True,
            "remedy": "",
        },
    ]


def _concrete_field_names(model) -> set[str]:
    return {
        f.name
        for f in model._meta.get_fields()
        if getattr(f, "concrete", False) and not f.auto_created
    }


def _create_payload(model, row: dict, natural_key: str) -> dict:
    """Row keys that are real, writable columns on this model.

    Generic on purpose: the manifests use different field names
    (``name`` vs ``global_name``, ``is_rtl``, ``metadata``, ``isced_level``),
    and filtering against ``_meta`` means a new manifest key cannot crash the
    apply path -- it is simply not written.
    """
    names = _concrete_field_names(model)
    payload = {k: v for k, v in row.items() if k != natural_key and k in names}
    if "is_active" in names:
        payload.setdefault("is_active", True)
    return payload


class Command(BaseCommand):
    help = (
        "Compare declared platform seed catalogs against the database and emit a "
        "receipt. Read-only unless --apply AND --confirm are both given."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--catalog",
            action="append",
            default=[],
            help="Limit to one catalog key (repeatable). Default: every catalog.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit the receipt as JSON on stdout and nothing else.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit 1 when any declared row is missing.",
        )
        parser.add_argument(
            "--strict-extras",
            action="store_true",
            help=(
                "Also treat undeclared rows as drift under --strict. Off by "
                "default: a tenant-authored global role is legitimate and is "
                "never proposed for deletion."
            ),
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Print the exact rows that WOULD be created. Writes nothing "
                "unless --confirm is also passed."
            ),
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="With --apply, actually create the missing rows.",
        )

    def handle(self, *args, **options):
        as_json = bool(options.get("json"))
        strict = bool(options.get("strict"))
        strict_extras = bool(options.get("strict_extras"))
        apply_mode = bool(options.get("apply"))
        confirmed = bool(options.get("confirm"))
        wanted = [str(c).strip() for c in (options.get("catalog") or []) if str(c).strip()]

        specs = load_catalog_specs()
        known = {spec["key"] for spec in specs}
        unknown = sorted(set(wanted) - known)
        if unknown:
            raise CommandError(
                f"Unknown catalog key(s): {', '.join(unknown)}. "
                f"Known: {', '.join(sorted(known))}"
            )
        if wanted:
            specs = [spec for spec in specs if spec["key"] in wanted]

        diffs = [self._diff_spec(spec) for spec in specs]
        scope = ",".join(wanted) if wanted else "all"

        # ---- read-only report -------------------------------------------------
        if not apply_mode:
            receipt = build_receipt(
                diffs,
                scope=scope,
                mode="read-only",
                generated_at=timezone.now().isoformat(),
            )
            self._emit(receipt, as_json=as_json)
            if strict and receipt.has_drift(include_extra=strict_extras):
                raise CommandError(
                    "Seed catalog drift: "
                    + ", ".join(
                        f"{d.key} missing {d.missing_count}" for d in receipt.drifted
                    ),
                    returncode=1,
                )
            return

        # ---- apply: plan first, always ---------------------------------------
        plan, refused = self._build_plan(specs, diffs)
        self._print_plan(plan, refused, as_json=as_json)

        if not confirmed:
            receipt = build_receipt(
                diffs,
                scope=scope,
                mode="apply-refused",
                generated_at=timezone.now().isoformat(),
            )
            self._emit(receipt, as_json=as_json)
            raise CommandError(
                "--apply prints the plan and stops. Re-run with --apply --confirm "
                "to create the rows listed above. Nothing was written.",
                returncode=2,
            )

        created = self._apply(plan)
        # Re-diff AFTER writing so the receipt reports the settled state rather
        # than the state that motivated the write.
        after = [self._diff_spec(spec) for spec in specs]
        receipt = build_receipt(
            after,
            scope=scope,
            mode="applied",
            generated_at=timezone.now().isoformat(),
            created=created,
        )
        self._emit(receipt, as_json=as_json)
        if strict and receipt.has_drift(include_extra=strict_extras):
            raise CommandError(
                "Drift remains after --apply: "
                + ", ".join(
                    f"{d.key} missing {d.missing_count}" for d in receipt.drifted
                ),
                returncode=1,
            )

    # ------------------------------------------------------------------ helpers
    def _diff_spec(self, spec: dict):
        model = spec["model"]
        natural_key = spec["natural_key"]
        base = dict(spec["base_filter"])
        # ACTUAL is every row, active or not. Filtering to is_active here is the
        # bug that makes a deactivated row look absent and invites a duplicate
        # insert that the unique index would refuse anyway.
        actual = list(
            model.objects.filter(**base).values_list(natural_key, flat=True)
        )
        if "is_active" in _concrete_field_names(model):
            inactive = list(
                model.objects.filter(**base, is_active=False).values_list(
                    natural_key, flat=True
                )
            )
        else:
            inactive = []
        return diff_catalog(
            spec["key"],
            declared=[row[natural_key] for row in spec["rows"]],
            actual=actual,
            inactive=inactive,
            model_label=spec["model_label"],
            natural_key=natural_key,
            apply_supported=bool(spec["apply_supported"]),
            remedy=str(spec["remedy"]),
        )

    def _build_plan(self, specs, diffs):
        by_key = {spec["key"]: spec for spec in specs}
        plan: list[tuple[dict, list[dict]]] = []
        refused: list = []
        for diff in diffs:
            if not diff.missing:
                continue
            spec = by_key[diff.key]
            if not spec["apply_supported"]:
                refused.append(diff)
                continue
            wanted = set(diff.missing)
            rows = [r for r in spec["rows"] if str(r[spec["natural_key"]]) in wanted]
            plan.append((spec, rows))
        return plan, refused

    def _print_plan(self, plan, refused, *, as_json: bool):
        out = self.stderr if as_json else self.stdout
        out.write("")
        out.write("PLAN -- rows that WOULD be created (create only; no update, no delete):")
        if not plan:
            out.write("  (nothing to create)")
        for spec, rows in plan:
            out.write(f"  {spec['key']} [{spec['model_label']}]: {len(rows)} row(s)")
            for row in rows:
                payload = _create_payload(spec["model"], row, spec["natural_key"])
                out.write(f"    + {row[spec['natural_key']]}  {payload}")
        for diff in refused:
            out.write(
                f"  {diff.key}: {diff.missing_count} missing, REFUSED by this command."
            )
            out.write(f"    missing: {list(diff.missing)}")
            out.write(f"    remedy: {diff.remedy}")
        out.write("")

    @transaction.atomic
    def _apply(self, plan):
        created: list[tuple[str, list[str]]] = []
        for spec, rows in plan:
            model = spec["model"]
            natural_key = spec["natural_key"]
            made: list[str] = []
            for row in rows:
                code = row[natural_key]
                lookup = dict(spec["base_filter"])
                # school__isnull=True is a filter, not a writable kwarg.
                lookup.pop("school__isnull", None)
                if "school__isnull" in spec["base_filter"]:
                    lookup["school"] = None
                lookup[natural_key] = code
                _obj, was_created = model.objects.get_or_create(
                    **lookup,
                    defaults=_create_payload(model, row, natural_key),
                )
                if was_created:
                    made.append(str(code))
            if made:
                created.append((spec["key"], made))
        return created

    def _emit(self, receipt, *, as_json: bool):
        if as_json:
            self.stdout.write(receipt.to_json())
            return
        totals = receipt.totals
        self.stdout.write(f"manifest_checksum: {receipt.manifest_checksum}")
        self.stdout.write(f"mode: {receipt.mode}   scope: {receipt.scope}")
        self.stdout.write("")
        header = (
            f"{'catalog':<34}{'decl':>6}{'present':>9}{'missing':>9}"
            f"{'extra':>7}{'inactive':>10}"
        )
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for diff in receipt.diffs:
            self.stdout.write(
                f"{diff.key:<34}{diff.declared_count:>6}{diff.present_count:>9}"
                f"{diff.missing_count:>9}{diff.extra_count:>7}{diff.inactive_count:>10}"
            )
        self.stdout.write("-" * len(header))
        self.stdout.write(
            f"{'TOTAL':<34}{totals['declared']:>6}{totals['present']:>9}"
            f"{totals['missing']:>9}{totals['extra']:>7}{totals['inactive']:>10}"
        )
        self.stdout.write("")
        for diff in receipt.diffs:
            if diff.missing:
                # Untruncated, unlike the audit's missing[:12].
                self.stdout.write(f"{diff.key}: missing {diff.missing_count}")
                for code in diff.missing:
                    self.stdout.write(f"    - {code}")
                if diff.remedy:
                    self.stdout.write(f"    remedy: {diff.remedy}")
            if diff.inactive:
                self.stdout.write(
                    f"{diff.key}: present but INACTIVE {diff.inactive_count}: "
                    f"{list(diff.inactive)}"
                )
            if diff.extra:
                self.stdout.write(
                    f"{diff.key}: undeclared (kept, never deleted) "
                    f"{diff.extra_count}: {list(diff.extra)}"
                )
        if receipt.created:
            self.stdout.write("")
            self.stdout.write(f"created {receipt.created_count} row(s):")
            for key, codes in receipt.created:
                self.stdout.write(f"  {key}: {list(codes)}")
        self.stdout.write("")
        if receipt.has_drift():
            self.stdout.write(
                self.style.WARNING(
                    f"DRIFT: {totals['missing']} declared row(s) absent across "
                    f"{len(receipt.drifted)} catalog(s)."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"IN SYNC: all {totals['declared']} declared row(s) present."
                )
            )
