"""
In-context guidance for Tenant Studio — answers common questions on the page.

Used by studio_shell to populate info tags, Q&A panels, and enriched mode cards.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.utils.translation import gettext_lazy as _


def _qa(q, a):
    return {"q": q, "a": a}


OVERVIEW_GUIDANCE = {
    "tip": _(
        "Studio is your school setup workbench. Most new schools start in Launch, "
        "then tune Experience (look and feel), Control (features), and Outputs (reports)."
    ),
    "questions": [
        _qa(
            _("Where do I start?"),
            _(
                "Open Launch → Guided onboarding or the checklist. Complete country, "
                "branding, and core settings before inviting staff."
            ),
        ),
        _qa(
            _("Will changes go live immediately?"),
            _(
                "Experience theme changes use Preview then Publish. Launch checklist "
                "items may need admin approval depending on your plan."
            ),
        ),
        _qa(
            _("Who can use Studio?"),
            _(
                "School administrators and staff with settings permissions. Parents and "
                "students never see Studio — only the portals you configure."
            ),
        ),
    ],
}

MODE_GUIDANCE: dict[str, dict[str, Any]] = {
    "experience": {
        "tip": _(
            "Preview every theme change before Publish. Rollback restores the last "
            "published snapshot if something looks wrong on mobile or dark mode."
        ),
        "questions": [
            _qa(
                _("What is Experience mode?"),
                _(
                    "Colors, typography, logos, and portal layout. Changes flow to parent, "
                    "teacher, and student surfaces after you publish."
                ),
            ),
            _qa(
                _("Why do I see contrast warnings?"),
                _(
                    "Low contrast can make text unreadable for some users. Fix warnings "
                    "before publish, or use recommended token pairs from the workbench."
                ),
            ),
        ],
    },
    "automation": {
        "tip": _(
            "Build and test workflows in Workflow center. Use simulation before turning "
            "automation on for real enrollments or fees."
        ),
        "questions": [
            _qa(
                _("What belongs in Automation?"),
                _(
                    "Approvals, notifications, scheduled jobs, and workflow steps — not "
                    "day-to-day grading (that stays in academic modules)."
                ),
            ),
            _qa(
                _("A pane says “explainer only” — what now?"),
                _(
                    "Open Workflow center from the link on that pane. The full builder "
                    "lives there until the visual tools are embedded in Studio."
                ),
            ),
        ],
    },
    "output": {
        "tip": _(
            "Report packs and document templates depend on branding and policy settings. "
            "Finish Launch checklist items if a pack shows as blocked."
        ),
        "questions": [
            _qa(
                _("What are Outputs?"),
                _(
                    "Report cards, transcripts, fee letters, IDs, and exports your school "
                    "prints or shares with families."
                ),
            ),
            _qa(
                _("Why is a report pack unavailable?"),
                _(
                    "Often missing grading scale, academic year, or branding. Check the "
                    "dependency graph pane for the first red item and fix it in Control or Launch."
                ),
            ),
        ],
    },
    "launch": {
        "tip": _(
            "Follow the checklist top to bottom. Health score summarizes blockers; "
            "each pane below answers one part of going live."
        ),
        "questions": [
            _qa(
                _("What does health score mean?"),
                _(
                    "Percent of required setup steps done (country, plan, branding, etc.). "
                    "100% means no known blockers — you can still refine before opening portals."
                ),
            ),
            _qa(
                _("Guided onboarding vs checklist?"),
                _(
                    "Onboarding is a step-by-step wizard; checklist is the full list. Use "
                    "either — completing one updates progress in the other where linked."
                ),
            ),
        ],
    },
    "control": {
        "tip": _(
            "Feature control turns modules on or off per school. Runtime and policy "
            "links open the same settings as the control plane, embedded here for convenience."
        ),
        "questions": [
            _qa(
                _("What is Control mode?"),
                _(
                    "Capabilities, feature flags, metadata, and entitlements that decide "
                    "which menus and tools appear for your roles."
                ),
            ),
            _qa(
                _("I toggled a feature — when does it apply?"),
                _(
                    "Most toggles apply on next page load. Some finance or integration "
                    "features may require a short cache refresh or staff re-login."
                ),
            ),
        ],
    },
}

LAUNCH_PANE_GUIDANCE: dict[str, dict[str, str]] = {
    "overview": {
        "title": _("Launch overview"),
        "body": _(
            "Summary of setup health, registry alignment, and the checklist. Use the "
            "left rail to open each topic."
        ),
    },
    "onboarding": {
        "title": _("Guided onboarding"),
        "body": _(
            "Wizard for first-time setup: school profile, locale, and essentials. Best "
            "path if you are creating a school for the first time on RunMyCampus."
        ),
    },
    "create_school": {
        "title": _("Create school"),
        "body": _(
            "Platform operators use this to register a new school tenant. Tenant admins "
            "usually skip this — your school already exists when you sign in."
        ),
    },
    "plan": {
        "title": _("Select plan"),
        "body": _(
            "Chooses billing plan and entitlements (which modules are included). Changes "
            "may require operator approval."
        ),
    },
    "blueprints": {
        "title": _("Blueprint gallery"),
        "body": _(
            "Starter packs for grading, finance, and workflows. Applying a blueprint "
            "copies recommended defaults — review before publish."
        ),
    },
    "infrastructure": {
        "title": _("School infrastructure"),
        "body": _(
            "Applies a structural template (sections, terms, roles). Preview the template "
            "before apply; rollback is limited once data exists."
        ),
    },
    "branding": {
        "title": _("Import branding"),
        "body": _(
            "Upload logo and colors or import from a file. Feeds Experience mode after save."
        ),
    },
    "migration": {
        "title": _("Migration path"),
        "body": _(
            "Import students and staff from another SIS. Run a trial import first; map "
            "fields in Migration Cloud before cutover."
        ),
    },
    "role_preview": {
        "title": _("Preview by role"),
        "body": _(
            "See what parents, teachers, or admins will see after setup. Use this before "
            "sending invitation emails."
        ),
    },
    "checklist": {
        "title": _("Launch checklist"),
        "body": _(
            "Every required and recommended step in one list. Links jump to the tool "
            "that completes each item."
        ),
    },
}

OUTPUT_PANE_GUIDANCE: dict[str, dict[str, str]] = {
    "dependency": {
        "title": _("Report dependency graph"),
        "body": _(
            "Shows which settings block which reports. Fix upstream items (branding, "
            "grading, year) first."
        ),
    },
    "reports": {
        "title": _("Report library"),
        "body": _(
            "Run and schedule standard reports. Custom layouts may live in Report card builder."
        ),
    },
    "documents": {
        "title": _("Document library"),
        "body": _(
            "Letter templates and PDFs sent to families. Requires settings.manage permission."
        ),
    },
    "builder": {
        "title": _("Report card builder"),
        "body": _(
            "Design report card layouts and columns. Publish when preview matches your "
            "grading policy."
        ),
    },
    "credentials": {
        "title": _("IDs and certificates"),
        "body": _(
            "Student ID cards and certificate templates. Uses branding from Experience."
        ),
    },
    "branding": {
        "title": _("Branding inheritance"),
        "body": _(
            "How report PDFs inherit logos and colors. Overrides are per-template."
        ),
    },
    "policy": {
        "title": _("Policy registry"),
        "body": _(
            "Links report packs to compliance and metadata rules. Operators may need "
            "to align blueprints here."
        ),
    },
}

AUTOMATION_PANE_GUIDANCE: dict[str, dict[str, str]] = {
    "overview": {
        "title": _("Automation overview"),
        "body": _("Health of workflows and links to Workflow center."),
    },
    "workflow": {
        "title": _("Workflow center"),
        "body": _(
            "Primary place to create, edit, and activate flows. Embedded here when your "
            "browser allows; otherwise open in full window."
        ),
    },
}


def get_active_guidance(
    *,
    mode: str | None,
    launch_pane: str | None = None,
    output_pane: str | None = None,
    automation_pane: str | None = None,
) -> dict[str, Any] | None:
    """Return {tip, questions, pane_hint?} for the active Studio surface."""
    if not mode:
        return deepcopy(OVERVIEW_GUIDANCE)

    base = MODE_GUIDANCE.get(mode)
    if not base:
        return None

    out = {
        "tip": base["tip"],
        "questions": list(base["questions"]),
    }

    if mode == "launch" and launch_pane:
        pane = LAUNCH_PANE_GUIDANCE.get(launch_pane)
        if pane:
            out["pane_label"] = pane["title"]
            out["pane_hint"] = pane["body"]
            out["questions"] = [
                _qa(_("What is this pane?"), pane["body"]),
                *out["questions"][:2],
            ]
    elif mode == "output" and output_pane:
        pane = OUTPUT_PANE_GUIDANCE.get(output_pane)
        if pane:
            out["pane_label"] = pane["title"]
            out["pane_hint"] = pane["body"]
            out["questions"] = [
                _qa(_("What is this pane?"), pane["body"]),
                *out["questions"][:2],
            ]
    elif mode == "automation" and automation_pane:
        pane = AUTOMATION_PANE_GUIDANCE.get(automation_pane)
        if pane:
            out["pane_label"] = pane["title"]
            out["pane_hint"] = pane["body"]
            out["questions"] = [
                _qa(_("What is this pane?"), pane["body"]),
                *out["questions"][:2],
            ]

    return out


def enrich_launch_left_rail(items: list[dict]) -> list[dict]:
    enriched = []
    for item in items:
        row = dict(item)
        pane = row.get("pane") or ""
        guide = LAUNCH_PANE_GUIDANCE.get(pane)
        if guide:
            row["info_title"] = str(guide["title"])
            row["info_body"] = str(guide["body"])
        enriched.append(row)
    return enriched


def enrich_modes_for_overview(modes: list[dict]) -> list[dict]:
    enriched = []
    for m in modes:
        row = dict(m)
        mode_id = row.get("id") or ""
        guide = MODE_GUIDANCE.get(mode_id)
        if guide:
            row["guidance_tip"] = str(guide["tip"])
            if guide.get("questions"):
                row["guidance_question"] = str(guide["questions"][0]["q"])
                row["guidance_answer"] = str(guide["questions"][0]["a"])
        enriched.append(row)
    return enriched


def apply_studio_guidance_to_context(context: dict, *, mode: str | None) -> None:
    """Mutate studio_shell context with guidance fields."""
    launch_pane = context.get("launch_pane")
    output_pane = context.get("output_pane")
    automation_pane = context.get("automation_pane")

    context["studio_guidance"] = get_active_guidance(
        mode=mode,
        launch_pane=launch_pane,
        output_pane=output_pane,
        automation_pane=automation_pane,
    )

    modes = context.get("studio_modes") or []
    context["studio_modes"] = enrich_modes_for_overview(modes)

    if context.get("launch_left_rail"):
        context["launch_left_rail"] = enrich_launch_left_rail(
            context["launch_left_rail"]
        )
