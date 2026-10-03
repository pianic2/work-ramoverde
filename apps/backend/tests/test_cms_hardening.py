"""Regression tests for the independent review of WR-19/WR-20 (findings F3, F4, F7)."""

import pytest
from auth_helpers import force_staff_login, mfa_session_for
from cms_media_helpers import make_asset, run_on_commit, staff_user
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.cms.models import Page, PageSection, SEOSettings
from apps.cms.sections import url_error, validate_section
from apps.cms.services import create_section
from apps.media import services as media_services
from apps.media.models import MediaAsset

PAGES = "/api/v1/cms/pages"
ASSETS = "/api/v1/media/assets"
EDITOR = (
    "cms.view_page",
    "cms.add_page",
    "cms.change_page",
    "cms.view_pagesection",
    "cms.add_pagesection",
    "cms.change_pagesection",
    "cms.delete_pagesection",
)
MEDIA_ADMIN = (
    "media.view_mediaasset",
    "media.change_mediaasset",
    "media.delete_mediaasset",
    "media.approve_mediaasset",
)


def _client(user=None) -> APIClient:
    client = APIClient(raise_request_exception=False)
    if user is not None:
        client.force_authenticate(user=user, token=mfa_session_for(user))
    return client


def _hero_page(asset: MediaAsset) -> tuple[Page, PageSection]:
    page = Page.objects.create(title="Home", slug="home")
    section = create_section(
        page, type="hero", variant="minimal", content={"heading": "Ciao", "image": asset.pk}
    )
    return page, section


def _reject(asset: MediaAsset) -> None:
    with run_on_commit():
        media_services.update_asset(asset, authorization_status="REJECTED")


# --- F3: existing references never block take-down or unrelated edits ------------------------


@pytest.mark.django_db
def test_section_with_rejected_media_can_still_be_disabled_and_edited():
    asset = make_asset(authorization_status="PENDING")
    page, section = _hero_page(asset)
    _reject(asset)
    client = _client(staff_user("e@example.com", *EDITOR))
    url = f"{PAGES}/{page.pk}/sections/{section.pk}"
    assert client.patch(url, {"enabled": False}, format="json").status_code == 200
    edited = client.patch(url, {"content": {"heading": "Nuovo", "image": asset.pk}}, format="json")
    assert edited.status_code == 200, edited.content


@pytest.mark.django_db
def test_newly_added_media_reference_must_still_be_public():
    good = make_asset()
    page, section = _hero_page(good)
    private = make_asset(visibility="PRIVATE")
    response = _client(staff_user("e@example.com", *EDITOR)).patch(
        f"{PAGES}/{page.pk}/sections/{section.pk}",
        {"content": {"heading": "Ciao", "image": private.pk}},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_page_with_rejected_og_image_can_still_be_edited():
    asset = make_asset(authorization_status="PENDING")
    page = Page.objects.create(title="Home", slug="home", og_image=asset)
    _reject(asset)
    response = _client(staff_user("e@example.com", *EDITOR)).patch(
        f"{PAGES}/{page.pk}", {"title": "Casa"}, format="json"
    )
    assert response.status_code == 200, response.content


@pytest.mark.django_db
def test_media_referenced_by_section_cannot_be_deleted_or_made_private():
    asset = make_asset()
    _hero_page(asset)
    client = _client(staff_user("m@example.com", *MEDIA_ADMIN))
    deleted = client.delete(f"{ASSETS}/{asset.pk}")
    assert deleted.status_code == 409
    assert "page 'home' section" in deleted.json()["error"]["details"]["detail"]
    private = client.patch(f"{ASSETS}/{asset.pk}", {"visibility": "PRIVATE"}, format="json")
    assert private.status_code == 409
    assert MediaAsset.objects.get(pk=asset.pk).visibility == "PUBLIC"


@pytest.mark.django_db
def test_media_used_as_og_image_cannot_be_made_private():
    page_image, seo_image = make_asset(), make_asset()
    Page.objects.create(title="Home", slug="home", og_image=page_image)
    seo = SEOSettings.load()
    seo.default_og_image = seo_image
    seo.save()
    client = _client(staff_user("m@example.com", *MEDIA_ADMIN))
    for asset in (page_image, seo_image):
        response = client.patch(f"{ASSETS}/{asset.pk}", {"visibility": "PRIVATE"}, format="json")
        assert response.status_code == 409


@pytest.mark.django_db
def test_unreferenced_media_can_be_made_private():
    asset = make_asset()
    client = _client(staff_user("m@example.com", *MEDIA_ADMIN))
    response = client.patch(f"{ASSETS}/{asset.pk}", {"visibility": "PRIVATE"}, format="json")
    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_hides_delete_for_referenced_media(client):
    from django.contrib.auth import get_user_model

    asset = make_asset()
    _hero_page(asset)
    admin = get_user_model().objects.create_superuser(email="root@example.com", password="x" * 16)
    force_staff_login(client, admin)
    assert client.get(f"/django-admin/media/mediaasset/{asset.pk}/delete/").status_code == 403


# --- F4: hostile JSON -----------------------------------------------------------------------


@pytest.mark.django_db
def test_deeply_nested_section_json_is_a_parse_error():
    page = Page.objects.create(title="Home", slug="home")
    body = '{"type":"hero","variant":"minimal","content":' + "[" * 50000 + "]" * 50000 + "}"
    response = _client(staff_user("e@example.com", *EDITOR)).generic(
        "POST", f"{PAGES}/{page.pk}/sections", body, content_type="application/json"
    )
    assert response.status_code == 400


def test_oversized_list_is_rejected_without_validating_every_item():
    items = [{"value": "<b>x</b>", "label": "y"}] * 5000
    with pytest.raises(ValidationError) as exc:
        validate_section("stats", 1, "row", {"items": items})
    messages = exc.value.message_dict["content"]
    assert any("Between 1 and 8 items" in m for m in messages)
    assert len(messages) == 1  # items beyond the limit are not walked


@pytest.mark.parametrize(
    "url",
    [
        "mailto:@",
        "mailto:x@",
        "tel:+",
        "https://user:pass@evil.example.com",
        "/​/evil.example.com",
        "‮https://x.example.com",
        "/%2F/evil.example.com",
    ],
)
def test_url_policy_rejects_review_edge_cases(url):
    assert url_error(url) is not None


# --- F7: publication checks also apply on create --------------------------------------------


@pytest.mark.django_db
def test_create_published_page_with_pending_og_image_is_rejected():
    asset = make_asset(authorization_status="PENDING")
    publisher = staff_user("p@example.com", *EDITOR, "cms.publish_page")
    response = _client(publisher).post(
        PAGES,
        {"title": "X", "slug": "x", "status": "PUBLISHED", "og_image": asset.pk},
        format="json",
    )
    assert response.status_code == 400
    assert not Page.objects.filter(slug="x").exists()
