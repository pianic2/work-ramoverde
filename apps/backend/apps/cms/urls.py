from django.urls import URLPattern, URLResolver, path
from rest_framework.routers import SimpleRouter

from .views import (
    NavigationItemViewSet,
    NavigationMenuViewSet,
    PageSectionOrderView,
    PageSectionViewSet,
    PageViewSet,
    PublicNavigationView,
    PublicPageView,
    PublicSiteSettingsView,
    SectionSchemaListView,
    SEOSettingsView,
    SiteSettingsView,
)

router = SimpleRouter(trailing_slash=False)
router.register("cms/pages", PageViewSet, basename="cms-page")
router.register(
    r"cms/pages/(?P<page_pk>\d+)/sections", PageSectionViewSet, basename="cms-page-section"
)
router.register("cms/navigation-menus", NavigationMenuViewSet, basename="cms-navigation-menu")
router.register(
    r"cms/navigation-menus/(?P<menu_pk>\d+)/items",
    NavigationItemViewSet,
    basename="cms-navigation-item",
)

urlpatterns: list[URLPattern | URLResolver] = [
    path("cms/section-schemas", SectionSchemaListView.as_view(), name="cms-section-schemas"),
    path(
        "cms/pages/<int:page_pk>/sections/order",
        PageSectionOrderView.as_view(),
        name="cms-page-sections-order",
    ),
    path("cms/site-settings", SiteSettingsView.as_view(), name="cms-site-settings"),
    path("cms/seo-settings", SEOSettingsView.as_view(), name="cms-seo-settings"),
    path("public/navigation/<slug:key>", PublicNavigationView.as_view(), name="public-navigation"),
    path("public/site-settings", PublicSiteSettingsView.as_view(), name="public-site-settings"),
    path("public/pages/<slug:slug>", PublicPageView.as_view(), name="public-page"),
    *router.urls,
]
