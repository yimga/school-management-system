"""Operator-facing CSV bulk school creation.

URL: /super/schools/bulk-create/
- GET → upload form + CSV column reference
- POST file=...  (no apply) → dry-run preview (no DB writes)
- POST file=... apply=1 → apply changes, render result summary
"""

from __future__ import annotations

import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View

from .services_bulk import apply_rows, parse_csv

logger = logging.getLogger(__name__)


@method_decorator(staff_member_required, name="dispatch")
class BulkSchoolCreateView(View):
    template_name = "lifecycle/bulk_create.html"

    def get(self, request):
        return render(request, self.template_name, {"phase": "form"})

    def post(self, request):
        upload = request.FILES.get("file")
        apply_flag = request.POST.get("apply") in ("1", "true", "yes", "on")
        if not upload:
            return render(
                request,
                self.template_name,
                {"phase": "form", "error": "Please choose a CSV file to upload."},
            )
        # Cap upload size at 4MB — bulk is for hundreds of rows, not
        # full SIS migrations.
        if upload.size > 4 * 1024 * 1024:
            return render(
                request,
                self.template_name,
                {"phase": "form", "error": "File exceeds 4MB cap."},
            )
        parsed = parse_csv(upload)
        if parsed.header_errors:
            return render(
                request,
                self.template_name,
                {"phase": "form", "error": "; ".join(parsed.header_errors)},
            )
        if not apply_flag:
            return render(
                request,
                self.template_name,
                {
                    "phase": "preview",
                    "parsed": parsed,
                    "valid_count": len(parsed.valid_rows),
                    "invalid_count": len(parsed.invalid_rows),
                },
            )
        result = apply_rows(parsed.rows, actor=request.user)
        return render(
            request,
            self.template_name,
            {
                "phase": "result",
                "result": result,
                "created_count": result.total_ok,
                "failed_count": len(result.failed),
            },
        )
