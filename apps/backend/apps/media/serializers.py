from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import MediaAsset
from .services import public_url

_METADATA_FIELDS = ["alt_text", "caption", "visibility", "origin", "source_note"]


class MediaAssetSerializer(serializers.ModelSerializer[MediaAsset]):
    """Staff representation: full metadata, never the blob itself."""

    public_url = serializers.SerializerMethodField()
    uploaded_by_email = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = [
            "id",
            "original_filename",
            "mime_type",
            "kind",
            "size",
            "checksum_sha256",
            "width",
            "height",
            *_METADATA_FIELDS,
            "authorization_status",
            "public_url",
            "uploaded_by_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "original_filename",
            "mime_type",
            "kind",
            "size",
            "checksum_sha256",
            "width",
            "height",
            "authorization_status",
            "public_url",
            "uploaded_by_email",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_public_url(self, obj: MediaAsset) -> str | None:
        return public_url(obj)

    @extend_schema_field(serializers.EmailField(allow_null=True))
    def get_uploaded_by_email(self, obj: MediaAsset) -> str | None:
        return getattr(obj.uploaded_by, "email", None)


class MediaAssetUploadSerializer(serializers.Serializer[Any]):
    file = serializers.FileField(allow_empty_file=False)
    alt_text = serializers.CharField(max_length=255, required=False, allow_blank=True)
    caption = serializers.CharField(max_length=500, required=False, allow_blank=True)
    visibility = serializers.ChoiceField(
        choices=MediaAsset.Visibility.choices, default=MediaAsset.Visibility.PRIVATE
    )
    origin = serializers.ChoiceField(
        choices=MediaAsset.Origin.choices, default=MediaAsset.Origin.STAFF_UPLOAD
    )
    source_note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class MediaAssetUpdateSerializer(serializers.ModelSerializer[MediaAsset]):
    class Meta:
        model = MediaAsset
        fields = [*_METADATA_FIELDS, "authorization_status"]


class PublicMediaAssetSerializer(serializers.ModelSerializer[MediaAsset]):
    """Anonymous representation of a PUBLIC + APPROVED asset."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = ["id", "url", "mime_type", "width", "height", "alt_text", "caption"]
        read_only_fields = fields

    def get_url(self, obj: MediaAsset) -> str:
        return public_url(obj) or ""
