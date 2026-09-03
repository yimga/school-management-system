from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

READINESS_STATUSES = frozenset(
    {
        "regional_fallback_only",
        "localization_ready",
        "education_model_ready",
        "configuration_ready",
        "repo_ready",
        "internal_pilot_ready",
        "external_validation_required",
    }
)


def _classify_iso(
    iso: str,
    *,
    has_baseline: bool,
    has_localization: bool,
    has_premium_profile: bool,
) -> str:
    if has_premium_profile:
        return "repo_ready"
    if has_localization:
        return "education_model_ready"
    if has_baseline:
        return "localization_ready"
    return "regional_fallback_only"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    failures: list[str] = []

    gov_path = ROOT / "docs" / "generated" / "country_governance_matrix.json"
    if not gov_path.is_file():
        failures.append("missing country_governance_matrix.json")
        print("verify_tenant_customer_250_country_matrix: FAIL")
        for f in failures:
            print(f"- {f}")
        return 1

    gov = json.loads(gov_path.read_text(encoding="utf-8"))
    rows = gov.get("rows") or []
    iso_list = sorted(
        {
            str(row.get("iso_alpha2") or row.get("country_code") or "").upper()[:2]
            for row in rows
            if isinstance(row, dict)
        }
        - {""}
    )

    if len(iso_list) < 249:
        failures.append(f"expected >= 249 ISO rows, got {len(iso_list)}")

    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(ROOT))

    import django

    django.setup()

    from apps.siteconfig.country_experience_baselines import list_country_experience_baselines
    from apps.siteconfig.local_experience_profiles import list_profiles

    baselines = {row.country_code.upper() for row in list_country_experience_baselines()}
    premium = {
        str(row.get("country") or "").upper()[:2]
        for row in list_profiles()
        if row.get("country")
    }

    loc_text = (
        ROOT / "apps" / "siteconfig" / "_seed_country_localization.py"
    ).read_text(encoding="utf-8")

    matrix_rows: list[dict] = []
    for iso in iso_list:
        has_baseline = iso in baselines
        has_loc = f'"{iso}"' in loc_text or f"'{iso}'" in loc_text
        has_profile = iso in premium
        status = _classify_iso(
            iso,
            has_baseline=has_baseline,
            has_localization=has_loc,
            has_premium_profile=has_profile,
        )
        if status not in READINESS_STATUSES:
            failures.append(f"invalid readiness status for {iso}: {status}")
        matrix_rows.append({"iso": iso, "readiness_status": status})

    out_path = ROOT / "docs" / "generated" / "tenant_customer_250_country_matrix.json"
    # write_bytes, not write_text: on Windows text mode translates "\n" to CRLF, and
    # docs/generated/*.json is `eol=lf`, so every run left the path permanently dirty
    # ("git diff-files" reports it modified even though the content is identical).
    out_path.write_bytes(
        (
            json.dumps(
                {
                    "iso_count": len(matrix_rows),
                    "readiness_statuses": sorted(READINESS_STATUSES),
                    "rows": sorted(matrix_rows, key=lambda row: row["iso"]),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    )

    repo_ready = sum(1 for r in matrix_rows if r["readiness_status"] == "repo_ready")
    if repo_ready < 1:
        failures.append("expected at least one repo_ready premium profile country")

    if failures:
        print("verify_tenant_customer_250_country_matrix: FAIL")
        for f in failures:
            print(f"- {f}")
        return 1

    print(
        "verify_tenant_customer_250_country_matrix: "
        f"TENANT_CUSTOMER_250_COUNTRY_MATRIX_PASS ({len(matrix_rows)} ISO, "
        f"{repo_ready} repo_ready)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
