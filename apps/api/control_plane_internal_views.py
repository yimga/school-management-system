# -*- coding: utf-8 -*-
"""
Internal APIs for platform control-plane automation (operator scope only).

See RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §2.1.1.
"""

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.urls import NoReverseMatch, reverse
from django.views import View

from apps.schools.control_plane import user_has_control_plane_access
from apps.schools.super_admin_bridge_registry import (
    PLATFORM_ADMIN_BRIDGE_ORDER,
    PLATFORM_ADMIN_BRIDGES,
)
from apps.schools.super_admin_paired_surfaces import (
    SUPER_FIRST_PAIRED_SPECS,
    build_surface_parity_matrix,
)


class _ControlPlaneOperatorMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Narrower than generic staff: platform operators only."""

    def test_func(self):
        return user_has_control_plane_access(getattr(self.request, "user", None))


class ControlPlaneBridgeManifestAPIView(_ControlPlaneOperatorMixin, View):
    """
    GET JSON manifest of every ``super:admin_bridge`` entry for scripts/Terraform/docsgen.

    Auth: control plane only (superuser or SUPERADMIN role), not tenant staff.
    """

    def get(self, request):
        bridges = []
        for bridge_key in PLATFORM_ADMIN_BRIDGE_ORDER:
            meta = PLATFORM_ADMIN_BRIDGES.get(bridge_key)
            if not meta:
                continue
            admin_url_name = meta.get("admin_url")
            if not admin_url_name:
                continue
            try:
                super_path = reverse(
                    "super:admin_bridge", kwargs={"bridge_key": bridge_key}
                )
            except NoReverseMatch:
                super_path = ""
            entry = {
                "bridge_key": bridge_key,
                "label": str(meta.get("label", bridge_key)),
                "description": str(meta.get("description", "")),
                "admin_url": str(admin_url_name),
                "super_bridge_path": super_path,
                "nav_id": meta.get("nav_id"),
                "show_in_nav": bool(meta.get("show_in_nav", False)),
            }
            bridges.append(entry)

        paired_super = []
        for spec in SUPER_FIRST_PAIRED_SPECS:
            super_url_name = (spec.get("super_url_name") or "").strip()
            bridge_key = (spec.get("bridge_key") or "").strip()
            entry = {
                "slug": spec["slug"],
                "label": str(spec["label"]),
                "super_url_name": super_url_name or None,
                "super_url": reverse(super_url_name) if super_url_name else None,
                "bridge_key": bridge_key or None,
            }
            if bridge_key:
                try:
                    entry["admin_bridge_path"] = reverse(
                        "super:admin_bridge", kwargs={"bridge_key": bridge_key}
                    )
                except NoReverseMatch:
                    entry["admin_bridge_path"] = ""
            paired_super.append(entry)

        parity = build_surface_parity_matrix()
        payload = {
            "version": "2026.05.16",
            "document": "docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §2.1.1",
            "bridge_count": len(bridges),
            "bridges": bridges,
            "paired_super_first": paired_super,
            "surface_spine": parity.get("spine", []),
            "surface_parity_ok": bool(parity.get("spine_ok"))
            and bool(parity.get("pairs_ok")),
            "operator_policy": reverse("super:operator_policy"),
            "platform_operator_hub": reverse("super:platform_operator_hub"),
            "configuration_center": reverse("configuration:center"),
            "platform_admin_index": reverse("admin:index"),
            "slo_targets_api": reverse("api:api-br-slo-targets"),
        }
        return JsonResponse(payload)
