"""Patient CRUD with partial updates and soft deletion."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BeforeValidator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import Patient, get_session, utc_now
from ..schemas import (
    BirthDate, Envelope, Name, PatientCreate, PatientOut, PatientUpdate, Phone, sanitize_text,
)

router = APIRouter(
    prefix="/patients", tags=["patients"],
    responses={
        404: {"model": Envelope[None], "description": "Patient not found"},
        422: {"model": Envelope[None], "description": "Invalid request fields"},
        500: {"model": Envelope[None], "description": "Server or database failure"},
    },
)
DatabaseSession = Annotated[Session, Depends(get_session)]


def active_patient(patient_id: UUID, session: Session) -> Patient:
    patient = session.get(Patient, patient_id)
    if patient is None or patient.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.get("", response_model=Envelope[list[PatientOut]])
def list_patients(
    session: DatabaseSession,
    last_name: Annotated[Name | None, BeforeValidator(sanitize_text), Query()] = None,
    date_of_birth: Annotated[BirthDate | None, BeforeValidator(sanitize_text), Query()] = None,
    phone_number: Annotated[Phone | None, BeforeValidator(sanitize_text), Query()] = None,
):
    query = select(Patient).where(Patient.deleted_at.is_(None))
    for column, value in (
        (Patient.last_name, last_name),
        (Patient.date_of_birth, date_of_birth),
        (Patient.phone_number, phone_number),
    ):
        if value is not None:
            query = query.where(column == value)
    patients = session.scalars(query.order_by(Patient.created_at, Patient.patient_id)).all()
    return {"data": patients, "error": None}


@router.get("/{patient_id}", response_model=Envelope[PatientOut])
def get_patient(patient_id: UUID, session: DatabaseSession):
    return {"data": active_patient(patient_id, session), "error": None}


@router.post("", status_code=201, response_model=Envelope[PatientOut])
def create_patient(payload: PatientCreate, session: DatabaseSession):
    patient = Patient(**payload.model_dump())
    session.add(patient)
    session.commit()
    session.refresh(patient)
    return {"data": patient, "error": None}


@router.put(
    "/{patient_id}", response_model=Envelope[PatientOut],
    responses={400: {"model": Envelope[None], "description": "No fields provided"}},
)
def update_patient(patient_id: UUID, payload: PatientUpdate, session: DatabaseSession):
    patient = active_patient(patient_id, session)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Provide at least one field to update")
    for field, value in changes.items():
        setattr(patient, field, value)
    # Explicitly bump even when the submitted value matches the stored value.
    patient.updated_at = utc_now()
    session.commit()
    session.refresh(patient)
    return {"data": patient, "error": None}


@router.delete("/{patient_id}", response_model=Envelope[PatientOut])
def delete_patient(patient_id: UUID, session: DatabaseSession):
    patient = active_patient(patient_id, session)
    patient.deleted_at = utc_now()
    patient.updated_at = patient.deleted_at
    session.commit()
    session.refresh(patient)
    return {"data": patient, "error": None}
