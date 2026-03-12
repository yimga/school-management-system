"""
Prompt registry: resolve prompt templates by key from AIPromptRegistry (DB) with
built-in fallbacks. Used by gateway views for setup, workflow, policy, migration,
document, support, admin, and design/experience features.
"""
from __future__ import annotations

import logging
from typing import Any

from django.db import DatabaseError

logger = logging.getLogger(__name__)

# Built-in templates (fallback when DB has no active approved prompt)
BUILTIN_PROMPTS: dict[str, str] = {
    "setup_assistant": (
        "You are a Setup Studio assistant. Answer concisely and helpfully.\n\n"
        "{context_block}\n\nUser question: {query}\n\n"
        "Provide 3–5 short actionable setup tips or explain the requested config."
    ),
    "workflow_draft": (
        "Generate a workflow definition as JSON only. User request: {query}\n\n"
        "Respond with a single JSON object with keys: name (string), trigger_type (string), "
        "steps (array of {{ action, role, config }}), description (string). No other text."
    ),
    "policy_explain": (
        "You are a policy explainer. Explain or compare policies in plain language.\n\n"
        "{context_block}\n\nUser request: {query}\n\n"
        "Respond with JSON only: {{ \"summary\": \"...\", \"differences\": [], \"warnings\": [] }}. No other text."
    ),
    "document_classify": (
        "Classify this document. Respond with JSON only: "
        "{{ \"category\": \"...\", \"tags\": [\"...\"], \"confidence\": 0.0-1.0 }}.\n\n"
        "Document excerpt: {query}\n\nNo other text."
    ),
    "live_preview": (
        "Explain live preview behaviour for setup, branding, or role previews. User question: {query}\n\n"
        "Respond concisely with what will change, what stays draft-only, and what to verify before launch."
    ),
    "semantic_search": (
        "Use the retrieved platform context to answer the question briefly and concretely.\n\n"
        "Question: {query}\n\nContext: {context_block}\n\n"
        "Respond with a short answer first, then mention the most relevant source object names if available."
    ),
    "migration_mapping": (
        "Suggest field mappings as JSON array only.\n\n"
        "Source schema or sample: {source_fields}\n\n"
        "Target schema: {target_fields}\n\n"
        "Each array item must be {{ \"source_field\", \"target_field\", \"confidence\", \"notes\" }}."
    ),
    "admin_copilot": (
        "You are an admin and configuration assistant. Use the following context to answer.\n\n"
        "{context_block}\n\nQuestion: {query}\n\nAnswer concisely; include links or doc refs if relevant."
    ),
    "support_suggest": (
        "Based on the following context, suggest a support response.\n\n{context_block}\n\n"
        "User message: {query}\n\nProvide a helpful, professional reply."
    ),
    "theme_experience": (
        "Suggest theme or experience improvements. User request: {query}\n\n"
        "Respond with JSON: {{ \"suggestions\": [], \"rationale\": \"...\" }}. No other text."
    ),
    "feature_control": (
        "Explain feature flags and control. User question: {query}\n\n"
        "Respond concisely with what the feature does and when to enable/disable it."
    ),
    "report_library": (
        "Recommend reports from the library. User need: {query}\n\n"
        "Respond with JSON: {{ \"recommendations\": [{{ \"name\", \"description\", \"fit\" }}] }}. No other text."
    ),
    "design_studio": (
        "Suggest design or layout changes. User request: {query}\n\n"
        "Respond with JSON: {{ \"suggestions\": [], \"components\": [] }}. No other text."
    ),
    "dashboard_pack_recommend": (
        "Recommend dashboards or experience packs for: {query}\n\n"
        "Respond with JSON: {{ \"dashboards\": [], \"packs\": [], \"rationale\": \"...\" }}. No other text."
    ),
    "marketplace_recommend": (
        "Recommend marketplace apps or experience packs for: {query}\n\n"
        "Respond with JSON only: {{ \"recommendations\": [{{ \"name\", \"category\", \"fit\", \"rationale\" }}], \"rationale\": \"...\" }}. No other text."
    ),
    "system_config": (
        "Explain system configuration options. User question: {query}\n\n"
        "Answer concisely; do not include secrets or internal URLs."
    ),
    "data_quality": (
        "You are a data quality assistant. Based on the context and the user's question, suggest data quality checks, "
        "validation rules, or remediation steps.\n\nContext: {context_block}\n\nQuestion: {query}\n\n"
        "Provide 3-5 concrete suggestions."
    ),
    "control_plane_intelligence": (
        "You are a control-plane intelligence assistant for platform operators. Use the context to answer concisely. "
        "Provide runbook-style steps or configuration insights where relevant.\n\nContext: {context_block}\n\n"
        "Question: {query}\n\nAnswer:"
    ),
}

OPTIONAL_PROMPT_ERRORS = (AttributeError, DatabaseError, ImportError, TypeError, ValueError)


def get_prompt_template(
    prompt_key: str,
    context: dict[str, Any] | None = None,
) -> str:
    """
    Resolve prompt template for prompt_key. If AIPromptRegistry has an active approved
    entry for that key, use its template_body (formatted with context). Otherwise
    use BUILTIN_PROMPTS. context is used for {query}, {context_block}, etc.
    """
    context = context or {}
    query = context.get("query", context.get("user_query", ""))
    context_block = context.get("context_block", context.get("context", ""))
    try:
        from apps.siteconfig.models import AIPromptRegistry
        rec = AIPromptRegistry.objects.filter(
            prompt_key=prompt_key,
            is_active=True,
            review_status="approved",
        ).first()
        if rec and rec.template_body:
            body = rec.template_body
            # Simple placeholder substitution
            body = body.replace("{query}", str(query))
            body = body.replace("{user_query}", str(query))
            body = body.replace("{context_block}", str(context_block))
            body = body.replace("{context}", str(context_block))
            for k, v in context.items():
                body = body.replace("{" + k + "}", str(v))
            return body
    except OPTIONAL_PROMPT_ERRORS as e:
        logger.debug("Prompt registry lookup failed for %s: %s", prompt_key, e)
    template = BUILTIN_PROMPTS.get(prompt_key)
    if not template:
        return ""  # callers may pass empty; they should provide fallback
    format_kw = {"query": query, "context_block": context_block, "context": context_block}
    for k, v in context.items():
        format_kw.setdefault(k, v)
    try:
        return template.format(**format_kw)
    except KeyError:
        return template.format(query=query, context_block=context_block)
