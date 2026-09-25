"""HTTP contract, persistence, filtering, fault injection, and concurrent writes."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from itertools import combinations
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.database import Patient
from backend.app.schemas import PatientCreate


def envelope(response, status):
    assert response.status_code == status, response.text
    result = response.json()
    assert set(result) == {"data", "error"}
    assert (result["error"] is None) == (status < 400)
    if status >= 400:
        assert result["data"] is None
    return result


def test_health_docs_and_openapi(client):
    assert envelope(client.get("/health"), 200)["data"] == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {
        "/health", "/patients", "/patients/{patient_id}",
        "/vapi/lookup-patient-by-phone", "/vapi/update-patient",
    }
    assert "201" in schema["paths"]["/patients"]["post"]["responses"]
    for path in schema["paths"].values():
        for operation in path.values():
            for response in operation["responses"].values():
                reference = response["content"]["application/json"]["schema"]["$ref"]
                shape = schema["components"]["schemas"][reference.rsplit("/", 1)[-1]]
                assert set(shape["properties"]) == {"data", "error"}


def test_crud_persistence_and_soft_delete(client, created, db):
    identity = created["patient_id"]
    assert UUID(identity).version == 4
    url = f"/patients/{identity}"
    assert envelope(client.get(url), 200)["data"] == created
    updated = envelope(client.put(url, json={"city": "Boston"}), 200)["data"]
    assert updated["city"] == "Boston"
    assert updated["created_at"] == created["created_at"]
    assert datetime.fromisoformat(updated["updated_at"]) > datetime.fromisoformat(created["updated_at"])
    for key in set(created) - {"city", "updated_at"}:
        assert updated[key] == created[key]
    same = envelope(client.put(url, json={"city": "Boston"}), 200)["data"]
    assert same["updated_at"] > updated["updated_at"]
    deleted = envelope(client.delete(url), 200)["data"]
    assert deleted["deleted_at"] == deleted["updated_at"]
    assert deleted["created_at"] == created["created_at"]
    assert all(p["patient_id"] != identity for p in envelope(client.get("/patients"), 200)["data"])
    for method, kwargs in [("get", {}), ("put", {"json": {"city": "Boston"}}), ("delete", {})]:
        envelope(getattr(client, method)(url, **kwargs), 404)
    with db[1]() as session:
        stored = session.get(Patient, UUID(identity))
        assert stored is not None and stored.deleted_at is not None


def test_all_filter_combinations(client, created, payload):
    envelope(client.post("/patients", json={**payload, "phone_number": "2125550100", "last_name": "Other"}), 201)
    filters = {"last_name": "O'Neil", "date_of_birth": "1992-02-29", "phone_number": "2125550199"}
    for size in (1, 2, 3):
        for keys in combinations(filters, size):
            params = {key: filters[key] for key in keys}
            result = envelope(client.get("/patients", params=params), 200)["data"]
            assert any(p["patient_id"] == created["patient_id"] for p in result)
            assert all(all(p[key] == filters[key] for key in keys) for p in result)
    assert envelope(client.get("/patients", params={**filters, "last_name": "Other"}), 200)["data"] == []
    assert envelope(client.get("/patients", params={"last_name": " O'Neil "}), 200)["data"][0]["patient_id"] == created["patient_id"]


@pytest.mark.parametrize("field", [name for name, field in PatientCreate.model_fields.items() if not field.is_required()])
def test_optional_null_round_trip(client, payload, field):
    created = envelope(client.post("/patients", json={**payload, field: None}), 201)["data"]
    assert created[field] is None
    url = f"/patients/{created['patient_id']}"
    assert envelope(client.get(url), 200)["data"][field] is None
    non_null = {
        "email": "jamie@example.com", "address_line_2": "Unit 4",
        "insurance_provider": "Demo Insurance", "insurance_member_id": "ABC123",
        "preferred_language": "Spanish", "emergency_contact_name": "Alex Demo",
        "emergency_contact_phone": "2125550198",
    }
    assert envelope(client.put(url, json={field: non_null[field]}), 200)["data"][field] == non_null[field]
    assert envelope(client.put(url, json={field: None}), 200)["data"][field] is None
    assert envelope(client.get(url), 200)["data"][field] is None


def test_full_update_round_trip(client, created):
    values = {
        "first_name": "Alex", "last_name": "Smith-Jones", "date_of_birth": "1980-05-17",
        "sex": "Female", "phone_number": "4155550198", "email": "alex@example.com",
        "address_line_1": "456 Sample Avenue", "address_line_2": "Unit 7", "city": "San Francisco",
        "state": "CA", "zip_code": "94105-1234", "insurance_provider": "Demo Insurance",
        "insurance_member_id": "ABC123", "preferred_language": "Spanish",
        "emergency_contact_name": "Jamie Demo", "emergency_contact_phone": "4155550197",
    }
    url = f"/patients/{created['patient_id']}"
    updated = envelope(client.put(url, json=values), 200)["data"]
    assert {key: updated[key] for key in values} == values
    assert envelope(client.get(url), 200)["data"] == updated


@pytest.mark.parametrize("field", [name for name, field in PatientCreate.model_fields.items() if field.is_required()])
def test_null_update_error_identifies_each_field(client, created, field):
    response = envelope(client.put(f"/patients/{created['patient_id']}", json={field: None}), 422)
    assert any(error["field"] == f"body.{field}" for error in response["error"]["details"])


def test_validation_is_atomic_and_private(client, created):
    url = f"/patients/{created['patient_id']}"
    result = envelope(client.put(url, json={"city": "Boston", "phone_number": "SECRET-invalid", "email": "SECRET-invalid"}), 422)
    assert len(result["error"]["details"]) == 2
    assert "SECRET" not in str(result)
    assert envelope(client.get(url), 200)["data"] == created


def test_multiple_required_nulls_report_all_fields(client, created):
    result = envelope(client.put(f"/patients/{created['patient_id']}", json={"first_name": None, "phone_number": None}), 422)
    assert {error["field"] for error in result["error"]["details"]} == {"body.first_name", "body.phone_number"}


@pytest.mark.parametrize("content", ["{broken", "[]", "null", '"text"', "42", ""])
def test_bad_request_bodies(client, content):
    envelope(client.post("/patients", content=content, headers={"Content-Type": "application/json"}), 422)


@pytest.mark.parametrize("params", [{"phone_number": "123"}, {"date_of_birth": "invalid"}, {"last_name": "<script>"}])
def test_invalid_filters(client, params):
    result = envelope(client.get("/patients", params=params), 422)
    assert result["error"]["details"][0]["field"].startswith("query.")


def test_http_errors(client, created):
    url = f"/patients/{created['patient_id']}"
    envelope(client.put(url, json={}), 400)
    for method, kwargs in [("get", {}), ("put", {"json": {"city": "Boston"}}), ("delete", {})]:
        envelope(getattr(client, method)(f"/patients/{uuid4()}", **kwargs), 404)
        envelope(getattr(client, method)("/patients/invalid-id", **kwargs), 422)
    envelope(client.get("/no-such-route"), 404)
    response = client.patch(url, json={"city": "Boston"})
    envelope(response, 405)
    assert response.headers.get("allow")


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_failed_write_rolls_back_and_next_request_recovers(client, created, payload, db, monkeypatch, method):
    url = "/patients" if method == "post" else f"/patients/{created['patient_id']}"
    kwargs = {"json": payload if method == "post" else {"city": "Boston"}} if method != "delete" else {}
    original = Session.flush

    def fail_after_flush(session, *args, **kwargs):
        has_changes = bool(session.new or session.dirty or session.deleted)
        original(session, *args, **kwargs)
        if has_changes:
            raise OperationalError("SECRET SQL", {}, Exception("SECRET failure"))

    with monkeypatch.context() as temporary:
        temporary.setattr(Session, "flush", fail_after_flush)
        result = envelope(getattr(client, method)(url, **kwargs), 500)
        assert "SECRET" not in str(result)
    assert envelope(client.get(f"/patients/{created['patient_id']}"), 200)["data"] == created
    with db[1]() as session:
        assert session.scalar(select(func.count()).select_from(Patient)) == 3
    envelope(client.put(f"/patients/{created['patient_id']}", json={"city": "Boston"}), 200)


@pytest.mark.parametrize("failure", [OperationalError("SECRET SQL", {}, Exception("SECRET")), RuntimeError("SECRET")])
def test_read_and_unexpected_failures_are_enveloped(client, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(Session, "scalars", fail)
    result = envelope(client.get("/patients"), 500)
    assert "SECRET" not in str(result)


def test_sql_strings_are_bound_and_apostrophes_allowed(client, payload):
    value = "Robert'); DROP TABLE patients; --"
    result = envelope(client.post("/patients", json={**payload, "address_line_1": value}), 201)["data"]
    assert result["address_line_1"] == value
    assert result["last_name"] == "O'Neil"
    assert len(envelope(client.get("/patients"), 200)["data"]) == 3


def test_parallel_creates_and_duplicate_phones(client, payload):
    def create(_):
        return client.post("/patients", json=payload)
    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(create, range(8)))
    records = [envelope(response, 201)["data"] for response in responses]
    assert len({record["patient_id"] for record in records}) == 8
    assert len(envelope(client.get("/patients", params={"phone_number": payload["phone_number"]}), 200)["data"]) == 8
