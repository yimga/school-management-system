"""academics/0070 must not re-ADD room/timeslot school_id when 0065 already healed them."""

from __future__ import annotations

import importlib.util
import pathlib
import unittest
from unittest.mock import MagicMock, patch


_SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "migrations"
    / "0070_curriculum_allocation_and_tenant_scoped_room_timeslot.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("academics_0070", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class Academics0070IdempotentSchoolFkTests(unittest.TestCase):
    def test_migration_uses_separate_database_and_state_for_room_and_timeslot(self):
        mod = _load_migration()
        ops = mod.Migration.operations
        sep = [
            op
            for op in ops
            if op.__class__.__name__ == "SeparateDatabaseAndState"
        ]
        self.assertGreaterEqual(len(sep), 2)
        state_models = []
        for op in sep:
            for state_op in op.state_operations:
                if getattr(state_op, "model_name", None) and getattr(
                    state_op, "name", None
                ) == "school":
                    state_models.append(state_op.model_name)
        self.assertIn("room", state_models)
        self.assertIn("timeslot", state_models)

    def test_ensure_skips_when_column_already_exists(self):
        # The idempotency helper was refactored from a generic
        # _ensure_live_school_fk("Room") to _ensure_school_fk_column(
        # apps, model_attr, related_name), wrapped by ensure_room_school_fk /
        # ensure_timeslot_school_fk. The guarantee is unchanged: when school_id
        # already exists (0065 healed it), the helper must return WITHOUT opening
        # a schema_editor to re-add the field.
        mod = _load_migration()
        apps_stub = MagicMock()
        with (
            patch.object(mod, "_column_exists", return_value=True),
            patch.object(mod.connection, "schema_editor") as schema_editor,
        ):
            mod._ensure_school_fk_column(apps_stub, "Room", "academic_rooms")
            schema_editor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
