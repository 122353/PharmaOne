from datetime import datetime, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import Alert, AlertVersion
from app.tinyfish import normalize_record
from app.ingestion import store_records


def test_retrieved_alert_is_deduplicated_and_refreshes_provenance():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine)
    row={"product_name":"Linezolid Tablets IP 600mg","manufacturer":"Symbiosis Pharmaceuticals","batch_number":"TG261185","reporting_period":"AUG-2026","quality_issue":"Dissolution"}
    record=normalize_record(row,'AUG-2026')
    with Session() as db:
        assert store_records(db,[record],'run-1')==1
        first=db.scalar(select(Alert))
        first_checked=first.retrieved_at
        changed=normalize_record({**row,"quality_issue":"Revised result"},'AUG-2026')
        assert store_records(db,[changed],'run-2')==0
        alerts=db.scalars(select(Alert)).all()
        assert len(alerts)==1
        assert alerts[0].quality_issue=='Revised result'
        assert alerts[0].run_id=='run-2'
        assert alerts[0].retrieved_at>=first_checked
        assert len(db.scalars(select(AlertVersion)).all())==2


def test_nonsemantic_source_format_change_does_not_create_new_version():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine)
    row={"product_name":"Drug A","manufacturer":"Maker A","batch_number":"B12","reporting_period":"AUG-2026","quality_issue":"Dissolution"}
    with Session() as db:
        store_records(db,[normalize_record(row,'AUG-2026')],'run-1')
        reformatted={**row,"quality_issue":"  Dissolution  ","page_layout":"revised"}
        store_records(db,[normalize_record(reformatted,'AUG-2026')],'run-2')
        assert len(db.scalars(select(AlertVersion)).all())==1
