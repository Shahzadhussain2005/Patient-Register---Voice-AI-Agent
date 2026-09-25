"""Boundary and malformed input tests applied to both API input schemas."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.app.schemas import PatientCreate, PatientUpdate, US_STATES

REQUIRED = [name for name, field in PatientCreate.model_fields.items() if field.is_required()]
OPTIONAL = [name for name, field in PatientCreate.model_fields.items() if not field.is_required()]
INVALID = [
    ("first_name", ""), ("first_name", "   "), ("first_name", "A" * 51),
    ("first_name", "Jane2"), ("first_name", "--'"), ("first_name", "Jane Doe"),
    ("last_name", ""), ("last_name", "B" * 51), ("last_name", "Doe_"),
    ("date_of_birth", "2025-02-29"), ("date_of_birth", "2024-13-01"),
    ("date_of_birth", "not-a-date"),
    ("date_of_birth", (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()),
    ("sex", "male"), ("sex", "Unknown"), ("sex", ""),
    ("phone_number", "123456789"), ("phone_number", "12345678901"),
    ("phone_number", "+12125550199"), ("phone_number", "212-555-0199"),
    ("phone_number", "abcdefghij"), ("phone_number", "１２３４５６７８９０"),
    ("phone_number", 2125550199),
    ("email", "broken"), ("email", "person@"), ("email", ""),
    ("address_line_1", ""), ("address_line_1", "   "),
    ("city", ""), ("city", " " * 3), ("city", "A" * 101),
    ("state", "ZZ"), ("state", "ny"), ("state", "New York"),
    ("zip_code", "1234"), ("zip_code", "123456"), ("zip_code", "123456789"),
    ("zip_code", "12345-123"), ("zip_code", "１２３４５"),
    ("insurance_member_id", "A-12"), ("insurance_member_id", "ABC 123"),
    ("insurance_member_id", ""), ("emergency_contact_phone", "123"),
    ("emergency_contact_phone", "212 555 0199"),
]


@pytest.mark.parametrize("schema", [PatientCreate, PatientUpdate])
@pytest.mark.parametrize("field,value", INVALID)
def test_invalid_values(schema, field, value, payload):
    data = {**payload, field: value} if schema is PatientCreate else {field: value}
    with pytest.raises(ValidationError):
        schema.model_validate(data)


@pytest.mark.parametrize("field", REQUIRED)
def test_required_fields_cannot_be_omitted_or_null(field, payload):
    data = dict(payload)
    data.pop(field)
    with pytest.raises(ValidationError):
        PatientCreate.model_validate(data)
    for schema, values in [(PatientCreate, {**payload, field: None}), (PatientUpdate, {field: None})]:
        with pytest.raises(ValidationError):
            schema.model_validate(values)


@pytest.mark.parametrize("field", OPTIONAL)
def test_optional_fields_can_be_null(field, payload):
    assert getattr(PatientCreate.model_validate({**payload, field: None}), field) is None
    assert PatientUpdate.model_validate({field: None}).model_dump(exclude_unset=True) == {field: None}


@pytest.mark.parametrize("field,value", [
    ("first_name", "A"), ("first_name", "A" * 50), ("first_name", "Élodie"),
    ("last_name", "O'Neil"), ("last_name", "Smith-Jones"),
    ("date_of_birth", "2000-02-29"),
    ("date_of_birth", datetime.now(timezone.utc).date().isoformat()),
    ("sex", "Male"), ("sex", "Female"), ("sex", "Other"), ("sex", "Decline to Answer"),
    ("city", "A"), ("city", "A" * 100), ("zip_code", "00501"),
    ("zip_code", "10001-1234"), ("insurance_member_id", "ABC0123"),
    ("email", "jamie+test@example.com"), ("emergency_contact_phone", "2125550198"),
])
def test_valid_boundaries(field, value, payload):
    PatientCreate.model_validate({**payload, field: value})
    PatientUpdate.model_validate({field: value})


def test_all_state_abbreviations(payload):
    assert len(US_STATES) == 51
    for state in US_STATES:
        assert PatientCreate.model_validate({**payload, "state": state}).state == state


@pytest.mark.parametrize("field", list(PatientCreate.model_fields))
@pytest.mark.parametrize("bad", ["<ScRiPt>alert(1)</ScRiPt>", "javascript:alert(1)", "abc\x00def"])
def test_plain_text_sanitization(field, bad):
    with pytest.raises(ValidationError):
        PatientUpdate.model_validate({field: bad})


def test_whitespace_defaults_and_omission(payload):
    data = PatientCreate.model_validate({name: f"  {value}  " for name, value in payload.items()})
    assert data.first_name == "Jamie"
    assert data.state == "NY"
    assert data.preferred_language == "English"
    assert PatientUpdate().model_dump(exclude_unset=True) == {}


@pytest.mark.parametrize("field", ["patient_id", "created_at", "updated_at", "deleted_at", "unknown"])
def test_system_fields_and_unknown_fields_rejected(field, payload):
    for schema, values in [(PatientCreate, {**payload, field: "anything"}), (PatientUpdate, {field: "anything"})]:
        with pytest.raises(ValidationError):
            schema.model_validate(values)
