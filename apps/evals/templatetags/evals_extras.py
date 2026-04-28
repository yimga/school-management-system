from django import template

register = template.Library()


@register.filter
def get_item(d, key):
    if d is None:
        return None
    return d.get(key)


@register.filter
def evaluation_incomplete(evaluation, required_fields):
    """Return True if any required field is missing on the evaluation.

    Used for UI indicators ("marks filled" / "missing marks").
    """
    if required_fields is None:
        required_fields = []

    # If no evaluation row exists yet, it's incomplete.
    if evaluation is None:
        return True

    for field in required_fields:
        value = getattr(evaluation, field, None)
        if value is None:
            return True
    return False


@register.simple_tag
def rosetta_view_grade_line(evaluation, to_scale="0-100"):
    """One-line “view in target system” for report/grade templates (see ``view_grade_in_target_system``)."""
    from apps.evals.rosetta_stone import format_rosetta_line

    if evaluation is None:
        return "—"
    return format_rosetta_line(evaluation, to_scale)
