"""Server-side patient validation, independent of the eventual voice agent."""

from datetime import date, datetime, timezone
import re
from typing import Annotated, Generic, TypeVar
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, ValidationInfo, field_validator

from .database import Sex

US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
    "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)


def validate_name(value: str) -> str:
    if not any(char.isalpha() for char in value) or not all(
        char.isalpha() or char in "-'" for char in value
    ):
        raise ValueError("Use letters, hyphens, and apostrophes only")
    return value


def validate_birth_date(value: date) -> date:
    if value > datetime.now(timezone.utc).date():
        raise ValueError("Date of birth must not be in the future")
    return value


def validate_state(value: str) -> str:
    if value not in US_STATES:
        raise ValueError("Use a valid uppercase two-letter US state abbreviation (or DC)")
    return value


Name = Annotated[str, Field(min_length=1, max_length=50), AfterValidator(validate_name)]
BirthDate = Annotated[date, AfterValidator(validate_birth_date)]
# Require the ten-digit US representation; formatted numbers and +1 are rejected.
Phone = Annotated[str, Field(pattern=r"^[0-9]{10}$", min_length=10, max_length=10)]
ZipCode = Annotated[str, Field(pattern=r"^[0-9]{5}(-[0-9]{4})?$", min_length=5, max_length=10)]
State = Annotated[str, AfterValidator(validate_state)]
City = Annotated[str, Field(min_length=1, max_length=100)]
Street = Annotated[str, Field(min_length=1)]
MemberId = Annotated[str, Field(pattern=r"^[A-Za-z0-9]+$")]


def sanitize_text(value):
    if not isinstance(value, str):
        return value
    # Demographics are plain text. SQLAlchemy bound parameters provide SQL
    # injection protection; do not reject legitimate apostrophes such as O'Neil.
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Control characters are not allowed")
    if re.search(r"<[^>]*>|javascript\s*:", value, flags=re.IGNORECASE):
        raise ValueError("HTML markup and script URLs are not allowed")
    return value.strip()


class PatientInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def sanitize_fields(cls, value):
        return sanitize_text(value)


class PatientCreate(PatientInput):
    first_name: Name
    last_name: Name
    date_of_birth: BirthDate
    sex: Sex
    phone_number: Phone
    email: EmailStr | None = None
    address_line_1: Street
    address_line_2: str | None = None
    city: City
    state: State
    zip_code: ZipCode
    insurance_provider: str | None = None
    insurance_member_id: MemberId | None = None
    preferred_language: str | None = "English"
    emergency_contact_name: str | None = None
    emergency_contact_phone: Phone | None = None


class PatientUpdate(PatientInput):

    first_name: Name | None = None
    last_name: Name | None = None
    date_of_birth: BirthDate | None = None
    sex: Sex | None = None
    phone_number: Phone | None = None
    email: EmailStr | None = None
    address_line_1: Street | None = None
    address_line_2: str | None = None
    city: City | None = None
    state: State | None = None
    zip_code: ZipCode | None = None
    insurance_provider: str | None = None
    insurance_member_id: MemberId | None = None
    preferred_language: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: Phone | None = None

    @field_validator("*", mode="before")
    @classmethod
    def prevent_clearing_required_fields(cls, value, info: ValidationInfo):
        # Field validators attach each error to its field and collect multiple
        # failures. Omitted update fields do not run this validator.
        field = PatientCreate.model_fields.get(info.field_name)
        if value is None and field is not None and field.is_required():
            raise ValueError(f"{info.field_name} cannot be null")
        return value


class PatientOut(PatientCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    patient_id: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    data: T | None = None
    error: str | dict | list | None = None
