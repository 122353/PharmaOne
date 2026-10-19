"""Small process-local abuse controls; limits reset on restart and per worker."""
import math
import time
from threading import Lock

from fastapi import Depends, HTTPException, Request

from .auth import current_user


class WindowLimiter:
    def __init__(self, max_keys: int = 10_000, clock=time.monotonic):
        self.max_keys = max_keys
        self.clock = clock
        self.entries: dict[tuple[str, str], tuple[int, float]] = {}
        self.lock = Lock()
        self.next_sweep = 0.0

    def clear(self):
        with self.lock:
            self.entries.clear()
            self.next_sweep = 0.0

    def check(self, user: str, operation: str, limit: int, seconds: int):
        with self.lock:
            now = self.clock()
            if now >= self.next_sweep or len(self.entries) >= self.max_keys:
                self.entries = {key: value for key, value in self.entries.items() if value[1] > now}
                self.next_sweep = now + seconds
            key = (user, operation)
            count, deadline = self.entries.get(key, (0, now + seconds))
            if deadline <= now:
                count, deadline = 0, now + seconds
            if count >= limit or (key not in self.entries and len(self.entries) >= self.max_keys):
                retry = max(1, math.ceil(deadline - now))
                raise HTTPException(429, "Too many requests; try again shortly", headers={"Retry-After": str(retry)})
            self.entries[key] = (count + 1, deadline)


limiter = WindowLimiter()


def sensitive_user(request: Request, user: str = Depends(current_user)) -> str:
    """Key by verified subject, never a client supplied IP or pharmacy ID."""
    path = request.url.path
    if path.startswith("/api/contextos/") or path.endswith("/translate") or path == "/api/scan/ocr":
        operation, limit = "provider", 6
    elif path.endswith("/import") or path.endswith("/attachments"):
        operation, limit = "upload", 10
    elif path in {"/api/matches/recheck", "/api/scan/match"}:
        operation, limit = "matching", 10
    else:
        operation, limit = "write", 60
    limiter.check(user, operation, limit, 60)
    return user
