"""Agent debug middleware: log workflow progress strip template resolution failures."""

from __future__ import annotations

from django.conf import settings
from django.template.exceptions import TemplateDoesNotExist

from apps.observability.agent_debug_session import agent_debug_log, workflow_progress_strip_deploy_probe


class AgentTemplateMissingDebugMiddleware:
    """Log deploy probe when the workflow progress strip partial is missing."""

    def process_exception(self, request, exception):
        if not isinstance(exception, TemplateDoesNotExist):
            return None
        if "rmc_workflow_progress_strip" not in str(exception):
            return None

        probe = workflow_progress_strip_deploy_probe(settings.BASE_DIR)
        template_dirs = []
        for engine in settings.TEMPLATES:
            template_dirs.extend(str(path) for path in engine.get("DIRS", []))

        # #region agent log
        agent_debug_log(
            hypothesis_id="H2",
            location="middleware_agent_template_debug.process_exception",
            message="TemplateDoesNotExist for rmc_workflow_progress_strip",
            data={
                **probe,
                "request_path": getattr(request, "path", ""),
                "template_dirs": template_dirs,
            },
            base_dir=settings.BASE_DIR,
        )
        # #endregion
        return None
