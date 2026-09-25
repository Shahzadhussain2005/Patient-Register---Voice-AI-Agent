# Phase 1: patient data model

From the project root, run:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
.venv\Scripts\python -m uvicorn backend.app.main:app --reload
```

Startup creates `patients.db` and inserts two fictional patients if the entire
table is empty. You can also run `.venv\Scripts\python -m backend.app.seed`.
The SQLite URL is configured through `.env`; its relative path is resolved from
the working directory. Run commands from the project root.

`database.py` defines the stored table: primary key, nullable columns, sex enum,
UUID generation, and timestamps. SQLite uses a CHECK constraint for the sex enum.
UTC timestamps retain their timezone when loaded through SQLAlchemy. `updated_at`
advances for updates issued through SQLAlchemy; direct SQL outside the application
does not run Python defaults. An unchanged ORM object does not issue an UPDATE.

`schemas.py` validates input before storage and defines output serialization.
It checks real calendar dates, future birth dates, email format, names, phone
numbers, ZIP codes, state abbreviations, and insurance member IDs. Phone numbers
must contain exactly ten ASCII digits; this checks representation, not whether
a number is assigned or reachable. States accept the 50 states plus DC, using
uppercase abbreviations. Names support Unicode letters, ASCII apostrophes and
hyphens. System-managed fields cannot be supplied in create or update input.

All update fields may be omitted. Use `model_dump(exclude_unset=True)` when
applying updates so omitted fields stay unchanged. Explicit null clears optional
fields; it is rejected for required fields. The language defaults to English
when omitted on creation.

What you just learned: the ORM protects the structure of stored records, while
Pydantic checks incoming values and shapes outgoing data. Both are needed because
API input rules are more detailed than SQLite's column types and null constraints.
No patient REST endpoints or voice features are implemented in this phase.
