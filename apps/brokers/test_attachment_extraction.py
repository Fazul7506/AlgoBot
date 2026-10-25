import io
import zipfile
from unittest import TestCase
from unittest.mock import Mock, patch

from apps.brokers.attachment_extraction import (
    AttachmentExtractionError,
    decode_data_url,
    extract_document_text,
)


class AttachmentExtractionTests(TestCase):
    def test_plain_text_extraction_is_bounded_and_decodes_utf8(self):
        self.assertEqual(extract_document_text(".txt", "hello café".encode()), "hello café")

    def test_data_url_rejects_mime_mismatch_and_invalid_base64(self):
        with self.assertRaises(AttachmentExtractionError):
            decode_data_url("data:image/png;base64,aGVsbG8=", "image/jpeg")
        with self.assertRaises(AttachmentExtractionError):
            decode_data_url("data:application/pdf;base64,not base64!")

    def test_docx_text_is_extracted_without_executing_embedded_content(self):
        output = io.BytesIO()
        document_xml = b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>AlgoBot integration plan</w:t></w:r></w:p></w:body></w:document>'
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", document_xml)
            archive.writestr("word/vbaProject.bin", b"not executed")
        extracted = extract_document_text(".docx", output.getvalue())
        self.assertIn("AlgoBot integration plan", extracted)
        self.assertNotIn("vbaProject", extracted)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("requests.post")
    def test_audio_transcription_returns_transcript_without_exposing_api_key(self, post):
        from apps.brokers.attachment_extraction import transcribe_audio
        response = Mock()
        response.ok = True
        response.json.return_value = {"text": "Turn left at the next street."}
        post.return_value = response

        transcript = transcribe_audio(b"audio bytes", "sample.wav")

        self.assertEqual(transcript, "Turn left at the next street.")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertNotIn("test-key", transcript)

    def test_unknown_binary_format_is_rejected(self):
        with self.assertRaises(AttachmentExtractionError):
            extract_document_text(".exe", b"binary")
