# Media module (WR-21)

`apps/backend/apps/media` owns `MediaAsset` (metadata in PostgreSQL), the storage abstraction and upload validation. Blobs never enter the database: the table stores only `object_key` and metadata (enforced by a test that checks no `bytea` column exists).

## Model

| Field | Notes |
| --- | --- |
| `object_key` | Server-generated: `<kind>/<YYYY>/<MM>/<uuid4hex><ext>`. Never contains the client filename. |
| `original_filename` | Display only; basename, control characters stripped, max 255. |
| `mime_type`, `kind` | Decided by content sniffing (IMAGE / DOCUMENT / VIDEO). |
| `size`, `checksum_sha256`, `width`, `height` | Computed server-side. Dimensions only for images. |
| `alt_text`, `caption`, `source_note` | Plain text only (markup, `javascript:`/`vbscript:`/`data:text/html`, control chars rejected). |
| `visibility` | `PUBLIC` / `PRIVATE` (default `PRIVATE`). |
| `origin` | `STAFF_UPLOAD` / `CLIENT_PROVIDED` / `THIRD_PARTY`. |
| `authorization_status` | `PENDING` (default) / `APPROVED` / `REJECTED`. Photo publication rules are **DA DEFINIRE** in the client SOT, so public usage requires `APPROVED`. |
| `stored_publicly` | Internal: where the blob currently sits. |
| `uploaded_by` | FK to `settings.AUTH_USER_MODEL`, `SET_NULL`. |

## Storage abstraction

Two Django storages configured in `config/settings/base.py`:

- `media_public` — the only storage that ever produces anonymous URLs.
- `media_private` — never exposes URLs to anonymous users.

**Rule:** a blob lives in `media_public` exactly while its asset is `PUBLIC` **and** `APPROVED`. Uploads that are PRIVATE, PENDING or REJECTED land in `media_private`; approving, rejecting or changing visibility moves the blob. So an unapproved photo is never reachable through the public bucket, even by guessing a key.

### Consistency between row and blob (review F1/F2)

- `update_asset` locks the row (`SELECT ... FOR UPDATE`), applies the changes to the **locked** row and saves only the changed fields, so a stale in-memory copy can never overwrite a concurrent approval or visibility change. The API and the Django admin both go through it; permission checks run against the locked row.
- Blobs are never moved inside the caller's transaction. After commit, `transaction.on_commit` runs `reconcile_storage(pk)`, which locks the committed row, copies the blob into the storage matching `PUBLIC AND APPROVED` if it is missing, records `stored_publicly`, then deletes the copy in the other storage, all under the row lock. A rollback therefore changes nothing. `reconcile_storage` is idempotent and also repairs leftovers from a crash between copy and delete.
- New uploads always go to private storage first; an asset that is created already publicly usable is published by the same after-commit reconcile. A rolled-back upload can leave an orphan blob in **private** storage only (never exposed); a periodic sweep is a follow-up.
- Between commit and reconcile (milliseconds) the public URL is withheld (`public_url` requires `stored_publicly`), and an asset just made PRIVATE may still be reachable at its old public URL for that instant.

| Environment | `media_public` | `media_private` |
| --- | --- | --- |
| Local / dev | `FileSystemStorage` at `$MEDIA_ROOT/public` (default `apps/backend/mediafiles/`, git-ignored). Django does **not** serve it; `MEDIA_PUBLIC_BASE_URL` is a placeholder until a static host/CDN is set up. | `FileSystemStorage` at `$MEDIA_ROOT/private` |
| Tests | `InMemoryStorage` | `InMemoryStorage` |
| Production (`S3_STORAGE_ENABLED=true`, Cloudflare R2) | `S3Storage`, bucket `S3_PUBLIC_BUCKET_NAME` (fallback `S3_BUCKET_NAME`), prefix `S3_PUBLIC_LOCATION` (default `public`), unsigned URLs, optional `S3_PUBLIC_CUSTOM_DOMAIN` | `S3Storage`, bucket `S3_PRIVATE_BUCKET_NAME` (fallback `S3_BUCKET_NAME`), prefix `S3_PRIVATE_LOCATION` (default `private`), signed URLs valid `MEDIA_PRIVATE_URL_TTL` seconds (default 300) |

R2 needs **two buckets** (public bucket bound to a custom domain, private bucket with no public access): a bucket is either public or not, so settings **refuse to start** when the resolved public and private bucket names are equal (review F8). `S3_BUCKET_NAME` remains required by the base storage block. Requires the optional `storage` extra (`uv sync --extra storage`).

## Upload validation (`inspection.py`)

1. Type decided from magic bytes, never from the client `Content-Type` or extension. Allowlist: JPEG, PNG, WebP, PDF, MP4 (brands isom/iso2/iso4-6/mp41/mp42/avc1/M4V). SVG, HTML, archives, text and everything else are rejected. AVIF is not enabled (optional in the requirements; add a signature + Pillow check if needed).
2. If the filename has an extension it must match the sniffed type (`photo.pdf` containing PNG bytes is rejected).
3. Size limit: `MEDIA_MAX_UPLOAD_SIZE` (default 15 MiB) and `MEDIA_MAX_VIDEO_UPLOAD_SIZE` for MP4 (default 200 MiB). Note Django's `DATA_UPLOAD_MAX_MEMORY_SIZE` does not cap file parts; the reverse proxy should cap the body size too.
4. Images: Pillow (pinned `pillow>=12,<13`) must agree on the format, `verify()` and a full `load()` must succeed (truncated/corrupt files rejected), and the pixel count must stay under `MEDIA_MAX_IMAGE_PIXELS` (decompression bombs rejected).
5. PDFs and MP4s are only signature-checked; they are never rendered or served inline (downloads are attachments).
6. EXIF is **not** stripped (optional in the requirements). The original bytes are stored unchanged so the checksum matches the upload; stripping GPS metadata before public use is a follow-up if the client wants it.

The same inspection runs for API and Django admin uploads (admin `save_model` calls `services.create_asset`).

## API

| Method & path | operationId | Authorization |
| --- | --- | --- |
| `GET /api/v1/media/assets` | `listMediaAssets` | staff + `media.view_mediaasset` |
| `POST /api/v1/media/assets` (multipart) | `createMediaAsset` | staff + `media.add_mediaasset` |
| `GET /api/v1/media/assets/{id}` | `getMediaAsset` | staff + `media.view_mediaasset` |
| `PATCH /api/v1/media/assets/{id}` | `updateMediaAsset` | staff + `media.change_mediaasset`; changing `authorization_status` **or** making the asset `PUBLIC` also needs `media.approve_mediaasset` (API and admin); making a referenced asset PRIVATE answers 409 |
| `DELETE /api/v1/media/assets/{id}` | `deleteMediaAsset` | staff + `media.delete_mediaasset`; 409 while referenced (section content, page og image, SEO default og image) |
| `GET /api/v1/media/assets/{id}/download` | `downloadMediaAsset` | staff + `media.view_mediaasset`; blobs not in public storage also need `media.download_private_mediaasset` |
| `GET /api/v1/public/media-assets` | `listPublicMediaAssets` | anonymous; only `PUBLIC` + `APPROVED` |

Staff authorization uses `apps.accounts.permissions.StaffModelPermissions`. Download responses carry `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store` and a sandboxing CSP. With S3 the endpoint answers `302` to a short-lived signed URL for non-public blobs (`MEDIA_PRIVATE_PRESIGNED_DOWNLOADS`); the signature pins `ResponseContentDisposition: attachment; filename=...` and `ResponseContentType` to the sniffed type, so the bucket response is always a download. Otherwise the endpoint streams the file.

JSON bodies of media and CMS endpoints are parsed by `apps.media.parsers.SafeJSONParser`: absurdly nested documents become a 400 `ParseError` instead of a `RecursionError`/500.

### References from other modules

`media` cannot import `cms`. It declares the signal `apps.media.signals.collect_references`; `cms` connects a receiver (`apps/cms/receivers.py`) that lists section content, page og images and the SEO default og image using the asset. A non-empty answer blocks delete and PUBLIC→PRIVATE (`services.AssetInUse` → 409; the admin hides delete and shows a form error). To take a referenced photo down, **reject** it: the public API stops serving it immediately, and drafts keep working.

### Polyglot files and public headers (accepted residual risk)

A file can pass the signature and Pillow checks while also being valid in another format (e.g. JPEG+HTML polyglot). This is accepted: public objects are served with the stored, sniffed Content-Type (django-storages sets it from the server-generated key extension, which always matches the sniffed type), never as HTML. `X-Content-Type-Options: nosniff` cannot be stored as S3/R2 object metadata; configure it as a response-header rule on the public custom domain (Cloudflare Transform Rule) at deployment. Private downloads always send `nosniff` and `attachment`.

### Permission codenames (for RBAC role mapping)

`media.view_mediaasset`, `media.add_mediaasset`, `media.change_mediaasset`, `media.delete_mediaasset`, and custom: `media.approve_mediaasset` (approve/reject for public use), `media.download_private_mediaasset` (download non-public blobs).

## Known limits

- No audit events yet (`audit.record_event` is WR-18); approval changes should be audited once it exists.
- No antivirus scanning and no EXIF stripping.
- Moving a blob between storages is a copy + delete right after commit in the request thread; very large videos make approval slow. Acceptable for MVP volumes.
- The reference scan over section JSON is a Python loop over all sections: fine at MVP scale, replace with a reference table if pages grow to thousands.
- Bulk delete is disabled in the admin so blobs are always cleaned up.

## Recovery and hardening (second review pass)

- **Storage recovery:** the post-commit blob move never turns a committed write into a 500; a failure is logged as `media.reconcile_failed` (with `asset_id`). `python manage.py reconcile_media` re-applies the storage rule to every asset (idempotent, exits non-zero if any asset fails). Run it after every deploy and on a schedule in production, so a rejected/private blob can never linger in the public bucket.
- **ORM deletes:** a `pre_delete` receiver raises `ProtectedError` for any asset still referenced (section content, page or SEO og image), covering model and queryset deletes as well as API/admin paths.
- **JSON parsing:** `apps.core.parsers.SafeJSONParser` is the DRF default parser for every endpoint (including anonymous auth endpoints): pathological nesting is a 400, not a 500.
- **Accepted residual risk (N4):** a concurrent "make private/delete" may miss a section reference that is not yet committed; public rendering still hides non-public media and the section stays editable.
