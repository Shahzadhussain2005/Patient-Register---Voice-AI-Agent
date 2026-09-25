"""Run the real server and seed CLI in separate processes on disposable databases."""

from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
PROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


@contextmanager
def live_server(tmp_path):
    # Ask the OS for an available local port so an existing development server
    # can keep running. Fail with its log if another process wins the bind race.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    environment = {**os.environ, "DATABASE_URL": f"sqlite:///{(tmp_path / 'live.db').as_posix()}"}
    log_path = tmp_path / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
            creationflags=PROCESS_FLAGS,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=5) as client:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise AssertionError(log_path.read_text(encoding="utf-8"))
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    raise AssertionError("Server did not start: " + log_path.read_text(encoding="utf-8"))
                yield client
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def test_real_http_flow_and_persistence_after_restart(tmp_path):
    create_payload = (ROOT / "docs/examples/patient-create.json").read_bytes()
    update_payload = (ROOT / "docs/examples/patient-update.json").read_bytes()
    headers = {"Content-Type": "application/json"}
    with live_server(tmp_path) as client:
        assert client.get("/health").json() == {"data": {"status": "ok"}, "error": None}
        assert len(client.get("/patients").json()["data"]) == 2
        response = client.post("/patients", content=create_payload, headers=headers)
        assert response.status_code == 201, response.text
        record = response.json()["data"]
        url = f"/patients/{record['patient_id']}"
        assert client.get(url).json()["data"] == record
        filters = {name: record[name] for name in ("last_name", "date_of_birth", "phone_number")}
        assert client.get("/patients", params=filters).json()["data"] == [record]
        response = client.put(url, content=update_payload, headers=headers)
        assert response.status_code == 200
        updated = response.json()["data"]
        assert updated["address_line_2"] == "Unit 4" and updated["email"] is None
        assert client.get("/patients", params={"phone_number": "123"}).status_code == 422
    with live_server(tmp_path) as client:
        assert client.get(url).json()["data"] == updated
        assert len(client.get("/patients").json()["data"]) == 3
        response = client.delete(url)
        assert response.status_code == 200 and response.json()["data"]["deleted_at"]
        assert client.get("/patients", params=filters).json() == {"data": [], "error": None}
        assert client.get(url).status_code == 404
    with live_server(tmp_path) as client:
        assert client.get(url).status_code == 404
        assert len(client.get("/patients").json()["data"]) == 2


def test_standalone_seed_command(tmp_path):
    import sqlite3

    database = tmp_path / "seed-cli.db"
    environment = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}"}
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-m", "backend.app.seed"], cwd=ROOT, env=environment,
            capture_output=True, text=True, timeout=30, creationflags=PROCESS_FLAGS,
        )
        assert result.returncode == 0, result.stderr
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 2
