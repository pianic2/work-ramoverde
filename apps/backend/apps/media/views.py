from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError, QuerySet
from django.http import FileResponse, HttpResponseBase, HttpResponseRedirect
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import StaffModelPermissions

from . import services
from .models import MediaAsset
from .serializers import (
    MediaAssetSerializer,
    MediaAssetUpdateSerializer,
    MediaAssetUploadSerializer,
    PublicMediaAssetSerializer,
)

APPROVE_PERMISSION = "media.approve_mediaasset"
DOWNLOAD_PRIVATE_PERMISSION = "media.download_private_mediaasset"


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The resource is still referenced and cannot be deleted."
    default_code = "conflict"


def as_drf_validation_error(exc: DjangoValidationError) -> ValidationError:
    if hasattr(exc, "error_dict"):
        return ValidationError(exc.message_dict)
    return ValidationError({"file": exc.messages})


@extend_schema_view(
    list=extend_schema(operation_id="listMediaAssets"),
    retrieve=extend_schema(operation_id="getMediaAsset"),
    create=extend_schema(
        operation_id="createMediaAsset",
        request={"multipart/form-data": MediaAssetUploadSerializer},
        responses={201: MediaAssetSerializer},
    ),
    partial_update=extend_schema(
        operation_id="updateMediaAsset",
        request={"application/json": MediaAssetUpdateSerializer},
        responses=MediaAssetSerializer,
    ),
    destroy=extend_schema(operation_id="deleteMediaAsset"),
)
class MediaAssetViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet[MediaAsset],
):
    """Staff media library. Requires staff + `media.<action>_mediaasset` permissions."""

    queryset = MediaAsset.objects.select_related("uploaded_by")
    serializer_class = MediaAssetSerializer
    permission_classes = [StaffModelPermissions]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        upload = MediaAssetUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        data = upload.validated_data
        try:
            asset = services.create_asset(
                upload=data["file"],
                uploaded_by=request.user,
                visibility=data["visibility"],
                alt_text=data.get("alt_text", ""),
                caption=data.get("caption", ""),
                origin=data["origin"],
                source_note=data.get("source_note", ""),
            )
        except DjangoValidationError as exc:
            raise as_drf_validation_error(exc) from exc
        return Response(MediaAssetSerializer(asset).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        asset = self.get_object()
        serializer = MediaAssetUpdateSerializer(asset, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        changes = dict(serializer.validated_data)
        new_status = changes.get("authorization_status", asset.authorization_status)
        if new_status != asset.authorization_status and not request.user.has_perm(
            APPROVE_PERMISSION
        ):
            raise PermissionDenied("Changing the authorization status requires approval rights.")
        try:
            asset = services.update_asset(asset, **changes)
        except DjangoValidationError as exc:
            raise as_drf_validation_error(exc) from exc
        return Response(MediaAssetSerializer(asset).data)

    def perform_destroy(self, instance: MediaAsset) -> None:
        try:
            services.delete_asset(instance)
        except ProtectedError as exc:
            raise Conflict() from exc

    @extend_schema(
        operation_id="downloadMediaAsset",
        responses={
            (200, "application/octet-stream"): OpenApiTypes.BINARY,
            302: OpenApiResponse(description="Redirect to a short-lived signed URL (S3/R2)."),
        },
    )
    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request: Request, pk: str | None = None) -> HttpResponseBase:
        """Download the blob as an attachment. Non-public blobs need the download permission."""
        asset = self.get_object()
        if not asset.stored_publicly and not request.user.has_perm(DOWNLOAD_PRIVATE_PERMISSION):
            raise PermissionDenied("Downloading private media requires a dedicated permission.")
        response: HttpResponseBase
        signed_url = services.private_download_url(asset)
        if signed_url:
            response = HttpResponseRedirect(signed_url)
        else:
            response = FileResponse(
                services.storage_for(asset).open(asset.object_key, "rb"),
                as_attachment=True,
                filename=asset.original_filename,
                content_type=asset.mime_type,
            )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "no-store"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response


@extend_schema_view(get=extend_schema(operation_id="listPublicMediaAssets"))
class PublicMediaAssetListView(generics.ListAPIView[MediaAsset]):
    """Anonymous listing: only PUBLIC + APPROVED assets."""

    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = PublicMediaAssetSerializer

    def get_queryset(self) -> QuerySet[MediaAsset]:
        return MediaAsset.publicly_usable().filter(stored_publicly=True)
