# Testing the Phase 1–3 backend and configuration

Latest verification on September 24, 2026: **253 tests passed**, with one
dependency deprecation warning, in 33.76 seconds. This includes the original
228 Phase 1–2 checks plus 25 Phase 3 tool-schema and adapter checks. Python
compilation and `pip check` passed in the earlier Phase 1–2 verification.
Live Vapi calls and later-phase functionality are not part of this result.

Run from the project root:

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q
```

Pytest uses `.test-tmp/` for disposable test databases and server logs; that
directory is recreated by pytest and is gitignored. Do not put project data in
it. The application's `patients.db` is not used or modified by the suite.
Live tests start their own servers on available localhost ports and stop them
afterward. No API keys or external services are needed.

| Test file | Coverage |
| --- | --- |
| `tests/test_validation.py` | Required/optional fields, invalid types and formats, length boundaries, leap dates and future dates, names, all 50 state abbreviations plus DC, phones, ZIP codes, email, insurance IDs, whitespace, malicious markup/control characters, protected fields |
| `tests/test_database.py` | Exact column set and nullability, UUIDs, SQLite enum/NOT NULL/primary-key constraints, UTC normalization, automatic timestamps, atomic seeding, repeated startup, existing and soft-deleted records |
| `tests/test_api.py` | CRUD, all seven filter combinations, full and partial updates, clearing every optional field, invalid JSON, UUIDs, HTTP errors, error privacy, rollback after SQL writes, recovery, soft deletion, OpenAPI envelopes, eight concurrent creates |
| `tests/test_live.py` | Real Uvicorn HTTP flow using the documented example files, data persistence across three server launches, standalone seed command run twice |
| `tests/test_vapi.py` | Exported tool schema drift, required fields/enums/patterns, requests built from actual tool URLs, lookup/update adapters, shared phone numbers, soft-deleted records, validation, and database failure rollback |

Defects reproduced and fixed during testing:

- Explicit `preferred_language: null` was replaced by the ORM default on insert.
  The database mapping now preserves explicit null while retaining the English
  default when omitted.
- Required fields set to null in a partial update produced a body-level error.
  Errors now identify each invalid field, including multiple fields in one request.
- Generated OpenAPI documentation described FastAPI's default validation error
  instead of the actual envelope. Documented errors now use `data` and `error`.

One remaining warning comes from the installed Starlette test client deprecating
its `httpx` integration in favor of `httpx2`. It does not fail the tests or affect
the application endpoints. Dependency upgrades should rerun this suite.

The concurrency test is a small correctness check, not a load benchmark. These
tests do not execute a live Vapi voice call or the Phase 4 web interface
(see [phase-4.md](phase-4.md) for manual browser checks).
The Phase 3 prompt and setup instructions exist; conversational acceptance
checks are listed in [the Vapi setup guide](vapi-assistant-config.md).
They also do not claim production security certification or multi-worker startup
testing. Restart any already-running development server to load the fixes.
