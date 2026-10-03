"""CMS receivers for signals declared by lower modules."""

from typing import Any

from django.dispatch import receiver

from apps.media.signals import collect_references


@receiver(collect_references, dispatch_uid="cms.media_references")
def report_media_references(sender: Any, asset_id: int, **kwargs: Any) -> list[str]:
    from .services import media_references

    return media_references(asset_id)
