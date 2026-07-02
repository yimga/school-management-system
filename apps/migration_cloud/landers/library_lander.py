"""Library lander — persists canonical library-catalog rows into ``apps.schoolops.LibraryItem``.

Canonical row shape::

    {
        "item_external_id":  "LIB-00198",
        "title":             "To Kill a Mockingbird",
        "author":            "Harper Lee",
        "isbn":              "9780061120084",
        "category":          "fiction"|"nonfiction"|"reference"|"textbook"|...
        "status":            "available"|"checked_out"|"lost"|"retired",
        "copies_total":      3,
    }

Upsert key: (school, isbn) if isbn present, else (school, title, author).
"""

from __future__ import annotations

from typing import Any, Iterator

from ._helpers import (
    coerce_int,
    filter_to_model_fields,
    model_field_names,
    record_id_mapping,
)
from .base import Lander, LanderContext, LanderError, LanderResult, register


class LibraryLander(Lander):
    domain = "library"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        try:
            from apps.schoolops.models import LibraryItem
        except ImportError as exc:
            raise LanderError(
                f"LibraryLander could not import target models: {exc!s}"
            ) from exc

        result = LanderResult()
        i_fields = model_field_names(LibraryItem)

        for row in canonical_rows:
            title = (row.get("title") or "").strip()
            isbn = (row.get("isbn") or "").strip()
            author = (row.get("author") or "").strip()
            if not title:
                result.quarantined += 1
                result.errors.append(
                    f"library: missing title in {row!r}"
                )
                continue

            copies = coerce_int(row.get("copies_total")) or 1
            defaults: dict[str, Any] = {"title": title[:255]}
            if "author" in i_fields and author:
                defaults["author"] = author[:255]
            if "isbn" in i_fields and isbn:
                defaults["isbn"] = isbn[:32]
            if "item_type" in i_fields:
                defaults["item_type"] = (row.get("category") or row.get("item_type") or "book").strip()[:32]
            if "copies_total" in i_fields:
                defaults["copies_total"] = copies
            if "is_active" in i_fields:
                status = (row.get("status") or "available").strip().lower()
                defaults["is_active"] = status not in ("retired", "lost")
            if "school" in i_fields and ctx.school is not None:
                defaults["school"] = ctx.school
            defaults = filter_to_model_fields(defaults, LibraryItem)

            lookup_kwargs: dict[str, Any] = {}
            if "school" in i_fields and ctx.school is not None:
                lookup_kwargs["school"] = ctx.school
            if isbn and "isbn" in i_fields:
                lookup_kwargs["isbn"] = isbn[:32]
            else:
                lookup_kwargs["title"] = title[:255]
                if author and "author" in i_fields:
                    lookup_kwargs["author"] = author[:255]

            if ctx.dry_run:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-lander-orchestrator
                exists = LibraryItem.objects.filter(**lookup_kwargs).exists()
                result.updated += 1 if exists else 0
                result.created += 0 if exists else 1
                continue
            try:
                from ._helpers import upsert_with_conflict_detection
                _lb_legacy = row.get("item_external_id") or isbn or f"{title}:{author}"
                obj, created, preserved = upsert_with_conflict_detection(
                    ctx=ctx, domain="library", model=LibraryItem,
                    lookup=lookup_kwargs, defaults=defaults, legacy_id=_lb_legacy,
                )
                if preserved:
                    result.skipped += 1
                    record_id_mapping(ctx=ctx, legacy_id=_lb_legacy, canonical_obj=obj, domain="library")
                    continue
                if created:
                    result.created += 1
                    result.created_ids.append(obj.pk)
                else:
                    result.updated += 1
                    result.updated_ids_with_old_values.append(
                        {"pk": obj.pk, "old": {k: getattr(obj, k, None) for k in defaults}}
                    )
                record_id_mapping(
                    ctx=ctx,
                    legacy_id=_lb_legacy,
                    canonical_obj=obj, domain="library",
                )
            except Exception as exc:  # noqa: BLE001
                result.quarantined += 1
                result.errors.append(
                    f"library upsert failed for {title!r}: {type(exc).__name__}: {exc}"
                )
        return result


register("library", LibraryLander())
