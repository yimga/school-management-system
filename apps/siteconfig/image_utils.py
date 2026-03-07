from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile


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
    if img_format == 'JPEG' or img_format == 'JPG':
        if img.mode != 'RGB':
            img = img.convert('RGB')
        output_format = 'JPEG'
        ext = 'jpg'
    elif img_format == 'PNG':
        if img.mode in ('RGBA', 'LA'):
            # Remove alpha for PNG if not needed
            background = Image.new('RGBA', img.size, (255, 255, 255, 0))
            background.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
            img = background
        output_format = 'PNG'
        ext = 'png'
    else:
        # Fallback to PNG
        img = img.convert('RGBA')
        output_format = 'PNG'
        ext = 'png'

    buffer = BytesIO()
    save_kwargs = {'optimize': True, 'quality': quality} if output_format == 'JPEG' else {'optimize': True}
    img.save(buffer, output_format, **save_kwargs)
    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"optimized.{ext}")
