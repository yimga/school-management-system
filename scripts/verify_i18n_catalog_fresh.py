#!/usr/bin/env python3
"""
Fail if locale/en/LC_MESSAGES/django.po is missing any string found by the i18n scanner.

Run after template/Python changes; fix with:
  python manage.py sync_i18n_catalog --compile

  --warn-stale   print msgids in .po but not in codebase (advisory)
  --strict-stale exit 1 if any stale entries exist (optional hygiene)

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Ratchet baseline for the CI-tier (`--compare`) mode. The DEFAULT invocation
# stays binary (any scanned string missing from en.po -> exit 1) because the
# deploy gate (`scripts/pre_deploy_gate.sh`) and the self-heal / plan-deliverable
# meta-gates depend on that contract. `--compare` is the additive, per-push
# early-warning tier: it fails only on a msgid that is missing NOW and was NOT
# in the frozen baseline set -- i.e. a genuinely NEW wrapped-but-unextracted
# string -- with `--update-baseline` as the standard, auditable escape hatch
# (mirrors scan_untranslated_template_text.py / scan_upload_validation_coverage.py).
BASELINE_PATH = ROOT / "var" / "security-audit-baseline-i18n-catalog-fresh.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify en django.po covers scanned strings")
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (default: this repository root)",
    )
    parser.add_argument(
        "--warn-stale",
        action="store_true",
        help="Print msgids present in .po but not found by scanner",
    )
    parser.add_argument(
        "--strict-stale",
        action="store_true",
        help="Exit 1 when stale entries exist (use after --prune-stale or manual cleanup)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Ratchet mode: fail only on NEW missing msgids vs the baseline (per-push CI tier).",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Freeze the current missing-msgid set as the --compare baseline, then exit 0.",
    )
    parser.add_argument(
        "--baseline",
        default=str(BASELINE_PATH),
        help="Baseline JSON path for --compare / --update-baseline.",
    )
    return parser


def _load_baseline_missing(path: Path) -> set[str] | None:
    """Return the frozen missing-msgid set, or None if the baseline is absent."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return set(data.get("missing", []))


def _write_baseline(path: Path, missing: set[str]) -> None:
    payload = {
        "finding_count": len(missing),
        "missing": sorted(missing),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "en django.po must cover every scanned translatable string. Ratchet: "
            "a msgid missing from en.po that is NOT in this baseline fails --compare. "
            "Fix with `python manage.py sync_i18n_catalog` (then commit locale/); "
            "re-freeze deliberately with --update-baseline."
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    return _build_parser().parse_args(argv)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def _configure_django(root: Path) -> None:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_i18n_catalog_fresh: {exc}", file=sys.stderr)
        return 1

    _configure_django(root)

    from apps.siteconfig.i18n_catalog_builder import verify_en_catalog_against_codebase

    missing, stale = verify_en_catalog_against_codebase(root)
    baseline_path = Path(args.baseline).resolve()

    # --- Freeze the current missing set as the ratchet baseline, then stop. ---
    if args.update_baseline:
        _write_baseline(baseline_path, missing)
        print(
            f"Wrote baseline -> {baseline_path} ({len(missing)} missing msgid(s) frozen)."
        )
        return 0

    # --- Ratchet (per-push CI) mode: fail only on NEW missing vs baseline. ---
    if args.compare:
        frozen = _load_baseline_missing(baseline_path)
        if frozen is None:
            print(
                f"FAIL: --compare needs a baseline at {baseline_path}; run "
                "verify_i18n_catalog_fresh.py --update-baseline first.",
                file=sys.stderr,
            )
            return 1
        new_missing = sorted(missing - frozen)
        if new_missing:
            print(
                f"FAIL: {len(new_missing)} NEW translatable string(s) wrapped but not "
                "extracted into locale/en/LC_MESSAGES/django.po (missing beyond the "
                "frozen baseline):",
                file=sys.stderr,
            )
            print(
                "Fix: python manage.py sync_i18n_catalog  (then commit locale/); "
                "or re-freeze deliberately with verify_i18n_catalog_fresh.py "
                "--update-baseline.",
                file=sys.stderr,
            )
            for m in new_missing[:40]:
                print(f"  {m[:120]!r}", file=sys.stderr)
            if len(new_missing) > 40:
                print(f"  ... and {len(new_missing) - 40} more", file=sys.stderr)
            return 1
        healed = len(frozen) - len(missing & frozen)
        note = f" ({healed} baselined gap(s) since closed)" if healed else ""
        print(
            f"OK: no NEW scanned strings missing from en django.po vs baseline"
            f"{note}."
        )
        return 0

    # --- Default (binary, deploy-gate) mode: any missing string fails. ---
    if missing:
        print(
            f"FAIL: {len(missing)} scanned strings missing from locale/en/LC_MESSAGES/django.po",
            file=sys.stderr,
        )
        print("Fix: python manage.py sync_i18n_catalog --compile", file=sys.stderr)
        for m in sorted(missing)[:40]:
            print(f"  {m[:120]!r}", file=sys.stderr)
        if len(missing) > 40:
            print(f"  ... and {len(missing) - 40} more", file=sys.stderr)
        return 1

    if args.warn_stale or args.strict_stale:
        if stale:
            print(f"INFO: {len(stale)} msgids in .po not seen by scanner (stale / manual).")
            if args.warn_stale:
                for s in sorted(stale)[:25]:
                    print(f"  {s[:120]!r}")
                if len(stale) > 25:
                    print(f"  ... and {len(stale) - 25} more")
            if args.strict_stale:
                return 1
        else:
            print("INFO: no stale .po entries vs scanner.")

    print("OK: en django.po covers all scanned translatable strings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
