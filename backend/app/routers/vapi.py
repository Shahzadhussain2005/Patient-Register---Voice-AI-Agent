"""JSON-body adapters for Vapi API Request tools; reuse the REST handlers."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.exceptions import HTTPException
from pydantic import ValidationError

from ..schemas import Envelope, PatientInput, PatientOut, PatientUpdate, Phone
from .patients import DatabaseSession, list_patients, update_patient

logger = logging.getLogger("uvicorn.error")


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


def _normalize_phone(raw: Any) -> str | None:
    """Accept spoken/formatted numbers; store/query as exactly 10 ASCII digits."""
    if raw is None:
        return None
    digits = re.sub(r"\D", "", str(raw).strip())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return digits
    return None


def _arguments_from_tool_calls(body: dict[str, Any]) -> dict[str, Any] | None:
    """Function-tool server envelope: message.toolCalls[0].function.arguments."""
    message = body.get("message")
    if not isinstance(message, dict):
        return None
    tool_calls = message.get("toolCalls") or message.get("toolCallList") or []
    if not tool_calls and isinstance(message.get("toolCall"), dict):
        tool_calls = [message["toolCall"]]
    if not isinstance(tool_calls, list) or not tool_calls:
        return None
    first = tool_calls[0]
    if not isinstance(first, dict):
        return None
    function = first.get("function") or {}
    arguments = function.get("arguments") if isinstance(function, dict) else None
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return None
    return arguments if isinstance(arguments, dict) else None


def extract_phone_number(body: Any) -> str | None:
    """Pull phone_number from API Request flat body or Function-tool nesting."""
    if not isinstance(body, dict):
        return None

    candidates: list[Any] = []
    if "phone_number" in body:
        candidates.append(body.get("phone_number"))
    for alias in ("phone", "phoneNumber", "number"):
        if alias in body:
            candidates.append(body.get(alias))

    nested = _arguments_from_tool_calls(body)
    if nested:
        candidates.append(nested.get("phone_number"))
        for alias in ("phone", "phoneNumber", "number"):
            candidates.append(nested.get(alias))

    # Some API Request configs nest under "body" or "parameters".
    for key in ("body", "parameters", "arguments"):
        inner = body.get(key)
        if isinstance(inner, dict):
            candidates.append(inner.get("phone_number"))
        elif isinstance(inner, str):
            try:
                parsed = json.loads(inner)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                candidates.append(parsed.get("phone_number"))

    for value in candidates:
        normalized = _normalize_phone(value)
        if normalized:
            return normalized
    return None


@router.post("/lookup-patient-by-phone", response_model=Envelope[list[PatientOut]])
async def lookup_by_phone(request: Request, session: DatabaseSession):
    """Equivalent to GET /patients?phone_number=..., using the same handler.

    Accepts the flat API Request body this project documents, plus common
    voice/Function payload variants. Always logs the raw JSON for Render debug.
    """
    try:
        raw = await request.json()
    except Exception:
        raw = None
    logger.info("vapi lookup raw body: %s", raw)

    phone = extract_phone_number(raw)
    if phone is None:
        raise HTTPException(
            status_code=422,
            detail={
                "details": [{
                    "field": "phone_number",
                    "message": (
                        "Expected a 10-digit US phone (or +1…). "
                        f"Received body keys: {sorted(raw) if isinstance(raw, dict) else type(raw).__name__}"
                    ),
                    "type": "value_error",
                }],
            },
        )

    try:
        payload = PhoneLookup(phone_number=phone)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"details": [
                {"field": ".".join(map(str, err["loc"])), "message": err["msg"], "type": err["type"]}
                for err in exc.errors()
            ]},
        ) from exc

    return list_patients(session=session, phone_number=payload.phone_number)


@router.post("/update-patient", response_model=Envelope[PatientOut])
def update_from_voice(payload: VoicePatientUpdate, session: DatabaseSession):
    """Move the identifier out of the body before invoking the PUT handler."""
    changes = PatientUpdate.model_validate(
        payload.model_dump(exclude={"patient_id"}, exclude_unset=True)
    )
    return update_patient(patient_id=payload.patient_id, payload=changes, session=session)
