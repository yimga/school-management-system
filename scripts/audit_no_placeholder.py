#!/usr/bin/env python
"""Audit templates for user-facing placeholder content that should not ship.

Catches text that smells like an unfinished stub: "Lorem ipsum", "Coming soon",
"Not implemented", "Sample data", "Replace me", "Placeholder text", "TBD".

Excludes legitimate uses:
- HTML attribute `placeholder=""` on form inputs (input affordance, not stub copy)
- `{# TODO #}` / `{% comment %}TODO{% endcomment %}` developer notes (not user-visible)
- copy a human has DECLARED with `{# placeholder-allow: <reason> #}`

WHY THIS IS A GATE AND NOT ONLY A REPORT (2026-09-02)
-----------------------------------------------------
Until now this was a reporter. ``main()`` ended in ``return 0`` unconditionally,
there was no ``--strict`` and no way to declare an intentional placeholder; and
across every workflow, hook, runner, npm script and test the only files that
named it were itself and ``generate_final_validation_truth_check.py`` -- which
merely RE-SERIALISES the artifact it finds on disk and never re-runs the scan.
So nothing could fail because of it, and nothing refreshed it.

The cost was sitting in the tree. ``docs/generated/no_placeholder_audit.json``
is a TRACKED artifact and it read::

    "finding_count": 0, "templates_scanned": 1086, "generated_at": "2026-05-19"

Anyone opening it concluded the platform ships no placeholder copy. By 2026-09-02
the corpus was 1910 templates, so 824 of the templates that certificate covered
had never been looked at -- 43% of the surface -- and the one live finding in the
tree (``studio_os/partials/launch_select_plan_body.html``) was not in it. A number
in a tracked file is read as a fact.

WHAT A DECLARATION IS
---------------------
A placeholder that is deliberate product copy is DECLARED where it lives, with a
written reason::

    {# placeholder-allow: plans are not productized; the lede says so #}
    <span>{% trans "Coming soon" %}</span>

The marker may sit on the finding's own line or on the line directly above it,
and ``<!-- placeholder-allow: ... -->`` is accepted too (the ``{# #}`` form is
preferred -- it is not shipped to the browser). It is read PER LINE and never
spans two: Django's ``tag_re`` has no DOTALL, so a multi-line ``{# #}`` is not a
comment at all and renders its own source onto the page.

Three ways a declaration fails to declare, each reported rather than ignored:

* ``allow-marker-without-reason`` -- the reason is empty or shorter than
  ``MIN_REASON_CHARS``. The marker exists so the next reader learns WHY; a marker
  with nothing in it is a mute button, which is the thing this audit forbids.
* ``stale-allow-marker`` -- the marker governs no finding. An excuse must not
  outlive the copy it was written for (the same rule as
  ``scan_blank_unique_text_fields``'s stale-ALLOWLIST report).
* ``malformed-allow-marker`` -- the line says ``placeholder-allow:`` but is not a
  well-formed single-line comment, so a typo cannot silently suppress anything.

CORPUS
------
Every directory Django actually loads templates from:
``settings.TEMPLATES[0]["DIRS"] == [BASE_DIR / "templates"]`` **plus**
``"APP_DIRS": True``. The old corpus was ``templates/`` alone, which left
``apps/athletics/templates/`` -- 12 rendered templates -- outside the scan
entirely. They are clean today; they were simply never asked.

ONE MORE THING THE CODE DID NOT DO
----------------------------------
The exclusion for ``placeholder="..."`` input attributes was documented but
never applied: the stripped string was computed and thrown away, and the
patterns were matched against the raw line. ``--self-check`` caught it on its
first run. Measured before fixing: 0 live findings are suppressed by applying
the exclusion, so the gate now does what it said and hides nothing.

WHAT ``--strict`` ASSERTS
-------------------------
1. no UNDECLARED finding anywhere in the corpus;
2. the corpus is non-empty (a zero over nothing is not a zero);
3. the committed artifact still describes what the tree contains.

(3) is compared on ``(file, kind)`` and ``(file, kind, reason)`` -- deliberately
NOT on ``templates_scanned``. The corpus grew by roughly eight templates a day
over the period that produced this defect, and a gate that demands a regenerated
JSON on every added template is a gate somebody switches off. ``templates_scanned``
stays in the artifact as a generation-time census and is labelled as one there.

``--strict`` WRITES NOTHING, so the pre-push hook does not dirty the tree.

Usage
-----
    python scripts/audit_no_placeholder.py              # refresh the artifact
    python scripts/audit_no_placeholder.py --strict     # the CI/pre-push gate
    python scripts/audit_no_placeholder.py --self-check # prove the classifier
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = ROOT / "templates"
APPS_ROOT = ROOT / "apps"
OUT_PATH = ROOT / "docs" / "generated" / "no_placeholder_audit.json"

USER_VISIBLE_PATTERNS = [
    (re.compile(r"\blorem\s+ipsum\b", re.I), "lorem-ipsum"),
    (re.compile(r"\bComing\s+soon\b", re.I), "coming-soon"),
    (re.compile(r"\bNot\s+implemented\b", re.I), "not-implemented"),
    (re.compile(r"\bReplace\s+me\b", re.I), "replace-me"),
    (re.compile(r"\bPlaceholder\s+text\b", re.I), "placeholder-text"),
    (re.compile(r"\bSample\s+data\b", re.I), "sample-data"),
    (re.compile(r"\bFake\s+content\b", re.I), "fake-content"),
    (re.compile(r"\bunder\s+construction\b", re.I), "under-construction"),
    (re.compile(r"\bWork\s+in\s+progress\b", re.I), "work-in-progress"),
    (re.compile(r"\bTBD\b"), "tbd"),
    (re.compile(r"\bTBA\b"), "tba"),
]

DEV_NOTE_PATTERNS = [
    (re.compile(r"^\s*\{#.*TODO.*#\}\s*$"), "django-todo-comment"),
    (re.compile(r"\{%\s*comment\s*%\}.*TODO.*\{%\s*endcomment\s*%\}", re.I | re.S), "django-todo-comment-block"),
]

INPUT_PLACEHOLDER_ATTR = re.compile(r'\bplaceholder\s*=\s*"[^"]*"')

EXCLUDE_DIRS = {".git", "__pycache__", "node_modules"}

# The declaration marker. Two accepted spellings; both must open and close on the
# SAME line (see the module docstring on Django's single-line {# #}).
MARKER_TOKEN = "placeholder-allow:"
ALLOW_MARKER_RES = (
    re.compile(r"\{#\s*placeholder-allow:(?P<reason>[^#]*)#\}", re.I),
    re.compile(r"<!--\s*placeholder-allow:(?P<reason>.*?)-->", re.I),
)
# A floor, not a quality bar: "x" and "later" are not reasons. Stated here so a
# future reader does not have to reverse-engineer the number out of a failure.
MIN_REASON_CHARS = 10

# Findings the gate raises about the MARKERS themselves rather than about copy.
MARKER_KINDS = frozenset(
    {"allow-marker-without-reason", "stale-allow-marker", "malformed-allow-marker"}
)


def visible_text(line: str) -> str:
    """The part of a line a reader can actually see.

    A form input's ``placeholder="Coming soon"`` is an input affordance, not
    shipped stub copy, and the module docstring has always said so. It was not
    true of the code: the stripped string was computed, used for the dev-note
    test, and then THROWN AWAY -- the placeholder patterns were matched against
    the raw line, so ``<input placeholder="Coming soon">`` was a finding. Found
    2026-09-02 by this module's own ``--self-check``, which is the point of
    having one. Measured before changing it: 0 of the live findings in the tree
    are suppressed by applying the exclusion, so this narrows the gate to what
    it always claimed and hides nothing.
    """
    return INPUT_PLACEHOLDER_ATTR.sub("", line)


def is_user_visible_line(line: str) -> bool:
    """False for developer notes ({# TODO #} and the {% comment %} block form)."""
    stripped = visible_text(line)
    for dev_pat, _ in DEV_NOTE_PATTERNS:
        if dev_pat.search(stripped):
            return False
    return True


def marker_reason(line: str) -> str | None:
    """The declared reason on this line, or None when the line carries no marker."""
    for pat in ALLOW_MARKER_RES:
        match = pat.search(line)
        if match:
            return match.group("reason").strip()
    return None


def template_roots() -> list[Path]:
    """Every directory the Django template engine loads from, in load order."""
    roots = [TEMPLATE_ROOT]
    if APPS_ROOT.is_dir():
        for child in sorted(APPS_ROOT.iterdir()):
            candidate = child / "templates"
            if candidate.is_dir():
                roots.append(candidate)
    return roots


def iter_templates() -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for root in template_roots():
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.html")):
            if any(part in EXCLUDE_DIRS for part in path.parts):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            out.append(path)
    return out


def scan_text(rel: str, text: str) -> tuple[list[dict], list[dict]]:
    """Classify one template's text. Returns (findings, declarations).

    Split out of ``scan_template`` so ``--self-check`` can exercise the exact
    classifier the tree scan uses, with no filesystem in the way.
    """
    lines = text.splitlines()
    markers: dict[int, str] = {}
    findings: list[dict] = []
    declarations: list[dict] = []

    for lineno, line in enumerate(lines, 1):
        reason = marker_reason(line)
        if reason is not None:
            markers[lineno] = reason
        elif MARKER_TOKEN in line.lower():
            findings.append({
                "file": rel,
                "line": lineno,
                "kind": "malformed-allow-marker",
                "snippet": line.strip()[:160],
            })

    used: set[int] = set()
    for lineno, line in enumerate(lines, 1):
        if not is_user_visible_line(line):
            continue
        haystack = visible_text(line)
        for pat, kind in USER_VISIBLE_PATTERNS:
            if not pat.search(haystack):
                continue
            owner = lineno if lineno in markers else (lineno - 1 if lineno - 1 in markers else None)
            record = {
                "file": rel,
                "line": lineno,
                "kind": kind,
                "snippet": line.strip()[:160],
            }
            if owner is None:
                findings.append(record)
                continue
            used.add(owner)
            reason = markers[owner]
            if len(reason) < MIN_REASON_CHARS:
                record["placeholder_kind"] = kind
                record["kind"] = "allow-marker-without-reason"
                record["marker_line"] = owner
                findings.append(record)
            else:
                record["reason"] = reason
                record["marker_line"] = owner
                declarations.append(record)

    for lineno in sorted(set(markers) - used):
        findings.append({
            "file": rel,
            "line": lineno,
            "kind": "stale-allow-marker",
            "snippet": lines[lineno - 1].strip()[:160],
        })

    findings.sort(key=lambda f: (f["file"], f["line"], f["kind"]))
    declarations.sort(key=lambda d: (d["file"], d["line"], d["kind"]))
    return findings, declarations


def scan_template(path: Path) -> tuple[list[dict], list[dict]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return [], []
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    return scan_text(rel, text)


def run_scan() -> tuple[int, list[dict], list[dict]]:
    findings: list[dict] = []
    declarations: list[dict] = []
    paths = iter_templates()
    for path in paths:
        found, declared = scan_template(path)
        findings.extend(found)
        declarations.extend(declared)
    findings.sort(key=lambda f: (f["file"], f["line"], f["kind"]))
    declarations.sort(key=lambda d: (d["file"], d["line"], d["kind"]))
    return len(paths), findings, declarations


def _histogram(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        out[row["kind"]] = out.get(row["kind"], 0) + 1
    return out


def build_payload(count: int, findings: list[dict], declarations: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "scripts/audit_no_placeholder.py",
        "enforced_by": (
            "scripts/audit_no_placeholder.py --strict "
            "(pre_push_boundary_check.py::no-placeholder-copy, "
            "architectural-boundaries.yml::u_no_placeholder_copy)"
        ),
        "templates_scanned": count,
        "templates_scanned_note": (
            "A census taken at generated_at over templates/ plus every "
            "apps/*/templates/ (APP_DIRS is True). It is deliberately NOT gated: "
            "the corpus grows daily and a JSON that must be regenerated on every "
            "added template is a gate somebody switches off. Do not read this "
            "number as current. What IS enforced on every push is the finding and "
            "declaration set below, which --strict re-derives from the live tree."
        ),
        "finding_count": len(findings),
        "by_kind": _histogram(findings),
        "findings": findings,
        "declared_count": len(declarations),
        "declared_by_kind": _histogram(declarations),
        "declarations": declarations,
    }


def signature(payload: dict) -> dict:
    """The part of the artifact that is a CLAIM about the tree.

    Line numbers are excluded on purpose -- an edit anywhere above a finding
    shifts them and would fail the gate for a change that altered nothing about
    what ships. ``templates_scanned`` is excluded for the reason the artifact
    itself records.
    """
    return {
        "findings": sorted(
            (str(row.get("file")), str(row.get("kind"))) for row in payload.get("findings") or []
        ),
        "declarations": sorted(
            (
                str(row.get("file")),
                str(row.get("kind")),
                str(row.get("reason") or "").strip(),
            )
            for row in payload.get("declarations") or []
        ),
    }


def write_payload(payload: dict) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n": .gitattributes pins docs/generated/*.json to eol=lf, and the
    # previous write_text() emitted CRLF on Windows -- a permanent phantom diff
    # for anyone who regenerated on this platform.
    with OUT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


# --- self-check -------------------------------------------------------------
# A scan that has never been shown finding anything is not evidence that there is
# nothing to find. These run in milliseconds and --strict refuses to report a
# result if any of them regress.
SELF_CHECK_CASES: tuple[tuple[str, str, list[str], int], ...] = (
    ("bare placeholder copy is a finding", "<span>Coming soon</span>\n", ["coming-soon"], 0),
    ("lorem ipsum is a finding", "<p>Lorem ipsum dolor</p>\n", ["lorem-ipsum"], 0),
    ("an input placeholder attribute is not", '<input placeholder="Coming soon">\n', [], 0),
    ("a django TODO note is not", "{# TODO: wire this up #}\n", [], 0),
    (
        "a same-line marker declares it",
        "<span>Coming soon</span>{# placeholder-allow: not productized yet #}\n",
        [],
        1,
    ),
    (
        "a marker on the line above declares it",
        "{# placeholder-allow: not productized yet #}\n<span>Coming soon</span>\n",
        [],
        1,
    ),
    (
        "an html-comment marker declares it",
        "<!-- placeholder-allow: not productized yet -->\n<span>Coming soon</span>\n",
        [],
        1,
    ),
    (
        "an EMPTY reason declares nothing",
        "{# placeholder-allow: #}\n<span>Coming soon</span>\n",
        ["allow-marker-without-reason"],
        0,
    ),
    (
        "a one-word reason declares nothing",
        "{# placeholder-allow: later #}\n<span>Coming soon</span>\n",
        ["allow-marker-without-reason"],
        0,
    ),
    (
        "a marker two lines up declares nothing",
        "{# placeholder-allow: not productized yet #}\n\n<span>Coming soon</span>\n",
        ["coming-soon", "stale-allow-marker"],
        0,
    ),
    (
        "a marker that governs nothing is stale",
        "{# placeholder-allow: not productized yet #}\n<p>shipped copy</p>\n",
        ["stale-allow-marker"],
        0,
    ),
    (
        "an unclosed marker suppresses nothing and is reported",
        "{# placeholder-allow: not productized yet\n<span>Coming soon</span>\n",
        ["coming-soon", "malformed-allow-marker"],
        0,
    ),
)


def run_self_check(verbose: bool = False) -> bool:
    ok = True
    for label, text, expect_kinds, expect_declared in SELF_CHECK_CASES:
        findings, declarations = scan_text("selfcheck.html", text)
        got_kinds = sorted(row["kind"] for row in findings)
        if got_kinds != sorted(expect_kinds) or len(declarations) != expect_declared:
            ok = False
            print(
                f"  SELF-CHECK FAIL  {label}\n"
                f"      expected findings={sorted(expect_kinds)} declared={expect_declared}\n"
                f"      got      findings={got_kinds} declared={len(declarations)}"
            )
        elif verbose:
            print(f"  ok  {label}")
    if verbose:
        verdict = "PASS" if ok else "FAIL"
        print(f"audit_no_placeholder --self-check: {len(SELF_CHECK_CASES)} cases, {verdict}")
    return ok


def _report(count: int, findings: list[dict], declarations: list[dict]) -> None:
    print(f"audit_no_placeholder: scanned {count} templates in {len(template_roots())} roots")
    print(f"  undeclared:  {len(findings)}")
    print(f"  declared:    {len(declarations)}")
    histogram = _histogram(findings)
    if histogram:
        print("  histogram:")
        for kind, num in sorted(histogram.items(), key=lambda kv: -kv[1]):
            print(f"    {num:4d}  {kind}")
    for row in declarations:
        print(f"  DECLARED  {row['file']}:{row['line']}  {row['kind']}  -- {row['reason']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit templates for placeholder copy that should not ship."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Gate mode: exit 1 on an undeclared placeholder, a broken marker, an "
        "empty corpus, or a committed artifact that no longer matches the tree. "
        "Writes nothing.",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Run the classifier over its known-good/known-bad cases and exit.",
    )
    args = parser.parse_args(argv)

    if args.self_check:
        return 0 if run_self_check(verbose=True) else 1

    if args.strict and not run_self_check(verbose=False):
        print("audit_no_placeholder: FAIL - the classifier failed its own self-check;")
        print("  refusing to report a scan result. Re-run with --self-check for detail.")
        return 1

    count, findings, declarations = run_scan()

    if count == 0:
        print("audit_no_placeholder: FAIL - the template corpus is EMPTY.")
        looked = ", ".join(str(r.relative_to(ROOT)) for r in template_roots())
        print(f"  looked in: {looked}")
        print("  A zero over an empty corpus is not a zero.")
        return 1

    payload = build_payload(count, findings, declarations)

    if not args.strict:
        write_payload(payload)
        _report(count, findings, declarations)
        print(f"  written:     {OUT_PATH.relative_to(ROOT).as_posix()}")
        return 0

    _report(count, findings, declarations)

    problems: list[str] = []
    for row in findings:
        if row["kind"] in MARKER_KINDS:
            problems.append(f"{row['file']}:{row['line']}  {row['kind']}  {row['snippet']}")
        else:
            problems.append(
                f"{row['file']}:{row['line']}  undeclared {row['kind']}  {row['snippet']}"
            )

    stored: dict | None = None
    if OUT_PATH.exists():
        try:
            stored = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stored = None
    rel_out = OUT_PATH.relative_to(ROOT).as_posix()
    if stored is None:
        problems.append(
            f"{rel_out} is missing or unreadable - that artifact is the tracked record"
        )
    else:
        live_sig = signature(payload)
        stored_sig = signature(stored)
        if live_sig != stored_sig:
            for key in ("findings", "declarations"):
                singular = key[:-1]
                for row in live_sig[key]:
                    if row not in stored_sig[key]:
                        problems.append(f"{rel_out} does not record live {singular}: {row}")
                for row in stored_sig[key]:
                    if row not in live_sig[key]:
                        problems.append(
                            f"{rel_out} still records a {singular} that is gone: {row}"
                        )

    if problems:
        print()
        print(f"audit_no_placeholder: FAIL - {len(problems)} problem(s)")
        for line in problems:
            print(f"  {line}")
        print()
        print("  Fix the copy, or DECLARE it where it lives with a written reason:")
        print("      {# placeholder-allow: why this ships as-is #}")
        print("  on the finding's own line or the line directly above it")
        print(f"  (at least {MIN_REASON_CHARS} characters - the reason is the point).")
        print("  Then refresh the record: python scripts/audit_no_placeholder.py")
        return 1

    print()
    print("audit_no_placeholder: PASS - no undeclared placeholder copy; artifact matches the tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
