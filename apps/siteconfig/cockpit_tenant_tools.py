"""v4.02.8 — Tenant workspace Tools edge-tray cockpit defaults."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _


def tenant_tools_defaults() -> dict[str, Any]:
    """Right-edge Tools tab + horizontal tray for authenticated tenant portal shells.

    Mirrors manager ``operator_tools`` semantics with tenant-safe groups and
    without operator-only utilities (notebook, incidents console, impersonate).
    """
    return {
        "enabled": True,
        "layout": "edge-tray",
        "tab_label": _("Tools"),
        "tray_notebook": False,
        "hide_floating_notebook": False,
        "workflow_header_only": False,
        "back_to_top_corner": "bottom-left",
    }
