import copy
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Page, PageSection
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
