from django.conf import settings
from django.db import models

from .validators import validate_multiline_plain_text, validate_plain_text


class MediaAsset(models.Model):
    """Metadata for one uploaded blob. The bytes live in object storage under `object_key`."""

    class Visibility(models.TextChoices):
        PUBLIC = "PUBLIC", "Public"
        PRIVATE = "PRIVATE", "Private"

    class AuthorizationStatus(models.TextChoices):
        PENDING = "PENDING", "Pending review"
        APPROVED = "APPROVED", "Approved for publication"
        REJECTED = "REJECTED", "Rejected"

    class Kind(models.TextChoices):
        IMAGE = "IMAGE", "Image"
        DOCUMENT = "DOCUMENT", "Document"
        VIDEO = "VIDEO", "Video"

    class Origin(models.TextChoices):
        STAFF_UPLOAD = "STAFF_UPLOAD", "Uploaded by staff"
        CLIENT_PROVIDED = "CLIENT_PROVIDED", "Provided by the client"
        THIRD_PARTY = "THIRD_PARTY", "Third party / licensed"

    object_key = models.CharField(max_length=255, unique=True, editable=False)
    original_filename = models.CharField(max_length=255, editable=False)
    mime_type = models.CharField(max_length=100, editable=False)
    kind = models.CharField(max_length=16, choices=Kind.choices, editable=False)
    size = models.PositiveBigIntegerField(editable=False)
    checksum_sha256 = models.CharField(max_length=64, editable=False, db_index=True)
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    alt_text = models.CharField(max_length=255, blank=True, validators=[validate_plain_text])
    caption = models.CharField(
        max_length=500, blank=True, validators=[validate_multiline_plain_text]
    )
    visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.PRIVATE
    )
    origin = models.CharField(max_length=32, choices=Origin.choices, default=Origin.STAFF_UPLOAD)
    source_note = models.CharField(
        max_length=255,
        blank=True,
        validators=[validate_plain_text],
        help_text="Author, licence or provenance of the file.",
    )
    authorization_status = models.CharField(
        max_length=16,
        choices=AuthorizationStatus.choices,
        default=AuthorizationStatus.PENDING,
        help_text="Public site usage requires APPROVED (photo publication rules are DA DEFINIRE).",
    )
    stored_publicly = models.BooleanField(
        default=False,
        editable=False,
        help_text="True while the blob sits in the public storage (PUBLIC and APPROVED).",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        permissions = [
            ("approve_mediaasset", "Can approve or reject media assets for public use"),
            ("download_private_mediaasset", "Can download private media assets"),
        ]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.object_key})"

    @property
    def is_publicly_usable(self) -> bool:
        return (
            self.visibility == self.Visibility.PUBLIC
            and self.authorization_status == self.AuthorizationStatus.APPROVED
        )

    @classmethod
    def publicly_usable(cls) -> "models.QuerySet[MediaAsset]":
        return cls.objects.filter(
            visibility=cls.Visibility.PUBLIC,
            authorization_status=cls.AuthorizationStatus.APPROVED,
        )
