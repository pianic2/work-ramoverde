import pytest
from cms_media_helpers import make_asset, staff_user
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.cms.models import NavigationItem, NavigationMenu, Page, SEOSettings, SiteSettings

MENUS = "/api/v1/cms/navigation-menus"
NAV_PERMS = (
    "cms.view_navigationmenu",
    "cms.add_navigationmenu",
    "cms.change_navigationmenu",
    "cms.delete_navigationmenu",
    "cms.view_navigationitem",
    "cms.add_navigationitem",
    "cms.change_navigationitem",
    "cms.delete_navigationitem",
)


def _client(user=None) -> APIClient:
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user)
    return client


def _page(slug, status=Page.Status.PUBLISHED) -> Page:
    return Page.objects.create(title=slug.title(), slug=slug, status=status)


def _item(menu, label, *, page=None, url="", parent=None, position=0, visible=True):
    item = NavigationItem(
        menu=menu,
        label=label,
        page=page,
        url=url,
        parent=parent,
        position=position,
        visible=visible,
    )
    item.full_clean()
    item.save()
    return item


# --- navigation ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_staff_navigation_crud_and_permissions():
    page = _page("servizi")
    assert _client().get(MENUS).status_code == 401
    assert _client(staff_user("np@example.com")).get(MENUS).status_code == 403
    client = _client(staff_user("nav@example.com", *NAV_PERMS))
    menu = client.post(MENUS, {"key": "header", "title": "Header"}, format="json")
    assert menu.status_code == 201, menu.content
    items_url = f"{MENUS}/{menu.json()['id']}/items"
    first = client.post(items_url, {"label": "Servizi", "page": page.pk}, format="json")
    assert first.status_code == 201, first.content
    child = client.post(
        items_url,
        {"label": "Preventivo", "url": "/contatti#preventivo", "parent": first.json()["id"]},
        format="json",
    )
    assert child.status_code == 201, child.content
    patched = client.patch(
        f"{items_url}/{first.json()['id']}", {"visible": False, "position": 3}, format="json"
    )
    assert patched.status_code == 200
    detail = client.get(f"{MENUS}/{menu.json()['id']}").json()
    assert len(detail["items"]) == 2
    assert client.delete(f"{items_url}/{child.json()['id']}").status_code == 204


@pytest.mark.django_db
def test_navigation_item_validation():
    menu = NavigationMenu.objects.create(key="header", title="Header")
    page = _page("chi-siamo")
    client = _client(staff_user("nav@example.com", *NAV_PERMS))
    url = f"{MENUS}/{menu.pk}/items"
    for payload in (
        {"label": "Nessun target"},
        {"label": "Due target", "page": page.pk, "url": "/x"},
        {"label": "Script", "url": "javascript:alert(1)"},
        {"label": "Http", "url": "http://example.com"},
        {"label": "<b>Markup</b>", "url": "/x"},
    ):
        assert client.post(url, payload, format="json").status_code == 400, payload
    parent = _item(menu, "Parent", url="/a")
    child = _item(menu, "Child", url="/b", parent=parent)
    too_deep = client.post(url, {"label": "Deep", "url": "/c", "parent": child.pk}, format="json")
    assert too_deep.status_code == 400
    other_menu = NavigationMenu.objects.create(key="footer", title="Footer")
    foreign = _item(other_menu, "Foreign", url="/f")
    cross = client.post(url, {"label": "X", "url": "/x", "parent": foreign.pk}, format="json")
    assert cross.status_code == 400


@pytest.mark.django_db
def test_model_clean_enforces_single_target():
    menu = NavigationMenu.objects.create(key="header", title="Header")
    with pytest.raises(ValidationError):
        _item(menu, "Nothing")


@pytest.mark.django_db
def test_public_navigation_shows_only_visible_items_with_published_targets():
    menu = NavigationMenu.objects.create(key="header", title="Header")
    published = _page("servizi")
    draft = _page("bozza", status=Page.Status.DRAFT)
    services = _item(menu, "Servizi", page=published, position=0)
    _item(menu, "Bozza", page=draft, position=1)
    _item(menu, "Nascosto", url="/x", position=2, visible=False)
    hidden_parent = _item(menu, "Padre nascosto", url="/p", position=3, visible=False)
    _item(menu, "Figlio orfano", url="/q", parent=hidden_parent)
    _item(menu, "Contatti", url="/contatti", position=4)
    _item(menu, "Potature", url="/servizi#potature", parent=services, position=0)
    _item(menu, "Figlio bozza", page=draft, parent=services, position=1)

    response = _client().get("/api/v1/public/navigation/header")
    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "header"
    assert [i["label"] for i in body["items"]] == ["Servizi", "Contatti"]
    assert body["items"][0] == {
        "label": "Servizi",
        "url": None,
        "page_slug": "servizi",
        "children": [{"label": "Potature", "url": "/servizi#potature", "page_slug": None}],
    }
    assert _client().get("/api/v1/public/navigation/missing").status_code == 404


@pytest.mark.django_db
def test_navigation_change_is_reflected_on_next_public_call():
    menu = NavigationMenu.objects.create(key="footer", title="Footer")
    item = _item(menu, "Privacy", url="/privacy")
    client = _client()
    assert client.get("/api/v1/public/navigation/footer").json()["items"][0]["label"] == "Privacy"
    editor = _client(staff_user("nav@example.com", *NAV_PERMS))
    editor.patch(f"{MENUS}/{menu.pk}/items/{item.pk}", {"label": "Privacy policy"}, format="json")
    assert (
        client.get("/api/v1/public/navigation/footer").json()["items"][0]["label"]
        == "Privacy policy"
    )


@pytest.mark.django_db
def test_page_referenced_by_navigation_cannot_be_deleted():
    menu = NavigationMenu.objects.create(key="header", title="Header")
    page = _page("servizi")
    _item(menu, "Servizi", page=page)
    client = _client(staff_user("p@example.com", "cms.view_page", "cms.delete_page"))
    assert client.delete(f"/api/v1/cms/pages/{page.pk}").status_code == 409
    assert Page.objects.filter(pk=page.pk).exists()


# --- site settings ------------------------------------------------------------------------


@pytest.mark.django_db
def test_site_settings_unconfirmed_values_are_null_by_default():
    body = _client().get("/api/v1/public/site-settings").json()
    for key in (
        "legal_name",
        "brand_name",
        "vat_number",
        "address",
        "phone",
        "email",
        "opening_hours",
        "tagline",
        "certifications_text",
        "footer_text",
    ):
        assert body[key] is None, key
    assert body["primary_cta"] is None
    assert SiteSettings.objects.count() <= 1


@pytest.mark.django_db
def test_staff_updates_site_settings_and_public_reflects_next_call():
    url = "/api/v1/cms/site-settings"
    assert _client().patch(url, {}, format="json").status_code == 401
    viewer = staff_user("v@example.com", "cms.view_sitesettings")
    assert _client(viewer).get(url).status_code == 200
    assert _client(viewer).patch(url, {"phone": "1"}, format="json").status_code == 403
    editor = _client(
        staff_user("s@example.com", "cms.view_sitesettings", "cms.change_sitesettings")
    )
    contact = _page("contatti")
    response = editor.patch(
        url,
        {
            "legal_name": "RAMO VERDE SRL",
            "brand_name": "RamoVerde",
            "vat_number": "01637570522",
            "address": "Località San Marziale 11/13, Colle di Val d'Elsa",
            "phone": "05771607653",
            "certifications_text": "ISO 9001, SOA V CATEGORIA",
            "primary_cta_label": "Richiedi un preventivo",
            "primary_cta_page": contact.pk,
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    public = _client().get("/api/v1/public/site-settings").json()
    assert public["legal_name"] == "RAMO VERDE SRL"
    assert public["vat_number"] == "01637570522"
    assert public["email"] is None
    assert public["primary_cta"] == {
        "label": "Richiedi un preventivo",
        "url": None,
        "page_slug": "contatti",
    }
    editor.patch(url, {"phone": "0577 1607653"}, format="json")
    assert _client().get("/api/v1/public/site-settings").json()["phone"] == "0577 1607653"
    assert SiteSettings.objects.count() == 1


@pytest.mark.django_db
def test_site_settings_validation():
    editor = _client(
        staff_user("s@example.com", "cms.view_sitesettings", "cms.change_sitesettings")
    )
    url = "/api/v1/cms/site-settings"
    for payload in (
        {"footer_text": "<script>alert(1)</script>"},
        {"vat_number": "IT-ABC"},
        {"phone": "call me"},
        {"email": "not-an-email"},
        {"primary_cta_label": "Vai"},  # label without target
        {"primary_cta_label": "Vai", "primary_cta_url": "javascript:alert(1)"},
    ):
        assert editor.patch(url, payload, format="json").status_code == 400, payload


@pytest.mark.django_db
def test_public_site_settings_hides_cta_to_unpublished_page():
    draft = _page("bozza", status=Page.Status.DRAFT)
    settings_obj = SiteSettings.load()
    settings_obj.primary_cta_label = "Vai"
    settings_obj.primary_cta_page = draft
    settings_obj.full_clean()
    settings_obj.save()
    assert _client().get("/api/v1/public/site-settings").json()["primary_cta"] is None


@pytest.mark.django_db
def test_site_settings_is_singleton():
    first = SiteSettings.load()
    second = SiteSettings(legal_name="RAMO VERDE SRL")
    second.save()
    assert first.pk == second.pk == 1
    assert SiteSettings.objects.count() == 1


@pytest.mark.django_db
def test_admin_pages_render_and_singleton_add_is_disabled_once_present(client):
    from django.contrib.auth import get_user_model

    admin = get_user_model().objects.create_superuser(email="root@example.com", password="x" * 16)
    client.force_login(admin)
    for url in (
        "/admin/cms/navigationmenu/add/",
        "/admin/cms/sitesettings/add/",
        "/admin/cms/seosettings/",
        "/admin/cms/page/add/",
    ):
        assert client.get(url).status_code == 200, url
    SiteSettings.load()
    assert client.get("/admin/cms/sitesettings/add/").status_code == 403


# --- SEO ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_seo_settings_defaults_and_public_exposure():
    url = "/api/v1/cms/seo-settings"
    editor = _client(
        staff_user("seo@example.com", "cms.view_seosettings", "cms.change_seosettings")
    )
    image = make_asset()
    private = make_asset(visibility="PRIVATE")
    assert editor.patch(url, {"default_og_image": private.pk}, format="json").status_code == 400
    response = editor.patch(
        url,
        {
            "default_title": "RamoVerde",
            "default_description": "Manutenzione del verde",
            "default_og_image": image.pk,
            "allow_indexing": True,
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    seo = _client().get("/api/v1/public/site-settings").json()["seo"]
    assert seo["default_title"] == "RamoVerde"
    assert seo["allow_indexing"] is True
    assert seo["default_og_image"]["id"] == image.pk
    assert SEOSettings.objects.count() == 1


@pytest.mark.django_db
def test_page_seo_falls_back_to_site_defaults():
    image = make_asset()
    seo = SEOSettings.load()
    seo.default_description = "Descrizione di default"
    seo.default_og_image = image
    seo.allow_indexing = False
    seo.save()
    Page.objects.create(title="Home", slug="home", status=Page.Status.PUBLISHED)
    body = _client().get("/api/v1/public/pages/home").json()["seo"]
    assert body["title"] == "Home"
    assert body["description"] == "Descrizione di default"
    assert body["og_image"]["id"] == image.pk
    assert body["noindex"] is True  # site-wide indexing disabled
    seo.allow_indexing = True
    seo.save()
    assert _client().get("/api/v1/public/pages/home").json()["seo"]["noindex"] is False


@pytest.mark.django_db
def test_page_seo_overrides_defaults():
    seo = SEOSettings.load()
    seo.default_description = "Default"
    seo.allow_indexing = True
    seo.save()
    Page.objects.create(
        title="Servizi",
        slug="servizi",
        status=Page.Status.PUBLISHED,
        seo_title="Servizi di giardinaggio",
        seo_description="Su misura",
        canonical_url="https://example.com/servizi",
        noindex=True,
    )
    body = _client().get("/api/v1/public/pages/servizi").json()["seo"]
    assert body == {
        "title": "Servizi di giardinaggio",
        "description": "Su misura",
        "canonical_url": "https://example.com/servizi",
        "noindex": True,
        "og_image": None,
    }
