import pytest
from auth_helpers import force_staff_login, mfa_session_for
from cms_media_helpers import make_asset, run_on_commit, staff_user
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.cms.models import Page, PageSection

PAGES = "/api/v1/cms/pages"
EDITOR_PERMS = (
    "cms.view_page",
    "cms.add_page",
    "cms.change_page",
    "cms.delete_page",
    "cms.view_pagesection",
    "cms.add_pagesection",
    "cms.change_pagesection",
    "cms.delete_pagesection",
)
CTA = {"heading": "Richiedi un preventivo", "cta": {"label": "Contattaci", "href": "/contatti"}}


def _client(user=None) -> APIClient:
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user, token=mfa_session_for(user))
    return client


def _editor(email="editor@example.com", *extra):
    return staff_user(email, *EDITOR_PERMS, *extra)


def _page(slug="home", status=Page.Status.DRAFT, **kwargs) -> Page:
    return Page.objects.create(title=slug.title(), slug=slug, status=status, **kwargs)


def _section(page, section_type="cta", content=None, **kwargs) -> PageSection:
    from apps.cms.services import create_section

    return create_section(
        page,
        type=section_type,
        variant=kwargs.pop("variant", "banner"),
        content=content if content is not None else CTA,
        **kwargs,
    )


# --- staff API -------------------------------------------------------------------------


@pytest.mark.django_db
def test_staff_page_crud():
    client = _client(_editor())
    created = client.post(PAGES, {"title": "Chi siamo", "slug": "chi-siamo"}, format="json")
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["status"] == "DRAFT"
    assert body["published_at"] is None
    page_id = body["id"]
    assert client.get(PAGES).json()["count"] == 1
    patched = client.patch(f"{PAGES}/{page_id}", {"seo_title": "Chi siamo"}, format="json")
    assert patched.status_code == 200
    assert client.delete(f"{PAGES}/{page_id}").status_code == 204
    assert not Page.objects.exists()


@pytest.mark.django_db
def test_staff_page_api_requires_staff_and_model_permissions():
    _page()
    assert _client().get(PAGES).status_code == 401
    assert _client(staff_user("nobody@example.com")).get(PAGES).status_code == 403
    viewer = staff_user("viewer@example.com", "cms.view_page")
    assert _client(viewer).get(PAGES).status_code == 200
    denied = _client(viewer).post(PAGES, {"title": "X", "slug": "x"}, format="json")
    assert denied.status_code == 403


@pytest.mark.django_db
def test_page_text_fields_reject_markup_and_canonical_must_be_https():
    client = _client(_editor())
    bad_title = client.post(PAGES, {"title": "<script>x</script>", "slug": "a"}, format="json")
    assert bad_title.status_code == 400
    bad_canonical = client.post(
        PAGES,
        {"title": "A", "slug": "a", "canonical_url": "javascript:alert(1)"},
        format="json",
    )
    assert bad_canonical.status_code == 400
    http_canonical = client.post(
        PAGES, {"title": "A", "slug": "a", "canonical_url": "http://x.example"}, format="json"
    )
    assert http_canonical.status_code == 400


@pytest.mark.django_db
def test_publishing_requires_publish_permission():
    page = _page()
    editor = _editor()
    response = _client(editor).patch(f"{PAGES}/{page.pk}", {"status": "PUBLISHED"}, format="json")
    assert response.status_code == 403
    publisher = _editor("publisher@example.com", "cms.publish_page")
    response = _client(publisher).patch(
        f"{PAGES}/{page.pk}", {"status": "PUBLISHED"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["published_at"] is not None


@pytest.mark.django_db
def test_publishing_rejected_while_section_media_is_not_approved():
    pending = make_asset(authorization_status="PENDING")
    page = _page()
    _section(page, "hero", {"heading": "Ciao", "image": pending.pk}, variant="split")
    publisher = _editor("publisher@example.com", "cms.publish_page")
    response = _client(publisher).patch(
        f"{PAGES}/{page.pk}", {"status": "PUBLISHED"}, format="json"
    )
    assert response.status_code == 400
    assert "approved" in str(response.json()).lower()


@pytest.mark.django_db
def test_add_edit_hide_remove_sections():
    page = _page()
    client = _client(_editor())
    url = f"{PAGES}/{page.pk}/sections"
    first = client.post(url, {"type": "cta", "variant": "banner", "content": CTA}, format="json")
    assert first.status_code == 201, first.content
    assert first.json()["position"] == 0
    assert first.json()["schema_version"] == 1
    second = client.post(
        url,
        {
            "type": "stats",
            "variant": "row",
            "content": {"items": [{"value": "20", "label": "Anni"}]},
        },
        format="json",
    )
    assert second.status_code == 201, second.content
    assert second.json()["position"] == 1
    section_id = first.json()["id"]
    edited = client.patch(
        f"{url}/{section_id}",
        {"content": {**CTA, "heading": "Nuovo titolo"}, "enabled": False},
        format="json",
    )
    assert edited.status_code == 200, edited.content
    assert edited.json()["enabled"] is False
    assert edited.json()["content"]["heading"] == "Nuovo titolo"
    assert client.delete(f"{url}/{section_id}").status_code == 204
    remaining = client.get(url).json()
    assert [(s["type"], s["position"]) for s in remaining] == [("stats", 0)]


@pytest.mark.django_db
def test_section_api_rejects_invalid_content_and_markup():
    page = _page()
    client = _client(_editor())
    url = f"{PAGES}/{page.pk}/sections"
    for payload in (
        {"type": "cta", "variant": "banner", "content": {**CTA, "heading": "<script>x</script>"}},
        {"type": "cta", "variant": "banner", "content": {**CTA, "html": "<p>x</p>"}},
        {
            "type": "cta",
            "variant": "banner",
            "content": {**CTA, "cta": {"label": "x", "href": "javascript:alert(1)"}},
        },
        {"type": "cta", "variant": "unknown", "content": CTA},
        {"type": "cta", "variant": "banner", "schema_version": 7, "content": CTA},
        {"type": "unknown", "variant": "banner", "content": CTA},
    ):
        response = client.post(url, payload, format="json")
        assert response.status_code == 400, payload
    assert not PageSection.objects.exists()


@pytest.mark.django_db
def test_sections_are_scoped_to_their_page():
    page, other = _page("a"), _page("b")
    section = _section(other)
    client = _client(_editor())
    assert client.get(f"{PAGES}/{page.pk}/sections/{section.pk}").status_code == 404
    assert client.get(f"{PAGES}/999999/sections").status_code == 404


@pytest.mark.django_db
def test_reorder_rewrites_positions_transactionally():
    page = _page()
    a, b, c = (_section(page) for _ in range(3))
    client = _client(_editor())
    url = f"{PAGES}/{page.pk}/sections/order"
    response = client.put(url, {"section_ids": [c.pk, a.pk, b.pk]}, format="json")
    assert response.status_code == 200, response.content
    assert [s["id"] for s in response.json()] == [c.pk, a.pk, b.pk]
    assert list(page.sections.values_list("id", "position")) == [(c.pk, 0), (a.pk, 1), (b.pk, 2)]
    # Partial or foreign id lists are rejected and leave the order untouched.
    foreign = _section(_page("other"))
    for ids in ([c.pk, a.pk], [c.pk, a.pk, b.pk, foreign.pk], [c.pk, c.pk, a.pk]):
        assert client.put(url, {"section_ids": ids}, format="json").status_code == 400
    assert list(page.sections.values_list("id", flat=True)) == [c.pk, a.pk, b.pk]


@pytest.mark.django_db
def test_reorder_requires_change_permission():
    page = _page()
    section = _section(page)
    viewer = staff_user("v@example.com", "cms.view_pagesection")
    response = _client(viewer).put(
        f"{PAGES}/{page.pk}/sections/order", {"section_ids": [section.pk]}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_can_read_draft_pages_and_disabled_sections():
    page = _page(status=Page.Status.DRAFT)
    _section(page, enabled=False)
    client = _client(_editor())
    assert client.get(f"{PAGES}/{page.pk}").status_code == 200
    assert len(client.get(f"{PAGES}/{page.pk}/sections").json()) == 1


@pytest.mark.django_db
def test_section_schema_catalogue_for_staff():
    response = _client(staff_user("s@example.com")).get("/api/v1/cms/section-schemas")
    assert response.status_code == 200
    types = {item["type"] for item in response.json()}
    assert {"hero", "gallery", "territory"} <= types
    assert _client().get("/api/v1/cms/section-schemas").status_code == 401


# --- model / admin cannot bypass validation ---------------------------------------------


@pytest.mark.django_db
def test_model_save_and_clean_validate_content():
    page = _page()
    section = PageSection(
        page=page, type="cta", variant="banner", position=0, content={"heading": "<b>x</b>"}
    )
    with pytest.raises(ValidationError):
        section.full_clean()
    with pytest.raises(ValidationError):
        section.save()
    assert not PageSection.objects.exists()


@pytest.mark.django_db
def test_admin_inline_rejects_invalid_section_content(client):
    from django.contrib.auth import get_user_model

    admin = get_user_model().objects.create_superuser(email="root@example.com", password="x" * 16)
    force_staff_login(client, admin)
    page = _page()
    data = {
        "title": page.title,
        "slug": page.slug,
        "status": "DRAFT",
        "seo_title": "",
        "seo_description": "",
        "canonical_url": "",
        "sections-TOTAL_FORMS": "1",
        "sections-INITIAL_FORMS": "0",
        "sections-MIN_NUM_FORMS": "0",
        "sections-MAX_NUM_FORMS": "1000",
        "sections-0-type": "cta",
        "sections-0-variant": "banner",
        "sections-0-position": "0",
        "sections-0-enabled": "on",
        "sections-0-schema_version": "1",
        "sections-0-content": (
            '{"heading": "<script>alert(1)</script>", "cta": {"label": "a", "href": "/"}}'
        ),
    }
    response = client.post(f"/django-admin/cms/page/{page.pk}/change/", data)
    assert response.status_code == 200  # re-rendered with errors
    assert not PageSection.objects.exists()


# --- public API -------------------------------------------------------------------------


@pytest.mark.django_db
def test_public_page_serves_only_published_pages():
    _page("bozza", status=Page.Status.DRAFT)
    _page("vecchia", status=Page.Status.ARCHIVED)
    client = _client()
    assert client.get("/api/v1/public/pages/bozza").status_code == 404
    assert client.get("/api/v1/public/pages/vecchia").status_code == 404
    assert client.get("/api/v1/public/pages/missing").status_code == 404


@pytest.mark.django_db
def test_public_page_serves_only_enabled_sections_in_order_with_resolved_media():
    image = make_asset(alt_text="Giardino")
    page = _page("home", status=Page.Status.PUBLISHED)
    hero = _section(page, "hero", {"heading": "Benvenuti", "image": image.pk}, variant="split")
    _section(page, enabled=False)
    stats = _section(page, "stats", {"items": [{"value": "10", "label": "Squadre"}]}, variant="row")
    response = _client().get("/api/v1/public/pages/home")
    assert response.status_code == 200
    body = response.json()
    assert [s["id"] for s in body["sections"]] == [hero.pk, stats.pk]
    resolved = body["sections"][0]["content"]["image"]
    assert resolved["id"] == image.pk
    assert resolved["alt_text"] == "Giardino"
    assert resolved["url"].startswith("/media/public/")
    assert "enabled" not in body["sections"][0]
    assert "status" not in body


@pytest.mark.django_db
def test_public_page_hides_media_that_stopped_being_public():
    from apps.media.services import update_asset

    image = make_asset()
    page = _page("home", status=Page.Status.PUBLISHED)
    _section(page, "hero", {"heading": "Benvenuti", "image": image.pk}, variant="split")
    # Referenced media cannot be made PRIVATE; rejecting it is the take-down path.
    with run_on_commit():
        update_asset(image, authorization_status="REJECTED")
    body = _client().get("/api/v1/public/pages/home").json()
    assert body["sections"][0]["content"]["image"] is None
