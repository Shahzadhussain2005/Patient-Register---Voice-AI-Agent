# Phase 3: configure the Vapi intake assistant

This phase supplies the prompt, three tool definitions, and two thin JSON-body
adapters. The existing REST endpoints remain available. Configuration was
checked against Vapi's documentation on September 24, 2026. A live Vapi call
still needs your Vapi account and a reachable deployment; local tests do not
measure speech quality or prove that a hosted model follows every instruction.

## 1. Start and expose the backend

From the project root, activate the installed dependencies and run:

```powershell
.\.venv\Scripts\python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
curl.exe -i http://127.0.0.1:8000/health
```

Use your deployed service's public HTTPS base URL, for example
`https://patient-api.example.com`. `localhost` on your computer is not reachable
by Vapi. On a hosted service, use the same application module and the port
required by that host. Keep SQLite on a writable persistent volume and set
`DATABASE_URL` to that file. For example, on Linux a mounted `/data` directory
can use `sqlite:////data/patients.db`. Startup creates/seeds an empty database.
If you use a temporary HTTPS tunnel instead, keep it running for the entire
call and update all tool URLs whenever the public hostname changes.

Verify the PUBLIC URL's `/health` and `/docs` before configuring tools. Use
fictional demo patients: the current assessment API has no access control.

Update your local, gitignored `.env` using the placeholders in `.env.example`:

```dotenv
DATABASE_URL=sqlite:///./patients.db
BACKEND_PUBLIC_URL=https://YOUR_DEPLOYED_HOST
VAPI_PRIVATE_KEY=YOUR_PRIVATE_VAPI_KEY
VAPI_ASSISTANT_ID=YOUR_ASSISTANT_ID_AFTER_CREATION
```

`BACKEND_PUBLIC_URL` and `VAPI_PRIVATE_KEY` are read only by the optional setup
snippet below. The backend itself needs neither to serve requests. Store the
private key in `.env`, not in the tool JSON, prompt, browser page, or repository.

## 2. Understand the tool transport

The checked-in [vapi-tools.json](vapi-tools.json) is an array of three **API
Request** tool creation payloads. Vapi derives their arguments from `body` and
waits for the HTTP response. A Function tool instead sends a Vapi-specific
webhook envelope, which the patient REST API does not accept. Use API Request
for these definitions. [Vapi's tool comparison](https://docs.vapi.ai/tools/api-request-vs-function)

| Tool | Vapi HTTP request | Existing behavior reused |
| --- | --- | --- |
| `lookup_patient_by_phone` | `POST /vapi/lookup-patient-by-phone` with `phone_number` in JSON | Same handler as `GET /patients?phone_number=...` |
| `create_patient` | `POST /patients` with confirmed demographics | The existing create endpoint directly |
| `update_patient` | `POST /vapi/update-patient` with `patient_id` and changed fields | Same handler as `PUT /patients/{patient_id}` |

The adapters call the existing handlers in-process; they do not make a second
network request or duplicate database logic. This explicitly moves lookup
arguments and the update UUID from Vapi's generated JSON body to the parameters
expected by the REST handlers. Do not put the UUID into `PUT /patients/{id}`'s
JSON body: its schema deliberately rejects system-managed fields.

Each tool's URL must begin with YOUR backend's public base URL. There is no
separate Function `server.url` to configure. Do not point the assistant's
general Server URL at `/patients`; leave it unset for this integration.
API Request tool configuration uses `body`, not `function.parameters`.
[Request configuration](https://docs.vapi.ai/tools/api-request/configuration)

## 3. Register the three tools

For full-fidelity schema entry, the API snippet below is the easiest route.
It creates three tools in YOUR Vapi account, prints only their names/IDs, and
does not create an assistant or place a call. Run it once after setting `.env`.
If it partially succeeds, keep the printed IDs and finish the missing tools
in the dashboard rather than registering duplicate copies of all three.
The Vapi control API accepts a private bearer key.
[Create Tool reference](https://docs.vapi.ai/api-reference/tools/create)

```powershell
@'
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from dotenv import load_dotenv

load_dotenv('.env')
base = os.environ.get('BACKEND_PUBLIC_URL', '').rstrip('/')
key = os.environ.get('VAPI_PRIVATE_KEY', '')
if urlparse(base).scheme != 'https' or not urlparse(base).hostname or 'YOUR_' in base:
    raise SystemExit('Set BACKEND_PUBLIC_URL to your reachable HTTPS backend.')
if not key or key.startswith(('replace_', 'YOUR_')):
    raise SystemExit('Set VAPI_PRIVATE_KEY in your local .env first.')

tools = json.loads(Path('docs/vapi-tools.json').read_text(encoding='utf-8'))
for tool in tools:
    tool['url'] = tool['url'].replace('https://YOUR_BACKEND_HOST', base, 1)
    request = Request(
        'https://api.vapi.ai/tool', method='POST',
        data=json.dumps(tool).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
    )
    try:
        with urlopen(request, timeout=30) as response:
            saved = json.load(response)
    except HTTPError as error:
        raise SystemExit(f"Tool {tool['name']} was rejected (HTTP {error.code}); inspect the schema in the dashboard.") from None
    print(tool['name'] + ': ' + saved['id'])
'@ | .\.venv\Scripts\python -
```

For dashboard-only setup, open **Tools → Create Tool → API Request** three
times. For each entry, copy `name`, `description`, `method`, the replaced `url`,
and the complete `body` schema. Use a JSON editor/import option if your current
dashboard exposes one; otherwise the API snippet preserves the nested schema
without manually entering every property. Mark precisely the fields in
`body.required` as required, lock additional properties, and retain every
pattern/enum/format. Publish the tools. [Vapi's creation workflow](https://docs.vapi.ai/tools/api-request/quickstart)

Inspect the saved JSON after creation: in particular, verify phone/ZIP
patterns, sex/state enums, and the exact required-field lists. Schema support
can differ between model providers; the API remains the final validator.

Keep the supplied 20-second timeout and the six-second delayed message.
The system-role failure message tells the model to give a field-specific or
general recovery response. No `backoffPlan` is set, so write tools do not
automatically retry and risk duplicate registration.
[API Request behavior](https://docs.vapi.ai/tools/api-request)

The current demo endpoints need no authentication header. Do not send your
private Vapi key to the patient API. If you later protect the backend, create
a Vapi Custom Credential for THAT backend and attach its `credentialId`.
[Endpoint credentials](https://docs.vapi.ai/tools/api-request/configuration)

## 4. Create the assistant

In the [Vapi dashboard](https://dashboard.vapi.ai), create a new assistant
named `Patient Registration Demo` and configure it as follows:

| Setting | Value |
| --- | --- |
| Model | An account-available model that supports tool calling; keep the dashboard's working default initially |
| Transcriber and voice | Working English selections available in your account; preview the voice |
| First message | `Hi, I'm the clinic's AI intake assistant. I can help you register or update your information. What phone number would you like us to use?` |
| System prompt | Paste only the content between `BEGIN SYSTEM PROMPT` and `END SYSTEM PROMPT` in [vapi-system-prompt.md](vapi-system-prompt.md) |
| Tools | Attach the three tool IDs created above; names must match the prompt exactly |
| General Server URL | Unset; request destinations already live on the tools |
| Phone number | None; this project uses browser microphone calls |

The prompt's `{{date}}` is Vapi's built-in UTC date variable. Keep the braces;
do not replace it with the date you configure the assistant.
[Vapi variables](https://docs.vapi.ai/assistants/dynamic-variables)

Publish/save the assistant and copy its assistant ID into `.env`. The same ID
will be used by the Phase 4 Web SDK page. If your dashboard offers browser
testing, allow the microphone and test there; otherwise complete the browser
call test when the Phase 4 page is available. Do not provision a phone number.
Both API Request and Function tools support Web SDK calls.
[Web-call tool support](https://docs.vapi.ai/tools/api-request-vs-function)

## 5. Verify backend wiring before a voice call

Use the automated contract tests with temporary SQLite databases:

```powershell
.\.venv\Scripts\python -m pytest -q tests/test_vapi.py
```

Or inspect a fictional seeded patient through the adapter locally:

```powershell
$body = @{ phone_number = "2025550101" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/vapi/lookup-patient-by-phone" -ContentType "application/json" -Body $body
```

Expected: `data` is an array containing Avery Demo (unless you previously
changed/deleted that demo record), and `error` is null. The same lookup against
the public base URL must work for Vapi. No extra `results` or `toolCallId`
response wrapper is needed for an API Request tool.

## 6. Run these conversational acceptance checks

Use fictional data, inspect tool calls/results in Vapi's call logs, and compare
the saved record in `/docs`. Each row is a test to perform, not a claim that a
live voice call has already passed. Vapi recommends checking arguments and
returned errors rather than judging only what the assistant said.
[Response troubleshooting](https://docs.vapi.ai/tools/api-request/response-handling)

| Caller scenario | Expected conversation and tool behavior |
| --- | --- |
| New number, required fields only | One early lookup; collect nine required fields; one combined optional opt-in; complete readback including English default; one create after explicit approval |
| Volunteer email and apartment early | Retain them without interrupting required collection; include both in readback/create |
| Choose insurance only | Ask only insurance details; do not separately solicit emergency contact or language |
| Future/invalid birth date or nine-digit phone | Re-prompt only for the invalid field; preserve all valid answers |
| `D-A-V-I-S, not D-A-V-I-E-S` | Replace the current spelling; summary and submitted arguments both use Davis |
| `Yes, but the ZIP is 00501` during final approval | No write yet; correct ZIP; full new readback and fresh approval |
| Start over before saving | Discard old draft/selection/consent; lookup again; never save the abandoned draft |
| Return with `2025550101` | Offer an update to Avery Demo; disambiguate identity; update the returned UUID and retain other fields |
| Shared phone number | Ask name/birth date; never choose the first match or read out everyone's data |
| Cancel or disconnect before final confirmation | No create/update call |
| Validation rejection from API | Speak the affected field's issue, correct it, and reconfirm before retrying |
| Backend unavailable/timeout | Audible error; no false success, silent failure, or automatic repeated save |

For a deterministic API validation check, submit a bad birth date/phone directly
using `/docs`. To test voice recovery from backend failure, stop your DEMO
backend before approving a save, then restore it after the test. These are
separate checks: local endpoint tests cannot prove spoken recovery behavior.

## Schema choices and limits

`python -m backend.app.vapi_tools` regenerates `docs/vapi-tools.json` from the
patient schema. Keep the placeholder base URL in version control; the setup
snippet substitutes your public URL at registration time. Field descriptions
carry conversational requirements; enums, formats, and patterns constrain
arguments. The exporter resolves the sex enum and carries over phone, ZIP,
email, and member-ID constraints. String-length limits use regex quantifiers.
Name patterns use ECMAScript Unicode property escapes (`\p{L}`); verify that
your chosen model accepts those schemas rather than replacing them with ASCII
patterns that would reject names the backend supports.

JSON Schema cannot enforce "birth date is not after the current UTC date"
with a portable static constraint. The prompt checks it conversationally and
Pydantic enforces it on every call. Neither schema hints nor the prompt replace
server-side validation or enforce caller consent deterministically.

For Vapi's published schema type subset, the optional voice arguments are
omitted or supplied as strings. Explicit null clearing remains available via
the REST API and adapter, but is not advertised by these voice tool schemas.
Do not use a string such as `"null"` or invent a new clearing field.
[Vapi schema types](https://raw.githubusercontent.com/VapiAI/server-sdk-typescript/main/src/api/types/JsonSchemaType.ts)

What you just learned: the system prompt governs conversation and permission
to act; the tool schema describes arguments; the backend validates and persists
them. A common voice-agent failure is acknowledging a correction while saving
an old value or reusing old consent. The single-current-draft and fresh-readback
rules explicitly address both. A real voice test is still needed to verify how
your selected model follows those rules.
