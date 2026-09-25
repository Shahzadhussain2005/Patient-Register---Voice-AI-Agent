"""Export Vapi API Request tools from the patient schemas, without network calls.

Run from the project root: python -m backend.app.vapi_tools
Vapi's portable schema subset uses string patterns for length constraints.
Optional voice arguments are omitted rather than emitted as null; REST still
supports explicit nulls. Dynamic calendar rules remain enforced by Pydantic.
"""

import json
from pathlib import Path

from .schemas import PatientCreate, US_STATES

PLACEHOLDER_BASE_URL = "https://YOUR_BACKEND_HOST"
DESCRIPTIONS = {
    "first_name": "First name: 1-50 Unicode letters, ASCII hyphens/apostrophes; at least one letter.",
    "last_name": "Last name: 1-50 Unicode letters, ASCII hyphens/apostrophes; at least one letter.",
    "date_of_birth": "Real calendar date in YYYY-MM-DD format, not after today in UTC. Clarify ambiguous dates.",
    "sex": "The caller's stated choice; never infer it from their name or voice.",
    "phone_number": "Caller-confirmed US phone number, exactly 10 ASCII digits, no country code or formatting.",
    "email": "Valid email address voluntarily provided by the caller. Omit if not provided.",
    "address_line_1": "Nonempty street address, trimmed plain text.",
    "address_line_2": "Apartment, suite, or unit voluntarily provided. Omit if not provided.",
    "city": "City, 1-100 characters after trimming whitespace.",
    "state": "Uppercase two-letter abbreviation for one of the 50 US states or DC.",
    "zip_code": "Five ASCII digits or ZIP+4 with a hyphen; preserve leading zeros.",
    "insurance_provider": "Insurance provider, only when the caller chooses to provide it.",
    "insurance_member_id": "Insurance member ID: ASCII letters and digits only. Preserve leading zeros.",
    "preferred_language": "Preferred language if volunteered; omit on create for the English default. Does not change the call's configured voice language.",
    "emergency_contact_name": "Emergency contact's name, only when offered or opted into.",
    "emergency_contact_phone": "Emergency contact's US number, exactly 10 ASCII digits.",
}


def patient_properties() -> dict:
    """Resolve enums and optional strings without provider-specific anyOf/$ref."""
    source = PatientCreate.model_json_schema()
    properties = {}
    for name, original in source["properties"].items():
        definition = original
        if "anyOf" in definition:
            definition = next(item for item in definition["anyOf"] if item.get("type") != "null")
        if "$ref" in definition:
            definition = source["$defs"][definition["$ref"].rsplit("/", 1)[-1]]
        result = {key: definition[key] for key in ("type", "enum", "format", "pattern") if key in definition}
        result["description"] = DESCRIPTIONS[name]
        if name in {"first_name", "last_name"}:
            # ECMAScript Unicode property escapes match the backend's letters.
            result["pattern"] = r"^(?=.*\p{L})[\p{L}'-]{1,50}$"
        elif name == "state":
            result["enum"] = sorted(US_STATES)
        elif name == "city":
            result["pattern"] = r"^[\s\S]{1,100}$"
        elif name == "address_line_1":
            result["pattern"] = r"^[\s\S]+$"
        properties[name] = result
    return properties


def build_tools() -> list[dict]:
    properties = patient_properties()
    required = [name for name, field in PatientCreate.model_fields.items() if field.is_required()]

    def tool(name, path, description, fields, required_fields):
        return {
            "type": "apiRequest", "name": name, "description": description,
            "method": "POST", "url": PLACEHOLDER_BASE_URL + path,
            "timeoutSeconds": 20,
            "messages": [
                {"type": "request-response-delayed", "timingMilliseconds": 6000,
                 "content": "I'm still waiting for the result. Thank you for your patience."},
                {"type": "request-failed", "role": "system",
                 "content": "The request failed. Speak a brief, helpful response. If specific validation fields are available, ask to correct only those fields and get fresh confirmation before saving. Otherwise say the action could not be confirmed. Never invent success, treat lookup failure as no match, or automatically retry a write."},
            ],
            "body": {"type": "object", "properties": fields,
                     "required": required_fields, "additionalProperties": False},
        }

    return [
        tool(
            "lookup_patient_by_phone", "/vapi/lookup-patient-by-phone",
            "Look up active patients after the caller confirms their phone number. Uses the same handler as GET /patients?phone_number=. An empty data array means no match; an error never means no match. Multiple matches require disambiguation; do not choose the first record.",
            {"phone_number": properties["phone_number"]}, ["phone_number"],
        ),
        tool(
            "create_patient", "/patients",
            "Create one patient ONLY after reading back every collected field and receiving explicit approval of the latest corrected summary. Include required fields and only supplied optional fields. Omit missing optional values; never invent them. Do not automatically retry a timed-out save.",
            properties, required,
        ),
        tool(
            "update_patient", "/vapi/update-patient",
            "Update a selected existing patient ONLY after explicit approval of the latest complete summary. Use the UUID returned by lookup, plus at least one changed demographic field. Omit unchanged fields. Uses the same handler as PUT /patients/{patient_id}. Never guess a UUID or automatically retry an uncertain save.",
            {"patient_id": {"type": "string", "format": "uuid", "description": "Exact patient_id returned by lookup for the selected record."}, **properties},
            ["patient_id"],
        ),
    ]


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[2] / "docs" / "vapi-tools.json"
    target.write_text(json.dumps(build_tools(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {target}")
