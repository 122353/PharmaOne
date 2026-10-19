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


@pytest.mark.parametrize("raw,reason", [
    (b"", "CSV columns"),
    (b"medicine_name,quantity\nDrug A,1\n", "CSV columns"),
    (b"x" * (2 * 1024 * 1024 + 1), "2 MB"),
    (b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\n" + b"Drug A,Maker,B1,10mg,2027-01-01,1\n" * 5001, "5000 rows"),
    (b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nDrug A,Maker,B1,10mg,2027-01-01,1\n".replace(b"Drug A", b"\xff"), "UTF-8"),
], ids=["empty", "missing-columns", "oversize", "too-many-rows", "invalid-utf8"])
def test_csv_rejects_invalid_file_shapes(raw, reason):
    with pytest.raises(ValueError, match=reason):
        parse_csv(raw)


def test_csv_partial_import_reports_invalid_date_and_retains_unicode():
    raw = "medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nऔषधि A,Example Labs,बॅच-1,10mg,2027-01-01,2\nDrug B,Example Labs,B2,10mg,not-a-date,2\n".encode()
    rows, errors = parse_csv(raw)
    assert len(rows) == 1 and rows[0]["medicine_name"] == "औषधि A"
    assert rows[0]["batch_number"] == "बॅच-1"
    assert len(errors) == 1 and errors[0]["row"] == 3


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
    ({"medicine_name":"Linezolid 300mg"}, "needs_verification"),
    ({"manufacturer":"Symbiosis Pharmaceuticals Private Limited"}, "potential_match"),
    ({"batch_number":"TG 261185"}, "potential_match"),
    ({"batch_number":"TG-261185"}, "no_identified_match"),
    ({"medicine_name":""}, "needs_verification"),
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


def test_tinyfish_sse_adapter_extracts_real_response_shape_without_network(monkeypatch):
    import json
    import httpx
    from app import tinyfish

    real_client = httpx.Client
    observed = {}
    row = {"product_name": "Synthetic Test Medicine", "manufacturer": "Example Labs", "batch_number": "SYN123", "quality_issue": "Synthetic test finding", "reporting_source": "Test source", "reporting_period": "AUG-2026"}
    event = {"type": "COMPLETE", "status": "COMPLETED", "run_id": "mock-provider-id", "resultJson": {"records": [row]}}

    def respond(request):
        observed["url"] = str(request.url)
        observed["key"] = request.headers.get("X-API-Key")
        observed["goal"] = json.loads(request.content)["goal"]
        return httpx.Response(200, text="data: " + json.dumps(event) + "\n\n", headers={"content-type": "text/event-stream"})

    monkeypatch.setattr(tinyfish.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    records, run_id = tinyfish.retrieve("synthetic-key", "AUG-2026", 1)
    assert observed["url"] == tinyfish.ENDPOINT
    assert observed["key"] == "synthetic-key"
    assert "AUG-2026" in observed["goal"]
    assert run_id == "mock-provider-id"
    assert records[0]["product_name"] == row["product_name"]
    assert records[0]["source_url"] == tinyfish.SOURCE_URL
