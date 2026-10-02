"""Technical admin panel. Model clean()/save() run the same validation as the API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.http import HttpRequest

from .models import Page, PageSection

if TYPE_CHECKING:
    _PageAdmin = admin.ModelAdmin[Page]
    _SectionInline = admin.StackedInline[PageSection, Page]
else:
    _PageAdmin = admin.ModelAdmin
    _SectionInline = admin.StackedInline


class PageSectionInline(_SectionInline):
    model = PageSection
    extra = 0
    ordering = ["position", "id"]
    fields = ["type", "variant", "position", "enabled", "schema_version", "content"]


@admin.register(Page)
class PageAdmin(_PageAdmin):
    list_display = ["title", "slug", "status", "published_at", "updated_at"]
    list_filter = ["status"]
    search_fields = ["title", "slug"]
    prepopulated_fields = {"slug": ["title"]}
    readonly_fields = ["published_at", "created_at", "updated_at"]
    raw_id_fields = ["og_image"]
    inlines = [PageSectionInline]

    def get_readonly_fields(self, request: HttpRequest, obj: Page | None = None) -> list[str]:
        readonly = list(self.readonly_fields)
        if not request.user.has_perm("cms.publish_page"):
            readonly.append("status")
        return readonly
