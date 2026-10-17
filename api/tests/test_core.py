import io
import pytest
from fastapi.testclient import TestClient

from app.matching import compare
from app.csv_import import parse_csv


def test_exact_match_needs_same_manufacturer_and_batch():
    alert = {"product_name": "Linezolid Tablets IP 600mg", "manufacturer": "Symbiosis Pharmaceuticals Pvt. Ltd.", "batch_number": "TG261185"}
    item = {"medicine_name": "Linezolid Tablets IP 600mg", "manufacturer": "Symbiosis Pharmaceuticals Pvt Ltd", "batch_number": "tg261185"}
    assert compare(item, alert)[0] == "potential_match"
    assert compare({**item, "batch_number": "OTHER"}, alert)[0] == "no_identified_match"
    assert compare({**item, "manufacturer": "Different Labs"}, alert)[0] == "needs_verification"
    assert compare({**item, "manufacturer": ""}, alert)[0] == "needs_verification"


def test_csv_rejects_formula_and_reports_missing_identifier():
    raw = b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nLinezolid,,TG261185,600mg,2027-01-01,4\n=HYPERLINK(1),X,Y,,,1\n"
    rows, errors = parse_csv(raw)
    assert len(rows) == 1
    assert rows[0]["quality_state"] == "needs_verification"
    assert errors[0]["row"] == 3


def test_auth_required_for_private_api():
    from app.main import app
    client = TestClient(app)
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize("change,expected", [
    ({}, "potential_match"),
    ({"batch_number":"TG261186"}, "no_identified_match"),
    ({"batch_number":" tg261185 "}, "potential_match"),
    ({"batch_number":""}, "needs_verification"),
    ({"manufacturer":""}, "needs_verification"),
    ({"manufacturer":"Different Laboratories"}, "needs_verification"),
    ({"medicine_name":"Other Product"}, "no_identified_match"),
    ({"medicine_name":"Linezolid Tablets 600mg"}, "potential_match"),
    ({"medicine_name":"Linezolid 300mg"}, "no_identified_match"),
    ({"manufacturer":"Symbiosis Pharmaceuticals Private Limited"}, "potential_match"),
    ({"batch_number":"TG 261185"}, "potential_match"),
    ({"batch_number":"TG-261185"}, "no_identified_match"),
    ({"medicine_name":""}, "no_identified_match"),
    ({"manufacturer":"Symbiosis Pharmaceuticals"}, "potential_match"),
    ({"manufacturer":"Pharmaceuticals"}, "needs_verification"),
    ({"batch_number":"tg261185"}, "potential_match"),
])
def test_matching_matrix(change, expected):
    source={"product_name":"Linezolid Tablets IP 600mg","manufacturer":"Symbiosis Pharmaceuticals Pvt. Ltd.","batch_number":"TG261185"}
    stock={"medicine_name":"Linezolid Tablets IP 600mg","manufacturer":"Symbiosis Pharmaceuticals Pvt Ltd","batch_number":"TG261185"}
    assert compare({**stock,**change},source)[0] == expected


def test_nsq_normalization_requires_source_identifiers():
    from app.tinyfish import normalize_record, fingerprint
    record = normalize_record({"Name of Product":"Linezolid Tablets IP 600mg","Manufactured By":"Symbiosis Pharmaceuticals","Batch No":"TG261185","NSQ Result":"Dissolution","Reporting Month & Year":"AUG-2026"}, "AUG-2026")
    assert record["classification"] == "nsq"
    assert record["source_url"].startswith("https://cdscoonline.gov.in/")
    assert record["fingerprint"] == fingerprint(record)
    with pytest.raises(ValueError):
        normalize_record({"Name of Product":"Linezolid"}, "AUG-2026")
    with pytest.raises(ValueError):
        normalize_record({"Name of Product":"Linezolid","Batch No":"B1","Reporting Month & Year":"JUL-2026"}, "AUG-2026")
    with pytest.raises(ValueError):
        normalize_record({"Name of Product":"Linezolid","Batch No":"B1"}, "AUG-2026")


def test_tinyfish_complete_event_extracts_result_json():
    from app.tinyfish import extract_result
    event={"type":"COMPLETE","status":"COMPLETED","resultJson":{"records":[{"product_name":"Linezolid"}]}}
    assert extract_result(event) == [{"product_name":"Linezolid"}]
