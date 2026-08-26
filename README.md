# AIIC Challenge Demo

Minimal end-to-end demo: browser input -> Python backend -> OpenAI-compatible chat API -> browser response.

## Run locally

```powershell
$env:LLM_API_KEY = "your-key"
$env:LLM_BASE_URL = "https://jojocode.com/v1"
$env:LLM_MODEL = "codex-auto-review"
python app.py
```

Open <http://127.0.0.1:8000>.

## Run on the server

Put `LLM_API_KEY` in a server-only `.env` file. Never commit `.env` or paste the key into GitHub.

