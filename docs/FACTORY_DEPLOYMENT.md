# Deployment and recovery

See `verification/REPORT.md` for actual acceptance evidence and remaining blockers.
Existing Drive OAuth was found in the earlier Factory worktree and reused through
`factory/legacy_drive_oauth.py`. Original client/token files remain unchanged.
Current release checks are in `verification/RELEASE_2026-11-18.md`. No authorized
YouTube channel token is available in this workspace or the inspected legacy
connection ledger; live publication remains blocked.

## PC A

Windows 11 + WSL2 + Docker Desktop Linux engine, Python/Node only for development.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-factory.ps1
docker compose --profile controller up -d --build
```

Open http://localhost:5175 and sign in with the generated token in `.env`.
Settings offers the one-time Ollama model download. Whisper caches on first use.
The default CPU/int8 path does not require a GPU. Data and model caches persist
in separate named volumes; scratch binds to the physical host SSD under
`scratch/controller` for accurate free-space checks.

Standard Drive credentials: mount an existing authorized-user JSON at
`secrets/drive-token.json`. Alternatively set `LEGACY_DRIVE_SECRETS_DIR` to the
existing split-file directory, `DRIVE_OAUTH_CLIENT_FILE=/run/legacy-drive/client.json`
and `DRIVE_OAUTH_TOKEN_FILE=/run/legacy-drive/token.json`. The mount is read-only.
Do not replace working credentials. Set `DRIVE_PARENT_ID` only for an authorized
private destination. Unknown or publicly shared destination permissions block uploads.

YouTube: mount independently authorized standard JSON files at
`secrets/youtube/<alias>.json`, with YouTube upload/channel scopes. Publisher's
Discover action reads the actual authorized channels. Drive-only authorization
cannot grant YouTube access. Public/scheduled upload additionally needs explicit
per-channel public authorization. The default is private and review first.

For a channel that has not been authorized, enable the YouTube Data API in its
existing Google project and use a **desktop** OAuth client on the host:

```powershell
.venv/Scripts/python.exe -m factory.youtube_oauth --client C:/private/youtube-desktop-client.json --output secrets/youtube/operator.json
```

The browser consent uses PKCE, a loopback callback and a five-minute deadline.
It requests `youtube.upload` and `youtube.readonly`, creates a new standard
authorized-user file exclusively, and never replaces existing credentials or
uploads a video. Mount `secrets/youtube` read-only and use Publisher Discover to
verify the intended channel. A Drive-only token cannot satisfy this consent.

## PC B

Clone the repository without `.env`, runtime data or credentials. Run setup with
`-Role worker`, then set the following in its ignored `.env`:

```dotenv
CONTROLLER_URL=http://<PC-A-private-or-Tailscale-IP>:8000
FACTORY_TOKEN=<existing-controller-token>
WORKER_ID=worker-b
DRIVE_PARENT_ID=<authorized-private-shared-parent-if-used>
```

On PC A, bind `API_BIND` to its specific private/Tailscale IP and restrict its
firewall to authorized workers. Tailscale supplies encrypted transport. The
worker makes outbound authenticated calls and exposes no worker port.
Mount appropriately authorized existing Drive tokens read-only on PC B.

```powershell
docker compose --profile worker up -d --build
# One-time model setup on PC B
docker compose --profile worker exec ollama ollama pull qwen2.5:3b
```

No second controller/UI/Postgres/Redis. Each PC has local model caches and one
heavy pipeline. URL jobs with Drive enabled are eligible for a remote worker;
controller uploads stay on PC A. No complete source video is transferred between
PCs. Worker registration is automatic. Upload rights-confirmed background/music
assets once through the controller. Claims include a manifest for only the
required assets, including the controller's automatic background choice. Workers
fetch them over the same authenticated private connection and verify SHA-256
and byte size before rendering. No source library or credential directory is
exposed by the asset endpoint.

The worker cache is limited by `ASSET_CACHE_BYTES` (default 2 GiB) and also counts
toward its 8 GiB processing budget. Intact current assets are reused; corrupt
files are fetched again, obsolete cache files and failed partial transfers are
removed. Oversized assets block the job with recovery guidance. Original approved
controller assets are retained. Use the private LAN/Tailscale endpoint described
above; this transfer adds no storage service or public worker port.

## Optional GPU

```powershell
# PC A
docker compose -f docker-compose.yml -f compose.gpu.yml --profile controller up -d --build
# PC B
docker compose -f docker-compose.yml -f compose.gpu.yml --profile worker up -d --build
```

The overlay installs pinned CUDA libraries and makes the GPU available to
Whisper and Ollama. ASR chooses CUDA only with at least 2500 MiB free, otherwise
CPU/int8. Each chunk exits its subprocess before LLM analysis. For the measured
`qwen2.5:3b` model, Ollama uses 36 layers only with at least 3500 MiB free;
unknown models retain the 24-layer cap and a 1000 MiB reserve. Context is 4096
with one parallel request. Ranking reuses one model/GPU plan across its windows,
then explicitly unloads it. A 60-second TTL also bounds retention after a crash.
A GPU server error or timeout retries once on CPU; later windows retain CPU
after that fallback. The GPU overlay selects the bundled `cuda_v12` backend;
`OLLAMA_LLM_LIBRARY` can override it for separately tested hardware.
This is a conservative policy, not a guarantee for every competing GPU workload.
The current machine has RTX 3050 **4 GB**. Docker CUDA initialization, small ASR
with `int8_float16`, sequential local Qwen inference and rendering have been
exercised on it. See the release report for sampled peaks and the exact limits
of this acceptance; a short smoke test does not establish sustained multi-hour
reliability or compatibility with arbitrary competing GPU workloads.
NVENC is optional through `FFMPEG_ENCODER=auto`; x264 is the default. A real
two-second H.264 NVENC encode passed on this card; sustained NVENC quality and
performance are not inferred from that smoke test.

## Optional narration

Set `WITH_TTS=1` in `.env`, rebuild, then use Settings to download the pinned
Kokoro model and listen to voice previews. EN/ES voices run on CPU in a separate
process. Model downloads report actual byte counts and verify SHA-256. Ordinary
clipping does not require this runtime or model. See `docs/licenses/TTS.md` for
MIT/Apache weights and optional GPL dependencies. RU/UK narration is unavailable;
original audio and multilingual captions remain usable. Voice-over is always an
explicit per-job choice; a TTS failure cannot block unrelated original-audio jobs.

## Operator workflow and recovery

Paste URL → automatic metadata → Shorts/Longs + style → confirm source rights →
Generate → measured Jobs stages → Editor preview → approve → Publisher.
Advanced options include full VOD, manual intervals, captions, sound modes,
licensed background/music, hooks and output quality. Preferences exclude source
URLs, rights assertions, narration text and automatic-publication consent.

Automatic uses an approved gameplay asset when present, otherwise CPU face
sampling with a smoothed horizontal camera. No detected face falls back to Blur.
Explicit Crop is fixed center. Largest-face selection is basic: speaker diarization,
identity tracking and visual-event understanding are not claimed.

Longs ranks global candidates and assembles selected intervals chronologically.
Silent/no-speech short footage can use Silent Video; longer visual sources require
manual intervals. The application does not invent narrated content for them.

Audio-first chunks are at most 15 minutes with independent JSON checkpoints.
Full-VOD analysis accepts known source duration up to 24 hours. Failed downloads
never fall back to downloading a full remote VOD. Default scratch budget 8 GiB,
free reserve 4 GiB; model cache and Docker images require additional disk space.
Manual clips without captions skip ASR. Pause removal trims video/audio together
and rebases word timestamps. Source audio remains the default.

Drive uploads rendered videos, thumbnails, transcripts, metadata and selected
**raw editable intervals**, verifies size/MD5, then removes the local job workspace.
The full original is not archived. Editor can retrieve a preserved interval with
bounded/checksummed reads and create a new version after cleanup; trimming cannot
extend beyond that preserved interval. Older outputs without these sources need
one re-upload or their original URL. Local exports keep files under scratch.

Drive artifacts and preserved editable intervals are retained indefinitely;
there is no automatic cloud deletion. Monitor the authorized Drive quota and
review old outputs and their editable sources together before manually removing
them. Local cleanup never substitutes for verified persistent storage.

Cancel fences the old worker and kills its subprocess group. Retry resumes
checkpoints. Worker leases expire after 120 seconds into BLOCKED, never blind
external replay. Unleased failed/cancelled work expires after 72 hours; active
jobs are excluded and metadata remains. The health endpoint detects a dead local
worker. Authenticated stage history and transition events survive restarts.

Publisher reads Drive in 8 MiB ranges directly into YouTube resumable uploads.
It stores sessions, reconciles final acknowledgments, enforces daily limits and
unique job/output/channel identity. UNCERTAIN requires YouTube Studio reconciliation;
it never blindly inserts a duplicate. YouTube scheduling uses timezone-aware UTC.
No real YouTube acceptance is claimed from fixture tests.
Before an upload session exists, Publisher lets the operator edit queued/failed
titles, descriptions, visibility and future schedules, then requeue. Session or
video identity prevents editing and duplicate reinsertion. Quota/permission
failures have bounded, sanitized diagnostics. Remote verification checks channel,
privacy, successful upload status and the exact native schedule.
Explicit source credits survive queue creation/editing; descriptions are checked
against YouTube's 5000-byte UTF-8 limit before upload. Invalid markup or oversized
multilingual descriptions receive a preflight error rather than silent truncation.

## Development checks

For the exact Windows worker setup, private binding, shared authorization and
physical acceptance limits, see [PC B setup](PC_B_WINDOWS.md). Two isolated local
Docker workers have been exercised; this does not establish two physical PCs.

Weak, heuristic or ungrounded selections require Editor approval even when
automatic publishing is enabled. A source quote replaces an unsupported model
title; that fallback is visible and is not a claim of editorial quality.

```powershell
.venv/Scripts/python.exe -m pytest factory_tests -q
.venv/Scripts/python.exe -m compileall -q factory
.venv/Scripts/python.exe scripts/check-secrets.py
# dashboard directory
npm run build -- --config vite.factory.config.js
```

Retained upstream POSIX tests run on Linux in CI. The actual production UI is
`factory.html`, built through `vite.factory.config.js`. Deployed images use an
explicit MIT-core allowlist and exclude upstream `cloud/` code.
