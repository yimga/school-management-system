#!/usr/bin/env python
"""Stratified human-review sample of # tenant-isolation-allow: markers.

Mechanical gates (``scan_tenant_queryset_safety.py`` count + marker quality) stay
at baseline 0. This script produces an operator-facing audit artifact for periodic
human review of allowlisted cross-tenant queries — not a CI failure gate.

Modes:
  Default: print summary to stdout, exit 0.
  ``--write``: write ``docs/generated/tenant_isolation_marker_audit_sample.json``.
  ``--check``: exit 1 when the artifact is missing, stale vs live marker count,
    or older than ``--max-age-days`` (default 90).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import re
import sys
import tokenize
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "docs" / "generated" / "tenant_isolation_marker_audit_sample.json"
SEARCH_ROOTS = [REPO_ROOT / "apps", REPO_ROOT / "services", REPO_ROOT / "config"]
_MARKER_RE = re.compile(r"#\s*tenant-isolation-allow:\s*(?P<reason>.*?)\s*$")


@dataclass(frozen=True)
class MarkerSite:
    path: str
    lineno: int
    reason: str
    app: str


def _app_bucket(rel_path: str) -> str:
    parts = Path(rel_path).parts
    if parts and parts[0] == "apps" and len(parts) > 1:
        return parts[1]
    if parts and parts[0] in {"services", "config"}:
        return parts[0]
    return "other"


def _collect_markers() -> list[MarkerSite]:
    out: list[MarkerSite] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            if any(p in py.parts for p in ("__pycache__", "node_modules", "migrations")):
                continue
            rel = py.relative_to(REPO_ROOT).as_posix()
            try:
                source = py.read_text(encoding="utf-8")
            except OSError:
                continue
            for tok in tokenize.generate_tokens(io.StringIO(source).readline):
                if tok.type != tokenize.COMMENT:
                    continue
                match = _MARKER_RE.search(tok.string)
                if not match:
                    continue
                reason = match.group("reason").strip()
                out.append(
                    MarkerSite(
                        path=rel,
                        lineno=tok.start[0],
                        reason=reason,
                        app=_app_bucket(rel),
                    )
                )
    out.sort(key=lambda m: (m.app, m.path, m.lineno))
    return out


def _stratified_sample(
    markers: list[MarkerSite],
    *,
    per_app: int,
    seed: int,
) -> list[MarkerSite]:
    by_app: dict[str, list[MarkerSite]] = defaultdict(list)
    for m in markers:
        by_app[m.app].append(m)
    rng = random.Random(seed)
    sample: list[MarkerSite] = []
    for app in sorted(by_app):
        bucket = by_app[app]
        if len(bucket) <= per_app:
            sample.extend(bucket)
            continue
        # Prefer one marker per distinct reason prefix, then fill randomly.
        by_reason: dict[str, list[MarkerSite]] = defaultdict(list)
        for site in bucket:
            key = site.reason.split()[0] if site.reason else ""
            by_reason[key].append(site)
        picked: list[MarkerSite] = []
        for reason_key in sorted(by_reason):
            if len(picked) >= per_app:
                break
            picked.append(rng.choice(by_reason[reason_key]))
        remaining = [m for m in bucket if m not in picked]
        rng.shuffle(remaining)
        for site in remaining:
            if len(picked) >= per_app:
                break
            picked.append(site)
        sample.extend(sorted(picked, key=lambda m: (m.path, m.lineno)))
    return sample


def _build_report(markers: list[MarkerSite], *, per_app: int, seed: int) -> dict:
    reason_counts = Counter(m.reason for m in markers)
    app_counts = Counter(m.app for m in markers)
    sample = _stratified_sample(markers, per_app=per_app, seed=seed)
    digest = hashlib.sha256(
        json.dumps([asdict(m) for m in markers], sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scanner": "sample_tenant_isolation_marker_audit.py",
        "total_marker_count": len(markers),
        "distinct_reason_count": len(reason_counts),
        "distinct_app_count": len(app_counts),
        "content_digest_sha256_prefix": digest,
        "sample_per_app": per_app,
        "sample_seed": seed,
        "sample_count": len(sample),
        "app_totals": dict(sorted(app_counts.items())),
        "top_reasons": [
            {"reason": reason, "count": count}
            for reason, count in reason_counts.most_common(25)
        ],
        "sample": [asdict(m) for m in sample],
        "review_prompt": (
            "For each sample row: confirm the queryset is intentionally cross-tenant "
            "or scoped upstream (request.school / schema_context). Flag markers whose "
            "reason does not match the query at that line."
        ),
    }


def _write_report(report: dict) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _check_report(report: dict, *, max_age_days: int) -> list[str]:
    errors: list[str] = []
    live = _collect_markers()
    live_count = len(live)
    stored = int(report.get("total_marker_count") or 0)
    if stored != live_count:
        errors.append(
            f"total_marker_count drift: artifact={stored} live={live_count} "
            f"(re-run with --write)"
        )
    live_digest = hashlib.sha256(
        json.dumps([asdict(m) for m in live], sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    if report.get("content_digest_sha256_prefix") != live_digest:
        errors.append(
            f"content digest drift: artifact={report.get('content_digest_sha256_prefix')} "
            f"live={live_digest} (re-run with --write)"
        )
    try:
        generated = datetime.fromisoformat(str(report.get("generated_at", "")))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - generated).days
        if age_days > max_age_days:
            errors.append(
                f"artifact age {age_days}d exceeds max_age_days={max_age_days} "
                f"(re-run with --write)"
            )
    except (TypeError, ValueError):
        errors.append("generated_at missing or invalid")
    if not report.get("sample"):
        errors.append("sample array is empty")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write audit sample JSON.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify artifact freshness vs live marker inventory.",
    )
    parser.add_argument(
        "--per-app",
        type=int,
        default=3,
        help="Max sample rows per app bucket (default 3).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=1707,
        help="RNG seed for reproducible sampling (default 1707).",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=90,
        help="--check fails when artifact is older than this many days.",
    )
    args = parser.parse_args()

    markers = _collect_markers()
    report = _build_report(markers, per_app=max(1, args.per_app), seed=args.seed)

    if args.write:
        _write_report(report)
        print(
            f"TENANT_ISOLATION_MARKER_AUDIT_SAMPLE_WRITTEN "
            f"total={report['total_marker_count']} sample={report['sample_count']} "
            f"-> {OUTPUT_PATH.relative_to(REPO_ROOT)}"
        )
        return 0

    if args.check:
        if not OUTPUT_PATH.exists():
            print(f"ERROR: missing {OUTPUT_PATH.relative_to(REPO_ROOT)}", file=sys.stderr)
            return 1
        stored = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        errors = _check_report(stored, max_age_days=args.max_age_days)
        if errors:
            for err in errors:
                print(f"STALE: {err}", file=sys.stderr)
            return 1
        print(
            f"TENANT_ISOLATION_MARKER_AUDIT_SAMPLE_OK "
            f"total={stored['total_marker_count']} sample={stored['sample_count']}"
        )
        return 0

    print(
        f"tenant-isolation markers: total={report['total_marker_count']} "
        f"apps={report['distinct_app_count']} reasons={report['distinct_reason_count']}"
    )
    print(
        f"sample (per_app={report['sample_per_app']}): {report['sample_count']} rows "
        f"(run --write to materialize {OUTPUT_PATH.relative_to(REPO_ROOT)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
