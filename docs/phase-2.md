# Phase 2: patient REST API

Run from the project root (install dependencies using the Phase 1 instructions):

```powershell
.\.venv\Scripts\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In another PowerShell terminal, run these exact commands from the project root.
Use `curl.exe` to avoid the Windows PowerShell `curl` alias. The example JSON
files contain fictional data and avoid Windows command-line JSON quoting issues.

```powershell
# Health: 200
curl.exe -i http://127.0.0.1:8000/health

# Create: 201. Capture the generated UUID for the following commands.
$created = curl.exe -sS -X POST http://127.0.0.1:8000/patients -H "Content-Type: application/json" --data-binary "@docs/examples/patient-create.json"
$created
$patientId = ($created | ConvertFrom-Json).data.patient_id

# List with all three filters (AND-combined): 200
curl.exe -i "http://127.0.0.1:8000/patients?last_name=Demo&date_of_birth=1992-05-10&phone_number=2125550199"

# Fetch by UUID: 200
curl.exe -i "http://127.0.0.1:8000/patients/$patientId"

# Partial update: 200. Sets the apartment, clears email, retains other fields.
curl.exe -i -X PUT "http://127.0.0.1:8000/patients/$patientId" -H "Content-Type: application/json" --data-binary "@docs/examples/patient-update.json"

# Soft delete: 200, with deleted_at in the returned record.
curl.exe -i -X DELETE "http://127.0.0.1:8000/patients/$patientId"

# List again: the deleted UUID is excluded (empty data on a clean demo run).
curl.exe -i "http://127.0.0.1:8000/patients?phone_number=2125550199"

# Fetch after deletion: 404
curl.exe -i "http://127.0.0.1:8000/patients/$patientId"

# Invalid phone filter: 422 with a field-specific message.
curl.exe -i "http://127.0.0.1:8000/patients?phone_number=123"

# Empty update: 400 (run with an active patient UUID).
# curl.exe -i -X PUT "http://127.0.0.1:8000/patients/$patientId" -H "Content-Type: application/json" --data-binary '{}'
```

All patient and health responses use `{"data": ..., "error": ...}`. Success has
`error: null`; failures have `data: null`. Validation failures contain
`error.details`, a list of field paths, messages, and error types. Framework
errors such as unknown paths and unsupported methods use the same envelope.
The framework's `/docs` UI and `/openapi.json` retain their standard formats.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/patients` | Active patients; optional exact-match `last_name`, `date_of_birth`, `phone_number` filters |
| GET | `/patients/{patient_id}` | Active patient or 404 |
| POST | `/patients` | Validated creation, 201 |
| PUT | `/patients/{patient_id}` | Partial update, 200; an empty object is 400 |
| DELETE | `/patients/{patient_id}` | Soft delete, 200 with updated record |
| GET | `/health` | 200 with `data.status` equal to `ok` |

Invalid UUIDs and invalid body/query fields return 422. Missing or soft-deleted
records return 404. Database failures roll back the request transaction and
return a generic 500; errors do not expose SQL or submitted patient data.
Every accepted update bumps `updated_at`, including resubmitting the same value.

Input strings are trimmed and plain-text demographic fields reject control
characters, HTML markup, and script URLs. SQLAlchemy parameter binding protects
queries from SQL injection; legitimate apostrophes remain allowed. Rendering
clients must still escape text appropriately. No uniqueness rule is added for
phone numbers because the supplied data model does not require one.

What you just learned: server-side validation protects the database even if a
voice agent misunderstands a caller, submits malformed tool arguments, or a
client calls the API directly. The same rules apply to every caller. Soft
deletion preserves the stored row while excluding it from ordinary reads.
