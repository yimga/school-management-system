#!/usr/bin/env python3
"""
Help-center tier ladder gate: Great (1339–1340) + Category-defining (1341–1345).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROOT_DIR = ROOT


def _ok(rel: str, needle: str) -> bool:
    path = ROOT / rel
    return path.is_file() and needle in path.read_text(encoding="utf-8", errors="replace")


#: Gates this ladder certifies that cannot pass without a seeded global KB corpus.
#: The precondition is NAMED here and CHECKED below rather than sniffed out of a
#: gate's output, so "this checkout has no seed data" can never be confused with
#: "the product is broken" -- and, just as important, can never be used to wave
#: away a real failure once the corpus IS present.
_KB_CORPUS_GATES = frozenset(
    {
        "scripts/verify_workflow_kb_corpus.py",
        "scripts/verify_workflow_kb_corpus_quality.py",
        "scripts/verify_workflow_kb_editorial.py",
    }
)

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


def _kb_corpus_seeded() -> bool | None:
    """True/False if we can tell, None if Django itself will not come up."""
    try:
        import django

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()
        from apps.portal.models_kb import KBArticle

        return KBArticle.objects.filter(school__isnull=True).exists()
    except Exception:
        return None


def _gate(rel: str, timeout: int = 300) -> tuple[str, str]:
    """Run another gate and honour its exit code.

    Returns (PASS | FAIL | SKIP, detail). SKIP IS NEVER PASS -- that distinction
    is the whole point of this rewrite. "Could not tell" must not read as
    "satisfied", which is exactly what `.is_file()` did: it reported this tier
    green while the verifier it names exited 1.

    The repo already draws this line the same way: pre_push_boundary_check.py
    renders a gate's exit-2 as SKIP precisely so an unrunnable check never reads
    as a passing one.
    """
    path = ROOT_DIR / rel
    if not path.is_file():
        return FAIL, f"{rel} does not exist"
    if rel in _KB_CORPUS_GATES and _kb_corpus_seeded() is not True:
        return SKIP, f"{rel} needs a seeded global KB corpus (manage.py seed_workflow_kb_corpus)"
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return SKIP, f"{rel} exceeded {timeout}s (machine load, not a verdict)"
    except OSError as exc:
        return SKIP, f"{rel} could not be launched: {exc}"
    if proc.returncode == 0:
        return PASS, ""
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
    detail = tail[-1] if tail else f"exit {proc.returncode}"
    return FAIL, f"{rel} exits {proc.returncode}: {detail}"


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
        # Contextual help drawer (fixed chip) + page-context JS on control plane / portal shells.
        (
            "1354-cp-drawer",
            _ok("templates/control_plane_skeleton.html", "help_contextual_drawer.html")
            and _ok("templates/control_plane_skeleton.html", "rmc-page-context-help.js")
            and _ok("templates/portal_base.html", "help_contextual_drawer.html"),
        ),
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
        # Batch 1356 — final gap closeout
        ("1356-feature-center-deflection", _ok("templates/schools/partials/manager_feature_center_body.html", "manager_feature_center")),
        ("1356-support-form", _ok("templates/schools/partials/manager_support_request_body.html", "data-deflection-form-auto")),
        ("1356-support-view", _ok("config/manager_operator_support.py", "ManagerSupportRequestForm")),
        ("1356-inline-copilot", _ok("templates/partials/help_module_inline_assistant.html", "show_module_inline_help_assistant")),
        ("1356-marketing-help", _ok("templates/marketing/partials/mkt_help_engine.html", "mkt-help-engine")),
        ("1356-north-star-email", _ok("apps/portal/tasks.py", "portal.help_north_star_weekly_email")),
        ("1356-kb-archive", _ok("apps/portal/kb_archive.py", "stale_kb_archive_candidates")),
        ("1356-archive-cmd", (ROOT / "apps/portal/management/commands/archive_stale_kb_articles.py").is_file()),
        ("1356-locale-ops", _ok("apps/portal/kb_locale_ops.py", "publish_locale_group")),
        ("1356-locale-publish-ui", _ok("templates/schools/partials/manager_kb_locale_families_body.html", "publish_group")),
        ("1647-odt-round-trip", _ok("apps/portal/kb_office_service.py", "reimport_odt_into_kb_article")),
        ("1647-reimport-route", _ok("apps/portal/urls_kb.py", "kb_article_reimport_odt")),
        ("1647-locale-publish-one", _ok("apps/portal/kb_locale_ops.py", "publish_locale_article")),
        ("1647-locale-coverage", _ok("templates/schools/partials/manager_kb_locale_families_body.html", "missing_locales")),
        ("1647-docs-hub-link", _ok("templates/schools/partials/manager_kb_locale_families_body.html", "docs_hub_url")),
        ("1648-kb-admin-locale", _ok("apps/portal/admin_kb.py", "Locale & translation")),
        ("1648-kb-admin-odt", _ok("apps/portal/admin_kb.py", "regenerate_odt_files")),
        ("1648-regenerate-odt-svc", _ok("apps/portal/kb_office_service.py", "regenerate_kb_article_odt")),
        ("1356-orchestrator-help", _ok("scripts/generate_orchestrator_journey_manifest.py", "supplementary_help_center_journeys")),
        ("1356-corpus-runbook", (ROOT / "docs/HELP_CENTER_LOCALE_CORPUS_RUNBOOK.md").is_file()),
        # Batch 1357 — community forums + marketing sovereign KB
        ("1357-forum-models", _ok("apps/portal/models_forums.py", "CommunityForumTopic")),
        ("1357-forum-views", _ok("apps/portal/views_forums.py", "forum_home")),
        ("1357-forum-urls", _ok("apps/portal/urls.py", "forum_home")),
        ("1357-forum-templates", (ROOT / "templates/portal/forums_home.html").is_file()),
        ("1357-forum-redirect", _ok("apps/portal/views.py", 'feature == "forums"')),
        ("1357-marketing-kb-module", _ok("apps/portal/marketing_kb.py", "marketing_kb_search")),
        ("1357-marketing-kb-search-url", _ok("config/urls.py", "marketing_kb_search")),
        ("1357-marketing-kb-typeahead", _ok("config/urls.py", "marketing_kb_typeahead")),
        ("1357-mkt-help-engine-search", _ok("templates/marketing/partials/mkt_help_engine.html", "marketing_kb_search")),
        ("1357-mkt-kb-results-template", (ROOT / "templates/marketing/kb_search_results.html").is_file()),
        ("1357-mkt-kb-typeahead-js", (ROOT / "static/marketing/js/mkt-kb-search-typeahead.js").is_file()),
        ("1357-forum-migration", (ROOT / "apps/portal/migrations/0038_community_forums_1357.py").is_file()),
        # Batch 1359 — help center elevation
        ("1359-unified-hub", _ok("apps/portal/help_unified_hub.py", "tenant_community_lane")),
        ("1359-forum-kb-bridge", _ok("apps/portal/help_forum_kb_bridge.py", "suggested_kb_for_text")),
        ("1359-marketing-hub-bundle", _ok("apps/portal/marketing_kb.py", "marketing_kb_hub_bundle")),
        ("1359-hybrid-search", _ok("apps/portal/marketing_kb.py", "marketing_kb_search_hybrid")),
        ("1359-mkt-help-hub", (ROOT / "templates/marketing/partials/mkt_help_hub.html").is_file()),
        ("1359-community-lane", (ROOT / "templates/partials/help_community_lane.html").is_file()),
        ("1359-forum-deflection", _ok("templates/portal/forums_new_topic.html", "data-deflection-form-auto")),
        ("1359-forum-kb-sidebar", _ok("templates/portal/forums_topic.html", "forum-kb-suggestions")),
        ("1359-tenant-help-community", _ok("templates/feedback/help_center.html", "help_community_lane")),
        ("1359-operator-public-kb", _ok("config/manager_help_center.py", "operator_public_kb_lane")),
        ("1359-unified-css", (ROOT / "static/css/rmc-help-unified-hub.css").is_file()),
        # Batch 1360 — forum notifications + marketing KB categories + compose AI
        ("1360-forum-notifications", _ok("apps/portal/forum_notifications.py", "send_forum_reply_notifications")),
        ("1360-forum-notify-task", _ok("apps/portal/tasks.py", "notify_forum_reply_task")),
        ("1360-forum-email-template", (ROOT / "templates/portal/email/forum_reply_notification.html").is_file()),
        ("1360-forum-compose-ai", _ok("apps/portal/help_forum_compose.py", "forum_compose_assistant_for_request")),
        ("1360-forum-compose-partial", (ROOT / "templates/portal/partials/forum_compose_ai_assistant.html").is_file()),
        ("1360-forum-compose-wired", _ok("templates/portal/forums_new_topic.html", "forum_compose_ai_assistant")),
        ("1360-marketing-kb-category-fn", _ok("apps/portal/marketing_kb.py", "marketing_kb_category_by_slug")),
        ("1360-marketing-kb-category-url", _ok("config/urls.py", "marketing_kb_category")),
        ("1360-mkt-kb-category-template", (ROOT / "templates/marketing/kb_category_public.html").is_file()),
        ("1360-mkt-hub-category-link", _ok("templates/marketing/partials/mkt_help_hub.html", "marketing_kb_category")),
        # Batch 1484 — page-aware help landing + KB auto-gen hub links
        ("1484-help-page-inbound", _ok("apps/portal/help_page_inbound.py", "parse_help_landing_inbound")),
        ("1484-manager-help-inbound", _ok("config/manager_help_center.py", "parse_help_landing_inbound")),
        ("1484-tenant-help-inbound", _ok("apps/feedback/views.py", "parse_help_landing_inbound")),
        ("1484-kb-auto-gen-cards", _ok("config/manager_help_center.py", "super:ai_center_generate_kb")),
        ("1484-help-search-prefill", _ok("templates/schools/partials/manager_help_center_body.html", "help_search_initial_q")),
        ("1484-404-help-hub", _ok("templates/errors/404.html", "manager_help_center")),
        ("1484-sidebar-help-center", _ok("apps/siteconfig/portal_sidebar_items.py", '"id": "help_center"')),
        # Batch 1485 — honest 10x finish (corpus, hub merge, auto-draft, inline AI)
        ("1485-workflow-corpus-module", (ROOT / "apps/portal/workflow_kb_corpus.py").is_file()),
        ("1485-seed-corpus-cmd", (ROOT / "apps/portal/management/commands/seed_workflow_kb_corpus.py").is_file()),
        ("1485-verify-corpus", _gate("scripts/verify_workflow_kb_corpus.py")),
        ("1485-hub-merge-lane", _ok("templates/feedback/help_center.html", "help_center_support_lane")),
        ("1485-support-hub-redirect", _ok("apps/portal/views_support.py", "feedback:help_center")),
        ("1485-portal-help-entry", _ok("apps/feedback/services.py", '"portal_help": "feedback:help_center"')),
        ("1485-staging-auto-draft", _ok("config/settings.py", "_HELP_AUTO_DRAFT_DEFAULT")),
        ("1485-inline-evals", _ok("templates/evals/compliance_dashboard.html", "help_module_inline_assistant")),
        ("1485-inline-siteconfig", _ok("templates/siteconfig/console_domains_hub.html", "help_module_inline_assistant")),
        ("1485-inline-migration", _ok("templates/migration_cloud/operator/command_center.html", "help_module_inline_assistant")),
        ("1485-inline-prefixes", _ok("apps/portal/help_proactive_inline.py", "/siteconfig/")),
        # Batch 1486 — full Phase 9 corpus + auto-draft posture + admin/super help bridge
        ("1486-audit-corpus-module", (ROOT / "apps/portal/workflow_kb_corpus_audit.py").is_file()),
        ("1486-all-corpus-merge", _ok("apps/portal/workflow_kb_corpus.py", "ALL_WORKFLOW_KB_CORPUS")),
        ("1486-audit-refresh-cmd", (ROOT / "scripts/refresh_workflow_help_kb_audit_kb_status.py").is_file()),
        ("1486-auto-draft-posture", _gate("scripts/verify_help_auto_draft_posture.py")),
        # The admin's help-centre link moved in 4bc5375fa (Admin navigation v3):
        # app_list.html lost it and the new templates/admin/sidebar_v3_body.html
        # gained it. The check kept naming the old file, so it has been failing on
        # main ever since -- unnoticed, because Actions billing has been down since
        # 2026-08-15. What the gate is actually for is that an admin user can reach
        # the help centre from the admin chrome, so accept it in either surface
        # rather than pinning one filename the next nav revision will move again.
        ("1486-admin-tenant-help", any(
            _ok(rel, "feedback:help_center")
            for rel in (
                "templates/admin/sidebar_v3_body.html",
                "templates/admin/app_list.html",
            )
        )),
        ("1486-admin-super-bridge", _gate("scripts/verify_admin_super_help_nav_bridge.py")),
        # Batch 1487 — editorial high-stakes runbooks + admin/super nav convergence
        ("1487-editorial-corpus", (ROOT / "apps/portal/workflow_kb_corpus_editorial.py").is_file()),
        ("1487-editorial-verify", _gate("scripts/verify_workflow_kb_editorial.py")),
        ("1487-nav-convergence-module", (ROOT / "apps/schools/manager_nav_convergence.py").is_file()),
        ("1487-nav-convergence-verify", _gate("scripts/verify_manager_nav_convergence.py")),
        ("1487-cp-nav-convergence", _ok(
            "apps/schools/manager_nav_convergence.py",
            "build_manager_complete_sidebar_groups",
        )),
        # Batch 1500 — enriched corpus + complete sidebar + platform back-to-top
        ("1500-corpus-enrich", (ROOT / "apps/portal/workflow_kb_corpus_enrich.py").is_file()),
        ("1500-corpus-quality-verify", _gate("scripts/verify_workflow_kb_corpus_quality.py")),
        ("1500-complete-sidebar-partial", (ROOT / "templates/partials/manager_complete_sidebar_nav.html").is_file()),
        ("1500-complete-sidebar-context", (
            _ok("apps/siteconfig/context_processors.py", "MANAGER_COMPLETE_SIDEBAR_NAV")
            and _ok("apps/siteconfig/context_processors.py", "build_manager_complete_sidebar_groups")
        )),
        ("1500-back-to-top-verify", _gate("scripts/verify_platform_back_to_top.py")),
        ("1500-back-to-top-idempotent", _ok(
            "static/js/_pages/components__back_to_top.js",
            "data-rmc-mounted",
        )),
    ]
    # A check is either a bool (a file/substring assertion) or a (verdict, detail)
    # pair from _gate. Skips are counted and NAMED, never folded into the pass
    # count: a ladder that says "142 checks" while seven of them were unrunnable
    # is claiming coverage it does not have.
    failed: list[str] = []
    skipped: list[str] = []
    for cid, result in checks:
        if isinstance(result, tuple):
            verdict, detail = result
            if verdict == FAIL:
                failed.append(f"{cid}: {detail}")
            elif verdict == SKIP:
                skipped.append(f"{cid}: {detail}")
        elif not result:
            failed.append(cid)

    for line in skipped:
        print(f"  SKIP {line}", file=sys.stderr)
    if failed:
        print(f"verify_help_center_tiers: FAIL ({len(failed)})", file=sys.stderr)
        for cid in failed:
            print(f"  - {cid}", file=sys.stderr)
        return 1
    verified = len(checks) - len(skipped)
    suffix = f", {len(skipped)} skipped" if skipped else ""
    print(
        f"verify_help_center_tiers: HELP_CENTER_TIERS_PASS "
        f"({verified} of {len(checks)} checks verified{suffix})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
