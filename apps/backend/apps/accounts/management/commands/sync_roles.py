from typing import Any

from django.core.management.base import BaseCommand

from apps.accounts.rbac import sync_roles


class Command(BaseCommand):
    help = "Create RBAC role groups and grant exactly the permissions of the matrix."

    def handle(self, *args: Any, **options: Any) -> None:
        missing = sync_roles()
        if missing:
            self.stdout.write(
                self.style.WARNING(
                    "Not yet defined (granted on a later sync): " + ", ".join(sorted(missing))
                )
            )
        self.stdout.write(self.style.SUCCESS("Roles synchronised."))
