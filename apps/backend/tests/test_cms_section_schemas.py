import pytest
from cms_media_helpers import make_asset
from django.core.exceptions import ValidationError

from apps.cms.sections import LATEST_VERSIONS, SECTION_SCHEMAS, SectionType, validate_section

ALL_TYPES = [
    "hero",
    "services",
    "projects",
    "gallery",
    "text-media",
    "stats",
    "certifications",
    "cta",
    "contact",
    "territory",
]


def _errors(exc: ValidationError) -> str:
    return str(exc.message_dict)


def test_registry_covers_initial_section_types():
    assert sorted(SectionType.values) == sorted(ALL_TYPES)
    for section_type in ALL_TYPES:
        assert (section_type, LATEST_VERSIONS[section_type]) in SECTION_SCHEMAS
        assert SECTION_SCHEMAS[(section_type, 1)].variants


@pytest.mark.django_db
def test_valid_hero_is_cleaned():
    image = make_asset()
    content = {
        "heading": "Manutenzione del verde",
        "subheading": "Colle di Val d'Elsa",
        "image": image.pk,
        "primary_cta": {"label": "Contattaci", "href": "/contatti"},
    }
    assert validate_section("hero", 1, "split", content) == content


def test_unknown_type_version_and_variant_rejected():
    with pytest.raises(ValidationError) as exc:
        validate_section("carousel", 1, "default", {})
    assert "type" in exc.value.message_dict
    with pytest.raises(ValidationError) as exc:
        validate_section("cta", 99, "banner", {})
    assert "schema_version" in exc.value.message_dict
    with pytest.raises(ValidationError) as exc:
        validate_section("cta", 1, "rainbow", {"heading": "x", "cta": {"label": "a", "href": "/"}})
    assert "variant" in exc.value.message_dict


def test_unknown_keys_and_wrong_types_rejected():
    with pytest.raises(ValidationError) as exc:
        validate_section(
            "cta", 1, "banner", {"heading": "Ciao", "cta": {"label": "Vai", "href": "/"}, "x": 1}
        )
    assert "content.x" in _errors(exc.value)
    with pytest.raises(ValidationError) as exc:
        validate_section("cta", 1, "banner", {"heading": 42, "cta": {"label": "Vai", "href": "/"}})
    assert "content.heading" in _errors(exc.value)
    with pytest.raises(ValidationError) as exc:
        validate_section("cta", 1, "banner", {"cta": {"label": "Vai", "href": "/"}})
    assert "content.heading" in _errors(exc.value)
    with pytest.raises(ValidationError):
        validate_section("cta", 1, "banner", ["not", "an", "object"])


def test_length_limits_enforced():
    with pytest.raises(ValidationError) as exc:
        validate_section(
            "cta", 1, "banner", {"heading": "x" * 500, "cta": {"label": "a", "href": "/"}}
        )
    assert "content.heading" in _errors(exc.value)


@pytest.mark.parametrize(
    "heading",
    [
        "<script>alert(1)</script>",
        "Ciao <b>mondo</b>",
        '<div style="color:red">x</div>',
        "<img src=x onerror=alert(1)>",
        "javascript:alert(1)",
    ],
)
def test_markup_and_script_rejected_in_text(heading):
    with pytest.raises(ValidationError) as exc:
        validate_section(
            "cta", 1, "banner", {"heading": heading, "cta": {"label": "a", "href": "/"}}
        )
    assert "content.heading" in _errors(exc.value)


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        " javascript:alert(1)",
        "JAVASCRIPT:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "http://insecure.example.com",
        "//evil.example.com",
        "vbscript:msgbox",
        "/path with spaces",
        "https://",
        "ftp://example.com",
        "\\\\evil",
    ],
)
def test_unsafe_urls_rejected(href):
    with pytest.raises(ValidationError) as exc:
        validate_section(
            "cta", 1, "banner", {"heading": "Hi", "cta": {"label": "Go", "href": href}}
        )
    assert "content.cta.href" in _errors(exc.value)


@pytest.mark.parametrize(
    "href", ["/contatti", "#preventivo", "https://example.com/a?b=c", "tel:+390577000000", "/"]
)
def test_safe_urls_accepted(href):
    validate_section("cta", 1, "banner", {"heading": "Hi", "cta": {"label": "Go", "href": href}})


@pytest.mark.django_db
def test_media_reference_must_exist_and_be_public():
    private = make_asset(visibility="PRIVATE")
    rejected = make_asset(visibility="PUBLIC", authorization_status="REJECTED")
    pending = make_asset(visibility="PUBLIC", authorization_status="PENDING")
    for bad in (private.pk, rejected.pk, 999_999, "1", True):
        with pytest.raises(ValidationError) as exc:
            validate_section("hero", 1, "split", {"heading": "Hi", "image": bad})
        assert "content.image" in _errors(exc.value)
    # Pending public media may be referenced by drafts; publication requires approval.
    validate_section("hero", 1, "split", {"heading": "Hi", "image": pending.pk})


@pytest.mark.django_db
def test_gallery_items_validated_with_paths():
    image = make_asset()
    with pytest.raises(ValidationError) as exc:
        validate_section(
            "gallery",
            1,
            "grid",
            {"items": [{"media": image.pk}, {"media": image.pk, "caption": "<i>x</i>"}]},
        )
    assert "content.items[1].caption" in _errors(exc.value)
    with pytest.raises(ValidationError):
        validate_section("gallery", 1, "grid", {"items": []})


def test_reference_id_lists_are_placeholders_of_positive_unique_ints():
    validate_section("services", 1, "grid", {"heading": "Servizi", "service_ids": [3, 1]})
    for bad in ([0], [1, 1], ["a"], "1,2", [1.5]):
        with pytest.raises(ValidationError):
            validate_section("services", 1, "grid", {"heading": "Servizi", "service_ids": bad})


def test_schema_description_is_json_friendly():
    import json

    schema = SECTION_SCHEMAS[("gallery", 1)]
    described = schema.describe()
    json.dumps(described)
    assert described["type"] == "gallery"
    assert described["fields"]["items"]["kind"] == "list"
    assert described["fields"]["items"]["item"]["fields"]["media"]["kind"] == "media"
