# AGENTS.md

## Cursor Cloud specific instructions

This repo is a single Flask process serving two independent apps (see `README.md` and `.cursor/rules/platform.mdc` for the editing-scope rules):

- VibeSpeak（音読）at `/` and `/admin` — package `flask_app/`
- Vibe Speak News at `/news/` and `/news/admin/` — package `news_app/`

### Running (development)

- A Python virtualenv lives at `.venv/` (the update script keeps its dependencies current). Activate it with `source .venv/bin/activate` before running anything.
- Dev server: `python run.py` → serves on `http://127.0.0.1:5001` (binds `0.0.0.0`). This is the dev entrypoint; `wsgi.py` / `gunicorn wsgi:application` is the production entrypoint (see `Procfile`).
- Health checks: `GET /health` (VibeSpeak) and `GET /news/health`.

### Non-obvious gotchas

- No automated test suite and no linter config exist in this repo. `python -m compileall flask_app news_app` is a quick syntax sanity check.
- The app runs and all pages render **without** `OPENAI_API_KEY`, but AI features (News summary evaluation/vocab/warmup, VibeSpeak grammar/OCR/TTS) need a real key. Set it in `.env` (`OPENAI_API_KEY=...`) or via the News admin settings UI. `news_app` auto-creates `.env` from `.env.example` on import if missing.
- News admin "settings save" (`POST /news/admin/api/settings`) is gated by a hardcoded password: `2479`.
- News persistent state is a JSON file at `data/app_state.json` (override dir with `NEWS_DATA_DIR`). It is not committed (`*.json` is gitignored); delete it to reset News state.
- `flask_app/` and `news_app/` must never import each other (enforced by project rules).
