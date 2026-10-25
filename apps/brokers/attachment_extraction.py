"""Extract text from common document attachments without executing document content."""
from __future__ import annotations

import base64
import binascii
import io
import re
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree

MAX_DECODED_BYTES = 4 * 1024 * 1024
MAX_EXTRACTED_CHARS = 200_000
TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".py", ".js", ".jsx", ".ts", ".tsx", ".html",
    ".css", ".scss", ".yaml", ".yml", ".toml", ".csv", ".tsv", ".log",
    ".xml", ".sql", ".sh", ".ini", ".cfg", ".conf", ".rtf",
}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".odt", ".ods", ".epub"}
IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}


class AttachmentExtractionError(ValueError):
    """Raised when an attachment cannot be safely extracted."""


def _clean_text(value: str) -> str:
    value = value.replace("\x00", "")
    value = re.sub(r"[ \t]+", " ", value)
    return value[:MAX_EXTRACTED_CHARS]


def _xml_text(data: bytes) -> str:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise AttachmentExtractionError("The document contains malformed XML.") from exc
    return " ".join(part.strip() for part in root.itertext() if part and part.strip())


def extract_document_text(extension: str, data: bytes) -> str:
    """Extract text from a bounded document payload; never run macros or embedded code."""
    extension = extension.lower()
    if len(data) > MAX_DECODED_BYTES:
        raise AttachmentExtractionError("The decoded file exceeds the 4 MB per-file limit.")
    if extension in TEXT_EXTENSIONS:
        text = data.decode("utf-8-sig", errors="replace")
        if extension == ".rtf":
            text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
            text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)
            text = text.replace("{", " ").replace("}", " ")
        return _clean_text(text)
    if extension == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise AttachmentExtractionError("PDF extraction is unavailable on this deployment; install pypdf to enable it.") from exc
        try:
            reader = PdfReader(io.BytesIO(data), strict=False)
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:200])
        except Exception as exc:
            raise AttachmentExtractionError("The PDF could not be parsed. Password-protected PDFs are not supported.") from exc
        return _clean_text(text)
    if extension not in DOCUMENT_EXTENSIONS - {".pdf"}:
        raise AttachmentExtractionError("This file format is not supported for text extraction.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            if len(names) > 2000 or sum(info.file_size for info in archive.infolist()) > 20 * 1024 * 1024:
                raise AttachmentExtractionError("The expanded document is too large to process safely.")
            if any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts for name in names):
                raise AttachmentExtractionError("The document archive contains unsafe paths.")
            if extension == ".docx":
                targets = [name for name in names if re.fullmatch(r"word/(document|footnotes|endnotes)\.xml", name)]
            elif extension == ".pptx":
                targets = sorted(name for name in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", name))
            elif extension == ".xlsx":
                targets = sorted(name for name in names if re.fullmatch(r"xl/sharedStrings\.xml|xl/worksheets/sheet\d+\.xml", name))
            elif extension == ".odt":
                targets = ["content.xml"] if "content.xml" in names else []
            elif extension == ".ods":
                targets = ["content.xml"] if "content.xml" in names else []
            else:  # EPUB
                targets = [name for name in names if name.lower().endswith((".xhtml", ".html", ".htm"))][:200]
            chunks = []
            for name in targets:
                chunks.append(_xml_text(archive.read(name)))
                if sum(map(len, chunks)) >= MAX_EXTRACTED_CHARS:
                    break
            extracted = "\n".join(chunks)
    except AttachmentExtractionError:
        raise
    except (zipfile.BadZipFile, OSError, KeyError, RuntimeError) as exc:
        raise AttachmentExtractionError("The document archive is invalid or could not be read.") from exc
    if not extracted.strip():
        raise AttachmentExtractionError("No readable text was found in this document.")
    return _clean_text(extracted)


def decode_data_url(data_url: str, expected_mime: str = "") -> tuple[str, bytes]:
    """Validate and decode a data URL with strict size and MIME checks."""
    if not isinstance(data_url, str) or not data_url.startswith("data:") or ";base64," not in data_url:
        raise AttachmentExtractionError("The attachment payload is not a valid base64 data URL.")
    header, encoded = data_url[5:].split(";base64,", 1)
    mime_type = header.lower()
    if expected_mime and mime_type != expected_mime.lower():
        raise AttachmentExtractionError("The attachment MIME type does not match its payload.")
    if len(encoded) > ((MAX_DECODED_BYTES + 2) // 3) * 4 + 8:
        raise AttachmentExtractionError("The encoded file exceeds the 4 MB per-file limit.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AttachmentExtractionError("The attachment is not valid base64 data.") from exc
    if len(data) > MAX_DECODED_BYTES:
        raise AttachmentExtractionError("The decoded file exceeds the 4 MB per-file limit.")
    return mime_type, data
