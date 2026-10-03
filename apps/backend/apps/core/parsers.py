from collections.abc import Mapping
from typing import IO, Any

from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser


class SafeJSONParser(JSONParser):
    """JSON parser that turns pathological nesting into a 400 instead of a 500."""

    def parse(
        self,
        stream: IO[Any],
        media_type: str | None = None,
        parser_context: Mapping[str, Any] | None = None,
    ) -> Any:
        try:
            return super().parse(stream, media_type, parser_context)
        except RecursionError as exc:
            raise ParseError("JSON parse error - document is nested too deeply.") from exc
