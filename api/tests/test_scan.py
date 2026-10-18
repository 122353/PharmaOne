import pytest
import io
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.auth import current_user
from app.main import app
from app.scan import sarvam_service
from app.sarvam import SarvamError
from app.models import Alert
from app.tinyfish import normalize_record


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    def db():
        with sessions() as session:
            yield session
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[current_user] = lambda: "user-a"
    with TestClient(app) as test_client:
        test_client.put('/api/pharmacies/current', json={"name": "A Pharmacy"})
        yield test_client, sessions
    app.dependency_overrides.clear()


def test_scan_exact_batch_and_missing_batch(client):
    http, sessions = client
    with sessions() as db:
        db.add(Alert(**normalize_record({"product_name": "Drug A", "manufacturer": "Maker A", "batch_number": "B12", "quality_issue": "Dissolution", "reporting_period": "AUG-2026"}, "AUG-2026"), run_id="run-1"))
        db.commit()
    exact = http.post('/api/scan/match', json={"medicine_name": "Drug A", "manufacturer": "Maker A", "batch_number": "B12", "confirmed": True})
    assert exact.status_code == 200
    assert exact.json()['matches'][0]['status'] == 'potential_match'
    assert exact.json()['matches'][0]['alert']['batch_number'] == 'B12'
    assert exact.json()['matches'][0]['explanation']['pharma_match']['model'] == 'PharmaMatch'
    assert exact.json()['matches'][0]['alert']['pharma_classify']['category'] == 'dissolution'
    missing = http.post('/api/scan/match', json={"medicine_name": "Drug A", "manufacturer": "Maker A", "batch_number": "", "confirmed": True})
    assert missing.json()['matches'][0]['status'] == 'needs_verification'
    assert http.post('/api/scan/match', json={"medicine_name": "Drug A", "batch_number": "B12", "confirmed": False}).status_code == 400
    wrong = http.post('/api/scan/match', json={"medicine_name": "Drug A", "manufacturer": "Maker A", "batch_number": "B13", "confirmed": True})
    assert wrong.json()['matches'] == []


def test_ocr_requires_valid_image_and_preserves_raw_text(client):
    http, _ = client
    class FakeOCR:
        def ocr(self, raw, filename, mime):
            return {"fields": {"medicine_name": "दवा A", "batch_number": "B12", "original_text": "दवा A बैच B12"},
                    "original": {"result": {"original_text": "दवा A बैच B12"}}, "status": "completed"}
    app.dependency_overrides[sarvam_service] = lambda: FakeOCR()
    try:
        invalid = http.post('/api/scan/ocr', files={"file": ("bad.png", b"not an image", "image/png")})
        assert invalid.status_code == 400
        image = io.BytesIO()
        Image.new('RGB', (12, 12), 'white').save(image, format='PNG')
        good = http.post('/api/scan/ocr', files={"file": ("pack.png", image.getvalue(), "image/png")})
        assert good.status_code == 200, good.text
        assert good.json()['fields']['medicine_name'] == 'दवा A'
        assert good.json()['original']['result']['original_text'] == 'दवा A बैच B12'
    finally:
        app.dependency_overrides.pop(sarvam_service, None)


def test_ocr_rejects_oversized_image_and_provider_failure(client):
    http, _ = client
    class FailingOCR:
        def ocr(self, raw, filename, mime):
            raise SarvamError("provider unavailable")
    app.dependency_overrides[sarvam_service] = lambda: FailingOCR()
    try:
        oversized = b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024)
        assert http.post('/api/scan/ocr', files={"file": ("pack.png", oversized, "image/png")}).status_code == 400
        image = io.BytesIO()
        Image.new('RGB', (12, 12), 'white').save(image, format='PNG')
        failed = http.post('/api/scan/ocr', files={"file": ("pack.png", image.getvalue(), "image/png")})
        assert failed.status_code == 502
        assert 'provider unavailable' not in failed.text
    finally:
        app.dependency_overrides.pop(sarvam_service, None)


def test_ocr_missing_or_wrong_batch_needs_human_correction(client):
    http, sessions = client
    with sessions() as db:
        db.add(Alert(**normalize_record({"product_name": "दवा A", "manufacturer": "Maker A", "batch_number": "B12",
                                         "quality_issue": "Dissolution", "reporting_period": "AUG-2026"}, "AUG-2026"), run_id="run-1"))
        db.commit()
    class IncompleteOCR:
        def ocr(self, raw, filename, mime):
            return {"fields": {"medicine_name": "दवा A", "manufacturer": "Maker A", "batch_number": "",
                               "strength": "", "manufacturing_date": "", "expiry_date": "", "original_text": "दवा A"},
                    "original": {"result": {"original_text": "दवा A"}}, "status": "completed"}
    app.dependency_overrides[sarvam_service] = lambda: IncompleteOCR()
    try:
        image = io.BytesIO()
        Image.new('RGB', (12, 12), 'white').save(image, format='PNG')
        extracted = http.post('/api/scan/ocr', files={"file": ("pack.png", image.getvalue(), "image/png")})
        assert extracted.status_code == 200
        assert extracted.json()['fields']['batch_number'] == ''
        assert extracted.json()['requires_confirmation'] is True
    finally:
        app.dependency_overrides.pop(sarvam_service, None)
    base = {"medicine_name": "दवा A", "manufacturer": "Maker A", "confirmed": True}
    wrong = http.post('/api/scan/match', json={**base, "batch_number": "B13"})
    assert wrong.status_code == 200 and wrong.json()['matches'] == []
    corrected = http.post('/api/scan/match', json={**base, "batch_number": "B12"})
    assert corrected.json()['matches'][0]['status'] == 'potential_match'
