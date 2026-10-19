import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from app import auth
from app.config import settings


def test_valid_supabase_asymmetric_token_and_wrong_role(monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    settings.cache_clear()

    class JWKS:
        def get_signing_key_from_jwt(self, token):
            return type("SigningKey", (), {"key": key.public_key()})()

    monkeypatch.setattr(auth, "jwks_client", lambda: JWKS())
    claims = {
        "sub": "user-a", "role": "authenticated", "aud": "authenticated",
        "iss": "https://example.supabase.co/auth/v1", "exp": 4102444800,
    }
    token = jwt.encode(claims, key, algorithm="ES256")
    assert auth.current_user("Bearer " + token) == "user-a"
    with pytest.raises(HTTPException) as exc:
        auth.current_user("Bearer " + jwt.encode({**claims, "role": "anon"}, key, algorithm="ES256"))
    assert exc.value.status_code == 401
    settings.cache_clear()


@pytest.mark.parametrize("missing", ["exp", "sub", "aud", "iss"])
def test_jwt_requires_security_claims(monkeypatch, missing):
    key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    settings.cache_clear()

    class JWKS:
        def get_signing_key_from_jwt(self, token):
            return type("SigningKey", (), {"key": key.public_key()})()

    monkeypatch.setattr(auth, "jwks_client", lambda: JWKS())
    claims = {"sub": "claim-test", "role": "authenticated", "aud": "authenticated",
              "iss": "https://example.supabase.co/auth/v1", "exp": 4102444800}
    del claims[missing]
    try:
        with pytest.raises(HTTPException) as exc:
            auth.current_user("Bearer " + jwt.encode(claims, key, algorithm="ES256"))
        assert exc.value.status_code == 401
        assert exc.value.detail == "Invalid session"
    finally:
        settings.cache_clear()

def test_supabase_jwt_authenticates_notification_api_with_isolated_database(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.db import Base, get_db
    from app.main import app
    from app.models import Pharmacy

    key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    settings.cache_clear()

    class JWKS:
        def get_signing_key_from_jwt(self, token):
            return type("SigningKey", (), {"key": key.public_key()})()

    monkeypatch.setattr(auth, "jwks_client", lambda: JWKS())
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Pharmacy(owner_id="jwt-notification-user", name="JWT Pharmacy"))
        db.commit()

    def isolated_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = isolated_db
    claims = {
        "sub": "jwt-notification-user", "role": "authenticated",
        "aud": "authenticated", "iss": "https://example.supabase.co/auth/v1",
        "exp": 4102444800,
    }
    token = jwt.encode(claims, key, algorithm="ES256")
    try:
        client = TestClient(app)
        response = client.get("/api/notifications", headers={"Authorization": "Bearer " + token})
        assert response.status_code == 200
        assert response.json() == []
        denied = jwt.encode({**claims, "role": "anon"}, key, algorithm="ES256")
        assert client.get("/api/notifications", headers={"Authorization": "Bearer " + denied}).status_code == 401
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        settings.cache_clear()
