"""Shell chrome may not hard-reverse a namespace its host does not mount.

WHY THIS EXISTS. ``templates/portal_base.html`` renders on the TENANT host and on the
OPERATOR host -- ``data-surface="{% if request.public_host_kind == 'manager' %}...``
in its own opening tag says so. Line 942 includes
``partials/rmc_support_quick_create.html``, which carries a bare
``{% url 'portal:support_quick_create' %}`` under no host guard at all. ``portal:``
is mounted only in ``config/tenant_urls.py``. On ``manager.runmycampus.com`` that tag
raises ``NoReverseMatch: 'portal' is not a registered namespace`` while rendering the
CLOSING chrome -- so the view ran, the query ran, the permission passed, the body
rendered, and the response was still a 500. Seven ``/super/migration/connectors/*``
routes were dead this way, and the same partial is reached by all 354 templates that
extend ``portal_base.html``.

WHY NO EXISTING GATE SEES IT.

* ``verify_url_name_integrity`` unions names across host urlconfs and asks whether
  each resolves SOMEWHERE. ``portal:support_quick_create`` does.
* ``audit_url_kwarg_contract`` checks view signatures, not template bodies.
* A test that renders the template supplies its own host, so it renders under the one
  urlconf where the tag is fine.
* Django never attempts a reverse at compile time, by design.

WHAT COUNTS AS SAFE. Two things, and the codebase already uses both:

``as`` form   ``{% url 'portal:x' as u %}`` assigns an empty string instead of
              raising. ``portal_base.html`` itself does this for four tenant-only
              names. This is the escape hatch for chrome that is optional on a host.

host guard    A tag inside ``{% if request.public_host_kind == 'manager' %}`` cannot
              render on a host where the namespace is missing.
              ``control_plane_sidebar.html`` guards ``super:sidebar_badges`` this way,
              and an ``{% include %}`` that is itself host-guarded protects everything
              downstream of it.

Guard tracking is what makes this gate usable rather than noise: a first cut without
it reported 53 tags, 47 of which were already guarded and could never fire. A
zero-baseline gate that cries wolf gets switched off, and then the six real ones ride
back in.

Guarded tags are still PRINTED, with a count -- they are safe but load-bearing, and a
future edit that removes the enclosing ``{% if %}`` should be visible as a jump in
that number rather than a silent new 500.

Zero-tolerance on UNGUARDED findings: exit 1.

    python scripts/audit_shell_url_namespace_contract.py
    python scripts/audit_shell_url_namespace_contract.py --json
    python scripts/audit_shell_url_namespace_contract.py --show-guarded
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

#: Which urlconfs each shell actually renders under. DECLARED, not inferred -- the
#: same reasoning as ``deployment_parity.PARITY_MUST_MATCH``: a shell nobody
#: classified must not be silently assumed single-host. ``config.urls`` is the
#: DEVELOPER urlconf and mounts everything, so it can never produce a finding and is
#: deliberately absent -- which is exactly why the box, misrouted onto config.urls,
#: hid this whole class until 2026-08-22.
SHELL_HOSTS: dict[str, tuple[str, ...]] = {
    # Branches on request.public_host_kind == 'manager' in its own <html> tag, and
    # /super/migration/connectors/* proved the operator half at runtime.
    "portal_base.html": ("config.tenant_urls", "config.manager_urls"),
    # apps/migration_cloud/urls.py is mounted in BOTH tenant_urls and manager_urls,
    # and connectors/operator/ renders control_plane_base -- so it reaches both.
    "control_plane_base.html": ("config.manager_urls", "config.tenant_urls"),
    "backend_base.html": ("config.tenant_urls", "config.manager_urls"),
    "backend_base_manager.html": ("config.manager_urls",),
    "backend_base_tenant.html": ("config.tenant_urls",),
    # Marketing / unauthenticated shell: public host plus both app hosts.
    "base.html": ("config.public_urls", "config.tenant_urls", "config.manager_urls"),
}

#: Context lookups that decide which host is rendering. A condition mentioning any of
#: these is treated as a host guard.
HOST_TOKENS = (
    "public_host_kind",
    "is_tenant_host",
    "is_manager_host",
    "is_public_host",
    "rmc_host_kind",
    "shell_is_super",
    "shell_is_portal",
)

_EXTENDS = re.compile(r"{%\s*extends\s+([\"'])(?P<name>[^\"']+)\1\s*%}")
_URLTAG = re.compile(r"{%\s*url\s+([\"'])(?P<name>[^\"']+)\1(?P<rest>.*?)%}", re.S)
_ASVAR = re.compile(r"\bas\s+[A-Za-z_][A-Za-z0-9_]*\s*$")
# One pass over every block tag we care about, in document order.
_TAGS = re.compile(
    r"{%\s*(?P<tag>if|elif|else|endif|include|extends|url)\b(?P<body>.*?)%}", re.S
)
_STRLIT = re.compile(r"^\s*([\"'])(?P<name>[^\"']+)\1")


def _is_host_guard(condition: str) -> bool:
    return any(token in condition for token in HOST_TOKENS)


def _template_path(name: str) -> str | None:
    candidate = os.path.join(REPO, "templates", *name.split("/"))
    if os.path.isfile(candidate):
        return candidate
    apps_dir = os.path.join(REPO, "apps")
    if os.path.isdir(apps_dir):
        for app in sorted(os.listdir(apps_dir)):
            candidate = os.path.join(apps_dir, app, "templates", *name.split("/"))
            if os.path.isfile(candidate):
                return candidate
    return None


def _read(name: str) -> str:
    path = _template_path(name)
    if path is None:
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def scan(name: str) -> tuple[list[dict], list[dict], list[str]]:
    """(url tags, child template edges, unresolvable includes) for one template.

    Each url tag and each edge carries ``guarded``: whether it sits inside an
    ``{% if %}`` chain that mentions the host. A branch of a host-conditional chain
    is guarded whichever branch it is -- ``{% if manager %}A{% else %}B{% endif %}``
    protects both A and B, because both are host-selected.
    """
    source = _read(name)
    if not source:
        return [], [], []
    stack: list[list[str]] = []  # one entry per open {% if %}, holding its chain
    tags: list[dict] = []
    edges: list[dict] = []
    unresolved: list[str] = []
    for match in _TAGS.finditer(source):
        tag = match.group("tag")
        body = match.group("body") or ""
        if tag == "if":
            stack.append([body])
            continue
        if tag == "elif":
            if stack:
                stack[-1].append(body)
            continue
        if tag == "else":
            if stack:
                stack[-1].append(" else ")
            continue
        if tag == "endif":
            if stack:
                stack.pop()
            continue
        guarded = any(_is_host_guard(" ".join(chain)) for chain in stack)
        line = source.count("\n", 0, match.start()) + 1
        if tag in {"include", "extends"}:
            literal = _STRLIT.match(body)
            if literal is None:
                unresolved.append(f"{name}:{line} {tag} {body.strip()[:60]}")
                continue
            edges.append({"child": literal.group("name"), "guarded": guarded})
            continue
        # tag == "url"
        literal = _STRLIT.match(body)
        if literal is None:
            continue  # {% url some_var %} -- not statically knowable, and rare.
        rest = body[literal.end():].strip()
        if _ASVAR.search(rest):
            continue  # `as var` never raises.
        tags.append({"view_name": literal.group("name"), "line": line, "guarded": guarded})
    return tags, edges, unresolved


def walk(root: str) -> tuple[dict[str, bool], list[str]]:
    """{template: reachable_without_any_host_guard} plus unresolvable includes.

    A template reached ONLY through guarded include sites cannot render on the wrong
    host at all, so its tags are guarded no matter how they are written.
    """
    unguarded: dict[str, bool] = {}
    unresolved: list[str] = []
    seen_any: set[str] = set()
    queue: list[tuple[str, bool]] = [(root, True)]
    while queue:
        name, open_path = queue.pop(0)
        already = unguarded.get(name)
        if name in seen_any and (already or not open_path):
            continue
        seen_any.add(name)
        unguarded[name] = bool(already) or open_path
        _, edges, unres = scan(name)
        unresolved.extend(unres)
        for edge in edges:
            queue.append((edge["child"], open_path and not edge["guarded"]))
    return unguarded, unresolved


def mounted_names(urlconf: str) -> tuple[set[str], set[str]]:
    """(namespace prefixes, fully-qualified names) reversible under this urlconf."""
    from django.urls import get_resolver

    namespaces: set[str] = set()
    names: set[str] = set()

    def descend(node, prefix: str = "") -> None:
        for key in getattr(node, "reverse_dict", {}):
            if isinstance(key, str):
                names.add(prefix + key)
        for ns, (_, sub) in getattr(node, "namespace_dict", {}).items():
            namespaces.add(prefix + ns)
            descend(sub, prefix + ns + ":")

    descend(get_resolver(urlconf))
    return namespaces, names


def _defect(view_name: str, namespaces: set[str], names: set[str]) -> str:
    if ":" not in view_name:
        return "" if view_name in names else "name not reversible"
    chain = view_name.rsplit(":", 1)[0]
    if chain not in namespaces:
        return f"namespace {chain!r} is not mounted"
    if view_name not in names:
        return "namespace mounted but name not reversible"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Shell chrome cross-host {% url %} contract.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--show-guarded", action="store_true")
    parser.add_argument("--shell", default="", help="Check one shell only.")
    args = parser.parse_args()

    import django

    django.setup()

    shells = {args.shell: SHELL_HOSTS[args.shell]} if args.shell else dict(SHELL_HOSTS)
    cache: dict[str, tuple[set[str], set[str]]] = {}
    findings: list[dict] = []
    guarded: list[dict] = []
    unresolved_all: list[str] = []
    summary: list[str] = []

    for shell, urlconfs in shells.items():
        reach, unresolved = walk(shell)
        unresolved_all.extend(unresolved)
        open_count = sum(1 for v in reach.values() if v)
        summary.append(
            f"{shell:<28} closure={len(reach):<4} host-open={open_count:<4} "
            f"hosts={', '.join(urlconfs)}"
        )
        for urlconf in urlconfs:
            if urlconf not in cache:
                cache[urlconf] = mounted_names(urlconf)
            namespaces, names = cache[urlconf]
            for template, open_path in reach.items():
                tags, _, _ = scan(template)
                for tag in tags:
                    reason = _defect(tag["view_name"], namespaces, names)
                    if not reason:
                        continue
                    row = {
                        "shell": shell,
                        "urlconf": urlconf,
                        "template": template,
                        "line": tag["line"],
                        "view_name": tag["view_name"],
                        "reason": reason,
                    }
                    if open_path and not tag["guarded"]:
                        findings.append(row)
                    else:
                        guarded.append(row)

    if args.json:
        print(
            json.dumps(
                {
                    "findings": findings,
                    "guarded": guarded,
                    "unresolved_includes": sorted(set(unresolved_all)),
                },
                indent=2,
            )
        )
        return 1 if findings else 0

    for line in summary:
        print(line)
    print(f"\nguarded (safe, but load-bearing): {len(guarded)}")
    if args.show_guarded:
        for row in guarded:
            print(
                f"   {row['template']}:{row['line']}  {{% url '{row['view_name']}' %}}"
                f"  -- {row['reason']} on {row['urlconf']}"
            )
    if unresolved_all:
        print(f"\nincludes not statically resolvable (not covered): {len(set(unresolved_all))}")
        for item in sorted(set(unresolved_all)):
            print(f"   {item}")
    print(f"\nFINDINGS (unguarded, will 500): {len(findings)}")
    for row in findings:
        print(
            f"   {row['template']}:{row['line']}  {{% url '{row['view_name']}' %}}  "
            f"-- {row['reason']} on {row['urlconf']} (via {row['shell']})"
        )
    if not findings:
        print(
            "   none -- every hard {% url %} reachable in unguarded shell chrome "
            "reverses on every host that shell renders on."
        )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
