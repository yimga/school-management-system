"""North-star recommended steps for role home (N1, N2, N8, N13, N27–N29)."""

from django.test import SimpleTestCase

from apps.dashboard.north_star_guidance import build_north_star_recommended_steps


class NorthStarGuidanceTests(SimpleTestCase):
    def test_admin_zero_data_bootstrap(self):
        steps = build_north_star_recommended_steps(
            "ADMIN",
            {
                "can_manage_people": True,
                "can_manage_settings": True,
                "can_manage_rbac": True,
                "can_use_messages": True,
            },
            workflow_progress={"students": 0, "teachers": 0},
        )
        ids = [s["action_id"] for s in steps]
        self.assertIn("add_student", ids)
        self.assertIn("add_teacher", ids)
        self.assertIn("setup_studio", ids)
        self.assertIn("roles_permissions", ids)
        self.assertIn("document_library", ids)
        self.assertIn("announcements", ids)

    def test_registrar_onboard_enrollment(self):
        steps = build_north_star_recommended_steps(
            "REGISTRAR",
            {
                "can_manage_people": True,
                "can_manage_settings": False,
                "can_manage_rbac": False,
            },
            workflow_progress={"students": 1, "teachers": 1},
        )
        ids = [s["action_id"] for s in steps]
        self.assertIn("onboard_student", ids)
        self.assertIn("workflow_center", ids)

    def test_it_admin_roles_when_missing_rbac_perm(self):
        steps = build_north_star_recommended_steps(
            "IT_ADMIN",
            {
                "can_manage_settings": False,
                "can_manage_rbac": False,
                "can_use_messages": False,
            },
            workflow_progress={},
        )
        ids = [s["action_id"] for s in steps]
        self.assertIn("roles_permissions", ids)

    def test_librarian_workflow_and_documents(self):
        steps = build_north_star_recommended_steps(
            "LIBRARIAN",
            {"can_manage_settings": True},
            workflow_progress={},
        )
        ids = [s["action_id"] for s in steps]
        self.assertIn("workflow_center", ids)
        self.assertIn("document_library", ids)

    def test_bursar_finance_invoice(self):
        steps = build_north_star_recommended_steps("BURSAR", {}, workflow_progress={})
        ids = [s["action_id"] for s in steps]
        self.assertIn("finance_console", ids)
        self.assertIn("create_invoice", ids)

    def test_teacher_import_grades(self):
        steps = build_north_star_recommended_steps("TEACHER", {}, workflow_progress={})
        self.assertIn("import_grades", [s["action_id"] for s in steps])

    def test_dean_workflow_and_ews_when_reports(self):
        steps = build_north_star_recommended_steps(
            "DEAN",
            {"can_manage_reports": True},
            workflow_progress={},
        )
        ids = [s["action_id"] for s in steps]
        self.assertIn("workflow_center", ids)
        self.assertIn("manage_exams", ids)

    def test_principal_ews_without_duplicating_dean_logic(self):
        steps = build_north_star_recommended_steps(
            "PRINCIPAL",
            {
                "can_manage_settings": True,
                "can_manage_rbac": True,
                "can_manage_reports": True,
                "can_use_messages": True,
            },
            workflow_progress={"students": 1, "teachers": 1},
        )
        ids = [s["action_id"] for s in steps]
        self.assertIn("manage_exams", ids)
        self.assertLessEqual(len(steps), 8)
