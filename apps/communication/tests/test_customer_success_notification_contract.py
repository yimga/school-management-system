"""Customer success notification contract."""

from django.test import SimpleTestCase


class CustomerSuccessNotificationContractTests(SimpleTestCase):
    def test_onboarding_nudge_task_importable(self):
        from apps.customersuccess.tasks import deliver_onboarding_day_n_nudges

        self.assertTrue(callable(deliver_onboarding_day_n_nudges))
