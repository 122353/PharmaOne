"""Opt-in real PostgreSQL workflow; an outer transaction protects existing data."""

import io
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import engine, get_db
from app.main import app
from app.models import Alert, Investigation, InventoryItem, Pharmacy
from app.tinyfish import normalize_record


@pytest.mark.skipif(
    os.getenv("PHARMAONE_TEST_POSTGRES") != "1" or engine.dialect.name != "postgresql",
    reason="Set PHARMAONE_TEST_POSTGRES=1 with a configured PostgreSQL database",
)
def test_postgres_pharmacy_workflow_rolls_back_test_records():
    """API commits persist across sessions, but only inside this rolled-back transaction."""
    from app.ingest_service import sync_once

    suffix = uuid4().hex[:12]
    owner_a, owner_b = f"pharmaone-test-a-{suffix}", f"pharmaone-test-b-{suffix}"
    product, maker, batch = f"Synthetic Test Medicine {suffix}", "Example Test Labs", f"T{suffix}"
    source = normalize_record(
        {
            "product_name": product,
            "manufacturer": maker,
            "batch_number": batch,
            "quality_issue": "Synthetic test finding",
            "reporting_period": "AUG-2026",
        },
        "AUG-2026",
    )
    with engine.connect() as connection:
        outer = connection.begin()
        identity = {"owner": owner_a}

        def db_override():
            with Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False) as session:
                yield session

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[current_user] = lambda: identity["owner"]
        try:
            with TestClient(app) as http:
                assert http.put("/api/pharmacies/current", json={"name": "Synthetic Pharmacy A"}).status_code == 200
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    run = sync_once(db, "synthetic-operator-key", "AUG-2026", 1, provider=lambda key, period, limit: ([source], "mock-provider-run"))
                    assert run.record_count == 1
                assert http.post("/api/ingestion/sync", json={"period": "AUG-2026", "account": "mine"}).status_code == 404

                csv = f"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\n{product},{maker},{batch},10mg,2027-01-01,3\n".encode()
                uploaded = http.post("/api/inventory/import", files={"file": ("test.csv", io.BytesIO(csv), "text/csv")})
                assert uploaded.status_code == 200, uploaded.text
                assert uploaded.json()["imported"] == 1
                match = next(m for m in http.get("/api/matches").json() if m["alert"]["fingerprint"] == source["fingerprint"])
                assert match["status"] == "potential_match"
                assert match["alert"]["source_url"].startswith("https://cdscoonline.gov.in/")
                assert http.get("/api/dashboard").json()["potential_count"] >= 1

                for status in ("open", "reviewed", "simulated_hold"):
                    result = http.post("/api/investigations", json={"match_id": match["id"], "status": status, "note": "Synthetic test review"})
                    assert result.status_code == 200, result.text
                investigation = result.json()
                assert len(http.get(f"/api/investigations/{investigation['id']}/events").json()) == 3

                # A new request uses a new session and sees committed state.
                persisted = http.get("/api/investigations").json()[0]
                assert persisted["status"] == "reviewed"
                assert persisted["simulated_hold"] is True
                assert http.get("/api/inventory").json()[0]["batch_number"] == batch

                identity["owner"] = owner_b
                assert http.put("/api/pharmacies/current", json={"name": "Synthetic Pharmacy B"}).status_code == 200
                assert http.get("/api/inventory").json() == []
                assert http.get("/api/investigations").json() == []
                assert http.get("/api/integrations/tinyfish").status_code == 404
                assert http.post("/api/ingestion/sync", json={"period": "AUG-2026", "account": "mine"}).status_code == 404
                assert http.post("/api/investigations", json={"match_id": match["id"], "status": "reviewed"}).status_code == 404
                assert http.patch("/api/inventory/" + match["inventory"]["id"], json={
                    "medicine_name": product, "manufacturer": maker, "batch_number": batch,
                    "strength": "10mg", "expiry_date": "2027-01-01", "quantity": 1,
                }).status_code == 404

                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    assert db.get(Alert, source["fingerprint"]) is not None
                    assert db.get(InventoryItem, match["inventory"]["id"]) is not None
                    assert db.get(Investigation, investigation["id"]) is not None
        finally:
            app.dependency_overrides.clear()
            outer.rollback()

    # Rollback also covers commits issued by the API, without touching existing rows.
    with Session(engine) as db:
        assert db.get(Alert, source["fingerprint"]) is None
        assert db.scalar(select(Pharmacy).where(Pharmacy.owner_id.in_([owner_a, owner_b]))) is None
