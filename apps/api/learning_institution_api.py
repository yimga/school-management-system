"""
Wedges 23–43 beyond-reach APIs: pack install, terminology, AI/heuristic suggest, ministry PDF, benchmarks.
"""

from __future__ import annotations

import io
import json
import logging

from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

logger = logging.getLogger(__name__)


def _school(request):
    return getattr(request, "school", None)


def _can_learning_institution_admin(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    role = getattr(user, "role", None) or ""
    return role in ("ADMIN", "IT_ADMIN", "PROPRIETOR", "LEADERSHIP")


@method_decorator(csrf_exempt, name="dispatch")
class LearningPackInstallView(LoginRequiredMixin, View):
    """
    POST JSON { "pack_slug": "evals_rubrics", "record_marketplace": true }
    Staff with settings.manage or superuser; requires request.school.
    """

    def post(self, request):
        school = _school(request)
        if not school:
            return JsonResponse({"error": "School context required"}, status=400)
        if not _can_learning_institution_admin(request.user):
            return JsonResponse({"error": "Forbidden"}, status=403)
        try:
            body = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        pack_slug = (body.get("pack_slug") or "").strip()
        record = bool(body.get("record_marketplace", True))
        try:
            if record:
                from apps.platform_runtime.learning_institution_runtime import (
                    install_wedge_pack_with_marketplace_record,
                )

                out = install_wedge_pack_with_marketplace_record(
                    school, pack_slug, installed_by=request.user
                )
            else:
                from apps.platform_runtime.learning_institution_runtime import (
                    apply_single_wedge_pack_slug,
                )

                out = apply_single_wedge_pack_slug(school, pack_slug)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except Exception as e:
            logger.exception("learning_pack_install")
            return JsonResponse({"error": str(e)}, status=500)
        return JsonResponse(out, status=200)


class InstitutionProfileSuggestView(LoginRequiredMixin, View):
    """GET — heuristic (and optional gateway) suggestion for delivery + institution type."""

    def get(self, request):
        if not _can_learning_institution_admin(request.user):
            return JsonResponse({"error": "Forbidden"}, status=403)
        school = _school(request)
        if not school:
            return JsonResponse({"error": "School context required"}, status=400)
        from apps.platform_runtime.learning_institution_runtime import (
            suggest_institution_profile_from_school,
        )

        data = suggest_institution_profile_from_school(school)
        if request.GET.get("ai") == "1":
            try:
                from django.conf import settings

                if getattr(settings, "AI_GATEWAY_ENABLED", True):
                    from services.ai_gateway import invoke

                    prompt = (
                        'Reply with JSON only: {"delivery_mode_codes":["W23_IN_PERSON"],'
                        '"institution_type_code":"W31_GENERAL_K12","confidence":0.5} '
                        f"for a school named roughly: {school.name[:80]!r}. Choose from SOT wedges 23-30 delivery codes and 31-43 institution codes."
                    )
                    raw, meta = invoke(
                        "general_chat", prompt, user_query="classify", metadata={}
                    )
                    if isinstance(raw, str) and "{" in raw:
                        start, end = raw.find("{"), raw.rfind("}") + 1
                        data["ai_json"] = json.loads(raw[start:end])
                        data["source"] = "ai_gateway"
                        data["ai_meta"] = {
                            k: meta.get(k) for k in ("provider", "model") if meta.get(k)
                        }
            except Exception as e:
                data["ai_error"] = str(e)[:200]
        return JsonResponse(data)


class TerminologyPackView(View):
    """GET ?locale=en&institution_code=W43_HIGHER_EDUCATION — public read for SPA."""

    def get(self, request):
        from apps.platform_runtime.learning_institution_catalog import (
            terminology_for_locale,
        )

        loc = request.GET.get("locale") or "en"
        ic = request.GET.get("institution_code") or ""
        return JsonResponse(
            {
                "locale": loc,
                "terms": terminology_for_locale(loc, ic or None),
                "catalog_version": __import__(
                    "apps.platform_runtime.learning_institution_catalog",
                    fromlist=["CATALOG_VERSION"],
                ).CATALOG_VERSION,
            }
        )


class MinistryStubPdfView(LoginRequiredMixin, View):
    """GET ?stub=stub_census_headcount — real PDF (ReportLab) for ministry stub exports."""

    def get(self, request):
        if not _can_learning_institution_admin(request.user):
            return HttpResponse("Forbidden", status=403)
        school = _school(request)
        stub = (request.GET.get("stub") or "").strip()
        if not stub or not stub.replace("_", "").isalnum():
            return HttpResponse("Invalid stub", status=400)
        from apps.platform_runtime.learning_institution_catalog import (
            MINISTRY_REPORT_STUBS,
        )

        label = stub
        for _k, rows in MINISTRY_REPORT_STUBS.items():
            for r in rows or []:
                if r.get("slug") == stub:
                    label = r.get("label") or stub
                    break
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
        except ImportError:
            return HttpResponse("PDF engine unavailable", status=503)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        c.setTitle(f"Ministry report — {label}")
        y = 750
        c.drawString(72, y, "RunMyCampus — Ministry / statutory export (generated)")
        y -= 24
        c.drawString(72, y, f"Report: {label}")
        y -= 24
        c.drawString(72, y, f"Stub key: {stub}")
        y -= 24
        if school:
            c.drawString(72, y, f"Tenant: {school.name} (id {school.pk})")
        else:
            c.drawString(72, y, "Tenant: (not resolved in session)")
        y -= 36
        c.drawString(
            72,
            y,
            "This document is a structured shell for RFP / accreditation workflows.",
        )
        y -= 20
        c.drawString(
            72, y, "Replace with live aggregates when ministry connectors are enabled."
        )
        c.showPage()
        c.save()
        pdf = buf.getvalue()
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="ministry_{stub}.pdf"'
        return resp


class LearningWedgeBenchmarksView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Superuser-only anonymized wedge adoption stats."""

    def test_func(self):
        return bool(getattr(self.request.user, "is_superuser", False))

    def get(self, request):
        from apps.platform_runtime.learning_institution_runtime import (
            aggregate_learning_wedge_benchmarks,
        )

        return JsonResponse(aggregate_learning_wedge_benchmarks())
