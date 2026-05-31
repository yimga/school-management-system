"""v4.00.94 Wave D — built-in AI actions seeded at AppConfig.ready."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from .ai_actions import AIAction, register_action


register_action(
    AIAction(
        id="summarize",
        label=_("Summarize this page"),
        icon="bi-card-text",
        description=_("Three-bullet summary of the current view."),
        prompt_template=(
            "You are an assistant inside a school management platform. The operator "
            "is viewing the page at {page_path}. Their role is {role}. Below is the "
            "page excerpt:\n\n{page_excerpt}\n\n"
            "Reply with exactly 3 bullet points summarizing what this page does and "
            "what the most likely next action is. No preamble."
        ),
        task_type="admin_copilot",
        order=10,
    )
)

register_action(
    AIAction(
        id="explain",
        label=_("Explain this"),
        icon="bi-info-square",
        description=_("Plain-language explanation of a column / metric / field."),
        prompt_template=(
            "You are a teacher-facing explainer. The operator is at {page_path} and "
            "asked: \"{user_query}\".\n\n"
            "Page context:\n{page_excerpt}\n\n"
            "Answer in 2-3 short sentences, plain English, no jargon. If the question "
            "is ambiguous, name the ambiguity first."
        ),
        task_type="admin_copilot",
        order=20,
    )
)

register_action(
    AIAction(
        id="draft",
        label=_("Draft message"),
        icon="bi-envelope-paper",
        description=_("Draft an email / message from a short brief."),
        prompt_template=(
            "You are drafting a school communication for an operator with role {role}. "
            "Brief: \"{user_query}\".\n\n"
            "Context about the current page:\n{page_excerpt}\n\n"
            "Output a polite, professional draft no longer than 120 words. End with a "
            "single-sentence call-to-action. The human will review before sending."
        ),
        task_type="teacher_comms_draft",
        order=30,
    )
)

register_action(
    AIAction(
        id="translate",
        label=_("Translate this"),
        icon="bi-translate",
        description=_("Translate selected text to the operator's locale."),
        prompt_template=(
            "Translate the text below into the most natural form for an operator in "
            "role {role}. Preserve the meaning and the formality register.\n\n"
            "Text:\n{page_excerpt}"
        ),
        task_type="narrative",
        order=40,
    )
)
