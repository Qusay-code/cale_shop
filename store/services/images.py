"""
Image processing services for CALE Shop.

This module is responsible for safely processing uploaded images
before they are stored in the database/media storage.

Processing pipeline:
1. Validate upload size.
2. Verify that the file is a real image.
3. Protect against decompression-bomb images.
4. Correct EXIF orientation.
5. Convert to a web-friendly color mode.
6. Resize large images while preserving aspect ratio.
7. Compress and convert the result to WebP.
8. Generate a safe unique filename.
"""

from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps
from PIL.Image import DecompressionBombError, DecompressionBombWarning


# Maximum original upload size.
# Keep this limit aligned with the request upload handler and reverse proxy.
MAX_UPLOAD_SIZE = 10 * 1024 * 1024


# Maximum number of pixels allowed in an image.
# This protects the server from extremely large/decompression-bomb images.
MAX_IMAGE_PIXELS = 60_000_000


# Maximum dimension of the processed image.
# Example:
# 6000x4000 -> 2400x1600
MAX_IMAGE_DIMENSION = 2400


# WebP quality.
# 85 provides a good balance between visual quality and file size.
WEBP_QUALITY = 85


# Formats accepted by the image pipeline.
ALLOWED_IMAGE_FORMATS = {
    "JPEG",
    "PNG",
    "WEBP",
}


def validate_uploaded_image(uploaded_file) -> None:
    """
    Validate an uploaded image before processing.

    Validation includes:
    - File size.
    - Real image verification.
    - Supported image format.
    - Protection against extremely large images.

    Args:
        uploaded_file:
            Django UploadedFile instance.

    Raises:
        ValidationError:
            If the uploaded file is invalid or unsafe.
    """

    if uploaded_file is None:
        raise ValidationError("لم يتم اختيار صورة.")

    # ---------------------------------------------------------
    # 1. Validate original file size.
    # ---------------------------------------------------------

    if uploaded_file.size > MAX_UPLOAD_SIZE:
        raise ValidationError(
            "حجم الصورة كبير جدًا. الحد الأقصى هو 10 ميجابايت."
        )

    # ---------------------------------------------------------
    # 2. Configure Pillow's decompression-bomb protection.
    # ---------------------------------------------------------

    previous_max_pixels = Image.MAX_IMAGE_PIXELS

    try:
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

        uploaded_file.seek(0)

        with Image.open(uploaded_file) as image:

            # Pillow may emit a warning before raising an error
            # for extremely large images.
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValidationError(
                    "أبعاد الصورة كبيرة جدًا ولا يمكن معالجتها بأمان."
                )

            if image.format not in ALLOWED_IMAGE_FORMATS:
                raise ValidationError(
                    "صيغة الصورة غير مدعومة. "
                    "استخدم JPG أو PNG أو WEBP."
                )

            # Verify the actual image structure.
            image.verify()

    except (DecompressionBombError, DecompressionBombWarning):
        raise ValidationError(
            "الصورة كبيرة جدًا أو غير آمنة للمعالجة."
        )

    except (OSError, SyntaxError, ValueError):
        raise ValidationError(
            "الملف المرفوع ليس صورة صالحة."
        )

    finally:
        Image.MAX_IMAGE_PIXELS = previous_max_pixels

        try:
            uploaded_file.seek(0)
        except (AttributeError, OSError):
            pass


def process_uploaded_image(
    uploaded_file,
    *,
    max_dimension: int = MAX_IMAGE_DIMENSION,
    quality: int = WEBP_QUALITY,
) -> tuple[str, ContentFile]:
    """
    Validate, resize and compress an uploaded image.

    The original uploaded image is not stored directly.

    Instead:

        Original image
              ↓
        Security validation
              ↓
        EXIF orientation correction
              ↓
        Resize if necessary
              ↓
        WebP compression
              ↓
        Unique .webp filename

    Args:
        uploaded_file:
            Django UploadedFile instance.

        max_dimension:
            Maximum width or height of the final image.

        quality:
            WebP quality from 1 to 100.

    Returns:
        A tuple containing:
            filename
            ContentFile

    Raises:
        ValidationError:
            If the image cannot be safely processed.
    """

    if not 1 <= quality <= 100:
        raise ValidationError(
            "قيمة جودة الصورة يجب أن تكون بين 1 و100."
        )

    if max_dimension <= 0:
        raise ValidationError(
            "أبعاد الصورة غير صحيحة."
        )

    # First perform all security validation.
    validate_uploaded_image(uploaded_file)

    try:
        uploaded_file.seek(0)

        with Image.open(uploaded_file) as source_image:

            # Correct images that were taken with a camera/phone
            # using EXIF orientation metadata.
            image = ImageOps.exif_transpose(source_image)

            # Preserve transparency for PNG/WebP images.
            has_alpha = (
                image.mode in ("RGBA", "LA")
                or "transparency" in image.info
            )

            if has_alpha:
                image = image.convert("RGBA")
            else:
                image = image.convert("RGB")

            # Resize while preserving the original aspect ratio.
            image.thumbnail(
                (max_dimension, max_dimension),
                Image.Resampling.LANCZOS,
            )

            output = BytesIO()

            save_kwargs = {
                "format": "WEBP",
                "quality": quality,
                "method": 6,
            }

            # Preserve ICC color profile when available.
            icc_profile = source_image.info.get("icc_profile")

            if icc_profile:
                save_kwargs["icc_profile"] = icc_profile

            image.save(
                output,
                **save_kwargs,
            )

    except (OSError, ValueError, SyntaxError):
        raise ValidationError(
            "تعذر معالجة الصورة. يرجى اختيار صورة أخرى."
        )

    finally:
        try:
            uploaded_file.seek(0)
        except (AttributeError, OSError):
            pass

    output.seek(0)

    # Generate a unique filename.
    filename = f"{uuid4().hex}.webp"

    return filename, ContentFile(
        output.getvalue(),
        name=filename,
    )

def delete_stored_image(file_field) -> None:
    """
    Delete an existing stored image safely.

    Args:
        file_field:
            Django FieldFile instance representing the stored image.

    The function does nothing when the field is empty.
    """
    if not file_field:
        return

    if not file_field.name:
        return

    storage = file_field.storage

    if storage.exists(file_field.name):
        storage.delete(file_field.name)
