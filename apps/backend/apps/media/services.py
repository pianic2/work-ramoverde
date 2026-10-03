"""MediaAsset service layer: every write path (API, admin, other modules) goes through here.

Storage rule: a blob is in the public storage only while its asset is PUBLIC *and*
APPROVED. Everything else (PRIVATE, PENDING, REJECTED) stays in the private storage, which
never produces a public URL. `stored_publicly` records where the blob currently is.
"""

import logging
import uuid
from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.core.files.storage import Storage, storages
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone
from django.utils.http import content_disposition_header

from .inspection import inspect_upload
from .models import MediaAsset
from .signals import collect_references

PUBLIC_STORAGE = "media_public"
PRIVATE_STORAGE = "media_private"
EDITABLE_FIELDS = frozenset(
    {"alt_text", "caption", "visibility", "origin", "source_note", "authorization_status"}
)


logger = logging.getLogger(__name__)


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
    """Short-lived signed URL for a non-public blob when the storage supports it (S3/R2).

    The signature also pins the response headers so the browser always downloads the file
    (attachment) with the sniffed Content-Type. Returns None when the file must be streamed.
    """
    if not settings.MEDIA_PRIVATE_PRESIGNED_DOWNLOADS or asset.stored_publicly:
        return None
    signer: Any = private_storage()  # S3Storage.url accepts response-header parameters
    url: str = signer.url(
        asset.object_key,
        parameters={
            "ResponseContentDisposition": content_disposition_header(
                as_attachment=True, filename=asset.original_filename
            ),
            "ResponseContentType": asset.mime_type,
        },
    )
    return url


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
    # New blobs always land in private storage; publishing happens after commit.
    asset.stored_publicly = False
    asset.full_clean(exclude=["object_key"])
    storage = private_storage()
    upload.seek(0)
    saved_key = storage.save(asset.object_key, upload)
    asset.object_key = saved_key
    try:
        asset.save()
    except Exception:
        storage.delete(saved_key)
        raise
    if asset.is_publicly_usable:
        schedule_reconcile(asset.pk)
    return asset


class AssetInUse(Exception):
    """The asset is referenced by published-facing content (see `signals.collect_references`)."""

    def __init__(self, references: list[str]) -> None:
        self.references = references
        super().__init__("This media asset is still used by: " + "; ".join(references) + ".")


def asset_references(asset_id: int) -> list[str]:
    """Human-readable places that reference the asset, collected from other modules."""
    found: list[str] = []
    for _receiver, response in collect_references.send(sender=MediaAsset, asset_id=asset_id):
        found.extend(response or [])
    return found


def _ensure_not_referenced(asset_id: int) -> None:
    references = asset_references(asset_id)
    if references:
        raise AssetInUse(references)


def schedule_reconcile(asset_id: int) -> None:
    """Place the blob after the current transaction commits; nothing happens on rollback.

    The write is already committed when this runs, so a storage failure is logged (not
    raised as a 500) and repaired later by `manage.py reconcile_media`.
    """

    def run() -> None:
        try:
            reconcile_storage(asset_id)
        except Exception:
            logger.exception("media.reconcile_failed", extra={"asset_id": asset_id})

    transaction.on_commit(run)


def reconcile_storage(asset_id: int) -> None:
    """Make the blob live in exactly the storage that matches the committed row.

    Idempotent and safe to re-run: copies the blob into the right storage if missing,
    records `stored_publicly`, then removes any copy left in the other storage.
    """
    with transaction.atomic():
        try:
            asset = MediaAsset.objects.select_for_update().get(pk=asset_id)
        except MediaAsset.DoesNotExist:
            return
        key = asset.object_key
        should_be_public = asset.is_publicly_usable
        target = public_storage() if should_be_public else private_storage()
        other = private_storage() if should_be_public else public_storage()
        if not target.exists(key):
            if not other.exists(key):
                raise FileNotFoundError(f"Blob {key} is missing from both storages")
            with other.open(key, "rb") as fh:
                saved = target.save(key, fh)
            if saved != key:  # never expected: keys are random and unique
                target.delete(saved)
                raise RuntimeError(f"Object key collision while moving {key}")
        if asset.stored_publicly != should_be_public:
            asset.stored_publicly = should_be_public
            asset.save(update_fields=["stored_publicly", "updated_at"])
        # Still under the row lock, so concurrent reconciles cannot delete each other's copy;
        # the blob already exists in `target`, so dropping the stale copy is always safe.
        if other.exists(key):
            other.delete(key)


APPROVE_PERMISSION = "media.approve_mediaasset"


def required_permissions(current: MediaAsset, changes: dict[str, Any]) -> set[str]:
    """Extra permissions needed for `changes` on top of `media.change_mediaasset`.

    Approving/rejecting and turning an asset PUBLIC both decide what reaches the public
    site, so both need approval rights.
    """
    needed: set[str] = set()
    status = changes.get("authorization_status", current.authorization_status)
    if status != current.authorization_status:
        needed.add(APPROVE_PERMISSION)
    visibility = changes.get("visibility", current.visibility)
    if visibility == MediaAsset.Visibility.PUBLIC and current.visibility != visibility:
        needed.add(APPROVE_PERMISSION)
    return needed


def update_asset(
    asset: MediaAsset,
    *,
    authorize: Callable[[set[str]], None] | None = None,
    **changes: Any,
) -> MediaAsset:
    """Apply metadata changes to the locked row (never a stale in-memory copy).

    `authorize` receives the extra permissions required against the locked row and must
    raise to refuse. The blob is moved only after commit (`schedule_reconcile`).
    """
    unknown = set(changes) - EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"Not editable: {sorted(unknown)}")
    with transaction.atomic():
        locked = MediaAsset.objects.select_for_update().get(pk=asset.pk)
        if authorize is not None:
            authorize(required_permissions(locked, changes))
        was_public = locked.visibility == MediaAsset.Visibility.PUBLIC
        for field, value in changes.items():
            setattr(locked, field, value)
        locked.full_clean()
        if was_public and locked.visibility == MediaAsset.Visibility.PRIVATE:
            _ensure_not_referenced(locked.pk)
        locked.save(update_fields=[*changes, "updated_at"])
        if locked.stored_publicly != locked.is_publicly_usable:
            schedule_reconcile(locked.pk)
    locked.refresh_from_db()  # picks up `stored_publicly` once the move has run
    return locked


def delete_asset(asset: MediaAsset) -> None:
    with transaction.atomic():
        locked = MediaAsset.objects.select_for_update().get(pk=asset.pk)
        _ensure_not_referenced(locked.pk)
        key = locked.object_key
        locked.delete()

        def remove_blobs() -> None:
            for storage in (public_storage(), private_storage()):
                if storage.exists(key):
                    storage.delete(key)

        transaction.on_commit(remove_blobs)
