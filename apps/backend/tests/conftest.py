import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _isolated_cache(db):
    """Throttle, lockout and single-use challenge state must not leak between tests."""
    cache.clear()
    yield
    cache.clear()
