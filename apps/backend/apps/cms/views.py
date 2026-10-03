from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError, QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStaffUser, StaffModelPermissions
from apps.media.parsers import SafeJSONParser

from . import services
from .models import NavigationItem, NavigationMenu, Page, PageSection, SEOSettings, SiteSettings
from .sections import LATEST_VERSIONS, SECTION_SCHEMAS
from .serializers import (
    NavigationItemSerializer,
    NavigationMenuSerializer,
    PageSectionSerializer,
    PageSerializer,
    PublicNavigationSerializer,
    PublicPageSerializer,
    PublicSiteSettingsSerializer,
    SectionOrderSerializer,
    SectionSchemaSerializer,
    SEOSettingsSerializer,
    SiteSettingsSerializer,
)

PUBLISH_PERMISSION = "cms.publish_page"
PAGE_PK_PARAMETER = OpenApiParameter("page_pk", int, OpenApiParameter.PATH)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The resource is still referenced and cannot be deleted."
    default_code = "conflict"


class StaffCrudViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet[Any],
):
    """CRUD without PUT; staff + Django model permissions (view perm required for reads)."""

    permission_classes = [StaffModelPermissions]
    parser_classes = [SafeJSONParser]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def perform_destroy(self, instance: Any) -> None:
        try:
            instance.delete()
        except ProtectedError as exc:
            raise Conflict() from exc


@extend_schema_view(
    list=extend_schema(operation_id="listCmsPages"),
    retrieve=extend_schema(operation_id="getCmsPage"),
    create=extend_schema(operation_id="createCmsPage"),
    partial_update=extend_schema(operation_id="updateCmsPage"),
    destroy=extend_schema(operation_id="deleteCmsPage"),
)
class PageViewSet(StaffCrudViewSet):
    """Staff page management. Drafts are visible here; changing `status` needs publish rights."""

    queryset = Page.objects.select_related("og_image")
    serializer_class = PageSerializer

    def _check_status_change(self, serializer: PageSerializer) -> None:
        current = serializer.instance.status if serializer.instance else Page.Status.DRAFT
        requested = serializer.validated_data.get("status", current)
        if requested != current and not self.request.user.has_perm(PUBLISH_PERMISSION):
            raise PermissionDenied("Changing the publication status requires publish rights.")

    def perform_create(self, serializer: PageSerializer) -> None:  # type: ignore[override]
        self._check_status_change(serializer)
        serializer.save()

    def perform_update(self, serializer: PageSerializer) -> None:  # type: ignore[override]
        self._check_status_change(serializer)
        serializer.save()


@extend_schema_view(
    list=extend_schema(operation_id="listCmsPageSections"),
    retrieve=extend_schema(operation_id="getCmsPageSection"),
    create=extend_schema(operation_id="createCmsPageSection"),
    partial_update=extend_schema(operation_id="updateCmsPageSection"),
    destroy=extend_schema(operation_id="deleteCmsPageSection"),
)
@extend_schema(parameters=[PAGE_PK_PARAMETER])
class PageSectionViewSet(StaffCrudViewSet):
    """Ordered sections of one page. New sections are appended; use `order` to reorder."""

    serializer_class = PageSectionSerializer
    pagination_class = None
    page: Page

    def get_queryset(self) -> QuerySet[PageSection]:
        return PageSection.objects.filter(page_id=int(self.kwargs.get("page_pk", 0))).order_by(
            "position", "id"
        )

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)  # authentication + permissions first
        self.page = get_object_or_404(Page, pk=kwargs["page_pk"])

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        if hasattr(self, "page"):
            context["page"] = self.page
        return context

    def perform_create(self, serializer: PageSectionSerializer) -> None:  # type: ignore[override]
        try:
            serializer.instance = services.create_section(self.page, **serializer.validated_data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc

    def perform_destroy(self, instance: PageSection) -> None:
        services.delete_section(instance)


class PageSectionOrderView(generics.GenericAPIView[PageSection]):
    """Replace the section order of a page (staff + `cms.change_pagesection`)."""

    permission_classes = [StaffModelPermissions]
    parser_classes = [SafeJSONParser]
    pagination_class = None
    queryset = PageSection.objects.all()
    serializer_class = SectionOrderSerializer

    @extend_schema(
        operation_id="reorderCmsPageSections",
        request=SectionOrderSerializer,
        responses=PageSectionSerializer(many=True),
    )
    def put(self, request: Request, page_pk: int) -> Response:
        """`section_ids` must list every section of the page exactly once."""
        page = get_object_or_404(Page, pk=page_pk)
        payload = SectionOrderSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            ordered = services.reorder_sections(page, payload.validated_data["section_ids"])
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        return Response(PageSectionSerializer(ordered, many=True).data)


class SectionSchemaListView(APIView):
    """Catalogue of section types, versions, variants and content fields (for editor UIs)."""

    permission_classes = [IsStaffUser]

    @extend_schema(
        operation_id="listCmsSectionSchemas", responses=SectionSchemaSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        data = []
        for schema in SECTION_SCHEMAS.values():
            described = schema.describe()
            data.append(
                {
                    "type": schema.type,
                    "schema_version": schema.version,
                    "latest": LATEST_VERSIONS[schema.type] == schema.version,
                    "variants": described["variants"],
                    "content_fields": described["fields"],
                }
            )
        return Response(SectionSchemaSerializer(data, many=True).data)


@extend_schema_view(get=extend_schema(operation_id="getPublicPage"))
class PublicPageView(generics.RetrieveAPIView[Page]):
    """Published page by slug with its enabled sections. Drafts and archived pages are 404."""

    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = PublicPageSerializer
    lookup_field = "slug"

    def get_queryset(self) -> QuerySet[Page]:
        return Page.objects.filter(status=Page.Status.PUBLISHED).select_related("og_image")


MENU_PK_PARAMETER = OpenApiParameter("menu_pk", int, OpenApiParameter.PATH)


@extend_schema_view(
    list=extend_schema(operation_id="listCmsNavigationMenus"),
    retrieve=extend_schema(operation_id="getCmsNavigationMenu"),
    create=extend_schema(operation_id="createCmsNavigationMenu"),
    partial_update=extend_schema(operation_id="updateCmsNavigationMenu"),
    destroy=extend_schema(operation_id="deleteCmsNavigationMenu"),
)
class NavigationMenuViewSet(StaffCrudViewSet):
    """Navigation menus (header, footer...) with their items."""

    queryset = NavigationMenu.objects.prefetch_related("items")
    serializer_class = NavigationMenuSerializer


@extend_schema_view(
    list=extend_schema(operation_id="listCmsNavigationItems"),
    retrieve=extend_schema(operation_id="getCmsNavigationItem"),
    create=extend_schema(operation_id="createCmsNavigationItem"),
    partial_update=extend_schema(operation_id="updateCmsNavigationItem"),
    destroy=extend_schema(operation_id="deleteCmsNavigationItem"),
)
@extend_schema(parameters=[MENU_PK_PARAMETER])
class NavigationItemViewSet(StaffCrudViewSet):
    """Items of one menu, ordered by `position`; `parent` allows one level of nesting."""

    serializer_class = NavigationItemSerializer
    pagination_class = None
    menu: NavigationMenu

    def get_queryset(self) -> QuerySet[NavigationItem]:
        return NavigationItem.objects.filter(menu_id=int(self.kwargs.get("menu_pk", 0))).order_by(
            "position", "id"
        )

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)  # authentication + permissions first
        self.menu = get_object_or_404(NavigationMenu, pk=kwargs["menu_pk"])

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        if hasattr(self, "menu"):
            context["menu"] = self.menu
        return context

    def perform_create(self, serializer: NavigationItemSerializer) -> None:  # type: ignore[override]
        serializer.save(menu=self.menu)


class SingletonSettingsView(generics.GenericAPIView[Any]):
    """GET / PATCH of a singleton settings row (staff + view/change model permission)."""

    permission_classes = [StaffModelPermissions]
    parser_classes = [SafeJSONParser]
    pagination_class = None

    def get_object(self) -> Any:
        model = self.get_queryset().model
        return model.load()

    def get(self, request: Request) -> Response:
        return Response(self.get_serializer(self.get_object()).data)

    def patch(self, request: Request) -> Response:
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


@extend_schema_view(
    get=extend_schema(operation_id="getCmsSiteSettings"),
    patch=extend_schema(operation_id="updateCmsSiteSettings"),
)
class SiteSettingsView(SingletonSettingsView):
    queryset = SiteSettings.objects.all()
    serializer_class = SiteSettingsSerializer


@extend_schema_view(
    get=extend_schema(operation_id="getCmsSeoSettings"),
    patch=extend_schema(operation_id="updateCmsSeoSettings"),
)
class SEOSettingsView(SingletonSettingsView):
    queryset = SEOSettings.objects.all()
    serializer_class = SEOSettingsSerializer


class PublicNavigationView(APIView):
    """Visible items of a menu whose targets are published pages or safe URLs."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(operation_id="getPublicNavigation", responses=PublicNavigationSerializer)
    def get(self, request: Request, key: str) -> Response:
        menu = get_object_or_404(NavigationMenu, key=key)
        return Response(PublicNavigationSerializer(services.public_navigation(menu)).data)


class PublicSiteSettingsView(APIView):
    """Public company data and SEO defaults. Unconfirmed values are null."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(operation_id="getPublicSiteSettings", responses=PublicSiteSettingsSerializer)
    def get(self, request: Request) -> Response:
        return Response(PublicSiteSettingsSerializer(services.public_site_settings()).data)
