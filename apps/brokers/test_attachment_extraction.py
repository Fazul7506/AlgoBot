import base64
import io
import zipfile

import pytest

from apps.brokers.attachment_extraction import (
    AttachmentExtractionError,
    decode_data_url,
    extract_document_text,
)


def test_plain_text_extraction_is_bounded_and_decodes_utf8():
    assert extract_document_text(".txt", "hello café".encode()) == "hello café"


def test_data_url_rejects_mime_mismatch_and_invalid_base64():
    with pytest.raises(AttachmentExtractionError):
        decode_data_url("data:image/png;base64,aGVsbG8=", "image/jpeg")
    with pytest.raises(AttachmentExtractionError):
        decode_data_url("data:application/pdf;base64,not base64!")


def test_docx_text_is_extracted_without_executing_embedded_content():
    output = io.BytesIO()
    document_xml = b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>AlgoBot integration plan</w:t></w:r></w:p></w:body></w:document>'
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/vbaProject.bin", b"not executed")
    extracted = extract_document_text(".docx", output.getvalue())
    assert "AlgoBot integration plan" in extracted
    assert "vbaProject" not in extracted


def test_unknown_binary_format_is_rejected():
    with pytest.raises(AttachmentExtractionError):
        extract_document_text(".exe", b"binary")
