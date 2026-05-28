"""Wave Q5 (v3.95.2 — 2026-05-26) — MAT Group Hub operator registry-editor form.

Operators previously edited ``SiteSettings.cockpit_payload["mat_groups"]`` as
raw JSON via Django admin. This form gives them a friendly UI:

- One line per member (`tenant_slug | display_name | region`).
- Group-level fields surfaced as regular form inputs.
- Round-trips through ``parse_mat_registry`` so the storage shape is the
  exact same JSON the kernel reads.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _



_MEMBERS_PLACEHOLDER = (
    "greenwich-park | Greenwich Park School | UK-London\n"
    "greenwich-meridian | Meridian Primary | UK-London"
)


class MATGroupEditorForm(forms.Form):
    """Single-group editor — add / replace one MAT group in the registry."""

    group_id = forms.CharField(
        max_length=120,
        label=_("Group ID"),
        help_text=_("Stable kebab-case key — used in URLs."),
    )
    display_name = forms.CharField(max_length=240, label=_("Display name"))
    operator_email = forms.EmailField(required=False, label=_("Operator email"))
    region = forms.CharField(required=False, max_length=120, label=_("Region"))
    members = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 8, "placeholder": _MEMBERS_PLACEHOLDER}),
        label=_("Members"),
        help_text=_(
            "One per line. Format: tenant_slug | display_name | region (region optional)."
        ),
    )
    delete = forms.BooleanField(
        required=False,
        label=_("Delete this group instead of saving"),
    )

    def clean_group_id(self):
        gid = (self.cleaned_data.get("group_id") or "").strip()
        if not gid:
            raise forms.ValidationError(_("Group ID is required."))
        if " " in gid or any(c.isupper() for c in gid):
            raise forms.ValidationError(
                _("Group ID must be lowercase kebab-case (no spaces, no upper)."),
            )
        return gid

    def clean_members(self):
        raw = (self.cleaned_data.get("members") or "").strip()
        # `clean_members` may run before `clean_delete`; read raw data to
        # detect the delete intent up-front so we skip member validation.
        delete_intent = bool(self.data.get("delete"))
        if delete_intent:
            return []
        if not raw:
            raise forms.ValidationError(_("At least one member is required."))
        out: list[dict[str, str]] = []
        for lineno, line in enumerate(raw.splitlines(), start=1):
            cleaned = line.strip()
            if not cleaned or cleaned.startswith("#"):
                continue
            parts = [p.strip() for p in cleaned.split("|")]
            if len(parts) < 2:
                raise forms.ValidationError(
                    _("Line %(n)d malformed: need 'slug | name [| region]'.")
                    % {"n": lineno},
                )
            slug = parts[0]
            name = parts[1]
            region = parts[2] if len(parts) >= 3 else ""
            if not slug or not name:
                raise forms.ValidationError(
                    _("Line %(n)d missing tenant_slug or display_name.")
                    % {"n": lineno},
                )
            out.append({
                "tenant_slug": slug,
                "display_name": name,
                "region": region,
            })
        if not out:
            raise forms.ValidationError(_("At least one member is required."))
        return out

    def to_payload_entry(self) -> dict[str, Any]:
        """Return the storage shape for a single group entry."""
        data = self.cleaned_data
        return {
            "display_name": data["display_name"],
            "operator_email": data.get("operator_email") or "",
            "region": data.get("region") or "",
            "members": data["members"],
        }


def apply_form_to_payload(
    payload: dict[str, Any] | None,
    form: MATGroupEditorForm,
) -> dict[str, Any]:
    """Apply the form's group to the existing operator payload.

    The payload shape is ``{"mat_groups": {group_id: {...}, ...}, ...}``.
    Returns the new payload (does not mutate input).
    """
    new_payload: dict[str, Any] = dict(payload or {})
    groups: dict[str, Any] = dict(new_payload.get("mat_groups") or {})
    group_id = form.cleaned_data["group_id"]
    if form.cleaned_data.get("delete"):
        groups.pop(group_id, None)
    else:
        groups[group_id] = form.to_payload_entry()
    new_payload["mat_groups"] = groups
    return new_payload


def load_form_initial_from_payload(
    payload: dict[str, Any] | None,
    group_id: str,
) -> dict[str, Any]:
    """Build the initial dict for the form when editing an existing group."""
    groups = (payload or {}).get("mat_groups") or {}
    entry = groups.get(group_id) or {}
    members = entry.get("members") or []
    members_text = "\n".join(
        f"{m.get('tenant_slug','')} | {m.get('display_name','')} "
        f"| {m.get('region','')}".rstrip(" |")
        for m in members if isinstance(m, dict)
    )
    return {
        "group_id": group_id,
        "display_name": entry.get("display_name", ""),
        "operator_email": entry.get("operator_email", ""),
        "region": entry.get("region", ""),
        "members": members_text,
    }
