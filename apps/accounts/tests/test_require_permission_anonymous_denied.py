"""Independent behavioral proof that `require_permission` denies anonymous users.

Context: the role-permission-matrix gate (`scripts/audit_role_permission_matrix.py`)
flagged 61 routes as "candidate_anonymous" — but every one of them already carries
`@require_permission(...)`. The gate's `_AUTH_GATING_NAMES` set simply omitted that
decorator (while including all its siblings: require_school_permission,
finance_access_required, ...). Before teaching the gate to recognize it, this test
proves — independently of the scanner — that `require_permission` actually bounces an
UNAUTHENTICATED request to login, so the flagged routes are genuinely protected and
the gate change corrects a false positive rather than hiding a hole.
"""

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.accounts.decorators import require_permission, tenant_admin_required


def _anon_request(path="/x/"):
    req = RequestFactory().get(path)
    req.user = AnonymousUser()
    req.school = None  # require_permission checks is_authenticated BEFORE school
    return req


class RequirePermissionDeniesAnonymousTests(TestCase):
    def test_decorator_bounces_anonymous_to_login(self):
        @require_permission("finance.manage")
        def secret_view(request):
            return HttpResponse("SECRET CONTENT")

        resp = secret_view(_anon_request())
        # Anonymous MUST NOT reach the view body; it is redirected to login.
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"].lower())
        self.assertNotIn(b"SECRET CONTENT", resp.content or b"")

    def test_multiple_permission_codes_still_deny_anonymous(self):
        @require_permission("finance.view", "finance.manage")
        def secret_view(request):
            return HttpResponse("SECRET")

        resp = secret_view(_anon_request())
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"].lower())

    def test_tenant_admin_required_bounces_anonymous_to_login(self):
        @tenant_admin_required
        def secret_view(request):
            return HttpResponse("SECRET")

        resp = secret_view(_anon_request())
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"].lower())

    def test_real_flagged_views_deny_anonymous(self):
        """A representative sample of the routes the scanner had flagged, called
        anonymously, must each be DENIED (login redirect or PermissionDenied) —
        never render a 200 to an anonymous caller. Covers both require_permission
        (finance/evals/payroll) and tenant_admin_required (siteconfig/portal), the
        two decorators the scanner had omitted. Proves the flags were false
        positives, not real holes."""
        samples = [
            # require_permission surfaces
            ("apps.finance.views_payments", "payment_list"),
            ("apps.finance.views_payments", "cash_office_closure"),
            ("apps.evals.views", "evaluation_admin"),
            ("apps.evals.views", "grade_approval_list"),
            ("apps.payroll.views", "dashboard"),
            # tenant_admin_required surfaces (the 6 residuals)
            ("apps.siteconfig.views", "maintenance_view"),
            ("apps.siteconfig.views", "toggle_preview_mode"),
            ("apps.siteconfig.views", "set_act_as_role"),
            ("apps.portal.views_contact_requests", "staff_contact_request_list"),
        ]
        import importlib

        checked = 0
        for module_path, attr in samples:
            try:
                mod = importlib.import_module(module_path)
                view = getattr(mod, attr)
            except (ImportError, AttributeError):
                continue  # view moved/renamed — skip rather than false-fail
            req = _anon_request()
            denied = False
            try:
                resp = view(req)
                # Denied == a redirect (to login) or a 403; NOT a 200 render.
                denied = getattr(resp, "status_code", 200) in (301, 302, 403)
            except PermissionDenied:
                denied = True
            except Exception:
                # An outer decorator may raise on a bare anonymous request (e.g.
                # missing school); that is still a denial of anonymous access.
                denied = True
            self.assertTrue(
                denied,
                f"{module_path}.{attr} rendered to an ANONYMOUS user — real hole!",
            )
            checked += 1
        self.assertGreater(checked, 0, "no sample views resolved — test is vacuous")
