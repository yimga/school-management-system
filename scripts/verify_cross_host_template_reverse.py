#!/usr/bin/env python3
"""verify_cross_host_template_reverse.py — a CBV template rendered on N hosts must
not reverse a namespace absent from any of those hosts.

RunMyCampus is HOST-SPLIT across urlconfs (``config.tenant_urls`` tenant host,
``config.urls`` admin/default, ``config.manager_urls`` operator,
``config.public_urls`` marketing). A single template can be the ``template_name``
of class-based views mounted on SEVERAL of those hosts at once — e.g.
``migration_cloud/connector/home.html`` renders on the tenant host
(``migration_cloud_connector``) AND under ``migration_cloud_portal`` (config) AND
``migration_cloud_super`` (manager). A hardcoded ``{% url 'migration_cloud_portal:… %}``
in that template then resolves on ONE host and raises ``NoReverseMatch`` (a 500)
on the others. That is exactly the connector-home cross-host 500 this repo hit —
and the reason the fix moved the URL resolution into the view (host-aware).

The sibling ``verify_url_name_integrity`` UNIONS names across every host, so a
cross-host name "exists" to it and it can never catch this class. This gate does:
for every CBV ``template_name`` reachable on ≥1 host, it flags an UNGUARDED
``{% url 'NS:name' %}`` whose namespace ``NS`` is absent from the flattened
namespace set of some host the template renders on.

Zero-FP by construction:
  * Only CBV ``template_name`` templates are considered (false-negative biased —
    include-only / function-view templates are skipped).
  * Per-host namespace sets are FLATTENED (nested namespaces included), so a
    template reversing a namespace that is merely NESTED on another host (resolved
    at request time via current_app) is NOT flagged.
  * A ``{% url %}`` inside a host-branch guard (``{% if shell == … %}`` /
    ``public_host_kind`` / ``is_manager_host`` / ``is_control_plane``) is skipped —
    the guard already selects the host-correct branch per host.
  * A ``{# cross-host-reverse-allow: <reason> #}`` marker on the ref line (or the
    line above) opts a deliberate site out.

Needs Django (live resolvers) → runs in ``ci.yml::django-tests``.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import django
from django.template.loader import get_template
from django.urls import get_resolver
from django.urls.resolvers import URLResolver

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)
BASELINE_PATH = os.path.join(
    REPO_ROOT, "var", "security-audit-baseline-cross-host-template-reverse.json"
)
MARKER = "cross-host-reverse-allow"

HOST_URLCONFS = (
    "config.tenant_urls",
    "config.urls",
    "config.manager_urls",
    "config.public_urls",
)

# Tokens in an {% if %}/{% elif %} condition that mark a host-specific branch —
# a reverse inside such a branch is host-selected and must not be flagged.
_HOST_GUARD_TOKENS = (
    "shell",
    "public_host_kind",
    "is_manager_host",
    "is_control_plane",
    "host_kind",
    "control_plane_shell",
)

_URL_RE = re.compile(r"""\{%\s*url\s+["']([a-zA-Z_][\w]*):([^"']+)["']""")
_TAG_RE = re.compile(r"\{%\s*(if|elif|else|endif)\b([^%]*)%\}", re.IGNORECASE)


def _flat_namespaces(resolver) -> set[str]:
    out: set[str] = set()
    for ns, entry in getattr(resolver, "namespace_dict", {}).items():
        out.add(ns)
        sub = entry[1]
        out |= _flat_namespaces(sub)
    return out


def _walk_callbacks(resolver):
    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            yield from _walk_callbacks(pattern)
        else:
            yield pattern.callback


def _cbv_template_names(resolver) -> set[str]:
    out: set[str] = set()
    for cb in _walk_callbacks(resolver):
        view_class = getattr(cb, "view_class", None)
        if view_class is None:
            continue
        name = getattr(view_class, "template_name", None)
        if isinstance(name, str) and name.strip():
            out.add(name)
        names = getattr(view_class, "template_names", None)
        if isinstance(names, (list, tuple)):
            for n in names:
                if isinstance(n, str) and n.strip():
                    out.add(n)
    return out


def _is_host_guard(cond: str) -> bool:
    low = (cond or "").lower()
    return any(tok in low for tok in _HOST_GUARD_TOKENS)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _has_marker(lines: list[str], lineno: int) -> bool:
    lo = max(0, lineno - 2)
    hi = min(len(lines), lineno)
    return any(MARKER in lines[i] for i in range(lo, hi))


def _unguarded_ns_refs(text: str) -> list[tuple[int, str, str]]:
    """Return (lineno, namespace, name) for each UNGUARDED namespaced url ref."""
    lines = text.splitlines()
    events = []
    for m in _TAG_RE.finditer(text):
        events.append((m.start(), "tag", m.group(1).lower(), m.group(2)))
    for m in _URL_RE.finditer(text):
        events.append((m.start(), "ref", m.group(1), m.group(2)))
    events.sort(key=lambda e: e[0])

    stack: list[bool] = []  # each frame: is it host-guarded?
    out: list[tuple[int, str, str]] = []
    for offset, kind, a, b in events:
        if kind == "tag":
            if a == "if":
                stack.append(_is_host_guard(b))
            elif a == "elif":
                if stack and _is_host_guard(b):
                    stack[-1] = True
            elif a == "endif":
                if stack:
                    stack.pop()
            # else: no change
        else:  # ref
            if any(stack):
                continue  # inside a host-branch guard
            lineno = _line_of(text, offset)
            if _has_marker(lines, lineno):
                continue
            out.append((lineno, a, b))
    return out


def scan() -> list[dict]:
    per_host_ns: dict[str, set[str]] = {}
    per_host_templates: dict[str, set[str]] = {}
    for uc in HOST_URLCONFS:
        try:
            resolver = get_resolver(uc)
        except Exception:  # noqa: BLE001 — a missing host urlconf is not this gate's job
            continue
        per_host_ns[uc] = _flat_namespaces(resolver)
        per_host_templates[uc] = _cbv_template_names(resolver)

    # template_name -> set of hosts it renders on
    template_hosts: dict[str, set[str]] = {}
    for uc, names in per_host_templates.items():
        for name in names:
            template_hosts.setdefault(name, set()).add(uc)

    findings: list[dict] = []
    for name, hosts in sorted(template_hosts.items()):
        try:
            origin = get_template(name).origin.name
        except Exception:  # noqa: BLE001 — dynamic/absent template names are out of scope
            continue
        if not origin or not os.path.isfile(origin):
            continue
        try:
            with open(origin, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        if "{% url" not in text and "{%url" not in text:
            continue
        rel = os.path.relpath(origin, REPO_ROOT).replace(os.sep, "/")
        for lineno, ns, ref_name in _unguarded_ns_refs(text):
            missing_on = sorted(
                uc for uc in hosts if ns not in per_host_ns.get(uc, set())
            )
            if missing_on:
                findings.append(
                    {
                        "file": rel,
                        "line": lineno,
                        "template": name,
                        "reverse": f"{ns}:{ref_name}",
                        "renders_on": sorted(hosts),
                        "missing_on": missing_on,
                        "reason": (
                            f"'{ns}' is absent on {missing_on} but this template also "
                            f"renders there; resolve the URL host-aware in the view "
                            f"(pass it into context) or add "
                            f"{{# {MARKER}: <reason> #}}"
                        ),
                    }
                )
    return sorted(findings, key=lambda f: (f["file"], f["line"]))


def _load_baseline() -> int:
    try:
        with open(BASELINE_PATH, encoding="utf-8") as fh:
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

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    django.setup()

    findings = scan()
    count = len(findings)

    if args.write_baseline:
        os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
        with open(BASELINE_PATH, "w", encoding="utf-8") as fh:
            json.dump(
                {"finding_count": count, "gate": "cross-host-template-reverse"},
                fh,
                indent=2,
            )
        print(f"baseline written: {count}")
        return 0

    if args.json:
        print(json.dumps({"finding_count": count, "findings": findings}, indent=2))
    else:
        for f in findings:
            print(f"{f['file']}:{f['line']}  {f['reverse']}  missing_on={f['missing_on']}")
        print(f"\ncross-host-template-reverse findings: {count}")

    if args.compare and count > _load_baseline():
        print(f"REGRESSION: {count} > baseline {_load_baseline()}", file=sys.stderr)
        return 1
    if args.strict and count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
