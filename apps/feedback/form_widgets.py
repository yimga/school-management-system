"""Shared Bootstrap styling for feedback / feature forms."""

from __future__ import annotations


def apply_bootstrap_form_styles(form) -> None:
    """Apply form-control / form-select classes without duplicating per-view logic."""
    for field in form.fields.values():
        widget = field.widget
        cls = widget.attrs.get("class", "")
        if hasattr(widget, "input_type") and widget.input_type in (
            "text",
            "number",
            "email",
            "url",
            "search",
        ):
            widget.attrs["class"] = f"{cls} form-control".strip()
        elif widget.__class__.__name__ == "Textarea":
            widget.attrs["class"] = f"{cls} form-control".strip()
        elif widget.__class__.__name__ == "Select":
            widget.attrs["class"] = f"{cls} form-select".strip()
