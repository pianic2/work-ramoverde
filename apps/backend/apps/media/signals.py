"""Signals declared by `media` so higher modules can react without `media` importing them.

`collect_references` is sent with `asset_id`; receivers (e.g. `cms`) return a list of
human-readable places that use the asset. A non-empty answer blocks deleting the asset or
making it PRIVATE (see `services.AssetInUse`).
"""

from django.dispatch import Signal

collect_references = Signal()
