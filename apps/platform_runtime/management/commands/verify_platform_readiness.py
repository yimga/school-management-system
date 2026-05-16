"""Wave N (2026-05-15): unified platform readiness preflight.

Single operator-facing surface that orchestrates every preflight in
the platform:

* **K4** — data residency (replica coverage + alignment + backfill).
* **L2** — CSP enforcement (middleware wiring + report URI + directive
  coverage + script-src hardening).
* **L-followup** — CSP runtime violation counters (informational).
* **N1** — documented baseline drift (CLAUDE.md scanner table vs
  ``var/security-audit-baseline-*.json``).

Useful for:

* Pre-deploy CI step that gates production rollout.
* On-call surface for "is the platform actually shippable right now?"
* Audit trail when flipping any platform-wide enforcement switch.

Exit codes:
  0 — every preflight is ready.
  1 — at least one preflight reports an issue.
  2 — invocation error (e.g. settings missing, scanner subprocess failed).

Usage:
  python manage.py verify_platform_readiness
  python manage.py verify_platform_readiness --json
  python manage.py verify_platform_readiness --section residency csp
"""

from __future__ import annotations

import json as _json
import subprocess
import sys
from pathlib import Path

from django.core.management.base import BaseCommand

# Sections we know how to run. Operators may opt into a subset with
# --section, e.g. when one preflight has known transient noise.
SECTIONS: tuple[str, ...] = (
    "residency", "csp", "rls", "at_risk", "baselines", "first_school",
)


class Command(BaseCommand):
    help = (
        "Unified preflight: data residency + CSP enforcement + documented "
        "scanner baselines. Exit 0 when all ready; 1 when any preflight blocks."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json", action="store_true",
            help="Emit machine-readable JSON instead of operator-friendly text.",
        )
        parser.add_argument(
            "--section", nargs="+", default=None,
            choices=SECTIONS,
            help=(
                f"Run only the named sections; default runs all of "
                f"{', '.join(SECTIONS)}."
            ),
        )

    def handle(self, *args, **opts):
        wanted = set(opts.get("section") or SECTIONS)
        sections: dict[str, dict] = {}

        if "residency" in wanted:
            sections["residency"] = self._residency_section()
        if "csp" in wanted:
            sections["csp"] = self._csp_section()
        if "rls" in wanted:
            sections["rls"] = self._rls_section()
        if "at_risk" in wanted:
            sections["at_risk"] = self._at_risk_section()
        if "baselines" in wanted:
            sections["baselines"] = self._baselines_section()
        if "first_school" in wanted:
            sections["first_school"] = self._first_school_section()

        overall_ready = all(s.get("ready") for s in sections.values())
        any_invocation_error = any(s.get("error") for s in sections.values())

        if opts.get("json"):
            payload = {
                "ready": overall_ready,
                "sections": sections,
            }
            self.stdout.write(_json.dumps(payload, indent=2, sort_keys=True, default=str))
        else:
            self._render_text(sections, overall_ready)

        # Exit code priority: invocation error > not-ready > ready.
        if any_invocation_error:
            raise SystemExit(2)
        if not overall_ready:
            raise SystemExit(1)

    # --- sections ----------------------------------------------------------

    def _residency_section(self) -> dict:
        try:
            from apps.schools.residency_readiness import assess_readiness

            report = assess_readiness()
        except (ImportError, RuntimeError) as exc:
            return {"ready": False, "error": str(exc), "details": {}}
        return {
            "ready": report.ready,
            "issue_count": report.issue_count(),
            "details": {
                "schools_total": report.schools_total,
                "active_regions": sorted(report.schools_active_regions),
                "missing_replicas": report.missing_replicas,
                "misaligned_schools": [
                    {"slug": s, "regulatory": r, "operational": o}
                    for s, r, o in report.misaligned_schools
                ],
                "unbackfilled_schools": [
                    {"slug": s, "country": c, "derived": d}
                    for s, c, d in report.unbackfilled_schools
                ],
            },
        }

    def _csp_section(self) -> dict:
        try:
            from apps.security.csp_readiness import assess_csp_readiness

            report = assess_csp_readiness()
        except (ImportError, RuntimeError) as exc:
            return {"ready": False, "error": str(exc), "details": {}}
        return {
            "ready": report.ready,
            "issue_count": report.issue_count(),
            "details": {
                "middleware_wired": report.middleware_wired,
                "report_uri": report.report_uri,
                "directives_missing": report.directives_missing,
                "script_src_has_unsafe_inline": report.script_src_has_unsafe_inline,
                "script_src_has_unsafe_eval": report.script_src_has_unsafe_eval,
                "style_src_has_unsafe_inline": report.style_src_has_unsafe_inline,
                "violations_last_hour": report.violations_last_hour,
                "violations_last_24h": report.violations_last_24h,
                "violations_by_directive_24h": report.violations_by_directive_24h,
            },
        }

    def _rls_section(self) -> dict:
        try:
            from apps.schools.rls_readiness import assess_rls_readiness

            report = assess_rls_readiness()
        except (ImportError, RuntimeError) as exc:
            return {"ready": False, "error": str(exc), "details": {}}
        return {
            "ready": report.ready,
            "issue_count": report.issue_count(),
            "details": {
                "backend_vendor": report.backend_vendor,
                "middleware_wired": report.middleware_wired,
                "rls_context_importable": report.rls_context_importable,
                "use_django_tenants_disabled": report.use_django_tenants_disabled,
                "guc_settable": report.guc_settable,
                "policy_count": report.policy_count,
                "skipped_checks": report.skipped_checks,
                "error_detail": report.error_detail,
            },
        }

    def _at_risk_section(self) -> dict:
        try:
            from apps.analytics.at_risk_readiness import assess_at_risk_readiness

            report = assess_at_risk_readiness()
        except (ImportError, RuntimeError) as exc:
            return {"ready": False, "error": str(exc), "details": {}}
        return {
            "ready": report.ready,
            "issue_count": report.issue_count(),
            "details": {
                "mode": report.mode,
                "resolved_path": report.resolved_path,
                "artifact_exists": report.artifact_exists,
                "artifact_loadable": report.artifact_loadable,
                "bundle_shape_valid": report.bundle_shape_valid,
                "bundle_model_version": report.bundle_model_version,
                "error_detail": report.error_detail,
            },
        }

    def _first_school_section(self) -> dict:
        """Wave 7 (v2.80): at least one tenant must meet the operating minimum.

        Calls ``apps.schools.first_school_readiness.assess_first_school_readiness``
        and surfaces the count of operating-ready tenants. The platform is not
        "ready to host a school" if zero tenants pass all minimum-operating
        criteria.
        """
        try:
            from apps.schools.first_school_readiness import (
                assess_first_school_readiness,
            )

            report = assess_first_school_readiness()
        except (ImportError, RuntimeError) as exc:
            return {"ready": False, "error": str(exc), "details": {}}
        return {
            "ready": report.ready,
            "issue_count": report.issue_count(),
            "details": {
                "schools_total": report.schools_total,
                "schools_operating_ready": report.schools_operating_ready,
                "tenants_ready": report.tenants_ready[:20],
                "tenants_not_ready": report.tenants_not_ready[:20],
                "error_detail": report.error_detail,
            },
        }

    def _baselines_section(self) -> dict:
        """Shell out to ``scripts/check_documented_baselines.py --json``.

        Done as a subprocess so the readiness command stays decoupled
        from the scanner module's filesystem-walking concerns and runs
        the script the same way CI does.
        """
        # Locate the repo root from this module's path. The command
        # module is at apps/platform_runtime/management/commands/.
        repo_root = Path(__file__).resolve().parents[4]
        script = repo_root / "scripts" / "check_documented_baselines.py"
        if not script.exists():
            return {"ready": False, "error": f"script missing: {script}", "details": {}}
        try:
            proc = subprocess.run(  # noqa: S603
                [sys.executable, str(script), "--json"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return {"ready": False, "error": str(exc), "details": {}}
        try:
            data = _json.loads(proc.stdout or "{}")
        except _json.JSONDecodeError:
            return {
                "ready": False,
                "error": "baseline checker stdout was not valid JSON",
                "details": {"stdout": proc.stdout[:500], "stderr": proc.stderr[:500]},
            }
        drift_count = int(data.get("drift_count", 0))
        return {
            "ready": drift_count == 0,
            "issue_count": drift_count,
            "details": {
                "drift": data.get("drift", []),
                "row_count": len(data.get("rows", [])),
            },
        }

    # --- rendering ---------------------------------------------------------

    def _render_text(self, sections: dict, overall_ready: bool) -> None:
        self.stdout.write("=== Platform readiness preflight ===")
        for name in SECTIONS:
            if name not in sections:
                continue
            section = sections[name]
            ready = section.get("ready")
            error = section.get("error")
            if error:
                self.stdout.write(self.style.ERROR(
                    f"!!  {name:12s} ERROR: {error}"
                ))
                continue
            if ready:
                self.stdout.write(self.style.SUCCESS(
                    f"OK  {name:12s} ready"
                ))
            else:
                issues = section.get("issue_count", 0)
                self.stdout.write(self.style.WARNING(
                    f"!!  {name:12s} NOT READY ({issues} issue{'s' if issues != 1 else ''})"
                ))
            # Render section-specific drilldown.
            self._render_section_detail(name, section)

        self.stdout.write("")
        if overall_ready:
            self.stdout.write(self.style.SUCCESS(
                "READY — every preflight is clean."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "NOT READY — resolve the issue(s) above before flipping "
                "production switches (DATA_RESIDENCY_ENFORCE, CSP_ENFORCE, "
                "etc.)."
            ))

    def _render_section_detail(self, name: str, section: dict) -> None:
        details = section.get("details") or {}
        if not details:
            return
        if name == "residency":
            if details.get("missing_replicas"):
                self.stdout.write(
                    "      missing replicas: " + ", ".join(details["missing_replicas"])
                )
            if details.get("misaligned_schools"):
                for row in details["misaligned_schools"][:5]:
                    self.stdout.write(
                        f"      misaligned: {row['slug']} "
                        f"regulatory={row['regulatory']} operational={row['operational']}"
                    )
            if details.get("unbackfilled_schools"):
                n = len(details["unbackfilled_schools"])
                self.stdout.write(
                    f"      unbackfilled tenants: {n} (run verify_data_residency --fix-derive)"
                )
        elif name == "csp":
            v1h = details.get("violations_last_hour", 0)
            v24 = details.get("violations_last_24h", 0)
            if v1h or v24:
                self.stdout.write(
                    f"      runtime violations: last-hour={v1h}  last-24h={v24}"
                )
            if details.get("directives_missing"):
                self.stdout.write(
                    "      missing directives: "
                    + ", ".join(details["directives_missing"])
                )
        elif name == "rls":
            self.stdout.write(f"      backend: {details.get('backend_vendor')}")
            if details.get("policy_count") is not None:
                self.stdout.write(f"      pg_policies: {details['policy_count']}")
            if not details.get("use_django_tenants_disabled"):
                self.stdout.write(self.style.ERROR(
                    "      WARNING: USE_DJANGO_TENANTS=True — RLS is bypassed!"
                ))
            if details.get("error_detail"):
                self.stdout.write(f"      detail: {details['error_detail']}")
        elif name == "at_risk":
            mode = details.get("mode")
            self.stdout.write(f"      mode: {mode}")
            if details.get("resolved_path"):
                self.stdout.write(f"      path: {details['resolved_path']}")
            if details.get("bundle_model_version"):
                self.stdout.write(
                    f"      model_version: {details['bundle_model_version']}"
                )
            if details.get("error_detail"):
                self.stdout.write(f"      detail: {details['error_detail']}")
        elif name == "baselines":
            for entry in details.get("drift") or []:
                self.stdout.write(
                    f"      {entry.get('scanner')}: {entry.get('reason')}"
                )
