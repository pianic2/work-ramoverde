from django.apps import AppConfig
from django.contrib.admin import apps as admin_apps


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self) -> None:
        from . import signals  # noqa: F401


class StaffAdminConfig(admin_apps.AdminConfig):
    """Replaces `django.contrib.admin` in INSTALLED_APPS with the locked-down admin site."""

    default = False
    default_site = "apps.accounts.admin_site.StaffAdminSite"
