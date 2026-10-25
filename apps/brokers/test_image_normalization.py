import io
from unittest import TestCase

from PIL import Image

from apps.brokers.attachment_extraction import (
    AttachmentExtractionError,
    normalize_image_for_vision,
)


class ImageNormalizationTests(TestCase):
    def _image_bytes(self, image_format):
        image = Image.new("RGBA", (16, 16), (255, 0, 0, 128))
        output = io.BytesIO()
        image.save(output, format=image_format)
        return output.getvalue()

    def test_gif_is_normalized_to_a_model_supported_format(self):
        mime, data = normalize_image_for_vision(self._image_bytes("GIF"), "image/gif")
        self.assertIn(mime, {"image/png", "image/jpeg"})
        self.assertTrue(data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8"))

    def test_rejects_unsupported_mime_types(self):
        with self.assertRaises(AttachmentExtractionError):
            normalize_image_for_vision(b"not an image", "image/svg+xml")
