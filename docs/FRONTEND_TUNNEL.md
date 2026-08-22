# Frontend ↔ local API over ngrok

The ranking model is unchanged. `POST /api/v1/frontend/therapy` only
normalizes `{mutation, clinical}` and calls the existing `recommend()`.

```
Browser
   │  HTTPS
   ▼
https://roxanna-matterless-frightenedly.ngrok-free.dev
   │  ngrok → local :8000
   ▼
uvicorn on this laptop
```

## What went wrong last time

| Symptom | Cause |
|---|---|
| `[Errno 48] address already in use` | API is **already** on :8000. Do not start a second uvicorn. |
| `zsh: command not found: #` | Comments were pasted into the same shell as commands. Use a **second** terminal for ngrok. |
| `ERR_NGROK_4018` | ngrok is not logged in. Run `ngrok config add-authtoken …` once. |
| `ngrok http 80` | Dashboard default. This API listens on **8000**, not 80. |

## Run it

Confirm the local API (one terminal):

```bash
curl -s http://127.0.0.1:8000/api/v1/frontend/health
```

If that fails, start it (only then):

```bash
cd /path/to/sih
export PYTHONPATH=.
backend/.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Second terminal — reserved domain, **port 8000**:

```bash
ngrok http 8000 --url https://roxanna-matterless-frightenedly.ngrok-free.dev
```

If you see `ERR_NGROK_4018` first, copy the token from
https://dashboard.ngrok.com/get-started/your-authtoken and run **one** line
(do not paste angle brackets):

```bash
ngrok config add-authtoken YOUR_AUTHTOKEN
```

Frontend `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=https://roxanna-matterless-frightenedly.ngrok-free.dev
```

Optional: `GENOGUIDE_TUNNEL_KEY` on the API and `NEXT_PUBLIC_GENOGUIDE_TUNNEL_KEY` on the UI (same value).

## Request

`POST /api/v1/frontend/therapy`

```json
{
  "mutation": { "gene": "EGFR", "protein_change": "p.Leu858Arg" },
  "clinical": { "indication": "lung adenocarcinoma" }
}
```

Headers: `Content-Type: application/json`, `ngrok-skip-browser-warning: true`.
Do not send `patient_id` or other identifiers.
