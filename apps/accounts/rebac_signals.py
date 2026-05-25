"""Signal handlers that keep relationship tuples in sync."""

from __future__ import annotations

import logging

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from apps.accounts.rebac_sync import (
    remove_guardian_tuples,
    remove_membership_tuples,
    remove_teacher_assignment_tuples,
    sync_guardian_tuples,
    sync_membership_tuples,
    sync_teacher_assignment_tuples,
    sync_user_roles_for_school,
)

logger = logging.getLogger(__name__)


def _connect():
    from apps.accounts.models import AccessRole, TemporaryRoleGrant, User
    from apps.evals.models import TeacherAssignment
    from apps.people.models import StudentGuardian
    from apps.schools.models import SchoolMembership

    @receiver(post_save, sender=SchoolMembership)
    def _membership_saved(sender, instance, **kwargs):
        try:
            sync_membership_tuples(instance)
        except Exception:
            logger.exception("rebac_sync_membership pk=%s", instance.pk)

    @receiver(post_delete, sender=SchoolMembership)
    def _membership_deleted(sender, instance, **kwargs):
        try:
            remove_membership_tuples(instance)
        except Exception:
            logger.exception("rebac_remove_membership pk=%s", instance.pk)

    @receiver(post_save, sender=StudentGuardian)
    def _guardian_saved(sender, instance, **kwargs):
        try:
            sync_guardian_tuples(instance)
        except Exception:
            logger.exception("rebac_sync_guardian pk=%s", instance.pk)

    @receiver(post_delete, sender=StudentGuardian)
    def _guardian_deleted(sender, instance, **kwargs):
        try:
            remove_guardian_tuples(instance)
        except Exception:
            logger.exception("rebac_remove_guardian pk=%s", instance.pk)

    @receiver(post_save, sender=TeacherAssignment)
    def _teacher_assignment_saved(sender, instance, **kwargs):
        try:
            sync_teacher_assignment_tuples(instance)
        except Exception:
            logger.exception("rebac_sync_teacher_assignment pk=%s", instance.pk)

    @receiver(post_delete, sender=TeacherAssignment)
    def _teacher_assignment_deleted(sender, instance, **kwargs):
        try:
            remove_teacher_assignment_tuples(instance)
        except Exception:
            logger.exception("rebac_remove_teacher_assignment pk=%s", instance.pk)

    @receiver(post_save, sender=TemporaryRoleGrant)
    def _temp_grant_saved(sender, instance, **kwargs):
        school = getattr(instance.role, "school", None)
        if school is None:
            return
        try:
            sync_user_roles_for_school(instance.user, school=school)
        except Exception:
            logger.exception("rebac_sync_temp_grant pk=%s", instance.pk)

    @receiver(post_delete, sender=TemporaryRoleGrant)
    def _temp_grant_deleted(sender, instance, **kwargs):
        school = getattr(instance.role, "school", None)
        if school is None:
            return
        try:
            sync_user_roles_for_school(instance.user, school=school)
        except Exception:
            logger.exception("rebac_remove_temp_grant pk=%s", instance.pk)

    @receiver(m2m_changed, sender=User.feature_permissions.through)
    def _user_direct_permissions_changed(sender, instance, action, **kwargs):
        if action not in ("post_add", "post_remove", "post_clear"):
            return
        from apps.schools.models import SchoolMembership

        for m in SchoolMembership.objects.filter(user=instance).select_related("school"):
            try:
                sync_user_roles_for_school(instance, school=m.school)
            except Exception:
                logger.exception(
                    "rebac_sync_direct_perms user=%s school=%s",
                    instance.pk,
                    m.school_id,
                )

    @receiver(m2m_changed, sender=User.roles.through)
    def _user_roles_changed(sender, instance, action, pk_set, **kwargs):
        if action not in ("post_add", "post_remove", "post_clear"):
            return
        from apps.schools.models import SchoolMembership

        for m in SchoolMembership.objects.filter(user=instance).select_related("school"):
            try:
                sync_user_roles_for_school(instance, school=m.school)
            except Exception:
                logger.exception(
                    "rebac_sync_user_roles user=%s school=%s",
                    instance.pk,
                    m.school_id,
                )

    @receiver(m2m_changed, sender=AccessRole.permissions.through)
    def _role_permissions_changed(sender, instance, action, **kwargs):
        if action not in ("post_add", "post_remove", "post_clear"):
            return
        from apps.accounts.models import User

        school = getattr(instance, "school", None)
        users = User.objects.filter(roles=instance)
        for user in users[:500]:
            if school is not None:
                sync_user_roles_for_school(user, school=school)
            else:
                from apps.schools.models import SchoolMembership

                for m in SchoolMembership.objects.filter(user=user).select_related(
                    "school",
                ):
                    sync_user_roles_for_school(user, school=m.school)


_connect()
