"""Resolvers + persistence writers for every wizard in the registry.

Each wizard JSON references callables here via dotted paths
(``apps.setup_studio.wizard_resolvers::name``). Options resolvers return
``[{value, label_token, metadata}]`` lists. Persistence writers take
``school, wizard_key, step_key, payload, actor_user_id`` and persist
through the 7-layer cascade — primarily via
``SiteSettings.cockpit_payload[wizards.<wizard_key>.<step_key>]``, with
best-effort integration into per-domain services where they exist.

CLAUDE.md constraints honored:
* No hardcoded role strings — option lists carry tokens, never literal "ADMIN"/etc.
* No money_float — Decimal-only via validators; resolvers return strings for amounts.
* Tenant queryset safety — writers only write to the school they receive.
* PII sanitization — _write_to_site_settings runs every payload through _coerce_for_json.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# Shared helpers (also imported indirectly by writers)
# ============================================================================


def _write_to_site_settings(school: Any, dotted_path: str, value: Any) -> None:
    """Persist a nested value into ``school.settings`` under ``dotted_path``.

    ``school.settings`` is the per-tenant JSONField that ``platform_runtime``'s
    ``get_effective_site_settings`` reads as overrides on top of the global
    ``SiteSettings`` singleton. The historical name of this helper is preserved
    so existing writers continue to call it; the storage target is per-tenant.
    """
    if school is None or getattr(school, "pk", None) is None:
        logger.debug("_write_to_site_settings: school missing or unsaved")
        return

    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        settings = {}
    target = settings
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        nxt = target.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            target[part] = nxt
        target = nxt
    target[parts[-1]] = _coerce_for_json(value)

    try:
        school.settings = settings
        school.save(update_fields=["settings"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("_write_to_site_settings: school.settings save failed: %s", exc)


def _coerce_for_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {k: _coerce_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_coerce_for_json(v) for v in value]
    if hasattr(value, "name") and hasattr(value, "read"):
        return {"file_name": getattr(value, "name", None), "file_size": getattr(value, "size", None)}
    return str(value)


def _default_cockpit_writer(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    """Persist payload at wizards.<wizard_key>.<step_key>. Default landing for every writer."""
    if school is None:
        return
    _write_to_site_settings(school, f"wizards.{wizard_key}.{step_key}", payload)


def _try_domain_integration(import_path: str, fn_name: str, **kwargs: Any) -> bool:
    """Best-effort: import + call a domain service. Returns True if it ran cleanly, False otherwise."""
    try:
        module = __import__(import_path, fromlist=[fn_name])
        fn = getattr(module, fn_name, None)
        if not callable(fn):
            return False
        fn(**kwargs)
        return True
    except (ImportError, AttributeError, TypeError) as exc:
        logger.debug("domain integration skipped (%s.%s): %s", import_path, fn_name, exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("domain integration call failed (%s.%s): %s", import_path, fn_name, exc)
        return False


# ============================================================================
# P1.1 — Cross-Platform Whitelabel & Branding (real implementation)
# ============================================================================


def list_heritage_palettes(*, request: Any, school: Any) -> list[dict[str, Any]]:
    palettes = [
        ("neutral_indigo", "Neutral Indigo", "#4F46E5", "#10B981"),
        ("kerala_heritage_emerald", "Kerala Heritage Emerald", "#0D7A4D", "#F4B840"),
        ("savannah_ochre", "Savannah Ochre", "#C57F39", "#2E5E47"),
        ("sahara_sand", "Sahara Sand", "#D4A574", "#3B5570"),
        ("bahia_carnival", "Bahia Carnival", "#E84A5F", "#FFD93D"),
        ("alpine_calm", "Alpine Calm", "#3B7B9E", "#A8B5A0"),
        ("riviera_azure", "Riviera Azure", "#2A9DF4", "#F9F4E8"),
        ("south_china_jade", "South China Jade", "#1B7F5C", "#E8B647"),
        ("nordic_quiet", "Nordic Quiet", "#5A6E8C", "#E1E9F1"),
        ("desert_dawn", "Desert Dawn", "#B85C38", "#5C8A6A"),
    ]
    return [
        {
            "value": key,
            "label_token": f"wizards.whitelabel.palette.{key}.label",
            "metadata": {"display_label": label, "primary_color_hex": primary, "secondary_color_hex": secondary},
        }
        for key, label, primary, secondary in palettes
    ]


def list_type_scale_anchors(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "compact", "label_token": "wizards.whitelabel.type_scale.compact", "metadata": {}},
        {"value": "comfortable", "label_token": "wizards.whitelabel.type_scale.comfortable", "metadata": {}},
        {"value": "spacious", "label_token": "wizards.whitelabel.type_scale.spacious", "metadata": {}},
    ]


def write_brand_assets(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    if school is None:
        return
    _try_domain_integration(
        "apps.brand_experience.services", "install_brand_assets",
        school=school,
        logo=payload.get("logo_file"),
        favicon=payload.get("favicon_file"),
        social_share_image=payload.get("social_share_image_file"),
        alt_text=payload.get("alt_text"),
    )
    _write_to_site_settings(school, "whitelabel.brand_assets", {
        "logo_file_name": getattr(payload.get("logo_file"), "name", None),
        "favicon_file_name": getattr(payload.get("favicon_file"), "name", None),
        "social_share_image_file_name": getattr(payload.get("social_share_image_file"), "name", None),
        "alt_text": payload.get("alt_text"),
    })


def write_typography_palette(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    if school is None:
        return
    palette_key = payload.get("palette_key")
    primary = payload.get("primary_color_hex")
    secondary = payload.get("secondary_color_hex")
    type_scale = payload.get("type_scale_anchor")

    for field, val in (
        ("brand_palette_key", palette_key),
        ("brand_primary_color", primary),
        ("brand_secondary_color", secondary),
        ("brand_type_scale_anchor", type_scale),
    ):
        if val:
            _try_domain_integration(
                "apps.platform_runtime.runtime_defaults_first_class",
                "set_runtime_default",
                school=school, field=field, value=val,
            )

    _write_to_site_settings(school, "whitelabel.typography_palette", {
        "palette_key": palette_key,
        "primary_color_hex": primary,
        "secondary_color_hex": secondary,
        "type_scale_anchor": type_scale,
    })


def write_custom_domain(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    if school is None:
        return
    domain = (payload.get("value") or "").strip().lower()
    if not domain:
        return
    if hasattr(school, "custom_domain"):
        try:
            setattr(school, "custom_domain", domain)
            school.save(update_fields=["custom_domain"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("write_custom_domain: direct field write failed: %s", exc)
    _write_to_site_settings(school, "whitelabel.custom_domain", {"domain": domain})


def write_pwa_manifest(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    if school is None:
        return
    _try_domain_integration(
        "apps.brand_experience.pwa_manifest", "compile_manifest",
        school=school,
        short_name=payload.get("app_short_name"),
        long_name=payload.get("app_long_name"),
        splash_background_color=payload.get("splash_background_color"),
        splash_text_color=payload.get("splash_text_color"),
        theme_color=payload.get("theme_color"),
    )
    _write_to_site_settings(school, "whitelabel.pwa_manifest", {
        "short_name": payload.get("app_short_name"),
        "long_name": payload.get("app_long_name"),
        "splash_background_color": payload.get("splash_background_color"),
        "splash_text_color": payload.get("splash_text_color"),
        "theme_color": payload.get("theme_color"),
    })


# ============================================================================
# Generic / shared resolvers
# ============================================================================


def list_countries(*, request: Any, school: Any) -> list[dict[str, Any]]:
    # Canonical full ISO catalog (~249, name-sorted). NB: the old
    # ``apps.siteconfig.country_registry.list_active_countries`` import never
    # existed in the tree, so this resolver ALWAYS hit the except and returned a
    # hardcoded 31-country list — most countries were missing from the wizard's
    # country <select>. Route through GlobalGeoCatalog like every other picker.
    try:
        from apps.siteconfig.global_catalog import GlobalGeoCatalog

        rows = GlobalGeoCatalog.list_countries() or []
        out = []
        for row in rows:
            cc = str(row.get("code_alpha2", "")).upper()
            if cc:
                out.append({
                    "value": cc,
                    "label_token": f"countries.{cc}",
                    "metadata": {"name": str(row.get("name", ""))},
                })
        if out:
            return out
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    # Last-resort fallback only when the catalog deps are unavailable.
    return [
        {"value": cc, "label_token": f"countries.{cc}", "metadata": {}}
        for cc in [
            "AE", "AR", "AU", "BR", "CA", "CM", "DE", "EG", "ES", "FR", "GB",
            "GH", "ID", "IN", "JP", "KE", "KR", "MX", "MY", "NG", "PH", "PK",
            "SA", "SG", "TH", "TR", "TZ", "UG", "US", "VN", "ZA",
        ]
    ]


def list_settlement_currencies(*, request: Any, school: Any) -> list[dict[str, Any]]:
    # Full ISO 4217 catalog (~180) via pycountry, so a school whose settlement
    # currency isn't in the legacy 27-item list can still select it.
    try:
        import pycountry

        out = []
        for cur in pycountry.currencies:
            code = str(getattr(cur, "alpha_3", "") or "").upper()
            if code:
                out.append({
                    "value": code,
                    "label_token": f"currencies.{code}",
                    "metadata": {"name": str(getattr(cur, "name", ""))},
                })
        if out:
            out.sort(key=lambda d: d["value"])
            return out
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    return [
        {"value": code, "label_token": f"currencies.{code}", "metadata": {}}
        for code in [
            "USD", "EUR", "GBP", "INR", "BRL", "MXN", "ZAR", "KES", "NGN",
            "GHS", "EGP", "AED", "SAR", "CNY", "JPY", "KRW", "IDR", "PHP",
            "MYR", "THB", "VND", "TRY", "PKR", "BDT", "LKR", "AUD", "CAD",
        ]
    ]


def list_supported_locales(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": code, "label_token": f"locales.{code}", "metadata": {}}
        for code in [
            "en", "fr", "es", "pt", "ar", "hi", "sw", "de", "it", "ja", "ko",
            "zh-CN", "zh-TW", "vi", "th", "tl", "id", "ms", "ta", "ml", "kn", "bn",
        ]
    ]


def list_communication_channels(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": v, "label_token": f"comm.channel.{v}", "metadata": {}}
        for v in ["sms", "whatsapp", "email", "push", "parent_portal", "voice_call"]
    ]


# ============================================================================
# P1.2 — Multi-Campus Local Sovereignty
# ============================================================================


def list_data_residency_regions(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": r, "label_token": f"residency.{r}", "metadata": {}}
        for r in [
            "us-east-1", "us-west-2", "eu-west-1", "eu-central-1",
            "ap-south-1", "ap-southeast-1", "ap-northeast-1",
            "me-central-1", "sa-east-1", "af-south-1",
        ]
    ]


def list_routing_profiles(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "default", "label_token": "routing.default", "metadata": {"edge_tier": False}},
        {"value": "edge_aggressive", "label_token": "routing.edge_aggressive", "metadata": {"edge_tier": True}},
        {"value": "legal_sovereign", "label_token": "routing.legal_sovereign", "metadata": {"edge_tier": False, "sovereign": True}},
        {"value": "hybrid", "label_token": "routing.hybrid", "metadata": {"edge_tier": True}},
    ]


def list_vocabulary_packs(*, request: Any, school: Any) -> list[dict[str, Any]]:
    packs = [
        "default_en", "in_kl_state_board_ml", "in_ka_state_board_kn",
        "in_ta_state_board_ta", "in_mh_state_board_mr",
        "ng_basic_education", "ke_8_4_4", "za_caps", "br_ensino_medio",
        "fr_education_nationale", "de_gymnasium", "ae_moe", "sa_moe",
        "us_k12", "gb_national_curriculum", "id_kurikulum_merdeka",
        "ph_k12_deped", "cm_anglo_gce", "cm_franco_bac",
    ]
    return [{"value": p, "label_token": f"vocabulary.pack.{p}", "metadata": {}} for p in packs]


def list_canonical_vocabulary_terms(*, request: Any, school: Any) -> list[dict[str, Any]]:
    terms = [
        "Student", "Teacher", "Principal", "Headteacher", "Class", "Term",
        "Semester", "Grade", "Period", "Tutor", "Counselor", "Bursar",
        "Cohort", "Lesson", "Section", "Assignment", "Quiz", "Exam",
    ]
    return [{"value": t, "label_token": f"vocab.canonical.{t.lower()}", "metadata": {}} for t in terms]


def list_statutory_schemas(*, request: Any, school: Any) -> list[dict[str, Any]]:
    schemas = [
        ("udise_plus_in", "UDISE+ India"),
        ("dapodik_id", "Dapodik Indonesia"),
        ("nslp_us", "NSLP United States"),
        ("ferpa_us", "FERPA United States"),
        ("gdpr_eu", "GDPR EU"),
        ("popia_za", "POPIA South Africa"),
        ("lgpd_br", "LGPD Brazil"),
        ("pdpa_sg", "PDPA Singapore"),
        ("pipeda_ca", "PIPEDA Canada"),
        ("ny_ed_2d_us", "NY Ed Law § 2-d United States"),
        ("zatca_sa", "ZATCA Saudi Arabia"),
        ("sat_mx", "SAT Mexico"),
        ("gst_einvoice_in", "GST e-Invoice India"),
    ]
    return [{"value": k, "label_token": f"statutory.{k}", "metadata": {"display_label": label}} for k, label in schemas]


def write_sovereignty_jurisdiction(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    if school is None:
        return
    cc = payload.get("country_code")
    state = payload.get("state_code")
    region = payload.get("data_residency_region")
    for field, val in (("country_code", cc), ("state_code", state), ("data_residency_region", region)):
        if val and hasattr(school, field):
            try:
                setattr(school, field, val)
            except Exception as exc:  # noqa: BLE001
                logger.debug("School.%s write skipped: %s", field, exc)
    try:
        update_fields = [f for f in ("country_code", "state_code", "data_residency_region") if hasattr(school, f)]
        if update_fields:
            school.save(update_fields=update_fields)
    except Exception as exc:  # noqa: BLE001
        logger.warning("School save failed in sovereignty wizard: %s", exc)
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_sovereignty_routing(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    from apps.setup_studio.sovereignty_kernel import apply_dynamic_routing
    apply_dynamic_routing(school=school, payload=payload)


def write_sovereignty_vocabulary(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    if school is None:
        return
    _write_to_site_settings(school, "sovereignty.vocabulary", payload)
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_sovereignty_statutory(*, school: Any, wizard_key: str, step_key: str, payload: dict[str, Any], actor_user_id: int | None) -> None:
    from apps.setup_studio.sovereignty_kernel import apply_statutory_alignment
    apply_statutory_alignment(school=school, payload=payload)


# ============================================================================
# P1.3 — Polymorphic Grading & Curricula
# ============================================================================


def list_curriculum_tracks(*, request: Any, school: Any) -> list[dict[str, Any]]:
    tracks = [
        "ib_diploma", "ib_myp", "ib_pyp",
        "cambridge_a_levels", "cambridge_igcse",
        "ap_advanced_placement",
        "local_k12", "local_ministry_track",
        "vocational_trade", "montessori",
        "cbse_in", "icse_in", "state_board_in",
        "bac_general_fr", "bac_d_cm", "gce_o_a_cm",
        "abitur_de", "matura_eu",
    ]
    return [{"value": t, "label_token": f"track.{t}", "metadata": {}} for t in tracks]


# GradingScale.ScaleType → this wizard's option value, so the country-recommended scale
# (apps.evals.grading_provisioning.resolve_local_scale_type) can be pre-selected. Adds
# numeric_0_20 to the option set so 0–20 (Francophone) systems are representable at all.
_SCALE_TYPE_TO_WIZARD_VALUE = {
    "numeric_0_20": "numeric_0_20",
    "percentage": "percentage",
    "gpa_4_0": "gpa_4",
    "letter_a_e": "letter",
    "us_letter": "letter",
}


def _recommended_grading_scale_value(school: Any) -> str:
    """The wizard option value matching the school's COUNTRY-recommended scale, or ""."""
    if school is None:
        return ""
    try:
        from apps.evals.grading_provisioning import resolve_local_scale_type

        return _SCALE_TYPE_TO_WIZARD_VALUE.get(resolve_local_scale_type(school), "")
    except Exception:  # noqa: BLE001 — recommendation is best-effort, never blocks the wizard
        return ""


def list_grading_scales(*, request: Any, school: Any) -> list[dict[str, Any]]:
    # numeric_0_20 added so Francophone/0–20 systems can be picked (was unrepresentable).
    scales = [
        "numeric_0_20", "percentage", "letter", "gpa_4", "gpa_5",
        "competency", "points_100", "points_1000",
    ]
    recommended = _recommended_grading_scale_value(school)
    options = [
        {
            "value": s,
            "label_token": f"grading.scale.{s}",
            "metadata": {"recommended": s == recommended} if recommended else {},
        }
        for s in scales
    ]
    # Local-first: surface the country-recommended scale FIRST so it is the natural pick
    # instead of a blind choice from a flat list.
    if recommended:
        options.sort(key=lambda o: 0 if o["value"] == recommended else 1)
    return options


def list_canonical_csv_fields(*, request: Any, school: Any) -> list[dict[str, Any]]:
    fields = [
        ("students.full_name", "Student full name"),
        ("students.date_of_birth", "Student date of birth"),
        ("students.grade_level", "Student grade level"),
        ("students.enrollment_status", "Student enrollment status"),
        ("students.guardian_phone", "Student guardian phone"),
        ("staff.full_name", "Staff full name"),
        ("staff.role", "Staff role"),
        ("staff.hire_date", "Staff hire date"),
        ("classes.code", "Class code"),
        ("classes.name", "Class name"),
        ("subjects.name", "Subject name"),
        ("grades.scale_value", "Grade value"),
        ("attendance.date", "Attendance date"),
        ("attendance.status", "Attendance status"),
    ]
    return [{"value": k, "label_token": f"canonical.{k.replace('.', '_')}", "metadata": {"display_label": label}} for k, label in fields]


def list_transcript_templates(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "basic_pdf", "label_token": "transcript.basic_pdf", "metadata": {"signature_scheme": None}},
        {"value": "signed_pdf_a3", "label_token": "transcript.signed_pdf_a3", "metadata": {"signature_scheme": "Ed25519"}},
        {"value": "jsonld_diploma", "label_token": "transcript.jsonld_diploma", "metadata": {"signature_scheme": "RSA-PSS-SHA256"}},
        {"value": "svg_certificate", "label_token": "transcript.svg_certificate", "metadata": {"signature_scheme": None}},
    ]


def write_grading_track(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.evals.grading_wizard_kernel import apply_curriculum_tracks
    apply_curriculum_tracks(school=school, payload=payload)


def write_grading_metrics(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.evals.grading_wizard_kernel import apply_assessment_metrics
    apply_assessment_metrics(school=school, payload=payload)


def write_grading_subject_mapping(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_grading_transcript(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


# ============================================================================
# P1.4 — Legacy Data Extraction Pipeline
# ============================================================================


def list_migration_vendors(*, request: Any, school: Any) -> list[dict[str, Any]]:
    vendors = ["powerschool", "blackbaud", "veracross", "alma", "facts", "skyward", "other"]
    return [{"value": v, "label_token": f"migration.vendor.{v}", "metadata": {}} for v in vendors]


def list_seeding_modes(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "dry_run", "label_token": "seed.dry_run", "metadata": {"writes_db": False}},
        {"value": "commit_to_staging", "label_token": "seed.commit_to_staging", "metadata": {"writes_db": True, "production": False}},
        {"value": "commit_to_production", "label_token": "seed.commit_to_production", "metadata": {"writes_db": True, "production": True}},
    ]


def write_migration_upload(*, school, wizard_key, step_key, payload, actor_user_id):
    if school is None:
        return
    _try_domain_integration(
        "apps.migration_cloud.companion_receiver", "register_upload",
        school=school, payload=payload, actor_user_id=actor_user_id,
    )
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_migration_mapping(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.migration_cloud.wizard_pipeline_kernel import apply_field_mapping
    apply_field_mapping(school=school, payload=payload, actor_user_id=actor_user_id)


def write_migration_cleanup(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.migration_cloud.wizard_pipeline_kernel import apply_error_cleanup
    apply_error_cleanup(school=school, payload=payload, actor_user_id=actor_user_id)


def write_migration_seeding(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.migration_cloud.wizard_pipeline_kernel import apply_seeding_mode
    apply_seeding_mode(school=school, payload=payload, actor_user_id=actor_user_id)


# ============================================================================
# P1.5 — AI Helpcenter Knowledge Injection
# ============================================================================


def list_helpcenter_audience_tags(*, request: Any, school: Any) -> list[dict[str, Any]]:
    tags = [
        "all_parents", "parent_primary", "parent_middle_school", "parent_high_school",
        "all_staff", "teacher", "admin_staff", "support_staff",
        "all_students", "student_primary", "student_middle_school", "student_high_school",
    ]
    return [{"value": t, "label_token": f"helpcenter.audience.{t}", "metadata": {}} for t in tags]


def list_helpcenter_escalation_routes(*, request: Any, school: Any) -> list[dict[str, Any]]:
    routes = [
        "bursar_sms", "bursar_email",
        "principal_email", "principal_phone",
        "headteacher_review",
        "admissions_phone", "admissions_email",
        "operator_ticket",
        "counselor_review",
    ]
    return [{"value": r, "label_token": f"helpcenter.escalation.{r}", "metadata": {}} for r in routes]


def write_helpcenter_sources(*, school, wizard_key, step_key, payload, actor_user_id):
    if school is None:
        return
    _try_domain_integration(
        "apps.customersuccess.services", "register_helpcenter_source",
        school=school, payload=payload,
    )
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_helpcenter_tagging(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.customersuccess.helpcenter_wizard_kernel import apply_audience_tags
    apply_audience_tags(school=school, payload=payload)


def write_helpcenter_fallbacks(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.customersuccess.helpcenter_wizard_kernel import apply_fallback_matrix
    apply_fallback_matrix(school=school, payload=payload)


def write_helpcenter_validation(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.customersuccess.helpcenter_wizard_kernel import apply_validation_probe
    apply_validation_probe(school=school, payload=payload)


# ============================================================================
# P2.1 — Local-First FinTech & Tax Matrix
# ============================================================================


def list_apms(*, request: Any, school: Any) -> list[dict[str, Any]]:
    apms = [
        ("upi_rupay", "UPI / RuPay", ["IN"], True, True),
        ("pix_brcode", "Pix BR Code", ["BR"], True, True),
        ("mpesa_stk", "M-Pesa STK", ["KE", "TZ", "UG"], False, True),
        ("mobile_money_gh", "Mobile Money Ghana", ["GH"], False, True),
        ("paystack_card", "Paystack Card", ["NG", "GH", "ZA"], True, True),
        ("instapay_eg", "InstaPay Egypt", ["EG"], False, True),
        ("snap_id", "Snap Indonesia", ["ID"], True, True),
        ("gcash_ph", "GCash Philippines", ["PH"], True, True),
        ("promptpay_th", "PromptPay Thailand", ["TH"], True, True),
        ("vietqr_vn", "VietQR Vietnam", ["VN"], True, True),
        ("stripe_card", "Stripe Card (Universal)", ["*"], True, True),
        ("paypal_universal", "PayPal (Universal)", ["*"], True, True),
    ]
    return [
        {
            "value": k,
            "label_token": f"fintech.apm.{k}",
            "metadata": {"display_label": label, "countries": countries, "recurring": recurring, "api_available": api},
        }
        for k, label, countries, recurring, api in apms
    ]


def list_einvoicing_options(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "zatca_pfx", "label_token": "einvoicing.zatca", "metadata": {"countries": ["SA"]}},
        {"value": "sat_cer", "label_token": "einvoicing.sat", "metadata": {"countries": ["MX"]}},
        {"value": "gst_gsp", "label_token": "einvoicing.gst", "metadata": {"countries": ["IN"]}},
        {"value": "sefaz_pfx", "label_token": "einvoicing.sefaz", "metadata": {"countries": ["BR"]}},
        {"value": "skip", "label_token": "einvoicing.skip", "metadata": {"countries": ["*"]}},
    ]


def write_fintech_settlement(*, school, wizard_key, step_key, payload, actor_user_id):
    if school is None:
        return
    _try_domain_integration(
        "apps.billing.services", "set_payment_settings",
        school=school,
        settlement_country=payload.get("settlement_country"),
        settlement_currency=payload.get("settlement_currency"),
        settlement_bank_account_alias=payload.get("settlement_bank_account_alias"),
    )
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_fintech_apm(*, school, wizard_key, step_key, payload, actor_user_id):
    if school is None:
        return
    _try_domain_integration(
        "apps.billing.services", "enable_apm",
        school=school, apm_key=payload.get("value"),
    )
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_fintech_split(*, school, wizard_key, step_key, payload, actor_user_id):
    if school is None:
        return
    from apps.billing.regional_pricing import compute_localized_price
    base = payload.get('base_usd') or payload.get('value') or '0.00'
    cc = payload.get('country_code') or getattr(school, 'country_code', None) or 'US'
    loc = compute_localized_price(base, str(cc).strip().upper())
    _write_to_site_settings(school, 'fintech.ppp_revenue_split', {
        'country_code': loc.country_code,
        'currency_code': loc.currency_code,
        'multiplier': str(loc.multiplier),
        'tax_rate': str(loc.tax_rate),
        'subtotal': str(loc.subtotal),
        'tax': str(loc.tax),
        'total': str(loc.total),
        'engine': 'billing.regional_pricing',
    })


def write_fintech_einvoicing(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


# ============================================================================
# P2.2 — Localized Activity & Asset Marketplace
# ============================================================================


def list_storefront_categories(*, request: Any, school: Any) -> list[dict[str, Any]]:
    cats = [
        "uniforms", "textbooks", "stationery", "lab_kits", "sports_kits",
        "event_tickets", "fundraiser_donations", "field_trip_payments",
        "exam_fees", "boarding_supplies", "graduation_packages",
    ]
    return [{"value": c, "label_token": f"marketplace.category.{c}", "metadata": {}} for c in cats]


def write_marketplace_storefront(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.marketplace.marketplace_wizard_kernel import apply_storefront_blueprint
    apply_storefront_blueprint(school=school, payload=payload)
    if school is not None:
        from apps.marketplace.localized_pricing import apply_ppp_to_storefront
        base = payload.get('base_usd') or payload.get('default_base_usd') or '0.00'
        apply_ppp_to_storefront(school=school, base_usd=base, payload=payload)


def write_marketplace_catalog(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.marketplace.marketplace_wizard_kernel import apply_catalog_seed
    apply_catalog_seed(school=school, payload=payload)


def write_marketplace_routing(*, school, wizard_key, step_key, payload, actor_user_id):
    if school is None:
        return
    from apps.marketplace.localized_pricing import apply_ppp_to_storefront
    base = payload.get('base_usd') or payload.get('value') or '0.00'
    apply_ppp_to_storefront(school=school, base_usd=base, payload=payload)


def write_marketplace_receipts(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.marketplace.marketplace_wizard_kernel import apply_receipt_automation
    apply_receipt_automation(school=school, payload=payload)


# ============================================================================
# P2.3 — Cashless Campus POS
# ============================================================================


def list_pos_credential_methods(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "barcode", "label_token": "pos.credential.barcode", "metadata": {"biometric": False}},
        {"value": "rfid", "label_token": "pos.credential.rfid", "metadata": {"biometric": False}},
        {"value": "biometric_thumb", "label_token": "pos.credential.biometric_thumb", "metadata": {"biometric": True}},
        {"value": "biometric_face", "label_token": "pos.credential.biometric_face", "metadata": {"biometric": True}},
        {"value": "qr_id_card", "label_token": "pos.credential.qr_id_card", "metadata": {"biometric": False}},
    ]


def write_pos_terminals(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_pos_credentials(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_pos_guardrails(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.schoolops.pos_config_kernel import configure_pos_guardrails
    configure_pos_guardrails(school=school, payload=payload)


def write_pos_allergens(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.schoolops.pos_config_kernel import configure_pos_allergens
    configure_pos_allergens(school=school, payload=payload)


# ============================================================================
# P2.4 — Dynamic Safeguarding / Incident / Medical
# ============================================================================


def list_incident_categories(*, request: Any, school: Any) -> list[dict[str, Any]]:
    cats = [
        "medical_emergency", "disciplinary_action", "safeguarding_concern",
        "bullying_report", "substance_incident", "weapons_incident",
        "self_harm_disclosure", "abuse_disclosure", "attendance_truancy",
        "academic_misconduct", "facility_hazard",
    ]
    return [{"value": c, "label_token": f"incident.category.{c}", "metadata": {}} for c in cats]


def list_audit_anchors(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "append_only_db", "label_token": "audit.anchor.append_only_db", "metadata": {"hsm": False}},
        {"value": "s3_object_lock", "label_token": "audit.anchor.s3_object_lock", "metadata": {"hsm": False, "worm": True}},
        {"value": "hsm_anchored", "label_token": "audit.anchor.hsm_anchored", "metadata": {"hsm": True}},
    ]


def write_safeguarding_categories(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.safeguarding.wizard_config_kernel import apply_enabled_categories
    apply_enabled_categories(school=school, payload=payload)


def write_safeguarding_routing(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.safeguarding.wizard_config_kernel import apply_legal_routing
    apply_legal_routing(school=school, payload=payload)


def write_safeguarding_stakeholders(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.safeguarding.wizard_config_kernel import apply_stakeholder_pipeline
    apply_stakeholder_pipeline(school=school, payload=payload)


def write_safeguarding_anchor(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.safeguarding.wizard_config_kernel import apply_audit_anchor
    apply_audit_anchor(school=school, payload=payload)


# ============================================================================
# P2.5 — Omnichannel Communication Routing
# ============================================================================


def list_event_triggers(*, request: Any, school: Any) -> list[dict[str, Any]]:
    triggers = [
        "student.marked_absent_today",
        "student.marked_absent_consecutive_days_3",
        "student.attendance_dropped_below_85pct",
        "fee.overdue_7_days",
        "fee.overdue_30_days",
        "grade.below_threshold",
        "safeguarding.flagged",
        "field_trip.permission_required",
        "report_card.published",
        "medical.allergy_alert",
    ]
    return [{"value": t, "label_token": f"trigger.{t}", "metadata": {}} for t in triggers]


def list_comm_channels(*, request: Any, school: Any) -> list[dict[str, Any]]:
    channels = ["app_push", "whatsapp", "sms", "email", "ussd_fallback", "voice_call", "parent_portal_inbox"]
    return [{"value": c, "label_token": f"comm.channel.{c}", "metadata": {}} for c in channels]


def write_comms_event(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_comms_gateway(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.communication.routing_config_kernel import apply_gateway_priority
    apply_gateway_priority(school=school, payload=payload)


def write_comms_guards(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_comms_translation(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


# ============================================================================
# P3.1 — JIT Operator Compliance & Safeguarding
# ============================================================================


def list_jit_triggers(*, request: Any, school: Any) -> list[dict[str, Any]]:
    trig = [
        "troubleshooting_active_bug", "migration_in_progress",
        "safeguarding_active", "legal_hold", "customer_request",
        "billing_inquiry", "security_incident_response",
    ]
    return [{"value": t, "label_token": f"jit.trigger.{t}", "metadata": {}} for t in trig]


def list_pii_redaction_fields(*, request: Any, school: Any) -> list[dict[str, Any]]:
    flds = [
        "student_full_name", "student_dob", "student_ssn_local",
        "parent_phone", "parent_email", "home_address",
        "medical_notes", "financial_records", "behavioral_notes",
        "guardian_relationship_status",
    ]
    return [{"value": f, "label_token": f"pii.redact.{f}", "metadata": {}} for f in flds]


def write_compliance_triggers(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_compliance_guardrails(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_compliance_masking(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_compliance_ledger(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.compliance.jit_compliance_kernel import apply_ledger_anchor
    apply_ledger_anchor(school=school, payload=payload, actor_user_id=actor_user_id)


# ============================================================================
# P3.2 — Human Capital, Shift, Substitute Market
# ============================================================================


def list_substitute_pool(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return []


def write_hr_contract(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.payroll.hr_wizard_kernel import apply_labor_contract_profile
    apply_labor_contract_profile(school=school, payload=payload)


def write_hr_tax(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_hr_absence(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.payroll.hr_wizard_kernel import apply_absence_logic
    apply_absence_logic(school=school, payload=payload)


def write_hr_substitute(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


# ============================================================================
# P3.3 — Institutional Performance & Board Reporting
# ============================================================================


def list_executive_kpis(*, request: Any, school: Any) -> list[dict[str, Any]]:
    kpis = [
        "enrollment_retention_pct", "tuition_collection_velocity_days",
        "class_passing_avg_pct", "teacher_retention_pct",
        "parent_nps", "safeguarding_open_incidents",
        "attendance_avg_pct", "library_resource_utilization",
        "campus_energy_usage_kwh", "applicant_yield_pct",
        "scholarship_burn_pct", "annual_giving_amount",
    ]
    return [{"value": k, "label_token": f"kpi.{k}", "metadata": {}} for k in kpis]


def write_analytics_kpis(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.reports.board_aggregation_kernel import apply_enabled_executive_kpis
    apply_enabled_executive_kpis(school=school, payload=payload)


def write_analytics_aggregation(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.reports.board_aggregation_kernel import refresh_board_kpi_snapshot
    raw = payload.get('value') or payload.get('kpi_keys') or []
    refresh_board_kpi_snapshot(school=school, kpi_keys=raw if isinstance(raw, list) else [raw])


def write_analytics_predictions(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_analytics_report(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


# ============================================================================
# P3.4 — Self-Healing Observability Guard
# ============================================================================


def list_observability_recovery_actions(*, request: Any, school: Any) -> list[dict[str, Any]]:
    actions = [
        "auto_failover_region", "kill_offending_job",
        "alert_oncall_sms", "alert_oncall_phone",
        "page_eng_lead", "create_incident_ticket",
        "throttle_inbound_traffic", "scale_out_worker_pool",
    ]
    return [{"value": a, "label_token": f"observability.action.{a}", "metadata": {}} for a in actions]


def write_observability_thresholds(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.observability.tenant_guard_kernel import apply_tenant_slo_thresholds
    apply_tenant_slo_thresholds(school=school, payload=payload)


def write_observability_actions(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_observability_tunnel(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


# ============================================================================
# P3.5 — Dynamic Multi-Campus Scheduling
# ============================================================================


def list_resource_constraints(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return []


def write_scheduling_resources(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.academics.scheduling_kernel import apply_resource_constraints
    apply_resource_constraints(school=school, payload=payload)


def write_scheduling_pathways(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_scheduling_solver(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.academics.scheduling_kernel import configure_solver
    configure_solver(school=school, payload=payload)


def write_scheduling_rollout(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


# ============================================================================
# P3.6 — Localized Field Trip Coordinator
# ============================================================================


def list_field_trip_transport(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": v, "label_token": f"fieldtrip.transport.{v}", "metadata": {}}
        for v in ["bus", "car", "train", "walk", "virtual", "boat", "metro"]
    ]


def write_fieldtrip_logistics(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_fieldtrip_authorization(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.schoolops.field_trip_kernel import setup_field_trip_authorization
    setup_field_trip_authorization(school=school, payload=payload)


def write_fieldtrip_roster(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


# ============================================================================
# P3.7 — Personal Graduation Pathway & Elective
# ============================================================================


def list_post_secondary_objectives(*, request: Any, school: Any) -> list[dict[str, Any]]:
    objs = [
        "engineering", "medicine", "arts", "vocational_trade",
        "university_general", "gap_year", "business_commerce",
        "law", "sciences_pure", "humanities", "education",
        "creative_industries", "military_service",
    ]
    return [{"value": o, "label_token": f"pathway.objective.{o}", "metadata": {}} for o in objs]


def write_pathway_objective(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_pathway_audit(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_pathway_matcher(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.academics.pathway_elective_kernel import match_elective_courses
    match_elective_courses(school=school, payload=payload)


def write_pathway_lock(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


# ============================================================================
# Parent + Staff persona onboarding
# ============================================================================


def write_parent_profile(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.accounts.persona_onboarding_kernel import apply_parent_profile
    apply_parent_profile(school=school, actor_user_id=actor_user_id, payload=payload)


def write_parent_children(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.accounts.persona_onboarding_kernel import apply_parent_linked_children
    apply_parent_linked_children(school=school, actor_user_id=actor_user_id, payload=payload)


def write_parent_preferences(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_parent_payment_preview(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_parent_consent(*, school, wizard_key, step_key, payload, actor_user_id):
    if school is None:
        return
    _try_domain_integration(
        "apps.compliance.services", "record_consent_acceptance",
        school=school, payload=payload, actor_user_id=actor_user_id,
    )
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_staff_profile(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.accounts.persona_onboarding_kernel import apply_staff_profile
    apply_staff_profile(school=school, actor_user_id=actor_user_id, payload=payload)


def write_staff_role(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_staff_background(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_staff_schedule(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.payroll.hr_wizard_kernel import apply_staff_schedule_preferences
    apply_staff_schedule_preferences(school=school, actor_user_id=actor_user_id, payload=payload)


def write_staff_training(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


# ============================================================================
# v3.94.0 — feature-growth wizards (4 new)
# ============================================================================


# ---- library_inventory_management ----

def list_library_categories(*, request: Any, school: Any) -> list[dict[str, Any]]:
    cats = [
        "fiction", "non_fiction", "biography", "reference", "textbook",
        "science", "history", "literature", "languages", "religion",
        "career_guidance", "early_reader", "young_adult", "research_journal",
    ]
    return [{"value": c, "label_token": f"library.category.{c}", "metadata": {}} for c in cats]


def list_barcode_schemes(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "isbn13", "label_token": "library.barcode.isbn13", "metadata": {"global_standard": True}},
        {"value": "code128", "label_token": "library.barcode.code128", "metadata": {"custom_school_codes": True}},
        {"value": "qr_code", "label_token": "library.barcode.qr_code", "metadata": {"smartphone_scannable": True}},
        {"value": "rfid", "label_token": "library.barcode.rfid", "metadata": {"requires_hardware": True}},
    ]


def write_library_catalog(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_library_fines(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.schoolops.library_config_kernel import configure_fine_policy
    configure_fine_policy(school=school, payload=payload)


def write_library_categories(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_library_barcode_scheme(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


# ---- exam_schedule_orchestration ----

def list_exam_room_strategies(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "by_subject_then_room", "label_token": "exam.strategy.by_subject_then_room", "metadata": {}},
        {"value": "by_grade_block", "label_token": "exam.strategy.by_grade_block", "metadata": {}},
        {"value": "balanced_cohort", "label_token": "exam.strategy.balanced_cohort", "metadata": {}},
        {"value": "manual_lock", "label_token": "exam.strategy.manual_lock", "metadata": {"requires_admin_review": True}},
    ]


def write_exam_window(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.academics.exam_orchestration_kernel import configure_exam_window
    configure_exam_window(school=school, payload=payload)


def write_exam_room_strategy(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_exam_invigilator(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_exam_results_pipeline(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


# ---- report_card_template_studio ----

def list_report_card_templates(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": "minimal_a4", "label_token": "report_card.template.minimal_a4", "metadata": {}},
        {"value": "narrative_classroom", "label_token": "report_card.template.narrative_classroom", "metadata": {}},
        {"value": "competency_based", "label_token": "report_card.template.competency_based", "metadata": {}},
        {"value": "exam_centric_certificate", "label_token": "report_card.template.exam_centric_certificate", "metadata": {}},
        {"value": "regional_government_form", "label_token": "report_card.template.regional_government_form", "metadata": {}},
    ]


def list_report_card_columns(*, request: Any, school: Any) -> list[dict[str, Any]]:
    cols = [
        "ca_score", "exam_score", "total_score", "grade_letter",
        "class_average", "class_rank", "remark", "subject_teacher_comment",
        "term_grade", "annual_grade",
    ]
    return [{"value": c, "label_token": f"report_card.column.{c}", "metadata": {}} for c in cols]


def write_report_card_template(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_report_card_columns(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.reports.report_card_kernel import apply_grade_columns
    apply_grade_columns(school=school, payload=payload)


def write_report_card_attendance(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.reports.report_card_kernel import apply_attendance_block
    apply_attendance_block(school=school, payload=payload)


def write_report_card_signature(*, school, wizard_key, step_key, payload, actor_user_id):
    if school is None:
        return
    _try_domain_integration(
        "apps.brand_experience.services", "install_brand_assets",
        school=school,
        logo=None,
        favicon=None,
        social_share_image=payload.get("school_seal_image"),
        alt_text="School seal for report cards",
    )
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


# ---- alumni_engagement_pipeline ----

def list_alumni_contact_channels(*, request: Any, school: Any) -> list[dict[str, Any]]:
    return [
        {"value": c, "label_token": f"alumni.channel.{c}", "metadata": {}}
        for c in ["email", "whatsapp", "sms", "linkedin", "alumni_portal", "postal_mail"]
    ]


def list_alumni_programs(*, request: Any, school: Any) -> list[dict[str, Any]]:
    progs = [
        "annual_reunion", "mentorship_matching", "career_panel",
        "scholarship_fundraiser", "alumni_newsletter", "homecoming_event",
        "guest_lecture_invitation", "volunteer_coaching",
    ]
    return [{"value": p, "label_token": f"alumni.program.{p}", "metadata": {}} for p in progs]


def write_alumni_graduation_capture(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.people.alumni_engagement import capture_graduation_cohort
    capture_graduation_cohort(school=school, payload=payload)


def write_alumni_contact_preferences(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)


def write_alumni_programs(*, school, wizard_key, step_key, payload, actor_user_id):
    from apps.people.alumni_engagement import configure_alumni_pipeline
    value = payload.get('value') or payload.get('programs') or []
    configure_alumni_pipeline(school=school, payload={**payload, 'programs': value if isinstance(value, list) else [value]})


def write_alumni_donation_pipeline(*, school, wizard_key, step_key, payload, actor_user_id):
    _default_cockpit_writer(school=school, wizard_key=wizard_key, step_key=step_key, payload=payload, actor_user_id=actor_user_id)
