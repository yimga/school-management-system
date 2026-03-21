# -*- coding: utf-8 -*-
"""
Super CRUD for platform catalog models removed from platform_admin_site.
All views wrapped with require_super_access_with_host in super_urls.
"""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.siteconfig.models_feature_controls import FeatureToggleDefinition
from apps.siteconfig.models_global_experience import GradingScaleConfig
from apps.siteconfig.models_platform_catalog import (
    CountryMultiplier,
    Plan,
    PlanAddon,
    RegionConfig,
)


def _ctx(request):
    return {
        "dashboard_url": reverse("super:dashboard"),
        "system_config_url": reverse("siteconfig:console_domains_hub"),
    }


class RegionConfigSuperForm(forms.ModelForm):
    class Meta:
        model = RegionConfig
        exclude = ("created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for _name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                field.widget.attrs.setdefault("class", "form-select")
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("class", "form-control")
            else:
                field.widget.attrs.setdefault("class", "form-control")
        if "grading_rule" in self.fields:
            self.fields["grading_rule"].widget = forms.Textarea(
                attrs={"class": "form-control font-monospace", "rows": 3}
            )

    def clean_grading_rule(self):
        value = self.cleaned_data.get("grading_rule")
        if value is None:
            return {}
        if isinstance(value, str):
            raise ValidationError(_("Grading rule must be valid JSON (object)."))
        if not isinstance(value, dict):
            raise ValidationError(
                _('Grading rule must be a JSON object (e.g. {} or {"type": "simple"}).')
            )
        return value


class GradingScaleConfigSuperForm(forms.ModelForm):
    class Meta:
        model = GradingScaleConfig
        exclude = ("created_at",)
        widgets = {
            "region": forms.Select(attrs={"class": "form-select"}),
            "scale_type": forms.TextInput(attrs={"class": "form-control"}),
            "display_format": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in (
            "min_score",
            "max_score",
            "grade_a_min",
            "grade_b_min",
            "grade_c_min",
            "grade_d_min",
            "grade_f_min",
        ):
            if name in self.fields:
                self.fields[name].widget = forms.NumberInput(
                    attrs={"class": "form-control", "step": "0.01"}
                )


class PlanSuperForm(forms.ModelForm):
    class Meta:
        model = Plan
        exclude = ("created_at", "updated_at")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "billing_model": forms.Select(attrs={"class": "form-select"}),
            "included_features": forms.Textarea(
                attrs={"class": "form-control font-monospace", "rows": 4}
            ),
            "tier_rules": forms.Textarea(
                attrs={"class": "form-control font-monospace", "rows": 4}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("max_students", "max_staff"):
            if name in self.fields:
                self.fields[name].widget = forms.NumberInput(attrs={"class": "form-control"})
        for name in ("base_price", "price_per_student"):
            if name in self.fields:
                self.fields[name].widget = forms.NumberInput(
                    attrs={"class": "form-control", "step": "0.01"}
                )
        if "is_active" in self.fields:
            self.fields["is_active"].widget = forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            )

    def clean_included_features(self):
        value = self.cleaned_data.get("included_features")
        if value is None:
            return []
        if isinstance(value, str):
            raise ValidationError(_("Included features must be valid JSON."))
        if not isinstance(value, list):
            raise ValidationError(
                _('Included features must be a JSON array of feature codes (e.g. ["library", "transport"]).')
            )
        return value

    def clean_tier_rules(self):
        value = self.cleaned_data.get("tier_rules")
        if value is None:
            return {}
        if isinstance(value, str):
            raise ValidationError(_("Tier rules must be valid JSON."))
        if not isinstance(value, (dict, list)):
            raise ValidationError(
                _("Tier rules must be a JSON object or array (volume bands).")
            )
        return value


class PlanAddonSuperForm(forms.ModelForm):
    class Meta:
        model = PlanAddon
        exclude = ("created_at", "updated_at")
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "is_active" in self.fields:
            self.fields["is_active"].widget = forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            )


class FeatureToggleDefinitionSuperForm(forms.ModelForm):
    class Meta:
        model = FeatureToggleDefinition
        exclude = ("created_at", "updated_at")
        widgets = {
            "key": forms.TextInput(attrs={"class": "form-control"}),
            "label": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "category": forms.TextInput(attrs={"class": "form-control"}),
            "scope": forms.Select(attrs={"class": "form-select"}),
            "owner": forms.TextInput(attrs={"class": "form-control"}),
            "source": forms.TextInput(attrs={"class": "form-control"}),
            "metadata": forms.Textarea(
                attrs={"class": "form-control font-monospace", "rows": 4}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("default_enabled", "is_active"):
            if name in self.fields:
                self.fields[name].widget = forms.CheckboxInput(
                    attrs={"class": "form-check-input"}
                )

    def clean_metadata(self):
        value = self.cleaned_data.get("metadata")
        if value is None:
            return {}
        if isinstance(value, str):
            raise ValidationError(_("Metadata must be valid JSON."))
        if not isinstance(value, dict):
            raise ValidationError(_('Metadata must be a JSON object (e.g. {}).'))
        return value


class CountryMultiplierSuperForm(forms.ModelForm):
    class Meta:
        model = CountryMultiplier
        exclude = ("created_at", "updated_at")
        widgets = {
            "country_code": forms.TextInput(attrs={"class": "form-control"}),
            "zone": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "multiplier" in self.fields:
            self.fields["multiplier"].widget = forms.NumberInput(
                attrs={"class": "form-control", "step": "0.0001"}
            )
        if "is_active" in self.fields:
            self.fields["is_active"].widget = forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            )


def _render_form(
    request,
    *,
    title: str,
    form: forms.Form,
    back_url: str,
    breadcrumb_extra: str,
    delete_url: str | None = None,
):
    return render(
        request,
        "schools/super_crud_form.html",
        {
            **_ctx(request),
            "page_title": title,
            "form": form,
            "back_url": back_url,
            "breadcrumb_extra": breadcrumb_extra,
            "delete_url": delete_url,
        },
    )


def _render_delete_confirm(
    request,
    *,
    page_title: str,
    object_label: str,
    back_url: str,
    breadcrumb_extra: str,
    delete_action_url: str,
    warning_lines: list[str] | None = None,
):
    return render(
        request,
        "schools/super_crud_confirm_delete.html",
        {
            **_ctx(request),
            "page_title": page_title,
            "object_label": object_label,
            "back_url": back_url,
            "breadcrumb_extra": breadcrumb_extra,
            "delete_action_url": delete_action_url,
            "warning_lines": warning_lines or [],
        },
    )


# --- Regions ---


@require_http_methods(["GET", "POST"])
def super_region_edit(request, code: str):
    region = get_object_or_404(RegionConfig, pk=code)
    if request.method == "POST":
        form = RegionConfigSuperForm(request.POST, instance=region)
        if form.is_valid():
            form.save()
            messages.success(request, "Region saved.")
            return redirect("super:regions_list")
    else:
        form = RegionConfigSuperForm(instance=region)
    return _render_form(
        request,
        title=f"Edit region {region.code}",
        form=form,
        back_url=reverse("super:regions_list"),
        breadcrumb_extra="Regions",
        delete_url=reverse("super:region_delete", kwargs={"code": region.code}),
    )


@require_http_methods(["GET", "POST"])
def super_region_add(request):
    if request.method == "POST":
        form = RegionConfigSuperForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Region created.")
            return redirect("super:regions_list")
    else:
        form = RegionConfigSuperForm()
    return _render_form(
        request,
        title="Add region",
        form=form,
        back_url=reverse("super:regions_list"),
        breadcrumb_extra="Regions",
    )


# --- Grading ---


@require_http_methods(["GET", "POST"])
def super_grading_edit(request, pk: int):
    row = get_object_or_404(GradingScaleConfig.objects.select_related("region"), pk=pk)
    if request.method == "POST":
        form = GradingScaleConfigSuperForm(request.POST, instance=row)
        if form.is_valid():
            form.save()
            messages.success(request, "Grading scale saved.")
            return redirect("super:grading_list")
    else:
        form = GradingScaleConfigSuperForm(instance=row)
    return _render_form(
        request,
        title=f"Edit grading scale #{pk}",
        form=form,
        back_url=reverse("super:grading_list"),
        breadcrumb_extra="Grading",
        delete_url=reverse("super:grading_delete", kwargs={"pk": row.pk}),
    )


@require_http_methods(["GET", "POST"])
def super_grading_add(request):
    initial = {}
    rc = (request.GET.get("region") or "").strip()
    if rc:
        initial["region"] = rc
    if request.method == "POST":
        form = GradingScaleConfigSuperForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Grading scale created.")
            return redirect("super:grading_list")
    else:
        form = GradingScaleConfigSuperForm(initial=initial)
    return _render_form(
        request,
        title="Add grading scale",
        form=form,
        back_url=reverse("super:grading_list"),
        breadcrumb_extra="Grading",
    )


# --- Plans ---


@require_http_methods(["GET", "POST"])
def super_plan_edit(request, pk: int):
    plan = get_object_or_404(Plan, pk=pk)
    if request.method == "POST":
        form = PlanSuperForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, "Plan saved.")
            return redirect("super:plans_list")
    else:
        form = PlanSuperForm(instance=plan)
    addons = list(PlanAddon.objects.all().order_by("name"))
    return render(
        request,
        "schools/super_plan_form.html",
        {
            **_ctx(request),
            "page_title": f"Edit plan {plan.slug}",
            "form": form,
            "back_url": reverse("super:plans_list"),
            "breadcrumb_extra": "Plans",
            "plan": plan,
            "addons": addons,
            "delete_url": reverse("super:plan_delete", kwargs={"pk": plan.pk}),
        },
    )


@require_http_methods(["GET", "POST"])
def super_plan_add(request):
    if request.method == "POST":
        form = PlanSuperForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Plan created.")
            return redirect("super:plans_list")
    else:
        form = PlanSuperForm()
    return _render_form(
        request,
        title="Add plan",
        form=form,
        back_url=reverse("super:plans_list"),
        breadcrumb_extra="Plans",
    )


@require_http_methods(["GET", "POST"])
def super_plan_addon_edit(request, pk: int):
    addon = get_object_or_404(PlanAddon, pk=pk)
    if request.method == "POST":
        form = PlanAddonSuperForm(request.POST, instance=addon)
        if form.is_valid():
            form.save()
            messages.success(request, "Add-on saved.")
            return redirect("super:plans_list")
    else:
        form = PlanAddonSuperForm(instance=addon)
    return _render_form(
        request,
        title=f"Edit add-on {addon.code}",
        form=form,
        back_url=reverse("super:plans_list"),
        breadcrumb_extra="Plans",
        delete_url=reverse("super:plan_addon_delete", kwargs={"pk": addon.pk}),
    )


@require_http_methods(["GET", "POST"])
def super_plan_addon_add(request):
    if request.method == "POST":
        form = PlanAddonSuperForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Add-on created.")
            return redirect("super:plans_list")
    else:
        form = PlanAddonSuperForm()
    return _render_form(
        request,
        title="Add plan add-on",
        form=form,
        back_url=reverse("super:plans_list"),
        breadcrumb_extra="Plans",
    )


# --- Feature toggles ---


@require_http_methods(["GET", "POST"])
def super_feature_toggle_edit(request, pk: int):
    row = get_object_or_404(FeatureToggleDefinition, pk=pk)
    if request.method == "POST":
        form = FeatureToggleDefinitionSuperForm(request.POST, instance=row)
        if form.is_valid():
            form.save()
            messages.success(request, "Feature toggle definition saved.")
            return redirect("super:feature_toggles_list")
    else:
        form = FeatureToggleDefinitionSuperForm(instance=row)
    return _render_form(
        request,
        title=f"Edit toggle: {row.key}",
        form=form,
        back_url=reverse("super:feature_toggles_list"),
        breadcrumb_extra="Feature toggles",
        delete_url=reverse("super:feature_toggle_delete", kwargs={"pk": row.pk}),
    )


@require_http_methods(["GET", "POST"])
def super_feature_toggle_add(request):
    if request.method == "POST":
        form = FeatureToggleDefinitionSuperForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Feature toggle definition created.")
            return redirect("super:feature_toggles_list")
    else:
        form = FeatureToggleDefinitionSuperForm()
    return _render_form(
        request,
        title="Add feature toggle definition",
        form=form,
        back_url=reverse("super:feature_toggles_list"),
        breadcrumb_extra="Feature toggles",
    )


# --- Deletes (confirm on GET; execute on POST confirm=yes) ---


@require_http_methods(["GET", "POST"])
def super_region_delete(request, code: str):
    region = get_object_or_404(RegionConfig, pk=code)
    from apps.schools.models import School

    school_count = School.objects.filter(default_region=region).count()
    warning_lines = [
        str(
            _(
                "Deleting removes related grading scales and education profiles (cascade). "
                "Schools with this default region will block delete (protected)."
            )
        ),
    ]
    if school_count:
        warning_lines.insert(
            0,
            str(
                _("{n} school(s) currently use this region as default.").format(
                    n=school_count
                )
            ),
        )

    if request.method == "POST" and request.POST.get("confirm") == "yes":
        try:
            region.delete()
        except ProtectedError:
            messages.error(
                request,
                str(
                    _(
                        "Cannot delete: schools or other records still reference this region. "
                        "Reassign schools first."
                    )
                ),
            )
            return redirect("super:regions_list")
        messages.success(request, str(_("Region deleted.")))
        return redirect("super:regions_list")

    return _render_delete_confirm(
        request,
        page_title=_("Delete region"),
        object_label=str(region),
        back_url=reverse("super:regions_list"),
        breadcrumb_extra=_("Regions"),
        delete_action_url=reverse("super:region_delete", kwargs={"code": region.code}),
        warning_lines=warning_lines,
    )


@require_http_methods(["GET", "POST"])
def super_grading_delete(request, pk: int):
    row = get_object_or_404(GradingScaleConfig.objects.select_related("region"), pk=pk)
    if request.method == "POST" and request.POST.get("confirm") == "yes":
        row.delete()
        messages.success(request, str(_("Grading scale deleted.")))
        return redirect("super:grading_list")

    return _render_delete_confirm(
        request,
        page_title=_("Delete grading scale"),
        object_label=str(row),
        back_url=reverse("super:grading_list"),
        breadcrumb_extra=_("Grading"),
        delete_action_url=reverse("super:grading_delete", kwargs={"pk": row.pk}),
        warning_lines=[str(_("This action cannot be undone."))],
    )


@require_http_methods(["GET", "POST"])
def super_plan_delete(request, pk: int):
    plan = get_object_or_404(Plan, pk=pk)
    if request.method == "POST" and request.POST.get("confirm") == "yes":
        plan.delete()
        messages.success(request, str(_("Plan deleted.")))
        return redirect("super:plans_list")

    return _render_delete_confirm(
        request,
        page_title=_("Delete plan"),
        object_label=str(plan),
        back_url=reverse("super:plans_list"),
        breadcrumb_extra=_("Plans"),
        delete_action_url=reverse("super:plan_delete", kwargs={"pk": plan.pk}),
        warning_lines=[
            str(
                _(
                    "School or subscription rows that referenced this plan will have plan set to empty (SET_NULL)."
                )
            ),
        ],
    )


@require_http_methods(["GET", "POST"])
def super_plan_addon_delete(request, pk: int):
    addon = get_object_or_404(PlanAddon, pk=pk)
    if request.method == "POST" and request.POST.get("confirm") == "yes":
        addon.delete()
        messages.success(request, str(_("Add-on deleted.")))
        return redirect("super:plans_list")

    return _render_delete_confirm(
        request,
        page_title=_("Delete plan add-on"),
        object_label=str(addon),
        back_url=reverse("super:plans_list"),
        breadcrumb_extra=_("Plans"),
        delete_action_url=reverse("super:plan_addon_delete", kwargs={"pk": addon.pk}),
        warning_lines=[str(_("This action cannot be undone."))],
    )


@require_http_methods(["GET", "POST"])
def super_feature_toggle_delete(request, pk: int):
    row = get_object_or_404(FeatureToggleDefinition, pk=pk)
    state_count = row.states.count()
    warning_lines = [
        str(
            _(
                "All per-school and global override rows for this definition will be removed (cascade)."
            )
        ),
    ]
    if state_count:
        warning_lines.insert(
            0,
            str(_("{n} toggle state row(s) will be deleted.").format(n=state_count)),
        )

    if request.method == "POST" and request.POST.get("confirm") == "yes":
        row.delete()
        messages.success(request, _("Feature toggle definition deleted."))
        return redirect("super:feature_toggles_list")

    return _render_delete_confirm(
        request,
        page_title=_("Delete feature toggle definition"),
        object_label=str(row),
        back_url=reverse("super:feature_toggles_list"),
        breadcrumb_extra=_("Feature toggles"),
        delete_action_url=reverse(
            "super:feature_toggle_delete", kwargs={"pk": row.pk}
        ),
        warning_lines=warning_lines,
    )


# --- Country price multipliers ---


@require_http_methods(["GET", "POST"])
def super_country_multiplier_add(request):
    if request.method == "POST":
        form = CountryMultiplierSuperForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, str(_("Country multiplier created.")))
            return redirect("super:country_multipliers_list")
    else:
        form = CountryMultiplierSuperForm()
    return _render_form(
        request,
        title=_("Add country multiplier"),
        form=form,
        back_url=reverse("super:country_multipliers_list"),
        breadcrumb_extra=_("Country multipliers"),
    )


@require_http_methods(["GET", "POST"])
def super_country_multiplier_edit(request, pk: int):
    row = get_object_or_404(CountryMultiplier, pk=pk)
    if request.method == "POST":
        form = CountryMultiplierSuperForm(request.POST, instance=row)
        if form.is_valid():
            form.save()
            messages.success(request, _("Country multiplier saved."))
            return redirect("super:country_multipliers_list")
    else:
        form = CountryMultiplierSuperForm(instance=row)
    return _render_form(
        request,
        title=str(_("Edit country multiplier %s") % row.country_code),
        form=form,
        back_url=reverse("super:country_multipliers_list"),
        breadcrumb_extra=_("Country multipliers"),
        delete_url=reverse("super:country_multiplier_delete", kwargs={"pk": row.pk}),
    )


@require_http_methods(["GET", "POST"])
def super_country_multiplier_delete(request, pk: int):
    row = get_object_or_404(CountryMultiplier, pk=pk)
    if request.method == "POST" and request.POST.get("confirm") == "yes":
        row.delete()
        messages.success(request, str(_("Country multiplier deleted.")))
        return redirect("super:country_multipliers_list")

    return _render_delete_confirm(
        request,
        page_title=_("Delete country multiplier"),
        object_label=str(row),
        back_url=reverse("super:country_multipliers_list"),
        breadcrumb_extra=_("Country multipliers"),
        delete_action_url=reverse(
            "super:country_multiplier_delete", kwargs={"pk": row.pk}
        ),
        warning_lines=[str(_("This action cannot be undone."))],
    )
