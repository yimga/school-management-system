"""Tripwire: every model carrying ``client_offline_id`` must be classified.

The recurring prod incident is tenant-schema drift on offline-sync columns added
via AddField to a pre-existing table (people.client_offline_id, schoolops
VisitorCheckIn). Those need an idempotent schema_repair heal + a forward RunPython
migration so a drifted tenant is repaired by `migrate_schemas --tenant`.

Models where the column was CREATED WITH the table (CreateModel) drift as a
missing TABLE instead — a migrate concern, not column-patchable — so they do NOT
get a heal.

This test fails the build whenever a NEW model gains a ``client_offline_id``
field, forcing the author to classify it below (and add a heal if it was an
AddField onto an existing table). It is the seal against the next whack-a-mole.
"""

from django.apps import apps
from django.test import SimpleTestCase

# Models with client_offline_id that were ADDED via AddField → MUST have a heal.
# Keep this in sync with the heals:
#   apps/people/schema_repair.py     (people/0059)
#   apps/schoolops/schema_repair.py  (schoolops/0027)
#   apps/schools/schema_repair.py    (schools/0082) — SHARED app, heals under --shared
#   apps/academics/schema_repair.py  (academics/0074) — Classroom + Attendance
_HEAL_COVERED = {
    "people.TeacherProfile",
    "people.StudentProfile",
    "people.Applicant",
    "schoolops.VisitorCheckIn",
    "schools.AdvancementGift",
    "schools.InKindDonation",
    "academics.Classroom",
    "academics.Attendance",
}

# Models that were CREATED WITH the column (CreateModel) → no heal needed
# (drift = missing TABLE, repaired by `migrate_schemas --tenant` / provisioning's
# _run_tenant_migrations, not by ADD COLUMN). Several inherit client_offline_id
# from a shared offline-capture base (apps/*/models_offline_capture.py,
# apps/schoolops/models_micro_friction.py) rather than declaring it inline.
_CREATED_WITH_COLUMN = {
    "people.StudentNote",
    "finance.OfflinePaymentIntent",
    "finance.FinanceOfflineCaptureRecord",
    "payroll.PayrollOfflineCaptureRecord",
    "schoolops.SubstituteHandoverPacketRecord",
    "schoolops.LostBelongingsTagRecord",
    "schoolops.LostBelongingsCustodyEventRecord",
}


class OfflineIdHealCoverageTripwire(SimpleTestCase):
    def test_all_client_offline_id_models_are_classified(self):
        found = set()
        for model in apps.get_models():
            try:
                model._meta.get_field("client_offline_id")
            except Exception:
                continue
            found.add(f"{model._meta.app_label}.{model.__name__}")

        classified = _HEAL_COVERED | _CREATED_WITH_COLUMN
        unclassified = found - classified
        self.assertFalse(
            unclassified,
            msg=(
                "New model(s) with a client_offline_id field are not classified: "
                f"{sorted(unclassified)}. If the column was AddField'd onto an "
                "existing table, add an idempotent heal (see "
                "apps/people/schema_repair.py + a forward RunPython migration) and "
                "list it in _HEAL_COVERED. If it was CreateModel'd with the table, "
                "list it in _CREATED_WITH_COLUMN."
            ),
        )

    def test_heal_covered_models_actually_exist(self):
        # Guard against typos / renames in the coverage list.
        for dotted in _HEAL_COVERED:
            app_label, model_name = dotted.split(".")
            self.assertIsNotNone(
                apps.get_model(app_label, model_name),
                msg=f"_HEAL_COVERED references missing model {dotted}",
            )
