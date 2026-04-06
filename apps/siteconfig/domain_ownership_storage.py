"""
Physical storage classification for ``EXACT_FIELD_OWNERS`` keys (Phase B / Batch 14+ discipline).

Every key in ``domain_ownership.EXACT_FIELD_OWNERS`` must be exactly one of:

* **Typed RuntimeDefaults column** - name appears in ``RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES``
  (see ``runtime_defaults_first_class.py``); authoritative platform defaults, merge order in
  ``get_effective_site_settings``.
* **Virtual-only** - still exposed on the effective tenant-settings facade but not a first-class column
  (file field, payload-only, or pending typed migration). Listed in ``VIRTUAL_ONLY_EXACT_FIELDS``.
* **Row metadata** - ``owner == "delete"`` (today: ``updated_at`` on the slim tenant settings row).

Gate: ``scripts/verify_domain_ownership_exact_storage.py`` (also ``pre_deploy_gate`` via
``verify_phase_5_siteconfig.py``).
"""

from __future__ import annotations

from typing import Final

# EXACT_FIELD_OWNERS keys that are not RuntimeDefaults first-class columns (yet).
# Keep in sync with tenant-settings virtual surface / PGB / payload (see SITECONFIG_OWNERSHIP_MIGRATION.md).
VIRTUAL_ONLY_EXACT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "auto_tag_photos_from_exif",
        "favicon",
        "teacher_reminder_time_of_day",
    }
)


def collect_exact_field_storage_errors(
    *,
    exact_field_owners: dict[str, str],
    first_class_field_names: frozenset[str],
    virtual_only_exact: frozenset[str],
) -> list[str]:
    """Return human-readable errors if the registry is incomplete or inconsistent."""
    errors: list[str] = []
    overlap = sorted(first_class_field_names & virtual_only_exact)
    for field in overlap:
        errors.append(
            f"Storage registry overlap: {field!r} appears in both "
            "RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES and VIRTUAL_ONLY_EXACT_FIELDS."
        )

    for field, owner in exact_field_owners.items():
        is_first_class = field in first_class_field_names
        is_virtual_only = field in virtual_only_exact

        if owner == "delete":
            if field != "updated_at":
                errors.append(
                    f'EXACT_FIELD_OWNERS[{field!r}] uses owner "delete" but only '
                    '"updated_at" is allowed for row metadata.'
                )
            if is_first_class:
                errors.append(
                    f"EXACT_FIELD_OWNERS[{field!r}] is row metadata but is also "
                    "registered as a RuntimeDefaults first-class column."
                )
            if is_virtual_only:
                errors.append(
                    f"EXACT_FIELD_OWNERS[{field!r}] is row metadata but is also "
                    "listed in VIRTUAL_ONLY_EXACT_FIELDS."
                )
            continue

        if is_first_class and is_virtual_only:
            errors.append(
                f"EXACT_FIELD_OWNERS[{field!r}] is classified as both a "
                "RuntimeDefaults first-class column and a virtual-only field."
            )
            continue

        if is_first_class or is_virtual_only:
            continue

        errors.append(
            f"EXACT_FIELD_OWNERS[{field!r}] (owner={owner!r}) is neither a "
            "RuntimeDefaults first-class column nor listed in "
            "domain_ownership_storage.VIRTUAL_ONLY_EXACT_FIELDS - add column + "
            "RUNTIME_DEFAULTS_FIRST_CLASS_* or register virtual key."
        )

    for field in virtual_only_exact:
        if field not in exact_field_owners:
            errors.append(
                f"VIRTUAL_ONLY_EXACT_FIELDS contains {field!r} missing from EXACT_FIELD_OWNERS"
            )

    return errors
