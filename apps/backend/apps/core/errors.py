from typing import Any

from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = exception_handler(exc, context)
    if response is None:
        return None
    details = response.data
    code: Any = "request_error"
    if isinstance(exc, APIException):
        # Prefer the specific code raised (e.g. "mfa_failed", "step_up_required").
        codes = exc.get_codes()
        code = codes if isinstance(codes, str) else exc.default_code
    request = context.get("request")
    response.data = {
        "error": {
            "code": str(code),
            "message": _message(details),
            "details": details,
            "request_id": getattr(request, "request_id", None),
        }
    }
    return response


def _message(details: Any) -> str:
    if isinstance(details, dict):
        return "The request could not be completed."
    if isinstance(details, list) and details and isinstance(details[0], str):
        return details[0]
    return "The request could not be completed."
