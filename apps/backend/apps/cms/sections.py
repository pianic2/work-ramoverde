"""Versioned section schema registry and dependency-free content validator.

Each (section type, schema_version) pair declares the allowed variants and a strict
content schema. Validation rejects unknown keys, wrong types, over-long strings, unsafe
URLs and any markup: section content is plain data, never HTML/JS/CSS.

To evolve a section, add a new (type, version + 1) entry and bump LATEST_VERSIONS; old
rows keep validating against the version they were written with.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.db import models

from apps.media.models import MediaAsset
from apps.media.validators import plain_text_error

Errors = dict[str, list[str]]
MediaResolver = Callable[[int], Any]


class SectionType(models.TextChoices):
    HERO = "hero", "Hero"
    SERVICES = "services", "Services"
    PROJECTS = "projects", "Projects"
    GALLERY = "gallery", "Gallery"
    TEXT_MEDIA = "text-media", "Text + media"
    STATS = "stats", "Stats"
    CERTIFICATIONS = "certifications", "Certifications"
    CTA = "cta", "Call to action"
    CONTACT = "contact", "Contact"
    TERRITORY = "territory", "Territory"


# --- URL policy -------------------------------------------------------------------------

_URL_MAX = 500


def url_error(value: str) -> str | None:
    """Allowed: site-relative paths ("/x"), anchors ("#x"), https URLs, tel: and mailto:."""
    if value != value.strip() or any(ch.isspace() for ch in value) or "\\" in value:
        return "URLs may not contain whitespace or backslashes."
    if plain_text_error(value):
        return "Unsafe URL."
    if value.startswith("//"):
        return "Protocol-relative URLs are not allowed."
    if value.startswith(("/", "#")):
        return None
    lowered = value.lower()
    if lowered.startswith("tel:"):
        return (
            None
            if len(value) > 4 and all(c in "+0123456789" for c in value[4:])
            else ("Invalid phone link.")
        )
    if lowered.startswith("mailto:"):
        return None if "@" in value else "Invalid e-mail link."
    parts = urlsplit(value)
    if parts.scheme == "https" and parts.netloc:
        return None
    return "Only https://, site-relative (/...), #anchor, tel: and mailto: URLs are allowed."


# --- field specs ------------------------------------------------------------------------


@dataclass(frozen=True)
class Context:
    errors: Errors
    media_refs: dict[str, int]  # path -> MediaAsset id, checked in one query afterwards

    def add(self, path: str, message: str) -> None:
        self.errors.setdefault(path, []).append(message)


class Spec:
    kind = "abstract"
    required = False

    def clean(self, value: Any, path: str, ctx: Context) -> Any:
        raise NotImplementedError

    def public(self, value: Any, resolve: MediaResolver) -> Any:
        return value

    def describe(self) -> dict[str, Any]:
        return {"kind": self.kind, "required": self.required}


@dataclass(frozen=True)
class Text(Spec):
    max_length: int
    required: bool = False
    multiline: bool = False
    kind = "text"

    def clean(self, value: Any, path: str, ctx: Context) -> Any:
        if not isinstance(value, str):
            ctx.add(path, "Must be a string.")
            return value
        if self.required and not value.strip():
            ctx.add(path, "This field may not be blank.")
        if len(value) > self.max_length:
            ctx.add(path, f"At most {self.max_length} characters.")
        message = plain_text_error(value, multiline=self.multiline)
        if message:
            ctx.add(path, message)
        return value

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "max_length": self.max_length, "multiline": self.multiline}


@dataclass(frozen=True)
class Url(Spec):
    required: bool = False
    kind = "url"

    def clean(self, value: Any, path: str, ctx: Context) -> Any:
        if not isinstance(value, str) or not value:
            ctx.add(path, "Must be a non-empty string.")
            return value
        if len(value) > _URL_MAX:
            ctx.add(path, f"At most {_URL_MAX} characters.")
        message = url_error(value)
        if message:
            ctx.add(path, message)
        return value


@dataclass(frozen=True)
class Boolean(Spec):
    required: bool = False
    kind = "boolean"

    def clean(self, value: Any, path: str, ctx: Context) -> Any:
        if not isinstance(value, bool):
            ctx.add(path, "Must be a boolean.")
        return value


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


@dataclass(frozen=True)
class Media(Spec):
    """Reference to a MediaAsset id. It must exist and be PUBLIC (and not REJECTED)."""

    required: bool = False
    kind = "media"

    def clean(self, value: Any, path: str, ctx: Context) -> Any:
        if not _is_positive_int(value):
            ctx.add(path, "Must be a media asset id.")
        else:
            ctx.media_refs[path] = value
        return value

    def public(self, value: Any, resolve: MediaResolver) -> Any:
        return resolve(value)


@dataclass(frozen=True)
class IdList(Spec):
    """Ordered ids of another module's records (services, projects, certifications).

    Those modules do not exist yet; ids are validated structurally only and resolved by
    the public API once the modules land.
    """

    target: str
    max_items: int
    required: bool = False
    kind = "id_list"

    def clean(self, value: Any, path: str, ctx: Context) -> Any:
        if not isinstance(value, list) or not all(_is_positive_int(item) for item in value):
            ctx.add(path, "Must be a list of positive integer ids.")
            return value
        if len(set(value)) != len(value):
            ctx.add(path, "Ids must be unique.")
        if len(value) > self.max_items:
            ctx.add(path, f"At most {self.max_items} items.")
        return value

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "target": self.target, "max_items": self.max_items}


@dataclass(frozen=True)
class Object(Spec):
    fields: Mapping[str, Spec]
    required: bool = False
    kind = "object"

    def clean(self, value: Any, path: str, ctx: Context) -> Any:
        if not isinstance(value, dict):
            ctx.add(path, "Must be an object.")
            return value
        for key in value:
            if key not in self.fields:
                ctx.add(f"{path}.{key}", "Unknown field.")
        for key, spec in self.fields.items():
            if key in value:
                spec.clean(value[key], f"{path}.{key}", ctx)
            elif spec.required:
                ctx.add(f"{path}.{key}", "This field is required.")
        return value

    def public(self, value: Any, resolve: MediaResolver) -> Any:
        return {key: self.fields[key].public(item, resolve) for key, item in value.items()}

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "fields": {key: spec.describe() for key, spec in self.fields.items()},
        }


@dataclass(frozen=True)
class ListOf(Spec):
    item: Spec
    max_items: int
    min_items: int = 0
    required: bool = False
    kind = "list"

    def clean(self, value: Any, path: str, ctx: Context) -> Any:
        if not isinstance(value, list):
            ctx.add(path, "Must be a list.")
            return value
        if not self.min_items <= len(value) <= self.max_items:
            ctx.add(path, f"Between {self.min_items} and {self.max_items} items.")
        for index, item in enumerate(value):
            self.item.clean(item, f"{path}[{index}]", ctx)
        return value

    def public(self, value: Any, resolve: MediaResolver) -> Any:
        result = []
        for item in value:
            public_item = self.item.public(item, resolve)
            # Drop entries whose required media is no longer publishable.
            if isinstance(self.item, Object) and any(
                spec.required and isinstance(spec, Media) and public_item.get(key) is None
                for key, spec in self.item.fields.items()
            ):
                continue
            result.append(public_item)
        return result

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "item": self.item.describe(),
            "min_items": self.min_items,
            "max_items": self.max_items,
        }


# --- registry ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionSchema:
    type: str
    version: int
    variants: tuple[str, ...]
    content: Object = field(repr=False)

    def describe(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "schema_version": self.version,
            "variants": list(self.variants),
            "fields": self.content.describe()["fields"],
        }


HEADING = Text(120)
REQUIRED_HEADING = Text(120, required=True)
INTRO = Text(600, multiline=True)
LINK = Object({"label": Text(40, required=True), "href": Url(required=True)})

_SCHEMAS = [
    SectionSchema(
        "hero",
        1,
        ("split", "image-background", "minimal"),
        Object(
            {
                "eyebrow": Text(60),
                "heading": REQUIRED_HEADING,
                "subheading": Text(300, multiline=True),
                "image": Media(),
                "primary_cta": LINK,
                "secondary_cta": LINK,
            }
        ),
    ),
    SectionSchema(
        "services",
        1,
        ("grid", "list"),
        Object(
            {
                "heading": HEADING,
                "intro": INTRO,
                "service_ids": IdList("services.Service", 24),
                "cta": LINK,
            }
        ),
    ),
    SectionSchema(
        "projects",
        1,
        ("grid", "carousel"),
        Object(
            {
                "heading": HEADING,
                "intro": INTRO,
                "project_ids": IdList("projects.Project", 24),
                "cta": LINK,
            }
        ),
    ),
    SectionSchema(
        "gallery",
        1,
        ("grid", "masonry", "carousel"),
        Object(
            {
                "heading": HEADING,
                "intro": INTRO,
                "items": ListOf(
                    Object({"media": Media(required=True), "caption": Text(200)}),
                    max_items=48,
                    min_items=1,
                    required=True,
                ),
            }
        ),
    ),
    SectionSchema(
        "text-media",
        1,
        ("media-left", "media-right", "text-only"),
        Object(
            {
                "heading": HEADING,
                "body": Text(5000, required=True, multiline=True),
                "media": Media(),
                "cta": LINK,
            }
        ),
    ),
    SectionSchema(
        "stats",
        1,
        ("row", "grid"),
        Object(
            {
                "heading": HEADING,
                "items": ListOf(
                    Object({"value": Text(20, required=True), "label": Text(80, required=True)}),
                    max_items=8,
                    min_items=1,
                    required=True,
                ),
            }
        ),
    ),
    SectionSchema(
        "certifications",
        1,
        ("badges", "list"),
        Object(
            {
                "heading": HEADING,
                "intro": INTRO,
                "certification_ids": IdList("certifications.Certification", 12),
            }
        ),
    ),
    SectionSchema(
        "cta",
        1,
        ("banner", "card"),
        Object({"heading": REQUIRED_HEADING, "body": Text(400, multiline=True), "cta": LINK}),
    ),
    SectionSchema(
        "contact",
        1,
        ("form", "details", "form-and-details"),
        Object(
            {
                "heading": HEADING,
                "intro": INTRO,
                # Contact data itself comes from SiteSettings; the section only toggles it.
                "show_phone": Boolean(),
                "show_address": Boolean(),
                "show_form": Boolean(),
            }
        ),
    ),
    SectionSchema(
        "territory",
        1,
        ("map", "list"),
        Object(
            {
                "heading": HEADING,
                "intro": INTRO,
                "areas": ListOf(Text(80, required=True), max_items=40),
                "image": Media(),
            }
        ),
    ),
]

SECTION_SCHEMAS: dict[tuple[str, int], SectionSchema] = {
    (schema.type, schema.version): schema for schema in _SCHEMAS
}
LATEST_VERSIONS: dict[str, int] = {}
for _schema in _SCHEMAS:
    LATEST_VERSIONS[_schema.type] = max(LATEST_VERSIONS.get(_schema.type, 0), _schema.version)
assert set(LATEST_VERSIONS) == set(SectionType.values), "registry must cover every SectionType"


def get_schema(section_type: str, version: int) -> SectionSchema | None:
    return SECTION_SCHEMAS.get((section_type, version))


def _check_media(refs: dict[str, int], ctx: Context) -> None:
    if not refs:
        return
    assets = MediaAsset.objects.in_bulk(set(refs.values()))
    for path, asset_id in refs.items():
        asset = assets.get(asset_id)
        if asset is None:
            ctx.add(path, "Media asset not found.")
        elif asset.visibility != MediaAsset.Visibility.PUBLIC:
            ctx.add(path, "Only PUBLIC media assets can be used in page content.")
        elif asset.authorization_status == MediaAsset.AuthorizationStatus.REJECTED:
            ctx.add(path, "This media asset was rejected for publication.")


def validate_section(section_type: str, version: int, variant: str, content: Any) -> Any:
    """Validate a section; return the content unchanged or raise a Django ValidationError."""
    if section_type not in LATEST_VERSIONS:
        raise ValidationError({"type": [f"Unknown section type {section_type!r}."]})
    schema = get_schema(section_type, version)
    if schema is None:
        raise ValidationError(
            {"schema_version": [f"Unknown schema version {version} for {section_type!r}."]}
        )
    if variant not in schema.variants:
        raise ValidationError({"variant": [f"Allowed variants: {', '.join(schema.variants)}."]})
    ctx = Context(errors={}, media_refs={})
    schema.content.clean(content, "content", ctx)
    if not ctx.errors:
        _check_media(ctx.media_refs, ctx)
    if ctx.errors:
        messages = [f"{path}: {msg}" for path, msgs in ctx.errors.items() for msg in msgs]
        raise ValidationError({"content": messages})
    return content


def media_ids(section_type: str, version: int, content: Any) -> set[int]:
    """All MediaAsset ids referenced by a (valid) section content."""
    schema = get_schema(section_type, version)
    if schema is None:
        return set()
    ctx = Context(errors={}, media_refs={})
    schema.content.clean(content, "content", ctx)
    return set(ctx.media_refs.values())


def public_content(section_type: str, version: int, content: Any, resolve: MediaResolver) -> Any:
    schema = get_schema(section_type, version)
    if schema is None or not isinstance(content, dict):
        return {}
    return schema.content.public(content, resolve)
