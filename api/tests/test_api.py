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


def test_investigation_checklist_and_review_history_persist(client):
    http,sessions,_=client
    http.put('/api/pharmacies/current',json={"name":"A Pharmacy"})
    with sessions() as db:
        db.add(Alert(**normalize_record({"product_name":"Drug A","manufacturer":"Maker A","batch_number":"B12","quality_issue":"Dissolution","reporting_period":"AUG-2026"},"AUG-2026"),run_id="run-1"))
        db.commit()
    http.post('/api/inventory/import',files={"file":("stock.csv",b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nDrug A,Maker A,B12,10mg,2027-01-01,1\n","text/csv")})
    mid=http.get('/api/matches').json()[0]['id']
    saved=http.post('/api/investigations',json={"match_id":mid,"status":"physical_verification_pending","note":"Check package","record_reviewed":True,"physical_verified":False})
    assert saved.status_code==200,saved.text
    assert saved.json()['record_reviewed'] is True
    assert saved.json()['physical_verified'] is False
    events=http.get('/api/investigations/'+saved.json()['id']+'/events').json()
    assert events[-1]['detail']['record_reviewed'] is True
    current = http.get('/api/investigations').json()[0]
    assert current['status'] == 'under_investigation'
    assert current['physical_status'] == 'pending'


def test_investigation_repeated_actions_do_not_duplicate_events_or_erase_review(client):
    http, sessions, _ = client
    http.put('/api/pharmacies/current', json={"name": "A Pharmacy"})
    with sessions() as db:
        db.add(Alert(**normalize_record({"product_name": "Drug A", "manufacturer": "Maker A",
                                         "batch_number": "B12", "quality_issue": "Dissolution",
                                         "reporting_period": "AUG-2026"}, "AUG-2026"), run_id="run-1"))
        db.commit()
    http.post('/api/inventory/import', files={"file": ("stock.csv", b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nDrug A,Maker A,B12,10mg,2027-01-01,1\n", "text/csv")})
    match_id = http.get('/api/matches').json()[0]['id']
    start = {"match_id": match_id, "status": "under_investigation", "note": "Review source", "record_reviewed": True}
    first = http.post('/api/investigations', json=start)
    assert first.status_code == 200
    record_id = first.json()['id']
    assert http.post('/api/investigations', json=start).status_code == 200
    assert len(http.get(f'/api/investigations/{record_id}/events').json()) == 1
    hold = {**start, "status": "simulated_hold", "note": ""}
    held = http.post('/api/investigations', json=hold)
    assert held.status_code == 200
    assert held.json()['status'] == 'under_investigation'
    assert held.json()['simulated_hold'] is True
    assert held.json()['note'] == 'Review source'
    assert http.post('/api/investigations', json=hold).status_code == 200
    assert len(http.get(f'/api/investigations/{record_id}/events').json()) == 2
    persisted = http.get('/api/investigations').json()[0]
    assert persisted['status'] == 'under_investigation'
    assert persisted['simulated_hold'] is True
    assert persisted['record_reviewed'] is True


def test_investigation_evidence_attachment_is_private(client):
    import io
    from PIL import Image
    http,sessions,identity=client
    http.put('/api/pharmacies/current',json={"name":"A Pharmacy"})
    with sessions() as db:
        db.add(Alert(**normalize_record({"product_name":"Drug A","manufacturer":"Maker A","batch_number":"B12","quality_issue":"Dissolution","reporting_period":"AUG-2026"},"AUG-2026"),run_id="run-1"))
        db.commit()
    http.post('/api/inventory/import',files={"file":("stock.csv",b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nDrug A,Maker A,B12,10mg,2027-01-01,1\n","text/csv")})
    mid=http.get('/api/matches').json()[0]['id']
    record=http.post('/api/investigations',json={"match_id":mid,"status":"open","note":"Review evidence"}).json()
    target='/api/investigations/'+record['id']+'/attachments'
    assert http.post(target,files={"file":("broken.png",b"\x89PNG\r\n\x1a\ninvalid","image/png")}).status_code==400
    assert http.post(target,files={"file":("broken.pdf",b"%PDF-1.7\nnot a document","application/pdf")}).status_code==400
    assert http.post(target,files={"file":("oversize.png",b"x"*(2*1024*1024+1),"image/png")}).status_code==400
    image=io.BytesIO();Image.new('RGB',(10,10),'white').save(image,format='PNG')
    uploaded=http.post(target,files={"file":("evidence.png",image.getvalue(),"image/png")})
    assert uploaded.status_code==200,uploaded.text
    attachment_id=uploaded.json()['id']
    assert len(http.get('/api/investigations/'+record['id']+'/attachments').json())==1
    assert http.get('/api/investigations/attachments/'+attachment_id).content==image.getvalue()
    identity['user']='user-b'
    http.put('/api/pharmacies/current',json={"name":"B Pharmacy"})
    assert http.get('/api/investigations/'+record['id']+'/attachments').status_code==404
    assert http.get('/api/investigations/attachments/'+attachment_id).status_code==404


def test_paid_sync_and_byok_routes_are_not_available_to_pharmacies(client):
    http, _, _ = client
    http.put('/api/pharmacies/current', json={"name": "A Pharmacy"})
    assert http.post('/api/ingestion/sync', json={"period": "AUG-2026", "account": "mine"}).status_code == 404
    assert http.post('/api/integrations/tinyfish', json={"api_key": "synthetic-key-123"}).status_code == 404
    assert http.get('/api/integrations/tinyfish').status_code == 404
    assert http.delete('/api/integrations/tinyfish').status_code == 404


def test_regulatory_change_history_is_scoped_to_own_inventory(client):
    from app.ingestion import store_records
    http, sessions, identity = client
    http.put('/api/pharmacies/current', json={"name": "A Pharmacy"})
    row={"product_name":"Drug A","manufacturer":"Maker A","batch_number":"B12","quality_issue":"Dissolution","reporting_period":"AUG-2026"}
    with sessions() as db:
        store_records(db,[normalize_record(row,'AUG-2026')],'run-1')
        store_records(db,[normalize_record({**row,"quality_issue":"Updated finding"},'AUG-2026')],'run-2')
    http.post('/api/inventory/import',files={"file":("stock.csv",b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nDrug A,Maker A,B12,10mg,2027-01-01,1\n","text/csv")})
    changed=http.get('/api/regulatory/changes')
    assert changed.status_code==200
    assert [x['kind'] for x in changed.json()] == ['updated','added']
    assert changed.json()[0]['own_inventory_impact'] is True
    identity['user']='user-b'
    http.put('/api/pharmacies/current',json={"name":"B Pharmacy"})
    assert http.get('/api/regulatory/changes').json()[0]['own_inventory_impact'] is False


def test_failed_sync_retains_last_successful_check_time(client):
    from app.models import IngestionRun
    from datetime import datetime, timezone, timedelta
    http, sessions, _ = client
    with sessions() as db:
        earlier = datetime.now(timezone.utc)-timedelta(days=1)
        db.add(IngestionRun(period='JUL-2026',source_kind='operator_live',status='succeeded',record_count=5,started_at=earlier,finished_at=earlier))
        db.add(IngestionRun(period='AUG-2026',source_kind='operator_live',status='failed',error='Source unavailable',record_count=0,started_at=datetime.now(timezone.utc),finished_at=datetime.now(timezone.utc)))
        db.commit()
    result = http.get('/api/ingestion/status').json()
    assert result['state'] == 'unavailable'
    assert result['record_count'] == 5
    assert result['last_checked'] is not None


def test_historical_snapshot_is_not_reported_as_a_live_source_check(client):
    from datetime import datetime, timezone
    from app.models import IngestionRun
    http, sessions, _ = client
    imported_at = datetime.now(timezone.utc)
    with sessions() as db:
        db.add(IngestionRun(
            period='AUG-2026', source_kind='historical_snapshot', status='succeeded',
            record_count=5, started_at=imported_at, finished_at=imported_at,
            provider_run_id='verified-snapshot-run',
            retrieval_metadata={'imported_as_historical': True},
        ))
        db.commit()
    result = http.get('/api/ingestion/status').json()
    assert result['state'] == 'historical_snapshot'
    assert result['last_checked'] is None
    assert result['historical_snapshot_imported'] is True
    assert result['snapshot_reporting_period'] == 'AUG-2026'


def test_inventory_edit_rejects_duplicate_identity(client):
    http, _, _ = client
    http.put('/api/pharmacies/current',json={"name":"A Pharmacy"})
    csv=b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nDrug A,Maker A,B1,10mg,2027-01-01,1\nDrug A,Maker A,B2,10mg,2027-01-01,1\n"
    assert http.post('/api/inventory/import',files={"file":("stock.csv",io.BytesIO(csv),"text/csv")}).status_code==200
    items=http.get('/api/inventory').json()
    edited=http.patch('/api/inventory/'+items[0]['id'],json={**items[1],"quantity":2})
    assert edited.status_code==409


def test_duplicate_rows_in_one_upload_are_skipped(client):
    http, _, _ = client
    http.put('/api/pharmacies/current', json={"name": "A Pharmacy"})
    row = b"Drug A,Maker A,B1,10mg,2027-01-01,1\n"
    csv = b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\n" + row + row
    result = http.post('/api/inventory/import', files={"file": ("stock.csv", io.BytesIO(csv), "text/csv")})
    assert result.status_code == 200, result.text
    assert result.json()["imported"] == 1
    assert result.json()["duplicates"] == 1
    assert len(http.get('/api/inventory').json()) == 1


def test_import_history_and_synthetic_mock_connector_are_private(client):
    http, _, identity=client
    http.put('/api/pharmacies/current',json={"name":"A Pharmacy"})
    response=http.post('/api/inventory/connectors/mock/import')
    assert response.status_code==200,response.text
    assert response.json()['imported']==1
    assert http.get('/api/inventory/imports').json()[0]['source']=='synthetic_mock_erp'
    assert http.post('/api/inventory/connectors/mock/import').json()['duplicates']==1
    identity['user']='user-b'
    http.put('/api/pharmacies/current',json={"name":"B Pharmacy"})
    assert http.get('/api/inventory/imports').json()==[]


def test_inventory_edit_rejects_invalid_expiry(client):
    http, _, _ = client
    http.put('/api/pharmacies/current', json={"name": "A Pharmacy"})
    csv = b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nDrug A,Maker A,B1,10mg,2027-01-01,1\n"
    http.post('/api/inventory/import', files={"file": ("stock.csv", io.BytesIO(csv), "text/csv")})
    item = http.get('/api/inventory').json()[0]
    result = http.patch('/api/inventory/' + item['id'], json={**item, "expiry_date": "not-a-date"})
    assert result.status_code == 422
    assert http.get('/api/inventory').json()[0]['expiry_date'] == "2027-01-01"


def test_source_status_does_not_expose_another_users_run(client):
    from app.models import IngestionRun
    http, sessions, identity = client
    with sessions() as db:
        db.add(IngestionRun(period='AUG-2026', requesting_user_id='user-a', status='failed', error='Private provider status'))
        db.commit()
    identity['user'] = 'user-b'
    status = http.get('/api/ingestion/status')
    assert status.status_code == 200
    assert status.json()['state'] == 'never_synced'
    assert 'Private provider status' not in status.text
