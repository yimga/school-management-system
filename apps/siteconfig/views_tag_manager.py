"""
Tag Manager UI: School Settings → create/edit InformationTag (zero-hardcoding tags).
Scoped to request.school; only tags for current tenant.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import permission_required
from apps.people.models import InformationTag


def _school_required(view_func):
    """Require request.school (tenant). Use after login_required."""
    def _wrapped(request, *args, **kwargs):
        if not getattr(request, "school", None):
            return HttpResponseForbidden("School context required.")
        return view_func(request, *args, **kwargs)
    return _wrapped


@login_required
@permission_required("settings.manage")
@_school_required
@require_http_methods(["GET", "POST"])
def tag_manager(request):
    """List all information tags for the school; form to create new tag."""
    school = request.school
    all_tags = list(
        InformationTag.objects.filter(school=school).order_by("sort_order", "name")
    )
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        category = (request.POST.get("category") or InformationTag.Category.GENERAL).strip()
        color_hex = (request.POST.get("color_hex") or "#3498db").strip()
        description = (request.POST.get("description") or "").strip()
        is_private = request.POST.get("is_private") == "on"
        is_critical = request.POST.get("is_critical") == "on"
        if not name:
            messages.error(request, "Tag name is required.")
        elif InformationTag.objects.filter(school=school, name__iexact=name).exists():
            messages.error(request, f"A tag named «{name}» already exists.")
        else:
            InformationTag.objects.create(
                school=school,
                name=name,
                category=category if category in dict(InformationTag.Category.choices) else InformationTag.Category.GENERAL,
                color_hex=color_hex if color_hex.startswith("#") else f"#{color_hex}",
                description=description,
                is_private=is_private,
                is_critical=is_critical,
            )
            messages.success(request, f"Tag «{name}» created.")
            return redirect("siteconfig:tag_manager")
    return render(request, "siteconfig/tag_manager.html", {
        "tags": all_tags,
        "category_choices": InformationTag.Category.choices,
    })


@login_required
@permission_required("settings.manage")
@_school_required
@require_http_methods(["GET", "POST"])
def tag_manager_edit(request, tag_id):
    """Edit or deactivate an information tag."""
    school = request.school
    tag = get_object_or_404(InformationTag, pk=tag_id, school=school)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            tag.is_active = False
            tag.save(update_fields=["is_active"])
            messages.success(request, f"Tag «{tag.name}» deactivated.")
            return redirect("siteconfig:tag_manager")
        if action == "save":
            tag.name = (request.POST.get("name") or tag.name).strip()
            category = (request.POST.get("category") or tag.category).strip()
            tag.category = category if category in dict(InformationTag.Category.choices) else tag.category
            tag.color_hex = (request.POST.get("color_hex") or tag.color_hex).strip()
            if not tag.color_hex.startswith("#"):
                tag.color_hex = f"#{tag.color_hex}"
            tag.description = (request.POST.get("description") or "").strip()
            tag.is_private = request.POST.get("is_private") == "on"
            tag.is_critical = request.POST.get("is_critical") == "on"
            try:
                tag.save()
                messages.success(request, f"Tag «{tag.name}» updated.")
            except Exception as e:
                messages.error(request, str(e))
            return redirect("siteconfig:tag_manager")
    return render(request, "siteconfig/tag_manager_edit.html", {"tag": tag, "category_choices": InformationTag.Category.choices})
