from django import template

from apps.platform_runtime.super_operational_frames import resolve_super_operational_frame

register = template.Library()


@register.inclusion_tag("components/rmc_operational_center_frame.html", takes_context=True)
def rmc_operational_frame(
    context,
    slug,
    title="",
    subtitle="",
    status_badge="",
    primary_url="",
    primary_label="",
    secondary_url="",
    secondary_label="",
    eyebrow="",
):
    """Render v8 steering frame; title/subtitle map to center_title/purpose."""
    frame = resolve_super_operational_frame(
        slug,
        center_title=title or "Operations",
        center_purpose=subtitle or "",
        center_eyebrow=eyebrow or "Platform operators",
        status_badge_text=status_badge or "",
        primary_url=primary_url or "",
        primary_label=primary_label or "",
        secondary_url=secondary_url or "",
        secondary_label=secondary_label or "",
    )
    return frame
