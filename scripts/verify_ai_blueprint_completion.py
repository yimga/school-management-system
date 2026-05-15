from __future__ import annotations

"""
AI blueprint structural gate (gateway, embeddings, portal views, prompts, metrics, docs).

Batch 40 §11.4: settings/runtime first-class secret anchors + hardened check_contains
(no uncaught FileNotFoundError when a required file is absent).

[--base REPO_ROOT] scopes all paths and scans to the given repository root
(default: directory containing this script's parent).

Run (from repo root):
  python scripts/verify_ai_blueprint_completion.py
"""

import argparse
from functools import lru_cache
from pathlib import Path
import subprocess
import sys

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT

FORBIDDEN_CLOUD_AI_SDK_TOKENS = (
    "google.generativeai",
    "generativelanguage.googleapis.com",
    "anthropic",
    "openai.OpenAI(",
    "from openai import OpenAI",
)
ALLOWED_CLOUD_AI_SDK_PATHS = {
    "services/ai_gateway.py",
}


@lru_cache(maxsize=1)
def _tracked_file_relpaths(root: Path) -> frozenset[str] | None:
    """Prefer tracked files so local scratch trees do not create false failures."""
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return frozenset(line.strip() for line in proc.stdout.splitlines() if line.strip())


def _iter_python_files(scan_root: Path, repo_root: Path):
    tracked = _tracked_file_relpaths(repo_root)
    if tracked is None:
        yield from scan_root.rglob("*.py")
        return

    prefix = scan_root.relative_to(repo_root).as_posix().rstrip("/") + "/"
    for relpath in sorted(path for path in tracked if path.startswith(prefix) and path.endswith(".py")):
        path = repo_root / relpath
        if path.is_file():
            yield path


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def check_contains(
    root: Path,
    relative_path: str,
    needle: str,
    label: str,
    failures: list[str],
) -> None:
    path = root / relative_path
    if not path.is_file():
        failures.append(f"{label}: missing file {relative_path}")
        return
    if needle not in path.read_text(encoding="utf-8"):
        failures.append(f"{label}: missing `{needle}` in {relative_path}")


def check_forbidden_cloud_ai_sdk_usage(root: Path, failures: list[str]) -> None:
    scan_roots = (root / "apps", root / "services")
    for scan_root in scan_roots:
        if not scan_root.is_dir():
            continue
        for path in _iter_python_files(scan_root, root):
            rel = path.relative_to(root)
            if "tests" in rel.parts:
                continue
            rel_posix = rel.as_posix()
            if rel_posix in ALLOWED_CLOUD_AI_SDK_PATHS:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in FORBIDDEN_CLOUD_AI_SDK_TOKENS:
                if needle in text:
                    failures.append(
                        f"Forbidden cloud AI SDK usage in {rel}: {needle}"
                    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI blueprint structural gate.")
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root (default: directory containing this script's parent).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_ai_blueprint_completion: {exc}", file=sys.stderr)
        return 1

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
        if not (root / relative_path).exists():
            failures.append(f"Missing required file: {relative_path}")

    gateway_checks = [
        ("services/ai_gateway.py", "class TaskType", "Gateway task enum"),
        ("services/ai_gateway.py", "def invoke(", "Gateway invoke facade"),
        (
            "services/ai_gateway.py",
            "AI_GATEWAY_ENABLED",
            "Gateway kill-switch enforcement",
        ),
        (
            "services/ai_gateway.py",
            "def _cost_class_for_tier(",
            "Gateway cost-class routing",
        ),
        ("services/ai_gateway.py", "def _call_vllm(", "vLLM adapter"),
        ("services/ai_gateway.py", "def _call_litellm(", "LiteLLM adapter"),
        (
            "services/ai_gateway.py",
            "def record_feedback(",
            "Gateway review-loop feedback",
        ),
        (
            "services/ai_gateway.py",
            'response_schema == "workflow_draft"',
            "Workflow schema routing",
        ),
        (
            "services/ai_gateway.py",
            'response_schema == "marketplace_recommend"',
            "Marketplace schema routing",
        ),
        (
            "services/ai_gateway.py",
            "def _safe_schema_default(",
            "Structured safe defaults",
        ),
        (
            "services/ai_gateway.py",
            "def _payload_contains_pii(",
            "PII-aware premium guard",
        ),
        (
            "services/ai_gateway.py",
            '"task_type": task_type',
            "AI audit task_type field",
        ),
        (
            "services/ai_gateway.py",
            '"latency_ms": round(latency_ms, 2)',
            "AI audit latency field",
        ),
        (
            "services/ai_gateway.py",
            '"tenant_id": str(tenant_id)',
            "AI audit tenant field",
        ),
        ("services/ai_gateway.py", '"request_id": request_id', "AI request id field"),
        (
            "services/ai_gateway.py",
            '"cost_class": _cost_class_for_tier',
            "AI cost class field",
        ),
    ]
    for relative_path, needle, label in gateway_checks:
        check_contains(root, relative_path, needle, label, failures)

    embeddings_checks = [
        (
            "services/embeddings.py",
            "class EmbeddingProvider",
            "Embedding provider interface",
        ),
        (
            "services/embeddings.py",
            "class OllamaEmbeddingProvider",
            "Ollama embedding backend",
        ),
        (
            "services/embeddings.py",
            "class OpenAICompatibleEmbeddingProvider",
            "OpenAI-compatible embedding backend",
        ),
        ("services/embeddings.py", "def get_embedding_provider()", "Embedding router"),
        ("services/embeddings.py", "def embed_batch(", "Batch embedding support"),
    ]
    for relative_path, needle, label in embeddings_checks:
        check_contains(root, relative_path, needle, label, failures)

    retrieval_checks = [
        (
            "services/ai_memory.py",
            "Q(school_id=school_id) | Q(school_id__isnull=True)",
            "Global + tenant retrieval",
        ),
        ("services/ai_memory.py", "actor_roles", "Role-aware retrieval signature"),
        ("services/ai_memory.py", "staff_only", "Staff visibility guard"),
    ]
    for relative_path, needle, label in retrieval_checks:
        check_contains(root, relative_path, needle, label, failures)

    endpoint_needles = [
        "ai/setup-assistant/",
        "ai/workflow-draft/",
        "ai/policy-explain/",
        "ai/document-classify/",
        "ai/semantic-search/",
        "ai/migration-suggest/",
        "ai/admin-copilot/",
        "ai/theme-recommend/",
        "ai/report-recommend/",
        "ai/design-studio-draft/",
        "ai/dashboard-pack-recommend/",
        "ai/marketplace-recommend/",
        "ai/control-plane-intelligence/",
        "ai/feedback/",
    ]
    urls_path = root / "apps" / "api" / "urls.py"
    if not urls_path.is_file():
        failures.append("Missing required file: apps/api/urls.py")
    else:
        api_urls = urls_path.read_text(encoding="utf-8")
        for needle in endpoint_needles:
            if needle not in api_urls:
                failures.append(f"Missing AI endpoint route: {needle}")

    view_checks = [
        'response_schema="workflow_draft"',
        'response_schema="policy_explain"',
        'response_schema="doc_classify"',
        'response_schema="migration_mapping"',
        'response_schema="theme_experience"',
        'response_schema="report_recommend"',
        'response_schema="design_studio"',
        'response_schema="dashboard_pack_recommend"',
        'response_schema="marketplace_recommend"',
        "_retrieval_kwargs(request)",
        'get_prompt_template("workflow_draft"',
        'get_prompt_template("document_classify"',
        '"semantic_search"',
        'get_prompt_template("live_preview"',
        '"data_quality"',
        '"control_plane_intelligence"',
        "def api_ai_feedback(",
        "record_feedback(",
        '"migration_mapping",',
    ]
    view_path = root / "apps" / "portal" / "views_ai_gateway.py"
    if not view_path.is_file():
        failures.append("Missing required file: apps/portal/views_ai_gateway.py")
    else:
        view_text = view_path.read_text(encoding="utf-8")
        for needle in view_checks:
            if needle not in view_text:
                failures.append(f"Missing view wiring: {needle}")

    prompt_checks = [
        '"setup_assistant"',
        '"workflow_draft"',
        '"policy_explain"',
        '"document_classify"',
        '"semantic_search"',
        '"migration_mapping"',
        '"support_suggest"',
        '"theme_experience"',
        '"feature_control"',
        '"report_library"',
        '"design_studio"',
        '"dashboard_pack_recommend"',
        '"marketplace_recommend"',
        '"system_config"',
        '"live_preview"',
        '"data_quality"',
        '"control_plane_intelligence"',
    ]
    pr_path = root / "apps" / "siteconfig" / "prompt_registry.py"
    if not pr_path.is_file():
        failures.append("Missing required file: apps/siteconfig/prompt_registry.py")
    else:
        prompt_registry = pr_path.read_text(encoding="utf-8")
        for needle in prompt_checks:
            if needle not in prompt_registry:
                failures.append(f"Missing prompt family in registry: {needle}")

    metric_checks = [
        (
            "apps/siteconfig/models_ai.py",
            "cost_class = models.CharField",
            "AI metric cost class",
        ),
        (
            "apps/siteconfig/models_ai.py",
            "review_count = models.PositiveIntegerField",
            "AI metric review count",
        ),
        (
            "apps/siteconfig/models_ai.py",
            "accepted_count = models.PositiveIntegerField",
            "AI metric accepted count",
        ),
        (
            "apps/siteconfig/models_ai.py",
            "manual_correction_count = models.PositiveIntegerField",
            "AI metric manual correction count",
        ),
        (
            "apps/siteconfig/admin.py",
            "register_platform_admin(AIPromptRegistry",
            "Prompt registry admin registration",
        ),
        (
            "apps/siteconfig/admin.py",
            "register_platform_admin(AIEmbeddingStore",
            "Embedding store admin registration",
        ),
        (
            "apps/siteconfig/admin.py",
            "register_platform_admin(AIGatewayMetric",
            "AI metric admin registration",
        ),
    ]
    for relative_path, needle, label in metric_checks:
        check_contains(root, relative_path, needle, label, failures)

    gateway_discipline_checks = [
        (
            "config/settings.py",
            "AI_GATEWAY_ENABLED",
            "Settings AI gateway feature flag",
        ),
        (
            "config/settings.py",
            "services.ai_gateway",
            "Settings documents single AI gateway entrypoint",
        ),
        (
            "apps/platform_runtime/models.py",
            "ai_provider_api_key = models.CharField",
            "RuntimeDefaults first-class AI provider API key column",
        ),
    ]
    for relative_path, needle, label in gateway_discipline_checks:
        check_contains(root, relative_path, needle, label, failures)

    doc_checks = [
        (
            "docs/architecture/AI_ADOPTION_BLUEPRINT_COMPLETE.md",
            "Historical verification snapshot only",
            "Historical banner",
        ),
        (
            "docs/COMMIT_AND_PUSH_PLAN_AI_BLUEPRINT.md",
            "Historical execution note only",
            "Commit-plan historical banner",
        ),
        (
            "docs/RunMyCampus_AI_Architecture_and_Model_Improvement.md",
            "Scope, phases, and deliverable tracking live only",
            "Architecture doc no longer claims tracker ownership",
        ),
        (
            "docs/architecture/ai_orchestration.md",
            "prompt payload contains detected PII",
            "PII governance doc",
        ),
        (
            "docs/architecture/ai_orchestration.md",
            "metadata-based role/staff visibility filtering",
            "Retrieval governance doc",
        ),
        (
            "docs/architecture/ai_orchestration.md",
            "review_count",
            "AI review-loop metrics doc",
        ),
        (
            "docs/architecture/ai_orchestration.md",
            "/api/ai/feedback/",
            "AI feedback endpoint doc",
        ),
        (
            "docs/architecture/ai_tiered_ollama.md",
            "Open WebUI",
            "Open WebUI operations guidance",
        ),
    ]
    for relative_path, needle, label in doc_checks:
        check_contains(root, relative_path, needle, label, failures)

    threat_checks = [
        (
            "docs/THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md",
            "scripts/verify_ai_blueprint_completion.py",
            "Threat model documents blueprint wiring gate",
        ),
        (
            "docs/THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md",
            "No parallel stacks",
            "Threat model: single-gateway discipline",
        ),
        (
            "docs/THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md",
            "services/inference.py",
            "Threat model: inference tier / data-class gating pointer",
        ),
        (
            "docs/THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md",
            "AI_GATEWAY_ENABLED",
            "Threat model: gateway kill-switch ops",
        ),
    ]
    for relative_path, needle, label in threat_checks:
        check_contains(root, relative_path, needle, label, failures)

    check_forbidden_cloud_ai_sdk_usage(root, failures)

    if failures:
        print("AI blueprint verification failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("AI blueprint verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
