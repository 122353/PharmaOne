import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.auth import current_user
from app.main import app
from app.contextos import sarvam_service, system_prompt, validate_generated_answer
from app.models import Alert, AuditEvent, Pharmacy
from app.tinyfish import normalize_record


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    identity = {"user": "user-a"}
    def db():
        with sessions() as session:
            yield session
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[current_user] = lambda: identity["user"]
    with TestClient(app) as test_client:
        yield test_client, sessions, identity
    app.dependency_overrides.clear()


class FakeSarvam:
    def chat(self, messages):
        assert "TG261185" in messages[-1]["content"]
        assert "supplied official record" in messages[0]["content"]
        return "TG261185 appears in the official NSQ evidence. Verify the pack physically."


def test_contextos_grounded_and_isolated(client):
    http, sessions, identity = client
    http.put('/api/pharmacies/current', json={"name": "A Pharmacy"})
    with sessions() as db:
        record = normalize_record({"product_name": "Drug A", "manufacturer": "Maker A", "batch_number": "TG261185", "quality_issue": "Dissolution", "reporting_period": "AUG-2026"}, "AUG-2026")
        db.add(Alert(**record, run_id="run-1"))
        db.commit()
    http.post('/api/inventory/import', files={"file": ("stock.csv", b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nDrug A,Maker A,TG261185,10mg,2027-01-01,1\n", "text/csv")})
    alert_id = http.get('/api/alerts').json()[0]['fingerprint']
    app.dependency_overrides[sarvam_service] = lambda: FakeSarvam()
    try:
        response = http.post('/api/contextos/ask', json={"question": "Why flagged?", "alert_id": alert_id, "language": "en"})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['mode'] == 'sarvam'
        assert data['evidence'][0]['batch_number'] == 'TG261185'
        assert data['evidence'][0]['source_url'].startswith('https://cdscoonline.gov.in/')
        assert data['inventory_match'] == 'potential_match'
        identity['user'] = 'user-b'
        http.put('/api/pharmacies/current', json={"name": "B Pharmacy"})
        other = http.post('/api/contextos/ask', json={"question": "Do I have it?", "alert_id": alert_id})
        assert other.json()['inventory_match'] == 'not_in_inventory'
        assert 'A Pharmacy' not in str(other.json())
    finally:
        app.dependency_overrides.pop(sarvam_service, None)


def test_contextos_missing_evidence_and_fallback(client):
    http, _, _ = client
    http.put('/api/pharmacies/current', json={"name": "A Pharmacy"})
    app.dependency_overrides[sarvam_service] = lambda: None
    try:
        empty = http.post('/api/contextos/ask', json={"question": "Any issue?", "language": "hi"})
        assert empty.status_code == 200
        assert empty.json()['mode'] == 'evidence_only'
        assert empty.json()['evidence'] == []
        assert http.post('/api/contextos/ask', json={"question": "Any issue?", "alert_id": "unknown"}).status_code == 404
    finally:
        app.dependency_overrides.pop(sarvam_service, None)


def test_contextos_does_not_silently_choose_unrelated_global_alert(client):
    http, sessions, _ = client
    http.put('/api/pharmacies/current', json={"name": "A Pharmacy"})
    with sessions() as db:
        record = normalize_record({"product_name": "Unrelated Drug", "manufacturer": "Maker B",
                                   "batch_number": "OTHER123", "quality_issue": "Dissolution",
                                   "reporting_period": "AUG-2026"}, "AUG-2026")
        db.add(Alert(**record, run_id="run-1"))
        db.commit()
    class MustNotCall:
        def chat(self, _):
            raise AssertionError("An unrelated global alert must not be sent to Sarvam")
    app.dependency_overrides[sarvam_service] = lambda: MustNotCall()
    try:
        response = http.post('/api/contextos/ask', json={"question": "What is affecting my pharmacy?"})
        assert response.status_code == 200
        assert response.json()['mode'] == 'evidence_only'
        assert response.json()['evidence'] == []
        assert 'OTHER123' not in str(response.json())
    finally:
        app.dependency_overrides.pop(sarvam_service, None)


def test_alert_translation_keeps_original_identifiers(client):
    http,sessions,_=client
    http.put('/api/pharmacies/current',json={"name":"A Pharmacy"})
    with sessions() as db:
        record=normalize_record({"product_name":"Drug A","manufacturer":"Maker A","batch_number":"B12","quality_issue":"Dissolution failure","reporting_period":"AUG-2026"},"AUG-2026")
        db.add(Alert(**record,run_id="run-1"))
        db.commit()
    class Translator:
        def translate(self, value, target):
            assert value=='Dissolution failure' and target=='hi-IN'
            return 'घुलनशीलता परीक्षण विफल'
    app.dependency_overrides[sarvam_service]=lambda:Translator()
    try:
        result=http.post('/api/alerts/'+record['fingerprint']+'/translate',json={"language":"hi"})
        assert result.status_code==200,result.text
        assert result.json()['original']=='Dissolution failure'
        assert result.json()['translated']=='घुलनशीलता परीक्षण विफल'
        assert result.json()['batch_number']=='B12'
    finally:
        app.dependency_overrides.pop(sarvam_service,None)


def test_contextos_rejects_unverified_batch_claim(client):
    http,sessions,_=client
    http.put('/api/pharmacies/current',json={"name":"A Pharmacy"})
    with sessions() as db:
        record=normalize_record({"product_name":"Drug A","manufacturer":"Maker A","batch_number":"B12","quality_issue":"Dissolution failure","reporting_period":"AUG-2026"},"AUG-2026")
        db.add(Alert(**record,run_id="run-1"))
        db.commit()
    class WrongBatch:
        def chat(self,messages):return 'Official batch B12 and batch B99 are both affected.'
    app.dependency_overrides[sarvam_service]=lambda:WrongBatch()
    try:
        response=http.post('/api/contextos/ask',json={"question":"Which batch?","alert_id":record['fingerprint']})
        assert response.json()['mode']=='evidence_only'
        assert 'B99' not in response.json()['answer']
        assert response.json()['fallback_reason']=='invented_batch'
        with sessions() as db:
            assert db.query(AuditEvent).filter(AuditEvent.action=='contextos_query').first().detail['outcome']=='invented_batch'
    finally:
        app.dependency_overrides.pop(sarvam_service,None)


@pytest.mark.parametrize("answer,expected", [
    ("Batch VRNT-933 has an NSQ dissolution finding. This is not automatically a recall.", None),
    ("Batch VRNT-933 has an NSQ finding. Verify batch and manufacturer.", None),
    ("The VRNT-933 batch has a Dissolution finding. Verify batch and manufacturer.", None),
    ("The batch of VRNT-933 has a Dissolution finding.", None),
    ("The batch was flagged for dissolution; its number is VRNT-933.", None),
    ("Batch VRNT-933 has an NSQ finding. This is not a recall order.", None),
    ("Batch VRNT-933 has an NSQ finding. This does not mean a recall order.", None),
    ("Batch VRNT-933 has an NSQ finding. This is not an official recall order.", None),
    ("आधिकारिक रिकॉर्ड में बैच VRNT-933 के लिए घुलनशीलता निष्कर्ष है। यह रिकॉल आदेश नहीं है।", None),
    ("The medicine has a dissolution finding.", "missing_batch"),
    ("Batch VRNT-933 and batch VRNT-934 are affected.", "invented_batch"),
    ("Batch VRNT-933 and batch of VRNT-934 are affected.", "invented_batch"),
    ("Batch VRNT-933 and batch: OTHER are affected.", "invented_batch"),
    ("Batch VRNT-933 has been recalled by the authority.", "unsupported_regulatory_order"),
    ("A recall order has been issued for batch VRNT-933.", "unsupported_regulatory_order"),
    ("Batch VRNT-933 is not a recall order, but it must not be dispensed.", "unsupported_regulatory_order"),
    ("A hold has been placed for batch VRNT-933.", "unsupported_regulatory_order"),
    ("Batch VRNT-933 must not be dispensed.", "unsupported_regulatory_order"),
])
def test_contextos_answer_validation(answer, expected):
    assert validate_generated_answer(answer, "VRNT-933") == expected


@pytest.mark.parametrize("language", ["en", "hi"])
def test_contextos_prompt_limits_generated_claims(language):
    prompt = system_prompt(language)
    assert "exact batch" in prompt
    assert "listed quality finding" in prompt
    assert "Do not discuss recalls, dispensing, sales, restrictions, or stock holds" in prompt
    assert ("Respond in Hindi." if language == "hi" else "Respond in English.") in prompt


def test_contextos_accepts_negative_recall_statement_with_official_evidence(client):
    http, sessions, _ = client
    http.put('/api/pharmacies/current', json={"name": "Synthetic Pharmacy"})
    with sessions() as db:
        record = normalize_record({"product_name": "Montelukast sodium & Levocetirizine hydrochloride Tablets IP",
                                   "manufacturer": "Vrihaan Pharmaceuticals LLP", "batch_number": "VRNT-933",
                                   "quality_issue": "Dissolution", "reporting_period": "AUG-2026"}, "AUG-2026")
        db.add(Alert(**record, run_id="synthetic-run"))
        db.commit()
    class NegativeRecall:
        def chat(self, _):
            return "Batch VRNT-933 has an NSQ dissolution finding. This is not automatically a recall. Verify the pack."
    app.dependency_overrides[sarvam_service] = lambda: NegativeRecall()
    try:
        response = http.post('/api/contextos/ask', json={"question": "Why flagged?", "alert_id": record['fingerprint']})
        assert response.status_code == 200
        assert response.json()['mode'] == 'sarvam'
        assert response.json()['fallback_reason'] is None
        assert response.json()['evidence'][0]['source_url'].startswith('https://cdscoonline.gov.in/')
    finally:
        app.dependency_overrides.pop(sarvam_service, None)


def test_contextos_daily_cap_prevents_provider_call(client):
    http, sessions, _ = client
    http.put('/api/pharmacies/current', json={"name": "Synthetic Pharmacy"})
    record = normalize_record({"product_name": "Synthetic Drug", "manufacturer": "Synthetic Maker",
                               "batch_number": "SYN123", "quality_issue": "Dissolution",
                               "reporting_period": "AUG-2026"}, "AUG-2026")
    with sessions() as db:
        db.add(Alert(**record, run_id="synthetic-run"))
        pharmacy = db.query(Pharmacy).first()
        for _ in range(20):
            db.add(AuditEvent(pharmacy_id=pharmacy.id, actor_id="user-a", action="contextos_query",
                              entity_id=record["fingerprint"][:36], detail={"outcome": "synthetic"}))
        db.commit()
    class MustNotCall:
        def chat(self, _):
            raise AssertionError("Daily cap must stop a provider request")
    app.dependency_overrides[sarvam_service] = lambda: MustNotCall()
    try:
        response = http.post('/api/contextos/ask', json={"question": "Why flagged?", "alert_id": record['fingerprint']})
        assert response.status_code == 429
    finally:
        app.dependency_overrides.pop(sarvam_service, None)
