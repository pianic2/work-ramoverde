import copy
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import (
    NavigationItem,
    NavigationMenu,
    Page,
    PageSection,
    SEOSettings,
    SiteSettings,
)
from .sections import LATEST_VERSIONS
from .services import page_seo, public_sections


def run_model_clean(instance: models.Model, exclude: list[str] | None = None) -> None:
    """Run the model's field validators and clean() and surface errors as DRF errors.

    Uniqueness is left to DRF's own validators.
    """
    try:
        instance.full_clean(exclude=exclude, validate_unique=False, validate_constraints=False)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.message_dict) from exc


class PageSerializer(serializers.ModelSerializer[Page]):
    class Meta:
        model = Page
        fields = [
            "id",
            "title",
            "slug",
            "status",
            "published_at",
            "seo_title",
            "seo_description",
            "og_image",
            "canonical_url",
            "noindex",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "published_at", "created_at", "updated_at"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        candidate = copy.copy(self.instance) if self.instance is not None else Page()
        for key, value in attrs.items():
            setattr(candidate, key, value)
        run_model_clean(candidate)
        return attrs


class PageSectionSerializer(serializers.ModelSerializer[PageSection]):
    content = serializers.JSONField(
        help_text="Section content; shape defined by the (type, schema_version) schema."
    )
    schema_version = serializers.IntegerField(
        min_value=1, required=False, help_text="Defaults to the latest version of the type."
    )

    class Meta:
        model = PageSection
        fields = [
            "id",
            "type",
            "variant",
            "position",
            "enabled",
            "schema_version",
            "content",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "position", "created_at", "updated_at"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if self.instance is not None:
            candidate = copy.copy(self.instance)
        else:
            candidate = PageSection(page=self.context["page"])
            attrs.setdefault("schema_version", LATEST_VERSIONS.get(attrs.get("type", ""), 1))
        for key, value in attrs.items():
            setattr(candidate, key, value)
        run_model_clean(candidate, exclude=["page", "position"])
        return attrs


class SectionOrderSerializer(serializers.Serializer[Any]):
    section_ids = serializers.ListField(child=serializers.IntegerField(min_value=1))


class SectionSchemaSerializer(serializers.Serializer[Any]):
    type = serializers.CharField()
    schema_version = serializers.IntegerField()
    latest = serializers.BooleanField()
    variants = serializers.ListField(child=serializers.CharField())
    content_fields = serializers.DictField(
        child=serializers.JSONField(), help_text="Content field name -> field description."
    )


# --- public (anonymous) representations -------------------------------------------------


class PublicMediaSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    url = serializers.CharField()
    mime_type = serializers.CharField()
    width = serializers.IntegerField(allow_null=True)
    height = serializers.IntegerField(allow_null=True)
    alt_text = serializers.CharField()


class PublicSectionSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    type = serializers.CharField()
    variant = serializers.CharField()
    schema_version = serializers.IntegerField()
    content = serializers.DictField(
        child=serializers.JSONField(),
        help_text="Validated content; media ids are replaced by public media objects (or null).",
    )


class PublicSeoSerializer(serializers.Serializer[Any]):
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    canonical_url = serializers.CharField(allow_null=True)
    noindex = serializers.BooleanField()
    og_image = PublicMediaSerializer(allow_null=True)


class PublicPageSerializer(serializers.Serializer[Any]):
    slug = serializers.SlugField()
    title = serializers.CharField()
    published_at = serializers.DateTimeField()
    seo = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()

    @extend_schema_field(PublicSeoSerializer)
    def get_seo(self, page: Page) -> dict[str, Any]:
        return page_seo(page)

    @extend_schema_field(PublicSectionSerializer(many=True))
    def get_sections(self, page: Page) -> list[dict[str, Any]]:
        return public_sections(page)


# --- navigation and settings (WR-20) ------------------------------------------------------


class NavigationItemSerializer(serializers.ModelSerializer[NavigationItem]):
    url = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    class Meta:
        model = NavigationItem
        fields = ["id", "parent", "label", "page", "url", "position", "visible", "updated_at"]
        read_only_fields = ["id", "updated_at"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if self.instance is not None:
            candidate = copy.copy(self.instance)
        else:
            candidate = NavigationItem(menu=self.context["menu"])
        for key, value in attrs.items():
            setattr(candidate, key, value)
        run_model_clean(candidate, exclude=["menu"])
        return attrs


class NavigationMenuSerializer(serializers.ModelSerializer[NavigationMenu]):
    items = NavigationItemSerializer(many=True, read_only=True)

    class Meta:
        model = NavigationMenu
        fields = ["id", "key", "title", "items", "updated_at"]
        read_only_fields = ["id", "items", "updated_at"]


class _SingletonSerializer(serializers.ModelSerializer[Any]):
    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        assert self.instance is not None, "singleton serializers always update an instance"
        candidate = copy.copy(self.instance)
        for key, value in attrs.items():
            setattr(candidate, key, value)
        run_model_clean(candidate)
        return attrs


class SiteSettingsSerializer(_SingletonSerializer):
    class Meta:
        model = SiteSettings
        exclude = ["id"]
        read_only_fields = ["updated_at"]


class SEOSettingsSerializer(_SingletonSerializer):
    class Meta:
        model = SEOSettings
        exclude = ["id"]
        read_only_fields = ["updated_at"]


class PublicNavigationLinkSerializer(serializers.Serializer[Any]):
    label = serializers.CharField()  # type: ignore[assignment]  # DRF Field.label clash
    url = serializers.CharField(allow_null=True, help_text="Safe URL target, if not a page.")
    page_slug = serializers.SlugField(allow_null=True, help_text="Published CMS page target.")


class PublicNavigationItemSerializer(PublicNavigationLinkSerializer):
    children = PublicNavigationLinkSerializer(many=True)


class PublicNavigationSerializer(serializers.Serializer[Any]):
    key = serializers.SlugField()
    title = serializers.CharField()
    items = PublicNavigationItemSerializer(many=True)


class PublicSeoDefaultsSerializer(serializers.Serializer[Any]):
    default_title = serializers.CharField(allow_null=True)
    default_description = serializers.CharField(allow_null=True)
    default_og_image = PublicMediaSerializer(allow_null=True)
    allow_indexing = serializers.BooleanField()


class PublicSiteSettingsSerializer(serializers.Serializer[Any]):
    """Unconfirmed (empty) values are null; never invented."""

    legal_name = serializers.CharField(allow_null=True)
    brand_name = serializers.CharField(allow_null=True)
    vat_number = serializers.CharField(allow_null=True)
    address = serializers.CharField(allow_null=True)
    phone = serializers.CharField(allow_null=True)
    email = serializers.EmailField(allow_null=True)
    opening_hours = serializers.CharField(allow_null=True)
    tagline = serializers.CharField(allow_null=True)
    certifications_text = serializers.CharField(allow_null=True)
    footer_text = serializers.CharField(allow_null=True)
    primary_cta = PublicNavigationLinkSerializer(allow_null=True)
    seo = PublicSeoDefaultsSerializer()
