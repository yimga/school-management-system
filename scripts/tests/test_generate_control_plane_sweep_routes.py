"""Unit tests for control-plane sweep route classification."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "generate_control_plane_sweep_routes",
    ROOT / "scripts" / "generate_control_plane_sweep_routes.py",
)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)


def test_password_change_done_not_admin_changelist():
    path = "/admin/password_change/done/"
    assert mod._admin_changelist_only(path) is False


def test_model_changelist_still_included():
    path = "/admin/accounts/user/"
    assert mod._admin_changelist_only(path) is True


if __name__ == "__main__":
    test_password_change_done_not_admin_changelist()
    test_model_changelist_still_included()
    print("OK: generate_control_plane_sweep_routes classification")
