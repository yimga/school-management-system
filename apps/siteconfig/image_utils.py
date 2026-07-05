import base64
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile


def resize_logo_to_data_uri(image_bytes, *, max_dim=512):
    """Resize/optimize raw logo bytes and return an inline ``data:`` URI.

    Returns ``(data_uri, mime, out_bytes, was_resized)`` where ``data_uri`` is a
    ``data:<mime>;base64,<...>`` string that renders in any ``<img src>`` WITHOUT
    a media-serving backend — so an uploaded logo survives ephemeral disks and
    hosts with no object storage (the root cause of "logo uploaded but not
    shown"). ``out_bytes`` is the re-encoded (possibly shrunk) image so the
    caller can persist/validate the same bytes it displays. ``was_resized`` is
    True when the source exceeded ``max_dim`` on either axis.

    Returns ``None`` when the bytes are not a Pillow-decodable raster image
    (e.g. SVG or corrupt input), so the caller can fall back to its normal
    validation / rejection path.
    """
    if not image_bytes:
        return None
    try:
        img = Image.open(BytesIO(image_bytes))
        img.load()
    except Exception:
        return None

    orig_w, orig_h = img.size
    src_fmt = (img.format or "").upper()
    was_resized = orig_w > max_dim or orig_h > max_dim
    if was_resized:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    has_alpha = ("A" in img.getbands()) or (
        img.mode == "P" and "transparency" in img.info
    )

    buffer = BytesIO()
    if src_fmt in ("JPEG", "JPG") and not has_alpha:
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(buffer, "JPEG", optimize=True, quality=85)
        mime = "image/jpeg"
    else:
        # PNG preserves transparency and is universally supported as a data URI.
        if img.mode not in ("RGBA", "RGB", "LA", "L", "P"):
            img = img.convert("RGBA")
        img.save(buffer, "PNG", optimize=True)
        mime = "image/png"

    out_bytes = buffer.getvalue()
    data_uri = "data:%s;base64,%s" % (
        mime,
        base64.b64encode(out_bytes).decode("ascii"),
    )
    return (data_uri, mime, out_bytes, was_resized)


def optimize_image(image_field, max_width=1920, max_height=1080, quality=85):
    """
    Optimize and compress an uploaded image for web delivery.
    - Resizes to fit within max_width/max_height (preserving aspect ratio)
    - Converts to RGB (removes alpha for JPEG)
    - Saves as JPEG or PNG with optimized settings
    - Returns a new ContentFile ready to be saved to an ImageField
    """
    if not image_field:
        return None

    img = Image.open(image_field)
    img_format = img.format
    # Resize if needed
    img.thumbnail((max_width, max_height), Image.LANCZOS)

    # Convert to RGB for JPEG
    if img_format == "JPEG" or img_format == "JPG":
        if img.mode != "RGB":
            img = img.convert("RGB")
        output_format = "JPEG"
        ext = "jpg"
    elif img_format == "PNG":
        if img.mode in ("RGBA", "LA"):
            # Remove alpha for PNG if not needed
            background = Image.new("RGBA", img.size, (255, 255, 255, 0))
            background.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
            img = background
        output_format = "PNG"
        ext = "png"
    else:
        # Fallback to PNG
        img = img.convert("RGBA")
        output_format = "PNG"
        ext = "png"

    buffer = BytesIO()
    save_kwargs = (
        {"optimize": True, "quality": quality}
        if output_format == "JPEG"
        else {"optimize": True}
    )
    img.save(buffer, output_format, **save_kwargs)
    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"optimized.{ext}")
