"""SQLite connection, patient table, and UTC persistence helpers."""

import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import UUID, uuid4

from dotenv import load_dotenv
from sqlalchemy import Date, DateTime, Enum as SAEnum, String, Uuid, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """SQLite drops timezone metadata; store UTC and restore it when reading."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


class Sex(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
    DECLINE_TO_ANSWER = "Decline to Answer"


class Base(DeclarativeBase):
    pass


# Enum prevents arbitrary sex values; SQLite enforces the values with a CHECK
# constraint because it does not have a native enum storage type.
class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    date_of_birth = mapped_column(Date, nullable=False)
    sex: Mapped[Sex] = mapped_column(
        SAEnum(Sex, values_callable=lambda enum: [item.value for item in enum],
               name="patient_sex", create_constraint=True, validate_strings=True),
        nullable=False,
    )
    phone_number: Mapped[str] = mapped_column(String(10), nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    address_line_1: Mapped[str] = mapped_column(String, nullable=False)
    address_line_2: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False)
    insurance_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    insurance_member_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Preserve explicit null; the default applies only when the value is omitted.
    preferred_language: Mapped[str | None] = mapped_column(String().evaluates_none(), default="English", nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(String, nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./patients.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def initialize_database() -> None:
    Base.metadata.create_all(engine)


def get_session():
    """One session per request; failed writes are rolled back before closing."""
    with SessionLocal() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
