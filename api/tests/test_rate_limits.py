from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException


def test_window_is_bounded_and_independent_per_user_and_operation():
    from app.rate_limit import WindowLimiter
    clock = [10.0]
    limiter = WindowLimiter(max_keys=2, clock=lambda: clock[0])
    limiter.check("a", "import", 2, 60)
    limiter.check("a", "import", 2, 60)
    with pytest.raises(HTTPException) as exc:
        limiter.check("a", "import", 2, 60)
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "60"
    limiter.check("b", "import", 2, 60)
    with pytest.raises(HTTPException):
        limiter.check("c", "import", 2, 60)
    assert len(limiter.entries) == 2
    clock[0] = 70.0
    limiter.check("a", "import", 2, 60)
    limiter.check("a", "write", 2, 60)
    assert len(limiter.entries) == 2


def test_concurrent_requests_cannot_exceed_window():
    from app.rate_limit import WindowLimiter
    limiter = WindowLimiter()

    def attempt(_):
        try:
            limiter.check("same-user", "provider", 4, 60)
            return True
        except HTTPException:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(20))) == 4


def test_sensitive_dependency_limits_after_auth_and_ignores_forwarded_identity():
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    from app.auth import current_user
    from app.rate_limit import limiter, sensitive_user

    test_app = FastAPI()
    identity = ["a"]
    test_app.dependency_overrides[current_user] = lambda: identity[0]

    @test_app.post("/api/scan/ocr")
    def endpoint(user=Depends(sensitive_user)):
        return {"user": user}

    limiter.clear()
    try:
        client = TestClient(test_app)
        for _ in range(6):
            assert client.post("/api/scan/ocr").status_code == 200
        blocked = client.post("/api/scan/ocr", headers={"X-Forwarded-For": "different"})
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) >= 1
        identity[0] = "b"
        assert client.post("/api/scan/ocr").status_code == 200
    finally:
        limiter.clear()
