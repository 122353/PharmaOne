"""Real local ES256/JWKS verification through API routes; no Supabase calls."""
import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import auth
from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import Alert
from app.tinyfish import normalize_record


@pytest.fixture
def signed_api(monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="local-test-key", use="sig", alg="ES256")
    requests = []

    class JWKSHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            payload = json.dumps({"keys": [jwk]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), JWKSHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("SUPABASE_URL", "https://local-auth.example.test")
    settings.cache_clear()
    client = jwt.PyJWKClient(f"http://127.0.0.1:{server.server_port}/jwks", cache_keys=True)
    monkeypatch.setattr(auth, "jwks_client", lambda: client)
    local_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(local_engine)

    def isolated_db():
        with Session(local_engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = isolated_db

    def headers(subject="tenant-a", *, changes=None, other_key=False):
        claims = {"sub": subject, "role": "authenticated", "aud": "authenticated",
                  "iss": "https://local-auth.example.test/auth/v1", "exp": int(time.time()) + 600}
        claims.update(changes or {})
        signing_key = ec.generate_private_key(ec.SECP256R1()) if other_key else key
        token = jwt.encode(claims, signing_key, algorithm="ES256", headers={"kid": "local-test-key"})
        return {"Authorization": "Bearer " + token}

    try:
        # Do not enter application lifespan; only the isolated database is used.
        yield TestClient(app), headers, local_engine, requests
    finally:
        app.dependency_overrides.clear()
        local_engine.dispose()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        settings.cache_clear()


@pytest.mark.parametrize("path", ["/api/me", "/api/dashboard", "/api/inventory", "/api/matches",
    "/api/notifications", "/api/investigations", "/api/suppliers/exposure", "/api/inventory/imports"])
def test_protected_resource_families_reject_no_session(signed_api, path):
    http, _, _, _ = signed_api
    assert http.get(path).status_code == 401


@pytest.mark.parametrize("changes,other_key", [
    ({"exp": 1}, False), ({"nbf": 4102444800}, False), ({"aud": "wrong"}, False),
    ({"iss": "https://wrong.example.test/auth/v1"}, False), ({"role": "anon"}, False),
    ({"sub": ""}, False), ({}, True),
])
def test_invalid_signed_sessions_are_generic_401(signed_api, changes, other_key):
    http, headers, _, _ = signed_api
    response = http.get("/api/me", headers=headers(changes=changes, other_key=other_key))
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid session"}


def test_real_jwks_tokens_enforce_all_tenant_boundaries(signed_api):
    http, headers, local_engine, jwks_requests = signed_api
    a, b = headers(), headers("tenant-b")
    assert http.put("/api/pharmacies/current", headers=a, json={"name": "Tenant A Pharmacy"}).status_code == 200
    record = normalize_record({"product_name": "Linezolid Tablets IP 600mg", "manufacturer": "Example Labs",
        "batch_number": "LOCAL-123", "quality_issue": "Synthetic dissolution finding",
        "reporting_period": "AUG-2026"}, "AUG-2026")
    with Session(local_engine) as db:
        db.add(Alert(**record, run_id="synthetic-auth-run"))
        db.commit()
    csv = b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nLinezolid Tablets IP 600mg,Example Labs,LOCAL-123,600mg,2028-01-01,3\n"
    assert http.post("/api/inventory/import", headers=a, files={"file": ("local.csv", csv, "text/csv")}).status_code == 200
    match = http.get("/api/matches", headers=a).json()[0]
    assert match["status"] == "potential_match"
    notification = http.get("/api/notifications", headers=a).json()[0]
    investigation = http.post("/api/investigations", headers=a,
        json={"match_id": match["id"], "status": "reviewed", "note": "Private tenant A note"}).json()
    image = io.BytesIO()
    Image.new("RGB", (2, 2)).save(image, format="PNG")
    file = ("local.png", image.getvalue(), "image/png")
    attachment = http.post(f"/api/investigations/{investigation['id']}/attachments", headers=a, files={"file": file}).json()
    assert http.post("/api/suppliers/links", headers=a, json={"inventory_id": match["inventory"]["id"],
        "supplier": "Private supplier A", "distributor": "Private distributor A"}).status_code == 200
    assert http.get("/api/dashboard", headers=a).json()["inventory_count"] == 1
    assert len(http.get("/api/inventory/imports", headers=a).json()) == 1

    assert http.put("/api/pharmacies/current", headers=b, json={"name": "Tenant B Pharmacy"}).status_code == 200
    for path in ["inventory", "matches", "notifications", "investigations", "suppliers/exposure", "inventory/imports"]:
        response = http.get("/api/" + path, headers=b)
        assert response.status_code == 200
        assert response.json() == []
    assert http.get("/api/dashboard", headers=b).json()["inventory_count"] == 0
    assert http.get("/api/dashboard", headers=b).json()["unread_notifications"] == 0
    assert http.get("/api/me", headers=b).json()["pharmacy"]["name"] == "Tenant B Pharmacy"
    assert http.patch(f"/api/notifications/{notification['id']}/read", headers=b).status_code == 404
    assert http.patch(f"/api/inventory/{match['inventory']['id']}", headers=b, json={
        "medicine_name": "Linezolid Tablets IP 600mg", "batch_number": "LOCAL-123", "manufacturer": "Example Labs", "quantity": 0}).status_code == 404
    assert http.post("/api/investigations", headers=b, json={"match_id": match["id"], "status": "closed"}).status_code == 404
    assert http.post("/api/suppliers/links", headers=b, json={"inventory_id": match["inventory"]["id"],
        "supplier": "Guessed", "distributor": "Guessed"}).status_code == 404
    assert http.get(f"/api/investigations/{investigation['id']}/events", headers=b).status_code == 404
    assert http.get(f"/api/investigations/{investigation['id']}/attachments", headers=b).status_code == 404
    assert http.post(f"/api/investigations/{investigation['id']}/attachments", headers=b, files={"file": file}).status_code == 404
    assert http.get(f"/api/investigations/attachments/{attachment['id']}", headers=b).status_code == 404
    # Regulatory source records are intentionally shared with every authenticated pharmacy.
    assert http.get(f"/api/alerts/{record['fingerprint']}", headers=b).status_code == 200
    assert http.get("/api/investigations", headers=a).json()[0]["note"] == "Private tenant A note"
    assert http.get("/api/notifications", headers=a).json()[0]["is_read"] is False
    assert jwks_requests == ["/jwks"]


def test_actual_sensitive_endpoint_returns_retry_after(signed_api):
    http, headers, _, _ = signed_api
    a = headers()
    http.put("/api/pharmacies/current", headers=a, json={"name": "Rate Test Pharmacy"})
    for _ in range(10):
        assert http.post("/api/matches/recheck", headers=a).status_code == 200
    response = http.post("/api/matches/recheck", headers=a)
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1
