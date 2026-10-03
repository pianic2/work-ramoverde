"""Regression tests for the independent review of WR-21 (findings F1, F2, F4-F6, F8)."""

import os
import subprocess
import sys
import threading

import pytest
from auth_helpers import force_staff_login, mfa_session_for
from cms_media_helpers import make_asset, staff_user
from django.db import close_old_connections, transaction
from rest_framework.test import APIClient

from apps.media import services
from apps.media.models import MediaAsset

ASSETS = "/api/v1/media/assets"


def _client(user=None) -> APIClient:
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user, token=mfa_session_for(user))
    return client


def _blob_location(asset: MediaAsset) -> tuple[bool, bool]:
    key = asset.object_key
    return services.public_storage().exists(key), services.private_storage().exists(key)


# --- F1: stale copies must not lose concurrent changes or desync the blob --------------------


@pytest.mark.django_db(transaction=True)
def test_stale_update_does_not_lose_approval_or_leave_blob_public():
    asset = make_asset(authorization_status="PENDING")  # PUBLIC + PENDING -> private storage
    first = MediaAsset.objects.get(pk=asset.pk)
    stale = MediaAsset.objects.get(pk=asset.pk)
    services.update_asset(first, authorization_status="APPROVED")
    services.update_asset(stale, visibility="PRIVATE")

    db = MediaAsset.objects.get(pk=asset.pk)
    assert db.authorization_status == "APPROVED"  # not overwritten by the stale copy
    assert db.visibility == "PRIVATE"
    assert db.stored_publicly is False
    assert _blob_location(db) == (False, True)


@pytest.mark.django_db(transaction=True)
def test_concurrent_updates_serialize_on_the_row_lock():
    asset = make_asset(authorization_status="PENDING")
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def run(**changes):
        try:
            copy = MediaAsset.objects.get(pk=asset.pk)
            barrier.wait()
            services.update_asset(copy, **changes)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            close_old_connections()

    threads = [
        threading.Thread(target=run, kwargs={"authorization_status": "APPROVED"}),
        threading.Thread(target=run, kwargs={"visibility": "PRIVATE"}),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    db = MediaAsset.objects.get(pk=asset.pk)
    assert (db.visibility, db.authorization_status) == ("PRIVATE", "APPROVED")
    assert db.stored_publicly is False
    assert _blob_location(db) == (False, True)


# --- F2: a rolled back approval leaves no public blob ----------------------------------------


@pytest.mark.django_db(transaction=True)
def test_rollback_after_approve_leaves_no_public_blob():
    asset = make_asset(authorization_status="PENDING")
    with pytest.raises(RuntimeError), transaction.atomic():
        services.update_asset(asset, authorization_status="APPROVED")
        raise RuntimeError("later failure in the same transaction")
    db = MediaAsset.objects.get(pk=asset.pk)
    assert (db.authorization_status, db.stored_publicly) == ("PENDING", False)
    assert _blob_location(db) == (False, True)


@pytest.mark.django_db(transaction=True)
def test_reconcile_repairs_a_blob_left_in_the_wrong_storage():
    asset = make_asset(visibility="PRIVATE")
    with services.private_storage().open(asset.object_key, "rb") as fh:
        services.public_storage().save(asset.object_key, fh)  # simulated crash leftover
    services.reconcile_storage(asset.pk)
    assert _blob_location(asset) == (False, True)


# --- F4: deep JSON is a 400, not a 500 ---------------------------------------------------------


@pytest.mark.django_db
def test_deeply_nested_json_body_is_a_parse_error():
    user = staff_user("deep@example.com", "media.view_mediaasset", "media.change_mediaasset")
    asset = make_asset()
    body = '{"alt_text": ' + "[" * 50000 + "]" * 50000 + "}"
    client = APIClient(raise_request_exception=False)
    client.force_authenticate(user=user, token=mfa_session_for(user))
    response = client.generic(
        "PATCH", f"{ASSETS}/{asset.pk}", body, content_type="application/json"
    )
    assert response.status_code == 400


# --- F5: presigned private download forces attachment -----------------------------------------


@pytest.mark.django_db
def test_presigned_download_forces_attachment_and_content_type(settings, monkeypatch):
    settings.MEDIA_PRIVATE_PRESIGNED_DOWNLOADS = True
    asset = make_asset(visibility="PRIVATE")
    captured: dict = {}

    def fake_url(name, parameters=None, expire=None, http_method=None):
        captured.update(name=name, parameters=parameters)
        return f"https://bucket.example/{name}?sig=1"

    monkeypatch.setattr(services.private_storage(), "url", fake_url)
    user = staff_user(
        "s3@example.com", "media.view_mediaasset", "media.download_private_mediaasset"
    )
    response = _client(user).get(f"{ASSETS}/{asset.pk}/download")
    assert response.status_code == 302
    assert captured["parameters"]["ResponseContentType"] == "image/png"
    assert captured["parameters"]["ResponseContentDisposition"].startswith("attachment;")
    assert asset.original_filename in captured["parameters"]["ResponseContentDisposition"]


# --- F6: making an asset PUBLIC needs approval rights ----------------------------------------


@pytest.mark.django_db
def test_visibility_to_public_requires_approve_permission():
    asset = make_asset(visibility="PRIVATE", authorization_status="APPROVED")
    editor = staff_user("ed@example.com", "media.view_mediaasset", "media.change_mediaasset")
    response = _client(editor).patch(
        f"{ASSETS}/{asset.pk}", {"visibility": "PUBLIC"}, format="json"
    )
    assert response.status_code == 403
    asset.refresh_from_db()
    assert asset.visibility == "PRIVATE"
    assert _blob_location(asset) == (False, True)


@pytest.mark.django_db
def test_admin_visibility_to_public_requires_approve_permission(client):
    asset = make_asset(visibility="PRIVATE", authorization_status="APPROVED")
    editor = staff_user("aded@example.com", "media.view_mediaasset", "media.change_mediaasset")
    force_staff_login(client, editor)
    data = {
        "alt_text": "x",
        "caption": "",
        "visibility": "PUBLIC",
        "origin": "STAFF_UPLOAD",
        "source_note": "",
    }
    response = client.post(f"/django-admin/media/mediaasset/{asset.pk}/change/", data)
    # Django admin is limited to technical superusers (WR-13): staff editors are refused.
    assert response.status_code == 302
    asset.refresh_from_db()
    assert asset.visibility == "PRIVATE"


@pytest.mark.django_db(transaction=True)
def test_admin_change_uses_locked_service_update(client):
    asset = make_asset(visibility="PUBLIC", authorization_status="PENDING")
    approver = staff_user(
        "adap@example.com",
        "media.view_mediaasset",
        "media.change_mediaasset",
        "media.approve_mediaasset",
    )
    approver.is_superuser = True  # Django admin is superuser-only (WR-13)
    approver.save(update_fields=["is_superuser"])
    force_staff_login(client, approver)
    data = {
        "alt_text": "Nuovo",
        "caption": "",
        "visibility": "PUBLIC",
        "origin": "STAFF_UPLOAD",
        "source_note": "",
        "authorization_status": "APPROVED",
    }
    response = client.post(f"/django-admin/media/mediaasset/{asset.pk}/change/", data)
    assert response.status_code == 302
    db = MediaAsset.objects.get(pk=asset.pk)
    assert (db.authorization_status, db.alt_text, db.stored_publicly) == ("APPROVED", "Nuovo", True)
    assert _blob_location(db) == (True, False)


# --- F8: one bucket for public and private is refused ------------------------------------------


def test_s3_refuses_same_bucket_for_public_and_private():
    env = os.environ.copy()
    env.update(
        DJANGO_SETTINGS_MODULE="config.settings.production",
        DATABASE_URL="postgresql://app:app@localhost:5432/app",
        DJANGO_SECRET_KEY="ci-only-not-a-secret-ci-only-not-a-secret-ci-only-not-a-secret",
        DJANGO_ALLOWED_HOSTS="example.com",
        DJANGO_CORS_ALLOWED_ORIGINS="https://web.example.com",
        DJANGO_CSRF_TRUSTED_ORIGINS="https://web.example.com",
        S3_STORAGE_ENABLED="true",
        S3_BUCKET_NAME="shared",
    )
    env.pop("S3_PUBLIC_BUCKET_NAME", None)
    env.pop("S3_PRIVATE_BUCKET_NAME", None)
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import django; django.setup()"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "S3_PUBLIC_BUCKET_NAME and S3_PRIVATE_BUCKET_NAME must differ" in result.stderr
