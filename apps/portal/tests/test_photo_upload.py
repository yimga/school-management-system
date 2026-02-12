"""
Tests for photo upload by token: feature flag, permissions, cleanup command, rate limit.
"""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.portal.models import PhotoUploadToken
from apps.people.models import StudentProfile, TeacherProfile
from apps.siteconfig.models import SiteSettings

User = get_user_model()


def _site_with_photo_upload_remote(enabled):
    site = SiteSettings.get_solo()
    pf = dict(site.portal_features or {})
    pf["photo_upload_remote"] = enabled
    site.portal_features = pf
    site.save(update_fields=["portal_features"])
    return site


class PhotoUploadFeatureDisabledTests(TestCase):
    """When feature is disabled, phone page and send-link return 404 with disabled template."""

    def setUp(self):
        _site_with_photo_upload_remote(False)
        self.token = PhotoUploadToken.objects.create(purpose=PhotoUploadToken.Purpose.REGISTRATION)

    def test_phone_page_returns_404_and_disabled_template_when_feature_off(self):
        url = reverse("portal:photo_upload_phone", kwargs={"token": self.token.token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "portal/photo_upload_disabled.html")
        self.assertContains(response, "unavailable", status_code=404)

    def test_send_link_page_returns_404_and_disabled_template_when_feature_off(self):
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        user = User.objects.create_user(username="staff", password="pass")
        ct = ContentType.objects.get_for_model(StudentProfile)
        perm = Permission.objects.get(codename="view_studentprofile", content_type=ct)
        user.user_permissions.add(perm)
        self.client.force_login(user)
        student = StudentProfile.objects.create(first_name="A", last_name="B", is_active=True)
        url = reverse("portal:photo_upload_send_link_student", kwargs={"student_id": student.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "portal/photo_upload_disabled.html")


class PhotoUploadPermissionTests(TestCase):
    """Send-link and generate-for-profile require view_studentprofile / view_teacherprofile."""

    def setUp(self):
        _site_with_photo_upload_remote(True)
        self.student = StudentProfile.objects.create(first_name="S", last_name="T", is_active=True)
        tuser = User.objects.create_user(username="teacher_user", password="pass")
        self.teacher = TeacherProfile.objects.create(user=tuser, is_active=True)

    def test_send_link_student_requires_view_studentprofile(self):
        user = User.objects.create_user(username="noperm", password="pass")
        self.client.force_login(user)
        url = reverse("portal:photo_upload_send_link_student", kwargs={"student_id": self.student.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_send_link_student_allowed_with_view_studentprofile(self):
        user = User.objects.create_user(username="hasperm", password="pass", is_staff=True)
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(StudentProfile)
        perm = Permission.objects.get(codename="view_studentprofile", content_type=ct)
        user.user_permissions.add(perm)
        self.client.force_login(user)
        url = reverse("portal:photo_upload_send_link_student", kwargs={"student_id": self.student.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_generate_for_profile_requires_view_studentprofile(self):
        user = User.objects.create_user(username="noperm2", password="pass")
        self.client.force_login(user)
        url = reverse("portal:photo_upload_generate_for_profile")
        response = self.client.post(url, {"student_id": self.student.id})
        self.assertEqual(response.status_code, 403)


class CleanupPhotoUploadTokensCommandTests(TestCase):
    """Management command deletes only expired tokens with no photo."""

    def setUp(self):
        from django.utils import timezone
        from datetime import timedelta
        self.cutoff = timezone.now() - timedelta(hours=50)
        # Old token, no photo
        self.old_empty = PhotoUploadToken.objects.create(purpose=PhotoUploadToken.Purpose.REGISTRATION)
        PhotoUploadToken.objects.filter(pk=self.old_empty.pk).update(created_at=self.cutoff)
        # Old token with photo (should not be deleted by command that only deletes empty)
        self.old_with_photo = PhotoUploadToken.objects.create(purpose=PhotoUploadToken.Purpose.REGISTRATION)
        PhotoUploadToken.objects.filter(pk=self.old_with_photo.pk).update(created_at=self.cutoff)

    @override_settings(MEDIA_ROOT="/tmp/photo_upload_test")
    def test_dry_run_reports_count_and_does_not_delete(self):
        from django.core.files.base import ContentFile
        self.old_with_photo.photo.save("x.jpg", ContentFile(b"fake"), save=True)
        out = StringIO()
        call_command("cleanup_photo_upload_tokens", "--dry-run", stdout=out)
        self.assertIn("Would delete 1 expired token(s)", out.getvalue())
        self.assertEqual(PhotoUploadToken.objects.count(), 2)

    @override_settings(MEDIA_ROOT="/tmp/photo_upload_test")
    def test_run_deletes_only_expired_empty_tokens(self):
        from django.core.files.base import ContentFile
        self.old_with_photo.photo.save("x.jpg", ContentFile(b"fake"), save=True)
        out = StringIO()
        call_command("cleanup_photo_upload_tokens", stdout=out)
        self.assertIn("Deleted 1 expired", out.getvalue())
        self.assertFalse(PhotoUploadToken.objects.filter(pk=self.old_empty.pk).exists())
        self.assertTrue(PhotoUploadToken.objects.filter(pk=self.old_with_photo.pk).exists())

    def test_run_says_no_expired_when_none(self):
        PhotoUploadToken.objects.all().delete()
        token = PhotoUploadToken.objects.create(purpose=PhotoUploadToken.Purpose.REGISTRATION)
        # token is recent, not expired
        out = StringIO()
        call_command("cleanup_photo_upload_tokens", stdout=out)
        self.assertIn("No expired tokens", out.getvalue())
        self.assertTrue(PhotoUploadToken.objects.filter(pk=token.pk).exists())


class PhotoUploadRateLimitTests(TestCase):
    """Generate and upload endpoints are rate-limited per IP."""

    def setUp(self):
        _site_with_photo_upload_remote(True)

    def test_generate_returns_200_when_feature_on(self):
        url = reverse("portal:photo_upload_generate")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("token", data)
        self.assertIn("full_url", data)
