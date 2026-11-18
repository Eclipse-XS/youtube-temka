# AI Content Factory

Self-hosted clipping and editing on the MIT OpenShorts core. Paste a completed
YouTube/Twitch VOD, choose Shorts or Longs and a style, then Generate. The app
probes the source, analyzes speech in bounded chunks, ranks highlights, renders,
previews and stores verified outputs on Drive. Original audio is the default.

This release is undergoing acceptance; see [actual verification](verification/REPORT.md).
YouTube uploads require an authorized channel and remain unverified in this environment.

## Start

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-factory.ps1
# PC A
docker compose --profile controller up -d --build
# PC B, after its private controller URL/token and Drive mount are configured
docker compose --profile worker up -d --build
```

Open [localhost:5175](http://localhost:5175) and use the token from the ignored
`.env`. Configure models once in Settings. Existing OAuth files mount read-only;
no credential regeneration or replacement is necessary for supported formats.
A working legacy split Drive client/token integration has been reused and verified.

## Included

- FastAPI + React, persistent SQLite queue, fenced local/remote workers.
- Automatic source probing, collapsible advanced controls, reusable preferences.
- Multi-hour audio-first analysis in 15-minute checkpointed chunks; selected video
  retrieval only. No full-VOD download fallback.
- Ollama structured ranking, explained unsuitable/visual decisions, visible
  heuristic fallback on malformed/empty responses or technical failures.
- Original sound, authorized music ducking/fades, silent mode and optional CPU
  Kokoro EN/ES narration with real voice previews.
- CPU face-sampled Smart Crop with smoothing and honest blur fallback, Gameplay
  Split, subtitles, opening hooks, synchronized pause removal, chronological Longs.
- Measured stages, preview/approval, verified resumable Drive uploads, checksummed
  editable-source preservation and new versions after local cleanup.
- Direct bounded Drive-to-YouTube resumable publishing, native schedules, channel
  limits, durable sessions and uncertain-outcome protection. Private/review default.

## Guides and development

- [Deployment: PC A / PC B, GPU, OAuth, recovery](docs/FACTORY_DEPLOYMENT.md)
- [Verification and remaining blockers](verification/REPORT.md)
- [Integration provenance](THIRD_PARTY_FACTORY.md)
- [Optional TTS licenses](docs/licenses/TTS.md)
- [Upstream README](docs/UPSTREAM_README.md)

Default Docker processing uses CPU/int8. The optional GPU overlay checks available
VRAM and unloads sequential model stages; physical 4 GB cards are unverified.
Narration is optional (`WITH_TTS=1`), requires a separate model download and adds
GPL phonemizer/eSpeak dependencies; the normal clipping image excludes them.

Python 3.12 development: install `requirements-factory.lock`, plus pytest, in a
venv. Run `python -m pytest factory_tests -q`. Build the actual UI with
`npm run build -- --config vite.factory.config.js` in `dashboard/`.
CI also exercises retained MIT modules on Linux, validates Compose and scans for
credential patterns. HTTP protocol fixtures are never described as real Google
acceptance tests. No public uploads occur without explicit channel authorization.
