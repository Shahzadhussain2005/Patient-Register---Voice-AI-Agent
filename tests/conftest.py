"""Use an isolated, real SQLite file for every test; never touch patients.db."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import database, seed
from backend.app.main import app


@pytest.fixture
def payload():
    return {
        "first_name": "Jamie", "last_name": "O'Neil", "date_of_birth": "1992-02-29",
        "sex": "Other", "phone_number": "2125550199", "address_line_1": "123 Example Street",
        "city": "New York", "state": "NY", "zip_code": "10001",
    }


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'patients.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessions)
    monkeypatch.setattr(seed, "SessionLocal", sessions)
    database.initialize_database()
    yield engine, sessions
    engine.dispose()


@pytest.fixture
def client(db):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def created(client, payload):
    response = client.post("/patients", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]
