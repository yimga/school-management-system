#!/usr/bin/env python
"""Generate translation-request packets for the 4 African locales.

12-pillar P11 polish (v3.23.9 2026-05-17). For locales the codebase
intentionally does NOT machine-translate (yo / ha / sw / pid — see
``docs/i18n/TRANSLATION_REQUEST_PACKETS.md``), this script produces a
Markdown packet per locale: the 111-string source set + brand-voice
notes + locale-specific notes + sign-off section. One row per string;
translator fills the right-hand column.

Usage:
    python scripts/generate_translation_request_packets.py
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "docs" / "i18n" / "translation_requests"

# The 111 high-leverage marketing strings (same set es/pt-br already cover).
# Pulled from the existing `locale/es/LC_MESSAGES/django.po` translated entries
# — see `scripts/seed_french_marketing_translations.py` for the canonical list.
SOURCE_MSGIDS: list[str] = [
    "Main navigation", "Toggle navigation", "Header primary action: Book demo",
    "Platform status", "All systems operational", "Login", "Book demo",
    "Book a demo", "Book a demo →", "Pricing", "Why switch", "More",
    "Choose language", "Run", "Teach", "Pay", "Communicate", "Grow",
    "was: Platform", "Solutions", "Company", "Demo",
    "Tuesday · Cedar Ridge Academy",
    "One quiet system behind admissions, classrooms, fees, and the message you send a parent at 8:14 a.m.",
    "See it live", "Platform overview", "Quick proof points",
    "to fully switch from legacy SIS", "Multi-tenant, region-aware",
    "Your school's hour. Your school's currency. Your school's calendar.",
    "Run on local time, in the right language, with the academic structure your country actually uses. No forks. No regional plug-ins. One platform that bends to each campus.",
    "Localisation surfaces", "180 currencies", "29 languages",
    "All major SIS imports", "FERPA · GDPR · POPIA aligned",
    "Offline-first where the network drops", "Platform scale",
    "Coming from somewhere else?",
    "We've moved schools off PowerSchool, Blackbaud, Infinite Campus, and a folder full of spreadsheets.",
    "Migration timeline", "Map your data", "Dry-run", "Cutover",
    "How a migration actually goes →",
    "Records, enrollment context, and learner profile continuity.",
    "Pipeline from enquiry through enrollment with one thread.",
    "Daily presence and formative marks tied to the same learner record.",
    "Invoices, receipts, and guardian visibility without spreadsheet drift.",
    "Assessment, transcripts, and reporting on one academic spine.",
    "Three plans, total transparency.",
    "Starter", "Growth", "Enterprise", "Custom", "Add-ons",
    "Migration Cloud",
    "Phased cutover, dry-run sandbox, dedicated migration lead.",
    "Marketplace apps", "Governed partner tiles — activate per campus.",
    "Premium support", "Enterprise SLA, operator command center access.",
    "FAQ", "Common questions", "Trust center",
    "Posture, certifications, and incident transparency.",
    "Request security packet", "Implementation assurance",
    "Contact sales →",
    "We document posture honestly — certifications and live PSP rails only when externally verified.",
    "Incident response", "Your name", "Work email", "School name",
    "Phone", "Country", "School type", "Number of students", "Message",
    "Send", "Get a 20-minute walkthrough.", "Your Tuesday.",
    "Read the full Tuesday for the head →", "Five roles. Five Tuesdays.",
    "What changes for everyone in the building",
    "Head of school", "Bursar", "Teacher", "Parent", "IT lead",
    "Talk to us", "All solutions →", "Talk to a human →",
    "Less software. More school.",
    "A campus advisor — editorial illustration.",
    "Product", "Why switch?", "Resources", "Help center",
    "Release notes", "Developers", "Status", "Privacy", "Terms", "Contact",
    "Between the bells · Sent by RunMyCampus",
    "Page not found", "That page isn't here.",
    "The link may be old, scoped to a different host, or missing required context. Try one of the stable entry points below.",
    "Go to homepage", "Contact support",
]


SURFACE_HINTS: dict[str, str] = {
    "Main navigation": "nav", "Toggle navigation": "nav", "Login": "nav-cta",
    "Pricing": "nav", "Why switch": "nav", "More": "nav",
    "Choose language": "nav",
    "Run": "verb-nav", "Teach": "verb-nav", "Pay": "verb-nav",
    "Communicate": "verb-nav", "Grow": "verb-nav", "was: Platform": "verb-nav",
    "Solutions": "nav", "Company": "nav", "Demo": "nav",
    "Book demo": "cta", "Book a demo": "cta", "Book a demo →": "cta",
    "See it live": "cta", "Send": "cta", "Talk to us": "cta",
    "Talk to a human →": "cta", "Contact sales →": "cta",
    "Request security packet": "cta", "Read the full Tuesday for the head →": "cta",
    "How a migration actually goes →": "cta", "All solutions →": "cta",
    "Get a 20-minute walkthrough.": "cta-supporting",
    "Tuesday · Cedar Ridge Academy": "hero-eyebrow",
    "Less software. More school.": "tagline",
    "Platform overview": "section-heading", "Quick proof points": "section-heading",
    "Platform scale": "section-heading", "Migration timeline": "section-heading",
    "Coming from somewhere else?": "section-heading",
    "Three plans, total transparency.": "section-heading",
    "Add-ons": "section-heading", "Trust center": "section-heading",
    "FAQ": "section-heading", "Common questions": "section-heading",
    "Implementation assurance": "section-heading",
    "Incident response": "section-heading",
    "Localisation surfaces": "section-heading",
    "Five roles. Five Tuesdays.": "section-heading",
    "What changes for everyone in the building": "section-heading",
    "Multi-tenant, region-aware": "section-heading",
    "Starter": "pricing-tier", "Growth": "pricing-tier",
    "Enterprise": "pricing-tier", "Custom": "pricing-tier",
    "Migration Cloud": "addon-name", "Marketplace apps": "addon-name",
    "Premium support": "addon-name",
    "Head of school": "persona", "Bursar": "persona", "Teacher": "persona",
    "Parent": "persona", "IT lead": "persona",
    "Page not found": "404", "That page isn't here.": "404",
    "Go to homepage": "404", "Contact support": "404",
    "The link may be old, scoped to a different host, or missing required context. Try one of the stable entry points below.": "404",
    "Product": "footer", "Why switch?": "footer", "Resources": "footer",
    "Help center": "footer", "Release notes": "footer",
    "Developers": "footer", "Status": "footer", "Privacy": "footer",
    "Terms": "footer", "Contact": "footer",
    "Between the bells · Sent by RunMyCampus": "email-signature",
    "Your name": "form-field", "Work email": "form-field",
    "School name": "form-field", "Phone": "form-field",
    "Country": "form-field", "School type": "form-field",
    "Number of students": "form-field", "Message": "form-field",
    "Platform status": "status-badge",
    "All systems operational": "status-badge",
    "Header primary action: Book demo": "a11y-aria",
    "180 currencies": "proof-point", "29 languages": "proof-point",
    "All major SIS imports": "proof-point",
    "FERPA · GDPR · POPIA aligned": "proof-point",
    "Offline-first where the network drops": "proof-point",
    "to fully switch from legacy SIS": "proof-point",
    "Your school's hour. Your school's currency. Your school's calendar.": "section-lede",
    "Run on local time, in the right language, with the academic structure your country actually uses. No forks. No regional plug-ins. One platform that bends to each campus.": "section-body",
    "We've moved schools off PowerSchool, Blackbaud, Infinite Campus, and a folder full of spreadsheets.": "section-body",
    "We document posture honestly — certifications and live PSP rails only when externally verified.": "section-body",
    "One quiet system behind admissions, classrooms, fees, and the message you send a parent at 8:14 a.m.": "hero-tagline",
    "Map your data": "migration-step", "Dry-run": "migration-step",
    "Cutover": "migration-step",
    "Posture, certifications, and incident transparency.": "section-body",
    "Phased cutover, dry-run sandbox, dedicated migration lead.": "addon-body",
    "Governed partner tiles — activate per campus.": "addon-body",
    "Enterprise SLA, operator command center access.": "addon-body",
    "Records, enrollment context, and learner profile continuity.": "verb-detail",
    "Pipeline from enquiry through enrollment with one thread.": "verb-detail",
    "Daily presence and formative marks tied to the same learner record.": "verb-detail",
    "Invoices, receipts, and guardian visibility without spreadsheet drift.": "verb-detail",
    "Assessment, transcripts, and reporting on one academic spine.": "verb-detail",
    "Your Tuesday.": "section-heading",
    "A campus advisor — editorial illustration.": "alt-text",
}


def surface(mid: str) -> str:
    return SURFACE_HINTS.get(mid, "body")


LOCALES = [
    (
        "yo",
        "Yoruba",
        "West Africa private schools, Nigeria primary corridor.",
        "Yoruba uses tonal diacritics that are load-bearing for meaning; please supply them. Honorifics for parents (Iya / Baba) are appropriate in parent-facing copy; RunMyCampus uses formal-respectful tone.",
    ),
    (
        "ha",
        "Hausa",
        "West Africa private schools, Nigeria / Niger corridor.",
        "Hausa marketing copy commonly uses Boko (Latin) script. School-domain vocabulary borrows heavily from English (makaranta = school is native; sakandare = secondary is borrowed). Prefer native terms where natural.",
    ),
    (
        "sw",
        "Swahili",
        "East Africa private schools, Kenya / Tanzania corridor (Kiswahili sanifu / standard Swahili).",
        "Use standard Swahili (Kiswahili sanifu) appropriate for both Kenyan and Tanzanian markets. School-domain native terms are well-developed (shule = school, mwalimu = teacher, mzazi = parent, mwanafunzi = student). Plural noun-class prefixes m-/wa- for people, ki-/vi- for things.",
    ),
    (
        "pid",
        "Nigerian Pidgin",
        "Pan-Nigeria operator-facing copy.",
        "No fully standardized orthography exists. Use a register suitable for operator dashboards and parent-facing messaging — closer to written Pidgin in major Nigerian newspapers than to street usage. Where a concept has no Pidgin term, the English noun is acceptable if it would be used naturally in conversation.",
    ),
]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for code, language, context, notes in LOCALES:
        path = OUT_DIR / f"{code}.md"
        lines: list[str] = []
        lines.append(f"# Translation request packet: {language} (`{code}`)")
        lines.append("")
        lines.append(f"**Target market:** {context}")
        lines.append("")
        lines.append(
            f"**Source language:** English (`en`)  ·  **Target locale:** `{code}`  ·  **Strings to translate:** {len(SOURCE_MSGIDS)}"
        )
        lines.append("")
        lines.append(
            "**Brand voice:** RunMyCampus marketing copy is editorial / quiet-luxury — short declarative sentences; school as honored institution; admin-facing tone is competent and reassuring; parent-facing tone is direct and warm. See [MARKETING_VOICE.md](../../MARKETING_VOICE.md) for the canonical voice guide."
        )
        lines.append("")
        lines.append(f"**Locale-specific notes:** {notes}")
        lines.append("")
        lines.append("## Instructions for the translator")
        lines.append("")
        lines.append(
            "1. Fill in the **Translation** column for each row below."
        )
        lines.append(
            "2. Where you cannot produce a natural translation (e.g. a domain-specific English term that has no good local equivalent and is commonly used by the audience untranslated), write the English term in the cell with a leading asterisk: `*English term`."
        )
        lines.append(
            "3. If the source string contains a placeholder like `%(name)s` or `{count}`, keep it **byte-identical** in the translation; only the surrounding words change."
        )
        lines.append("4. Sign and date the bottom of this packet.")
        lines.append(
            f"5. Hand the filled packet back to the operator. They will copy translations into `locale/{code}/LC_MESSAGES/django.po` and run `python manage.py i18n_review_status --mark-reviewed {code} --reviewer \"<your-name>\"`."
        )
        lines.append("")
        lines.append("## String table")
        lines.append("")
        lines.append(
            f"| # | Surface | English (source) | Translation ({language}) |"
        )
        lines.append("|---|---|---|---|")
        for n, mid in enumerate(SOURCE_MSGIDS, 1):
            safe_mid = mid.replace("|", "\\|")
            lines.append(f"| {n} | `{surface(mid)}` | {safe_mid} | _—_ |")
        lines.append("")
        lines.append("## Sign-off")
        lines.append("")
        lines.append("- **Translator name:** _—_")
        lines.append("- **Date completed:** _—_")
        lines.append("- **Native-speaker affirmation (Y/N):** _—_")
        lines.append(
            "- **Notes for the operator** (terms left in English, ambiguities, queries): _—_"
        )
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(
            f"Once filled, this packet maps 1:1 into `locale/{code}/LC_MESSAGES/django.po`. Operator runs `python manage.py sync_i18n_catalog --compile` to regenerate `.mo`."
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)} ({len(SOURCE_MSGIDS)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
