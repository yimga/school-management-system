"""
Platform marketplace manifest schema (read models for catalog + governance).

This does not assert third-party certification. ``app_key`` in the JSON manifest
mirrors :class:`MarketplaceApp.slug` for cross-system identity.
"""

from __future__ import annotations

import re
from typing import Any

from apps.siteconfig.commercial_tiers import (
    COMMERCIAL_TIER_ENTERPRISE,
    COMMERCIAL_TIER_PRO,
    commercial_tier_for_school,
    normalize_commercial_tier_slug,
    tier_meets_minimum,
)

# Documented lifecycle labels for tenant catalog (UI + tests)
LIFECYCLE_AVAILABLE = "available"
LIFECYCLE_INSTALLED = "installed"  # sandbox / staged
LIFECYCLE_ACTIVE = "active"
LIFECYCLE_DISABLED = "disabled"

# Pricing labels + billing_sku wiring; Stripe Checkout and webhooks apply live charges
# (see views_billing_stripe, billing/services.finalize_marketplace_addon_payment).
PRICING_FREE = "free"
PRICING_PAID = "paid"
PRICING_INCLUDED = "included_in_plan"
PRICING_ENTERPRISE = "enterprise"

# Governance / rollout (supplement listing certification fields)
ROLLOUT_GA = "ga"
ROLLOUT_BETA = "beta"
ROLLOUT_INTERNAL = "internal"


def _merge_permission_scope_lists(*lists) -> list[str]:
    """Preserve order, de-duplicate string codes from permissions / scopes manifest keys."""
    seen: set[str] = set()
    out: list[str] = []
    for lst in lists:
        if not lst:
            continue
        for item in lst:
            code = str(item).strip()
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(code)
    return out


def platform_app_version() -> str:
    """RunMyCampus platform semver (see config.settings.APP_VERSION)."""
    try:
        from django.conf import settings

        return str(getattr(settings, "APP_VERSION", "") or "0.0.0").strip() or "0.0.0"
    except Exception:
        return "0.0.0"


def normalize_pricing_kind(raw: str) -> str:
    """Bucket for UI: free | paid | included | enterprise."""
    pt = (raw or "").strip().lower()
    if pt in ("", PRICING_INCLUDED, "included", "included_in_plan"):
        return "included"
    if pt == PRICING_FREE or pt == "free":
        return "free"
    if pt == PRICING_PAID or pt == "paid":
        return "paid"
    if pt == PRICING_ENTERPRISE or pt == "enterprise":
        return "enterprise"
    return "included"


def normalize_platform_manifest(
    raw: dict[str, Any] | None,
    *,
    app_slug: str,
    app_name: str,
    version: str,
    publisher_slug: str = "",
) -> dict[str, Any]:
    """Merge canonical keys into the app manifest dict (non-destructive for unknown keys)."""
    base: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    merged_codes = _merge_permission_scope_lists(
        base.get("permissions"),
        base.get("scopes"),
    )
    pricing_raw = (base.get("pricing_type") or PRICING_INCLUDED).strip()
    pricing_kind = normalize_pricing_kind(pricing_raw)
    pub_disp = (base.get("publisher_display_name") or "").strip()
    min_plat = (
        (base.get("min_platform_version") or base.get("min_rmc_version") or "")
        .strip()
    )
    overlay = {
        "app_key": base.get("app_key") or app_slug,
        "name": base.get("name") or app_name,
        "version": base.get("version") or version,
        "publisher": base.get("publisher") or publisher_slug or "",
        "publisher_display_name": pub_disp or base.get("publisher") or publisher_slug or "",
        "category": (base.get("category") or "").strip(),
        "required_features": list(base.get("required_features") or []),
        "required_plan": (base.get("required_plan") or "").strip(),
        "pricing_type": pricing_raw,
        "pricing_kind": pricing_kind,
        "price_display": (base.get("price_display") or "").strip(),
        "trial_available": bool(base.get("trial_available", False)),
        "billing_sku": (base.get("billing_sku") or "").strip(),
        "upgrade_message": (base.get("upgrade_message") or "").strip(),
        "permissions": merged_codes,
        "scopes": merged_codes,
        "dependencies": list(base.get("dependencies") or []),
        "installable": base.get("installable", True),
        "configurable": base.get("configurable", True),
        "rollout_status": (base.get("rollout_status") or ROLLOUT_GA).strip(),
        "rollback_supported": bool(base.get("rollback_supported", True)),
        "min_platform_version": min_plat,
        "tenant_editable_config_keys": [
            str(x).strip()
            for x in (base.get("tenant_editable_config_keys") or [])
            if str(x).strip()
        ],
        "required_commercial_tier": normalize_commercial_tier_slug(
            base.get("required_commercial_tier") or base.get("min_commercial_tier")
        ),
        "capability_bindings": list(base.get("capability_bindings") or []),
        "enabled_features": list(base.get("enabled_features") or []),
        "package_id": (base.get("package_id") or "").strip(),
    }
    merged = {**base, **overlay}
    if not merged.get("capability_bindings"):
        try:
            from apps.marketplace.capability_contract import (
                enrich_manifest_capability_bindings,
            )

            merged = enrich_manifest_capability_bindings(app_slug, merged)
        except ImportError:
            pass
    return merged


def classify_scope_access(scope_code: str, *, sensitive: bool = False) -> str:
    """
    Coarse OAuth-style tier for operator UI (manifest scopes are declarative;
    runtime enforcement remains in API policy).
    """
    code = (scope_code or "").lower()
    if sensitive or ":admin" in code or code.endswith(":admin") or ".admin" in code:
        return "admin"
    if (
        ":write" in code
        or ".write" in code
        or "write" in code
        or ":mutate" in code
    ):
        return "write"
    return "read"


def validate_manifest_keys(manifest: dict[str, Any] | None) -> list[str]:
    """Return human-readable warnings for suspicious manifest shapes (never raises)."""
    warnings: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest is not an object"]
    rf = manifest.get("required_features")
    if rf is not None and not isinstance(rf, (list, tuple)):
        warnings.append("required_features should be a list")
    pt = manifest.get("pricing_type")
    if pt is not None and str(pt) not in (
        PRICING_FREE,
        PRICING_PAID,
        PRICING_INCLUDED,
        PRICING_ENTERPRISE,
        "",
    ):
        warnings.append(f"unknown pricing_type: {pt}")
    rs = manifest.get("rollout_status")
    if rs is not None and str(rs) not in (ROLLOUT_GA, ROLLOUT_BETA, ROLLOUT_INTERNAL, ""):
        warnings.append(f"unknown rollout_status: {rs}")
    rct = manifest.get("required_commercial_tier") or manifest.get("min_commercial_tier")
    if rct is not None and str(rct).strip() and not normalize_commercial_tier_slug(rct):
        warnings.append(f"unknown required_commercial_tier: {rct}")
    tek = manifest.get("tenant_editable_config_keys")
    if tek is not None and not isinstance(tek, (list, tuple)):
        warnings.append("tenant_editable_config_keys should be a list")
    inst = manifest.get("installable")
    if inst is not None and not isinstance(inst, bool):
        warnings.append("installable should be a boolean")
    sc = manifest.get("scopes")
    if sc is not None and not isinstance(sc, (list, tuple)):
        warnings.append("scopes should be a list")
    pm = manifest.get("permissions")
    if pm is not None and not isinstance(pm, (list, tuple)):
        warnings.append("permissions should be a list")
    return warnings


def _compare_versions(installed: str, catalog: str) -> int:
    """Return -1 if installed < catalog, 0 if equal, 1 if installed > catalog."""
    if not catalog:
        return 0
    if not installed:
        return -1
    try:
        from packaging.version import Version

        vi, vc = Version(installed), Version(catalog)
        if vi < vc:
            return -1
        if vi > vc:
            return 1
        return 0
    except Exception:
        pass
    # Lexicographic fallback for non-semver strings
    si = [int(x) for x in re.findall(r"\d+", installed) or [0]]
    sc = [int(x) for x in re.findall(r"\d+", catalog) or [0]]
    maxlen = max(len(si), len(sc))
    si.extend([0] * (maxlen - len(si)))
    sc.extend([0] * (maxlen - len(sc)))
    for a, b in zip(si, sc):
        if a < b:
            return -1
        if a > b:
            return 1
    return 0


def listing_pipeline_phase(listing) -> str:
    """
    Developer/publisher pipeline foundation: coarse phase from listing.status.
    Maps to draft | pending_review | approved | rejected | suspended.
    """
    from apps.marketplace.models import MarketplaceListing

    raw = getattr(listing, "status", "") or ""
    mp = {
        MarketplaceListing.Status.DRAFT: "draft",
        MarketplaceListing.Status.PENDING_REVIEW: "pending_review",
        MarketplaceListing.Status.APPROVED: "approved",
        MarketplaceListing.Status.REJECTED: "rejected",
        MarketplaceListing.Status.SUSPENDED: "suspended",
    }
    return mp.get(str(raw), "unknown")


def compatibility_signals_for_listing(
    school,
    listing,
    manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Non-blocking readiness signals for catalog / installed views.
    Uses install compatibility checks plus manifest min_platform_version vs APP_VERSION.
    """
    manifest = manifest if isinstance(manifest, dict) else {}
    messages: list[str] = []
    ok = True
    try:
        from apps.marketplace.services import check_app_compatibility

        app = getattr(listing, "app", None)
        if app is not None:
            _listing_ok, warns, errs = check_app_compatibility(
                school, app, warn_only=True
            )
            messages.extend(errs)
            messages.extend(warns)
            if errs:
                ok = False
    except Exception:
        pass

    min_pf = (manifest.get("min_platform_version") or "").strip()
    if min_pf:
        pv = platform_app_version()
        if _compare_versions(pv, min_pf) < 0:
            ok = False
            messages.append(
                f"Platform version {pv} is below manifest minimum {min_pf}."
            )

    try:
        from apps.marketplace.listing_display import catalog_listing_display

        cd = catalog_listing_display(listing)
        min_rmc = (cd.get("min_rmc_version") or "").strip()
        if min_rmc:
            pv = platform_app_version()
            if _compare_versions(pv, min_rmc) < 0:
                ok = False
                messages.append(
                    f"Platform version {pv} is below listing minimum RMC {min_rmc}."
                )
    except Exception:
        pass

    return {"ok": ok, "messages": messages}


def governance_badge_label(
    *,
    app_kind: str,
    listing,
) -> str:
    """
    Return a single badge bucket: certified | beta | internal | verified | none.

    Listing certification / security review fields take precedence over manifest rollout.
    """
    from apps.marketplace.models import MarketplaceApp, MarketplaceListing

    meta = getattr(listing, "metadata", None) or {}
    if isinstance(meta, dict):
        badge = (meta.get("governance_badge") or "").strip().lower()
        if badge in ("certified", "beta", "internal"):
            return badge
    app = getattr(listing, "app", None)
    if app and getattr(app, "kind", "") == MarketplaceApp.AppKind.TENANT_PRIVATE:
        return "internal"
    if listing.certification_status == MarketplaceListing.ReviewStatus.APPROVED:
        return "certified"
    if listing.security_review_status == MarketplaceListing.ReviewStatus.APPROVED:
        return "verified"
    if listing.status == MarketplaceListing.Status.PENDING_REVIEW or (
        isinstance(meta, dict) and meta.get("rollout_status") == ROLLOUT_BETA
    ):
        return "beta"
    return "none"


def entitlement_hints_for_school(school, manifest: dict[str, Any] | None) -> dict[str, Any]:
    """
    Read-only hints for catalog cards: missing entitlements without mutating tenant state.
    """
    from apps.schools.models import School

    manifest = manifest if isinstance(manifest, dict) else {}
    missing: list[str] = []
    for code in manifest.get("required_features") or []:
        c = str(code).strip()
        if not c:
            continue
        try:
            from apps.billing import entitlements as entitlements_service

            ok = entitlements_service.can(school, c)
        except (AttributeError, TypeError, ValueError, ImportError):
            try:
                ok = school.has_feature(c)
            except (AttributeError, TypeError, ValueError):
                ok = False
        if not ok:
            missing.append(c)
    required_plan = (manifest.get("required_plan") or "").strip()
    plan_ok = True
    plan_slug = ""
    if required_plan:
        plan = getattr(school, "plan", None)
        plan_slug = getattr(plan, "slug", "") if plan else ""
        plan_ok = plan_slug == required_plan
    req_tier = normalize_commercial_tier_slug(
        manifest.get("required_commercial_tier") or manifest.get("min_commercial_tier")
    )
    school_tier = commercial_tier_for_school(school)
    tier_ok = tier_meets_minimum(school_tier, req_tier)
    pt_raw = str(manifest.get("pricing_type") or PRICING_INCLUDED).strip().lower()
    monetization_blocked = False
    monetization_message = ""
    billing_type = getattr(school, "billing_type", "") or ""
    bypass_paid_gate = billing_type in (
        School.BillingType.COMPLIMENTARY,
        School.BillingType.MANUAL_OVERRIDE,
    )
    if not bypass_paid_gate:
        if pt_raw == PRICING_PAID:
            if not tier_meets_minimum(school_tier, COMMERCIAL_TIER_PRO):
                monetization_blocked = True
                monetization_message = (
                    "Paid marketplace apps require Pro or Enterprise. "
                    "Open Plan & entitlements to upgrade billing, then use Get app."
                )
            elif billing_type == School.BillingType.FREE_TRIAL:
                try:
                    ba = school.billing_account
                    linked = (ba.external_customer_ref or "").strip()
                except Exception:  # noqa: BLE001
                    linked = ""
                if not linked:
                    monetization_blocked = True
                    monetization_message = (
                        "Complete subscription checkout (or link a Stripe customer) "
                        "before installing paid marketplace apps."
                    )
        elif pt_raw == PRICING_ENTERPRISE:
            if not tier_meets_minimum(school_tier, COMMERCIAL_TIER_ENTERPRISE):
                monetization_blocked = True
                monetization_message = (
                    "This app is priced for Enterprise tenants. "
                    "Open Plan & entitlements to review upgrade options."
                )

    blocked = bool(missing) or not plan_ok or not tier_ok or monetization_blocked
    upgrade_message = (
        manifest.get("upgrade_message") or ""
    ).strip() or "Upgrade your plan or enable required modules to use this app."
    if monetization_blocked and monetization_message:
        upgrade_message = (manifest.get("upgrade_message") or "").strip() or (
            monetization_message
        )
    if not tier_ok and req_tier:
        upgrade_message = (
            manifest.get("upgrade_message") or ""
        ).strip() or (
            f"This app requires a {req_tier.title()} plan or higher. "
            "Open Plan & entitlements to review your tier, then contact your account team to upgrade."
        )
    return {
        "blocked": blocked,
        "missing_features": missing,
        "required_plan_ok": plan_ok,
        "required_plan": required_plan,
        "current_plan_slug": plan_slug,
        "required_commercial_tier": req_tier,
        "current_commercial_tier": school_tier,
        "commercial_tier_ok": tier_ok,
        "upgrade_message": upgrade_message,
        "pricing_type": manifest.get("pricing_type") or PRICING_INCLUDED,
        "price_display": (manifest.get("price_display") or "").strip(),
        "trial_available": bool(manifest.get("trial_available", False)),
        "billing_sku": (manifest.get("billing_sku") or "").strip(),
        "monetization_blocked": monetization_blocked,
        "monetization_message": monetization_message,
    }


def resolve_tenant_catalog_signals(
    *,
    listing,
    school,
    installation,
    listing_installable: bool,
) -> dict[str, Any]:
    """
    Derive UX signals for tenant app catalog cards.

    Primary lifecycle is mutually exclusive for display; ``show_update`` /
    ``show_rollback`` are orthogonal flags (e.g. active + update available).
    """
    from apps.marketplace.models import AppInstallation

    app = listing.app
    manifest = normalize_platform_manifest(
        app.manifest,
        app_slug=app.slug,
        app_name=app.name,
        version=app.version,
        publisher_slug=getattr(getattr(listing, "publisher", None), "slug", "") or "",
    )
    entitlement = entitlement_hints_for_school(school, manifest)

    tenant_phase = ""
    if installation:
        tenant_phase = installation.install_phase or ""

    show_update = False
    show_rollback = False
    primary = LIFECYCLE_AVAILABLE

    if not listing_installable or getattr(listing, "kill_switch_active", False):
        primary = LIFECYCLE_DISABLED
    elif installation:
        if installation.status == AppInstallation.Status.SUSPENDED:
            primary = LIFECYCLE_DISABLED
        elif installation.install_phase == AppInstallation.InstallPhase.SANDBOX:
            primary = LIFECYCLE_INSTALLED
            show_rollback = True
        elif installation.status == AppInstallation.Status.ACTIVE:
            primary = LIFECYCLE_ACTIVE
            icv = (installation.config or {}).get("installed_catalog_version") or ""
            if _compare_versions(icv, app.version) < 0:
                show_update = True

    gov = governance_badge_label(app_kind=app.kind, listing=listing)

    icv = ""
    prev_cv = ""
    if installation:
        cfg = installation.config or {}
        icv = cfg.get("installed_catalog_version") or ""
        prev_cv = cfg.get("previous_catalog_version") or ""

    compat = compatibility_signals_for_listing(school, listing, manifest)

    rollback_ok = bool(manifest.get("rollback_supported", True))
    safe_rollback_eligible = False
    if rollback_ok and installation:
        if installation.install_phase == AppInstallation.InstallPhase.SANDBOX:
            safe_rollback_eligible = True
        elif prev_cv and show_update:
            safe_rollback_eligible = True

    disabled_sm = bool(
        not listing_installable
        or getattr(listing, "kill_switch_active", False)
        or (
            installation
            and installation.status == AppInstallation.Status.SUSPENDED
        )
    )
    active_sm = bool(
        installation
        and installation.status == AppInstallation.Status.ACTIVE
        and installation.install_phase == AppInstallation.InstallPhase.ACTIVE
        and not getattr(listing, "kill_switch_active", False)
        and listing_installable
    )
    installed_sm = installation is not None
    available_sm = bool(
        not installed_sm
        and listing_installable
        and not getattr(listing, "kill_switch_active", False)
    )

    return {
        "lifecycle": primary,
        "tenant_install_phase": tenant_phase,
        "show_update": show_update,
        "show_rollback": show_rollback,
        "governance_badge": gov,
        "manifest_ui": manifest,
        "entitlement": entitlement,
        "manifest_warnings": validate_manifest_keys(app.manifest),
        "listing_pipeline_phase": listing_pipeline_phase(listing),
        "compatibility": compat,
        "previous_catalog_version": prev_cv,
        "safe_rollback_eligible": safe_rollback_eligible and rollback_ok,
        "state_machine": {
            "available": available_sm,
            "installed": installed_sm,
            "active": active_sm,
            "disabled": disabled_sm,
            "update_available": show_update,
            "rollback_available": show_rollback,
            "installed_catalog_version": icv,
            "catalog_version": app.version,
            "previous_catalog_version": prev_cv,
            "compatibility_ok": compat.get("ok"),
            "compatibility_messages": compat.get("messages") or [],
            "safe_rollback_eligible": safe_rollback_eligible and rollback_ok,
        },
    }

