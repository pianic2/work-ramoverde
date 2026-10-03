"""Server-side inspection of uploaded files.

The client's Content-Type header and filename extension are never trusted: the type is
decided from the file's leading bytes (magic numbers) and images are fully decoded with
Pillow. Anything outside the allowlist (SVG, HTML, archives, executables...) is rejected.
"""

import hashlib
import os
import re
import warnings
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from PIL import Image

_SNIFF_BYTES = 64
_MP4_BRANDS = {b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"M4V "}


@dataclass(frozen=True)
class FileType:
    mime_type: str
    kind: str  # MediaAsset.Kind value
    extension: str
    allowed_extensions: frozenset[str]
    pillow_format: str | None = None


JPEG = FileType("image/jpeg", "IMAGE", ".jpg", frozenset({".jpg", ".jpeg"}), "JPEG")
PNG = FileType("image/png", "IMAGE", ".png", frozenset({".png"}), "PNG")
WEBP = FileType("image/webp", "IMAGE", ".webp", frozenset({".webp"}), "WEBP")
PDF = FileType("application/pdf", "DOCUMENT", ".pdf", frozenset({".pdf"}))
MP4 = FileType("video/mp4", "VIDEO", ".mp4", frozenset({".mp4"}))


@dataclass(frozen=True)
class InspectedFile:
    file_type: FileType
    size: int
    checksum_sha256: str
    width: int | None
    height: int | None
    original_filename: str


def sniff(head: bytes) -> FileType | None:
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return WEBP
    if head.startswith(b"%PDF-"):
        return PDF
    if head[4:8] == b"ftyp" and head[8:12] in _MP4_BRANDS:
        return MP4
    return None


def safe_original_filename(name: str | None) -> str:
    """Display-only basename: no directories, no control characters, bounded length."""
    base = os.path.basename((name or "").replace("\\", "/"))
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    return base[-255:] or "upload"


def _read_head(upload: UploadedFile) -> bytes:
    upload.seek(0)
    head = upload.read(_SNIFF_BYTES)
    upload.seek(0)
    return bytes(head)


def _checksum(upload: UploadedFile) -> str:
    digest = hashlib.sha256()
    upload.seek(0)
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    return digest.hexdigest()


def _image_dimensions(upload: UploadedFile, file_type: FileType) -> tuple[int, int]:
    invalid = ValidationError("The image is corrupted or not a valid image.", code="invalid_image")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            upload.seek(0)
            with Image.open(upload) as image:
                if image.format != file_type.pillow_format:
                    raise invalid
                width, height = image.size
                if width * height > settings.MEDIA_MAX_IMAGE_PIXELS:
                    raise ValidationError("The image has too many pixels.", code="too_large")
                image.verify()
            upload.seek(0)
            with Image.open(upload) as image:
                image.load()  # full decode: catches truncated data that verify() misses
    except ValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError("The image has too many pixels.", code="too_large") from exc
    except Exception as exc:  # Pillow raises many exception types for malformed input
        raise invalid from exc
    finally:
        upload.seek(0)
    return width, height


def inspect_upload(upload: UploadedFile) -> InspectedFile:
    file_type = sniff(_read_head(upload))
    if file_type is None:
        raise ValidationError(
            "Unsupported file type. Allowed: JPEG, PNG, WebP, PDF, MP4.", code="unsupported_type"
        )
    original_filename = safe_original_filename(upload.name)
    extension = os.path.splitext(original_filename)[1].lower()
    if extension and extension not in file_type.allowed_extensions:
        raise ValidationError(
            "The file extension does not match the file content.", code="extension_mismatch"
        )
    size = int(upload.size or 0)
    limit = (
        settings.MEDIA_MAX_VIDEO_UPLOAD_SIZE
        if file_type.kind == "VIDEO"
        else settings.MEDIA_MAX_UPLOAD_SIZE
    )
    if size <= 0:
        raise ValidationError("The file is empty.", code="empty")
    if size > limit:
        raise ValidationError(f"The file exceeds the {limit} byte limit.", code="too_large")
    width = height = None
    if file_type.pillow_format:
        width, height = _image_dimensions(upload, file_type)
    return InspectedFile(
        file_type=file_type,
        size=size,
        checksum_sha256=_checksum(upload),
        width=width,
        height=height,
        original_filename=original_filename,
    )
