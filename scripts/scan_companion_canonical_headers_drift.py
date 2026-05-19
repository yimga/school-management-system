"""Scan: detect drift between Django ``DOMAIN_CANONICAL_HEADERS`` SOT and the
JSON mirrors carried by the companion siblings.

Background
----------
The 23-domain canonical-headers contract lives in Django at::

    apps/migration_cloud/accelerators/runmycampus_canonical.py
        :: DOMAIN_CANONICAL_HEADERS

Each companion sibling ships a JSON mirror of the same data so the
sibling can drive its own canonical-CSV ingest WITHOUT loading the
Django runtime::

    companion-tauri/src-tauri/src/canonical_headers.json   (embedded via Rust include_str!)
    companion-docker/app/canonical_headers.json

Without a CI gate the JSON mirrors can silently drift from the Django
SOT — a maintainer adds a new canonical column in Django, the sibling
keeps the old shape, and client-side canonical mappings start producing
silently wrong results.

This scanner is the gate.

What it checks
--------------
For every domain ``D`` in the Django SOT:

  * ``D`` appears in BOTH ``companion-tauri/.../canonical_headers.json``
    and ``companion-docker/app/canonical_headers.json``.
  * The canonical-column list for ``D`` is IDENTICAL between the SOT and
    each mirror. Order matters — column order is load-bearing for
    canonical-CSV canonicalization (deterministic hashing client-side).

For every domain in either JSON that is NOT in the Django SOT: also a
violation (stale companion data).

Allow marker
------------
Either JSON file may carry a top-level escape hatch in TWO forms:

  1. JSON-native (preferred — JSON has no native comments)::

         "_canonical-headers-drift-allow": {
             "<domain>": "<reason>"
         }

  2. A leading ``// canonical-headers-drift-allow: <domain> -- <reason>``
     line at the very top of the file (the loader strips leading ``//``
     comments before passing to ``json.loads``). Multiple lines may stack.

When the scanner sees a matched domain it skips drift comparison for
that domain in the file it was declared in. Use sparingly — the only
legitimate use is a transient deprecation window where one mirror is
being intentionally rotated behind the other.

Constraints
-----------
This scanner is stdlib-only by design (``ast``, ``json``, ``pathlib``,
``argparse``, ``sys``) so it can run as a lightweight CI gate without
booting Django. It DOES NOT import the Django app — it parses the
``DOMAIN_CANONICAL_HEADERS`` literal via the ``ast`` module.

Note on order semantics
-----------------------
The Django SOT type annotation is ``dict[str, set[str]]`` (set
literals). The JSON mirror is an ordered list. Set literals in Python
source nonetheless have a deterministic source order (the order the
maintainer wrote them in). The scanner uses that source-order via
``ast.Set.elts`` so it can compare ORDER-SENSITIVE against the JSON
list. When a domain is later promoted to a tuple/list literal in the
SOT the scanner continues to work because we accept any iterable AST
node (``ast.Set`` / ``ast.List`` / ``ast.Tuple``).

Usage::

    python scripts/scan_companion_canonical_headers_drift.py
    python scripts/scan_companion_canonical_headers_drift.py --json
    python scripts/scan_companion_canonical_headers_drift.py --strict

Exit codes::

    0  all mirrors identical to SOT
    1  drift detected (only when ``--strict`` or when run without flags)

CLAUDE.md scanner-table row (consolidator will add to the table later)::

    | `scan_companion_canonical_headers_drift.py` | **0** (v3.39.0 introduction 2026-05-19 — zero-tolerance from day 1; baseline 0 at first scan after Agent 3 verified Django SOT + 2 JSON mirrors all 23 domains identical) | architectural-boundaries.yml::canonical-headers-drift | Sister gate to v3.38.0 Agent 2 per-vendor CSV pre-processors. Both companion-tauri and companion-docker carry JSON mirrors of `apps/migration_cloud/accelerators/runmycampus_canonical.py::DOMAIN_CANONICAL_HEADERS`. Mirror drift = silently wrong canonical mappings client-side. Scanner asserts byte-identical domain -> canonical-column-list mapping (order-sensitive). |
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import sys
from typing import Any


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

DJANGO_SOT_PATH = (
    REPO_ROOT
    / "apps"
    / "migration_cloud"
    / "accelerators"
    / "runmycampus_canonical.py"
)
TAURI_MIRROR_PATH = (
    REPO_ROOT
    / "companion-tauri"
    / "src-tauri"
    / "src"
    / "canonical_headers.json"
)
DOCKER_MIRROR_PATH = (
    REPO_ROOT / "companion-docker" / "app" / "canonical_headers.json"
)
BASELINE_PATH = (
    REPO_ROOT
    / "var"
    / "security-audit-baseline-canonical-headers-drift.json"
)

SOT_DICT_NAME = "DOMAIN_CANONICAL_HEADERS"
ALLOW_KEY = "_canonical-headers-drift-allow"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_django_sot(path: pathlib.Path) -> dict[str, list[str]]:
    """AST-parse the Django module and extract ``DOMAIN_CANONICAL_HEADERS``.

    Returns a ``{domain: [column, column, ...]}`` mapping using source
    order from the dict / set / list / tuple literal.
    """
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    for node in tree.body:
        # Module-level assignment: ``DOMAIN_CANONICAL_HEADERS: ... = {...}``
        # or ``DOMAIN_CANONICAL_HEADERS = {...}``.
        target_names: list[str] = []
        value_node: ast.AST | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = [node.target.id]
            value_node = node.value
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    target_names.append(t.id)
            value_node = node.value
        if SOT_DICT_NAME not in target_names or value_node is None:
            continue
        if not isinstance(value_node, ast.Dict):
            raise CanonicalHeadersDriftScanError(
                f"{path}: {SOT_DICT_NAME} is not a dict literal"
            )
        result: dict[str, list[str]] = {}
        for key_node, val_node in zip(value_node.keys, value_node.values):
            if not isinstance(key_node, ast.Constant) or not isinstance(
                key_node.value, str
            ):
                raise CanonicalHeadersDriftScanError(
                    f"{path}: {SOT_DICT_NAME} key is not a string literal"
                )
            domain = key_node.value
            columns = _extract_iterable_of_strings(val_node, path, domain)
            result[domain] = columns
        return result
    raise CanonicalHeadersDriftScanError(
        f"{path}: did not find module-level assignment of {SOT_DICT_NAME}"
    )


def _extract_iterable_of_strings(
    node: ast.AST, path: pathlib.Path, domain: str
) -> list[str]:
    """Pull a Python iterable of string literals out of an AST node.

    Accepts ``ast.Set``, ``ast.List``, ``ast.Tuple``. Preserves source
    order (which is what set literals carry too — Python's set literal
    parser keeps source order in ``elts``).
    """
    if not isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        raise CanonicalHeadersDriftScanError(
            f"{path}: {SOT_DICT_NAME}[{domain!r}] value is not a set/list/tuple literal"
        )
    out: list[str] = []
    for elt in node.elts:
        if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
            raise CanonicalHeadersDriftScanError(
                f"{path}: {SOT_DICT_NAME}[{domain!r}] contains non-string element"
            )
        out.append(elt.value)
    return out


_HEADER_COMMENT_MARKER = "canonical-headers-drift-allow:"


def _strip_leading_line_comments(text: str) -> tuple[str, dict[str, str]]:
    """Strip leading ``//``-prefixed comment lines from a JSON text.

    Any leading comment line matching ``// canonical-headers-drift-allow:
    <domain> -- <reason>`` (or ``: <domain> <reason>``) contributes an
    entry to the returned ``allow`` dict. The returned ``text`` is safe
    to pass to ``json.loads``.
    """
    allow: dict[str, str] = {}
    lines = text.splitlines(keepends=True)
    consumed = 0
    for line in lines:
        stripped = line.lstrip()
        if not stripped.startswith("//"):
            break
        comment_body = stripped[2:].strip()
        if _HEADER_COMMENT_MARKER in comment_body:
            payload = comment_body.split(_HEADER_COMMENT_MARKER, 1)[1].strip()
            # Split on " -- " preferred, else first whitespace.
            if " -- " in payload:
                dom, reason = payload.split(" -- ", 1)
            else:
                parts = payload.split(None, 1)
                dom = parts[0] if parts else ""
                reason = parts[1] if len(parts) > 1 else ""
            dom = dom.strip()
            if dom:
                allow[dom] = reason.strip()
        consumed += len(line)
    return text[consumed:], allow


def load_json_mirror(
    path: pathlib.Path,
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Load a companion sibling's canonical_headers.json.

    Returns ``(mirror, allow_markers)`` where ``mirror`` is the
    ``{domain: [column, ...]}`` mapping with metadata keys stripped, and
    ``allow_markers`` is the parsed allow block (``{domain: reason}``)
    or empty dict. Allow entries can come from either a top-level
    ``_canonical-headers-drift-allow`` JSON object OR a leading line
    comment ``// canonical-headers-drift-allow: <domain> -- <reason>``.
    """
    raw_text = path.read_text(encoding="utf-8")
    cleaned_text, header_allow = _strip_leading_line_comments(raw_text)
    raw = json.loads(cleaned_text)
    if not isinstance(raw, dict):
        raise CanonicalHeadersDriftScanError(
            f"{path}: top-level value is not a JSON object"
        )
    allow: dict[str, str] = dict(header_allow)
    if ALLOW_KEY in raw:
        allow_block = raw.get(ALLOW_KEY)
        if not isinstance(allow_block, dict):
            raise CanonicalHeadersDriftScanError(
                f"{path}: {ALLOW_KEY} is present but is not an object"
            )
        for d, reason in allow_block.items():
            if not isinstance(d, str) or not isinstance(reason, str):
                raise CanonicalHeadersDriftScanError(
                    f"{path}: {ALLOW_KEY}[{d!r}] reason is not a string"
                )
            allow[d] = reason
    mirror: dict[str, list[str]] = {}
    for key, value in raw.items():
        if key == ALLOW_KEY:
            continue
        # Metadata keys (those starting with "_") are ignored. They are
        # typically a "_comment" describing the file.
        if key.startswith("_"):
            continue
        if not isinstance(value, list):
            raise CanonicalHeadersDriftScanError(
                f"{path}: domain {key!r} value is not a JSON array"
            )
        cols: list[str] = []
        for v in value:
            if not isinstance(v, str):
                raise CanonicalHeadersDriftScanError(
                    f"{path}: domain {key!r} contains non-string element"
                )
            cols.append(v)
        mirror[key] = cols
    return mirror, allow


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


class CanonicalHeadersDriftScanError(RuntimeError):
    """Raised when the scanner cannot load or parse one of its inputs."""


def classify_drift(
    sot_cols: list[str] | None, mirror_cols: list[str] | None
) -> str:
    """Return one of: identical / missing-in-mirror / extra-in-mirror /
    order-mismatch / column-set-mismatch.
    """
    if sot_cols is None and mirror_cols is not None:
        return "extra-in-mirror"
    if sot_cols is not None and mirror_cols is None:
        return "missing-in-mirror"
    # Both non-None by elimination — explicit type narrowing instead of assert
    # so this file stays clean under ``python -O`` (scan_assert_in_production
    # zero-tolerance gate).
    if sot_cols is None or mirror_cols is None:  # pragma: no cover
        return "column-set-mismatch"
    if sot_cols == mirror_cols:
        return "identical"
    if set(sot_cols) == set(mirror_cols):
        return "order-mismatch"
    return "column-set-mismatch"


def compare_mirror(
    label: str,
    sot: dict[str, list[str]],
    mirror: dict[str, list[str]],
    allow: dict[str, str],
) -> list[dict[str, Any]]:
    """Return one row per domain (across the union of SOT and mirror)."""
    rows: list[dict[str, Any]] = []
    all_domains = sorted(set(sot.keys()) | set(mirror.keys()))
    for domain in all_domains:
        sot_cols = sot.get(domain)
        mirror_cols = mirror.get(domain)
        drift_kind = classify_drift(sot_cols, mirror_cols)
        allowed = domain in allow
        rows.append(
            {
                "mirror": label,
                "domain": domain,
                "sot_columns": sot_cols if sot_cols is not None else [],
                "mirror_columns": mirror_cols if mirror_cols is not None else [],
                "drift_kind": drift_kind,
                "allowed": allowed,
                "allow_reason": allow.get(domain, ""),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_text_report(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    header = (
        f"{'mirror':<22} {'domain':<26} {'drift_kind':<22} {'allowed':<8} reason"
    )
    lines.append(header)
    lines.append("-" * len(header))
    drifts = [r for r in rows if r["drift_kind"] != "identical"]
    show = drifts if drifts else rows[:5]
    for r in show:
        lines.append(
            f"{r['mirror']:<22} {r['domain']:<26} {r['drift_kind']:<22} "
            f"{'yes' if r['allowed'] else 'no':<8} {r['allow_reason']}"
        )
    if not drifts:
        lines.append("(no drift detected; first 5 rows shown above)")
    return "\n".join(lines)


def run() -> tuple[int, list[dict[str, Any]]]:
    """Run the scan; return ``(unallowed_drift_count, all_rows)``."""
    sot = load_django_sot(DJANGO_SOT_PATH)
    tauri_mirror, tauri_allow = load_json_mirror(TAURI_MIRROR_PATH)
    docker_mirror, docker_allow = load_json_mirror(DOCKER_MIRROR_PATH)

    rows: list[dict[str, Any]] = []
    rows.extend(compare_mirror("companion-tauri", sot, tauri_mirror, tauri_allow))
    rows.extend(
        compare_mirror("companion-docker", sot, docker_mirror, docker_allow)
    )

    unallowed_drift = sum(
        1 for r in rows if r["drift_kind"] != "identical" and not r["allowed"]
    )
    return unallowed_drift, rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 on ANY unallowed drift (zero-tolerance gate mode).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the text table.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "Overwrite the baseline JSON with the current unallowed-drift "
            "count (use only when intentionally reducing — never to silence "
            "a new drift)."
        ),
    )
    args = parser.parse_args(argv)

    try:
        unallowed_drift, rows = run()
    except CanonicalHeadersDriftScanError as exc:
        sys.stderr.write(f"scan_companion_canonical_headers_drift: {exc}\n")
        return 2

    baseline_total = 0
    if BASELINE_PATH.exists():
        try:
            baseline_total = int(
                json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get(
                    "finding_count", 0
                )
            )
        except (json.JSONDecodeError, ValueError):
            baseline_total = 0

    if args.update_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps(
                {
                    "finding_count": unallowed_drift,
                    "generated_at": "2026-05-19",
                    "generated_by": "scan_companion_canonical_headers_drift",
                    "rows": rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    if args.json:
        sys.stdout.write(
            json.dumps(
                {
                    "finding_count": unallowed_drift,
                    "baseline": baseline_total,
                    "rows": rows,
                },
                indent=2,
            )
            + "\n"
        )
    else:
        sys.stdout.write(
            f"canonical-headers-drift scan: {unallowed_drift} unallowed drift(s)\n"
        )
        sys.stdout.write(f"baseline: {baseline_total}\n")
        sys.stdout.write(_format_text_report(rows) + "\n")

    # Default exit policy: 0 if no unallowed drift; 1 otherwise.
    # ``--strict`` is currently equivalent (we're zero-tolerance from day 1)
    # but kept as an explicit affordance for parity with sibling scanners.
    if unallowed_drift > baseline_total:
        sys.stderr.write(
            f"FAIL: {unallowed_drift} unallowed drift(s) > baseline {baseline_total}\n"
        )
        return 1
    if args.strict and unallowed_drift > 0:
        sys.stderr.write(
            f"FAIL: strict mode and {unallowed_drift} unallowed drift(s) present\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
