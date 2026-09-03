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
import ast
import inspect
import json
import os
import re
import sys
import textwrap

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

# Matches BOTH ``{% url 'ns:name' %}`` and ``{% url 'bare_name' %}``. The bare form
# was invisible to this gate until 2026-08-31 -- see _flat_names above.
_URL_RE = re.compile(r"""\{%\s*url\s+["'](\w[\w.\-]*(?::\w[\w.\-]*)*)["']([^%]*)%\}""")
_TAG_RE = re.compile(r"\{%\s*(if|elif|else|endif)\b([^%]*)%\}", re.IGNORECASE)
_CHILD_RE = re.compile(r"""\{%\s*(?:extends|include)\s+["']([^"']+\.html?)["']""")

#: Depth cap for the extends/include walk (cycle + runaway guard).
_MAX_TEMPLATE_DEPTH = 12


def _flat_namespaces(resolver) -> set[str]:
    """Every namespace ``reverse()`` can actually resolve on this urlconf.

    Both kinds count. ``namespace_dict`` holds INSTANCE namespaces; ``app_dict``
    holds APPLICATION namespaces, and ``django.urls.reverse`` resolves an app
    namespace to one of its instances (``reverse("admin:index")`` works even though
    the tenant admin is mounted under the instance namespace ``tenant_admin``).
    Reading only ``namespace_dict`` reported ``admin:*`` as missing from
    ``config.tenant_urls``, where ``reverse("admin:index", urlconf=...)`` returns
    ``/admin/`` --- three false findings that made the real ones easy to dismiss.
    """
    out: set[str] = set(getattr(resolver, "app_dict", {}))
    for ns, entry in getattr(resolver, "namespace_dict", {}).items():
        out.add(ns)
        sub = entry[1]
        out |= _flat_namespaces(sub)
    return out


def _flat_names(resolver) -> set[str]:
    """Fully-qualified view names reversible on this urlconf.

    Needed for the NAMESPACE-LESS half of this gate: ``{% url 'manager_help_center' %}``
    carries no namespace at all, so the namespace test above can never see it, and
    ``manager_help_center`` is mounted ONLY in ``config.manager_urls``. That exact tag
    sat in ``accounts/partials/operator_documentation_body.html`` --- a body the
    control-plane shell also renders on a ``local`` host (``config.urls``) --- and
    turned ``/authentication/documentation/`` into a 500 there.
    """
    out: set[str] = set()

    def descend(node, prefix: str = "") -> None:
        for key in getattr(node, "reverse_dict", {}):
            if isinstance(key, str):
                out.add(prefix + key)
        for ns, entry in getattr(node, "namespace_dict", {}).items():
            descend(entry[1], prefix + ns + ":")

    descend(resolver)
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


# --- function-view template discovery (host-bound render() / TemplateResponse) ---
# A CBV exposes its template via ``view_class.template_name`` (read above). A
# function view names its template as a literal arg to ``render(request, "x.html")``
# / ``TemplateResponse(request, "x.html")`` — invisible to the CBV walk, which is
# exactly why the help-center function view's cross-host reverse shipped a 500.
# We AST-parse each function-view callback's OWN source and collect those literals.
# False-negative biased: a render via a helper, a non-literal path, or a callback
# whose source can't be read is skipped (never a false finding).
_FV_RENDER_TEMPLATE_ARG = {"render": 1, "TemplateResponse": 1}
_FV_TEMPLATE_KWARGS = {"template_name", "template"}

# Shell-dispatch keywords. RunMyCampus does not render most operator pages with a
# literal render() -- the view names its BODY partial and hands it to a shell
# helper (render_account_page / render_siteconfig_operator_page /
# render_kb_if_operator), which then does
# ``{% include operator_cp_body_template %}`` -- a VARIABLE include no template
# walk can follow. Every such body was therefore invisible to this gate, and one
# of them (accounts/partials/operator_documentation_body.html) carried a bare
# {% url 'manager_help_center' %}: a 500 on every local/dev host, since
# use_control_plane_shell() returns True for public_host_kind "local" too.
#
# A literal keyword in the view's OWN source is an exact view->template binding,
# exactly like a CBV ``template_name``, so these are graded on the STRICT tier.
#
# Which HOSTS a body renders on is a property of the helper's own gate, not of
# where the view is mounted, so it is DECLARED here per callee (same reasoning as
# audit_shell_url_namespace_contract.SHELL_HOSTS) and then INTERSECTED with the
# urlconfs that actually mount the view. A helper nobody classified is not
# assumed -- it is skipped, so this can only ever be false-negative.
_SHELL_BODY_KWARGS = {"body_template", "operator_body_template", "manager_body_template"}

#: callee name -> urlconfs its body partial can render under.
#: ``None`` means "no host gate at all -- wherever the view is mounted".
_SHELL_BODY_CALLEES: dict[str, tuple[str, ...] | None] = {
    # Gate: apps.schools.control_plane.use_control_plane_shell(request), which is
    # True for public_host_kind in ("manager", "local") -- and a "local" host is
    # routed to config.urls by UrlConfSwitcherMiddleware. That second host is the
    # one everybody forgets, and it is where the documentation body 500'd.
    "render_account_page": ("config.manager_urls", "config.urls"),
    "render_siteconfig_operator_page": ("config.manager_urls", "config.urls"),
    # Gate: apps.portal.kb_context.is_operator_help_request(request), which is
    # ``request.urlconf == "config.manager_urls"`` -- manager host ONLY.
    "render_kb_if_operator": ("config.manager_urls",),
    "render_operator_kb_page": ("config.manager_urls",),
    # No host gate: renders on whatever urlconf mounts the view.
    "render_manager_report_page": None,
}


def _call_func_name(call: ast.Call) -> str | None:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _str_literal(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_request_first_arg(call: ast.Call) -> bool:
    """Gate render()/TemplateResponse() on a literal ``request`` first arg so a
    custom ``obj.render(...)`` method is never misread as the Django shortcut."""
    if not call.args:
        return False
    a = call.args[0]
    return (isinstance(a, ast.Name) and a.id == "request") or (
        isinstance(a, ast.Attribute) and a.attr == "request"
    )


def _looks_like_template(value: str) -> bool:
    return bool(value) and " " not in value and value.endswith((".html", ".htm"))


def _fv_rendered_templates(source: str) -> set[str]:
    out: set[str] = set()
    try:
        tree = ast.parse(textwrap.dedent(source))
    except (SyntaxError, ValueError):
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_func_name(node)
        if name not in _FV_RENDER_TEMPLATE_ARG or not _is_request_first_arg(node):
            continue
        idx = _FV_RENDER_TEMPLATE_ARG[name]
        val = _str_literal(node.args[idx]) if len(node.args) > idx else None
        if val is None:
            for kw in node.keywords:
                if kw.arg in _FV_TEMPLATE_KWARGS:
                    val = _str_literal(kw.value)
                    if val:
                        break
        if val and _looks_like_template(val):
            out.add(val)
    return out


def _shell_body_templates(source: str) -> dict[str, tuple[str, ...] | None]:
    """{body template -> declared hosts} for classified shell-helper calls."""
    out: dict[str, tuple[str, ...] | None] = {}
    try:
        tree = ast.parse(textwrap.dedent(source))
    except (SyntaxError, ValueError):
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = _call_func_name(node)
        if callee not in _SHELL_BODY_CALLEES:
            continue
        declared = _SHELL_BODY_CALLEES[callee]
        for kw in node.keywords:
            if kw.arg not in _SHELL_BODY_KWARGS:
                continue
            val = _str_literal(kw.value)
            if val and _looks_like_template(val):
                out[val] = declared
    return out


def _function_view_template_names(
    resolver,
) -> tuple[set[str], dict[str, tuple[str, ...] | None]]:
    """(loose render() literals, strict shell-body kwargs -> declared hosts)."""
    out: set[str] = set()
    shell: dict[str, tuple[str, ...] | None] = {}
    seen: set[int] = set()
    for cb in _walk_callbacks(resolver):
        if getattr(cb, "view_class", None) is not None:
            continue  # CBV — covered by _cbv_template_names
        if id(cb) in seen:
            continue
        seen.add(id(cb))
        try:
            source = inspect.getsource(inspect.unwrap(cb))
        except (OSError, TypeError, ValueError):
            continue  # C funcs, dynamically-built views, unreadable source
        out |= _fv_rendered_templates(source)
        shell.update(_shell_body_templates(source))
    return out, shell


def _is_finding(is_cbv: bool, missing_on: set[str], hosts: set[str]) -> bool:
    """Two-tier sensitivity. A CBV's ``template_name`` maps to hosts exactly, so a
    namespace absent on ANY host it renders on is a real conditional 500. A template
    discovered only via a function-view ``render()`` is looser (shared app-includes
    attribute a page to hosts it never serves), so it is a finding only when the
    namespace is absent on EVERY host it renders on — a guaranteed 500 wherever it
    renders, which ``verify_url_name_integrity`` misses (it unions across hosts)."""
    if not missing_on:
        return False
    if not is_cbv and set(missing_on) != set(hosts):
        return False
    return True


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
    """Return (lineno, namespace, name) for each UNGUARDED url ref.

    ``namespace`` is "" for a namespace-less name
    (``{% url 'manager_help_center' %}``); the caller then tests the NAME against
    the host's reversible-name set instead of testing the namespace.
    """
    lines = text.splitlines()
    events = []
    for m in _TAG_RE.finditer(text):
        events.append((m.start(), "tag", m.group(1).lower(), m.group(2)))
    for m in _URL_RE.finditer(text):
        # `{% url 'ns:name' as var %}` cannot raise - URLNode re-raises only when
        # asvar is None; otherwise it sets the var to "". Flagging it would
        # penalise the very idiom this gate wants authors to adopt.
        if re.search(r"\bas\s+\w+\s*$", m.group(2).strip()):
            continue
        view_name = m.group(1)
        namespace, _, rest = view_name.partition(":")
        if rest:
            events.append((m.start(), "ref", namespace, rest))
        else:
            events.append((m.start(), "ref", "", view_name))
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


_TEXT_CACHE: dict[str, str | None] = {}


def _template_text(name: str) -> str | None:
    """Read a template's raw source once, by resolved origin. None when absent."""
    if name in _TEXT_CACHE:
        return _TEXT_CACHE[name]
    text: str | None = None
    try:
        origin = get_template(name).origin.name
        if origin and os.path.isfile(origin):
            with open(origin, encoding="utf-8") as fh:
                text = fh.read()
    except Exception:  # noqa: BLE001 - dynamic/absent names are out of scope
        text = None
    _TEXT_CACHE[name] = text
    return text


def _unguarded_children(text: str) -> set[str]:
    """Literal extends/include targets that are NOT inside a host-branch guard.

    A host-guarded include already selects the host-correct child, so propagating the
    parent's full host set through it would manufacture a false finding. Non-literal
    targets are skipped - false-negative biased, as everywhere else in this gate.
    """
    events: list[tuple[int, str, str, str]] = []
    for m in _TAG_RE.finditer(text):
        events.append((m.start(), "tag", m.group(1).lower(), m.group(2)))
    for m in _CHILD_RE.finditer(text):
        events.append((m.start(), "child", "", m.group(1)))
    events.sort(key=lambda e: e[0])

    stack: list[bool] = []
    out: set[str] = set()
    for _offset, kind, a, b in events:
        if kind == "tag":
            if a == "if":
                stack.append(_is_host_guard(b))
            elif a == "elif":
                if stack and _is_host_guard(b):
                    stack[-1] = True
            elif a == "endif":
                if stack:
                    stack.pop()
        elif not any(stack):
            out.add(b)
    return out


def _propagate_hosts(host_map: dict[str, set[str]]) -> None:
    """Propagate each root's host set down its extends/include closure, IN PLACE.

    The gate used to scan a root template's OWN source only, so a bare reverse
    INHERITED from a shared parent or partial was invisible. That is how the
    command-palette 500 shipped: components/rmc_command_palette.html reversed
    kb: and siteconfig: - both absent from config.public_urls - and base.html
    includes it on every authenticated page, but the palette is include-only so it
    is never a CBV template_name nor a function-view render() literal.

    Called SEPARATELY for the CBV map and the function-view map so the caller keeps
    the gate's two-tier sensitivity. Merging them would let a loose function-view
    host attribution ("shared app-includes attribute a page to hosts it never
    serves") inherit the strict CBV tier and manufacture false findings.
    """
    queue: list[tuple[str, int]] = [(name, 0) for name in list(host_map)]
    while queue:
        name, depth = queue.pop()
        if depth >= _MAX_TEMPLATE_DEPTH:
            continue
        text = _template_text(name)
        if not text:
            continue
        hosts = host_map.get(name, set())
        if not hosts:
            continue
        for child in _unguarded_children(text):
            before = host_map.get(child)
            after = (before or set()) | hosts
            if before is None or after != before:
                host_map[child] = after
                queue.append((child, depth + 1))


def scan() -> list[dict]:
    per_host_ns: dict[str, set[str]] = {}
    per_host_names: dict[str, set[str]] = {}
    per_host_cbv: dict[str, set[str]] = {}
    per_host_fv: dict[str, set[str]] = {}
    per_host_shell: dict[str, dict[str, tuple[str, ...] | None]] = {}
    for uc in HOST_URLCONFS:
        try:
            resolver = get_resolver(uc)
        except Exception:  # noqa: BLE001 — a missing host urlconf is not this gate's job
            continue
        per_host_ns[uc] = _flat_namespaces(resolver)
        per_host_names[uc] = _flat_names(resolver)
        per_host_cbv[uc] = _cbv_template_names(resolver)
        per_host_fv[uc], per_host_shell[uc] = _function_view_template_names(
            resolver
        )

    # Two INDEPENDENT maps: template -> hosts, by discovery kind. A CBV
    # template_name maps to hosts exactly; function-view discovery is looser. Each
    # is propagated down its own extends/include closure so a partial inherits the
    # tier of the roots that actually reach it (see _propagate_hosts).
    cbv_hosts: dict[str, set[str]] = {}
    fv_hosts: dict[str, set[str]] = {}
    shell_hosts: dict[str, set[str]] = {}
    for uc in per_host_ns:
        for name in per_host_cbv.get(uc, set()):
            cbv_hosts.setdefault(name, set()).add(uc)
        for name in per_host_fv.get(uc, set()):
            fv_hosts.setdefault(name, set()).add(uc)
        for name, declared in per_host_shell.get(uc, {}).items():
            # Mounted here, so this host counts -- but only if the helper's own
            # gate can select this body on it.
            if declared is None or uc in declared:
                shell_hosts.setdefault(name, set()).add(uc)
            else:
                shell_hosts.setdefault(name, set())

    root_templates = set(cbv_hosts) | set(fv_hosts) | set(shell_hosts)
    _propagate_hosts(cbv_hosts)
    _propagate_hosts(fv_hosts)
    _propagate_hosts(shell_hosts)

    template_hosts: dict[str, set[str]] = {}
    for name in set(cbv_hosts) | set(fv_hosts) | set(shell_hosts):
        template_hosts[name] = (
            cbv_hosts.get(name, set())
            | fv_hosts.get(name, set())
            | shell_hosts.get(name, set())
        )

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
        # CBV template_name → hosts is exact, so a namespace absent on ANY host it
        # renders on is a real cross-host 500 (the connector-home class). A template
        # discovered ONLY through a function-view render() is looser — shared app
        # includes (e.g. apps.accounts.urls on the marketing host) attribute a page
        # to hosts it never actually serves — so we require the namespace to be
        # absent on EVERY host the page renders on: that is a guaranteed 500 wherever
        # it renders (the /help/ class), which verify_url_name_integrity misses
        # because it unions names across all hosts. This keeps the gate zero-FP.
        strict_hosts = cbv_hosts.get(name, set()) | shell_hosts.get(name, set())
        rel = os.path.relpath(origin, REPO_ROOT).replace(os.sep, "/")
        for lineno, ns, ref_name in _unguarded_ns_refs(text):
            if ns:
                missing_on = sorted(
                    uc for uc in hosts if ns not in per_host_ns.get(uc, set())
                )
            else:
                # Namespace-less name: the namespace test above is vacuous, so ask
                # the only question that means anything -- is the NAME reversible
                # on this host? manager_help_center is mounted in config.manager_urls
                # and nowhere else; a bare tag for it in a body the control-plane
                # shell also renders on a `local` host is a 500 on localhost.
                missing_on = sorted(
                    uc
                    for uc in hosts
                    if ref_name not in per_host_names.get(uc, set())
                )
            missing_strict = {uc for uc in strict_hosts if uc in set(missing_on)}
            # Strict: a CBV template_name maps to hosts exactly, so absent on ANY
            # host it renders on is a real conditional 500. Loose: absent on EVERY
            # host is a guaranteed 500 wherever it renders.
            is_cbv = bool(missing_strict)
            if not _is_finding(is_cbv, set(missing_on), hosts):
                continue
            findings.append(
                {
                    "file": rel,
                    "line": lineno,
                    "template": name,
                    "reverse": f"{ns}:{ref_name}" if ns else ref_name,
                    "renders_on": sorted(hosts),
                    "missing_on": missing_on,
                    "discovery": "exact" if is_cbv else "function_view",
                    "via": "root" if name in root_templates else "include_chain",
                    "reason": (
                        f"{ns + ':' + ref_name if ns else ref_name} is not reversible "
                        f"on {missing_on} but this template also renders there; "
                        f"resolve the URL host-aware in the view (pass it into "
                        f"context), use the `{{% url '...' as var %}}` form, or add "
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
