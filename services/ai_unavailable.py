"""User-visible payloads when live AI is required but unreachable."""

from __future__ import annotations

from services.ai_schemas import validate_guided_assistant


def _operator_recovery_detail() -> str:
    from services.ai_deployment_posture import is_litellm_configured, normalize_deployment_profile

    profile = normalize_deployment_profile()
    if profile == "online":
        if is_litellm_configured():
            return (
                "On Render (online profile): verify LITELLM_PROXY_URL, LITELLM_API_KEY, "
                "LITELLM_MODEL, and outbound HTTPS from the dyno. "
                "Run `python scripts/verify_render_online_ai_posture.py` in the repo."
            )
        return (
            "On Render (online profile): set LITELLM_PROXY_URL and LITELLM_API_KEY for SaaS live AI, "
            "or operate a LAN hub with RMC_DEPLOYMENT_PROFILE=edge and Ollama. "
            "See docs/AI_DEPLOYMENT_POSTURE.md."
        )
    if profile == "hybrid":
        return (
            "Hybrid profile: verify LiteLLM on Render and/or Ollama on the hub per "
            "docs/LOCAL_HUB_MODE.md and docs/AI_DEPLOYMENT_POSTURE.md."
        )
    return (
        "On the application server (edge/hub): start Ollama (`ollama serve`), pull the configured model, "
        "then run `python scripts/verify_ollama_live.py --strict --invoke`."
    )


def _reference_docs() -> list[str]:
    refs = ["docs/AI_DEPLOYMENT_POSTURE.md"]
    from services.ai_deployment_posture import normalize_deployment_profile

    if normalize_deployment_profile() in {"edge", "hybrid"}:
        refs.append("docs/OLLAMA_OPERATIONS_AND_UPDATES.md")
    else:
        refs.append("docs/OPERATOR_OLLAMA_AND_RENDER.md")
    return refs


def build_ollama_unavailable_guided(*, user_query: str = "") -> dict[str, object]:
    """
    Structured guided_assistant response when OLLAMA_REQUIRE_LIVE is on and no model answered.

    Avoids misleading template hints from rules fallback (the \"weird answer\" UX).
    """
    q = (user_query or "").strip()
    summary = (
        "Live AI is unavailable right now. Your question was not answered by a language model. "
        "Please try again shortly or contact your school platform administrator."
    )
    if q:
        summary += f"\n\nYour question: {q[:500]}"
    return validate_guided_assistant(
        {
            "summary": summary,
            "actions": [
                {
                    "title": "For operators",
                    "detail": _operator_recovery_detail(),
                },
                {
                    "title": "For staff",
                    "detail": (
                        "School offline mode (queued attendance/grades) still works without AI. "
                        "Live assistants need connectivity to your school server (Render or LAN hub)."
                    ),
                },
            ],
            "cautions": [
                "This is not product guidance — do not act on template fallback text when live AI is down.",
            ],
            "references": _reference_docs(),
        }
    )


def ollama_unavailable_message() -> str:
    from services.ai_deployment_posture import normalize_deployment_profile

    profile = normalize_deployment_profile()
    if profile == "online":
        return (
            "Live AI is unavailable. The platform could not reach the configured cloud AI proxy. "
            "Contact your administrator or try again later."
        )
    return (
        "Live AI is unavailable. The platform could not reach the inference server "
        "(cloud or Ollama). Contact your administrator or try again later."
    )
