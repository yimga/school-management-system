"""RunMyCampus AI Center — governed query, indexing, KB drafts, friction (extends services/ai/)."""

from services.ai_center.audit import emit_ai_center_event
from services.ai_center.contextual_insights import get_contextual_tip
from services.ai_center.friction_analysis import analyze_friction_signals, friction_topics_for_operator
from services.ai_center.indexing import (
    build_platform_index,
    get_feature_evidence,
    get_missing_context_reason,
    index_document,
    search_by_module,
    search_by_role,
    search_by_route,
    search_platform_knowledge,
)
from services.ai_center.kb_generator import (
    generate_faqs_for_module,
    generate_kb_article_from_code_change,
    generate_kb_article_from_route,
    generate_operator_runbook,
    generate_release_note_from_feature,
    generate_tenant_guide,
    propose_faqs_from_feedback,
    propose_help_topics_from_errors,
)
from services.ai_center.ollama_client import OllamaAICenterClient
from services.ai_center.query_service import answer_platform_question

__all__ = [
    "OllamaAICenterClient",
    "analyze_friction_signals",
    "answer_platform_question",
    "build_platform_index",
    "emit_ai_center_event",
    "friction_topics_for_operator",
    "generate_faqs_for_module",
    "generate_kb_article_from_code_change",
    "generate_kb_article_from_route",
    "generate_operator_runbook",
    "generate_release_note_from_feature",
    "generate_tenant_guide",
    "get_contextual_tip",
    "get_feature_evidence",
    "get_missing_context_reason",
    "index_document",
    "propose_faqs_from_feedback",
    "propose_help_topics_from_errors",
    "search_by_module",
    "search_by_role",
    "search_by_route",
    "search_platform_knowledge",
]
