#!/usr/bin/env python3
"""
Help-center tier ladder gate: Great (1339–1340) + Category-defining (1341–1345).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ok(rel: str, needle: str) -> bool:
    path = ROOT / rel
    return path.is_file() and needle in path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    checks = [
        ("1339-synonyms", _ok("apps/portal/kb_synonyms.py", "expand_query_synonyms")),
        ("1339-typeahead-api", _ok("apps/api/urls.py", "kb-typeahead")),
        ("1339-typeahead-js", (ROOT / "static/js/rmc-help-search-typeahead.js").is_file()),
        ("1339-zero-result", _ok("apps/portal/help_search_intelligence.py", "zero_result_fingerprints")),
        ("1340-review-queue", _ok("config/manager_urls.py", "manager_ai_review_queue")),
        ("1340-review-template", (ROOT / "templates/schools/partials/manager_ai_review_queue_body.html").is_file()),
        ("1340-review-note-field", _ok("apps/feedback/models.py", "note = models.TextField")),
        ("1340-review-migration", (ROOT / "apps/feedback/migrations/0005_support_ai_review_note.py").is_file()),
        ("1341-celery-reindex", _ok("config/settings.py", "portal-reindex-kb-embeddings-weekly")),
        ("1341-publish-embed", _ok("apps/portal/models_kb.py", "KB_EMBEDDING_AUTO_REFRESH")),
        ("1342-proactive", _ok("apps/schools/operator_help_signals.py", "safe_proactive_friction_nudges")),
        ("1343-locale-field", _ok("apps/portal/models_kb.py", "locale = models.CharField")),
        ("1343-migration", (ROOT / "apps/portal/migrations/0036_kbarticle_locale.py").is_file()),
        ("1344-offline-doc", (ROOT / "docs/OFFLINE_HELP_APPLIANCE.md").is_file()),
        ("1344-offline-ui", _ok("templates/portal/partials/kb_ai_assistant_panel.html", "data-rmc-kb-ai-offline")),
        ("1345-governance", _ok("apps/portal/help_governance.py", "ai_help_enabled_for_request")),
        ("1345-purge-cmd", (ROOT / "apps/feedback/management/commands/purge_help_telemetry.py").is_file()),
        ("1345-feature-flag", _ok("apps/siteconfig/models_support.py", "enable_ai_help_assistant")),
        ("unified-deflection-js", _ok("static/js/rmc-support-deflection.js", "data-deflection-surface")),
        ("unified-persona", (ROOT / "templates/partials/help_persona_quickstart.html").is_file()),
        ("tenant-help-ai", _ok("templates/feedback/help_center.html", "kb_ai_assistant_panel")),
        # Wave 2 — 1346–1353
        ("1346-school-context", _ok("apps/portal/school_help_context.py", "build_school_help_context_block")),
        ("1346-gateway-inject", _ok("services/ai/gateway.py", "build_school_help_context_block")),
        ("1347-deflection-cp", _ok("apps/portal/context_processors.py", "support_deflection_urls")),
        ("1347-feature-form", _ok("templates/feedback/feature_center.html", "data-deflection-form-auto")),
        ("1347-contact-form", _ok("templates/feedback/contact_us.html", "data-deflection-form-auto")),
        ("1348-hitl-publish", _ok("apps/portal/kb_hitl_publish.py", "create_kb_draft_from_review")),
        ("1348-review-button", _ok("templates/schools/partials/manager_ai_review_queue_body.html", "publish_kb_draft")),
        ("1349-analytics", _ok("config/manager_urls.py", "manager_help_analytics")),
        ("1349-north-star", _ok("apps/portal/help_north_star.py", "build_north_star_bundle")),
        ("1350-locale-group", _ok("apps/portal/models_kb.py", "locale_group_id")),
        ("1351-pgvector", _ok("apps/portal/kb_pgvector.py", "search_kb_pgvector")),
        ("1352-proactive", _ok("apps/portal/help_proactive_inline.py", "proactive_nudge_for_request")),
        ("1352-nudge-template", (ROOT / "templates/partials/help_proactive_nudge.html").is_file()),
        ("1353-journeys", _ok("apps/portal/help_guided_journeys.py", "JOURNEY_BY_PREFIX")),
        ("1353-csat-api", _ok("apps/api/urls.py", "ai-support-session-rating")),
        ("1353-csat-model", _ok("apps/feedback/models.py", "SupportAISessionRating")),
        ("1353-csat-js", _ok("static/js/rmc-kb-ai-assistant.js", "postSessionRating")),
        # Batch 1354 — all-bases-covered
        ("1354-manager-deflection", _ok("templates/schools/partials/manager_help_center_body.html", "data-deflection-form-auto")),
        ("1354-school-feedback-deflection", _ok("templates/feedback/school_center.html", "data-deflection-form-auto")),
        ("1354-role-feedback-deflection", _ok("templates/feedback/role_center.html", "data-deflection-form-auto")),
        ("1354-cp-drawer", _ok("templates/control_plane_skeleton.html", "help_contextual_drawer")),
        ("1354-csat-hitl", _ok("apps/portal/views_ai_gateway.py", 'thumbs == "down"')),
        ("1354-publish-kb", _ok("apps/portal/kb_hitl_publish.py", "publish_kb_article")),
        ("1354-journey-resolve", _ok("apps/portal/context_processors.py", "resolve_journey_articles")),
        ("1354-content-gap", _ok("apps/portal/help_content_gaps.py", "ensure_content_gap_task")),
        ("1354-gap-model", _ok("apps/feedback/models.py", "HelpContentGapTask")),
        ("1354-analytics-csv", _ok("config/manager_help_analytics.py", 'format") == "csv"')),
        ("1354-locale-families", _ok("config/manager_urls.py", "manager_kb_locale_families")),
        ("1354-purge-beat", _ok("config/settings.py", "portal-purge-help-telemetry-monthly")),
        ("1354-kb-pgvector-cmd", (ROOT / "apps/portal/management/commands/migrate_kb_embeddings_to_pgvector.py").is_file()),
        ("1354-journey-seed", (ROOT / "apps/portal/management/commands/seed_help_journey_slugs.py").is_file()),
        ("1354-deflection-panel-class", _ok("templates/partials/help_deflection_strip.html", "rmc-support-deflection-panel")),
        ("1354-locale-fallback", _ok("apps/portal/kb_embeddings.py", "filter_kb_queryset_by_locale_with_fallback")),
    ]
    failed = [cid for cid, ok in checks if not ok]
    if failed:
        print(f"verify_help_center_tiers: FAIL ({len(failed)})", file=sys.stderr)
        for cid in failed:
            print(f"  - {cid}", file=sys.stderr)
        return 1
    print(f"verify_help_center_tiers: HELP_CENTER_TIERS_PASS ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
