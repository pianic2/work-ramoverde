"""Technical admin panel. Model clean()/save() run the same validation as the API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.http import HttpRequest

from .models import (
    NavigationItem,
    NavigationMenu,
    Page,
    PageSection,
    SEOSettings,
    SiteSettings,
)

if TYPE_CHECKING:
    _PageAdmin = admin.ModelAdmin[Page]
    _MenuAdmin = admin.ModelAdmin[NavigationMenu]
    _SingletonAdmin = admin.ModelAdmin[Any]
    _SectionInline = admin.StackedInline[PageSection, Page]
    _ItemInline = admin.TabularInline[NavigationItem, NavigationMenu]
else:
    _PageAdmin = _MenuAdmin = _SingletonAdmin = admin.ModelAdmin
    _SectionInline = admin.StackedInline
    _ItemInline = admin.TabularInline


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


class NavigationItemInline(_ItemInline):
    model = NavigationItem
    fk_name = "menu"
    extra = 0
    ordering = ["position", "id"]
    fields = ["label", "page", "url", "parent", "position", "visible"]


@admin.register(NavigationMenu)
class NavigationMenuAdmin(_MenuAdmin):
    list_display = ["key", "title", "updated_at"]
    inlines = [NavigationItemInline]


class SingletonAdmin(_SingletonAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return not self.model._default_manager.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(SiteSettings)
class SiteSettingsAdmin(SingletonAdmin):
    raw_id_fields = ["primary_cta_page"]


@admin.register(SEOSettings)
class SEOSettingsAdmin(SingletonAdmin):
    raw_id_fields = ["default_og_image"]
