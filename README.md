# AI Content Factory

Self-hosted video clipping/editing adapter on the MIT OpenShorts core.

The original AI Content Factory code and OAuth files were absent from the selected
workspace. This implementation preserves the OpenShorts history and excludes its
restricted cloud code from the deployed images. This is not yet a fully accepted
production 6.0 release; verification and remaining blockers are recorded below.

## Start

One-time configuration:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-factory.ps1
```

Preserve the generated `.env`. Mount existing Google authorized-user JSON files
read-only under `secrets/` when available; they are never committed or overwritten.

PC A:

```powershell
docker compose --profile controller up -d --build
```

PC B, after setting its private controller URL/token and its own Drive authorization:

```powershell
docker compose --profile worker up -d --build
```

Open http://localhost:5175 and sign in with the token from `.env`. Initial model
setup is available in Settings. Default processing is CPU/int8; the optional
`compose.gpu.yml` configuration is documented separately.

## What is connected

- FastAPI + React, one durable SQLite queue, authenticated controller/worker calls.
- Bounded URL/local ingest, 15-minute audio chunks, faster-whisper small, language
  detection and word timestamps; no unconditional multi-hour video download.
- Ollama structured ranking with honest deterministic fallback.
- Real FFmpeg vertical center-crop/blur/gameplay layouts, multilingual karaoke
  captions, opening text, bitrate/FPS controls, and chronological 16:9 Longs.
- Preview/approval, transcript exports, verified resumable Drive uploads and cleanup.
- Direct Drive-to-YouTube chunk transfer, private/review defaults, native scheduling,
  daily channel limits, durable sessions, duplicate protection and uncertain states.

## Verification and operational limits

- [Deployment guide](docs/FACTORY_DEPLOYMENT.md)
- [Verification report](verification/REPORT.md)
- [Licenses and upstream integration](THIRD_PARTY_FACTORY.md)
- [Original upstream README](docs/UPSTREAM_README.md)

Run the adapter tests:

```powershell
.venv\Scripts\python.exe -m pytest factory_tests -q
```

On a fresh development machine, create a Python 3.12 venv and install
`requirements-factory.lock` first. Run the API with `uvicorn factory.api:app` and
the dashboard with `npx vite --config vite.factory.config.js` from `dashboard/`.
Normal operator usage uses the web application and Compose, not these commands.

Do not assume real Drive/YouTube acceptance from HTTP fixture tests. Public uploads,
physical dual-PC operation, 4 GB GPU operation and the complete browser workflow
must be verified against the remaining acceptance requirements.
