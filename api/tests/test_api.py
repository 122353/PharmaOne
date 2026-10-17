import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.auth import current_user
from app.main import app
from app.models import Alert
from app.tinyfish import normalize_record


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    identity = {"user": "user-a"}
    def db():
        with sessions() as session:
            yield session
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[current_user] = lambda: identity["user"]
    with TestClient(app) as test_client:
        yield test_client, sessions, identity
    app.dependency_overrides.clear()


def test_tenant_isolation_and_investigation_survives_recheck(client):
    http, sessions, identity = client
    assert http.put('/api/pharmacies/current', json={"name":"A Pharmacy"}).status_code == 200
    with sessions() as db:
        record = normalize_record({"product_name":"Linezolid Tablets IP 600mg","manufacturer":"Symbiosis Pharmaceuticals Pvt. Ltd.","batch_number":"TG261185","quality_issue":"Dissolution","reporting_period":"AUG-2026"}, "AUG-2026")
        db.add(Alert(**record, run_id="run-1"))
        db.commit()
    csv = b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nLinezolid Tablets IP 600mg,Symbiosis Pharmaceuticals Pvt Ltd,TG261185,600mg,2027-01-01,4\n"
    response = http.post('/api/inventory/import', files={"file":("stock.csv", io.BytesIO(csv), "text/csv")})
    assert response.status_code == 200, response.text
    matches = http.get('/api/matches').json()
    assert len(matches) == 1 and matches[0]['status'] == 'potential_match'
    mid = matches[0]['id']
    item_id = matches[0]['inventory']['id']
    edited = http.patch('/api/inventory/'+item_id, json={"medicine_name":"Linezolid Tablets IP 600mg","manufacturer":"Symbiosis Pharmaceuticals Pvt Ltd","batch_number":"TG261185","strength":"600mg","expiry_date":"2027-01-01","quantity":5})
    assert edited.status_code == 200, edited.text
    assert http.post('/api/investigations', json={"match_id":mid,"status":"simulated_hold","note":"Training only"}).status_code == 200
    assert http.post('/api/matches/recheck').status_code == 200
    assert http.get('/api/matches').json()[0]['id'] == mid
    assert http.get('/api/investigations').json()[0]['match_id'] == mid
    identity['user'] = 'user-b'
    assert http.get('/api/inventory').status_code == 404
    assert http.get('/api/investigations').status_code == 404
    assert http.get('/api/matches').status_code == 404
    assert http.put('/api/pharmacies/current', json={"name":"B Pharmacy"}).status_code == 200
    assert http.get('/api/inventory').json() == []
    assert http.get('/api/investigations').json() == []


def test_missing_key_cannot_start_paid_job(client):
    http, _, _ = client
    http.put('/api/pharmacies/current',json={"name":"A Pharmacy"})
    response = http.post('/api/ingestion/sync',json={"period":"AUG-2026","account":"mine"})
    assert response.status_code == 409


def test_tinyfish_connection_is_owner_scoped_and_never_returns_plaintext(client, monkeypatch):
    import base64
    from app import crypto
    from app.config import settings
    monkeypatch.setenv('TINYFISH_ENCRYPTION_KEY',base64.urlsafe_b64encode(b'a'*32).decode())
    settings.cache_clear()
    http, sessions, identity = client
    key = 'tf_test_user_a_secret_12345'
    response = http.post('/api/integrations/tinyfish',json={"api_key":key})
    assert response.status_code == 200
    assert key not in response.text
    with sessions() as db:
        from app.models import TinyfishConnection
        stored = db.query(TinyfishConnection).one()
        assert key not in stored.encrypted_key
        assert crypto.decrypt(stored.encrypted_key) == key
    identity['user'] = 'user-b'
    assert http.get('/api/integrations/tinyfish').json()['connected'] is False
    assert http.delete('/api/integrations/tinyfish').json()['connected'] is False
    identity['user'] = 'user-a'
    assert http.get('/api/integrations/tinyfish').json()['connected'] is True
    settings.cache_clear()


def test_failed_sync_retains_last_successful_check_time(client):
    from app.models import IngestionRun
    from datetime import datetime, timezone, timedelta
    http, sessions, _ = client
    with sessions() as db:
        earlier = datetime.now(timezone.utc)-timedelta(days=1)
        db.add(IngestionRun(period='JUL-2026',status='succeeded',record_count=5,started_at=earlier,finished_at=earlier))
        db.add(IngestionRun(period='AUG-2026',status='failed',error='Source unavailable',record_count=0,started_at=datetime.now(timezone.utc),finished_at=datetime.now(timezone.utc)))
        db.commit()
    result = http.get('/api/ingestion/status').json()
    assert result['state'] == 'failed'
    assert result['record_count'] == 5
    assert result['last_checked'] is not None


def test_inventory_edit_rejects_duplicate_identity(client):
    http, _, _ = client
    http.put('/api/pharmacies/current',json={"name":"A Pharmacy"})
    csv=b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nDrug A,Maker A,B1,10mg,2027-01-01,1\nDrug A,Maker A,B2,10mg,2027-01-01,1\n"
    assert http.post('/api/inventory/import',files={"file":("stock.csv",io.BytesIO(csv),"text/csv")}).status_code==200
    items=http.get('/api/inventory').json()
    edited=http.patch('/api/inventory/'+items[0]['id'],json={**items[1],"quantity":2})
    assert edited.status_code==409
