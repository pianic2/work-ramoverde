from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.media.models import MediaAsset
from apps.media.validators import validate_multiline_plain_text, validate_plain_text

from .sections import LATEST_VERSIONS, SectionType, url_error, validate_section


def validate_canonical_url(value: str) -> None:
    if not value.lower().startswith("https://") or url_error(value):
        raise ValidationError("Canonical URL must be an absolute https:// URL.")


def validate_public_media(asset: MediaAsset | None, field: str) -> None:
    """Media referenced by public-facing content must be PUBLIC and not REJECTED."""
    if asset is None:
        return
    if asset.visibility != MediaAsset.Visibility.PUBLIC:
        raise ValidationError({field: "Only PUBLIC media assets can be used."})
    if asset.authorization_status == MediaAsset.AuthorizationStatus.REJECTED:
        raise ValidationError({field: "This media asset was rejected for publication."})


class Page(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        ARCHIVED = "ARCHIVED", "Archived"

    title = models.CharField(max_length=200, validators=[validate_plain_text])
    slug = models.SlugField(max_length=100, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    # Per-page SEO; empty values fall back to the site-wide SEOSettings.
    seo_title = models.CharField(max_length=70, blank=True, validators=[validate_plain_text])
    seo_description = models.CharField(
        max_length=300, blank=True, validators=[validate_multiline_plain_text]
    )
    og_image = models.ForeignKey(
        MediaAsset, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    canonical_url = models.CharField(
        max_length=500, blank=True, validators=[validate_canonical_url]
    )
    noindex = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]
        permissions = [("publish_page", "Can publish, unpublish or archive pages")]

    def __str__(self) -> str:
        return f"{self.title} (/{self.slug})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = {*kwargs["update_fields"], "published_at"}
        super().save(*args, **kwargs)

    def clean(self) -> None:
        validate_public_media(self.og_image, "og_image")
        if self.status == self.Status.PUBLISHED and self.pk is not None:
            from .services import publication_errors

            errors = publication_errors(self)
            if errors:
                raise ValidationError({"status": errors})


class PageSection(models.Model):
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="sections")
    type = models.CharField(max_length=32, choices=SectionType.choices)
    variant = models.CharField(max_length=40)
    position = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    schema_version = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    content = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["page", "position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["page", "position"], name="cms_pagesection_unique_position"
            )
        ]

    def __str__(self) -> str:
        return f"{self.page.slug}#{self.position} {self.type}/{self.variant}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Validation also runs on plain ORM saves so no write path can store unsafe content.
        self.content = validate_section(self.type, self.schema_version, self.variant, self.content)
        super().save(*args, **kwargs)

    def clean(self) -> None:
        self.content = validate_section(self.type, self.schema_version, self.variant, self.content)

    @staticmethod
    def latest_version(section_type: str) -> int:
        return LATEST_VERSIONS.get(section_type, 1)
