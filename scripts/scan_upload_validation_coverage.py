#!/usr/bin/env python3
"""Coverage ratchet for file-upload validation.

The platform has ONE shared upload-validation primitive
(:func:`apps.security.upload_validation.validate_uploaded_file` — size cap +
magic-byte sniff + malware-scan hook). This scanner FREEZES the set of DIRECT
``request.FILES`` intake sites that persist / handle an uploaded file WITHOUT
routing it through a recognised validator, so the sprawl can only shrink and a
NEW unvalidated intake fails CI. It is the read-of-uploads twin of the other
fragmentation ratchets (``scan_access_resolver_fragmentation`` /
``scan_config_resolver_fragmentation``): it does not fix anything — it makes the
uncovered count visible and prevents regressions.

What is a DIRECT intake (a finding candidate):
    * ``request.FILES["x"]`` / ``request.FILES.get(...)`` / ``.getlist(...)`` /
      ``.pop(...)`` / ``.values()`` / ``.setlist(...)`` — the view pulls the raw
      UploadedFile out itself and is responsible for validating it.

What is NOT counted (deliberately, to avoid burying the real signal):
    * ``SomeForm(request.POST, request.FILES)`` — form-routed. ``request.FILES``
      is a bare argument, never subscripted / ``.get``'d here; validation lives
      in the form field / ``clean_*`` and is a separate concern. Including these
      would flood the baseline with false positives and get the gate switched
      off (the cross-tenancy-fk noise-burial lesson).

A direct-intake function is CREDITED (not a finding) when its body calls a
recognised validator (see ``_VALIDATOR_CALLS``) or a known validating persist
helper, OR it carries a ``# upload-validation-allow: <reason>`` marker within
the function. False-NEGATIVE biased: it credits a function that calls ANY
validator even if it does not validate the specific file — never a false
positive.

Flags: ``--compare`` (line-insensitive, keyed on ``(path, function)`` multiset;
exit 1 only on NEW findings), ``--update-baseline``, ``--json``, ``--strict``.
Stdlib only (AST + tokenize); no Django import, so it runs in the deps-free
architectural-boundaries job.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPS_DIR = ROOT / "apps"
BASELINE = ROOT / "var" / "security-audit-baseline-upload-validation-coverage.json"
MARKER = "upload-validation-allow:"

# ``request.FILES.<method>(...)`` shapes that pull a raw upload out directly.
_FILES_METHODS = frozenset({"get", "getlist", "pop", "values", "setlist", "__getitem__"})

# A direct-intake function is credited when it calls one of these.
_VALIDATOR_CALLS = frozenset(
    {
        "validate_uploaded_file",
        "validate_logo_upload",
        "validate_favicon_upload",
        "validate_brand_image_upload",
        "LogoUploadValidator",
        "sniff_file_mime",
        "sniff_image_mime",
        "validate_svg_safe",
        "scan_for_malware",
        # Known helpers that validate the upload internally before persisting.
        "persist_school_brand_logo",
        "persist_school_brand_favicon",
    }
)

# SOT / helper modules that DEFINE the validators — never flag themselves.
_SKIP_BASENAMES = frozenset(
    {"upload_validation.py", "school_brand_assets.py", "svg_sanitize.py"}
)


def _is_files_attr(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "FILES"


def _iter_direct_intakes(func: ast.AST) -> bool:
    """True when ``func`` contains a direct ``request.FILES`` intake shape."""
    for node in ast.walk(func):
        # request.FILES["x"]
        if isinstance(node, ast.Subscript) and _is_files_attr(node.value):
            return True
        # request.FILES.get(...) / .getlist(...) / .values() / ...
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _FILES_METHODS
            and _is_files_attr(node.func.value)
        ):
            return True
    return False


def _calls_a_validator(func: ast.AST) -> bool:
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = None
        if isinstance(fn, ast.Name):
            name = fn.id
        elif isinstance(fn, ast.Attribute):
            name = fn.attr
        if name in _VALIDATOR_CALLS:
            return True
    return False


def _marker_lines(source: str) -> set[int]:
    """Line numbers carrying a real ``# upload-validation-allow:`` COMMENT.

    Uses tokenize so the marker text inside a string literal is not mistaken
    for a live marker.
    """
    lines: set[int] = set()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type == tokenize.COMMENT and MARKER in tok.string:
                lines.add(tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return lines


def _func_span(func: ast.AST) -> tuple[int, int]:
    start = getattr(func, "lineno", 0)
    end = getattr(func, "end_lineno", start) or start
    # Include the decorator lines above the def, where a marker may sit.
    for dec in getattr(func, "decorator_list", []) or []:
        start = min(start, getattr(dec, "lineno", start))
    return start, end


def _iter_py_files(apps_dir: Path):
    for path in apps_dir.rglob("*.py"):
        parts = path.parts
        if "migrations" in parts or "tests" in parts:
            continue
        if path.name.startswith("test_"):
            continue
        if path.name in _SKIP_BASENAMES:
            continue
        yield path


def scan(apps_dir: Path = APPS_DIR, root: Path = ROOT) -> list[dict]:
    findings: list[dict] = []
    for path in _iter_py_files(apps_dir):
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            continue
        markers = _marker_lines(source)
        rel = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _iter_direct_intakes(node):
                continue
            if _calls_a_validator(node):
                continue
            start, end = _func_span(node)
            if any(start <= ln <= end for ln in markers):
                continue
            findings.append({"path": rel, "function": node.name, "line": node.lineno})
    findings.sort(key=lambda f: (f["path"], f["function"], f["line"]))
    return findings


def _key(f: dict) -> tuple[str, str]:
    return (f["path"], f["function"])


def _load_baseline() -> list[dict]:
    if not BASELINE.exists():
        return []
    try:
        data = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data.get("findings", [])


def _write_baseline(findings: list[dict]) -> None:
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"finding_count": len(findings), "findings": findings}
    BASELINE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true", help="Fail on NEW findings vs baseline")
    parser.add_argument("--update-baseline", action="store_true", help="Write the current findings as the baseline")
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON")
    parser.add_argument("--strict", action="store_true", help="Fail if any findings exist at all")
    args = parser.parse_args(argv)

    findings = scan()

    if args.update_baseline:
        _write_baseline(findings)
        print(f"upload-validation-coverage: baseline written ({len(findings)} unvalidated intake sites)")
        return 0

    if args.json:
        print(json.dumps({"finding_count": len(findings), "findings": findings}, indent=2))

    if args.compare:
        from collections import Counter

        baseline = Counter(_key(f) for f in _load_baseline())
        current = Counter(_key(f) for f in findings)
        new = current - baseline
        if new:
            print("UPLOAD_VALIDATION_COVERAGE_REGRESSION — new unvalidated request.FILES intake:")
            for (rel, func), n in sorted(new.items()):
                print(f"  - {rel}::{func} (+{n})")
            print(
                "Route the upload through apps.security.upload_validation."
                "validate_uploaded_file, or mark a reviewed site with "
                "'# upload-validation-allow: <reason>'."
            )
            return 1
        print(f"upload-validation-coverage: no new unvalidated intake ({len(findings)} frozen).")
        return 0

    if args.strict and findings:
        print(f"UPLOAD_VALIDATION_COVERAGE: {len(findings)} unvalidated direct request.FILES intake site(s)")
        for f in findings:
            print(f"  - {f['path']}::{f['function']}:{f['line']}")
        return 1

    print(f"upload-validation-coverage: {len(findings)} unvalidated direct request.FILES intake site(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
