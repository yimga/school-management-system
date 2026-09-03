#!/usr/bin/env python
"""An admin registered on a site no urlconf mounts is a page that does not exist.

WHY THIS EXISTS
---------------
RunMyCampus does not serve Django's default ``admin.site``. ``config/manager_urls.py``
mounts ``platform_admin_site`` and ``config/tenant_urls.py`` mounts
``tenant_admin_site``; a repo-wide search finds no ``admin.site.urls`` anywhere. The
house convention is therefore ``@admin.register(Model, site=tenant_admin_site)`` or
``site=platform_admin_site``, and 132 registrations follow it.

Twenty-six do not. They name no site, so they land on the default registry and are
reachable from no URL on any host: FerpaDisclosure, the django-tenants Client/Domain
pair, the webhook subscription/delivery/DomainEvent trio, SchoolContextProfile plus
three bare ``admin.site.register`` calls beside it, six metadata catalogs, five
orchestration surfaces, BlueprintPack, and four social-media models. Every one is a
screen somebody wrote and nobody can open.

A hand grep for ``@admin.register`` finds 23 of them and misses the three bare
``admin.site.register(...)`` calls, which is the argument for a gate over a sweep.

Nothing else can see this. The module imports, the class is valid, ``admin.register``
happily accepts it, and Django's own checks are satisfied -- ``admin.site`` is a real
site, it is simply not routed. ``verify_url_name_integrity`` asks whether a NAME
reverses, and ``admin:`` names do reverse, against the site that is never served.

WHAT IT CHECKS
--------------
Every ``@admin.register(...)`` decorator and every ``<site>.register(...)`` call under
``apps/**/*.py`` (excluding tests and migrations) must target a site this repo actually
mounts. A decorator with no ``site=`` keyword targets the default; so does an explicit
``admin.site.register(...)``.

The mounted-site names are DISCOVERED from ``config/*urls*.py`` rather than hardcoded,
so mounting a third admin site does not silently make this gate wrong.

FLOOR, NOT A BACKLOG. The burndown reached zero on 2026-08-31 and the baseline may
only shrink; a NEW unmounted registration fails the gate. The note this paragraph
used to carry -- that placement was 'not derivable from the settings split' because
four apps were in NEITHER SHARED_APPS nor TENANT_APPS -- was simply wrong. Those
lists hold AppConfig dotted paths (apps.governance.apps.GovernanceConfig), so a
bare-module-name membership test misses apps that are in fact there. Placement is
derivable, and TenantAdminSite.register is fail-closed, so a misclassification
renders an empty screen rather than leaking another tenant's rows.

Stdlib only (ast + pathlib), so it runs in the deps-free boundary job.
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "var" / "security-audit-baseline-admin-unmounted-site.json"

_ALLOW_RE = re.compile(r"admin-site-allow:\s*(\S.*)")


def mounted_site_names(config_dir: pathlib.Path) -> set[str]:
    """Admin-site objects some urlconf actually routes.

    Reads ``path(..., <name>.urls)`` out of every ``config/*urls*.py``. Discovered
    rather than hardcoded so a third mounted site does not make this gate lie.
    """
    names: set[str] = set()
    for path in sorted(config_dir.glob("*urls*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "urls"
                and isinstance(node.value, ast.Name)
            ):
                names.add(node.value.id)
    return names


def _allow_reason(lines: list[str], lineno: int) -> str | None:
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(lines):
            match = _ALLOW_RE.search(lines[idx])
            if match:
                return match.group(1).strip()
    return None


def _target_site(node: ast.AST) -> str | None:
    """The site a registration targets, or None when it takes the default."""
    if isinstance(node, ast.Call):
        for kw in node.keywords:
            if kw.arg == "site":
                if isinstance(kw.value, ast.Name):
                    return kw.value.id
                if isinstance(kw.value, ast.Attribute):
                    return kw.value.attr
                return "<dynamic>"
    return None


def _display(path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        # A temp tree under test is not below the repo root; report it as-is
        # rather than crashing the scan.
        return str(path).replace("\\", "/")


def scan_file(path: pathlib.Path, mounted: set[str], root: pathlib.Path = REPO_ROOT) -> list[dict]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        # verify_python_files_parse owns unparseable files; saying it twice buries
        # the report that explains the fix.
        return []
    lines = source.splitlines()
    findings: list[dict] = []

    for node in ast.walk(tree):
        # @admin.register(Model)  /  @admin.register(Model, site=...)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                func = dec.func
                if not (isinstance(func, ast.Attribute) and func.attr == "register"):
                    continue
                site = _target_site(dec)
                if site is None or (site not in mounted and site != "<dynamic>"):
                    if _allow_reason(lines, dec.lineno):
                        continue
                    findings.append({
                        "path": _display(path, root),
                        "line": dec.lineno,
                        "symbol": node.name,
                        "site": site or "admin.site (default)",
                    })
        # admin.site.register(Model, ...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr != "register":
                continue
            owner = node.func.value
            if not (isinstance(owner, ast.Attribute) and owner.attr == "site"):
                continue
            if _allow_reason(lines, node.lineno):
                continue
            findings.append({
                "path": _display(path, root),
                "line": node.lineno,
                "symbol": "admin.site.register",
                "site": "admin.site (default)",
            })
    return findings


def collect(apps_dir: pathlib.Path, mounted: set[str], root: pathlib.Path | None = None) -> list[dict]:
    out: list[dict] = []
    # EVERY module under apps/, not just admin.py and admin/*.py. Those two globs
    # were the whole blind spot: apps/finance/payment_admin.py carried five bare
    # registrations and apps/portal/admin_kb.py another eight, and this scanner
    # reported a clean zero the entire time because it never opened either file.
    # A registration is a registration wherever it is written.
    for path in sorted(apps_dir.rglob("*.py")):
        rel = path.as_posix()
        if "/migrations/" in rel or "/tests/" in rel:
            continue
        if "register" not in path.read_text(encoding="utf-8", errors="ignore"):
            continue  # cheap pre-filter; nothing here can register a model
        out.append(path)
    root = root if root is not None else apps_dir.parent
    findings: list[dict] = []
    for path in out:
        findings.extend(scan_file(path, mounted, root))
    return findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true", help="fail only on NEW findings")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    mounted = mounted_site_names(REPO_ROOT / "config")
    findings = collect(REPO_ROOT / "apps", mounted)

    if args.json:
        print(json.dumps({"mounted_sites": sorted(mounted), "findings": findings}, indent=2))
    else:
        print(f"mounted admin sites: {', '.join(sorted(mounted)) or '(none found)'}")
        for f in findings:
            print(f"  {f['path']}:{f['line']}  {f['symbol']} -> {f['site']}")
        print(f"admin-unmounted-site: {len(findings)} registration(s) on an unmounted site.")

    if not args.compare:
        return 1 if findings else 0

    try:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8")).get("finding_count", 0)
    except (OSError, ValueError):
        baseline = 0
    if len(findings) > baseline:
        print(
            f"FAIL: {len(findings)} unmounted admin registrations, baseline {baseline}. "
            "A new one is a page nobody can open -- pass site=tenant_admin_site or "
            "site=platform_admin_site, or mark it `# admin-site-allow: <reason>`.",
            file=sys.stderr,
        )
        return 1
    if len(findings) < baseline:
        print(f"OK: down to {len(findings)} from a baseline of {baseline}. Update the baseline.")
    else:
        print(f"OK: no new unmounted admin registrations (count={len(findings)}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
