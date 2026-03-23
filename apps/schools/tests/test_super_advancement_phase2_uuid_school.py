"""Super advancement phase2 placeholder: donor POST must accept UUID school_id (tenant PK)."""

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import AdvancementDonor, School


@override_settings(ALLOWED_HOSTS=["*"])
class SuperAdvancementPhase2UuidSchoolTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Adv UUID School",
            slug="adv-uuid-school",
            subdomain="adv-uuid-school",
            is_active=True,
        )
        self.superuser = User.objects.create_superuser(
            "su_adv_phase2", "su_adv_phase2@x.edu", "pw"
        )

    def test_add_donor_post_accepts_uuid_school_id(self):
        c = Client()
        c.force_login(self.superuser)
        url = reverse("super:advancement_phase2_placeholder")
        r = c.post(
            url,
            {
                "action": "add_donor",
                "school_id": str(self.school.pk),
                "display_name": "UUID Patron",
                "email": "patron@example.org",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(
            AdvancementDonor.objects.filter(
                school=self.school, display_name="UUID Patron"
            ).count(),
            1,
        )
