from django.utils.deprecation import MiddlewareMixin

from apps.siteconfig.preview_state import (
    PREVIEW_MODE_SESSION_KEY,
    ACT_AS_ROLE_SESSION_KEY,
    reset_preview_mode,
    set_preview_mode,
)
import logging

logger = logging.getLogger(__name__)

HEADER_NAME = "HTTP_X_PREVIEW_MODE"


class PreviewModeMiddleware(MiddlewareMixin):
    """Toggle preview routing for admin requests using headers or session."""

    def process_request(self, request):
        header_value = request.META.get(HEADER_NAME, "").lower()
        header_enabled = header_value in {"1", "true", "yes", "on"}
        session_enabled = bool(request.session.get(PREVIEW_MODE_SESSION_KEY))
        enabled = header_enabled or session_enabled
        request.preview_mode_enabled = enabled
        request.preview_mode_source = "header" if header_enabled else ("session" if session_enabled else None)
        request.preview_act_as_role = request.session.get(ACT_AS_ROLE_SESSION_KEY)
        if request.preview_act_as_role:
            logger.debug(
                "Request in preview mode acting as %s for user %s",
                request.preview_act_as_role,
                request.user.username if hasattr(request.user, "username") else "anonymous",
            )
        set_preview_mode(enabled)
        request.preview_mode_session_key = PREVIEW_MODE_SESSION_KEY

    def process_response(self, request, response):
        reset_preview_mode()
        return response

    def process_exception(self, request, exception):
        reset_preview_mode()
        return None
