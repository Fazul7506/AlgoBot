"""Extract text from common document attachments without executing document content."""
from __future__ import annotations

import base64
import binascii
import io
import os
import re
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

MAX_DECODED_BYTES = 4 * 1024 * 1024
MAX_EXTRACTED_CHARS = 200_000
TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".py", ".js", ".jsx", ".ts", ".tsx", ".html",
    ".css", ".scss", ".yaml", ".yml", ".toml", ".csv", ".tsv", ".log",
    ".xml", ".sql", ".sh", ".bash", ".ini", ".cfg", ".conf", ".rtf", ".ipynb",
    ".go", ".rs", ".java", ".kt", ".kts", ".swift", ".c", ".h", ".cc", ".cpp", ".hpp",
    ".cs", ".php", ".rb", ".r", ".scala", ".lua", ".pl", ".vue", ".svelte", ".astro",
    ".mdx", ".graphql", ".gql", ".proto", ".prisma", ".tf", ".hcl", ".dockerfile", ".lock",
}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".odt", ".ods", ".epub", ".zip"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mpga", ".mpeg", ".mp4", ".webm", ".ogg", ".opus", ".flac", ".aac"}
IMAGE_MIME_TYPES = {
    "image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp",
    "image/tiff", "image/x-ms-bmp",
}
VISION_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}


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
    if extension == ".zip":
        chunks = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > 1000 or sum(entry.file_size for entry in entries) > 20 * 1024 * 1024:
                    raise AttachmentExtractionError("The ZIP archive expands beyond the safe 20 MB / 1,000-file limit.")
                for entry in entries:
                    name = PurePosixPath(entry.filename)
                    if name.is_absolute() or ".." in name.parts or entry.is_dir():
                        if name.is_absolute() or ".." in name.parts:
                            raise AttachmentExtractionError("The ZIP archive contains unsafe paths.")
                        continue
                    if entry.file_size > MAX_DECODED_BYTES:
                        continue
                    inner_ext = Path(name.name).suffix.lower()
                    if inner_ext in TEXT_EXTENSIONS:
                        raw = archive.read(entry)
                        chunks.append(f"--- {entry.filename} ---\\n" + raw.decode("utf-8-sig", errors="replace"))
                    elif inner_ext in DOCUMENT_EXTENSIONS - {".zip"}:
                        try:
                            extracted = extract_document_text(inner_ext, archive.read(entry))
                        except AttachmentExtractionError:
                            continue
                        chunks.append(f"--- {entry.filename} ---\\n" + extracted)
                    if sum(map(len, chunks)) >= MAX_EXTRACTED_CHARS:
                        break
        except AttachmentExtractionError:
            raise
        except (zipfile.BadZipFile, OSError, KeyError, RuntimeError) as exc:
            raise AttachmentExtractionError("The ZIP archive is invalid or could not be read.") from exc
        if not chunks:
            raise AttachmentExtractionError("No readable text or supported documents were found in the ZIP archive.")
        return _clean_text("\\n".join(chunks))
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


def transcribe_audio(data: bytes, filename: str) -> str:
    """Transcribe a small user-supplied audio file through the configured OpenAI API."""
    if len(data) > MAX_DECODED_BYTES:
        raise AttachmentExtractionError("The decoded audio exceeds the 4 MB per-file limit.")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        try:
            from django.conf import settings
            api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
        except Exception:
            api_key = ""
    if not api_key:
        raise AttachmentExtractionError("Audio transcription requires OPENAI_API_KEY; no audio was processed.")
    import requests
    try:
        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (Path(filename).name[:180] or "audio.bin", data, "application/octet-stream")},
            data={"model": "whisper-1"},
            timeout=(10, 90),
        )
    except requests.RequestException as exc:
        raise AttachmentExtractionError("The audio transcription service could not be reached.") from exc
    if not response.ok:
        raise AttachmentExtractionError(f"Audio transcription failed with HTTP {response.status_code}.")
    try:
        text = str(response.json().get("text") or "").strip()
    except (ValueError, TypeError):
        text = ""
    if not text:
        raise AttachmentExtractionError("No speech transcript was returned for this audio file.")
    return _clean_text(text)


def normalize_image_for_vision(data: bytes, mime_type: str) -> tuple[str, bytes]:
    """Decode common still-image formats and normalize them to model-supported PNG/JPEG/WebP."""
    if mime_type.lower() not in IMAGE_MIME_TYPES:
        raise AttachmentExtractionError("This image format is not supported.")
    if len(data) > MAX_DECODED_BYTES:
        raise AttachmentExtractionError("The decoded image exceeds the 4 MB per-file limit.")
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
        with Image.open(io.BytesIO(data)) as source:
            if getattr(source, "n_frames", 1) > 1:
                source.seek(0)
            source.load()
            if source.width * source.height > 20_000_000:
                raise AttachmentExtractionError("The image dimensions exceed the safe 20-megapixel limit.")
            image = ImageOps.exif_transpose(source)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            output = io.BytesIO()
            if image.mode == "RGBA":
                image.save(output, format="PNG", optimize=True)
                result_mime = "image/png"
            else:
                image.save(output, format="JPEG", quality=88, optimize=True)
                result_mime = "image/jpeg"
            normalized = output.getvalue()
            if len(normalized) > MAX_DECODED_BYTES:
                image.thumbnail((2048, 2048))
                image = image.convert("RGB")
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=78, optimize=True)
                normalized = output.getvalue()
                result_mime = "image/jpeg"
            if len(normalized) > MAX_DECODED_BYTES:
                raise AttachmentExtractionError("The normalized image exceeds the 4 MB limit.")
            return result_mime, normalized
    except AttachmentExtractionError:
        raise
    except Exception as exc:
        raise AttachmentExtractionError("The image could not be safely decoded.") from exc


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
