from functools import lru_cache
import jwt
from fastapi import Header, HTTPException
from .config import settings


@lru_cache
def jwks_client():
    url = settings().supabase_url.rstrip("/")
    if not url:
        return None
    return jwt.PyJWKClient(f"{url}/auth/v1/.well-known/jwks.json", cache_keys=True)


def current_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    client = jwks_client()
    if client is None:
        raise HTTPException(503, "Supabase Auth is not configured")
    token = authorization[7:]
    try:
        if len(token) > 16_384:
            raise ValueError("Token too large")
        key = client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256", "ES256"], audience=settings().supabase_jwt_audience, issuer=f"{settings().supabase_url.rstrip('/')}/auth/v1", options={"require": ["exp", "sub", "aud", "iss"]})
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject or len(subject) > 64 or claims.get("role") != "authenticated":
            raise ValueError("Invalid role")
        return subject
    except Exception as exc:
        raise HTTPException(401, "Invalid session") from exc
