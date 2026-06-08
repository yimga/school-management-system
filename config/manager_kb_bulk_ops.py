"""
Operator UI for one-click KB bulk import + ODT generation (batch 1658).
"""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.portal.kb_bulk_ops_service import run_generate_kb_odt, run_import_docs_to_kb
from apps.schools.control_plane import require_control_plane_access
from apps.schools.operator_report_render import render_manager_report_page


@require_http_methods(["GET", "POST"])
@require_control_plane_access
def manager_kb_bulk_ops(request):
    last_output = ""
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        dry_run = request.POST.get("dry_run") == "on"
        overwrite = request.POST.get("overwrite") == "on"

        if action == "import_docs":
            result = run_import_docs_to_kb(
                category=(request.POST.get("category") or "system-admin").strip(),
                overwrite=overwrite,
                dry_run=dry_run,
                include_root=request.POST.get("include_root") == "on",
                generate_odt=request.POST.get("generate_odt") == "on",
                odt_engine=(request.POST.get("odt_engine") or "auto").strip(),
            )
            last_output = (result.get("stdout") or "") + (result.get("stderr") or "")
            label = _("Dry-run import") if dry_run else _("Import docs to KB")
            messages.success(request, str(label))
        elif action == "generate_odt":
            result = run_generate_kb_odt(
                article_slug=(request.POST.get("article_slug") or "").strip(),
                engine=(request.POST.get("engine") or "auto").strip(),
                formats=(request.POST.get("formats") or "odt").strip(),
                dry_run=dry_run,
                overwrite=overwrite,
            )
            last_output = (result.get("stdout") or "") + (result.get("stderr") or "")
            label = _("Dry-run ODT generation") if dry_run else _("Generate KB ODT")
            messages.success(request, str(label))
        else:
            messages.error(request, str(_("Unknown action.")))
            return redirect("manager_kb_bulk_ops")

        request.session["manager_kb_bulk_ops_output"] = last_output[-12000:]
        return redirect("manager_kb_bulk_ops")

    last_output = request.session.pop("manager_kb_bulk_ops_output", "")

    return render_manager_report_page(
        request,
        body_template="schools/partials/manager_kb_bulk_ops_body.html",
        context={
            "help_center_url": reverse("manager_help_center"),
            "docs_hub_url": reverse("kb:kb_docs_hub"),
            "locale_families_url": reverse("manager_kb_locale_families"),
            "last_output": last_output,
        },
        page_title=str(_("KB bulk operations")),
        page_archetype="operational-workbench",
    )
