from django.urls import URLPattern, URLResolver, path
from rest_framework.routers import SimpleRouter

from .views import MediaAssetViewSet, PublicMediaAssetListView

router = SimpleRouter(trailing_slash=False)
router.register("media/assets", MediaAssetViewSet, basename="media-asset")

urlpatterns: list[URLPattern | URLResolver] = [
    path("public/media-assets", PublicMediaAssetListView.as_view(), name="public-media-assets"),
    *router.urls,
]
