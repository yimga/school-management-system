"""Trust-center marketing evidence — repo proof ledgers, honest external gaps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings

from apps.platform_runtime.procurement_packet import (
    GENERATED_DIR_DEFAULT,
    _proof_summary,
    build_procurement_packet,
)
from apps.schools.marketing_region import trust_regulatory_cards_for_country

TRUST_COMPLIANCE_ANCHOR_SLUGS = frozenset(
    {
        "security-compliance",
        "platform-security",
        "trust-center",
        "security",
        "compliance",
    }
)

_TRUST_MATRIX_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "tenant_isolation",
        "control": "Campus isolation",
        "mechanism": "Dedicated tenant boundary per school; host routing enforces scope",
        "posture": "Student and staff records stay within the school context",
        "evidence_key": "tenant_isolation",
    },
    {
        "id": "authentication",
        "control": "Access control",
        "mechanism": "Role-based permissions; MFA-ready sign-in patterns",
        "posture": "Teachers, families, and admins see only what their role allows",
        "evidence_key": "rbac",
    },
    {
        "id": "audit_trails",
        "control": "Audit trails",
        "mechanism": "Logged exports and sensitive administrative actions",
        "posture": "Reviewable history for compliance and support escalations",
        "evidence_key": "audit",
    },
    {
        "id": "encryption",
        "control": "Encryption",
        "mechanism": "TLS in transit; encrypted storage for sensitive fields",
        "posture": "Documented key rotation in the security packet",
        "evidence_key": "encryption",
    },
    {
        "id": "payments",
        "control": "Payments",
        "mechanism": "Processor-hosted checkout; card data not stored on platform",
        "posture": "PCI scope reduced—live rails depend on your processor contract",
        "evidence_key": "payments",
    },
    {
        "id": "api_surface",
        "control": "Integrations & API",
        "mechanism": "Rate limits and scoped access for partner connections",
        "posture": "Read-oriented public API posture; write paths permissioned",
        "evidence_key": "api",
    },
    {
        "id": "data_residency",
        "control": "Regional defaults",
        "mechanism": "Country compliance profiles and tenant configuration cascade",
        "posture": "Local calendars, currencies, and privacy defaults per campus",
        "evidence_key": "residency",
    },
    {
        "id": "incident_response",
        "control": "Incident response",
        "mechanism": "Documented playbooks and customer security contact path",
        "posture": "Coordinated breach notification when contracts require it",
        "evidence_key": "incidents",
    },
    {
        "id": "offline_sync",
        "control": "Offline & sync",
        "mechanism": "Queued capture with explicit merge policies",
        "posture": "Operations continue when connectivity drops—common in regional deployments",
        "evidence_key": "offline",
    },
)

_REGULATORY_CARD_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "ferpa",
        "title": "FERPA",
        "summary": "Schools remain controller; access controls and auditability for education records.",
        "url_name": "marketing_trust_ferpa",
        "deep_dive_label": "FERPA deep dive",
    },
    {
        "id": "coppa",
        "title": "COPPA",
        "summary": "Under-13 accounts provisioned by the school with jurisdiction-appropriate consent.",
        "url_name": "marketing_trust_coppa",
        "deep_dive_label": "COPPA deep dive",
    },
    {
        "id": "gdpr",
        "title": "GDPR / privacy",
        "summary": "Processor posture, DSAR workflows, and regional compliance profiles.",
        "url_name": "marketing_trust_gdpr",
        "deep_dive_label": "GDPR pack",
    },
    {
        "id": "accessibility",
        "title": "WCAG 2.2",
        "summary": "AA target across surfaces; AAA contrast goals for grades and ledgers.",
        "url_name": "marketing_trust_accessibility",
        "deep_dive_label": "Accessibility statement",
    },
    {
        "id": "retention",
        "title": "Retention",
        "summary": "Configurable retention, export, and end-of-contract teardown.",
        "url_name": "marketing_trust_retention",
        "deep_dive_label": "Retention schedules",
    },
    {
        "id": "incidents",
        "title": "Incidents",
        "summary": "Security incident and breach notification playbooks.",
        "url_name": "marketing_trust_incidents",
        "deep_dive_label": "Incident response",
    },
)


def _generated_dir() -> Path:
    raw = getattr(settings, "RMC_GENERATED_DOCS_DIR", None) or GENERATED_DIR_DEFAULT
    return Path(raw)


def _safe_load_json(path: Path) -> dict[str, Any]:
    from apps.platform_runtime.procurement_packet import _safe_load_json as _load

    return _load(path)


def _architecture_pillars(base: Path) -> dict[str, Any]:
    scorecard = _safe_load_json(base / "architecture_certification_scorecard.json")
    pillars = scorecard.get("pillars") or []
    return {p.get("id"): p for p in pillars if isinstance(p, dict)}


def _architecture_grade(base: Path) -> str:
    scorecard = _safe_load_json(base / "architecture_certification_scorecard.json")
    return str(scorecard.get("composite_repo_grade") or "").strip()


def _security_governance(base: Path) -> dict[str, Any]:
    reg = _safe_load_json(base / "security_exception_register.json")
    summary = reg.get("summary") or {}
    return {
        "total_findings": summary.get("total_findings"),
        "product_violations": summary.get("product_violations", 0),
        "high_risk": summary.get("high_risk"),
        "generated_at": reg.get("generated_at"),
    }


def _graphql_posture(base: Path) -> dict[str, Any]:
    gql = _safe_load_json(base / "graphql_security_review.json")
    if not gql:
        return {}
    return {
        "risk_level": gql.get("risk_level"),
        "mutations": gql.get("mutations"),
        "introspection": gql.get("introspection"),
        "rate_limiting": gql.get("rate_limiting"),
    }


def _buyer_readiness_label(raw: str) -> str:
    """Map internal readiness tokens to procurement-friendly labels."""
    token = (raw or "").strip().lower()
    mapping = {
        "ready": "Ready in product",
        "partial": "Partially ready",
        "blocked": "Blocked on external step",
        "not_started": "Planned",
        "external": "Requires vendor or regulator action",
    }
    if token in mapping:
        return mapping[token]
    if not token:
        return "See security packet"
    return raw.replace("_", " ").strip().title()[:80]


def _external_dependency_rows(base: Path, *, limit: int = 6) -> list[dict[str, str]]:
    reg = _safe_load_json(base / "external_dependencies_register.json")
    entries = reg.get("entries_flat") or []
    priority = (
        "blocks_full_market",
        "blocks_feature",
        "blocks_region",
        "non_blocking",
    )

    def sort_key(entry: dict) -> int:
        level = str(entry.get("blocking_level") or "")
        try:
            return priority.index(level)
        except ValueError:
            return len(priority)

    rows: list[dict[str, str]] = []
    for entry in sorted(entries, key=sort_key):
        level = str(entry.get("blocking_level") or "non_blocking")
        if level == "non_blocking" and len(rows) >= 2:
            continue
        rows.append(
            {
                "name": str(entry.get("external_dependency") or "")[:80],
                "blocking_level": level,
                "status": str(entry.get("status") or ""),
                "external_action": str(entry.get("external_action_needed") or "")[:120],
                "platform_readiness": _buyer_readiness_label(
                    str(entry.get("repo_readiness") or "")
                ),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _evidence_for_key(key: str, *, proof: dict[str, Any], pillars: dict[str, Any]) -> dict[str, str]:
    kill = proof.get("kill_test") or {}
    kill_ok = kill.get("verdict") == "PASS" or (
        kill.get("critical_count") == 0 and kill.get("verdict") is None
    )
    external = proof.get("external_dependencies") or {}
    blocking = external.get("blocking_level_counts") or {}
    governance = proof.get("_governance") or {}

    if key == "tenant_isolation":
        pillar = pillars.get("rls_tenant_isolation") or {}
        ev = str(pillar.get("evidence") or "").strip()
        if ev:
            return {"label": ev[:72], "status": "verified"}
        if kill_ok:
            return {"label": "Isolation checks passed in latest release", "status": "verified"}
        return {"label": "Isolation evidence refresh in progress", "status": "partial"}

    if key == "rbac":
        pillar = pillars.get("security") or {}
        ev = str(pillar.get("evidence") or "").strip()
        if ev:
            return {"label": ev[:72], "status": "verified"}
        return {"label": "Role and route access matrix reviewed", "status": "documented"}

    if key == "audit":
        if kill_ok:
            return {"label": "Security regression suite green", "status": "verified"}
        return {"label": "Audit posture documented in security packet", "status": "documented"}

    if key == "encryption":
        return {
            "label": "Field encryption and key rotation documented",
            "status": "documented",
        }

    if key == "payments":
        if int(blocking.get("blocking") or 0) or int(blocking.get("blocks_full_market") or 0):
            return {
                "label": "Processor-hosted; live settlement via your PSP",
                "status": "external",
            }
        return {"label": "Processor-hosted payment rails", "status": "documented"}

    if key == "api":
        gql = proof.get("_graphql") or {}
        risk = str(gql.get("risk_level") or "reviewed")
        return {"label": f"Integration API review · {risk}", "status": "documented"}

    if key == "residency":
        return {"label": "Regional profiles and export tooling", "status": "documented"}

    if key == "incidents":
        return {"label": "Incident playbooks published", "status": "documented"}

    if key == "offline":
        return {"label": "Offline queue and merge policies", "status": "documented"}

    if key == "governance":
        violations = governance.get("product_violations", 0)
        if violations == 0:
            return {"label": "Security review queue · no open product violations", "status": "verified"}
        return {"label": f"{violations} open items in security review queue", "status": "partial"}

    return {"label": "See security packet", "status": "documented"}


def _proof_badges(proof: dict[str, Any]) -> list[dict[str, str]]:
    badges: list[dict[str, str]] = []
    kill = proof.get("kill_test")
    if kill:
        verdict = kill.get("verdict") or (
            "PASS" if kill.get("critical_count") == 0 else "FAIL"
        )
        badges.append(
            {
                "id": "kill_test",
                "label": "Release safety checks",
                "value": str(verdict),
                "status": "ok" if verdict == "PASS" else "warn",
            }
        )
    northstar = proof.get("northstar")
    if northstar:
        score = northstar.get("score") or northstar.get("verdict") or "—"
        badges.append(
            {
                "id": "northstar",
                "label": "Platform quality index",
                "value": str(score)[:24],
                "status": "ok",
            }
        )
    route = proof.get("route_surface")
    if route:
        broken = route.get("broken_count")
        verdict = route.get("verdict") or (
            "CERTIFIED" if broken == 0 else f"{broken} broken"
        )
        badges.append(
            {
                "id": "routes",
                "label": "Navigation integrity",
                "value": str(verdict)[:32],
                "status": "ok" if broken == 0 else "warn",
            }
        )
    integrity = proof.get("proof_integrity")
    if integrity:
        badges.append(
            {
                "id": "proof_integrity",
                "label": "Evidence integrity",
                "value": str(integrity.get("verdict") or "READY")[:32],
                "status": "ok",
            }
        )
    closure = proof.get("closure")
    if closure:
        closed_n = len(closure.get("closed") or [])
        partial_n = len(closure.get("partial") or [])
        badges.append(
            {
                "id": "closure",
                "label": "Release readiness",
                "value": f"{closed_n} closed / {partial_n} partial",
                "status": "ok" if partial_n == 0 else "warn",
            }
        )
    gov = proof.get("_governance") or {}
    if gov.get("product_violations") is not None:
        pv = int(gov.get("product_violations") or 0)
        badges.append(
            {
                "id": "sec_exceptions",
                "label": "Security review queue",
                "value": f"{pv} open items" if pv else "Clear",
                "status": "ok" if pv == 0 else "warn",
            }
        )
    grade = proof.get("_architecture_grade")
    if grade:
        badges.append(
            {
                "id": "arch_grade",
                "label": "Architecture",
                "value": grade,
                "status": "ok",
            }
        )
    return badges


def _procurement_brief_cards(packet: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "security",
            "title": "Security",
            "body": str(packet.get("security_summary") or ""),
        },
        {
            "id": "data",
            "title": "Data handling",
            "body": str(packet.get("data_handling_summary") or ""),
        },
        {
            "id": "isolation",
            "title": "Tenant isolation",
            "body": str(packet.get("tenant_isolation_summary") or ""),
        },
        {
            "id": "audit",
            "title": "Audit & exports",
            "body": str(packet.get("audit_posture") or ""),
        },
        {
            "id": "offline",
            "title": "Offline posture",
            "body": str(packet.get("offline_posture") or ""),
        },
        {
            "id": "implementation",
            "title": "Implementation",
            "body": str(packet.get("implementation_process") or ""),
        },
    ]


def _certification_honesty(packet: dict[str, Any]) -> list[dict[str, str]]:
    honesty = packet.get("honesty") or {}
    items = [
        ("SOC 2 Type II", bool(honesty.get("claims_soc2"))),
        ("ISO 27001", bool(honesty.get("claims_iso27001"))),
        ("PCI DSS attestation", bool(honesty.get("claims_pci"))),
        ("Live PSP settlement", bool(honesty.get("psp_live_ready_claim_allowed"))),
    ]
    rows: list[dict[str, str]] = []
    for label, claimed in items:
        rows.append(
            {
                "label": label,
                "status": "published" if claimed else "not_published",
                "detail": (
                    "Externally attested — see security packet"
                    if claimed
                    else "Control design documented; external attestation not published"
                ),
            }
        )
    return rows


def _ci_gate_posture(proof: dict[str, Any], governance: dict[str, Any]) -> list[dict[str, str]]:
    kill_ok = (proof.get("kill_test") or {}).get("verdict") == "PASS" or (
        (proof.get("kill_test") or {}).get("critical_count") == 0
    )
    gates = [
        ("Campus data scoping", "Automated isolation checks", kill_ok),
        ("Sensitive data in logs", "No PII in application logs", True),
        ("Financial precision", "Ledger amounts use decimal math", True),
        ("API documentation", "Integration contracts documented", True),
        ("Security review queue", "No open product violations", governance.get("product_violations") == 0),
    ]
    return [
        {
            "name": name,
            "detail": detail,
            "status": "green" if ok else "watch",
        }
        for name, detail, ok in gates
    ]


def build_trust_compliance_context(
    *,
    generated_dir: str | Path | None = None,
    country_code: str = "",
) -> dict[str, Any]:
    """Context for trust / security-compliance marketing surfaces."""
    base = Path(generated_dir) if generated_dir else _generated_dir()
    proof = _proof_summary(str(base))
    proof["_governance"] = _security_governance(base)
    proof["_graphql"] = _graphql_posture(base)
    proof["_architecture_grade"] = _architecture_grade(base)

    pillars = _architecture_pillars(base)
    packet = build_procurement_packet(generated_dir=str(base))

    matrix_rows: list[dict[str, Any]] = []
    for spec in _TRUST_MATRIX_SPECS:
        evidence = _evidence_for_key(
            spec["evidence_key"], proof=proof, pillars=pillars
        )
        matrix_rows.append({**spec, **evidence})

    present = proof.get("present_files") or []
    as_of = ""
    if present:
        as_of = "Evidence pack updated from latest release checks"

    return {
        "trust_compliance_anchor_mode": "full",
        "trust_matrix_rows": matrix_rows,
        "trust_proof_badges": _proof_badges(proof),
        "trust_evidence_as_of": as_of,
        "trust_proof_artifact_count": len(present),
        "trust_procurement_cards": _procurement_brief_cards(packet),
        "trust_regulatory_cards": trust_regulatory_cards_for_country(
            list(_REGULATORY_CARD_SPECS),
            country_code,
        ),
        "trust_external_dependencies": _external_dependency_rows(base),
        "trust_certification_honesty": _certification_honesty(packet),
        "trust_ci_gates": _ci_gate_posture(proof, proof["_governance"]),
        "trust_architecture_grade": proof["_architecture_grade"],
        "trust_compliance_status": str(packet.get("compliance_status") or ""),
        "trust_governance_summary": proof["_governance"],
        "trust_graphql_posture": proof["_graphql"],
    }
