import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_live_and_ready_report_status_and_request_id():
    client = APIClient()
    response = client.get("/api/v1/health/live", HTTP_X_REQUEST_ID="test-request-1")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["X-Request-ID"] == "test-request-1"

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    assert ready.json()["dependencies"]["database"] == "ok"
