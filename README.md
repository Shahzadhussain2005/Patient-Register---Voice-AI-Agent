# Patient Register (MVP)

Voice patient intake: browser call → Vapi assistant → Render API → database.

```text
Patient Register/
  backend/          # FastAPI patient API + Vapi tool adapters
  frontend/         # Auralis voice page (Vapi Web SDK)
  docs/             # Phase guides + Vapi config
  tests/            # Pytest suite
```

## Backend

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

See `docs/phase-1.md`, `docs/phase-2.md`, and `docs/vapi-assistant-config.md`.

## Frontend (Phase 4)

```powershell
cd frontend
copy .env.example .env
# Edit .env: VITE_VAPI_PUBLIC_KEY + VITE_VAPI_ASSISTANT_ID
npm install
npm run dev
```

Details: `docs/phase-4.md`. Never put `VAPI_PRIVATE_KEY` in `frontend/`.
