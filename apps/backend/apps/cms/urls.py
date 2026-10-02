from django.urls import URLPattern, URLResolver, path
from rest_framework.routers import SimpleRouter

from .views import (
    PageSectionOrderView,
    PageSectionViewSet,
    PageViewSet,
    PublicPageView,
    SectionSchemaListView,
)

router = SimpleRouter(trailing_slash=False)
router.register("cms/pages", PageViewSet, basename="cms-page")
router.register(
    r"cms/pages/(?P<page_pk>\d+)/sections", PageSectionViewSet, basename="cms-page-section"
)

urlpatterns: list[URLPattern | URLResolver] = [
    path("cms/section-schemas", SectionSchemaListView.as_view(), name="cms-section-schemas"),
    path(
        "cms/pages/<int:page_pk>/sections/order",
        PageSectionOrderView.as_view(),
        name="cms-page-sections-order",
    ),
    path("public/pages/<slug:slug>", PublicPageView.as_view(), name="public-page"),
    *router.urls,
]
