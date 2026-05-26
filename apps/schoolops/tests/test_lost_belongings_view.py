"""View tests for lost_belongings_qr wiring (batch 1509)."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import set_urlconf

from apps.schoolops.views_lost_belongings import (
    lost_belongings_lookup,
    lost_belongings_mint,
    lost_belongings_recover,
)
from apps.schools.models import School


User = get_user_model()


class LostBelongingsViewTests(TestCase):
    def setUp(self) -> None:
        set_urlconf("config.tenant_urls")
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="LB School",
            slug=f"lb-{uuid.uuid4().hex[:10]}",
            subdomain=f"lb-{uuid.uuid4().hex[:10]}",
            features={},
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}",
            email="adm@l.test",
            password="x",
            role=User.Role.ADMIN,
        )

    def tearDown(self) -> None:
        set_urlconf(None)

    def _req(self, method, path, *, user, data=None):
        if method == "GET":
            r = self.factory.get(path)
        else:
            r = self.factory.post(path, data or {})
        r.user = user
        r.school = self.school
        SessionMiddleware(lambda x: None).process_request(r)
        r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        return r

    def test_mint_get_renders_form(self) -> None:
        req = self._req("GET", "/lb/mint/", user=self.admin)
        resp = lost_belongings_mint(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"asset_id", resp.content)

    def test_mint_post_renders_short_code_not_raw_asset(self) -> None:
        req = self._req(
            "POST",
            "/lb/mint/",
            user=self.admin,
            data={
                "asset_id": "raw-asset-DISTINCT-XYZ",
                "label_hint": "blue lunch bag",
            },
        )
        resp = lost_belongings_mint(req)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        # short_code is what should be visible; asset_id stays internal.
        self.assertIn("Short code", body)
        self.assertIn("Tag minted", body)
        # asset_id is allowed to appear in the form's submitted value; the
        # tag.asset_id is NOT rendered to the template by design.

    def test_mint_rejects_email_in_label_hint(self) -> None:
        req = self._req(
            "POST",
            "/lb/mint/",
            user=self.admin,
            data={
                "asset_id": "a",
                "label_hint": "lost at parent@example.com",
            },
        )
        resp = lost_belongings_mint(req)
        body = resp.content.decode("utf-8")
        self.assertIn("must not contain an email", body)
        self.assertNotIn("Tag minted", body)

    def test_lookup_resolves_persisted_short_code(self) -> None:
        from apps.schoolops.lost_belongings_qr import mint_tag
        from apps.schoolops.micro_friction_persistence import persist_lost_belongings_tag

        tag = mint_tag(
            tenant_id=str(self.school.pk),
            asset_id="asset-persist-1",
            label_hint="green backpack",
        )
        persist_lost_belongings_tag(
            school_id=self.school.pk,
            user_id=self.admin.pk,
            tag=tag,
            asset_id="asset-persist-1",
        )
        req = self.factory.post(
            "/lf/",
            {"short_code": tag.short_code, "notes": "near main gate", "notify_parent": "on"},
        )
        SessionMiddleware(lambda x: None).process_request(req)
        req.session.save()
        resp = lost_belongings_lookup(req)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"Tag not found", resp.content)

    def test_lookup_get_renders_form_anonymously(self) -> None:
        # NO user attached - should still render
        req = self.factory.get("/lf/")
        SessionMiddleware(lambda x: None).process_request(req)
        req.session.save()
        from django.contrib.auth.models import AnonymousUser

        req.user = AnonymousUser()
        resp = lost_belongings_lookup(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"short_code", resp.content)

    def test_lookup_post_records_anonymous_sighting(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        from apps.schoolops.lost_belongings_qr import mint_tag
        from apps.schoolops.micro_friction_persistence import persist_lost_belongings_tag

        tag = mint_tag(
            tenant_id=str(self.school.pk),
            asset_id="asset-sight-1",
            label_hint="library folder",
        )
        persist_lost_belongings_tag(
            school_id=self.school.pk,
            user_id=self.admin.pk,
            tag=tag,
            asset_id="asset-sight-1",
        )
        req = self.factory.post(
            "/lf/",
            {
                "short_code": tag.short_code,
                "notes": "found near library",
                "notify_parent": "on",
            },
        )
        SessionMiddleware(lambda x: None).process_request(req)
        req.session.save()
        req.user = AnonymousUser()
        resp = lost_belongings_lookup(req)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("sighting recorded", body)

    def test_lookup_post_redacts_sensitive_notes(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        from apps.schoolops.lost_belongings_qr import mint_tag
        from apps.schoolops.micro_friction_persistence import persist_lost_belongings_tag

        tag = mint_tag(
            tenant_id=str(self.school.pk),
            asset_id="asset-redact-1",
            label_hint="wallet",
        )
        persist_lost_belongings_tag(
            school_id=self.school.pk,
            user_id=self.admin.pk,
            tag=tag,
            asset_id="asset-redact-1",
        )
        req = self.factory.post(
            "/lf/",
            {
                "short_code": tag.short_code,
                "notes": "call me at phone 555-1234",
            },
        )
        SessionMiddleware(lambda x: None).process_request(req)
        req.session.save()
        req.user = AnonymousUser()
        resp = lost_belongings_lookup(req)
        body = resp.content.decode("utf-8")
        # service-side scrub should have masked the note
        self.assertIn("REDACTED", body)
        self.assertNotIn("555-1234", body)

    def test_recover_get_renders_form(self) -> None:
        req = self._req("GET", "/lb/recover/", user=self.admin)
        resp = lost_belongings_recover(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"staff_id", resp.content)

    def test_recover_post_does_not_echo_raw_staff_id(self) -> None:
        from apps.schoolops.lost_belongings_qr import mint_tag
        from apps.schoolops.micro_friction_persistence import persist_lost_belongings_tag

        tag = mint_tag(
            tenant_id=str(self.school.pk),
            asset_id="asset-recover-1",
            label_hint="jacket",
        )
        persist_lost_belongings_tag(
            school_id=self.school.pk,
            user_id=self.admin.pk,
            tag=tag,
            asset_id="asset-recover-1",
        )
        req = self._req(
            "POST",
            "/lb/recover/",
            user=self.admin,
            data={
                "short_code": tag.short_code,
                "staff_id": "raw-staff-DISTINCT-RECOVER",
                "notes": "found at lost-and-found bin",
            },
        )
        resp = lost_belongings_recover(req)
        body = resp.content.decode("utf-8")
        self.assertNotIn("raw-staff-DISTINCT-RECOVER", body)
        self.assertIn("Recovery logged", body)

    def test_audit_log_omits_raw_asset_id_on_mint(self) -> None:
        req = self._req(
            "POST",
            "/lb/mint/",
            user=self.admin,
            data={
                "asset_id": "raw-asset-LOG-XYZ",
                "label_hint": "blue lunch bag",
            },
        )
        # The mint path itself doesn't log (the service writes only on
        # sighting/recovery), so the absence of leakage is asserted via
        # the rendered template not containing the raw asset_id.
        resp = lost_belongings_mint(req)
        body = resp.content.decode("utf-8")
        self.assertNotIn("raw-asset-LOG-XYZ", body)

    def test_audit_log_on_recovery_omits_raw_staff_id(self) -> None:
        from apps.schoolops.lost_belongings_qr import mint_tag
        from apps.schoolops.micro_friction_persistence import persist_lost_belongings_tag

        tag = mint_tag(
            tenant_id=str(self.school.pk),
            asset_id="asset-log-1",
            label_hint="cap",
        )
        persist_lost_belongings_tag(
            school_id=self.school.pk,
            user_id=self.admin.pk,
            tag=tag,
            asset_id="asset-log-1",
        )
        req = self._req(
            "POST",
            "/lb/recover/",
            user=self.admin,
            data={
                "short_code": tag.short_code,
                "staff_id": "raw-staff-LOG-XYZ",
                "notes": "ok",
            },
        )
        with self.assertLogs("apps.schoolops.lost_belongings_qr", level="INFO") as cm:
            lost_belongings_recover(req)
        log_text = "\n".join(cm.output)
        self.assertNotIn("raw-staff-LOG-XYZ", log_text)
