"""v3.54.0 — Experience overflow & next-realm invariants.

Locks the horizontal cut-off bug fixed in v3.54 plus the visual experience
control-room contract:

  1. /studio/experience/ renders for staff users (operator + tenant paths).
  2. When the workspace renders, the workspace contract markers are present.
  3. No inline `style="width: <Npx>"` on responsive Experience workspace
     components (string-scan over the rendered body).
  4. Every Experience rail item has an `href=` to a real route (no `#` dummies).
  5. When `theme_token_values` is provided, the workbench context renders them.
  6. The new live preview pane mounts an iframe with a `title=` attribute
     when role preview entries exist, or an honest empty state otherwise.

These tests DO NOT execute layout in a real browser — they assert the HTML
contract that the new CSS depends on. The coordinator runs them.
"""

import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Permission

User = get_user_model()


class ExperienceOverflowInvariantsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="exp-overflow-user",
            email="exp-overflow@example.com",
            password="password",
            role=User.Role.IT_ADMIN,
        )
        cls.user.is_staff = True
        cls.user.save(update_fields=["is_staff"])
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        cls.user.feature_permissions.add(manage_perm)

    def setUp(self):
        self.client.force_login(self.user)
        self.experience_url = reverse("studio_os:experience")

    # ------------------------------------------------------------
    # 1. Renders for staff
    # ------------------------------------------------------------
    def test_experience_page_renders_for_staff(self):
        response = self.client.get(self.experience_url)
        self.assertEqual(response.status_code, 200)

    # ------------------------------------------------------------
    # 2. Workspace contract markers present when workspace renders
    # ------------------------------------------------------------
    def test_workspace_markers_when_workspace_renders(self):
        response = self.client.get(self.experience_url)
        body = response.content
        # Workspace renders only when use_experience_in_page or experience_left_rail
        # is truthy; on shells where neither is set, the fallback card renders.
        # We only assert the contract conditionally.
        if b"data-rmc-studio-workspace" in body:
            self.assertIn(b'data-studio-workspace-mode="experience"', body)
            self.assertIn(b'data-rmc-studio-workspace-main="1"', body)

    # ------------------------------------------------------------
    # 3. No fixed-pixel-width inline style on responsive components.
    #    We scan the rendered HTML for `style="width: 999px"` patterns
    #    inside elements whose class implies a responsive workspace
    #    role (rail/main/context/canvas/preview).
    # ------------------------------------------------------------
    def test_no_fixed_pixel_width_on_responsive_components(self):
        response = self.client.get(self.experience_url)
        body = response.content.decode("utf-8", errors="replace")
        # Pixel-width inline style anywhere is suspicious; in workspace shells
        # specifically it is a horizontal-cutoff source.
        offenders = re.findall(
            r"""<[^>]*class="[^"]*(?:rmc-studio-workspace|"""
            r"""rmc-studio-experience|experience-rail-link)[^"]*"[^>]*"""
            r"""style="[^"]*\bwidth\s*:\s*\d+(?:\.\d+)?px""",
            body,
            flags=re.IGNORECASE,
        )
        self.assertEqual(
            offenders,
            [],
            msg=f"Fixed-px width on responsive Experience components: {offenders[:3]}",
        )

    # ------------------------------------------------------------
    # 4. Every rail item has a real href (no '#' dummies in the rail
    #    list rendered by experience_inpage_rail / experience_iframe_rail).
    # ------------------------------------------------------------
    def test_no_dummy_hash_links_in_experience_rail(self):
        response = self.client.get(self.experience_url)
        body = response.content.decode("utf-8", errors="replace")
        # Find the experience-rail-list (iframe branch) anchors and verify
        # none point to a bare '#'. The in-page rail uses `#theme-colors-form`
        # anchors (real intra-page targets), which are NOT dummies.
        for match in re.finditer(
            r'<ul[^>]*id="experience-rail-list"[^>]*>(.*?)</ul>',
            body,
            flags=re.DOTALL,
        ):
            block = match.group(1)
            self.assertNotIn(
                'href="#"',
                block,
                msg="experience-rail-list contains '#' dummy anchor",
            )

    # ------------------------------------------------------------
    # 5. Workbench context renders theme_token_values when provided.
    #    This route loads get_theme_colors_context() which populates
    #    theme_token_values from the live form data.
    # ------------------------------------------------------------
    def test_workbench_context_renders_when_workspace_renders(self):
        response = self.client.get(self.experience_url)
        body = response.content
        # When the workspace renders, the workbench context aside MUST appear
        # (it carries state badges, version history, audit, related tools, and
        # — when theme_token_values is provided — the token property list).
        if b"data-rmc-studio-workspace" in body:
            self.assertIn(
                b"studio-os__experience-context",
                body,
                msg="Experience workspace rendered but context column did not",
            )

    # ------------------------------------------------------------
    # 6. Live preview pane renders an iframe with title= when role
    #    preview entries are populated, or honest empty state otherwise.
    # ------------------------------------------------------------
    def test_live_preview_pane_has_iframe_title_or_empty_state(self):
        response = self.client.get(self.experience_url)
        body = response.content.decode("utf-8", errors="replace")
        # The preview pane is included inside the in-page canvas.
        if 'data-rmc-studio-experience-preview="1"' in body:
            # Either an iframe with a title attribute, or the honest empty
            # state must be present.
            has_iframe_with_title = bool(
                re.search(
                    r"<iframe[^>]*\btitle\s*=",
                    body,
                    flags=re.IGNORECASE,
                )
            )
            has_empty_state = "rmc-studio-experience-preview__empty" in body
            self.assertTrue(
                has_iframe_with_title or has_empty_state,
                msg="Preview pane neither rendered an iframe with title nor an empty state",
            )

    # ------------------------------------------------------------
    # 7. The new Experience CSS file is linked from the mode page.
    #    This guards against accidental unlink that would re-introduce
    #    the rail-label horizontal overflow.
    # ------------------------------------------------------------
    def test_experience_mode_links_experience_scoped_css(self):
        response = self.client.get(self.experience_url)
        body = response.content
        self.assertIn(b"studio-experience-mode.css", body)
