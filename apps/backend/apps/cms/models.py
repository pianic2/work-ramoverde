from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

from apps.media.models import MediaAsset
from apps.media.validators import validate_multiline_plain_text, validate_plain_text

from .sections import LATEST_VERSIONS, SectionType, media_ids, url_error, validate_section


def validate_canonical_url(value: str) -> None:
    if not value.lower().startswith("https://") or url_error(value):
        raise ValidationError("Canonical URL must be an absolute https:// URL.")


def _stored_value(instance: models.Model, attname: str) -> Any:
    """Value of `attname` currently in the database (None for unsaved rows)."""
    if instance.pk is None:
        return None
    return (
        type(instance)
        ._default_manager.filter(pk=instance.pk)
        .values_list(attname, flat=True)
        .first()
    )


def validate_changed_public_media(instance: models.Model, field: str) -> None:
    """Check a media FK only when it changes, so later rejection never blocks other edits."""
    asset = getattr(instance, field)
    if asset is not None and asset.pk != _stored_value(instance, f"{field}_id"):
        validate_public_media(asset, field)


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
        validate_changed_public_media(self, "og_image")
        if self.status == self.Status.PUBLISHED:
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
        self._validate_content()
        super().save(*args, **kwargs)

    def clean(self) -> None:
        self._validate_content()

    def _validate_content(self) -> None:
        self.content = validate_section(
            self.type,
            self.schema_version,
            self.variant,
            self.content,
            already_referenced=self._stored_media_ids(),
        )

    def _stored_media_ids(self) -> set[int]:
        if self.pk is None:
            return set()
        stored = (
            PageSection.objects.filter(pk=self.pk)
            .values_list("type", "schema_version", "content")
            .first()
        )
        return media_ids(*stored) if stored else set()

    @staticmethod
    def latest_version(section_type: str) -> int:
        return LATEST_VERSIONS.get(section_type, 1)


def validate_safe_url(value: str) -> None:
    message = url_error(value)
    if message:
        raise ValidationError(message)


validate_vat_number = RegexValidator(
    r"^(IT)?\d{11}$", "Enter an 11-digit Italian VAT number (optionally prefixed by IT)."
)
validate_phone = RegexValidator(r"^\+?[0-9 ]{6,20}$", "Enter digits, spaces and optional +.")


def _check_single_target(page: "Page | None", url: str, label_field: str) -> dict[str, str]:
    if page is not None and url:
        return {label_field: "Choose either a page or a URL, not both."}
    if page is None and not url:
        return {label_field: "A page or a URL is required."}
    return {}


class NavigationMenu(models.Model):
    key = models.SlugField(max_length=50, unique=True, help_text="e.g. header, footer")
    title = models.CharField(max_length=100, validators=[validate_plain_text])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


class NavigationItem(models.Model):
    """Menu entry pointing at a CMS page or a safe URL. One level of nesting."""

    menu = models.ForeignKey(NavigationMenu, on_delete=models.CASCADE, related_name="items")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    label = models.CharField(max_length=80, validators=[validate_plain_text])
    page = models.ForeignKey(
        Page, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    url = models.CharField(max_length=500, blank=True, validators=[validate_safe_url])
    position = models.PositiveIntegerField(default=0)
    visible = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["menu", "position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(page__isnull=False) & models.Q(url=""))
                | (models.Q(page__isnull=True) & ~models.Q(url="")),
                name="cms_navigationitem_single_target",
                violation_error_message="Choose exactly one target: a page or a URL.",
            )
        ]

    def __str__(self) -> str:
        return f"{self.menu.key}: {self.label}"

    def clean(self) -> None:
        errors = _check_single_target(self.page, self.url, "url")
        if self.parent is not None:
            if self.parent.menu_id != self.menu_id:
                errors["parent"] = "The parent must belong to the same menu."
            elif self.parent.parent_id is not None or (
                self.pk is not None and self.parent.pk == self.pk
            ):
                errors["parent"] = "Only one level of nesting is supported."
            elif self.pk is not None and self.children.exists():
                errors["parent"] = "An item with children cannot become a child."
        if errors:
            raise ValidationError(errors)


class SingletonModel(models.Model):
    """Exactly one row (pk=1), created lazily by `load()`."""

    SINGLETON_PK = 1

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.pk = self.SINGLETON_PK
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> Any:
        obj, _ = cls._default_manager.get_or_create(pk=cls.SINGLETON_PK)
        return obj

    @classmethod
    def current(cls) -> Any:
        """Read-only access for public endpoints: never writes, unsaved defaults if absent."""
        return cls._default_manager.filter(pk=cls.SINGLETON_PK).first() or cls()


class SiteSettings(SingletonModel):
    """Company data shown on the public site.

    Every field starts empty. Only values confirmed by the client Source of Truth may be
    entered (legal name, brand, VAT, operational address, phone, certifications); e-mail,
    opening hours, tagline etc. are DA DEFINIRE and must stay empty until confirmed.
    """

    legal_name = models.CharField(max_length=200, blank=True, validators=[validate_plain_text])
    brand_name = models.CharField(max_length=100, blank=True, validators=[validate_plain_text])
    vat_number = models.CharField(max_length=13, blank=True, validators=[validate_vat_number])
    address = models.CharField(max_length=300, blank=True, validators=[validate_plain_text])
    phone = models.CharField(max_length=20, blank=True, validators=[validate_phone])
    email = models.EmailField(blank=True)
    opening_hours = models.CharField(
        max_length=300, blank=True, validators=[validate_multiline_plain_text]
    )
    tagline = models.CharField(max_length=200, blank=True, validators=[validate_plain_text])
    certifications_text = models.CharField(
        max_length=500, blank=True, validators=[validate_multiline_plain_text]
    )
    primary_cta_label = models.CharField(
        max_length=40, blank=True, validators=[validate_plain_text]
    )
    primary_cta_page = models.ForeignKey(
        Page, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    primary_cta_url = models.CharField(max_length=500, blank=True, validators=[validate_safe_url])
    footer_text = models.CharField(
        max_length=1000, blank=True, validators=[validate_multiline_plain_text]
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="cms_sitesettings_singleton")
        ]

    def __str__(self) -> str:
        return "Site settings"

    def clean(self) -> None:
        has_target = self.primary_cta_page is not None or bool(self.primary_cta_url)
        if self.primary_cta_label or has_target:
            errors = _check_single_target(
                self.primary_cta_page, self.primary_cta_url, "primary_cta_url"
            )
            if not self.primary_cta_label:
                errors["primary_cta_label"] = "A label is required when a target is set."
            if errors:
                raise ValidationError(errors)


class SEOSettings(SingletonModel):
    """Site-wide SEO defaults; pages override them field by field."""

    default_title = models.CharField(max_length=70, blank=True, validators=[validate_plain_text])
    default_description = models.CharField(
        max_length=300, blank=True, validators=[validate_multiline_plain_text]
    )
    default_og_image = models.ForeignKey(
        MediaAsset, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    allow_indexing = models.BooleanField(
        default=False,
        help_text="Off until launch: public pages are served with noindex.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SEO settings"
        verbose_name_plural = "SEO settings"
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="cms_seosettings_singleton")
        ]

    def __str__(self) -> str:
        return "SEO settings"

    def clean(self) -> None:
        validate_changed_public_media(self, "default_og_image")
