"""School-defined custom fields ride the rail; target identity is resolved, never guessed.

Registered 2026-09-02: ``dynamic_field_definition`` and ``dynamic_field_value``
(the ``metadata`` EAV pair every Migration Cloud lander writes behind, via
residual capture) joined ``_DERIVED_ENTITY_SPECS``. Everything mechanical --
bundle build, apply, tombstones, parity, the G4 handshake -- derives from the
registry and needed no edits. What DID need building, and what these tests hold,
is the one property no other entity has: ``DynamicFieldValue.entity_id`` is a pk
STRING naming a row in another table, invisible to the FK remap, and the two
deployments mint pks in unrelated integer spaces. So:

*   the bundle builder attaches the TARGET row's sync anchor (``entity_anchor``)
    whenever the target has one;
*   every apply path resolves the target anchor-first, then in-bundle remap,
    then pk-with-existence -- and refuses (``dfv_target_unresolved``) rather than
    attach a value to whatever row happens to sit at that integer;
*   opaque namespaces (``migration_residual:<domain>``, ``migration_artifact``)
    pass through untouched: they are grouping keys, not row references.
"""

from __future__ import annotations

from django.test import TestCase

from apps.academics.models import Department
from apps.api.sync_services import (
    _dfv_target_model,
    _get_entity_config,
    _resolve_dfv_target,
    _sync_conflict_policy,
)
from apps.metadata.models import DynamicFieldValue
from apps.schools.models import School
from apps.sync_engine.edge_outbox import build_edge_delta_rows
from apps.sync_engine.policy_registry import MergeStrategy


def _school():
    return School.objects.first() or School.objects.create(
        name="Rail High", slug="rail-high", subdomain="railhigh"
    )


class RegistrationTests(TestCase):
    def test_both_entities_are_on_the_edge_registry_only(self):
        edge = _get_entity_config(include_derived=True)
        online = _get_entity_config(include_derived=False)
        for entity in ("dynamic_field_definition", "dynamic_field_value"):
            self.assertIn(entity, edge)
            # The online DeltaSyncAPI surface stays the original three.
            self.assertNotIn(entity, online)

    def test_derived_field_sets_carry_the_data_and_the_provenance(self):
        config = _get_entity_config(include_derived=True)
        _model, dfv_fields = config["dynamic_field_value"]
        for f in ("entity_type", "entity_id", "field_key", "value_json", "source", "source_ref"):
            self.assertIn(f, dfv_fields, f)
        # school scopes the bundle, the anchor is identity -- neither is DATA.
        self.assertNotIn("school", dfv_fields)
        self.assertNotIn("client_offline_id", dfv_fields)
        _model, dfd_fields = config["dynamic_field_definition"]
        for f in ("entity_type", "field_key", "label", "data_type", "required", "validation_json", "is_active"):
            self.assertIn(f, dfd_fields, f)

    def test_both_entities_declare_a_conflict_policy(self):
        # Unclassified would mean fail-closed manual review for every offline
        # custom-field edit; these are benign school-scoped data, causal LWW.
        for entity in ("dynamic_field_definition", "dynamic_field_value"):
            strategy, protected = _sync_conflict_policy(entity)
            self.assertEqual(strategy, MergeStrategy.CAUSAL_LWW, entity)
            self.assertFalse(protected, entity)


class TargetModelVocabularyTests(TestCase):
    def test_rail_name_and_app_model_name_both_resolve(self):
        config = _get_entity_config(include_derived=True)
        self.assertIs(_dfv_target_model("department", config), Department)
        self.assertIs(_dfv_target_model("academics.department", config), Department)

    def test_opaque_namespaces_resolve_to_nothing(self):
        config = _get_entity_config(include_derived=True)
        for opaque in ("migration_residual:academics", "migration_artifact", "incident", ""):
            self.assertIsNone(_dfv_target_model(opaque, config), opaque)


class ResolveTargetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = _school()
        cls.dept = Department.objects.create(
            school=cls.school,
            name="Woodwork",
            code="WOO-RL",
            client_offline_id="box-dept-1",
        )
        cls.config = _get_entity_config(include_derived=True)

    def _changes(self, entity_id, entity_type="department"):
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "field_key": "head_count",
            "value_json": {"v": 3},
        }

    def test_anchor_resolves_to_the_local_pk(self):
        out, reason = _resolve_dfv_target(
            self.school.pk, self._changes("424242"), "box-dept-1", self.config
        )
        self.assertIsNone(reason)
        self.assertEqual(out["entity_id"], str(self.dept.pk))

    def test_unknown_anchor_is_refused_not_guessed(self):
        out, reason = _resolve_dfv_target(
            self.school.pk, self._changes("424242"), "never-existed", self.config
        )
        self.assertIsNone(out)
        self.assertEqual(reason, "target_anchor_not_found")

    def test_pk_with_a_live_row_passes_through(self):
        out, reason = _resolve_dfv_target(
            self.school.pk, self._changes(str(self.dept.pk)), "", self.config
        )
        self.assertIsNone(reason)
        self.assertEqual(out["entity_id"], str(self.dept.pk))

    def test_pk_with_no_row_is_refused(self):
        out, reason = _resolve_dfv_target(
            self.school.pk, self._changes("424242"), "", self.config
        )
        self.assertIsNone(out)
        self.assertEqual(reason, "target_not_found")

    def test_missing_target_id_is_refused(self):
        out, reason = _resolve_dfv_target(
            self.school.pk, self._changes(""), "", self.config
        )
        self.assertIsNone(out)
        self.assertEqual(reason, "target_id_missing")

    def test_opaque_namespace_passes_untouched(self):
        changes = self._changes("a12r5", entity_type="migration_residual:academics")
        out, reason = _resolve_dfv_target(self.school.pk, changes, "", self.config)
        self.assertIsNone(reason)
        self.assertEqual(out, changes)

    def test_in_bundle_remap_wins_when_there_is_no_anchor(self):
        remap = {("department", "77"): self.dept.pk}
        out, reason = _resolve_dfv_target(
            self.school.pk, self._changes("77"), "", self.config, remap=remap
        )
        self.assertIsNone(reason)
        self.assertEqual(out["entity_id"], str(self.dept.pk))


class OutboundAnchorEnrichmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = _school()
        cls.dept = Department.objects.create(
            school=cls.school,
            name="Forge",
            code="FRG-RL",
            client_offline_id="box-dept-2",
        )

    def test_bundle_row_carries_the_target_anchor(self):
        DynamicFieldValue.objects.create(
            school=self.school,
            entity_type="department",
            entity_id=str(self.dept.pk),
            field_key="head_count",
            value_json={"v": 4},
            source="import",
        )
        rows, _meta = build_edge_delta_rows(
            self.school, entities=["dynamic_field_value"]
        )
        ours = [r for r in rows if r.get("changes", {}).get("field_key") == "head_count"]
        self.assertEqual(len(ours), 1)
        self.assertEqual(ours[0].get("entity_anchor"), "box-dept-2")

    def test_anchorless_target_means_no_entity_anchor_key(self):
        # Absent means absent: a pk-portable (cloud-authored) target has no
        # anchor and the receiver falls back to pk-with-existence.
        plain = Department.objects.create(
            school=self.school, name="Loom", code="LOO-RL"
        )
        DynamicFieldValue.objects.create(
            school=self.school,
            entity_type="department",
            entity_id=str(plain.pk),
            field_key="loom_count",
            value_json={"v": 2},
            source="import",
        )
        rows, _meta = build_edge_delta_rows(
            self.school, entities=["dynamic_field_value"]
        )
        ours = [r for r in rows if r.get("changes", {}).get("field_key") == "loom_count"]
        self.assertEqual(len(ours), 1)
        self.assertNotIn("entity_anchor", ours[0])


class ApplyPathTests(TestCase):
    """End to end through _apply_changes_inner, the path a cloud pull takes."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        cls.school = _school()
        cls.staff = get_user_model().objects.create_user(
            username="dfv_rail_staff",
            password="Test1234",
            email="dfv_rail_staff@test.com",
            is_staff=True,
        )
        cls.dept = Department.objects.create(
            school=cls.school,
            name="Casting",
            code="CST-RL",
            client_offline_id="box-dept-3",
        )

    def _item(self, *, anchor, pk=987654):
        item = {
            "entity_type": "dynamic_field_value",
            "id": pk,
            "changes": {
                "entity_type": "department",
                "entity_id": "313131",  # the SENDER's pk space; must never land verbatim
                "field_key": "furnace_count",
                "value_json": {"v": 1},
                "source": "import",
                "source_ref": "bundle:9/artifact:9",
            },
            "updated_at": "2026-09-02T12:00:00+00:00",
        }
        if anchor:
            item["entity_anchor"] = anchor
        return item

    def test_cloud_pull_create_resolves_the_target_by_anchor(self):
        from apps.api.sync_services import _apply_changes_inner

        out = _apply_changes_inner(
            self.school.pk, self.staff, [self._item(anchor="box-dept-3")],
            sync_origin="cloud-pull",
        )
        self.assertEqual(out["success_count"], 1, out)
        row = DynamicFieldValue.objects.get(
            school=self.school, entity_type="department", field_key="furnace_count"
        )
        self.assertEqual(row.entity_id, str(self.dept.pk))
        self.assertNotEqual(row.entity_id, "313131")
        self.assertEqual(row.source, "import")

    def test_unresolvable_target_is_refused_with_its_own_reason(self):
        from apps.api.sync_services import _apply_changes_inner

        out = _apply_changes_inner(
            self.school.pk, self.staff, [self._item(anchor="never-existed")],
            sync_origin="cloud-pull",
        )
        self.assertEqual(out["success_count"], 0)
        result = out["results"][0]
        self.assertEqual(result["status"], 409)
        self.assertEqual(result["data"]["error"], "dfv_target_unresolved")
        self.assertFalse(
            DynamicFieldValue.objects.filter(
                school=self.school, field_key="furnace_count"
            ).exists()
        )
