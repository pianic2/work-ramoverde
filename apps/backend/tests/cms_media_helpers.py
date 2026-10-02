"""Shared helpers for media and CMS tests (not a test module)."""

import io

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

User = get_user_model()


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (32, 16)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(30, 120, 60)).save(buffer, format=fmt)
    return buffer.getvalue()


def png_upload(name: str = "photo.png", size: tuple[int, int] = (32, 16)) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, image_bytes("PNG", size), content_type="image/png")


PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< >>\n%%EOF\n"


def staff_user(email: str, *codenames: str):
    """Active staff user holding exactly the given `app_label.codename` permissions."""
    user = User.objects.create_user(email=email, password="x" * 16, is_staff=True)
    for perm in codenames:
        app_label, codename = perm.split(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return User.objects.get(pk=user.pk)


def make_asset(
    *, visibility: str = "PUBLIC", authorization_status: str = "APPROVED", alt_text: str = "Alt"
):
    from apps.media.services import create_asset

    return create_asset(
        upload=png_upload(),
        uploaded_by=None,
        visibility=visibility,
        alt_text=alt_text,
        authorization_status=authorization_status,
    )
