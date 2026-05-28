"""Operator-facing 'clone from template' school creation.

URL: /super/schools/<uuid:source_id>/clone/
- GET → form prefilled with source.name/slug, asks for new_name + new_slug
- POST → invokes clone_school(), returns to source or new 360 view
"""

from __future__ import annotations

import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

from apps.schools.models import School

from .services_clone import clone_school

logger = logging.getLogger(__name__)


@method_decorator(staff_member_required, name="dispatch")
class CloneSchoolView(View):
    template_name = "lifecycle/clone.html"

    def get(self, request, source_id):
        source = get_object_or_404(School, id=source_id)
        return render(
            request,
            self.template_name,
            {"source": source},
        )

    def post(self, request, source_id):
        source = get_object_or_404(School, id=source_id)
        new_name = (request.POST.get("new_name") or "").strip()
        new_slug = (request.POST.get("new_slug") or "").strip().lower()
        new_subdomain = (request.POST.get("new_subdomain") or "").strip().lower() or None
        if not new_name or not new_slug:
            return render(
                request,
                self.template_name,
                {"source": source, "error": "Both new_name and new_slug are required."},
                status=400,
            )
        try:
            cloned = clone_school(
                source,
                new_name=new_name,
                new_slug=new_slug,
                new_subdomain=new_subdomain,
                actor=request.user,
            )
        except ValueError as exc:
            return render(
                request,
                self.template_name,
                {"source": source, "error": str(exc)},
                status=400,
            )
        return redirect(reverse("super:lifecycle_timeline", args=[cloned.new_id]))
