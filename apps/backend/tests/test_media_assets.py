import hashlib

import pytest
from auth_helpers import force_staff_login, mfa_session_for
from cms_media_helpers import PDF_BYTES, image_bytes, make_asset, png_upload, staff_user
from django.core.files.storage import storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from rest_framework.test import APIClient

from apps.media.models import MediaAsset

ASSETS = "/api/v1/media/assets"
UPLOADER_PERMS = ("media.add_mediaasset", "media.view_mediaasset")


def _client(user=None) -> APIClient:
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user, token=mfa_session_for(user))
    return client


def _upload(client: APIClient, upload, **fields):
    return client.post(ASSETS, {"file": upload, **fields}, format="multipart")


@pytest.mark.django_db
def test_staff_upload_stores_blob_in_storage_and_metadata_in_db():
    user = staff_user("up@example.com", *UPLOADER_PERMS)
    payload = image_bytes("PNG", (40, 20))
    response = _upload(
        _client(user),
        SimpleUploadedFile("../../etc/My Photo.png", payload, content_type="image/png"),
        alt_text="Cantiere",
        visibility="PUBLIC",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    asset = MediaAsset.objects.get(pk=body["id"])
    assert asset.mime_type == "image/png"
    assert asset.kind == "IMAGE"
    assert (asset.width, asset.height) == (40, 20)
    assert asset.size == len(payload)
    assert asset.checksum_sha256 == hashlib.sha256(payload).hexdigest()
    assert asset.original_filename == "My Photo.png"
    assert asset.uploaded_by == user
    assert asset.authorization_status == "PENDING"
    # Random key, no user-controlled filename in the object path.
    assert "Photo" not in asset.object_key and ".." not in asset.object_key
    assert asset.object_key.endswith(".png")
    # PUBLIC but still PENDING: the blob waits in private storage, no public URL yet.
    assert body["public_url"] is None
    storage = storages["media_private"]
    assert storage.exists(asset.object_key)
    with storage.open(asset.object_key) as fh:
        assert fh.read() == payload
    assert not storages["media_public"].exists(asset.object_key)


@pytest.mark.django_db
def test_no_blob_column_in_media_table():
    with connection.cursor() as cursor:
        columns = connection.introspection.get_table_description(cursor, MediaAsset._meta.db_table)
    binary_types = {"bytea"}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT data_type FROM information_schema.columns WHERE table_name = %s",
            [MediaAsset._meta.db_table],
        )
        types = {row[0] for row in cursor.fetchall()}
    assert columns
    assert not types & binary_types


@pytest.mark.django_db
def test_pdf_upload_private_goes_to_private_storage():
    user = staff_user("pdf@example.com", *UPLOADER_PERMS)
    response = _upload(
        _client(user),
        SimpleUploadedFile("contratto.pdf", PDF_BYTES, content_type="application/pdf"),
        visibility="PRIVATE",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["mime_type"] == "application/pdf"
    assert body["width"] is None
    assert body["public_url"] is None
    asset = MediaAsset.objects.get(pk=body["id"])
    assert storages["media_private"].exists(asset.object_key)
    assert not storages["media_public"].exists(asset.object_key)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "content", "content_type"),
    [
        ("evil.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>', "image/svg+xml"),
        ("page.html", b"<!doctype html><script>alert(1)</script>", "text/html"),
        ("notes.txt", b"just text", "text/plain"),
        ("archive.zip", b"PK\x03\x04rest", "application/zip"),
    ],
)
def test_disallowed_types_are_rejected(name, content, content_type):
    user = staff_user("bad@example.com", *UPLOADER_PERMS)
    response = _upload(_client(user), SimpleUploadedFile(name, content, content_type=content_type))
    assert response.status_code == 400
    assert MediaAsset.objects.count() == 0


@pytest.mark.django_db
def test_spoofed_extension_and_content_type_are_rejected():
    user = staff_user("spoof@example.com", *UPLOADER_PERMS)
    html_as_jpeg = SimpleUploadedFile(
        "photo.jpg", b"<html><script>alert(1)</script></html>", content_type="image/jpeg"
    )
    assert _upload(_client(user), html_as_jpeg).status_code == 400
    # Real PNG bytes behind a .pdf name: extension does not match the sniffed type.
    png_as_pdf = SimpleUploadedFile("doc.pdf", image_bytes("PNG"), content_type="application/pdf")
    assert _upload(_client(user), png_as_pdf).status_code == 400
    # Truncated image with a valid PNG signature fails Pillow verification.
    broken = SimpleUploadedFile("x.png", image_bytes("PNG")[:40], content_type="image/png")
    assert _upload(_client(user), broken).status_code == 400
    assert MediaAsset.objects.count() == 0


@pytest.mark.django_db
def test_oversize_upload_is_rejected(settings):
    settings.MEDIA_MAX_UPLOAD_SIZE = 10
    user = staff_user("big@example.com", *UPLOADER_PERMS)
    response = _upload(_client(user), png_upload())
    assert response.status_code == 400
    assert MediaAsset.objects.count() == 0


@pytest.mark.django_db
def test_upload_requires_staff_with_add_permission():
    assert _upload(_client(), png_upload()).status_code == 401
    viewer = staff_user("viewer@example.com", "media.view_mediaasset")
    assert _upload(_client(viewer), png_upload()).status_code == 403


@pytest.mark.django_db
def test_markup_in_alt_text_is_rejected():
    user = staff_user("alt@example.com", *UPLOADER_PERMS)
    response = _upload(_client(user), png_upload(), alt_text="<img src=x onerror=alert(1)>")
    assert response.status_code == 400


@pytest.mark.django_db
def test_private_download_denied_to_anonymous_and_staff_without_permission():
    asset = make_asset(visibility="PRIVATE")
    url = f"{ASSETS}/{asset.pk}/download"
    assert _client().get(url).status_code == 401
    no_perm = staff_user("noperm@example.com")
    assert _client(no_perm).get(url).status_code == 403
    view_only = staff_user("viewonly@example.com", "media.view_mediaasset")
    assert _client(view_only).get(url).status_code == 403


@pytest.mark.django_db
def test_private_download_streams_attachment_with_nosniff():
    asset = make_asset(visibility="PRIVATE")
    user = staff_user(
        "dl@example.com", "media.view_mediaasset", "media.download_private_mediaasset"
    )
    response = _client(user).get(f"{ASSETS}/{asset.pk}/download")
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Content-Type"] == "image/png"
    assert b"".join(response.streaming_content).startswith(b"\x89PNG")


@pytest.mark.django_db
def test_private_download_redirects_to_presigned_url_when_enabled(settings, monkeypatch):
    settings.MEDIA_PRIVATE_PRESIGNED_DOWNLOADS = True
    asset = make_asset(visibility="PRIVATE")
    storage = storages["media_private"]
    monkeypatch.setattr(
        storage, "url", lambda key, **kw: f"https://bucket.example/{key}?X-Amz-Expires=300"
    )
    user = staff_user(
        "s3@example.com", "media.view_mediaasset", "media.download_private_mediaasset"
    )
    response = _client(user).get(f"{ASSETS}/{asset.pk}/download")
    assert response.status_code == 302
    assert response["Location"].startswith("https://bucket.example/")
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_private_asset_has_no_public_url_and_is_not_in_public_listing():
    make_asset(visibility="PRIVATE")
    pending = make_asset(visibility="PUBLIC", authorization_status="PENDING")
    rejected = make_asset(visibility="PUBLIC", authorization_status="REJECTED")
    approved = make_asset(visibility="PUBLIC", authorization_status="APPROVED")
    response = _client().get("/api/v1/public/media-assets")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["results"]]
    assert ids == [approved.pk]
    assert pending.pk not in ids and rejected.pk not in ids
    item = response.json()["results"][0]
    assert item["url"].startswith("/media/public/")
    assert set(item) == {"id", "url", "mime_type", "width", "height", "alt_text", "caption"}


@pytest.mark.django_db
def test_staff_list_requires_view_permission_and_shows_all():
    make_asset(visibility="PRIVATE")
    make_asset(visibility="PUBLIC")
    assert _client().get(ASSETS).status_code == 401
    assert _client(staff_user("np@example.com")).get(ASSETS).status_code == 403
    viewer = staff_user("v@example.com", "media.view_mediaasset")
    response = _client(viewer).get(ASSETS)
    assert response.status_code == 200
    assert response.json()["count"] == 2


@pytest.mark.django_db(transaction=True)
def test_approval_requires_approve_permission():
    asset = make_asset(visibility="PUBLIC", authorization_status="PENDING")
    editor = staff_user("ed@example.com", "media.view_mediaasset", "media.change_mediaasset")
    url = f"{ASSETS}/{asset.pk}"
    assert _client(editor).patch(url, {"alt_text": "Nuovo"}, format="json").status_code == 200
    denied = _client(editor).patch(url, {"authorization_status": "APPROVED"}, format="json")
    assert denied.status_code == 403
    approver = staff_user(
        "ap@example.com",
        "media.view_mediaasset",
        "media.change_mediaasset",
        "media.approve_mediaasset",
    )
    ok = _client(approver).patch(url, {"authorization_status": "APPROVED"}, format="json")
    assert ok.status_code == 200
    assert ok.json()["public_url"].startswith("/media/public/")
    asset.refresh_from_db()
    assert asset.authorization_status == "APPROVED"
    assert asset.alt_text == "Nuovo"
    # Approval publishes the blob: it moves from private to public storage.
    assert storages["media_public"].exists(asset.object_key)
    assert not storages["media_private"].exists(asset.object_key)


@pytest.mark.django_db(transaction=True)
def test_visibility_change_moves_blob_between_storages():
    asset = make_asset(visibility="PUBLIC")
    assert storages["media_public"].exists(asset.object_key)
    user = staff_user("mv@example.com", "media.view_mediaasset", "media.change_mediaasset")
    response = _client(user).patch(f"{ASSETS}/{asset.pk}", {"visibility": "PRIVATE"}, format="json")
    assert response.status_code == 200
    assert response.json()["public_url"] is None
    assert storages["media_private"].exists(asset.object_key)
    assert not storages["media_public"].exists(asset.object_key)


@pytest.mark.django_db(transaction=True)
def test_delete_removes_metadata_and_blob():
    asset = make_asset(visibility="PUBLIC")
    user = staff_user("del@example.com", "media.view_mediaasset", "media.delete_mediaasset")
    response = _client(user).delete(f"{ASSETS}/{asset.pk}")
    assert response.status_code == 204
    assert not MediaAsset.objects.filter(pk=asset.pk).exists()
    assert not storages["media_public"].exists(asset.object_key)


@pytest.mark.parametrize("fmt", ["JPEG", "WEBP"])
def test_inspection_accepts_jpeg_and_webp(fmt):
    from apps.media.inspection import inspect_upload

    upload = SimpleUploadedFile(f"x.{fmt.lower()}", image_bytes(fmt, (8, 6)))
    inspected = inspect_upload(upload)
    assert inspected.file_type.pillow_format == fmt
    assert (inspected.width, inspected.height) == (8, 6)


def test_video_uses_separate_size_limit(settings):
    from django.core.exceptions import ValidationError

    from apps.media.inspection import inspect_upload

    mp4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00" * 64
    settings.MEDIA_MAX_UPLOAD_SIZE = 10
    settings.MEDIA_MAX_VIDEO_UPLOAD_SIZE = 1000
    assert inspect_upload(SimpleUploadedFile("v.mp4", mp4)).file_type.kind == "VIDEO"
    settings.MEDIA_MAX_VIDEO_UPLOAD_SIZE = 10
    with pytest.raises(ValidationError):
        inspect_upload(SimpleUploadedFile("v.mp4", mp4))


def test_too_many_pixels_rejected(settings):
    from django.core.exceptions import ValidationError

    from apps.media.inspection import inspect_upload

    settings.MEDIA_MAX_IMAGE_PIXELS = 100
    with pytest.raises(ValidationError):
        inspect_upload(SimpleUploadedFile("big.png", image_bytes("PNG", (20, 20))))


@pytest.mark.parametrize(
    "value",
    [
        "<script>alert(1)</script>",
        "<b>bold</b>",
        "</p>",
        "<!-- x -->",
        "javascript:alert(1)",
        "JaVaScRiPt :alert(1)",
        "data:text/html;base64,xx",
        "line\nbreak",
        "nul\x00byte",
    ],
)
def test_plain_text_rejects_markup_and_scripts(value):
    from apps.media.validators import plain_text_error

    assert plain_text_error(value) is not None


def test_plain_text_accepts_ordinary_text():
    from apps.media.validators import plain_text_error

    assert plain_text_error("Lavori 3 < 5 & 10 > 2 — 100% verde") is None
    assert plain_text_error("Riga uno\nRiga due", multiline=True) is None


@pytest.mark.django_db
def test_admin_upload_rejects_spoofed_file_and_accepts_valid_image(client):
    from django.contrib.auth import get_user_model

    admin = get_user_model().objects.create_superuser(email="root@example.com", password="x" * 16)
    force_staff_login(client, admin)
    url = "/django-admin/media/mediaasset/add/"
    base = {"alt_text": "", "caption": "", "visibility": "PUBLIC", "origin": "STAFF_UPLOAD"}
    bad = SimpleUploadedFile("photo.jpg", b"<html></html>", content_type="image/jpeg")
    response = client.post(url, {**base, "source_note": "", "file": bad})
    assert response.status_code == 200  # form re-rendered with errors
    assert MediaAsset.objects.count() == 0
    response = client.post(url, {**base, "source_note": "", "file": png_upload()})
    assert response.status_code == 302
    asset = MediaAsset.objects.get()
    assert asset.uploaded_by == admin
    assert storages["media_private"].exists(asset.object_key)
