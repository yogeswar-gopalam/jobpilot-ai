# JobPilot AI — free job API starter

## Job listings
Uses the public Himalayas Remote Jobs API, which requires no signup or API key. It primarily covers remote jobs and refreshes daily. JobPilot links to the source/application link and credits Himalayas. See https://himalayas.app/docs/remote-jobs-api for current API details and terms.

## Run on Windows
1. Install Python 3.10+.
2. Extract this ZIP.
3. Double-click `start_windows.bat`.
4. Open http://127.0.0.1:5000.
5. The app loads `.env` automatically. For live AI chat, put a valid OpenAI-compatible provider key in `.env` as `AI_API_KEY`. Keep it private. ChatGPT subscription does not include API usage automatically.

## GitHub
Create a private repo at https://github.com/new and upload extracted files. Do not upload `.env`, `.db`, virtual environments, or keys. `.gitignore` excludes them.

## Render
Create a Render Web Service from the GitHub repo. Build command: `pip install -r requirements.txt`. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 90`. Set `AI_API_KEY`, `AI_BASE_URL`, and `AI_MODEL` in Render Environment if you want live AI chat.

## Limitations
This is a single-user prototype, not a production-ready multi-user service: it has no authentication or per-user data isolation. Do not collect sensitive user information or expose real profiles publicly until auth and a persistent database are added. SQLite may reset on ephemeral hosting. The chatbot needs an AI provider API key; if missing, it clearly reports setup is needed. The app never automatically submits applications or sends emails.
