#!/usr/bin/env python3
"""scan_tenant_template_operator_links.py — no tenant-facing template may link to an
operator ("super"/"manager_") route outside a ``public_host_kind == 'manager'`` guard
(H4.6 of docs/generated/tenant_operator_isolation_forensic_audit_2026_07_04.md).

The entire tenant->operator LINK boundary rests today on a hand-applied
``{% if request.public_host_kind == 'manager' %}`` convention around every
``{% url 'super:...' %}`` in the shared dual-purpose shells (portal_base, sidebar,
command palette, ...). Nothing enforced it: ``verify_url_name_integrity`` even
CONFIRMS a ``super:`` name resolves (it is registered in the host-split
``config.manager_urls``), so a new tenant template with an ungated
``{% url 'super:x' %}`` would render an operator link to tenant users and pass every
other gate.

This gate flags an operator reference in a tenant-facing template unless it is inside a
manager-host guard (an enclosing ``{% if %}``/``{% elif %}`` whose condition mentions
``public_host_kind`` and ``manager``) or carries an
``<!-- operator-link-allow: <reason> -->`` marker (same line or the line above).

Operator references detected:
  * ``{% url "super:..." %}`` / ``{% url 'manager_...' %}`` (operator url names), and
  * a literal ``/super/`` in an ``href=``/``action=``/``hx-get=``/``hx-post=`` attribute.

Operator-only template subtrees (schools/super, siteconfig/super, control_plane_*,
manager_*, admin/, portal/operator/, ...) are excluded — a super: link there is
expected. Stdlib-only (regex) so it runs in the deps-free architectural-boundaries job.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)
TEMPLATES_ROOT = os.path.join(REPO_ROOT, "templates")
BASELINE_PATH = os.path.join(
    REPO_ROOT, "var", "security-audit-baseline-tenant-template-operator-links.json"
)
MARKER = "operator-link-allow"

# Path fragments (posix) marking an operator-only template — excluded from scanning.
_OPERATOR_PATH_FRAGMENTS = (
    "/super/",
    "/super_",
    "/operator/",
    "/manager_",
    "control_plane",
    "/admin/",
    "_control_plane",
    "/orchestration/",
    "/lifecycle/",
    "operator_",
    "/metadata/",
    "/platform_runtime/",
    "/marketplace/",
    "/mat_group_hub/",
)

# A template that (directly) extends one of these operator bases renders only on the
# control plane, so its super:/manager_ links are expected — exclude it.
_OPERATOR_BASE_TEMPLATES = frozenset(
    {"control_plane_base.html", "control_plane_skeleton.html"}
)
_EXTENDS_RE = re.compile(r"""\{%\s*extends\s+["']([^"']+)["']""")


def _extends_operator_base(text: str) -> bool:
    m = _EXTENDS_RE.search(text)
    if not m:
        return False
    return os.path.basename(m.group(1)) in _OPERATOR_BASE_TEMPLATES

# Operator-only attribute-context partials (emit ONLY data-attributes, so they can
# carry no HTML/Django marker without tripping scan_attribute_context_includes) that
# are included exclusively by operator/control-plane list templates.
_OPERATOR_ONLY_PARTIAL_BASENAMES = frozenset({"rmc_school_lens_api_attrs.html"})

_TAG_RE = re.compile(r"\{%\s*(if|elif|else|endif)\b([^%]*)%\}", re.IGNORECASE)
_URL_OP_RE = re.compile(r"""\{%\s*url\s+["'](super:[^"']*|manager_[^"']*)["']""")
_ATTR_SUPER_RE = re.compile(r"""(?:href|action|hx-get|hx-post|hx-put|data-url)\s*=\s*["']/super/""")
# any token we must place: (offset, kind, payload)


def _is_operator_template(rel_posix: str) -> bool:
    low = "/" + rel_posix.lower()
    return any(frag in low for frag in _OPERATOR_PATH_FRAGMENTS)


def _is_manager_condition(cond: str) -> bool:
    """True when an ``{% if %}`` condition confines its body to the manager host.

    Recognizes the canonical ``public_host_kind == 'manager'`` and the equivalent
    boolean context flags the shells use (``is_manager_host``, ``CONTROL_PLANE_SHELL``,
    ``is_control_plane_request``), all set from ``public_host_kind == 'manager'``.
    """
    c = cond.lower()
    if "public_host_kind" in c and "manager" in c:
        return True
    return any(flag in c for flag in ("is_manager_host", "control_plane_shell", "is_control_plane"))


def _iter_templates():
    for dirpath, _dirs, files in os.walk(TEMPLATES_ROOT):
        for fn in files:
            if not fn.endswith((".html", ".txt")):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")
            yield full, rel


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _has_marker(lines: list[str], lineno: int) -> bool:
    lo = max(0, lineno - 2)
    hi = min(len(lines), lineno)
    return any(MARKER in lines[i] for i in range(lo, hi))


def _scan_text(text: str):
    """Return list of (lineno) offsets of UNGUARDED operator references."""
    lines = text.splitlines()
    # Collect events: control-flow tags and operator refs, sorted by offset.
    events = []
    for m in _TAG_RE.finditer(text):
        events.append((m.start(), "tag", m.group(1).lower(), m.group(2)))
    for m in _URL_OP_RE.finditer(text):
        events.append((m.start(), "ref", None, None))
    for m in _ATTR_SUPER_RE.finditer(text):
        events.append((m.start(), "ref", None, None))
    events.sort(key=lambda e: e[0])

    # Stack of frames: {"guard": bool, "branch_ok": bool}
    stack: list[dict] = []
    findings_lines: list[int] = []
    for offset, kind, tag, cond in events:
        if kind == "tag":
            if tag == "if":
                g = _is_manager_condition(cond or "")
                stack.append({"guard": g, "branch_ok": g})
            elif tag == "elif":
                if stack:
                    g = _is_manager_condition(cond or "")
                    stack[-1]["guard"] = g
                    stack[-1]["branch_ok"] = g
            elif tag == "else":
                if stack and stack[-1]["guard"]:
                    # else of a manager guard is the NON-manager (tenant) branch
                    stack[-1]["branch_ok"] = False
            elif tag == "endif":
                if stack:
                    stack.pop()
        else:  # operator reference
            safe = any(f["guard"] and f["branch_ok"] for f in stack)
            if not safe:
                lineno = _line_of(text, offset)
                if not _has_marker(lines, lineno):
                    findings_lines.append(lineno)
    return findings_lines


def scan():
    findings = []
    for full, rel in _iter_templates():
        if _is_operator_template(rel):
            continue
        if os.path.basename(rel) in _OPERATOR_ONLY_PARTIAL_BASENAMES:
            continue
        try:
            with open(full, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        if "super:" not in text and "/super/" not in text and "manager_" not in text:
            continue
        if _extends_operator_base(text):
            continue
        for lineno in _scan_text(text):
            findings.append(
                {
                    "file": rel,
                    "line": lineno,
                    "reason": "operator (super:/manager_/`/super/`) link in a tenant-facing "
                    "template outside a public_host_kind=='manager' guard; wrap it or add "
                    "<!-- operator-link-allow: <reason> -->",
                }
            )
    return sorted(findings, key=lambda f: (f["file"], f["line"]))


def _load_baseline() -> int:
    try:
        with open(BASELINE_PATH, "r", encoding="utf-8") as fh:
            return int(json.load(fh).get("finding_count", 0))
    except (OSError, ValueError, KeyError):
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args()

    findings = scan()
    count = len(findings)

    if args.write_baseline:
        os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
        with open(BASELINE_PATH, "w", encoding="utf-8") as fh:
            json.dump({"finding_count": count, "gate": "tenant-template-operator-links"}, fh, indent=2)
        print(f"baseline written: {count}")
        return 0

    if args.json:
        print(json.dumps({"finding_count": count, "findings": findings}, indent=2))
    else:
        for f in findings:
            print(f"{f['file']}:{f['line']}")
        print(f"\ntenant-template-operator-links findings: {count}")

    if args.compare and count > _load_baseline():
        print(f"REGRESSION: {count} > baseline {_load_baseline()}", file=sys.stderr)
        return 1
    if args.strict and count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
