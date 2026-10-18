import json
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.db import Base, get_db
from app.main import app
from app.models import Alert, IngestionRun
from app.verified_snapshot import import_verified_snapshot


EVIDENCE = Path(__file__).resolve().parents[2] / "evidence"


def test_verified_tinyfish_snapshot_is_persistent_and_idempotent():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        assert import_verified_snapshot(db, EVIDENCE / "cdsco-aug-2026-tinyfish.json", EVIDENCE / "cdsco-verification-report.json") == 5
        assert import_verified_snapshot(db, EVIDENCE / "cdsco-aug-2026-tinyfish.json", EVIDENCE / "cdsco-verification-report.json") == 0
        assert len(db.scalars(select(Alert)).all()) == 5
        run = db.scalar(select(IngestionRun))
        assert run.status == "succeeded"
        assert run.provider_run_id == "7d650bd4-71e6-49dc-b967-f95304ecb6aa"
        assert all(alert.source_url == "https://cdscoonline.gov.in/CDSCO/viewPublicNSQDrug" and alert.retrieved_at for alert in db.scalars(select(Alert)))


def test_snapshot_import_rejects_unverified_changes(tmp_path):
    snapshot = json.loads((EVIDENCE / "cdsco-aug-2026-tinyfish.json").read_text(encoding="utf-8"))
    snapshot["records"][0]["batch_number"] = "CHANGED"
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(snapshot), encoding="utf-8")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db, pytest.raises(ValueError, match="verification"):
        import_verified_snapshot(db, changed, EVIDENCE / "cdsco-verification-report.json")


def test_snapshot_verification_survives_windows_line_endings(tmp_path):
    original = (EVIDENCE / "cdsco-aug-2026-tinyfish.json").read_bytes()
    windows_copy = tmp_path / "windows.json"
    windows_copy.write_bytes(original.replace(b"\n", b"\r\n"))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        assert import_verified_snapshot(db, windows_copy, EVIDENCE / "cdsco-verification-report.json") == 5


def test_verified_alert_to_synthetic_pharmacy_hold_persists_and_isolated():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        import_verified_snapshot(db, EVIDENCE / "cdsco-aug-2026-tinyfish.json", EVIDENCE / "cdsco-verification-report.json")
    identity = {"user": "synthetic-a"}

    def db_override():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[current_user] = lambda: identity["user"]
    try:
        with TestClient(app) as http:
            assert http.put("/api/pharmacies/current", json={"name": "Synthetic Pharmacy A"}).status_code == 200
            csv = (
                "medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\n"
                "Linezolid Tablets IP 600mg,Symbiosis Pharmaceuticals Pvt Ltd,TG261185,600mg,2028-04-01,4\n"
                "Linezolid Tablets IP 600mg,,TG261185,600mg,2028-04-01,2\n"
                "Linezolid Tablets IP 600mg,Symbiosis Pharmaceuticals Pvt Ltd,WRONG,600mg,2028-04-01,2\n"
                "Linezolid Tablets 300mg,Symbiosis Pharmaceuticals Pvt Ltd,TG261185,300mg,2028-04-01,2\n"
                "Linezolid Tablets IP 600mg,Symbiosis Pharmaceuticals Pvt Ltd,TG261185,600mg,2028-04-01,4\n"
            ).encode()
            upload = http.post("/api/inventory/import", files={"file": ("synthetic.csv", io.BytesIO(csv), "text/csv")})
            assert upload.status_code == 200, upload.text
            assert upload.json()["duplicates"] == 1
            matches = http.get("/api/matches").json()
            assert {m["status"] for m in matches} == {"potential_match", "needs_verification"}
            potential = next(m for m in matches if m["status"] == "potential_match")
            assert potential["alert"]["batch_number"] == "TG261185"
            assert http.get("/api/dashboard").json()["potential_count"] == 1
            hold = http.post("/api/investigations", json={"match_id": potential["id"], "status": "simulated_hold", "note": "Synthetic demonstration only"})
            assert hold.status_code == 200, hold.text
        with TestClient(app) as refreshed:
            history = refreshed.get("/api/investigations").json()
            assert history[0]["status"] == "under_investigation"
            assert history[0]["simulated_hold"] is True
            assert refreshed.get("/api/investigations/" + history[0]["id"] + "/events").json()
            identity["user"] = "synthetic-b"
            assert refreshed.put("/api/pharmacies/current", json={"name": "Synthetic Pharmacy B"}).status_code == 200
            assert refreshed.get("/api/inventory").json() == []
            assert refreshed.get("/api/matches").json() == []
            assert refreshed.get("/api/investigations").json() == []
            assert len(refreshed.get("/api/alerts").json()) == 5
    finally:
        app.dependency_overrides.clear()
