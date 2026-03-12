from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def check_contains(relative_path: str, needle: str, label: str, failures: list[str]) -> None:
    if needle not in read_text(relative_path):
        failures.append(f"{label}: missing `{needle}` in {relative_path}")


def main() -> int:
    failures: list[str] = []

    required_files = [
        "services/ai_gateway.py",
        "services/ai_schemas.py",
        "services/embeddings.py",
        "services/ai_memory.py",
        "apps/portal/views_ai_gateway.py",
        "apps/siteconfig/prompt_registry.py",
        "docs/architecture/ai_orchestration.md",
        "docs/architecture/ai_tiered_ollama.md",
    ]
    for relative_path in required_files:
        if not (ROOT / relative_path).exists():
            failures.append(f"Missing required file: {relative_path}")

    gateway_checks = [
        ("services/ai_gateway.py", "class TaskType", "Gateway task enum"),
        ("services/ai_gateway.py", "def invoke(", "Gateway invoke facade"),
        ("services/ai_gateway.py", "def _cost_class_for_tier(", "Gateway cost-class routing"),
        ("services/ai_gateway.py", "def _call_vllm(", "vLLM adapter"),
        ("services/ai_gateway.py", "def _call_litellm(", "LiteLLM adapter"),
        ("services/ai_gateway.py", "def record_feedback(", "Gateway review-loop feedback"),
        ("services/ai_gateway.py", "response_schema == \"workflow_draft\"", "Workflow schema routing"),
        ("services/ai_gateway.py", "response_schema == \"marketplace_recommend\"", "Marketplace schema routing"),
        ("services/ai_gateway.py", "def _safe_schema_default(", "Structured safe defaults"),
        ("services/ai_gateway.py", "def _payload_contains_pii(", "PII-aware premium guard"),
        ("services/ai_gateway.py", "\"task_type\": task_type", "AI audit task_type field"),
        ("services/ai_gateway.py", "\"latency_ms\": round(latency_ms, 2)", "AI audit latency field"),
        ("services/ai_gateway.py", "\"tenant_id\": str(tenant_id)", "AI audit tenant field"),
        ("services/ai_gateway.py", "\"request_id\": request_id", "AI request id field"),
        ("services/ai_gateway.py", "\"cost_class\": _cost_class_for_tier", "AI cost class field"),
    ]
    for relative_path, needle, label in gateway_checks:
        check_contains(relative_path, needle, label, failures)

    embeddings_checks = [
        ("services/embeddings.py", "class EmbeddingProvider", "Embedding provider interface"),
        ("services/embeddings.py", "class OllamaEmbeddingProvider", "Ollama embedding backend"),
        ("services/embeddings.py", "class OpenAICompatibleEmbeddingProvider", "OpenAI-compatible embedding backend"),
        ("services/embeddings.py", "def get_embedding_provider()", "Embedding router"),
        ("services/embeddings.py", "def embed_batch(", "Batch embedding support"),
    ]
    for relative_path, needle, label in embeddings_checks:
        check_contains(relative_path, needle, label, failures)

    retrieval_checks = [
        ("services/ai_memory.py", "Q(school_id=school_id) | Q(school_id__isnull=True)", "Global + tenant retrieval"),
        ("services/ai_memory.py", "actor_roles", "Role-aware retrieval signature"),
        ("services/ai_memory.py", "staff_only", "Staff visibility guard"),
    ]
    for relative_path, needle, label in retrieval_checks:
        check_contains(relative_path, needle, label, failures)

    endpoint_needles = [
        "path('ai/setup-assistant/'",
        "path('ai/workflow-draft/'",
        "path('ai/policy-explain/'",
        "path('ai/document-classify/'",
        "path('ai/semantic-search/'",
        "path('ai/migration-suggest/'",
        "path('ai/admin-copilot/'",
        "path('ai/theme-recommend/'",
        "path('ai/report-recommend/'",
        "path('ai/design-studio-draft/'",
        "path('ai/dashboard-pack-recommend/'",
        "path('ai/marketplace-recommend/'",
        "path('ai/control-plane-intelligence/'",
        "path('ai/feedback/'",
    ]
    api_urls = read_text("apps/api/urls.py")
    for needle in endpoint_needles:
        if needle not in api_urls:
            failures.append(f"Missing AI endpoint route: {needle}")

    view_checks = [
        "response_schema=\"workflow_draft\"",
        "response_schema=\"policy_explain\"",
        "response_schema=\"doc_classify\"",
        "response_schema=\"migration_mapping\"",
        "response_schema=\"theme_experience\"",
        "response_schema=\"report_recommend\"",
        "response_schema=\"design_studio\"",
        "response_schema=\"dashboard_pack_recommend\"",
        "response_schema=\"marketplace_recommend\"",
        "_retrieval_kwargs(request)",
        "get_prompt_template(\"workflow_draft\"",
        "get_prompt_template(\"document_classify\"",
        "get_prompt_template(\"semantic_search\"",
        "get_prompt_template(\"live_preview\"",
        "get_prompt_template(\"data_quality\"",
        "get_prompt_template(\"control_plane_intelligence\"",
        "def api_ai_feedback(",
        "record_feedback(",
        "\"migration_mapping\",",
    ]
    view_text = read_text("apps/portal/views_ai_gateway.py")
    for needle in view_checks:
        if needle not in view_text:
            failures.append(f"Missing view wiring: {needle}")

    prompt_checks = [
        "\"setup_assistant\"",
        "\"workflow_draft\"",
        "\"policy_explain\"",
        "\"document_classify\"",
        "\"semantic_search\"",
        "\"migration_mapping\"",
        "\"support_suggest\"",
        "\"theme_experience\"",
        "\"feature_control\"",
        "\"report_library\"",
        "\"design_studio\"",
        "\"dashboard_pack_recommend\"",
        "\"marketplace_recommend\"",
        "\"system_config\"",
        "\"live_preview\"",
        "\"data_quality\"",
        "\"control_plane_intelligence\"",
    ]
    prompt_registry = read_text("apps/siteconfig/prompt_registry.py")
    for needle in prompt_checks:
        if needle not in prompt_registry:
            failures.append(f"Missing prompt family in registry: {needle}")

    metric_checks = [
        ("apps/siteconfig/models_ai.py", "cost_class = models.CharField", "AI metric cost class"),
        ("apps/siteconfig/models_ai.py", "review_count = models.PositiveIntegerField", "AI metric review count"),
        ("apps/siteconfig/models_ai.py", "accepted_count = models.PositiveIntegerField", "AI metric accepted count"),
        ("apps/siteconfig/models_ai.py", "manual_correction_count = models.PositiveIntegerField", "AI metric manual correction count"),
        ("apps/siteconfig/admin.py", "register_platform_admin(AIPromptRegistry", "Prompt registry admin registration"),
        ("apps/siteconfig/admin.py", "register_platform_admin(AIEmbeddingStore", "Embedding store admin registration"),
        ("apps/siteconfig/admin.py", "register_platform_admin(AIGatewayMetric", "AI metric admin registration"),
    ]
    for relative_path, needle, label in metric_checks:
        check_contains(relative_path, needle, label, failures)

    doc_checks = [
        ("docs/architecture/AI_ADOPTION_BLUEPRINT_COMPLETE.md", "Historical verification snapshot only", "Historical banner"),
        ("docs/COMMIT_AND_PUSH_PLAN_AI_BLUEPRINT.md", "Historical execution note only", "Commit-plan historical banner"),
        ("docs/RunMyCampus_AI_Architecture_and_Model_Improvement.md", "Scope, phases, and deliverable tracking live only", "Architecture doc no longer claims tracker ownership"),
        ("docs/architecture/ai_orchestration.md", "prompt payload contains detected PII", "PII governance doc"),
        ("docs/architecture/ai_orchestration.md", "metadata-based role/staff visibility filtering", "Retrieval governance doc"),
        ("docs/architecture/ai_orchestration.md", "review_count", "AI review-loop metrics doc"),
        ("docs/architecture/ai_orchestration.md", "/api/ai/feedback/", "AI feedback endpoint doc"),
        ("docs/architecture/ai_tiered_ollama.md", "Open WebUI", "Open WebUI operations guidance"),
    ]
    for relative_path, needle, label in doc_checks:
        check_contains(relative_path, needle, label, failures)

    if failures:
        print("AI blueprint verification failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("AI blueprint verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
