"""
Session ↔ tenant binding — reject session school_id that disagrees with resolved host school.

When a user bookmarks a child campus URL but session still holds a sibling school_id,
force session realignment to request.school (set by TenantMiddleware) to block BOLA drift.
"""

from __future__ import annotations

import logging

from django.contrib.auth import logout
from django.http import HttpResponseForbidden

logger = logging.getLogger(__name__)


class SessionSchoolBindingMiddleware:
    """
    After TenantMiddleware: keep request.session['school_id'] aligned with request.school.

    Mismatch on authenticated tenant requests indicates session fixation or IDOR tampering;
    realign when the user may access request.school, else force logout.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        school = getattr(request, "school", None)
        if (
            user
            and getattr(user, "is_authenticated", False)
            and school is not None
            and hasattr(request, "session")
        ):
            session_sid = (request.session.get("school_id") or "").strip()
            host_sid = str(school.pk)
            if session_sid and session_sid != host_sid:
                from apps.schools.tenant_switch_security import user_may_switch_to_school

                active = None
                if session_sid:
                    from apps.schools.models import School

                    active = School.objects.filter(pk=session_sid, is_active=True).first()
                if user_may_switch_to_school(user, school, active_school=active):
                    from apps.schools.session_school_bind import sign_session_school_bind

                    sign_session_school_bind(
                        request.session, school_id=host_sid, user_id=user.pk
                    )
                    logger.info(
                        "session_school_realigned",
                        extra={
                            "from_school_id": session_sid,
                            "to_school_id": host_sid,
                            "user_id": getattr(user, "pk", None),
                        },
                    )
                else:
                    logger.warning(
                        "session_school_binding_rejected",
                        extra={
                            "session_school_id": session_sid,
                            "host_school_id": host_sid,
                            "user_id": getattr(user, "pk", None),
                        },
                    )
                    logout(request)
                    return HttpResponseForbidden(
                        "Session school does not match this campus. Sign in again."
                    )
            elif not session_sid:
                from apps.schools.session_school_bind import sign_session_school_bind

                sign_session_school_bind(
                    request.session, school_id=host_sid, user_id=user.pk
                )
            else:
                from apps.schools.session_school_bind import (
                    sign_session_school_bind,
                    verify_session_school_bind,
                )
                from apps.schools.tenant_switch_security import user_may_access_school_api

                if not verify_session_school_bind(request.session, user):
                    if user_may_access_school_api(
                        user, school, session_school_id=session_sid
                    ):
                        sign_session_school_bind(
                            request.session, school_id=host_sid, user_id=user.pk
                        )
                    else:
                        logger.warning(
                            "session_school_bind_sig_invalid",
                            extra={
                                "host_school_id": host_sid,
                                "user_id": getattr(user, "pk", None),
                            },
                        )
                        logout(request)
                        return HttpResponseForbidden(
                            "Session campus binding is invalid. Sign in again."
                        )

        return self.get_response(request)
