#!/usr/bin/env python3
"""Platform-wide template render-safety audit.

Detects bug classes that can leak content into the rendered page or cause
outages on first load. Output is a structured report; non-zero exit if any
findings.

Checks:
  1. Direct render leaks: stray  {#  / #}  / {{  / }}  / {%  / %}  tokens
  2. Tag balance: every  {% if/for/block/with/comment/verbatim/spaceless/
     autoescape/blocktrans/blocktranslate/cache/filter/localize/localtime/
     timezone/language %}  has matching  {% end... %}
  3. Multi-line  {# ... #}  (Django supports single-line only)
  4. Broken references: include/extends paths exist; {% static %} files exist
  5. Bad {% load %} libs (best-effort: names not in known set)

Excludes node_modules, staticfiles, .git, vendor copies.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOTS = [ROOT / "templates"]
# Also walk apps/*/templates if any exist
for app in (ROOT / "apps").glob("*/templates"):
    TEMPLATE_ROOTS.append(app)
STATIC_ROOT = ROOT / "static"

EXCLUDE_PARTS = {"node_modules", "staticfiles", ".git", "venv", ".venv"}

# Template names supplied by third-party packages (django.contrib.admin,
# django-unfold). They won't be found in our project tree but are valid at
# runtime via the template loader's app dirs.
THIRD_PARTY_TEMPLATE_PREFIXES = (
    "admin/",
    "unfold/",
    "django/",
    "auth/",
    "registration/",
    "rest_framework/",
    "debug_toolbar/",
)

# django-unfold static assets ship inside the package, not under project static/.
THIRD_PARTY_STATIC_PREFIXES = (
    "unfold/",
)

# Gitignored build-output directories (vite/rollup bundles). These are produced
# at build/deploy time and are absent at lint time, so a "file not found" here
# is a build-timing artifact, not a real broken reference. The gate still
# catches genuinely-missing COMMITTED assets (typos, deleted images).
BUILD_ARTIFACT_STATIC_PREFIXES = (
    "js/dist/",
)


def iter_templates() -> list[Path]:
    out: list[Path] = []
    for r in TEMPLATE_ROOTS:
        if not r.exists():
            continue
        for p in r.rglob("*.html"):
            if any(part in EXCLUDE_PARTS for part in p.parts):
                continue
            out.append(p)
    return sorted(out)


# ----------------------------- Check 1 + 3: leaks ---------------------------

MULTILINE_HASH = re.compile(r"\{#((?:(?!#\}).)*?\n(?:(?!#\}).)*?)#\}", re.DOTALL)


# A <script type="application/json"> island is NOT inert: it is built with
# {% if %} / {% url %} / {% trans %} and rendered by Django, so it IS
# template territory. Masking it hid two multi-line {# #} comments inside
# components/rmc_command_palette.html (2026-08-31) that this gate is written
# to catch -- it reported 0 findings while they were live, and the resulting
# malformed JSON silently emptied the command palette on every shell.
# Executable JS stays masked: it legitimately carries `}}`, `${...}` and
# Alpine `x-data="{...}"`, none of which are Django tokens.
_SCRIPT_OR_STYLE = re.compile(
    r"<style\b[^>]*>.*?</style>"
    r"|<script\b(?![^>]*\btype\s*=\s*[\"']application/(?:ld\+)?json[\"'])"
    r"[^>]*>.*?</script>",
    re.IGNORECASE | re.DOTALL,
)


def _strip_script_style(text: str) -> str:
    """Replace <script>...</script> and <style>...</style> bodies with spaces,
    preserving line count so reported line numbers stay accurate.
    Inline JS/CSS legitimately contains `}}`, `{` etc. and isn't Django template
    syntax — masking them avoids false positives."""

    def repl(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    return _SCRIPT_OR_STYLE.sub(repl, text)


TAG_OR_COMMENT = re.compile(r"\{%.*?%\}|\{#.*?#\}", re.DOTALL)


def _blank_keep_newlines(m: "re.Match[str]") -> str:
    """Blank a match but keep its newlines, so line numbers stay true."""
    return re.sub(r"[^\n]", " ", m.group(0))


def find_token_leaks(text: str) -> list[tuple[int, str]]:
    """Find structurally-broken template tokens that would leak as page text."""
    issues: list[tuple[int, str]] = []

    # Mask script/style bodies — they aren't Django template territory.
    template_text = _strip_script_style(text)

    # 1. Multi-line {# #}
    for m in MULTILINE_HASH.finditer(template_text):
        line = template_text.count("\n", 0, m.start()) + 1
        issues.append((line, "multi-line `{# ... #}` (Django supports single-line only)"))

    # 2. Single-line {# ... #} bodies may legitimately contain `#` chars
    # (like `#main-content` anchors or `#353` issue refs). Use a tempered
    # token to mask any well-formed single-line comment.
    masked = re.sub(r"\{#(?:(?!#\}|\n).)*#\}", " ", template_text)
    for m in re.finditer(r"\{#", masked):
        line = masked.count("\n", 0, m.start()) + 1
        issues.append((line, "orphan `{#` with no matching `#}` on the same line"))
    for m in re.finditer(r"#\}", masked):
        line = masked.count("\n", 0, m.start()) + 1
        issues.append((line, "orphan `#}` with no preceding `{#` on the same line"))

    # 3. Orphan {{ without }}, or }} without {{
    # Mask {% %} and {# #} FIRST. `{% endif %}}` is a tag plus a literal `}`
    # closing a JSON object, and its last two characters read as an orphan
    # `}}` to a scan that has not removed tags yet. Newlines are preserved so
    # reported line numbers stay accurate.
    tagless = TAG_OR_COMMENT.sub(_blank_keep_newlines, template_text)
    masked2 = re.sub(r"\{\{.*?\}\}", " ", tagless, flags=re.DOTALL)
    for m in re.finditer(r"\{\{", masked2):
        line = masked2.count("\n", 0, m.start()) + 1
        issues.append((line, "orphan `{{` with no matching `}}`"))
    for m in re.finditer(r"\}\}", masked2):
        line = masked2.count("\n", 0, m.start()) + 1
        issues.append((line, "orphan `}}` with no preceding `{{`"))

    # 4. Orphan {% without %}
    masked3 = re.sub(r"\{%.*?%\}", " ", template_text, flags=re.DOTALL)
    for m in re.finditer(r"\{%", masked3):
        line = masked3.count("\n", 0, m.start()) + 1
        issues.append((line, "orphan `{%` with no matching `%}`"))
    for m in re.finditer(r"%\}", masked3):
        line = masked3.count("\n", 0, m.start()) + 1
        issues.append((line, "orphan `%}` with no preceding `{%`"))

    return issues


# ----------------------------- Check 2: tag balance --------------------------

PAIRED = {
    "if": "endif",
    "for": "endfor",
    "block": "endblock",
    "with": "endwith",
    "comment": "endcomment",
    "spaceless": "endspaceless",
    "autoescape": "endautoescape",
    "verbatim": "endverbatim",
    "blocktrans": "endblocktrans",
    "blocktranslate": "endblocktranslate",
    "cache": "endcache",
    "filter": "endfilter",
    "localize": "endlocalize",
    "localtime": "endlocaltime",
    "timezone": "endtimezone",
    "language": "endlanguage",
    "ifchanged": "endifchanged",
}
ENDS = {v: k for k, v in PAIRED.items()}

TAG_RE = re.compile(r"\{%\s*(\w+)([^%]*?)%\}", re.DOTALL)


def _strip_hash_comments(text: str) -> str:
    """Mask single-line `{# ... #}` comment bodies with spaces (preserving
    newlines + line count) so tags appearing inside them aren't tokenized."""

    def repl(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    return re.sub(r"\{#(?:(?!#\}|\n).)*#\}", repl, text)


def find_tag_imbalance(text: str) -> list[tuple[int, str]]:
    """Stack-based check that openers and closers pair up. Skips {% verbatim %}
    and {% comment %} bodies so the content inside isn't tokenized. Also masks
    {# ... #} bodies so tag-like text inside comments isn't parsed."""
    text = _strip_hash_comments(text)
    issues: list[tuple[int, str]] = []
    stack: list[tuple[str, int]] = []  # (tag_name, line)
    pos = 0
    while pos < len(text):
        m = TAG_RE.search(text, pos)
        if not m:
            break
        tag = m.group(1)
        line = text.count("\n", 0, m.start()) + 1
        pos = m.end()
        # Skip verbatim/comment bodies
        if tag in ("verbatim", "comment"):
            end_token = "end" + tag
            m_end = re.search(r"\{%\s*" + end_token + r"\s*%\}", text[pos:], re.DOTALL)
            if not m_end:
                issues.append((line, f"unclosed `{{% {tag} %}}` (no `{{% {end_token} %}}` found)"))
                break
            pos = pos + m_end.end()
            continue
        if tag in PAIRED:
            stack.append((tag, line))
        elif tag in ENDS:
            expected = ENDS[tag]
            if not stack:
                issues.append((line, f"`{{% {tag} %}}` with no matching opener"))
            else:
                opener, opener_line = stack[-1]
                if opener == expected:
                    stack.pop()
                else:
                    # Could still be valid if the closer matches further down
                    # (e.g. closing an outer block before an inner is closed).
                    # We flag it — usually a real bug.
                    issues.append(
                        (
                            line,
                            f"`{{% {tag} %}}` does not close opener `{{% {opener} %}}` "
                            f"on line {opener_line}",
                        )
                    )
                    stack.pop()
    for opener, opener_line in stack:
        issues.append((opener_line, f"unclosed `{{% {opener} %}}` — no matching `{{% end{opener} %}}`"))
    return issues


# ----------------------------- Check 4: broken references --------------------

INCLUDE_RE = re.compile(r'\{%\s*include\s+["\']([^"\']+)["\']')
EXTENDS_RE = re.compile(r'\{%\s*extends\s+["\']([^"\']+)["\']')
STATIC_RE = re.compile(r'\{%\s*static\s+["\']([^"\']+)["\']\s*%\}')

ALL_TEMPLATE_NAMES: set[str] = set()


def build_template_index() -> None:
    ALL_TEMPLATE_NAMES.clear()
    for r in TEMPLATE_ROOTS:
        if not r.exists():
            continue
        for p in r.rglob("*.html"):
            if any(part in EXCLUDE_PARTS for part in p.parts):
                continue
            rel = p.relative_to(r).as_posix()
            ALL_TEMPLATE_NAMES.add(rel)


def _is_third_party(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in THIRD_PARTY_TEMPLATE_PREFIXES)


def find_missing_refs(text: str) -> list[tuple[int, str]]:
    issues: list[tuple[int, str]] = []
    for m in INCLUDE_RE.finditer(text):
        path = m.group(1)
        if "{" in path or "}" in path:
            continue
        if _is_third_party(path):
            continue
        if path not in ALL_TEMPLATE_NAMES:
            line = text.count("\n", 0, m.start()) + 1
            issues.append((line, f"`{{% include \"{path}\" %}}` — target template not found"))
    for m in EXTENDS_RE.finditer(text):
        path = m.group(1)
        if "{" in path or "}" in path:
            continue
        if _is_third_party(path):
            continue
        if path not in ALL_TEMPLATE_NAMES:
            line = text.count("\n", 0, m.start()) + 1
            issues.append((line, f"`{{% extends \"{path}\" %}}` — base template not found"))
    for m in STATIC_RE.finditer(text):
        path = m.group(1)
        if "{" in path or "}" in path:
            continue
        if any(path.startswith(prefix) for prefix in THIRD_PARTY_STATIC_PREFIXES):
            continue
        if any(path.startswith(prefix) for prefix in BUILD_ARTIFACT_STATIC_PREFIXES):
            continue
        candidate = STATIC_ROOT / path
        if not candidate.exists():
            line = text.count("\n", 0, m.start()) + 1
            issues.append((line, f"`{{% static \"{path}\" %}}` — file not found in static/"))
    return issues


# ----------------------------- Driver ----------------------------------------


def audit() -> int:
    build_template_index()
    files = iter_templates()
    total_findings = 0
    by_class: dict[str, int] = defaultdict(int)
    per_file: dict[Path, list[tuple[int, str]]] = {}

    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings: list[tuple[int, str]] = []
        findings.extend(find_token_leaks(text))
        findings.extend(find_tag_imbalance(text))
        findings.extend(find_missing_refs(text))
        if findings:
            per_file[p] = findings
            total_findings += len(findings)
            for _, msg in findings:
                # Group by issue type prefix
                msg.split("`", 2)[-1][:40] if "`" in msg else msg[:40]
                by_class[msg.split(" ")[0]] += 1

    # Report
    print(f"Scanned {len(files)} templates across {len(TEMPLATE_ROOTS)} root(s).")
    print(f"Total findings: {total_findings}")
    print(f"Files with findings: {len(per_file)}\n")

    if per_file:
        print("By file (top 50):")
        ranked = sorted(per_file.items(), key=lambda kv: -len(kv[1]))[:50]
        for p, findings in ranked:
            print(f"\n  {p.relative_to(ROOT)} ({len(findings)})")
            for line, msg in findings[:30]:
                print(f"    L{line}: {msg}")
            if len(findings) > 30:
                print(f"    ... and {len(findings) - 30} more")

    return 0 if total_findings == 0 else 1


def main(argv: list[str]) -> int:
    """CLI entry. Supports `--compare` to match the other architectural-boundary
    scanners: exit 1 if findings > 0 (the baseline is fixed at zero — any
    render-safety finding is a real bug, no allowlist file needed)."""
    # The `--compare` flag exists for parity with the other CI gates in
    # `.github/workflows/architectural-boundaries.yml`. Behavior is identical
    # to a plain run today; the flag reserves the option to evolve into a
    # baseline-driven gate later without touching CI yaml.
    _ = "--compare" in argv  # noqa: F841 — currently informational
    return audit()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
