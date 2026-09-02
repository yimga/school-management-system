#!/usr/bin/env python
"""A test that names a production urlconf must speak to a host that gets it.

``ROOT_URLCONF`` does not decide which urlconf serves a request on this deployment.
``apps.schools.middleware.UrlConfSwitcherMiddleware`` reassigns ``request.urlconf``
from the ``Host`` header on every request, so this shape --

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    class Something(TestCase):
        def test_x(self):
            self.client.get("/finance/reports/")     # no host

-- is served by ``config.urls``, the DEVELOPER urlconf, which no production host is
ever given. Measured, not assumed (``apps/schools/tests/test_host_routing_contract_2026_09_02.py``
pins it): under that exact decorator, a request with the default ``testserver`` host
resolves on ``config.urls`` with ``request.school`` set to ``None``.

**Why it is worse than a no-op.** The developer urlconf is a SUPERSET of every host's
routes. So the test does not fail -- it passes, against a URL surface no tenant is
served, with no school bound. A route deleted from ``config.tenant_urls`` keeps such a
test green while every real tenant 404s. The decorator additionally reads, to any
future reviewer, as proof the test IS on the tenant surface.

The fix is a host, not a setting: ``apps/test_utils/tenant_hosts.py`` supplies
``TenantHostTestCase`` (client pre-bound to a real tenant host, with a fail-closed
probe in ``setUp``), ``tenant_client(host)``, and ``assert_resolved_urlconf(response,
expected)`` for tests that want to prove which surface answered.

**Scoped to the decorated class or method, never the file.** The first cut of this
gate matched ``ROOT_URLCONF`` and client requests anywhere in the same module and
reported ``apps/schools/tests/test_signup_slug_suggest.py``, where the override sits
on a ``reverse()``-only method and the requests belong to a different class -- a
correct file the gate called wrong. Scope resolution is what makes the finding count
mean something.

Deliberately narrow, so a finding is always real:

* Only a ``ROOT_URLCONF`` assigned one of the HOST-SPLIT urlconfs counts. A test
  pointing ``ROOT_URLCONF`` at a fixture urlconf of its own is doing something else.
* Only a scope that ISSUES CLIENT REQUESTS counts. ``reverse("x", urlconf=...)`` and
  ``get_resolver("config.tenant_urls")`` never touch middleware, so they honour the
  urlconf they are handed and are correct as written -- 33 files in this repo do
  exactly that, and flagging them is how a gate gets switched off.
* A scope that sets a host ANYWHERE inside it -- ``HTTP_HOST``, ``SERVER_NAME``, one
  of the ``apps.test_utils`` login helpers, or the tenant-host base class -- is
  credited without checking that it does so on every call. A decorated METHOD is also
  credited by its enclosing class, since the client is usually built in ``setUp``.
  False-negative biased on purpose: this gate catches the shape that CANNOT be right,
  not per-request host discipline.

Zero-tolerance, and no baseline JSON: there is nothing to ratchet, because a request
aimed at a urlconf it will not reach is never intentional. A reviewed exception is
declared in the file, where the reviewer is, with
``# test-host-fidelity-allow: <reason>``.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (REPO_ROOT / "apps",)

#: The urlconfs the middleware selects by host. ``config.urls`` is deliberately absent:
#: it is the developer surface, so pointing ROOT_URLCONF at it claims nothing.
HOST_URLCONFS = frozenset(
    {
        "config.tenant_urls",
        "config.manager_urls",
        "config.public_urls",
        "config.api_urls",
        "config.docs_urls",
    }
)

ALLOW_MARKER = "test-host-fidelity-allow:"

#: Names that mean "a host is being supplied here". Matched as identifiers, keywords
#: or attributes anywhere inside the scope under test.
HOST_EVIDENCE_NAMES = frozenset(
    {
        "HTTP_HOST",
        "SERVER_NAME",
        "login_manager_client",
        "login_tenant_client",
        "login_tenant_admin_client",
        "login_manager_control_plane",
        "tenant_client",
        "public_client",
        "manager_client",
        "tenant_host",
        "TenantHostTestCase",
        "TenantHostTransactionTestCase",
    }
)

#: Django test-client methods that build a real request and therefore run middleware.
CLIENT_REQUEST_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "trace", "generic"}
)


def _module_dict_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = dict(ROOT_URLCONF=...)`` / ``{...}`` settings bundles.

    Tests routinely hoist the settings into a constant and splat it
    (``@override_settings(**_TENANT_SETTINGS)``), so the literal is nowhere near the
    decorator that applies it.
    """
    found: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        urlconf = _root_urlconf_from_settings_source(node.value)
        if not urlconf:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                found[target.id] = urlconf
    return found


def _root_urlconf_from_settings_source(node: ast.expr) -> str | None:
    """Read a host ROOT_URLCONF out of a ``dict(...)`` call or a ``{...}`` literal."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
        for keyword in node.keywords:
            if keyword.arg == "ROOT_URLCONF" and isinstance(keyword.value, ast.Constant):
                value = keyword.value.value
                if isinstance(value, str) and value in HOST_URLCONFS:
                    return value
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant)
                and key.value == "ROOT_URLCONF"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and value.value in HOST_URLCONFS
            ):
                return value.value
    return None


def _declared_urlconf(node: ast.AST, constants: dict[str, str]) -> str | None:
    """The host urlconf a decorator (or ``with`` block) on ``node`` claims, if any."""
    decorators = list(getattr(node, "decorator_list", []))
    if isinstance(node, ast.With):
        decorators = [item.context_expr for item in node.items]

    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        # ``self.settings(...)`` is SimpleTestCase's own wrapper around
        # override_settings and is the idiom eight of these requests used, so
        # omitting it made the gate blind to a whole file. Any callable is accepted
        # as long as it carries a ROOT_URLCONF naming a host urlconf -- that kwarg
        # is what makes the claim, whatever the helper is called.
        if name not in {"override_settings", "modify_settings", "settings"}:
            continue
        for keyword in decorator.keywords:
            # override_settings(ROOT_URLCONF="config.tenant_urls")
            if keyword.arg == "ROOT_URLCONF" and isinstance(keyword.value, ast.Constant):
                value = keyword.value.value
                if isinstance(value, str) and value in HOST_URLCONFS:
                    return value
            # override_settings(**_TENANT_SETTINGS)
            if keyword.arg is None:
                if isinstance(keyword.value, ast.Name):
                    resolved = constants.get(keyword.value.id)
                    if resolved:
                        return resolved
                inline = _root_urlconf_from_settings_source(keyword.value)
                if inline:
                    return inline
    return None


def _client_request_lines(scope: ast.AST) -> list[int]:
    """Lines inside ``scope`` where a test client issues a real request."""
    lines: list[int] = []
    for node in ast.walk(scope):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in CLIENT_REQUEST_METHODS:
            continue
        # The receiver must look like a client: `client`, `self.client`, `c.client`...
        receiver = func.value
        receiver_name = (
            receiver.attr
            if isinstance(receiver, ast.Attribute)
            else getattr(receiver, "id", "")
        )
        if "client" in receiver_name.lower():
            lines.append(node.lineno)
    return sorted(lines)


def _has_host_evidence(scope: ast.AST) -> bool:
    for node in ast.walk(scope):
        if isinstance(node, ast.Name) and node.id in HOST_EVIDENCE_NAMES:
            return True
        if isinstance(node, ast.Attribute) and node.attr in HOST_EVIDENCE_NAMES:
            return True
        if isinstance(node, ast.keyword) and node.arg in HOST_EVIDENCE_NAMES:
            return True
    return False


def _class_bases(node: ast.AST) -> set[str]:
    if not isinstance(node, ast.ClassDef):
        return set()
    names = set()
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def scan_file(path: Path) -> list[dict]:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if ALLOW_MARKER in source:
        return []

    # A parse failure is NOT reported here; verify_python_files_parse owns that, and
    # saying it twice buries the report that explains how to fix it.
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    constants = _module_dict_constants(tree)
    rel = path.relative_to(REPO_ROOT).as_posix()
    findings: list[dict] = []

    # Walk classes and functions, carrying the nearest enclosing class so a decorated
    # METHOD can be credited by a host set in its class's setUp.
    def visit(node: ast.AST, enclosing_class: ast.ClassDef | None) -> None:
        for child in ast.iter_child_nodes(node):
            is_scope = isinstance(
                child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.With)
            )
            if is_scope:
                urlconf = _declared_urlconf(child, constants)
                if urlconf:
                    request_lines = _client_request_lines(child)
                    if request_lines:
                        credited = (
                            _has_host_evidence(child)
                            or bool(_class_bases(child) & HOST_EVIDENCE_NAMES)
                            or (
                                enclosing_class is not None
                                and (
                                    _has_host_evidence(enclosing_class)
                                    or bool(
                                        _class_bases(enclosing_class) & HOST_EVIDENCE_NAMES
                                    )
                                )
                            )
                        )
                        if not credited:
                            findings.append(
                                {
                                    "file": rel,
                                    "line": request_lines[0],
                                    "scope": getattr(child, "name", "with-block"),
                                    "declared_urlconf": urlconf,
                                    "request_count": len(request_lines),
                                    "reason": (
                                        "declares a host urlconf and issues client "
                                        "requests, but never sets a Host header -- these "
                                        "requests are served by config.urls, the "
                                        "developer urlconf, with no school bound"
                                    ),
                                }
                            )
                        # Whether credited or not, the scope is decided. Nested scopes
                        # inherit the same override, so re-reporting them would count
                        # one mistake many times.
                        continue
            visit(child, child if isinstance(child, ast.ClassDef) else enclosing_class)

    visit(tree, None)
    findings.sort(key=lambda f: (f["file"], f["line"]))
    return findings


def _iter_test_files():
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("test*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--compare",
        action="store_true",
        help=(
            "Accepted for symmetry with the ratcheted scanners. This gate is "
            "zero-tolerance and has no baseline, so it behaves identically either way."
        ),
    )
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args(argv)

    findings: list[dict] = []
    scanned = 0
    for path in _iter_test_files():
        scanned += 1
        findings.extend(scan_file(path))

    if args.json:
        import json

        print(json.dumps({"finding_count": len(findings), "findings": findings}, indent=2))
        return 1 if findings else 0

    if findings:
        print(
            f"[scan-test-host-fidelity] {len(findings)} scope(s) aim at a production "
            f"urlconf they never reach:",
            file=sys.stderr,
        )
        for f in findings:
            print(
                f"  {f['file']}:{f['line']}  {f['scope']} declares "
                f"{f['declared_urlconf']}; {f['request_count']} client request(s), "
                f"no Host header",
                file=sys.stderr,
            )
        print(
            "\n  These requests are served by config.urls (the DEVELOPER urlconf), which\n"
            "  mounts a superset of every production route -- so they pass while proving\n"
            "  nothing about the surface they name, and request.school is None.\n"
            "  Fix: use apps.test_utils.tenant_hosts (TenantHostTestCase / tenant_client)\n"
            "  and assert with assert_resolved_urlconf(response, expected).\n"
            f"  Reviewed exception: # {ALLOW_MARKER} <reason>",
            file=sys.stderr,
        )
        return 1

    print(
        f"[scan-test-host-fidelity] {scanned} test files scanned, 0 findings.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
