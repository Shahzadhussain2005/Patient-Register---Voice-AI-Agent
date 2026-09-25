# Phase 4: voice frontend (Vapi Web SDK)

The intake page starts browser microphone calls. Vapi's API Request tools still
call your Render backend; the webpage does not talk to the patient API.

## Layout

```text
frontend/
  index.html
  package.json
  vite.config.js
  .env.example
  public/favicon.svg
  src/
    main.js
    lib/vapi.js      # Web SDK wrapper (public key only)
    ui/app.js        # Call controls + transcript
    styles/
      tokens.css
      app.css
```

## Configure

1. Copy `frontend/.env.example` to `frontend/.env`.
2. Set `VITE_VAPI_PUBLIC_KEY` from the Vapi dashboard (API Keys → **Public**).
3. Set `VITE_VAPI_ASSISTANT_ID` to the assistant created in Phase 3.

Never put `VAPI_PRIVATE_KEY` in `frontend/` or any browser bundle.

## Run locally

```powershell
cd frontend
npm install
npm run dev
```

Open the printed URL (usually `http://localhost:5173`), allow the microphone,
and click **Start Call**.

## Production build

```powershell
cd frontend
npm run build
npm run preview
```

Host `frontend/dist` on any static host (or a separate Render static site).
The voice page does not need your FastAPI origin for calls.

## End-to-end check

1. Render backend `/health` returns ok.
2. Vapi tools point at your live Render URLs (not `YOUR_BACKEND_HOST`).
3. Start a call; when asked for a phone, use a seeded demo number such as
   `2025550101`.
4. Confirm tool results in the Vapi call log and that the assistant speaks the
   outcome.
