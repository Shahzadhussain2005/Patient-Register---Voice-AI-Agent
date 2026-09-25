"""Contract tests for Vapi schemas and adapters; no Vapi account/network needed."""

import json
from pathlib import Path
import re
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.database import Sex
from backend.app.schemas import PatientCreate, US_STATES
from backend.app.vapi_tools import build_tools

ROOT = Path(__file__).resolve().parents[1]


def check(response, status):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"data", "error"}
    assert (body["error"] is None) == (status < 400)
    if status >= 400:
        assert body["data"] is None
    return body


def test_export_matches_patient_contract():
    tools = json.loads((ROOT / "docs/vapi-tools.json").read_text(encoding="utf-8"))
    assert tools == build_tools(), "Regenerate with python -m backend.app.vapi_tools"
    lookup, create, update = tools
    assert [tool["name"] for tool in tools] == ["lookup_patient_by_phone", "create_patient", "update_patient"]
    assert set(create["body"]["properties"]) == set(PatientCreate.model_fields)
    assert set(update["body"]["properties"]) == set(PatientCreate.model_fields) | {"patient_id"}
    assert set(create["body"]["required"]) == {name for name, field in PatientCreate.model_fields.items() if field.is_required()}
    assert update["body"]["required"] == ["patient_id"]
    assert lookup["body"]["required"] == ["phone_number"]
    props = create["body"]["properties"]
    assert props["sex"]["enum"] == [value.value for value in Sex]
    assert set(props["state"]["enum"]) == US_STATES
    assert props["date_of_birth"]["format"] == "date"
    assert props["email"]["format"] == "email"
    assert update["body"]["properties"]["patient_id"]["format"] == "uuid"
    for tool in tools:
        assert tool["type"] == "apiRequest" and tool["method"] == "POST"
        assert "function" not in tool and "backoffPlan" not in tool
        assert tool["body"]["additionalProperties"] is False
        assert {message["type"] for message in tool["messages"]} == {"request-response-delayed", "request-failed"}


@pytest.mark.parametrize("field,valid,invalid", [
    ("phone_number", "2125550199", "212-555-0199"),
    ("emergency_contact_phone", "2125550100", "123"),
    ("zip_code", "00501", "123456"),
    ("zip_code", "00501-1234", "005011234"),
    ("insurance_member_id", "ABC123", "ABC-123"),
    ("city", "a" * 100, "a" * 101),
    ("address_line_1", "123 Demo Street", ""),
])
def test_exported_patterns(field, valid, invalid):
    pattern = build_tools()[1]["body"]["properties"][field]["pattern"]
    assert re.fullmatch(pattern, valid)
    assert not re.fullmatch(pattern, invalid)


def test_real_tool_definitions_create_lookup_update(client, payload):
    lookup, create, update = build_tools()

    def invoke(tool, arguments):
        return client.request(tool["method"], urlparse(tool["url"]).path, json=arguments)

    patient = check(invoke(create, payload), 201)["data"]
    matches = check(invoke(lookup, {"phone_number": payload["phone_number"]}), 200)["data"]
    assert matches == [patient]
    updated = check(invoke(update, {"patient_id": patient["patient_id"], "city": "Boston"}), 200)["data"]
    assert updated["city"] == "Boston"
    assert updated["first_name"] == patient["first_name"]
    assert updated["updated_at"] > patient["updated_at"]
    assert client.get(f"/patients/{patient['patient_id']}").json()["data"] == updated


def test_lookup_matches_rest_for_multiple_and_deleted_records(client, created, payload):
    second = check(client.post("/patients", json={**payload, "first_name": "Alex"}), 201)["data"]
    body = {"phone_number": "  " + payload["phone_number"] + "  "}
    matches = check(client.post("/vapi/lookup-patient-by-phone", json=body), 200)["data"]
    assert {p["patient_id"] for p in matches} == {created["patient_id"], second["patient_id"]}
    check(client.delete(f"/patients/{created['patient_id']}"), 200)
    actual = check(client.post("/vapi/lookup-patient-by-phone", json=body), 200)
    assert actual == client.get("/patients", params={"phone_number": payload["phone_number"]}).json()
    assert len(actual["data"]) == 1
    assert check(client.post("/vapi/lookup-patient-by-phone", json={"phone_number": "2125550000"}), 200)["data"] == []


@pytest.mark.parametrize("body", [{}, {"phone_number": "123"}, {"phone_number": None}])
def test_lookup_validation(client, body):
    check(client.post("/vapi/lookup-patient-by-phone", json=body), 422)


def test_lookup_accepts_formatted_extra_and_nested_payloads(client, created, payload):
    phone = payload["phone_number"]
    assert check(client.post("/vapi/lookup-patient-by-phone", json={
        "phone_number": f"({phone[:3]}) {phone[3:6]}-{phone[6:]}",
        "extra": True,
    }), 200)["data"][0]["patient_id"] == created["patient_id"]
    assert check(client.post("/vapi/lookup-patient-by-phone", json={
        "phone_number": f"+1{phone}",
    }), 200)["data"][0]["patient_id"] == created["patient_id"]
    nested = {
        "message": {
            "type": "tool-calls",
            "toolCalls": [{
                "id": "call_test",
                "function": {
                    "name": "lookup_patient_by_phone",
                    "arguments": {"phone_number": phone},
                },
            }],
        },
    }
    assert check(client.post("/vapi/lookup-patient-by-phone", json=nested), 200)["data"][0][
        "patient_id"
    ] == created["patient_id"]


@pytest.mark.parametrize("changes", [
    {"phone_number": "123"}, {"date_of_birth": "2999-01-01"}, {"state": "ZZ"},
    {"city": None}, {"deleted_at": "2026-01-01"}, {"patient_id": None},
    {"patient_id": "invalid"}, {"address_line_1": "<script>"},
])
def test_update_validation(client, created, changes):
    body = {"patient_id": created["patient_id"], **changes}
    check(client.post("/vapi/update-patient", json=body), 422)
    assert client.get(f"/patients/{created['patient_id']}").json()["data"] == created


def test_update_missing_id_empty_changes_and_missing_patient(client, created):
    check(client.post("/vapi/update-patient", json={"city": "Boston"}), 422)
    check(client.post("/vapi/update-patient", json={"patient_id": created["patient_id"]}), 400)
    check(client.post("/vapi/update-patient", json={"patient_id": str(uuid4()), "city": "Boston"}), 404)
    client.delete(f"/patients/{created['patient_id']}")
    check(client.post("/vapi/update-patient", json={"patient_id": created["patient_id"], "city": "Boston"}), 404)


def test_adapter_preserves_rest_null_clearing(client, created):
    result = check(client.post("/vapi/update-patient", json={"patient_id": created["patient_id"], "preferred_language": None}), 200)
    assert result["data"]["preferred_language"] is None


def test_adapter_database_failure_rolls_back(client, created, monkeypatch):
    def fail(*args, **kwargs):
        raise OperationalError("private SQL", {}, Exception("private detail"))
    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail)
        error = check(client.post("/vapi/update-patient", json={"patient_id": created["patient_id"], "city": "Boston"}), 500)
        assert "private" not in str(error)
    assert client.get(f"/patients/{created['patient_id']}").json()["data"] == created
