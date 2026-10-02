"""MediaAsset service layer: every write path (API, admin, other modules) goes through here.

Storage rule: a blob is in the public storage only while its asset is PUBLIC *and*
APPROVED. Everything else (PRIVATE, PENDING, REJECTED) stays in the private storage, which
never produces a public URL. `stored_publicly` records where the blob currently is.
"""

import uuid
from typing import Any

from django.conf import settings
from django.core.files.storage import Storage, storages
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from .inspection import inspect_upload
from .models import MediaAsset

PUBLIC_STORAGE = "media_public"
PRIVATE_STORAGE = "media_private"
EDITABLE_FIELDS = frozenset(
    {"alt_text", "caption", "visibility", "origin", "source_note", "authorization_status"}
)


def public_storage() -> Storage:
    return storages[PUBLIC_STORAGE]


def private_storage() -> Storage:
    return storages[PRIVATE_STORAGE]


def storage_for(asset: MediaAsset) -> Storage:
    return public_storage() if asset.stored_publicly else private_storage()


def public_url(asset: MediaAsset) -> str | None:
    """URL usable by anonymous visitors, or None when the asset must not be public."""
    if not (asset.stored_publicly and asset.is_publicly_usable):
        return None
    return public_storage().url(asset.object_key)


def private_download_url(asset: MediaAsset) -> str | None:
    """Short-lived signed URL when the storage supports it (S3/R2), else None (stream)."""
    if not settings.MEDIA_PRIVATE_PRESIGNED_DOWNLOADS:
        return None
    return storage_for(asset).url(asset.object_key)


def _new_object_key(kind: str, extension: str) -> str:
    now = timezone.now()
    return f"{kind.lower()}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{extension}"


def create_asset(
    *,
    upload: UploadedFile,
    uploaded_by: Any,
    visibility: str = MediaAsset.Visibility.PRIVATE,
    alt_text: str = "",
    caption: str = "",
    origin: str = MediaAsset.Origin.STAFF_UPLOAD,
    source_note: str = "",
    authorization_status: str = MediaAsset.AuthorizationStatus.PENDING,
) -> MediaAsset:
    inspected = inspect_upload(upload)
    asset = MediaAsset(
        object_key=_new_object_key(inspected.file_type.kind, inspected.file_type.extension),
        original_filename=inspected.original_filename,
        mime_type=inspected.file_type.mime_type,
        kind=inspected.file_type.kind,
        size=inspected.size,
        checksum_sha256=inspected.checksum_sha256,
        width=inspected.width,
        height=inspected.height,
        alt_text=alt_text,
        caption=caption,
        visibility=visibility,
        origin=origin,
        source_note=source_note,
        authorization_status=authorization_status,
        uploaded_by=uploaded_by,
    )
    asset.stored_publicly = asset.is_publicly_usable
    asset.full_clean(exclude=["object_key"])
    storage = storage_for(asset)
    upload.seek(0)
    saved_key = storage.save(asset.object_key, upload)
    asset.object_key = saved_key
    try:
        asset.save()
    except Exception:
        storage.delete(saved_key)
        raise
    return asset


def _move_blob(asset: MediaAsset, *, to_public: bool) -> None:
    source = public_storage() if asset.stored_publicly else private_storage()
    target = public_storage() if to_public else private_storage()
    with source.open(asset.object_key, "rb") as fh:
        saved = target.save(asset.object_key, fh)
    if saved != asset.object_key:  # never expected: keys are random and unique
        target.delete(saved)
        raise RuntimeError(f"Object key collision while moving {asset.object_key}")
    source.delete(asset.object_key)
    asset.stored_publicly = to_public


@transaction.atomic
def update_asset(asset: MediaAsset, **changes: Any) -> MediaAsset:
    unknown = set(changes) - EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"Not editable: {sorted(unknown)}")
    for field, value in changes.items():
        setattr(asset, field, value)
    asset.full_clean()
    sync_storage_location(asset)
    asset.save()
    return asset


def sync_storage_location(asset: MediaAsset) -> None:
    """Move the blob so that it is public exactly when the asset is publicly usable."""
    should_be_public = asset.is_publicly_usable
    if asset.pk is not None and asset.stored_publicly != should_be_public:
        _move_blob(asset, to_public=should_be_public)


def delete_asset(asset: MediaAsset) -> None:
    storage = storage_for(asset)
    key = asset.object_key
    asset.delete()
    transaction.on_commit(lambda: storage.delete(key))
