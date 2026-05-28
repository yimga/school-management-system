"""RLS-JWT auth-handoff signal receivers (v4.00.5).

Listens to ``django.contrib.auth.signals.user_logged_out`` to drop the
``rmc_rls_jwt`` cookie, completing the auth-handoff lifecycle:

* login           -> middleware response-path mints + sets the cookie (no signal needed)
* request         -> middleware verifies + binds app.current_school_id
* logout (this)   -> stash a marker on the request so the middleware can clear it

The marker pattern: Django's ``user_logged_out`` signal fires from
``django.contrib.auth.logout()`` BEFORE the view returns its response, so we
can't directly mutate a response here. Instead we set ``request._rls_jwt_clear=True``
and the middleware checks for it.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(user_logged_out)
def _on_user_logged_out(sender: Any, request: Any, user: Any, **kwargs: Any) -> None:
    """Mark the request so the middleware drops the rmc_rls_jwt cookie on response."""
    if request is None:
        return
    try:
        setattr(request, "_rls_jwt_clear", True)
    except (AttributeError, TypeError):
        logger.debug("rls_jwt.logout_mark_failed")
