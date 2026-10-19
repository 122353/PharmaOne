import pytest


@pytest.fixture(autouse=True)
def isolated_rate_limit_state():
    """Each test represents a fresh worker; individual tests exercise shared windows."""
    from app.rate_limit import limiter
    limiter.clear()
    yield
    limiter.clear()
