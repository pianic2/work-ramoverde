from typing import Any

from django.core.management.base import BaseCommand

from apps.media.models import MediaAsset
from apps.media.services import reconcile_storage


class Command(BaseCommand):
    help = (
        "Move every media blob into the storage matching its committed state "
        "(public only while PUBLIC + APPROVED). Idempotent; run after deploys or on a schedule."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        failed = 0
        ids = MediaAsset.objects.order_by("pk").values_list("pk", flat=True)
        for asset_id in ids.iterator():
            try:
                reconcile_storage(asset_id)
            except Exception as exc:  # report and continue with the remaining assets
                failed += 1
                self.stderr.write(f"asset {asset_id}: {exc.__class__.__name__}")
        self.stdout.write(f"reconciled {ids.count() - failed} assets, {failed} failed")
        if failed:
            raise SystemExit(1)
