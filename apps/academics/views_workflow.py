"""
World Engine: JSON-driven workflow wizard. Loads WorkflowConfig by workflow_key and renders steps dynamically.
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views.generic import View

from .models import WorkflowConfig


@method_decorator(login_required, name="dispatch")
class WorkflowWizardView(View):
    """Generic wizard that loads steps from WorkflowConfig and renders the current step."""

    def get_config(self, workflow_key):
        return get_object_or_404(
            WorkflowConfig, workflow_key=workflow_key, is_active=True
        )

    def get(self, request, workflow_key):
        config = self.get_config(workflow_key)
        steps = config.steps or []
        if not steps:
            return render(
                request, "academics/workflow_empty.html", {"workflow_key": workflow_key}
            )
        step_index = max(0, min(int(request.GET.get("step", 0)), len(steps) - 1))
        step = steps[step_index]
        context = {
            "workflow_key": workflow_key,
            "workflow_config": config,
            "steps": steps,
            "current_step": step,
            "step_index": step_index,
            "step_count": len(steps),
            "has_prev": step_index > 0,
            "has_next": step_index < len(steps) - 1,
        }
        template = step.get("template") or "academics/workflow_step.html"
        return render(request, template, context)

    def post(self, request, workflow_key):
        config = self.get_config(workflow_key)
        steps = config.steps or []
        if not steps:
            raise Http404("No steps")
        step_index = max(0, min(int(request.POST.get("step_index", 0)), len(steps) - 1))
        # Optional: persist step data to session, then redirect to next or done
        next_index = step_index + 1
        if next_index >= len(steps):
            return render(
                request,
                "academics/workflow_done.html",
                {"workflow_key": workflow_key, "workflow_config": config},
            )
        from django.shortcuts import redirect
        from django.urls import reverse

        url = (
            reverse("academics:workflow_wizard", kwargs={"workflow_key": workflow_key})
            + f"?step={next_index}"
        )
        return redirect(url)
