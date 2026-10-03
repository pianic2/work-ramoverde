from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest

from . import services
from .models import MediaAsset

if TYPE_CHECKING:
    _ModelForm = forms.ModelForm[MediaAsset]
    _ModelAdmin = admin.ModelAdmin[MediaAsset]
else:
    _ModelForm = forms.ModelForm
    _ModelAdmin = admin.ModelAdmin


class MediaAssetUploadForm(_ModelForm):
    """Admin upload goes through the same inspection as the API."""

    file = forms.FileField(required=True)

    class Meta:
        model = MediaAsset
        fields = ["alt_text", "caption", "visibility", "origin", "source_note"]

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        upload = cleaned.get("file")
        if upload is not None:
            from .inspection import inspect_upload

            try:
                inspect_upload(upload)
            except ValidationError as exc:
                self.add_error("file", exc)
        return cleaned


def _form_changes(form: forms.BaseForm) -> dict[str, Any]:
    return {
        field: form.cleaned_data[field]
        for field in form.changed_data
        if field in services.EDITABLE_FIELDS and field in form.cleaned_data
    }


@admin.register(MediaAsset)
class MediaAssetAdmin(_ModelAdmin):
    list_display = [
        "id",
        "original_filename",
        "kind",
        "visibility",
        "authorization_status",
        "size",
        "created_at",
    ]
    list_filter = ["kind", "visibility", "authorization_status", "origin"]
    search_fields = ["original_filename", "alt_text", "caption", "checksum_sha256"]
    readonly_fields = [
        "object_key",
        "original_filename",
        "mime_type",
        "kind",
        "size",
        "checksum_sha256",
        "width",
        "height",
        "stored_publicly",
        "uploaded_by",
        "created_at",
        "updated_at",
    ]

    def get_form(
        self,
        request: HttpRequest,
        obj: MediaAsset | None = None,
        change: bool = False,
        **kwargs: Any,
    ) -> type[forms.ModelForm[MediaAsset]]:
        if obj is None:
            kwargs["form"] = MediaAssetUploadForm
            return super().get_form(request, obj, change=change, **kwargs)
        base = super().get_form(request, obj, change=change, **kwargs)

        class MediaAssetChangeForm(base):  # type: ignore[valid-type,misc]
            """Same authorization and reference rules as the API, checked on the form."""

            def clean(self) -> dict[str, Any]:
                cleaned: dict[str, Any] = super().clean() or {}
                changes = _form_changes(self)
                needed = services.required_permissions(self.instance, changes)
                if not all(request.user.has_perm(perm) for perm in needed):
                    raise ValidationError(
                        "Approving, rejecting or publishing media requires approval rights."
                    )
                going_private = (
                    self.instance.visibility == MediaAsset.Visibility.PUBLIC
                    and changes.get("visibility") == MediaAsset.Visibility.PRIVATE
                )
                if going_private:
                    references = services.asset_references(self.instance.pk)
                    if references:
                        raise ValidationError(str(services.AssetInUse(references)))
                return cleaned

        return MediaAssetChangeForm

    def get_fields(self, request: HttpRequest, obj: MediaAsset | None = None) -> tuple[str, ...]:
        if obj is None:
            return ("file", "alt_text", "caption", "visibility", "origin", "source_note")
        return (
            "alt_text",
            "caption",
            "visibility",
            "origin",
            "source_note",
            "authorization_status",
            *self.readonly_fields,
        )

    def get_readonly_fields(self, request: HttpRequest, obj: MediaAsset | None = None) -> list[str]:
        readonly = list(self.readonly_fields)
        if obj is not None and not request.user.has_perm("media.approve_mediaasset"):
            readonly.append("authorization_status")
        return readonly if obj is not None else []

    def save_model(
        self, request: HttpRequest, obj: MediaAsset, form: forms.ModelForm[MediaAsset], change: bool
    ) -> None:
        if not change:
            created = services.create_asset(
                upload=form.cleaned_data["file"],
                uploaded_by=request.user,
                **{field: form.cleaned_data[field] for field in MediaAssetUploadForm.Meta.fields},
            )
            obj.pk = created.pk
            obj.refresh_from_db()
            return

        def authorize(permissions: set[str]) -> None:
            if not all(request.user.has_perm(perm) for perm in permissions):
                raise PermissionDenied

        services.update_asset(obj, authorize=authorize, **_form_changes(form))
        obj.refresh_from_db()

    def delete_model(self, request: HttpRequest, obj: MediaAsset) -> None:
        services.delete_asset(obj)

    def has_delete_permission(self, request: HttpRequest, obj: MediaAsset | None = None) -> bool:
        # Bulk deletes would bypass blob cleanup; delete one asset at a time, and never one
        # that page content still uses.
        if obj is None or not super().has_delete_permission(request, obj):
            return False
        return not services.asset_references(obj.pk)
