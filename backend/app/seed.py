"""Insert two fictional patients only when the entire patient table is empty."""

from sqlalchemy import select

from .database import Patient, SessionLocal, initialize_database
from .schemas import PatientCreate


def seed_demo_patients() -> None:
    with SessionLocal.begin() as session:
        if session.scalar(select(Patient.patient_id).limit(1)) is not None:
            return
        examples = [
            dict(first_name="Avery", last_name="Demo", date_of_birth="1990-04-12",
                 sex="Other", phone_number="2025550101", address_line_1="123 Example Street",
                 city="Washington", state="DC", zip_code="20001", email="avery@example.com"),
            dict(first_name="Morgan", last_name="Sample", date_of_birth="1985-09-23",
                 sex="Decline to Answer", phone_number="4155550102", address_line_1="456 Sample Avenue",
                 address_line_2="Unit 2", city="San Francisco", state="CA", zip_code="94105-1234"),
        ]
        for example in examples:
            validated = PatientCreate.model_validate(example)
            session.add(Patient(**validated.model_dump()))


if __name__ == "__main__":
    initialize_database()
    seed_demo_patients()
