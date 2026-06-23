#!/usr/bin/env python
"""Codemod: add `# rbac-allow: <reason>` markers to the candidate-anonymous
routes that `audit_role_permission_matrix.py` flags but which are intentionally
public OR protected by an in-view mechanism the AST scanner cannot see
(token/grant, HMAC signature, OAuth2 bearer, firewall-fronted scrape, etc.).

Driven by the freshly-generated docs/generated/role_permission_matrix.json so it
marks EXACTLY the routes the scanner currently flags — no more, no less.

Safety contract (so this never rubber-stamps a real hole):
  * Every (view_file basename, view_symbol) among the candidates must resolve to
    a REVIEWED reason via `reason_for()`. If ANY candidate has no reviewed reason,
    the codemod writes NOTHING and prints the un-triaged pairs for human review.
  * A marker is inserted only on the line directly above the `path(...)` call
    (matching indentation) — never editing the route line itself — and only when
    neither that line nor the line above already carries an `rbac-allow` marker.
  * Idempotent: re-running after a successful pass inserts nothing.

Run:  python scripts/codemod_rbac_allow_public_routes.py [--apply]
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATRIX_JSON = ROOT / "docs" / "generated" / "role_permission_matrix.json"

# Same path-capture regex the scanner uses, so finditer order + match spans align.
URL_PATH_RE = re.compile(
    r"""path\(\s*r?["']([^"']*)["']\s*,\s*([A-Za-z_][A-Za-z0-9_.]*)(\(\s*\))?\s*[,)]""",
    re.DOTALL,
)


def _sym(view_symbol: str) -> str:
    raw = view_symbol
    if raw.endswith(".as_view"):
        raw = raw[: -len(".as_view")]
    return raw.split(".")[-1]


# Whole-file public surfaces (marketing/signup/PWA/service-worker/status) are now
# excluded from candidate scope by the scanner itself (_PUBLIC_SURFACE_VIEW_BASENAMES),
# so they no longer reach this codemod. Intentionally empty: if one ever leaks back
# in as a candidate, reason_for() returns None and the codemod ABORTS (fail-loud)
# rather than auto-marking it.
_BY_FILE: dict[str, str] = {}

# Per-(file, symbol) reasons for files that mix public + in-view-protected routes.
_EXACT = {
    ("section8_views.py", "find_school"): "public-tenant-discovery-pre-login",
    ("section8_views.py", "global_login_discovery"): "public-tenant-discovery-pre-login",
    ("section8_views.py", "frozen_account"): "public-frozen-account-landing-page",
    ("section8_views.py", "jwks_json"): "public-lti-1p3-jwks-keyset-by-design",
    ("section8_views.py", "public_support_hub"): "public-self-service-support-hub",
    ("section8_views.py", "public_verify_hub"): "public-self-service-verify-hub",
    ("section8_views.py", "verify_caddy_domain"): "machine-endpoint-caddy-on-demand-tls-domain-check",
    ("views.py", "api_weather_context"): "public-safe-weather-widget-snapshot",
    ("views.py", "csrf_token_refresh"): "public-csrf-token-issue-pre-auth",
    ("views.py", "healthz"): "public-health-probe-for-load-balancer",
    ("views.py", "public_version"): "public-version-string-no-sensitive-data",
    ("views_administration.py", "internal_admin_alias_redirect"): "redirect-only-target-admin-enforces-auth",
    ("views_auditor.py", "auditor_inspect"): "signed-auditor-grant-token-plus-ip-allowlist-in-view",
    ("views_metrics.py", "PrometheusMetricsView"): "prometheus-scrape-anonymous-firewall-protected",
    ("views_oauth_metrics.py", "lms_oauth_metrics_text"): "prometheus-oauth-metrics-scrape-firewall-protected",
    ("views_owner_onboarding.py", "OwnerOnboardingAccountView"): "token-gated-onboarding-uidb64-token-in-url",
    ("views_rum.py", "rum_ingest"): "rum-ingest-authed-by-body-token-or-x-rum-key-header",
    ("views_tour.py", "tour_steps_public_api"): "public-tour-steps-for-marketing-shell",
    ("api_views.py", "platform_billing_processor_webhook"): "payment-processor-webhook-hmac-signature-verified-in-view",
}


def reason_for(view_file: str | None, view_symbol: str) -> str | None:
    base = (view_file or "").split("/")[-1]
    sym = _sym(view_symbol)
    if base == "section8_views.py" and sym.startswith("lti_"):
        if sym in ("lti_launch", "lti_launch_callback"):
            return "lti-1p3-signed-jwt-launch-verified-in-view"
        return "lti-1p3-oauth2-bearer-and-scope-verified-in-view"
    if (base, sym) in _EXACT:
        return _EXACT[(base, sym)]
    if base in _BY_FILE:
        return _BY_FILE[base]
    return None


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    data = json.loads(MATRIX_JSON.read_text(encoding="utf-8"))
    cand = [r for r in data["rows"] if r["candidate_anonymous"]]

    # Fail-loud triage gate: every candidate must have a reviewed reason.
    untriaged = sorted(
        {
            ((r["view_file"] or "UNRESOLVED").split("/")[-1], r["view_symbol"])
            for r in cand
            if reason_for(r["view_file"], r["view_symbol"]) is None
        }
    )
    if untriaged:
        print("ABORT: un-triaged candidate routes (no reviewed reason). Review these first:")
        for base, sym in untriaged:
            print(f"  {base:34} {sym}")
        return 2

    # Group candidate (url_pattern, view_symbol) -> reason, per urls_file.
    by_file: dict[str, dict[tuple[str, str], str]] = defaultdict(dict)
    for r in cand:
        by_file[r["urls_file"]][(r["url_pattern"], r["view_symbol"])] = reason_for(
            r["view_file"], r["view_symbol"]
        )

    total_marked = 0
    for urls_file, wanted in sorted(by_file.items()):
        path = ROOT / urls_file
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        # line_no (1-based) -> (indent, reason) to insert ABOVE that line.
        inserts: dict[int, tuple[str, str]] = {}
        for m in URL_PATH_RE.finditer(text):
            key = (m.group(1), m.group(2))
            if key not in wanted:
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            cur = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
            prev = lines[line_no - 2] if line_no - 2 >= 0 else ""
            if "rbac-allow" in cur or "rbac-allow" in prev:
                continue
            indent = cur[: len(cur) - len(cur.lstrip())]
            inserts[line_no] = (indent, wanted[key])
        if not inserts:
            continue
        # Insert bottom-up so earlier line numbers stay valid.
        for line_no in sorted(inserts, reverse=True):
            indent, reason = inserts[line_no]
            lines.insert(line_no - 1, f"{indent}# rbac-allow: {reason}\n")
        total_marked += len(inserts)
        print(f"  {urls_file}: +{len(inserts)} markers")
        if apply:
            path.write_text("".join(lines), encoding="utf-8")

    print(f"\n{'APPLIED' if apply else 'DRY-RUN'}: {total_marked} markers across {len(by_file)} urls files")
    if not apply:
        print("Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
