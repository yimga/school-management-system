"""audit_page_standards — Static audit of every page template in templates/.

Implements the contract documented in
``docs/design/PAGE_AND_DASHBOARD_STANDARDS.md`` and reports per-template
findings. Informational by default; CI can flip to ``--strict`` once a
baseline is achieved.

What it checks (per template that looks like a page — extends a base):

- Skip link present (or marked ``hide_skip_link`` deliberately)
- Exactly one <h1>
- <main id="main-content" role="main"> present (when not a partial)
- Forms include ``{% csrf_token %}``
- Marketing forms include the ``website_url`` honeypot input
- Skeleton loaders carry ``aria-busy``
- Toasts have ``aria-live`` (heuristic — checks for class "*toast*")
- No inline ``<script>`` (CSP-friendly)
- Inline ``style="…"`` count (informational)

Usage::

    python scripts/audit_page_standards.py
    python scripts/audit_page_standards.py --strict        # exit 1 on any error
    python scripts/audit_page_standards.py --json out.json  # machine-readable
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = ROOT / "templates"

# Regexes are intentionally simple — we are not parsing HTML, only doing
# heuristic best-effort lints. The verifier's value is the consistent baseline,
# not perfect parsing.
RE_EXTENDS = re.compile(r'\{%\s*extends\s+["\']([^"\']+)["\']', re.IGNORECASE)
# A skip link is any anchor pointing to a #*-content target, OR a class hint
# (visually-hidden-focusable / skip-link). All these are valid skip-link forms.
RE_SKIP_LINK = re.compile(
    r'href="#[\w-]*content"|skip-link|visually-hidden-focusable',
    re.IGNORECASE,
)
RE_HIDE_SKIP_LINK = re.compile(r"hide_skip_link", re.IGNORECASE)
RE_H1 = re.compile(r"<h1[\s>]", re.IGNORECASE)
# ARIA 1.2: <main> and <div role="main"> are equivalent landmarks.
# Accept either as satisfying the main-landmark requirement.
RE_MAIN = re.compile(
    r'<main[\s>]|<div[^>]*\brole="main"',
    re.IGNORECASE,
)
RE_FORM_TAG = re.compile(r"<form[\s>]", re.IGNORECASE)
# Only POST forms need CSRF; GET search forms intentionally don't.
# We treat method="post" (any quotes) AND a Django template expression that
# resolves to "post" (e.g. `{% if x %}post{% else %}get{% endif %}`) as POST.
RE_FORM_POST = re.compile(
    r'<form[^>]*\bmethod=["\']?post["\']?',
    re.IGNORECASE,
)
RE_FORM_DYNAMIC_METHOD_POST = re.compile(
    r'<form[^>]*\bmethod=["\'][^"\']*\bpost\b[^"\']*["\']',
    re.IGNORECASE,
)
RE_CSRF = re.compile(r"\{%\s*csrf_token\s*%\}", re.IGNORECASE)
RE_HONEYPOT = re.compile(r'name="website_url"', re.IGNORECASE)
RE_SKELETON = re.compile(r"skeleton-loader", re.IGNORECASE)
RE_ARIA_BUSY = re.compile(r'aria-busy="true"', re.IGNORECASE)
RE_TOAST_CLASS = re.compile(r'class="[^"]*\btoast\b', re.IGNORECASE)
RE_ARIA_LIVE = re.compile(r'aria-live="(polite|assertive)"', re.IGNORECASE)
# Inline executable script: <script> with no `src=` AND no `type="application/json|ld+json"`.
# JSON / linked-data data-island tags are CSP-safe (browsers don't execute them).
RE_INLINE_SCRIPT = re.compile(
    r'<script(?![^>]*\bsrc=)(?![^>]*\btype=["\'](?:application/(?:json|ld\+json)|importmap)["\'])',
    re.IGNORECASE,
)
RE_INLINE_STYLE_ATTR = re.compile(r'\bstyle="[^"]+"', re.IGNORECASE)


def _is_partial_path(path: Path) -> bool:
    """A 'partial' is anything in /partials/, /components/, /errors/, /emails/,
    or under Django's /admin/ override directory — none are top-level pages
    that need their own landmarks (they're either fragments, error pages with
    their own minimal scaffold, transactional emails, or admin overrides that
    inherit Django admin's chrome).
    """
    parts = {p.lower() for p in path.parts}
    return any(d in parts for d in (
        "partials", "components", "errors", "emails", "admin", "unfold",
    ))


def _is_marketing_path(path: Path) -> bool:
    return any(p.lower() == "marketing" for p in path.parts)


def _extends_target(text: str) -> str | None:
    """Return the path the template extends (e.g. 'base.html') or None."""
    m = RE_EXTENDS.search(text)
    if not m:
        return None
    return m.group(1).strip()


# Cache: template path → (provides_skip_link, provides_main_landmark)
# Computed by transitively walking {% extends %} chains so a child of a child
# of a base inherits the landmarks correctly without per-base allowlisting.
_landmark_cache: dict[str, tuple[bool, bool]] = {}


def _resolve_template_path(rel_target: str) -> Path | None:
    """Resolve a template name (e.g. 'portal_base.html') to a file path."""
    rel_target = rel_target.lstrip("/")
    candidate = TEMPLATES_ROOT / rel_target
    if candidate.exists():
        return candidate
    return None


RE_INCLUDE = re.compile(r'\{%\s*include\s+["\']([^"\']+)["\']', re.IGNORECASE)


def _included_paths(text: str) -> list[Path]:
    """Resolve every {% include "..." %} in ``text`` to a file path."""
    out: list[Path] = []
    for m in RE_INCLUDE.finditer(text):
        target = m.group(1).strip()
        p = _resolve_template_path(target)
        if p is not None:
            out.append(p)
    return out


def _landmarks_provided(path: Path, _seen: set[str] | None = None) -> tuple[bool, bool, bool]:
    """Return ``(skip_link, main_landmark, h1)`` provided by ``path`` or its base/include tree.

    Walks ``{% extends %}`` AND ``{% include %}`` recursively; cycle-safe via ``_seen``.
    The h1 component is True when the template (or any of its included partials,
    transitively) renders an ``<h1>`` element. Without this, pages whose primary
    heading lives in a shared header partial (e.g. ``components/page_header.html``)
    were false-flagged as missing_h1.
    """
    key = str(path)
    if key in _landmark_cache:
        cached = _landmark_cache[key]
        # Older cache entries had 2 values — ignore those.
        if len(cached) == 3:
            return cached  # type: ignore[return-value]

    _seen = _seen or set()
    if key in _seen:
        return (False, False, False)
    _seen = _seen | {key}

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return (False, False, False)

    text_clean = _strip_comments(text) if "_strip_comments" in globals() else text
    has_skip = bool(RE_SKIP_LINK.search(text_clean))
    has_main = bool(RE_MAIN.search(text_clean))
    has_h1 = bool(RE_H1.search(text_clean))

    # Walk {% extends %}
    parent = _extends_target(text)
    if parent:
        parent_path = _resolve_template_path(parent)
        if parent_path is not None:
            ps, pm, ph = _landmarks_provided(parent_path, _seen)
            has_skip = has_skip or ps
            has_main = has_main or pm
            has_h1 = has_h1 or ph

    # Walk {% include %} — partials can supply the h1 even if the page doesn't.
    for inc_path in _included_paths(text_clean):
        is_, im_, ih_ = _landmarks_provided(inc_path, _seen)
        has_skip = has_skip or is_
        has_main = has_main or im_
        has_h1 = has_h1 or ih_

    result = (has_skip, has_main, has_h1)
    _landmark_cache[key] = result  # type: ignore[assignment]
    return result


_RE_DJANGO_COMMENT_BLOCK = re.compile(
    r"\{%\s*comment\s*(?:\".*?\")?\s*%\}.*?\{%\s*endcomment\s*%\}",
    re.IGNORECASE | re.DOTALL,
)
_RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_RE_DJANGO_LINE_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)


def _strip_comments(text: str) -> str:
    """Strip Django + HTML comments — they don't reach the browser."""
    text = _RE_DJANGO_COMMENT_BLOCK.sub("", text)
    text = _RE_HTML_COMMENT.sub("", text)
    text = _RE_DJANGO_LINE_COMMENT.sub("", text)
    return text


def _audit_one(path: Path) -> dict:
    raw_text = path.read_text(encoding="utf-8", errors="replace")
    # Strip comment blocks before regex matching so commented-out <script>
    # tags (Django {% comment %} or <!-- ... -->) don't false-positive.
    text = _strip_comments(raw_text)
    extends_target = _extends_target(text)
    extends_base = extends_target is not None
    findings: list[str] = []

    is_partial = _is_partial_path(path)
    is_marketing = _is_marketing_path(path)

    # A "thin base" template is one that defines no {% block content %} body
    # of its own — it only sets block overrides for child templates. Children
    # of such templates inherit parents' landmarks; the base itself ships no
    # rendered <body> content. Skip page-level checks for these.
    declares_content = bool(re.search(r"\{%\s*block\s+content\s*%\}", text, re.IGNORECASE))
    is_thin_base = extends_base and not declares_content

    # Only run page-level checks on templates that extend a base AND aren't
    # under partials/ or components/ — those are fragments, not pages.
    if extends_base and not is_partial and not is_thin_base:
        # Inheritance: a child page inherits skip-link + main landmark + h1 from
        # its base — and from its base's base, AND from any partial it includes.
        base_skip = base_main = base_h1 = False
        if extends_target:
            base_path = _resolve_template_path(extends_target)
            if base_path is not None:
                base_skip, base_main, base_h1 = _landmarks_provided(base_path)

        # The page's OWN includes can also satisfy the requirement (e.g.
        # components/page_header.html provides an <h1> for the including page).
        for inc_path in _included_paths(text):
            i_skip, i_main, i_h1 = _landmarks_provided(inc_path)
            base_skip = base_skip or i_skip
            base_main = base_main or i_main
            base_h1 = base_h1 or i_h1

        if not (
            RE_SKIP_LINK.search(text)
            or RE_HIDE_SKIP_LINK.search(text)
            or base_skip
        ):
            findings.append("missing_skip_link")

        h1_count = len(RE_H1.findall(text))
        if h1_count == 0 and not base_h1:
            findings.append("missing_h1")
        elif h1_count > 1:
            findings.append(f"multiple_h1:{h1_count}")

        if not (RE_MAIN.search(text) or base_main):
            findings.append("missing_main_landmark")

    # Form-level checks apply only to POST forms — GET search forms do not need CSRF.
    has_post_form = bool(RE_FORM_POST.search(text) or RE_FORM_DYNAMIC_METHOD_POST.search(text))
    if has_post_form:
        if not RE_CSRF.search(text):
            findings.append("form_missing_csrf_token")
        if is_marketing and not RE_HONEYPOT.search(text):
            findings.append("marketing_form_missing_honeypot")

    # Skeleton loader — when present, must be aria-busy.
    if RE_SKELETON.search(text) and not RE_ARIA_BUSY.search(text):
        findings.append("skeleton_loader_missing_aria_busy")

    # Toast — when present, must have aria-live.
    if RE_TOAST_CLASS.search(text) and not RE_ARIA_LIVE.search(text):
        findings.append("toast_missing_aria_live")

    # Inline scripts (CSP-hostile) — count. Django admin / unfold templates
    # use vendor-supplied inline JS we don't control, so we exempt them from
    # this check (page-level a11y checks were already exempted earlier).
    parts = {p.lower() for p in path.parts}
    is_vendor_admin = bool(parts & {"admin", "unfold"})
    if not is_vendor_admin:
        inline_scripts = len(RE_INLINE_SCRIPT.findall(text))
        if inline_scripts:
            findings.append(f"inline_script_count:{inline_scripts}")

    # Inline style attributes — informational.
    inline_styles = len(RE_INLINE_STYLE_ATTR.findall(text))

    try:
        rel_path = str(path.relative_to(ROOT))
    except ValueError:
        rel_path = str(path)
    return {
        "path": rel_path,
        "is_partial": is_partial,
        "is_marketing": is_marketing,
        "extends_base": extends_base,
        "findings": findings,
        "inline_style_count": inline_styles,
    }


def _iter_templates() -> list[Path]:
    if not TEMPLATES_ROOT.exists():
        return []
    return sorted(p for p in TEMPLATES_ROOT.rglob("*.html") if "node_modules" not in p.parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="exit 1 on any finding")
    parser.add_argument("--json", type=str, default="", help="path to write JSON report")
    args = parser.parse_args()

    rows = [_audit_one(p) for p in _iter_templates()]
    finding_total = sum(len(r["findings"]) for r in rows)
    pages_with_findings = sum(1 for r in rows if r["findings"])

    summary = {
        "templates_scanned": len(rows),
        "pages_with_findings": pages_with_findings,
        "finding_total": finding_total,
        "by_finding": {},
    }
    counter: dict[str, int] = {}
    for r in rows:
        for f in r["findings"]:
            # Strip count suffixes for grouping
            key = f.split(":", 1)[0]
            counter[key] = counter.get(key, 0) + 1
    summary["by_finding"] = dict(sorted(counter.items(), key=lambda kv: -kv[1]))

    print(f"audit_page_standards: scanned {len(rows)} templates")
    print(f"  pages with findings: {pages_with_findings}")
    print(f"  total findings:      {finding_total}")
    if summary["by_finding"]:
        print("  finding histogram:")
        for k, v in summary["by_finding"].items():
            print(f"    {v:5d}  {k}")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"summary": summary, "rows": rows}, indent=2),
            encoding="utf-8",
        )
        print(f"  json report: {args.json}")

    if args.strict and finding_total:
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
