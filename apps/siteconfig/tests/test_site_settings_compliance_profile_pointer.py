from django.test import TestCase

from apps.finance.models import ComplianceProfile
from apps.siteconfig.forms import SiteSettingsForm
from apps.siteconfig.models import SiteSettings


class SiteSettingsComplianceProfilePointerTests(TestCase):
    def test_property_and_form_initialise_pointer_without_model_relation(self):
        profile = ComplianceProfile.objects.create(name="CM Default", country_code="CM")
        site = SiteSettings.get_solo()
        site.compliance_profile = profile
        site.save()

        site.refresh_from_db()
        self.assertEqual(site.compliance_profile_id, profile.pk)
        self.assertEqual(site.compliance_profile.pk, profile.pk)

        form = SiteSettingsForm(instance=site)
        self.assertEqual(form.initial["compliance_profile"], profile.pk)
        self.assertIn((profile.pk, profile.name), form.fields["compliance_profile"].choices)
