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


@register.simple_tag
def grade_band(scale_type, score):
    """Displayed grade label for a raw ``score`` on an operational ``scale_type``.

    The rich label for the non-numeric world scales — WAEC ``A1``…``F9``, ``Pass``/
    ``Fail``, qualitative descriptor — and the ordinary A–E letter otherwise. A grade
    surface that knows the school's scale renders its TRUE label via this one tag
    instead of a coarse letter: ``{% grade_band scale_type score %}``."""
    from apps.evals.grading import format_grade_band

    return format_grade_band(scale_type, score)
