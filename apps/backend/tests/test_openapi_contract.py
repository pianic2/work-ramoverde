"""Contract hygiene for the DRF -> OpenAPI -> Orval pipeline (WR-11)."""

import re

import pytest
from drf_spectacular.generators import SchemaGenerator

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
OPERATION_ID = re.compile(r"^[a-z][A-Za-z0-9]*$")


@pytest.fixture(scope="module")
def schema() -> dict:
    return SchemaGenerator().get_schema(request=None, public=True)


def operations(schema: dict) -> list[tuple[str, str, dict]]:
    return [
        (path, method, operation)
        for path, item in schema["paths"].items()
        for method, operation in item.items()
        if method in HTTP_METHODS
    ]


def test_every_operation_is_versioned_under_api_v1(schema: dict):
    paths = {path for path, _, _ in operations(schema)}
    assert paths
    assert all(path.startswith("/api/v1/") for path in paths), sorted(paths)


def test_operation_ids_are_unique_camel_case_function_names(schema: dict):
    ids = [operation["operationId"] for _, _, operation in operations(schema)]
    assert len(ids) == len(set(ids)), "duplicate operationId breaks generated client names"
    invalid = [operation_id for operation_id in ids if not OPERATION_ID.fullmatch(operation_id)]
    assert not invalid, f"operationIds must be stable camelCase names: {invalid}"
