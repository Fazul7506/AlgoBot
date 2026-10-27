"""Validation and normalization helpers for user-uploaded profile pictures."""
import io

from PIL import Image, UnidentifiedImageError


MAX_PROFILE_PICTURE_BYTES = 5 * 1024 * 1024
MAX_PROFILE_PICTURE_PIXELS = 25_000_000
ALLOWED_PROFILE_PICTURE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


class ProfilePictureError(ValueError):
    """Raised when an uploaded profile picture is invalid."""


def normalize_profile_picture(upload):
    """Validate an uploaded image and return bounded WebP bytes and MIME type."""
    if upload is None:
        return None, ""

    if getattr(upload, "size", 0) > MAX_PROFILE_PICTURE_BYTES:
        raise ProfilePictureError("Profile picture must be 5 MB or smaller.")

    try:
        upload.seek(0)
        with Image.open(upload) as source:
            image_format = source.format
            if image_format not in ALLOWED_PROFILE_PICTURE_FORMATS:
                raise ProfilePictureError(
                    "Profile picture must be a JPEG, PNG, WEBP, or GIF image."
                )
            if source.width < 1 or source.height < 1:
                raise ProfilePictureError("The selected image has invalid dimensions.")
            if source.width * source.height > MAX_PROFILE_PICTURE_PIXELS:
                raise ProfilePictureError(
                    "Profile picture dimensions must not exceed 25 megapixels."
                )
            source.verify()

        upload.seek(0)
        with Image.open(upload) as source:
            source.seek(0)
            source.load()
            has_alpha = (
                source.mode in {"RGBA", "LA"}
                or "transparency" in source.info
            )
            image = source.convert("RGBA" if has_alpha else "RGB")
            image.thumbnail((512, 512), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=85, method=6)
            return output.getvalue(), "image/webp"
    except ProfilePictureError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
    ) as exc:
        raise ProfilePictureError(
            "Upload a valid image file (JPEG, PNG, WEBP, or GIF)."
        ) from exc
    finally:
        try:
            upload.seek(0)
        except (AttributeError, OSError, ValueError):
            pass
