"""
Regional visual asset matrix for public marketing (VISUAL-ENGINE-10X).

Maps ISO country codes to loop variants and APM icon keys. Used by
``marketing_media_context`` and ``{% marketing_asset %}`` template tags.
"""
from __future__ import annotations

from typing import Any

# Markets where marketing emphasizes passive / phone-ban campus tracking copy.
PHONE_BAN_COUNTRIES: frozenset[str] = frozenset({
    "FR",  # common phone restrictions in schools — illustrative routing
})

# Country → sovereign loop bucket (files under static/marketing/video/loops/).
_COUNTRY_LOOP_BUCKET: dict[str, str] = {
    "US": "sovereign_us",
    "CA": "sovereign_us",
    "GB": "sovereign_eu",
    "IE": "sovereign_eu",
    "SA": "sovereign_mena",
    "AE": "sovereign_mena",
    "NG": "sovereign_ssa",
    "KE": "sovereign_ssa",
    "GH": "sovereign_ssa",
    "IN": "sovereign_apac",
    "ID": "sovereign_apac",
    "BR": "sovereign_latam",
    "MX": "sovereign_latam",
}

LOOP_BUCKETS: tuple[str, ...] = (
    "sovereign_default",
    "sovereign_us",
    "sovereign_eu",
    "sovereign_mena",
    "sovereign_ssa",
    "sovereign_apac",
    "sovereign_latam",
)

# Base paths relative to static/ (no leading static/).
VISUAL_ASSET_MATRIX: dict[str, dict[str, str]] = {
    bucket: {
        "sovereign_hero_loop_mp4": f"marketing/video/loops/{bucket}.mp4",
        "sovereign_hero_loop_webm": f"marketing/video/loops/{bucket}.webm",
        "sovereign_hero_poster": f"marketing/img/posters/{bucket}.svg",
        "transit_vector": "images/marketing/platform-offline-sync-console.svg",
    }
    for bucket in LOOP_BUCKETS
}

# Page slug → required manifest keys (Tier S + A).
PAGE_MEDIA_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "home": ("sovereign_hero_loop_mp4", "split_ledger_viz", "transit_viz", "gradebook_viz"),
    "pricing": ("split_ledger_viz", "apm_strip"),
    "platform-fees-payments": ("split_ledger_viz", "apm_strip"),
    "platform-offline-first": ("transit_viz", "sovereign_hero_loop_mp4"),
    "platform-grading-report-cards": ("gradebook_viz",),
    "platform-admissions": ("admissions_flow_mp4",),
    "platform-security": ("transit_vector",),
}

# Marketing sandbox wizard module keys → setup studio step keys (subset).
SANDBOX_MODULE_TO_SETUP_STEP: dict[str, str] = {
    "institution_basics": "institution_basics",
    "plan_choice": "plan_choice",
    "blueprint": "blueprint",
    "branding": "branding",
    "starter_stack": "starter_stack",
    "data_path": "data_path",
    "finance": "starter_stack",
    "offline": "starter_stack",
    "communications": "starter_stack",
}

VALID_SANDBOX_MODULES: frozenset[str] = frozenset(SANDBOX_MODULE_TO_SETUP_STEP.keys())

# Zero-hardcoded marketing copy registry (RUNMYCAMPUS-SURGICAL-REFIT).
# Country keys are ISO2; marketing_local may override headline/regulatory at render time.
MARKETING_COPY_REGISTRY: dict[str, dict[str, str]] = {
    "US": {
        "txt_hero_headline": "The Sovereign Operating System for Modern Districts",
        "txt_governing_body": "Department of Education Integration",
        "txt_operational_claim": "Ambient, Phone-Free Campus Tracking Mechanics",
        "txt_clinical_headline": "Split-Gateway Ledger Flow",
        "txt_clinical_lead": "Real-time payment distributions and automated electronic invoicing.",
        "txt_hero_subheadline": "One control plane for admissions, fees, and the message you send at 8:14 a.m.",
        "txt_academics_headline": "Gradebooks that morph to your framework.",
        "txt_academics_lead": "Switch illustrative frameworks — US letters, IB, Cambridge, or local scales — without re-entering history.",
        "txt_edge_headline": "Network drop simulator — phone-ban immune attendance.",
        "txt_edge_lead": "Toggle from fiber to total blackout; attendance still logs via QR sweeps and passive RFID.",
        "txt_compliance_headline": "One-click auditor gateway with PII masking.",
        "txt_compliance_lead": "Time-bounded inspector links, geo-fenced access, and immutable audit signatures.",
        "txt_pricing_headline": "Entitlement calculator — transparent tiers in your currency.",
        "txt_pricing_lead": "Select transport, grading, comms, and billing modules; see indicative per-student pricing.",
    },
    "SA": {
        "txt_hero_headline": "نظام التشغيل السيادي للمؤسسات التعليمية الحديثة",
        "txt_governing_body": "بوابة التكامل مع وزارة التعليم (MoE Portal)",
        "txt_operational_claim": "آليات التتبع المحيطي الذكي بدون استخدام هواتف الطلاب",
        "txt_clinical_headline": "دفتر الأستاذ المالي متعدد البوابات",
        "txt_clinical_lead": "توزيع المدفوعات في الوقت الفعلي والفوترة الإلكترونية الآلية.",
        "txt_academics_headline": "سجلات درجات تتكيف مع إطارك التعليمي.",
        "txt_academics_lead": "بدّل بين الأطر التوضيحية دون إعادة إدخال السجل التاريخي.",
        "txt_edge_headline": "محاكي انقطاع الشبكة — حضور بلا هواتف طلاب.",
        "txt_edge_lead": "من الألياف إلى الانقطاع الكامل؛ الحضور عبر QR وبطاقات RFID.",
        "txt_compliance_headline": "بوابة المدقق بنقرة واحدة مع إخفاء بيانات التعريف.",
        "txt_compliance_lead": "روابط مفتش محددة زمنياً وتوقيعات تدقيق غير قابلة للعكس.",
        "txt_pricing_headline": "حاسبة الاستحقاقات — أسعار شفافة بعملتك.",
        "txt_pricing_lead": "اختر وحدات النقل والدرجات والاتصالات والفوترة.",
    },
    "BR": {
        "txt_hero_headline": "O sistema operacional soberano para redes modernas",
        "txt_governing_body": "Integração com secretarias de educação",
        "txt_operational_claim": "Rastreamento de campus sem celular no bolso — QR e totens",
        "txt_clinical_headline": "Fluxo de ledger com divisão de gateways",
        "txt_clinical_lead": "Distribuição de pagamentos em tempo real e faturamento eletrônico.",
        "txt_academics_headline": "Diários que se adaptam ao seu currículo.",
        "txt_academics_lead": "Alterne frameworks ilustrativos sem reescrever o histórico.",
        "txt_edge_headline": "Simulador de queda de rede — presença sem celular.",
        "txt_edge_lead": "De fibra a blackout total; QR e RFID passivo continuam.",
        "txt_compliance_headline": "Portal do auditor com mascaramento de PII.",
        "txt_compliance_lead": "Links de inspetor com prazo e assinaturas de auditoria imutáveis.",
        "txt_pricing_headline": "Calculadora de direitos — preços na sua moeda.",
        "txt_pricing_lead": "Selecione transporte, notas, comunicação e faturamento.",
    },
}

_APM_PRIMARY_STATIC: dict[str, str] = {
    "US": "images/marketing/platform-offline-sync-console.svg",
    "SA": "images/marketing/platform-offline-sync-console.svg",
    "BR": "images/marketing/platform-offline-sync-console.svg",
    "NG": "images/marketing/platform-offline-sync-console.svg",
    "IN": "images/marketing/platform-offline-sync-console.svg",
}

# platform slug → {% marketing_viz %} key for generic + auto-wired templates
PLATFORM_VIZ_BY_SLUG: dict[str, str] = {
    "platform-admissions": "split_ledger_viz",
    "platform-fees-payments": "split_ledger_viz",
    "platform-offline-first": "transit_viz",
    "platform-grading-report-cards": "gradebook_viz",
    "platform-security": "transit_viz",
    "platform-attendance": "gradebook_viz",
    "platform-analytics": "gradebook_viz",
    "platform-student-information-system": "gradebook_viz",
    "platform-student-portal": "gradebook_viz",
    "platform-teacher-portal": "gradebook_viz",
    "platform-parent-portal": "split_ledger_viz",
    "platform-communications": "split_ledger_viz",
    "platform-workflows": "transit_viz",
    "platform-integrations": "transit_viz",
    "platform-runtime": "transit_viz",
    "platform-control-plane": "transit_viz",
    "platform-education-os": "transit_viz",
    "platform-marketplace": "split_ledger_viz",
    "platform-migration-cloud": "transit_viz",
}


def platform_viz_key_for_slug(slug: str) -> str:
    s = (slug or "").strip().lower()
    if not s.startswith("platform-"):
        return "split_ledger_viz"
    return PLATFORM_VIZ_BY_SLUG.get(s, "split_ledger_viz")


def loop_bucket_for_country(country_code: str) -> str:
    cc = (country_code or "").strip().upper()
    return _COUNTRY_LOOP_BUCKET.get(cc, "sovereign_default")


def assets_for_country(country_code: str) -> dict[str, str]:
    bucket = loop_bucket_for_country(country_code)
    base = dict(VISUAL_ASSET_MATRIX.get(bucket, VISUAL_ASSET_MATRIX["sovereign_default"]))
    base["loop_bucket"] = bucket
    return base


def apm_primary_static_for_country(country_code: str) -> str:
    """Static path (under static/) for clinical ledger APM hero image."""
    cc = (country_code or "").strip().upper()
    return _APM_PRIMARY_STATIC.get(cc, _APM_PRIMARY_STATIC["US"])


def apm_icons_for_country(country_code: str) -> list[dict[str, str]]:
    """Return illustrative APM labels for Clinical Ledger strip (no live PSP claims)."""
    cc = (country_code or "").strip().upper()
    catalog: dict[str, list[dict[str, str]]] = {
        "US": [
            {"id": "card", "label": "Card"},
            {"id": "ach", "label": "ACH"},
        ],
        "BR": [{"id": "pix", "label": "Pix"}],
        "IN": [{"id": "upi", "label": "UPI"}, {"id": "card", "label": "Card"}],
        "NG": [{"id": "bank", "label": "Bank transfer"}, {"id": "card", "label": "Card"}],
        "KE": [{"id": "mpesa", "label": "M-Pesa"}, {"id": "card", "label": "Card"}],
        "SA": [{"id": "sar", "label": "SAR rails"}, {"id": "card", "label": "Card"}],
        "AE": [{"id": "aed", "label": "AED rails"}, {"id": "card", "label": "Card"}],
    }
    return list(catalog.get(cc, [{"id": "card", "label": "Card"}, {"id": "bank", "label": "Bank transfer"}]))


def marketing_copy_token(country_code: str, token: str, marketing_local: dict[str, Any] | None) -> str:
    """Resolve marketing copy tokens for {% marketing_copy %} / {% text_token %}."""
    ml = marketing_local or {}
    cc = (country_code or "US").strip().upper() or "US"
    registry = MARKETING_COPY_REGISTRY.get(cc) or MARKETING_COPY_REGISTRY["US"]

    if token == "txt_hero_headline" and ml.get("headline_lead"):
        return str(ml["headline_lead"])
    if token == "txt_governing_body" and ml.get("regulatory_line"):
        return str(ml["regulatory_line"])
    if token == "txt_hero_subheadline" and ml.get("hero_subline"):
        return str(ml["hero_subline"])

    if token in registry:
        return registry[token]

    extras = {
        "txt_platform_title": "RunMyCampus",
        "txt_student_label": "Students",
        "txt_hero_subheadline": ml.get("hero_subline") or "",
    }
    return str(extras.get(token, f"[{token}]"))
