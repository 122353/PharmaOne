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
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine,autoflush=False,expire_on_commit=False)
    identity={"user":"user-a"}
    def db():
        with sessions() as session:yield session
    app.dependency_overrides[get_db]=db
    app.dependency_overrides[current_user]=lambda:identity["user"]
    with TestClient(app) as http:yield http,sessions,identity
    app.dependency_overrides.clear()


def test_synthetic_supplier_exposure_is_private(client):
    http, sessions, identity = client
    http.put('/api/pharmacies/current', json={"name": "A Pharmacy"})
    with sessions() as db:
        db.add(Alert(**normalize_record({"product_name":"Drug A","manufacturer":"Maker A","batch_number":"B12","quality_issue":"Dissolution","reporting_period":"AUG-2026"},"AUG-2026"),run_id="run-1"))
        db.commit()
    http.post('/api/inventory/import',files={"file":("stock.csv",b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nDrug A,Maker A,B12,10mg,2027-01-01,1\n","text/csv")})
    item_id=http.get('/api/inventory').json()[0]['id']
    created=http.post('/api/suppliers/links',json={"inventory_id":item_id,"supplier":"Synthetic Supplier","distributor":"Synthetic Distributor"})
    assert created.status_code==200, created.text
    graph=http.get('/api/suppliers/exposure').json()
    assert graph[0]['synthetic'] is True and graph[0]['potential_exposure'] is True
    identity['user']='user-b'
    http.put('/api/pharmacies/current',json={"name":"B Pharmacy"})
    assert http.get('/api/suppliers/exposure').json()==[]
    assert http.post('/api/suppliers/links',json={"inventory_id":item_id,"supplier":"Leak","distributor":"Leak"}).status_code==404
