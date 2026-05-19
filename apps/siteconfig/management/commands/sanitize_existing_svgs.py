"""Retro-sanitize historical SVG uploads on tenant brand fields.

v2.59 wired ``validate_svg_safe`` as an upload-time validator on every
``ImageField`` / ``FileField`` that accepts SVG. But rows that existed
*before* v2.59 were never re-validated — so a malicious pre-v2.59 SVG is
still served via ``<img src="…/logo.svg">`` or inlined into a template.

This command walks every model + field that carries the validator,
re-reads each SVG, and:

* **Clean** — sanitized output matches the source byte-for-byte. No-op.
* **Sanitized** — output differs (e.g. an ``onload="…"`` got stripped).
  In ``--apply`` mode the sanitized bytes are written back through the
  storage backend. ``--dry-run`` (default) only reports.
* **Quarantined** — the sanitizer raised ``ValidationError`` (DOCTYPE /
  ENTITY / malformed XML). In ``--apply`` mode the field is cleared
  (``logo = None``) so the malicious bytes stop being served; the
  original file is renamed to ``<name>.quarantined-<ts>`` so an operator
  can audit. ``--dry-run`` only reports.

Usage:
  python manage.py sanitize_existing_svgs              # dry-run
  python manage.py sanitize_existing_svgs --apply      # write changes
  python manage.py sanitize_existing_svgs --apply --json
  python manage.py sanitize_existing_svgs --field logo # restrict scope

Exit codes:
  0 — all rows clean OR --dry-run with findings.
  1 — --apply ran and at least one row could not be sanitized
      (e.g. storage write failure). Operator action required.
  2 — invocation error (model lookup failed, etc.).
"""

from __future__ import annotations

import json as _json
import time as _time
from dataclasses import dataclass, field

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

# ((app_label, model_name), [field_name, ...]) — keep in sync with the
# `validators=[validate_svg_safe]` declarations across the codebase.
# Adding a new SVG-accepting field? Append it here so the retro-sanitize
# sweep covers it on the next run.
SVG_FIELD_REGISTRY: tuple[tuple[tuple[str, str], tuple[str, ...]], ...] = (
    (
        ("brand_experience", "PlatformGlobalBranding"),
        ("svg_background", "logo", "background_image", "favicon", "sidebar_icon"),
    ),
    (("siteconfig", "ThemePack"), ("logo",)),
    (("siteconfig", "ReportCardStyle"), ("watermark_logo",)),
)


@dataclass
class Outcome:
    model: str
    field: str
    pk: int
    name: str
    status: str  # "clean" | "sanitized" | "quarantined" | "skipped" | "error"
    detail: str = ""


@dataclass
class RunSummary:
    apply: bool
    scanned: int = 0
    clean: int = 0
    sanitized: int = 0
    quarantined: int = 0
    skipped: int = 0
    errors: int = 0
    outcomes: list[Outcome] = field(default_factory=list)


def _looks_like_svg(name: str, data: bytes) -> bool:
    if name.lower().endswith(".svg"):
        return True
    head = data[:1024].lstrip().lower()
    return head.startswith(b"<?xml") or b"<svg" in head


class Command(BaseCommand):
    help = (
        "Re-validate every historical SVG upload on tenant brand fields. "
        "Default is dry-run; pass --apply to write sanitized bytes back."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Persist sanitized bytes / quarantine results. Default is dry-run.",
        )
        parser.add_argument(
            "--json", action="store_true",
            help="Emit machine-readable JSON instead of operator-friendly text.",
        )
        parser.add_argument(
            "--field", action="append", default=None,
            help=(
                "Restrict the sweep to fields with this name (may be repeated). "
                "Example: --field logo --field favicon"
            ),
        )

    def handle(self, *args, **opts):
        try:
            from apps.siteconfig.svg_sanitize import sanitize_svg_bytes
        except ImportError as exc:
            raise SystemExit(2) from exc

        wanted_fields = set(opts.get("field") or [])
        summary = RunSummary(apply=bool(opts.get("apply")))

        for (app_label, model_name), fields in SVG_FIELD_REGISTRY:
            try:
                model = django_apps.get_model(app_label, model_name)
            except LookupError as exc:
                summary.errors += 1
                summary.outcomes.append(Outcome(
                    model=f"{app_label}.{model_name}",
                    field="", pk=-1, name="",
                    status="error", detail=f"model lookup failed: {exc}",
                ))
                continue

            for field_name in fields:
                if wanted_fields and field_name not in wanted_fields:
                    continue
                self._sweep_field(
                    summary, model, app_label, model_name, field_name,
                    sanitize_svg_bytes,
                )

        if opts.get("json"):
            self.stdout.write(_json.dumps(self._summary_to_dict(summary), indent=2, sort_keys=True, default=str))
        else:
            self._render_text(summary)

        # Exit 1 only if --apply ran and we had errors; otherwise informational.
        if summary.apply and summary.errors:
            raise SystemExit(1)

    # --- sweeping ----------------------------------------------------------

    def _sweep_field(self, summary, model, app_label, model_name, field_name, sanitize):
        # `.exclude(field='')` filters out blank string rows but Django
        # FileField stores empty as "" — exclude both blank string and NULL.
        qs = model.objects.exclude(**{f"{field_name}": ""}).exclude(**{f"{field_name}__isnull": True})
        for instance in qs.iterator():
            f = getattr(instance, field_name, None)
            if not f or not getattr(f, "name", ""):
                continue
            summary.scanned += 1
            try:
                data = f.read()
                f.close()
            except (FileNotFoundError, OSError, ValueError) as exc:
                summary.skipped += 1
                summary.outcomes.append(Outcome(
                    model=f"{app_label}.{model_name}",
                    field=field_name, pk=instance.pk, name=f.name,
                    status="skipped",
                    detail=f"file unreadable: {type(exc).__name__}",
                ))
                continue

            if not _looks_like_svg(f.name, data):
                # Raster file — validator is a no-op for these. Skip silently.
                summary.skipped += 1
                continue

            try:
                sanitized = sanitize(data)
            except ValidationError as exc:
                self._quarantine(summary, instance, field_name, f, str(exc),
                                 app_label, model_name)
                continue

            if sanitized == data:
                summary.clean += 1
                summary.outcomes.append(Outcome(
                    model=f"{app_label}.{model_name}",
                    field=field_name, pk=instance.pk, name=f.name,
                    status="clean",
                ))
                continue

            # Sanitized differs from source — re-save through storage.
            if summary.apply:
                try:
                    base = f.name.rsplit("/", 1)[-1]
                    f.save(base, ContentFile(sanitized), save=True)
                    status = "sanitized"
                except (OSError, ValueError) as exc:
                    summary.errors += 1
                    summary.outcomes.append(Outcome(
                        model=f"{app_label}.{model_name}",
                        field=field_name, pk=instance.pk, name=f.name,
                        status="error",
                        detail=f"save failed: {exc}",
                    ))
                    continue
            else:
                status = "sanitized"

            summary.sanitized += 1
            summary.outcomes.append(Outcome(
                model=f"{app_label}.{model_name}",
                field=field_name, pk=instance.pk, name=f.name,
                status=status,
                detail=f"bytes changed: {len(data)} -> {len(sanitized)}",
            ))

    def _quarantine(self, summary, instance, field_name, file_obj, reason,
                    app_label, model_name):
        """Strip the unsafe field; rename the underlying file to .quarantined-<ts>."""
        original = file_obj.name
        if summary.apply:
            try:
                storage = file_obj.storage
                ts = int(_time.time())
                new_name = f"{original}.quarantined-{ts}"
                # Best effort rename — not all storage backends support
                # arbitrary move. We do this by reading + saving under
                # the new name then deleting the original, which all
                # storage backends support.
                try:
                    file_obj.open("rb")
                    contents = file_obj.read()
                    file_obj.close()
                    storage.save(new_name, ContentFile(contents))
                except (FileNotFoundError, OSError) as exc:
                    summary.errors += 1
                    summary.outcomes.append(Outcome(
                        model=f"{app_label}.{model_name}",
                        field=field_name, pk=instance.pk, name=original,
                        status="error",
                        detail=f"quarantine copy failed: {exc}",
                    ))
                    return

                # Delete the live file and clear the model field so
                # nothing references it any more.
                try:
                    storage.delete(original)
                except (FileNotFoundError, OSError):
                    pass
                setattr(instance, field_name, None)
                instance.save(update_fields=[field_name])
            except (OSError, ValueError) as exc:
                summary.errors += 1
                summary.outcomes.append(Outcome(
                    model=f"{app_label}.{model_name}",
                    field=field_name, pk=instance.pk, name=original,
                    status="error",
                    detail=f"quarantine failed: {exc}",
                ))
                return

        summary.quarantined += 1
        summary.outcomes.append(Outcome(
            model=f"{app_label}.{model_name}",
            field=field_name, pk=instance.pk, name=original,
            status="quarantined",
            detail=reason,
        ))

    # --- rendering ---------------------------------------------------------

    def _summary_to_dict(self, summary: RunSummary) -> dict:
        return {
            "apply": summary.apply,
            "scanned": summary.scanned,
            "clean": summary.clean,
            "sanitized": summary.sanitized,
            "quarantined": summary.quarantined,
            "skipped": summary.skipped,
            "errors": summary.errors,
            "outcomes": [
                {
                    "model": o.model, "field": o.field, "pk": o.pk,
                    "name": o.name, "status": o.status, "detail": o.detail,
                }
                for o in summary.outcomes
            ],
        }

    def _render_text(self, summary: RunSummary) -> None:
        mode = "APPLY" if summary.apply else "DRY-RUN"
        self.stdout.write(f"=== sanitize_existing_svgs ({mode}) ===")
        self.stdout.write(f"  scanned:     {summary.scanned}")
        self.stdout.write(f"  clean:       {summary.clean}")
        self.stdout.write(f"  sanitized:   {summary.sanitized}")
        self.stdout.write(f"  quarantined: {summary.quarantined}")
        self.stdout.write(f"  skipped:     {summary.skipped}")
        self.stdout.write(f"  errors:      {summary.errors}")

        # Verbose detail for rows that changed or failed.
        attention = [
            o for o in summary.outcomes
            if o.status in {"sanitized", "quarantined", "error"}
        ]
        if attention:
            self.stdout.write("")
            self.stdout.write("Details:")
            for o in attention:
                self.stdout.write(
                    f"  [{o.status}] {o.model}.{o.field} pk={o.pk} "
                    f"name={o.name} -- {o.detail}"
                )

        if not summary.apply and (summary.sanitized or summary.quarantined):
            self.stdout.write("")
            self.stdout.write(
                "Re-run with --apply to persist sanitized bytes and "
                "quarantine unsafe files."
            )
