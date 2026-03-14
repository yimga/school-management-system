"""
Image processing utilities for the School Management System.
Provides image compression, resizing, and optimization for better performance.
"""

import os
import logging
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Handles image compression and optimization"""

    # Maximum dimensions for different image types
    MAX_SIZES = {
        'profile': (400, 400),      # Profile photos
        'document': (1200, 1600),   # Document scans
        'logo': (300, 300),         # Logos and icons
        'general': (800, 600),      # General images
    }

    # Quality settings for different formats
    QUALITY_SETTINGS = {
        'JPEG': 85,
        'PNG': 95,  # PNG is lossless, but we can optimize
        'WEBP': 80,
    }

    @staticmethod
    def compress_image(image_file, image_type='general', max_size_mb=2):
        """
        Compress and optimize an uploaded image.

        Args:
            image_file: Django File object or file path
            image_type: Type of image ('profile', 'document', 'logo', 'general')
            max_size_mb: Maximum file size in MB

        Returns:
            ContentFile: Optimized image as Django ContentFile
        """
        try:
            # Open image
            if hasattr(image_file, 'read'):
                # Django file object
                image = Image.open(image_file)
                original_name = getattr(image_file, 'name', 'image.jpg')
            else:
                # File path
                image = Image.open(image_file)
                original_name = os.path.basename(image_file)

            # Convert to RGB if necessary (for JPEG compatibility)
            if image.mode in ('RGBA', 'LA', 'P'):
                # Create white background for transparent images
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')

            # Get max dimensions for this image type
            max_width, max_height = ImageProcessor.MAX_SIZES.get(image_type, (800, 600))

            # Resize if necessary
            if image.width > max_width or image.height > max_height:
                image.thumbnail((max_width, max_height), Image.LANCZOS)

            # Determine output format
            original_ext = os.path.splitext(original_name)[1].lower()
            if original_ext in ['.jpg', '.jpeg']:
                output_format = 'JPEG'
                file_extension = 'jpg'
            elif original_ext == '.png':
                output_format = 'PNG'
                file_extension = 'png'
            else:
                # Default to WebP for better compression
                output_format = 'WEBP'
                file_extension = 'webp'

            # Compress and save to BytesIO
            output_buffer = BytesIO()
            quality = ImageProcessor.QUALITY_SETTINGS.get(output_format, 85)

            # For PNG, we can try to optimize without quality loss
            if output_format == 'PNG':
                # Try PNG optimization
                image.save(output_buffer, format=output_format, optimize=True)
            else:
                image.save(output_buffer, format=output_format, quality=quality, optimize=True)

            # Check file size
            file_size = output_buffer.tell()
            max_size_bytes = max_size_mb * 1024 * 1024

            # If still too large, reduce quality further
            if file_size > max_size_bytes and output_format != 'PNG':
                output_buffer = BytesIO()
                reduced_quality = max(quality - 20, 50)  # Minimum quality of 50
                image.save(output_buffer, format=output_format, quality=reduced_quality, optimize=True)

            # Create new filename
            base_name = os.path.splitext(original_name)[0]
            new_filename = f"{base_name}_optimized.{file_extension}"

            # Return as ContentFile
            output_buffer.seek(0)
            return ContentFile(output_buffer.getvalue(), name=new_filename)

        except Exception as e:
            logger.error(f"Error compressing image {original_name}: {str(e)}")
            # Return original file if compression fails
            if hasattr(image_file, 'read'):
                image_file.seek(0)
                return ContentFile(image_file.read(), name=getattr(image_file, 'name', 'image.jpg'))
            else:
                with open(image_file, 'rb') as f:
                    return ContentFile(f.read(), name=os.path.basename(image_file))

    @staticmethod
    def create_thumbnail(image_file, size=(150, 150)):
        """
        Create a thumbnail from an image.

        Args:
            image_file: Django File object or file path
            size: Tuple of (width, height) for thumbnail

        Returns:
            ContentFile: Thumbnail as Django ContentFile
        """
        try:
            # Open image
            if hasattr(image_file, 'read'):
                image = Image.open(image_file)
                original_name = getattr(image_file, 'name', 'image.jpg')
            else:
                image = Image.open(image_file)
                original_name = os.path.basename(image_file)

            # Convert to RGB
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Create thumbnail
            image.thumbnail(size, Image.LANCZOS)

            # Save to BytesIO
            thumb_buffer = BytesIO()
            image.save(thumb_buffer, format='JPEG', quality=80, optimize=True)

            # Create filename
            base_name = os.path.splitext(original_name)[0]
            thumb_filename = f"{base_name}_thumb.jpg"

            thumb_buffer.seek(0)
            return ContentFile(thumb_buffer.getvalue(), name=thumb_filename)

        except Exception as e:
            logger.error(f"Error creating thumbnail for {original_name}: {str(e)}")
            return None

    @staticmethod
    def get_image_info(image_file):
        """
        Get information about an image file.

        Args:
            image_file: Django File object or file path

        Returns:
            dict: Image information
        """
        try:
            if hasattr(image_file, 'read'):
                image = Image.open(image_file)
            else:
                image = Image.open(image_file)

            return {
                'width': image.width,
                'height': image.height,
                'format': image.format,
                'mode': image.mode,
                'size_bytes': image_file.size if hasattr(image_file, 'size') else 0,
            }
        except Exception as e:
            logger.error(f"Error getting image info: {str(e)}")
            return {}


def compress_uploaded_image(sender, instance, **kwargs):
    """
    Signal handler to automatically compress uploaded images.
    Connect this to post_save signals for models with image fields.
    """
    # This would be implemented per model that has image fields
    pass