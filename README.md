# dama5 (AN1 / AN2 RAG app)

Portable copy of the AN1 FastAPI stack. All data paths default to **this folder** (the directory that contains `an1_app.py`). Moving the repo only requires updating `.env` if you use overrides—no hard-coded machine paths in code.

## Prerequisites

- Python 3.11+ recommended
- For full LLM answers: Ollama on `http://localhost:11434` with `mistral:instruct`, or Vertex (see `.env.example`)

## Setup

```powershell
cd $PSScriptRoot   # or: cd path\to\dama5
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env if using Vertex or non-default paths
```

Optional: place `freesound_community-gong-79191.mp3` in the repo root, or set `DAMA_GONG_MP3` to an `.mp3` path.

## Run

```powershell
.\start_dama5.ps1
```

**Sign-in landing** (username + password, SQLite on the server, session cookie) is **on by default**. Open `/` to register or log in, then `/app` for chat. To allow **open chat with no login** (smoke tests, local hacks), set `DAMA_DIY_AUTH=0` in `.env` or the shell.

The `-Diy` switch only sets a dev session secret and `DAMA_SESSION_HTTPS_ONLY=0` for plain HTTP when those are unset (auth is already on by default).

**Listen on all interfaces** (LAN or `0.0.0.0` binding):

```powershell
.\start_dama5.ps1 -Global
```

On HTTPS (e.g. Cloud Run), set `DAMA_SESSION_HTTPS_ONLY=1` and a strong `DAMA_SESSION_SECRET`. **Firebase**: set `DAMA_DIY_AUTH=0` and enable `DAMA_FIREBASE_ENABLED` — DIY mode wins when it is on.

The app loads a repo-root `.env` on startup (variables already set in the shell take precedence).

Or manually:

```powershell
cd path\to\dama5
$env:PORT = 8000   # optional; change if the port is already in use
uvicorn an1_app:app --reload --host 127.0.0.1 --port $env:PORT
```

If `8000` is busy (common with another app), set `$env:PORT = 18080` before `start_dama5.ps1` or uvicorn.

- App: http://127.0.0.1:8000/
- Index status: http://127.0.0.1:8000/api/index_status

If `exists` is false, open the UI and use **Rebuild** / `POST /api/build`, or copy `rag_index_an1` and `rag_index_an2` from another machine.

## Path overrides (optional)

| Variable | Purpose |
|----------|---------|
| `DAMA_DATA_DIR` | Parent for default `an1.json`, `an2.json`, `rag_index_an1`, `rag_index_an2` |
| `AN1_JSON_PATH` / `AN2_JSON_PATH` | Explicit corpus JSON files |
| `CHROMA_AN1_DIR` / `CHROMA_AN2_DIR` | Chroma persist directories |
| `DAMA_DEBUG_LOG_PATH` | Debug NDJSON log path |
| `DAMA_GONG_MP3` | Gong sound file |

## Smoke tests

With the server running:

```powershell
pip install -r requirements-smoke.txt
$env:SMOKE_BASE_URL = "http://127.0.0.1:8000"
pytest test_smoke_from_screenshots.py -q
```

## Slim Vertex-only install

For Cloud Run–style images without local Chroma, use `requirements-an1-vertex.txt` (see dama3 `Dockerfile.an1` pattern).

## Preflight (resolved paths)

```powershell
python -c "import an1_build_index as m; print('BASE_DIR', m.BASE_DIR); print('AN1', m.AN1_PATH); print('AN2', m.AN2_PATH); print('Chroma1', m.PERSIST_DIR); print('Chroma2', m.PERSIST_AN2_DIR)"
```
