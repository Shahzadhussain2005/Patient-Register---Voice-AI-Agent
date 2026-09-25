"""Real SQLite constraints, UTC round trips, and startup/seed behavior."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from backend.app.database import Patient
from backend.app.main import app
from backend.app.schemas import PatientCreate, PatientOut
from backend.app.seed import seed_demo_patients


def test_table_matches_spec(db):
    columns = {column["name"]: column for column in inspect(db[0]).get_columns("patients")}
    assert set(columns) == set(PatientCreate.model_fields) | {"patient_id", "created_at", "updated_at", "deleted_at"}
    for name, field in PatientCreate.model_fields.items():
        assert columns[name]["nullable"] is (not field.is_required())
    assert columns["patient_id"]["primary_key"]
    assert not columns["created_at"]["nullable"]
    assert not columns["updated_at"]["nullable"]


def test_defaults_utc_and_update(db, payload):
    with db[1]() as session:
        patient = Patient(**PatientCreate.model_validate(payload).model_dump())
        session.add(patient)
        session.commit()
        identity = patient.patient_id
        assert isinstance(identity, UUID) and identity.version == 4
        created = patient.created_at
        updated = patient.updated_at
        assert patient.deleted_at is None
        assert patient.preferred_language == "English"
    with db[1]() as session:
        patient = session.get(Patient, identity)
        assert patient.created_at.utcoffset() == timedelta(0)
        assert patient.updated_at.utcoffset() == timedelta(0)
        patient.city = "Boston"
        session.commit()
        assert patient.updated_at > updated
        assert patient.created_at == created
        assert PatientOut.model_validate(patient).patient_id == identity


def test_non_utc_timestamp_normalized_and_naive_rejected(db, payload):
    supplied = datetime(2020, 1, 1, 12, tzinfo=timezone(timedelta(hours=5)))
    with db[1]() as session:
        patient = Patient(**PatientCreate.model_validate(payload).model_dump(), created_at=supplied)
        session.add(patient)
        session.commit()
        session.refresh(patient)
        assert patient.created_at == datetime(2020, 1, 1, 7, tzinfo=timezone.utc)
        patient.updated_at = datetime(2020, 1, 1)
        with pytest.raises(StatementError):
            session.commit()
        session.rollback()


@pytest.mark.parametrize("assignment", ["sex = 'Invalid'", "first_name = NULL", "created_at = NULL", "patient_id = patient_id"])
def test_sqlite_constraints(db, payload, assignment):
    with db[1].begin() as session:
        session.add(Patient(**PatientCreate.model_validate(payload).model_dump()))
    if assignment == "patient_id = patient_id":
        with pytest.raises(IntegrityError), db[0].begin() as conn:
            conn.execute(text("INSERT INTO patients SELECT * FROM patients"))
    else:
        with pytest.raises(IntegrityError), db[0].begin() as conn:
            conn.execute(text(f"UPDATE patients SET {assignment}"))


def test_seed_is_atomic(db, monkeypatch):
    original = PatientCreate.model_validate
    calls = 0

    def fail_second(value):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("Simulated second seed failure")
        return original(value)

    monkeypatch.setattr(PatientCreate, "model_validate", fail_second)
    with pytest.raises(ValueError):
        seed_demo_patients()
    with db[1]() as session:
        assert session.scalar(select(func.count()).select_from(Patient)) == 0


def test_startup_is_idempotent_and_does_not_reseed_deleted_rows(db):
    with TestClient(app) as client:
        patients = client.get("/patients").json()["data"]
        assert len(patients) == 2
    with TestClient(app) as client:
        assert {p["patient_id"] for p in client.get("/patients").json()["data"]} == {p["patient_id"] for p in patients}
        for patient in patients:
            assert client.delete(f"/patients/{patient['patient_id']}").status_code == 200
    with TestClient(app) as client:
        assert client.get("/patients").json()["data"] == []
    with db[1]() as session:
        assert session.scalar(select(func.count()).select_from(Patient)) == 2


def test_nonempty_table_is_not_seeded(db, payload):
    with db[1].begin() as session:
        session.add(Patient(**PatientCreate.model_validate(payload).model_dump()))
    seed_demo_patients()
    with db[1]() as session:
        assert session.scalar(select(func.count()).select_from(Patient)) == 1
