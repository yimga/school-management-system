"""Tests for real-time propagation of RBAC / authority changes.

Covers the User authority signal (invalidate + push), the m2m handler wiring, the
no-op path for non-authority writes, and the producer's room targeting.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

User = get_user_model()


class AccessRealtimeSignalTests(TestCase):
    def _make(self, username):
        return User.objects.create_user(
            username=username, email=f"{username}@example.com", password="x"
        )

    def test_authority_change_invalidates_and_pushes(self):
        u = self._make("rt1")
        with mock.patch(
            "apps.accounts.access_realtime.push_access_changed_realtime"
        ) as push, mock.patch(
            "apps.platform_runtime.helpers.invalidate_effective_site_settings_cache"
        ) as inval:
            u.is_superuser = True
            u.save(update_fields=["is_superuser"])
        self.assertTrue(push.called)
        self.assertTrue(inval.called)

    def test_last_login_only_save_does_not_push(self):
        u = self._make("rt2")
        with mock.patch(
            "apps.accounts.access_realtime.push_access_changed_realtime"
        ) as push:
            u.last_login = timezone.now()
            u.save(update_fields=["last_login"])
        self.assertFalse(push.called)

    def test_m2m_handler_propagates_for_user_instance(self):
        from apps.accounts.signals_access import _on_user_m2m_changed

        u = self._make("rt3")
        with mock.patch("apps.accounts.signals_access._propagate") as prop:
            _on_user_m2m_changed(
                sender=User.roles.through, instance=u, action="post_add"
            )
        prop.assert_called_once()

    def test_m2m_handler_ignores_non_user_and_pre_actions(self):
        from apps.accounts.signals_access import _on_user_m2m_changed

        u = self._make("rt4")
        with mock.patch("apps.accounts.signals_access._propagate") as prop:
            _on_user_m2m_changed(
                sender=User.roles.through, instance=object(), action="post_add"
            )
            _on_user_m2m_changed(
                sender=User.roles.through, instance=u, action="pre_add"
            )
        prop.assert_not_called()

    def test_producer_sends_to_each_user_school_room(self):
        from apps.accounts.access_realtime import push_access_changed_realtime
        from apps.schools.models import School, SchoolMembership

        school = School.objects.create(name="RT High", slug="rt-high")
        u = self._make("rt5")
        SchoolMembership.objects.create(user=u, school=school, role="ADMIN")

        layer = mock.MagicMock()
        layer.group_send = mock.AsyncMock()
        with mock.patch("channels.layers.get_channel_layer", return_value=layer):
            sent = push_access_changed_realtime(u, reason="test")

        self.assertEqual(sent, 1)
        room, message = layer.group_send.await_args.args
        self.assertEqual(room, f"notifications_sync_{school.id}_{u.id}")
        self.assertEqual(message["type"], "access.changed")

    def test_producer_no_membership_sends_nothing(self):
        from apps.accounts.access_realtime import push_access_changed_realtime

        u = self._make("rt6")
        layer = mock.MagicMock()
        layer.group_send = mock.AsyncMock()
        with mock.patch("channels.layers.get_channel_layer", return_value=layer):
            sent = push_access_changed_realtime(u)
        self.assertEqual(sent, 0)
        layer.group_send.assert_not_called()
