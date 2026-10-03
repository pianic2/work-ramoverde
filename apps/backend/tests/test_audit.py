import pytest
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.utils import DatabaseError
from django.test import RequestFactory

from apps.audit.models import AuditEvent
from apps.audit.services import record_event

User = get_user_model()


@pytest.mark.django_db
def test_record_event_stores_actor_request_context_and_safe_metadata():
    actor = User.objects.create_user(email="actor@example.com", password="x" * 16)
    request = RequestFactory().post(
        "/api/v1/auth/session/login",
        HTTP_USER_AGENT="pytest-agent/1.0",
        REMOTE_ADDR="203.0.113.7",
    )
    request.request_id = "req-123"  # type: ignore[attr-defined]

    event = record_event(
        "auth.login.success",
        request=request,
        actor=actor,
        target=actor,
        metadata={"channel": "web", "password": "hunter2-secret", "nested": {"otp": "123456"}},
    )

    stored = AuditEvent.objects.get(pk=event.pk)
    assert stored.action == "auth.login.success"
    assert stored.actor_id == actor.pk
    assert stored.target_type == "accounts.user"
    assert stored.target_id == str(actor.pk)
    assert stored.ip_address == "203.0.113.7"
    assert stored.user_agent == "pytest-agent/1.0"
    assert stored.request_id == "req-123"
    assert stored.metadata == {
        "channel": "web",
        "password": "[redacted]",
        "nested": {"otp": "[redacted]"},
    }
    assert "hunter2-secret" not in str(stored.metadata)


@pytest.mark.django_db
def test_audit_events_are_append_only_in_orm():
    event = record_event("auth.logout")
    event.action = "tampered"
    with pytest.raises(RuntimeError):
        event.save()
    with pytest.raises(RuntimeError):
        event.delete()
    with pytest.raises(RuntimeError):
        AuditEvent.objects.filter(pk=event.pk).update(action="tampered")
    with pytest.raises(RuntimeError):
        AuditEvent.objects.filter(pk=event.pk).delete()


@pytest.mark.django_db
def test_audit_events_are_append_only_in_postgresql():
    event = record_event("auth.logout")
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("UPDATE audit_auditevent SET action = 'tampered' WHERE id = %s", [event.pk])


@pytest.mark.django_db
def test_audit_event_rows_cannot_be_deleted_in_postgresql():
    event = record_event("auth.logout")
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("DELETE FROM audit_auditevent WHERE id = %s", [event.pk])


@pytest.mark.django_db
def test_user_agent_is_truncated_and_untrusted_forwarded_for_is_ignored():
    request = RequestFactory().get(
        "/",
        HTTP_USER_AGENT="a" * 2000,
        HTTP_X_FORWARDED_FOR="198.51.100.1",
        REMOTE_ADDR="203.0.113.9",
    )
    event = record_event("auth.login.failure", request=request, outcome="failure")
    assert len(event.user_agent) == 512
    assert event.ip_address == "203.0.113.9"
    assert event.outcome == "failure"
