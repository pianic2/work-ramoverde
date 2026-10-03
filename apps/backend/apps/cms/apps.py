from django.apps import AppConfig


class CmsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cms"

    def ready(self) -> None:
        from . import receivers  # noqa: F401  (connects signal receivers)
