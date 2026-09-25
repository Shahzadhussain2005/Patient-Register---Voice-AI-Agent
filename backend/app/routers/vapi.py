"""JSON-body adapters for Vapi API Request tools; reuse the REST handlers."""

from uuid import UUID

from fastapi import APIRouter

from ..schemas import Envelope, PatientInput, PatientOut, PatientUpdate, Phone
from .patients import DatabaseSession, list_patients, update_patient


class PhoneLookup(PatientInput):
    phone_number: Phone


class VoicePatientUpdate(PatientUpdate):
    # This is routing metadata, not a writable patient demographic field.
    patient_id: UUID


router = APIRouter(
    prefix="/vapi", tags=["voice tools"],
    responses={
        400: {"model": Envelope[None], "description": "No update fields provided"},
        404: {"model": Envelope[None], "description": "Patient not found"},
        422: {"model": Envelope[None], "description": "Invalid tool arguments"},
        500: {"model": Envelope[None], "description": "Server or database failure"},
    },
)


@router.post("/lookup-patient-by-phone", response_model=Envelope[list[PatientOut]])
def lookup_by_phone(payload: PhoneLookup, session: DatabaseSession):
    """Equivalent to GET /patients?phone_number=..., using the same handler."""
    return list_patients(session=session, phone_number=payload.phone_number)


@router.post("/update-patient", response_model=Envelope[PatientOut])
def update_from_voice(payload: VoicePatientUpdate, session: DatabaseSession):
    """Move the identifier out of the body before invoking the PUT handler."""
    changes = PatientUpdate.model_validate(
        payload.model_dump(exclude={"patient_id"}, exclude_unset=True)
    )
    return update_patient(patient_id=payload.patient_id, payload=changes, session=session)
