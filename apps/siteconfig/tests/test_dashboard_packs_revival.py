"""
Tests for the "Dashboard Packs revival" feature.

Covers the three layers of the feature:
  * the pure catalog (apps.siteconfig.dashboard_pack_catalog),
  * the resolver / precedence chain (apps.siteconfig.dashboard_pack_resolver),
  * the seed command + the per-user switcher DRF API
    (apps.api.user_preferences_api.DashboardPackPreferenceAPI).

The resolver is unit-tested with a minimal fake request (an object exposing only
``.school`` and ``.user``) so it can be exercised without an HttpRequest, mirroring
the resolver's own duck-typed ``getattr(request, ...)`` reads.
"""

from types import SimpleNamespace

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School
from apps.siteconfig import dashboard_pack_catalog as catalog
from apps.siteconfig import dashboard_pack_resolver as resolver
from apps.siteconfig.models_dashboard import (
    DashboardPack,
    DashboardPackAssignment,
    DashboardTemplate,
    DashboardUserPreference,
    TenantLayoutAssignment,
)


def _fake_request(school, user):
    """A minimal request the resolver can read (.school / .user only)."""
    return SimpleNamespace(school=school, user=user)


def _make_school(slug, sector=""):
    return School.objects.create(
        name=slug.replace("-", " ").title(),
        slug=slug,
        subdomain=slug,
        is_active=True,
        primary_sector=sector,
    )


class DashboardPackSeederTests(TestCase):
    """Case 1: the seed command is idempotent and wires templates per pack."""

    def test_seed_creates_packs_and_one_active_template_each_idempotently(self):
        call_command("seed_workflow_dashboard_packs")

        expected_codes = {row["code"] for row in catalog.DASHBOARD_PACKS}
        self.assertEqual(
            set(DashboardPack.objects.values_list("code", flat=True)),
            expected_codes,
        )
        # Exactly one active template per pack.
        for pack in DashboardPack.objects.all():
            active_templates = DashboardTemplate.objects.filter(
                dashboard_pack=pack, is_active=True
            )
            self.assertEqual(
                active_templates.count(),
                1,
                f"pack {pack.code} should have exactly one active template",
            )

        packs_after_first = DashboardPack.objects.count()
        templates_after_first = DashboardTemplate.objects.count()

        # Re-run: no duplicates.
        call_command("seed_workflow_dashboard_packs")
        self.assertEqual(DashboardPack.objects.count(), packs_after_first)
        self.assertEqual(DashboardTemplate.objects.count(), templates_after_first)

        # recommended_sectors is populated for the operations admin pack.
        ops = DashboardPack.objects.get(code="school-admin-operations")
        self.assertTrue(ops.recommended_sectors)
        self.assertIn("PUBLIC", ops.recommended_sectors)


class DashboardPackCatalogTests(TestCase):
    """Pure-catalog assertions (no DB needed but kept under TestCase for parity)."""

    def test_dashboard_template_for_pack_shape(self):
        row = catalog.DASHBOARD_PACKS[0]
        name, schema = catalog.dashboard_template_for_pack(row)
        self.assertIsInstance(name, str)
        self.assertTrue(name)
        self.assertIn("chrome", schema)
        self.assertIn("header_variant", schema["chrome"])
        self.assertIn("role_home", schema)
        self.assertIn("eyebrow", schema["role_home"])
        self.assertIn("purpose", schema["role_home"])
        self.assertIn("theme", schema)
        self.assertEqual(schema["source_pack"], row["code"])

    def test_recommended_sectors_for(self):
        ops_row = next(
            r for r in catalog.DASHBOARD_PACKS if r["code"] == "school-admin-operations"
        )
        self.assertIn("PUBLIC", catalog.recommended_sectors_for(ops_row))
        # An unlisted pack is sector-neutral (empty).
        neutral_row = next(
            r for r in catalog.DASHBOARD_PACKS if r["code"] == "teacher-planner"
        )
        self.assertEqual(catalog.recommended_sectors_for(neutral_row), [])


class DashboardPackResolverDefaultTests(TestCase):
    """Case 2: default_pack_for_role sector cascade within the admin family."""

    def setUp(self):
        call_command("seed_workflow_dashboard_packs")

    def test_assignment_role_for_user_role_mapping(self):
        self.assertEqual(resolver.assignment_role_for_user_role("BURSAR"), "ADMIN")
        self.assertEqual(
            resolver.assignment_role_for_user_role("PRINCIPAL"), "LEADERSHIP"
        )
        self.assertEqual(resolver.assignment_role_for_user_role("TEACHER"), "TEACHER")
        self.assertEqual(
            resolver.assignment_role_for_user_role("SOMETHING_UNKNOWN"), "ADMIN"
        )

    def test_assignment_roles_match_role_choices(self):
        self.assertEqual(
            set(resolver.assignment_roles()),
            {choice[0] for choice in TenantLayoutAssignment.ROLE_CHOICES},
        )

    def test_public_sector_admin_resolves_to_operations(self):
        school = _make_school("public-school", sector="PUBLIC")
        pack = resolver.default_pack_for_role(school, "ADMIN")
        self.assertIsNotNone(pack)
        self.assertEqual(pack.code, "school-admin-operations")

    def test_private_sector_admin_resolves_to_executive(self):
        school = _make_school("private-school", sector="PRIVATE")
        pack = resolver.default_pack_for_role(school, "ADMIN")
        self.assertIsNotNone(pack)
        self.assertEqual(pack.code, "school-admin-executive")

    def test_unknown_sector_admin_falls_back_to_first_in_family(self):
        school = _make_school("mystery-school", sector="WAKANDA")
        pack = resolver.default_pack_for_role(school, "ADMIN")
        self.assertIsNotNone(pack)
        # first active pack in the "admin" family by name ordering.
        expected = (
            DashboardPack.objects.filter(is_active=True, family="admin")
            .order_by("name")
            .first()
        )
        self.assertEqual(pack.code, expected.code)


class DashboardPackReachabilityTests(TestCase):
    """No seeded pack family is orphaned: every family is switchable by some role."""

    def setUp(self):
        call_command("seed_workflow_dashboard_packs")

    def test_every_seeded_family_is_reachable_by_some_role(self):
        seeded_families = {row["family"] for row in catalog.DASHBOARD_PACKS}
        reachable = set()
        for role in resolver.assignment_roles():
            for pack in resolver.available_packs_for_role(role):
                obj = DashboardPack.objects.get(code=pack["code"])
                reachable.add(obj.family)
        orphaned = seeded_families - reachable
        self.assertEqual(orphaned, set(), f"orphaned (unreachable) families: {orphaned}")

    def test_admin_bucket_can_switch_to_finance_specialized_pack(self):
        codes = {p["code"] for p in resolver.available_packs_for_role("ADMIN")}
        self.assertIn("bursar-collection-rate", codes)
        self.assertIn("finance-office-ledger", codes)


class DashboardPackAssignmentTests(TestCase):
    """Case 3: assign_default_dashboard_packs (apply / dry-run / idempotent)."""

    def setUp(self):
        call_command("seed_workflow_dashboard_packs")
        self.school = _make_school("assign-school", sector="PUBLIC")

    def test_apply_creates_assignments_for_each_role_with_a_pack(self):
        summary = resolver.assign_default_dashboard_packs(self.school, apply=True)

        # Every role that resolved to a pack got both records.
        roles_with_pack = [
            r
            for r in resolver.assignment_roles()
            if resolver.default_pack_for_role(self.school, r) is not None
        ]
        self.assertEqual(
            summary["pack_assignments_created"], len(roles_with_pack)
        )
        self.assertEqual(
            DashboardPackAssignment.objects.filter(school=self.school).count(),
            len(roles_with_pack),
        )
        # Layout assignments need a template; all seeded packs have one.
        self.assertEqual(
            summary["layout_assignments_created"], len(roles_with_pack)
        )
        self.assertEqual(
            TenantLayoutAssignment.objects.filter(school=self.school).count(),
            len(roles_with_pack),
        )

    def test_apply_is_idempotent(self):
        resolver.assign_default_dashboard_packs(self.school, apply=True)
        pack_count = DashboardPackAssignment.objects.filter(school=self.school).count()
        layout_count = TenantLayoutAssignment.objects.filter(school=self.school).count()

        summary = resolver.assign_default_dashboard_packs(self.school, apply=True)
        self.assertEqual(summary["pack_assignments_created"], 0)
        self.assertEqual(summary["layout_assignments_created"], 0)
        self.assertEqual(
            DashboardPackAssignment.objects.filter(school=self.school).count(),
            pack_count,
        )
        self.assertEqual(
            TenantLayoutAssignment.objects.filter(school=self.school).count(),
            layout_count,
        )

    def test_dry_run_writes_nothing(self):
        summary = resolver.assign_default_dashboard_packs(self.school, apply=False)
        self.assertFalse(summary["applied"])
        self.assertEqual(
            DashboardPackAssignment.objects.filter(school=self.school).count(), 0
        )
        self.assertEqual(
            TenantLayoutAssignment.objects.filter(school=self.school).count(), 0
        )
        # The dry run still reports which roles it would assign.
        self.assertTrue(summary["roles"])


class DashboardPackOverlayTests(TestCase):
    """Case 4: overlay_role_home provenance + tenant_layout overlay."""

    def setUp(self):
        call_command("seed_workflow_dashboard_packs")
        self.school = _make_school("overlay-school", sector="PUBLIC")
        self.user = User.objects.create_user(
            username="overlay_admin",
            password="testpass123",
            role=User.Role.ADMIN,
        )

    def _role_home(self):
        return {
            "eyebrow": "Original eyebrow",
            "title": "Original title",
            "destinations": [{"label": "Home", "url": "/"}],
        }

    def test_overlay_no_assignments_keeps_content_and_marks_default(self):
        request = _fake_request(self.school, self.user)
        base = self._role_home()
        result = resolver.overlay_role_home(base, request)

        # Returns a NEW dict and never mutates the caller's.
        self.assertIsNot(result, base)
        self.assertNotIn("dashboard_pack", base)

        # Original content preserved.
        self.assertEqual(result["title"], "Original title")
        self.assertEqual(result["destinations"], [{"label": "Home", "url": "/"}])

        # Provenance present with source == "default".
        self.assertIn("dashboard_pack", result)
        self.assertEqual(result["dashboard_pack"]["source"], "default")
        # eyebrow never blank.
        self.assertTrue(result["eyebrow"])

    def test_overlay_tenant_layout_eyebrow_wins(self):
        # Build a template with a known role_home.eyebrow and assign it.
        pack = DashboardPack.objects.filter(family="admin", is_active=True).first()
        template = DashboardTemplate.objects.create(
            dashboard_pack=pack,
            name="Overlay Admin Custom",
            config_schema={
                "chrome": {"header_variant": "standard"},
                "role_home": {"eyebrow": "Overlaid Admin Eyebrow"},
                "theme": {},
            },
            is_active=True,
        )
        TenantLayoutAssignment.objects.create(
            school=self.school,
            role="ADMIN",
            template=template,
            is_active=True,
        )

        request = _fake_request(self.school, self.user)
        result = resolver.overlay_role_home(self._role_home(), request)

        self.assertEqual(result["eyebrow"], "Overlaid Admin Eyebrow")
        self.assertEqual(result["dashboard_pack"]["source"], "tenant_layout")


class DashboardPackPrecedenceTests(TestCase):
    """Case 5: per-user choice beats the tenant_layout assignment."""

    def setUp(self):
        call_command("seed_workflow_dashboard_packs")
        self.school = _make_school("precedence-school", sector="PUBLIC")
        self.user = User.objects.create_user(
            username="precedence_admin",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        # A tenant layout assignment exists (lower precedence than user choice).
        resolver.assign_default_dashboard_packs(self.school, apply=True)

    def test_user_choice_overrides_tenant_layout(self):
        coarse_role = resolver.assignment_role_for_user_role(self.user.role)
        # Pick an available pack for this user's role that is NOT the layout default.
        available = resolver.available_packs_for_role(coarse_role)
        self.assertTrue(available)
        chosen_code = available[0]["code"]

        prefs, _ = DashboardUserPreference.objects.get_or_create(user=self.user)
        prefs.set_dashboard_pack(coarse_role, chosen_code)
        prefs.save()

        # Load a fresh user for the request so the reverse OneToOne accessor reads the
        # saved preference (in production request.user is loaded fresh per request).
        fresh_user = User.objects.get(pk=self.user.pk)
        request = _fake_request(self.school, fresh_user)
        self.assertTrue(fresh_user.is_authenticated)
        resolved = resolver.resolve_effective_template(request)

        self.assertEqual(resolved["source"], "user")
        self.assertEqual(resolved["pack_code"], chosen_code)


class DashboardPackDepthTests(TestCase):
    """Depth: config_schema drives module visibility + KPI priority, not just chrome."""

    def setUp(self):
        call_command("seed_workflow_dashboard_packs")
        self.school = _make_school("depth-school", sector="PUBLIC")
        self.user = User.objects.create_user(
            username="depth_admin",
            password="testpass123",
            role=User.Role.ADMIN,
        )

    def test_config_schema_carries_modules_and_kpis(self):
        finance_row = next(
            r for r in catalog.DASHBOARD_PACKS if r["code"] == "finance-office-ledger"
        )
        _name, schema = catalog.dashboard_template_for_pack(finance_row)
        self.assertIn("modules", schema)
        # Finance hides the academic "top_performing" module.
        self.assertFalse(schema["modules"].get("top_performing", True))
        self.assertTrue(schema["kpis"])  # non-empty ordered KPI priority

    def test_same_family_packs_render_distinctly(self):
        _n1, s1 = catalog.dashboard_template_for_pack(
            next(r for r in catalog.DASHBOARD_PACKS if r["code"] == "teacher-gradebook-quick")
        )
        _n2, s2 = catalog.dashboard_template_for_pack(
            next(r for r in catalog.DASHBOARD_PACKS if r["code"] == "teacher-planner")
        )
        # The two teacher packs differ in module config (planner off vs on).
        self.assertNotEqual(s1["modules"], s2["modules"])

    def test_overlay_attaches_modules_and_kpis(self):
        pack = DashboardPack.objects.filter(family="finance", is_active=True).first()
        template = DashboardTemplate.objects.filter(
            dashboard_pack=pack, is_active=True
        ).first()
        TenantLayoutAssignment.objects.create(
            school=self.school, role="ADMIN", template=template, is_active=True
        )
        result = resolver.overlay_role_home(
            {"eyebrow": "x", "title": "t"}, _fake_request(self.school, self.user)
        )
        self.assertIn("dashboard_modules", result)
        self.assertIn("dashboard_kpis", result)
        self.assertEqual(result["dashboard_pack"]["source"], "tenant_layout")


class DashboardPackPortalDepthTests(TestCase):
    """Portal depth: a pack hides specific cockpit sections (default-visible)."""

    def setUp(self):
        call_command("seed_workflow_dashboard_packs")
        self.school = _make_school("portal-depth-school", sector="PUBLIC")
        self.user = User.objects.create_user(
            username="pd_parent",
            password="testpass123",
            role=User.Role.PARENT,
        )

    def test_config_schema_carries_hidden_sections(self):
        row = next(
            r for r in catalog.DASHBOARD_PACKS if r["code"] == "parent-payments"
        )
        _name, schema = catalog.dashboard_template_for_pack(row)
        self.assertIn("sections", schema)
        self.assertEqual(schema["sections"].get("parent__sibling_compare"), False)

    def test_unassigned_school_hides_nothing(self):
        from apps.siteconfig.context_processors import (
            dashboard_pack_switcher_context,
        )

        ctx = dashboard_pack_switcher_context(_fake_request(self.school, self.user))
        self.assertEqual(ctx["dashboard_pack_hidden_sections"], [])

    def test_assigned_pack_hides_its_sections(self):
        from apps.siteconfig.context_processors import (
            dashboard_pack_switcher_context,
        )

        pack = DashboardPack.objects.get(code="parent-payments")
        template = DashboardTemplate.objects.filter(
            dashboard_pack=pack, is_active=True
        ).first()
        TenantLayoutAssignment.objects.create(
            school=self.school, role="PARENT", template=template, is_active=True
        )
        fresh_user = User.objects.get(pk=self.user.pk)
        ctx = dashboard_pack_switcher_context(
            _fake_request(self.school, fresh_user)
        )
        hidden = ctx["dashboard_pack_hidden_sections"]
        self.assertIn("parent__sibling_compare", hidden)
        self.assertIn("parent__life_event_timeline", hidden)


class DashboardPackBreadthTests(TestCase):
    """Breadth: every coarse role now has a switchable set (students included)."""

    def setUp(self):
        call_command("seed_workflow_dashboard_packs")

    def test_student_family_is_now_switchable(self):
        available = resolver.available_packs_for_role("STUDENT")
        self.assertGreaterEqual(len(available), 2)
        codes = {p["code"] for p in available}
        self.assertIn("student-focus-today", codes)
        self.assertIn("student-progress-tracker", codes)

    def test_every_coarse_role_has_at_least_one_pack(self):
        for role in resolver.assignment_roles():
            self.assertTrue(
                resolver.available_packs_for_role(role),
                f"role {role} has no switchable packs",
            )


class DashboardPackCrossShellTests(TestCase):
    """All-shells expansion: portal chrome honors per-user choice + global switcher context."""

    def setUp(self):
        call_command("seed_workflow_dashboard_packs")
        self.school = _make_school("xshell-school", sector="PUBLIC")
        self.user = User.objects.create_user(
            username="xshell_teacher",
            password="testpass123",
            role=User.Role.TEACHER,
        )

    def test_portal_chrome_template_honors_user_choice(self):
        from apps.siteconfig.portal_chrome import (
            resolve_dashboard_template_for_request,
        )

        coarse = resolver.assignment_role_for_user_role(self.user.role)
        chosen = resolver.available_packs_for_role(coarse)[0]["code"]
        prefs, _ = DashboardUserPreference.objects.get_or_create(user=self.user)
        prefs.set_dashboard_pack(coarse, chosen)
        prefs.save()

        fresh_user = User.objects.get(pk=self.user.pk)
        template = resolve_dashboard_template_for_request(
            _fake_request(self.school, fresh_user)
        )
        self.assertIsNotNone(template)
        self.assertEqual(template.dashboard_pack.code, chosen)

    def test_switcher_context_processor_enabled_for_multi_pack_role(self):
        from apps.siteconfig.context_processors import (
            dashboard_pack_switcher_context,
        )

        fresh_user = User.objects.get(pk=self.user.pk)
        ctx = dashboard_pack_switcher_context(
            _fake_request(self.school, fresh_user)
        )["dashboard_pack_switcher"]
        self.assertTrue(ctx["enabled"])
        self.assertEqual(ctx["role"], "TEACHER")
        self.assertTrue(ctx["endpoint"])
        self.assertGreater(len(ctx["available"]), 1)

    def test_switcher_context_processor_disabled_without_school(self):
        from apps.siteconfig.context_processors import (
            dashboard_pack_switcher_context,
        )

        ctx = dashboard_pack_switcher_context(
            _fake_request(None, self.user)
        )["dashboard_pack_switcher"]
        self.assertFalse(ctx["enabled"])


class DashboardPackPreferenceApiTests(TestCase):
    """Case 6: the DRF switcher API GET/PATCH contract."""

    def setUp(self):
        call_command("seed_workflow_dashboard_packs")
        self.user = User.objects.create_user(
            username="api_teacher",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        self.url = reverse("api:dashboard-pack-preference")

    def test_get_returns_role_and_available_packs(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["role"], "TEACHER")
        self.assertEqual(payload["selected"], "")
        codes = {p["code"] for p in payload["available"]}
        # Teacher family packs are offered.
        self.assertIn("teacher-planner", codes)
        # Packs from another family are not.
        self.assertNotIn("school-admin-operations", codes)

    def test_patch_allowed_code_persists(self):
        self.client.force_login(self.user)
        response = self.client.patch(
            self.url,
            data={"dashboard_pack": "teacher-planner"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["selected"], "teacher-planner")

        prefs = DashboardUserPreference.objects.get(user=self.user)
        self.assertEqual(prefs.get_dashboard_pack("TEACHER"), "teacher-planner")

    def test_patch_bogus_code_rejected(self):
        self.client.force_login(self.user)
        response = self.client.patch(
            self.url,
            data={"dashboard_pack": "this-code-does-not-exist"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_empty_clears_choice(self):
        self.client.force_login(self.user)
        # First set a value...
        self.client.patch(
            self.url,
            data={"dashboard_pack": "teacher-planner"},
            content_type="application/json",
        )
        # ...then clear it.
        response = self.client.patch(
            self.url,
            data={"dashboard_pack": ""},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selected"], "")
        prefs = DashboardUserPreference.objects.get(user=self.user)
        self.assertEqual(prefs.get_dashboard_pack("TEACHER"), "")


class DashboardPackPreviewCatalogTests(TestCase):
    """Phase 4b: display-label SOT + honest, config-derived pack_preview."""

    def test_family_label_known_and_fallback(self):
        self.assertEqual(catalog.family_label("admin"), "Admin")
        self.assertEqual(catalog.family_label("it_admin"), "IT")
        # Unknown family → title-cased slug; empty → "Other".
        self.assertEqual(catalog.family_label("some_new_family"), "Some New Family")
        self.assertEqual(catalog.family_label(""), "Other")

    def test_kpi_and_theme_labels(self):
        self.assertEqual(catalog.kpi_label("recent_admissions"), "Admissions")
        self.assertEqual(catalog.kpi_label("mystery_kpi"), "Mystery Kpi")
        self.assertEqual(catalog.theme_label("soft-glass"), "Soft glass")
        self.assertEqual(catalog.theme_label("crisp-professional"), "Crisp")

    def test_pack_preview_is_config_derived(self):
        preview = catalog.pack_preview("school-admin-executive", "admin")
        self.assertEqual(
            preview["header_variant"], catalog.FAMILY_HEADER_VARIANT["admin"]
        )
        self.assertTrue(preview["kpis"])
        self.assertEqual(preview["kpi_count"], len(preview["kpis"]))
        self.assertIn("id", preview["kpis"][0])
        self.assertIn("label", preview["kpis"][0])
        # The preview theme matches what the seeded template config carries.
        _name, schema = catalog.dashboard_template_for_pack(
            next(
                r
                for r in catalog.DASHBOARD_PACKS
                if r["code"] == "school-admin-executive"
            )
        )
        self.assertEqual(
            preview["theme"], schema.get("theme", {}).get("visual_preset", "")
        )


class DashboardPackGroupingTests(TestCase):
    """Phase 4b: enriched packs + family grouping (primary first, nothing dropped)."""

    def setUp(self):
        call_command("seed_workflow_dashboard_packs")

    def test_available_packs_are_enriched(self):
        packs = resolver.available_packs_for_role("ADMIN")
        self.assertTrue(packs)
        pack = packs[0]
        for key in (
            "code",
            "name",
            "description",
            "family",
            "family_label",
            "kpis",
            "kpi_count",
            "focus_areas",
            "theme",
            "theme_label",
            "header_variant",
        ):
            self.assertIn(key, pack)

    def test_grouping_primary_first_and_covers_every_pack(self):
        user = User.objects.create_user(
            username="group_admin", password="testpass123", role=User.Role.ADMIN
        )
        grouped = resolver.grouped_available_packs_for_user(user)

        self.assertEqual(grouped["primary_family"], "admin")
        self.assertTrue(grouped["groups"])
        self.assertTrue(grouped["groups"][0]["is_primary"])
        # Exactly one primary group.
        self.assertEqual(
            sum(1 for g in grouped["groups"] if g["is_primary"]), 1
        )
        # Every switchable pack appears exactly once across the groups.
        flat = [p["code"] for g in grouped["groups"] for p in g["packs"]]
        avail = [p["code"] for p in resolver.available_packs_for_role("ADMIN")]
        self.assertEqual(sorted(flat), sorted(avail))
        self.assertEqual(len(flat), len(set(flat)))

    def test_selected_pack_family_floats_to_primary(self):
        user = User.objects.create_user(
            username="group_bursar", password="testpass123", role=User.Role.ADMIN
        )
        grouped = resolver.grouped_available_packs_for_user(
            user, selected_code="finance-office-ledger"
        )
        self.assertEqual(grouped["primary_family"], "finance")
        self.assertTrue(grouped["groups"][0]["is_primary"])
        self.assertEqual(grouped["groups"][0]["family"], "finance")


class DashboardPackSwitcherRenderTests(TestCase):
    """Phase 4b: the switcher context + template render end-to-end."""

    def setUp(self):
        call_command("seed_workflow_dashboard_packs")
        self.school = _make_school("render-school", sector="PRIVATE")
        self.user = User.objects.create_user(
            username="render_admin", password="testpass123", role=User.Role.ADMIN
        )

    def _switcher_context(self):
        from apps.siteconfig.context_processors import (
            dashboard_pack_switcher_context,
        )

        fresh_user = User.objects.get(pk=self.user.pk)
        return dashboard_pack_switcher_context(_fake_request(self.school, fresh_user))

    def test_context_exposes_groups_and_primary_family(self):
        ctx = self._switcher_context()["dashboard_pack_switcher"]
        self.assertTrue(ctx["enabled"])
        self.assertTrue(ctx["groups"])
        self.assertEqual(ctx["primary_family"], "admin")
        self.assertTrue(ctx["groups"][0]["is_primary"])
        # A fresh admin has no explicit choice → header shows the school default.
        self.assertIsNone(ctx["selected_pack"])
        # The admin bucket switches across many families, so there are "other" packs.
        self.assertGreater(ctx["other_pack_count"], 0)
        # Flat "available" is preserved (length gate + API parity) and matches groups.
        grouped_codes = sorted(
            p["code"] for g in ctx["groups"] for p in g["packs"]
        )
        self.assertEqual(
            grouped_codes, sorted(p["code"] for p in ctx["available"])
        )
        # other_pack_count == every non-primary pack.
        primary_count = len(ctx["groups"][0]["packs"])
        self.assertEqual(
            ctx["other_pack_count"], len(ctx["available"]) - primary_count
        )

    def test_template_renders_grouped_cards_with_previews(self):
        from django.template.loader import render_to_string

        html = render_to_string(
            "components/dashboard_pack_switcher.html", self._switcher_context()
        )
        self.assertIn("Choose your dashboard", html)
        self.assertIn('name="dashboard_pack"', html)  # radios preserved
        self.assertIn("rmc-dpk__summary-title", html)  # full-width header bar
        self.assertIn("rmc-dpk-card", html)  # card grammar
        self.assertIn("rmc-dpk-preview", html)  # mini-layout schematic
        self.assertIn("rmc-dpk-chip--kpi", html)  # real KPI chips
        self.assertIn("Your dashboards", html)  # primary group label
        self.assertIn("Other role dashboards", html)  # collapsible other-families
        self.assertIn("School default", html)  # reset option retained
