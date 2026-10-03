"""Second-pass review of WR-19/21 (N1-N3): parser coverage, storage recovery, ORM deletes."""

import pytest
from cms_media_helpers import make_asset
from django.core.management import call_command
from django.db import transaction
from django.db.models import ProtectedError
from rest_framework.test import APIClient
from test_cms_hardening import _hero_page

from apps.media import services
from apps.media.models import MediaAsset

DEEP_JSON = '{"a":' + "[" * 50_000


@pytest.mark.django_db
def test_anonymous_deeply_nested_json_is_a_parse_error_everywhere():
    response = APIClient().post(
        "/api/v1/auth/session/login", DEEP_JSON, content_type="application/json"
    )
    assert response.status_code == 400


def _blob_location(asset: MediaAsset) -> tuple[bool, bool]:
    key = asset.object_key
    return services.public_storage().exists(key), services.private_storage().exists(key)


@pytest.mark.django_db(transaction=True)
def test_failed_post_commit_move_is_logged_not_raised(monkeypatch, caplog):
    asset = make_asset()  # PUBLIC + APPROVED, blob in public storage
    monkeypatch.setattr(services, "reconcile_storage", lambda pk: (_ for _ in ()).throw(OSError))
    with caplog.at_level("ERROR"), transaction.atomic():
        services.schedule_reconcile(asset.pk)
    assert "media.reconcile_failed" in caplog.text


@pytest.mark.django_db(transaction=True)
def test_reconcile_media_command_repairs_mismatched_assets():
    asset = make_asset()
    MediaAsset.objects.filter(pk=asset.pk).update(authorization_status="REJECTED")
    assert _blob_location(asset) == (True, False)
    call_command("reconcile_media")
    assert _blob_location(asset) == (False, True)
    assert MediaAsset.objects.get(pk=asset.pk).stored_publicly is False


@pytest.mark.django_db
def test_referenced_asset_cannot_be_deleted_through_the_orm():
    asset = make_asset()
    _hero_page(asset)
    with pytest.raises(ProtectedError), transaction.atomic():
        MediaAsset.objects.filter(pk=asset.pk).delete()
    with pytest.raises(ProtectedError), transaction.atomic():
        MediaAsset.objects.get(pk=asset.pk).delete()
    assert MediaAsset.objects.filter(pk=asset.pk).exists()
