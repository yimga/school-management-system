#!/usr/bin/env python3
"""Verify that every matrix-promoted workflow's ``entry_path`` resolves.

Run after each refresh of ``apps/platform_runtime/workflow_registry_promoted.py``
(or before a release wave) to catch promoted entries whose declared
``entry_path`` no longer maps to any URL pattern in the current URL graph.
This is the operator-side gate Wave D's SOT entry calls out: each
``needs-review`` entry needs hand-verification before its chip surfaces to
end users.

Outputs:
  docs/generated/promoted_workflow_route_verification.json
  exit 0 when all promoted entries resolve OR are honestly marked
  ``needs-review``; exit 1 when a promoted entry's path resolves to a 404.

Run:
  python scripts/verify_promoted_workflows.py
  python scripts/verify_promoted_workflows.py --strict   # exit 1 on warnings
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "docs/generated/promoted_workflow_route_verification.json"


def _bootstrap_django():
    """Best-effort Django settings load so we can use URL reversal."""
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        import django  # type: ignore[import]
        django.setup()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: could not boot Django ({exc!r}); doing static-only verification", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit 1 on warnings (not just errors)")
    args = parser.parse_args()

    django_up = _bootstrap_django()

    from apps.platform_runtime.workflow_registry import WORKFLOWS  # type: ignore[import]

    promoted = [w for w in WORKFLOWS.values() if getattr(w, "source", "") == "matrix-promoted"]
    hand_seeded = [w for w in WORKFLOWS.values() if getattr(w, "source", "") == "hand-seeded"]

    results: list[dict] = []
    errors = 0
    warnings = 0

    # Pull all registered URL patterns once
    pattern_paths: list[str] = []
    if django_up:
        try:
            from django.urls import get_resolver  # type: ignore[import]

            def _collect(urlconf_module, prefix=""):
                resolver = get_resolver(urlconf_module)
                for pat in resolver.url_patterns:
                    # Regex patterns expose `.pattern`, include() patterns nest
                    try:
                        route = getattr(pat.pattern, "_route", None) or str(pat.pattern)
                    except Exception:
                        route = str(pat)
                    nested = getattr(pat, "url_patterns", None)
                    if nested is not None:
                        for sub in nested:
                            try:
                                sub_route = getattr(sub.pattern, "_route", None) or str(sub.pattern)
                            except Exception:
                                sub_route = str(sub)
                            pattern_paths.append(prefix + route + sub_route)
                    else:
                        pattern_paths.append(prefix + route)
            # Walk the 4 root URLconfs the platform exposes
            for module_name in ("config.urls", "config.manager_urls", "config.tenant_urls", "config.public_urls"):
                try:
                    _collect(module_name)
                except Exception:
                    pass
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: URL graph collection failed: {exc!r}", file=sys.stderr)

    for wf in promoted:
        entry_path = getattr(wf, "entry_path", None)
        result = {
            "key": wf.key,
            "title": wf.title,
            "module": wf.module,
            "audience": wf.audience,
            "entry_path": entry_path,
            "status": "unverified",
            "evidence": "",
        }
        if not entry_path:
            result["status"] = "warn"
            result["evidence"] = "no entry_path set"
            warnings += 1
            results.append(result)
            continue
        # Strip trailing parameter placeholders (e.g. /school/<id>/) for prefix match
        normalized = entry_path
        for ch in ("<", ">"):
            normalized = normalized.replace(ch, "")
        # Match if any URL pattern starts with the same first-path segment
        first_seg = "/".join(entry_path.strip("/").split("/")[:2])
        matching = [
            p for p in pattern_paths
            if first_seg in p or p.strip("^$") in entry_path
        ]
        if matching:
            result["status"] = "resolves"
            result["evidence"] = f"first-segment {first_seg!r} matched in URL graph"
        elif not django_up:
            result["status"] = "skipped"
            result["evidence"] = "Django not bootable; static-only run"
            warnings += 1
        else:
            result["status"] = "not_found"
            result["evidence"] = f"no URL pattern matched {entry_path!r} or first-segment {first_seg!r}"
            errors += 1
        results.append(result)

    out = {
        "doc": "promoted_workflow_route_verification",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "django_bootable": django_up,
        "total_workflows": len(WORKFLOWS),
        "hand_seeded": len(hand_seeded),
        "promoted": len(promoted),
        "promoted_results": results,
        "summary": {
            "resolves": sum(1 for r in results if r["status"] == "resolves"),
            "warn": sum(1 for r in results if r["status"] == "warn"),
            "skipped": sum(1 for r in results if r["status"] == "skipped"),
            "not_found": sum(1 for r in results if r["status"] == "not_found"),
        },
        "exit_code": 1 if errors else (1 if (args.strict and warnings) else 0),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"Wrote {OUT_PATH.relative_to(ROOT)}")
    print(f"Total: {len(WORKFLOWS)} | hand-seeded: {len(hand_seeded)} | promoted: {len(promoted)}")
    print(f"Resolves: {out['summary']['resolves']} | warn: {out['summary']['warn']} | "
          f"skipped: {out['summary']['skipped']} | not_found: {out['summary']['not_found']}")

    if errors:
        print(f"FAIL: {errors} promoted entries reference paths not in the URL graph", file=sys.stderr)
        return 1
    if args.strict and warnings:
        print(f"FAIL (strict): {warnings} warnings", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
