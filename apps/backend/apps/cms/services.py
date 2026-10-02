"""CMS write operations that span several rows (positions, publication checks)."""

from collections.abc import Iterable, Sequence
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from apps.media.models import MediaAsset
from apps.media.services import public_url

from .models import Page, PageSection
from .sections import media_ids, public_content


def _lock_page(page: Page) -> Page:
    return Page.objects.select_for_update().get(pk=page.pk)


def _rewrite_positions(sections: Sequence[PageSection]) -> None:
    """Assign positions 0..n-1 in the given order without tripping the unique constraint."""
    offset = max((s.position for s in sections), default=0) + len(sections) + 1
    for index, section in enumerate(sections):
        section.position = offset + index
    PageSection.objects.bulk_update(sections, ["position"])
    for index, section in enumerate(sections):
        section.position = index
    PageSection.objects.bulk_update(sections, ["position"])


@transaction.atomic
def create_section(page: Page, **fields: Any) -> PageSection:
    page = _lock_page(page)
    last = page.sections.aggregate(last=Max("position"))["last"]
    fields.setdefault("schema_version", PageSection.latest_version(fields.get("type", "")))
    section = PageSection(page=page, position=0 if last is None else last + 1, **fields)
    section.full_clean(exclude=["page"])
    section.save()
    return section


@transaction.atomic
def delete_section(section: PageSection) -> None:
    page = _lock_page(section.page)
    section.delete()
    _rewrite_positions(list(page.sections.order_by("position", "id")))


@transaction.atomic
def reorder_sections(page: Page, section_ids: Sequence[int]) -> list[PageSection]:
    page = _lock_page(page)
    sections = {s.pk: s for s in page.sections.all()}
    if len(set(section_ids)) != len(section_ids) or set(section_ids) != set(sections):
        raise ValidationError(
            {"section_ids": ["Provide every section id of this page exactly once."]}
        )
    ordered = [sections[pk] for pk in section_ids]
    _rewrite_positions(ordered)
    return ordered


def _referenced_media(sections: Iterable[PageSection]) -> set[int]:
    ids: set[int] = set()
    for section in sections:
        ids |= media_ids(section.type, section.schema_version, section.content)
    return ids


def publication_errors(page: Page) -> list[str]:
    """Reasons why `page` cannot be served publicly (unapproved/non-public media)."""
    sections = list(page.sections.filter(enabled=True))
    ids = _referenced_media(sections)
    if page.og_image_id:
        ids.add(page.og_image_id)
    usable = set(MediaAsset.publicly_usable().filter(pk__in=ids).values_list("pk", flat=True))
    missing = sorted(ids - usable)
    if missing:
        return [
            "Every referenced media asset must be PUBLIC and approved before publishing "
            f"(not approved: {', '.join(map(str, missing))})."
        ]
    return []


def public_media(asset: MediaAsset | None) -> dict[str, Any] | None:
    if asset is None or not asset.is_publicly_usable:
        return None
    url = public_url(asset)
    if url is None:
        return None
    return {
        "id": asset.pk,
        "url": url,
        "mime_type": asset.mime_type,
        "width": asset.width,
        "height": asset.height,
        "alt_text": asset.alt_text,
    }


def public_sections(page: Page) -> list[dict[str, Any]]:
    """Enabled sections in order, media references resolved to public URLs."""
    sections = list(page.sections.filter(enabled=True).order_by("position", "id"))
    assets = MediaAsset.publicly_usable().in_bulk(_referenced_media(sections))

    def resolve(asset_id: int) -> dict[str, Any] | None:
        return public_media(assets.get(asset_id))

    return [
        {
            "id": section.pk,
            "type": section.type,
            "variant": section.variant,
            "schema_version": section.schema_version,
            "content": public_content(
                section.type, section.schema_version, section.content, resolve
            ),
        }
        for section in sections
    ]


def page_seo(page: Page) -> dict[str, Any]:
    return {
        "title": page.seo_title or page.title,
        "description": page.seo_description,
        "canonical_url": page.canonical_url or None,
        "noindex": page.noindex,
        "og_image": public_media(page.og_image),
    }
