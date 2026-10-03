from typing import Any

from django.db.models import ProtectedError
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import MediaAsset
from .services import asset_references


@receiver(pre_delete, sender=MediaAsset)
def protect_referenced_assets(
    sender: type[MediaAsset], instance: MediaAsset, **kwargs: Any
) -> None:
    """Last line of defence: no code path (ORM, queryset, admin) deletes a referenced asset."""
    references = asset_references(instance.pk)
    if references:
        raise ProtectedError(f"Media asset {instance.pk} is in use: {references}", {instance})
