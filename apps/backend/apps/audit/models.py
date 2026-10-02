"""Append-only security and business audit trail (WR-18).

Rows are written only through `apps.audit.services.record_event`. Updates and
deletes are refused by the ORM (model + queryset) and by a PostgreSQL trigger
installed in migration 0001, so a buggy or compromised code path cannot rewrite history.
"""

from typing import Any, NoReturn

from django.conf import settings
from django.db import models

APPEND_ONLY_MESSAGE = "Audit events are append-only."


class AuditEventQuerySet(models.QuerySet["AuditEvent"]):
    def update(self, **kwargs: Any) -> NoReturn:
        raise RuntimeError(APPEND_ONLY_MESSAGE)

    def delete(self) -> NoReturn:
        raise RuntimeError(APPEND_ONLY_MESSAGE)


class AuditEvent(models.Model):
    class Outcome(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.CharField(max_length=64, db_index=True)
    outcome = models.CharField(max_length=16, choices=Outcome.choices, default=Outcome.SUCCESS)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    request_id = models.CharField(max_length=128, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["actor", "created_at"])]

    def __str__(self) -> str:
        return f"{self.action} ({self.outcome})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise RuntimeError(APPEND_ONLY_MESSAGE)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise RuntimeError(APPEND_ONLY_MESSAGE)
