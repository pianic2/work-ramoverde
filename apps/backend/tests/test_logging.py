import json
import logging

from apps.core.logging import JsonFormatter


def test_json_logs_include_exception_traceback():
    try:
        raise ValueError("example failure")
    except ValueError as error:
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="request failed",
            args=(),
            exc_info=(type(error), error, error.__traceback__),
        )
    event = json.loads(JsonFormatter().format(record))
    assert event["message"] == "request failed"
    assert "ValueError: example failure" in event["exception"]
    assert "test_json_logs_include_exception_traceback" in event["exception"]
