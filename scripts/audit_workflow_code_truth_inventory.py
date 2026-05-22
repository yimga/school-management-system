#!/usr/bin/env python3
"""Platform-wide workflow code-truth inventory (Phase 0).

Walks every Django URL configuration in this repo (the 6 root URLconfs under
config/ plus every apps/*/*urls*.py) and produces a single inventory artifact
describing what physically exists per app + per surface (operator / tenant /
public / api / docs / shared).

The output is intentionally read-only: it records what the filesystem says,
not what should exist. Classification of workflows by audience, primary
action, and click count is Phase 1 and lives in a separate artifact.

Outputs:
  docs/generated/platform_workflow_code_truth_inventory.json
  docs/generated/platform_workflow_code_truth_inventory.md

Run:
  python scripts/audit_workflow_code_truth_inventory.py
"""

from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
APPS_DIR = ROOT / "apps"
CONFIG_DIR = ROOT / "config"
TEMPLATES_DIR = ROOT / "templates"
DOCS_GENERATED = ROOT / "docs" / "generated"

OUT_JSON = DOCS_GENERATED / "platform_workflow_code_truth_inventory.json"
OUT_MD = DOCS_GENERATED / "platform_workflow_code_truth_inventory.md"

ROOT_URLCONFS = {
    "operator": CONFIG_DIR / "manager_urls.py",
    "tenant": CONFIG_DIR / "tenant_urls.py",
    "public": CONFIG_DIR / "public_urls.py",
    "api": CONFIG_DIR / "api_urls.py",
    "docs": CONFIG_DIR / "docs_urls.py",
    "default": CONFIG_DIR / "urls.py",
}

# Surfaces whose presence in an app's reachable-set classifies the app's audience.
PRIMARY_SURFACES = ("operator", "tenant", "public", "api", "docs", "default")


@dataclass
class RouteEntry:
    pattern: str
    name: str | None
    view_ref: str | None  # textual unparse of the view expression
    line: int
    urlconf: str  # repo-relative path of the urls.py file that declares it


@dataclass
class IncludeEntry:
    prefix: str
    target: str  # the include() argument as unparsed text
    namespace: str | None
    line: int
    urlconf: str


@dataclass
class AppRollup:
    app: str
    path: str
    urls_files: list[str] = field(default_factory=list)
    route_count: int = 0
    include_count: int = 0
    named_routes: int = 0
    unnamed_routes: int = 0
    views_modules: list[str] = field(default_factory=list)
    forms_modules: list[str] = field(default_factory=list)
    services_modules: list[str] = field(default_factory=list)
    models_files: list[str] = field(default_factory=list)
    template_dirs: list[str] = field(default_factory=list)
    test_files: int = 0
    readme_or_docs: list[str] = field(default_factory=list)
    surfaces: list[str] = field(default_factory=list)  # operator/tenant/public/api/docs/default
    reachable_from: list[str] = field(default_factory=list)  # which root URLconfs include this app
    has_apicenter_import: bool = False  # AI-Center / ai_helpers reference
    has_feedback_import: bool = False  # feedback app reference
    has_help_template: bool = False  # templates/<app>/help/* or *_help.html
    likely_workflow_pages: list[str] = field(default_factory=list)  # template files that look like a user workflow


def _safe_unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "<unparse-failed>"


def _walk_path_call(call: ast.Call, urlconf_rel: str) -> RouteEntry | IncludeEntry | None:
    func = call.func
    fname = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
    if fname not in {"path", "re_path"}:
        return None
    if not call.args:
        return None

    # First arg: route pattern (string literal expected, but tolerate non-literals)
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        pattern = first.value
    else:
        pattern = _safe_unparse(first)

    # Second arg: view callable OR include(...) call
    if len(call.args) >= 2:
        second = call.args[1]
        if isinstance(second, ast.Call):
            inner_func = second.func
            inner_name = (
                inner_func.attr if isinstance(inner_func, ast.Attribute)
                else (inner_func.id if isinstance(inner_func, ast.Name) else "")
            )
            if inner_name == "include":
                target = _safe_unparse(second.args[0]) if second.args else "<no-arg>"
                namespace = None
                for kw in second.keywords:
                    if kw.arg == "namespace" and isinstance(kw.value, ast.Constant):
                        namespace = kw.value.value
                return IncludeEntry(
                    prefix=pattern,
                    target=target,
                    namespace=namespace,
                    line=call.lineno,
                    urlconf=urlconf_rel,
                )
        view_ref = _safe_unparse(second)
    else:
        view_ref = None

    # name= kwarg
    route_name: str | None = None
    for kw in call.keywords:
        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
            route_name = kw.value.value
            break

    return RouteEntry(
        pattern=pattern,
        name=route_name,
        view_ref=view_ref,
        line=call.lineno,
        urlconf=urlconf_rel,
    )


def parse_urlconf(path: Path) -> tuple[list[RouteEntry], list[IncludeEntry]]:
    routes: list[RouteEntry] = []
    includes: list[IncludeEntry] = []
    if not path.exists():
        return routes, includes
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return routes, includes
    urlconf_rel = str(path.relative_to(ROOT)).replace("\\", "/")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            entry = _walk_path_call(node, urlconf_rel)
            if isinstance(entry, RouteEntry):
                routes.append(entry)
            elif isinstance(entry, IncludeEntry):
                includes.append(entry)
    return routes, includes


# ---- Include target -> app inference ---------------------------------------

INCLUDE_APP_RE = re.compile(r"apps\.(?P<app>[a-zA-Z_][a-zA-Z0-9_]*)")


def includes_to_app(include_target: str) -> str | None:
    """Best-effort: extract the app name from an include() target string."""
    m = INCLUDE_APP_RE.search(include_target)
    return m.group("app") if m else None


# ---- Per-app filesystem scan -----------------------------------------------

def _list_module_files(app_dir: Path, prefix: str) -> list[str]:
    out = []
    for p in app_dir.iterdir():
        if p.is_file() and p.suffix == ".py" and (p.name == f"{prefix}.py" or p.name.startswith(f"{prefix}_") or p.name.startswith(f"{prefix}s_")):
            out.append(p.name)
    # also look at common module dirs like views/, forms/, services/, models/
    sub = app_dir / prefix
    if sub.is_dir():
        for p in sub.rglob("*.py"):
            if p.name != "__init__.py":
                out.append(str(p.relative_to(app_dir)).replace("\\", "/"))
    pluraldir = app_dir / f"{prefix}s"
    if pluraldir.is_dir():
        for p in pluraldir.rglob("*.py"):
            if p.name != "__init__.py":
                out.append(str(p.relative_to(app_dir)).replace("\\", "/"))
    return sorted(set(out))


def _count_test_files(app_dir: Path) -> int:
    count = 0
    for p in app_dir.rglob("test_*.py"):
        if "__pycache__" in p.parts:
            continue
        count += 1
    tests_dir = app_dir / "tests"
    if tests_dir.is_dir():
        for p in tests_dir.rglob("*.py"):
            if p.name != "__init__.py" and "__pycache__" not in p.parts:
                count += 1
    return count


def _list_template_dirs(app_name: str) -> list[str]:
    out = []
    if not TEMPLATES_DIR.is_dir():
        return out
    candidate = TEMPLATES_DIR / app_name
    if candidate.is_dir():
        out.append(str(candidate.relative_to(ROOT)).replace("\\", "/"))
    # also pick up any top-level templates/*.html that obviously belong (rare)
    return out


def _likely_workflow_templates(app_name: str) -> list[str]:
    """Heuristic: page templates whose filename suggests a user workflow.

    Workflow signals: 'wizard', 'setup', 'onboarding', 'review', 'approval',
    'install', 'configure', 'import', 'export', 'launch', 'create', 'new_',
    'edit_', 'form', 'request', 'submit'.
    """
    out: list[str] = []
    workflow_words = (
        "wizard", "setup", "onboarding", "review", "approval", "approve",
        "install", "configure", "import", "export", "launch", "create",
        "new_", "edit_", "form", "request", "submit", "checkout",
        "publish", "rollback", "migrate", "guided", "step_",
    )
    candidate = TEMPLATES_DIR / app_name
    if not candidate.is_dir():
        return out
    for p in candidate.rglob("*.html"):
        rel = str(p.relative_to(TEMPLATES_DIR)).replace("\\", "/").lower()
        if any(w in rel for w in workflow_words):
            out.append(rel)
    return sorted(out)[:20]  # cap to keep JSON tractable; full list lives on disk


def _has_help_template(app_name: str) -> bool:
    candidate = TEMPLATES_DIR / app_name
    if not candidate.is_dir():
        return False
    for p in candidate.rglob("*.html"):
        rel = p.name.lower()
        if "help" in rel or "how_to" in rel or "howto" in rel or "faq" in rel:
            return True
    return False


def _grep_imports(app_dir: Path, needle: str) -> bool:
    """Cheap grep — true if any .py file in the app imports the needle."""
    for p in app_dir.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if needle in txt:
            return True
    return False


def build_app_rollup(app_name: str, app_dir: Path) -> AppRollup:
    roll = AppRollup(app=app_name, path=str(app_dir.relative_to(ROOT)).replace("\\", "/"))
    for f in sorted(app_dir.iterdir()):
        if f.is_file() and "urls" in f.name and f.suffix == ".py":
            roll.urls_files.append(f.name)
    roll.views_modules = _list_module_files(app_dir, "view")
    # second pass for view-prefixed files
    roll.views_modules += [n for n in _list_module_files(app_dir, "views") if n not in roll.views_modules]
    roll.views_modules = sorted(set(roll.views_modules))
    roll.forms_modules = sorted(set(
        _list_module_files(app_dir, "form")
        + _list_module_files(app_dir, "forms")
    ))
    roll.services_modules = sorted(set(
        _list_module_files(app_dir, "service")
        + _list_module_files(app_dir, "services")
    ))
    roll.models_files = sorted(set(
        _list_module_files(app_dir, "model")
        + _list_module_files(app_dir, "models")
    ))
    roll.template_dirs = _list_template_dirs(app_name)
    roll.test_files = _count_test_files(app_dir)

    # readme/howto markdown
    for name in ("README.md", "HOWTO.md", "WORKFLOW.md", "USAGE.md"):
        if (app_dir / name).exists():
            roll.readme_or_docs.append(name)

    roll.likely_workflow_pages = _likely_workflow_templates(app_name)
    roll.has_help_template = _has_help_template(app_name)

    # AI / feedback / KB cross-refs (cheap grep)
    roll.has_apicenter_import = _grep_imports(app_dir, "services.ai_helpers") or _grep_imports(app_dir, "apicenter")
    roll.has_feedback_import = _grep_imports(app_dir, "apps.feedback") or _grep_imports(app_dir, "from apps.feedback")
    return roll


# ---- Surface reachability --------------------------------------------------

def reachable_apps_from(urlconf: Path) -> dict[str, list[str]]:
    """Walk includes transitively from a root urlconf, return {app: [include_chain]}."""
    routes, includes = parse_urlconf(urlconf)
    visited: dict[str, list[str]] = {}
    queue: list[tuple[str, list[str]]] = []
    for inc in includes:
        app = includes_to_app(inc.target)
        if app:
            queue.append((app, [f"{urlconf.name}:{inc.prefix}"]))
    # transitive: walk each app's *urls*.py for nested includes
    while queue:
        app, chain = queue.pop()
        if app in visited:
            continue
        visited[app] = chain
        app_dir = APPS_DIR / app
        if not app_dir.is_dir():
            continue
        for urls_file in app_dir.glob("*urls*.py"):
            _, sub_includes = parse_urlconf(urls_file)
            for sub in sub_includes:
                sub_app = includes_to_app(sub.target)
                if sub_app and sub_app not in visited:
                    queue.append((sub_app, chain + [f"{app}/{urls_file.name}:{sub.prefix}"]))
    return visited


# ---- Main ------------------------------------------------------------------

def main() -> int:
    DOCS_GENERATED.mkdir(parents=True, exist_ok=True)

    # 1. Discover all URL configs
    all_urlconfs: dict[str, Path] = dict(ROOT_URLCONFS)
    for app_urls in sorted(APPS_DIR.glob("*/*urls*.py")):
        rel = str(app_urls.relative_to(ROOT)).replace("\\", "/")
        all_urlconfs[rel] = app_urls

    # 2. Parse every URL config
    all_routes: list[RouteEntry] = []
    all_includes: list[IncludeEntry] = []
    per_urlconf_counts: dict[str, dict[str, int]] = {}
    for label, p in all_urlconfs.items():
        r, i = parse_urlconf(p)
        all_routes.extend(r)
        all_includes.extend(i)
        per_urlconf_counts[label] = {
            "exists": int(p.exists()),
            "routes": len(r),
            "includes": len(i),
            "named_routes": sum(1 for x in r if x.name),
        }

    # 3. Surface reachability: which apps are reachable from each root URLconf
    surface_to_apps: dict[str, dict[str, list[str]]] = {}
    for surface, urlconf_path in ROOT_URLCONFS.items():
        surface_to_apps[surface] = reachable_apps_from(urlconf_path)

    # 4. Per-app rollup
    app_dirs = sorted(p for p in APPS_DIR.iterdir() if p.is_dir() and not p.name.startswith("__") and p.name != "test_utils")
    app_rollups: list[AppRollup] = []
    for app_dir in app_dirs:
        roll = build_app_rollup(app_dir.name, app_dir)
        # tag surfaces
        for surface, app_chain in surface_to_apps.items():
            if app_dir.name in app_chain:
                roll.surfaces.append(surface)
                roll.reachable_from.append(app_chain[app_dir.name][0])
        # count this app's own routes
        own_routes = [
            r for r in all_routes
            if r.urlconf.startswith(f"apps/{app_dir.name}/")
        ]
        own_includes = [
            i for i in all_includes
            if i.urlconf.startswith(f"apps/{app_dir.name}/")
        ]
        roll.route_count = len(own_routes)
        roll.include_count = len(own_includes)
        roll.named_routes = sum(1 for r in own_routes if r.name)
        roll.unnamed_routes = roll.route_count - roll.named_routes
        app_rollups.append(roll)

    # 5. Cross-reference: existing inventory artifacts
    related_inventories: list[dict[str, Any]] = []
    if DOCS_GENERATED.is_dir():
        for p in sorted(DOCS_GENERATED.glob("*.json")):
            n = p.name.lower()
            if any(k in n for k in ("workflow", "inventory", "route", "studio_os_code_truth", "platform_pulse", "shell_surface")):
                related_inventories.append({
                    "path": str(p.relative_to(ROOT)).replace("\\", "/"),
                    "size_bytes": p.stat().st_size,
                })

    # 6. Honest-gaps signals (sample, not exhaustive — exhaustive classification is Phase 1).
    # Important framing: an app with zero routes and zero urls.py is NOT a defect — many
    # apps in this repo are model-only / service-only (billing, schoolops, observability,
    # tenancy, locale, registries, packages, etc.) and surface through other apps' views.
    gaps: dict[str, list[str]] = defaultdict(list)
    for roll in app_rollups:
        if roll.route_count > 0 and roll.test_files == 0:
            gaps["routes_without_tests"].append(roll.app)
        if roll.template_dirs and roll.test_files == 0:
            gaps["templates_without_tests"].append(roll.app)
        if roll.route_count == 0 and not roll.urls_files and roll.views_modules:
            gaps["views_present_but_no_urls_file_check_inclusion"].append(roll.app)
        if roll.route_count > 0 and not roll.has_help_template and not roll.has_apicenter_import:
            gaps["routes_without_help_or_ai_signal"].append(roll.app)
        if roll.likely_workflow_pages and not roll.has_help_template:
            gaps["workflow_templates_without_help"].append(roll.app)
        if roll.likely_workflow_pages and not roll.has_feedback_import:
            gaps["workflow_templates_without_feedback_hook"].append(roll.app)
        # Only flag as orphan if app has its own urls.py / routes but none of them are
        # reachable from any of the 6 root URLconfs. Apps with no routes at all are
        # service/model layers, not orphans.
        if (roll.route_count > 0 or roll.urls_files) and not roll.surfaces:
            gaps["app_has_routes_but_no_root_urlconf_inclusion"].append(roll.app)
    # Surface (informational, not a gap) which apps are service-only by design.
    service_only_apps = sorted(
        roll.app for roll in app_rollups
        if roll.route_count == 0 and not roll.urls_files
    )

    # 7. Surface-level totals
    surface_totals: dict[str, dict[str, int]] = {}
    for surface in PRIMARY_SURFACES:
        routes_on_surface = [r for r in all_routes if r.urlconf == str(ROOT_URLCONFS[surface].relative_to(ROOT)).replace("\\", "/")]
        surface_totals[surface] = {
            "root_urlconf": str(ROOT_URLCONFS[surface].relative_to(ROOT)).replace("\\", "/"),
            "root_routes": len(routes_on_surface),
            "reachable_apps": len(surface_to_apps[surface]),
        }

    # 8. Assemble final JSON
    out = {
        "doc": "platform_workflow_code_truth_inventory",
        "phase": 0,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": (
            "Code-truth inventory of every Django URL configuration in this repo "
            "(6 root URLconfs + every apps/*/*urls*.py) and the per-app rollup "
            "of views, forms, services, models, templates, tests, README/howto, "
            "and AI/feedback/help cross-references. Read-only filesystem walk; "
            "no Django startup. Phase 1 (classification by audience / primary action "
            "/ click count) builds on this artifact, not on it."
        ),
        "source": "scripts/audit_workflow_code_truth_inventory.py",
        "summary": {
            "urlconfs_scanned": len(all_urlconfs),
            "root_urlconfs": list(ROOT_URLCONFS.keys()),
            "per_app_urlconf_files": sum(
                1 for k in all_urlconfs if k.startswith("apps/")
            ),
            "total_routes": len(all_routes),
            "total_includes": len(all_includes),
            "total_named_routes": sum(1 for r in all_routes if r.name),
            "total_unnamed_routes": sum(1 for r in all_routes if not r.name),
            "apps_scanned": len(app_rollups),
            "apps_with_routes": sum(1 for r in app_rollups if r.route_count > 0),
            "apps_with_tests": sum(1 for r in app_rollups if r.test_files > 0),
            "apps_with_templates": sum(1 for r in app_rollups if r.template_dirs),
            "apps_with_help_template": sum(1 for r in app_rollups if r.has_help_template),
            "apps_with_ai_helpers_or_apicenter_import": sum(1 for r in app_rollups if r.has_apicenter_import),
            "apps_with_feedback_import": sum(1 for r in app_rollups if r.has_feedback_import),
            "operator_reachable_apps": len(surface_to_apps["operator"]),
            "tenant_reachable_apps": len(surface_to_apps["tenant"]),
            "public_reachable_apps": len(surface_to_apps["public"]),
            "api_reachable_apps": len(surface_to_apps["api"]),
            "docs_reachable_apps": len(surface_to_apps["docs"]),
        },
        "surface_totals": surface_totals,
        "per_urlconf_counts": per_urlconf_counts,
        "apps": [asdict(r) for r in app_rollups],
        "gaps": dict(gaps),
        "service_only_apps": service_only_apps,
        "related_inventories": related_inventories,
        "phase_0_deferred": [
            "Workflow classification by audience (operator / tenant admin / teacher / parent / student / support / partner) — Phase 1",
            "Primary-action / next-best-action / blocker identification per workflow — Phase 1",
            "Current vs ideal step count per workflow — Phase 1",
            "How-to coverage gap classification (strong / usable / fragmented / broken / missing) — Phase 1",
            "Contextual information tag coverage audit — Phase 3",
            "AI workflow assistant coverage audit — Phase 8",
        ],
        "verdict": "PHASE_0_INVENTORY_READY",
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, sort_keys=False), encoding="utf-8")

    # 9. Markdown render
    md: list[str] = []
    md.append(f"# Platform Workflow Code-Truth Inventory (Phase 0)\n")
    md.append(f"_Generated {out['generated_at']} by `{out['source']}`._\n")
    md.append(f"\n{out['scope']}\n\n")

    md.append("## Summary\n\n")
    s = out["summary"]
    md.append(f"- URL configs scanned: **{s['urlconfs_scanned']}** ({s['per_app_urlconf_files']} per-app + {len(ROOT_URLCONFS)} root)\n")
    md.append(f"- Total `path(...)`/`re_path(...)` route declarations: **{s['total_routes']}** ({s['total_named_routes']} named, {s['total_unnamed_routes']} unnamed)\n")
    md.append(f"- Total `include(...)` chains: **{s['total_includes']}**\n")
    md.append(f"- Apps scanned: **{s['apps_scanned']}**\n")
    md.append(f"- Apps with routes: **{s['apps_with_routes']}** | with tests: **{s['apps_with_tests']}** | with templates: **{s['apps_with_templates']}**\n")
    md.append(f"- Apps with help template: **{s['apps_with_help_template']}** | with AI hook: **{s['apps_with_ai_helpers_or_apicenter_import']}** | with feedback import: **{s['apps_with_feedback_import']}**\n")
    md.append(f"- Apps reachable from operator (manager_urls): **{s['operator_reachable_apps']}**\n")
    md.append(f"- Apps reachable from tenant (tenant_urls): **{s['tenant_reachable_apps']}**\n")
    md.append(f"- Apps reachable from public (public_urls): **{s['public_reachable_apps']}**\n")
    md.append(f"- Apps reachable from api (api_urls): **{s['api_reachable_apps']}**\n")
    md.append(f"- Apps reachable from docs (docs_urls): **{s['docs_reachable_apps']}**\n")

    md.append("\n## Surface totals (root URLconfs)\n\n")
    md.append("| Surface | Root URLconf | Direct routes | Reachable apps |\n")
    md.append("|---|---|---:|---:|\n")
    for surface, info in surface_totals.items():
        md.append(f"| {surface} | `{info['root_urlconf']}` | {info['root_routes']} | {info['reachable_apps']} |\n")

    md.append("\n## Per-app rollup\n\n")
    md.append("| App | Routes | Tests | Surfaces | Help? | AI? | FB? | Tmpl dirs | Workflow tmpls |\n")
    md.append("|---|---:|---:|---|:-:|:-:|:-:|---:|---:|\n")
    for roll in sorted(app_rollups, key=lambda r: (-r.route_count, r.app)):
        surfaces_str = ",".join(roll.surfaces) if roll.surfaces else "—"
        help_flag = "✓" if roll.has_help_template else " "
        ai_flag = "✓" if roll.has_apicenter_import else " "
        fb_flag = "✓" if roll.has_feedback_import else " "
        md.append(
            f"| `{roll.app}` | {roll.route_count} | {roll.test_files} | {surfaces_str} | {help_flag} | {ai_flag} | {fb_flag} | "
            f"{len(roll.template_dirs)} | {len(roll.likely_workflow_pages)} |\n"
        )

    md.append("\n## Honest gaps (signals, not classifications)\n\n")
    md.append("Phase 0 only flags _signals_. Classification (strong vs broken vs missing how-to) is Phase 1.\n\n")
    md.append("**Framing:** an app with zero routes and zero `urls.py` is NOT a defect. Many apps in this repo are model-only / service-only and surface through other apps' views. Those are listed in the **Service-only apps** section below, not in gaps.\n\n")
    for gap_name, apps in sorted(gaps.items()):
        md.append(f"### `{gap_name}` ({len(apps)} apps)\n\n")
        md.append("  " + ", ".join(f"`{a}`" for a in sorted(apps)) + "\n\n")

    md.append("## Service-only apps (informational)\n\n")
    md.append(f"{len(service_only_apps)} apps have no `*urls*.py` and no `path(...)` declarations. These are model / service / task layers that surface through other apps' views:\n\n")
    md.append("  " + ", ".join(f"`{a}`" for a in service_only_apps) + "\n\n")

    md.append("\n## Related existing inventories (cross-reference)\n\n")
    for inv in related_inventories:
        md.append(f"- `{inv['path']}` ({inv['size_bytes']:,} bytes)\n")

    md.append("\n## Phase 0 deferred (next waves)\n\n")
    for line in out["phase_0_deferred"]:
        md.append(f"- {line}\n")

    md.append(f"\n**Verdict:** `{out['verdict']}`\n")

    OUT_MD.write_text("".join(md), encoding="utf-8")

    print(f"Wrote {OUT_JSON.relative_to(ROOT)} ({OUT_JSON.stat().st_size:,} bytes)")
    print(f"Wrote {OUT_MD.relative_to(ROOT)} ({OUT_MD.stat().st_size:,} bytes)")
    print(f"Apps: {s['apps_scanned']} | Routes: {s['total_routes']} | Includes: {s['total_includes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
