# AI Content Factory: deployment and limits

This integration is not yet accepted as a production-ready 6.0 release.
See `verification/REPORT.md` for measured results and the acceptance matrix.
The requested original AI Content Factory repository and its OAuth integrations
were not present: the selected workspace was empty before OpenShorts was cloned.
No working authentication files have been replaced or committed.

## PC A: controller and local worker

Prerequisites: Windows 11, WSL2, working Docker Desktop Linux engine, enough
space for Docker images and model weights in addition to the scratch allowance.
The default path uses CPU/int8 for 4 GB GPU compatibility. NVIDIA acceleration
is optional and separately configured.

1. Run `powershell -ExecutionPolicy Bypass -File scripts/setup-factory.ps1` once.
   This preserves an existing `.env` and creates a random controller token only
   when missing/too short. It does not create Google credentials or contact Google.
2. Open the existing `.env` to obtain `FACTORY_TOKEN` for the local login. Do not
   commit it. All normal API and worker endpoints require authentication.
3. If existing valid Drive OAuth is available, mount the standard authorized-user
   JSON read-only at `secrets/drive-token.json`. Configure `DRIVE_PARENT_ID` for a
   shared authorized parent folder, when required. A service-account key or OAuth
   client-secret-only file is not an authorized-user refresh token. Settings can
   test access without overwriting the original file. Unknown legacy token formats
   still require an adapter after the original project is supplied.
4. Optional YouTube credentials: place each independently authorized standard JSON
   in `secrets/youtube/<alias>.json`. Settings does not expose token contents.
   Publisher discovers the actual authenticated channels before accepting a queue
   item. Do not assume a Drive-only token has YouTube scopes.

Start after initial configuration:

```powershell
docker compose --profile controller up -d --build
```

Open [http://localhost:5175](http://localhost:5175). The API binds to loopback on
port 8000. Ollama has no published host port. SQLite lives in a named data volume;
scratch is a host bind mount under `scratch/controller` or `scratch/worker`, so
free-space preflight observes the physical Windows SSD instead of Docker's much
larger thin virtual filesystem. Whisper/Ollama caches use separate volumes.

In Settings, use **Download configured model** once to install `qwen2.5:3b`.
Until available, highlight analysis explicitly reports heuristic fallback. Model
pulls report actual downloaded bytes. Whisper small downloads on its first use.
Normal starts reuse the model caches and usable OAuth refresh credentials.

## PC B: processing worker

Copy this project, without its runtime data or credentials. Configure `.env`:

```dotenv
CONTROLLER_URL=http://<PC-A-private-or-Tailscale-IP>:8000
FACTORY_TOKEN=<same-controller-token>
WORKER_ID=worker-b
```

On PC A, set `API_BIND` to its specific private/Tailscale IP, and permit port
8000 only from the authorized worker in the host firewall. Prefer Tailscale for
encrypted transport. Do not bind an unauthenticated worker API to the Internet.
The worker makes outbound authenticated calls; it exposes no worker server.

Authorize this machine appropriately for the shared Drive destination. Mount its
own existing valid token read-only. Configure the same `DRIVE_PARENT_ID`.

```powershell
docker compose --profile worker up -d --build
```

This starts a processing worker plus its local model daemon, without a second
controller, dashboard, database service, Redis, or GPU pooling. Optional initial
model installation on PC B:

```powershell
docker compose --profile worker exec ollama ollama pull qwen2.5:3b
```

Remote workers currently accept URL jobs with Drive storage enabled. Uploaded
local source files remain assigned to PC A; complete sources are not transferred
between workers. Remote gameplay assets must be available in that worker's own
background library. Automatic background synchronization is not implemented.
Worker registration is implicit in authenticated heartbeat/claim calls.
Only one lease is active per worker ID. Keep one processing worker per PC.

## Optional GPU acceleration

Requires Docker Desktop/WSL NVIDIA support. The optional image installs pinned
CUDA user-space libraries for CTranslate2. Actual free VRAM is inspected before
ASR selects GPU; each ASR chunk runs in its own process and releases model memory
on exit. Ollama uses CPU, one inference at a time, `keep_alive=0` and 4096 context.

```powershell
docker compose -f docker-compose.yml -f compose.gpu.yml --profile controller up -d --build
docker compose -f docker-compose.yml -f compose.gpu.yml --profile worker up -d --build
```

These are alternatives to the default CPU commands. The machine inspected during
development has RTX 3050 **6 GB**, not the requested 4 GB configuration. GPU
performance and memory safety on physical 4 GB cards remain unverified. CPU mode
does not reserve GPU model memory. `FFMPEG_ENCODER=auto` probes NVENC, otherwise
use `x264`; GPU rendering is not required for a functional CPU deployment.

## Operator workflow

Create → confirm rights → probe URL or upload an authorized video → configure
interval/Shorts/Longs → Generate → Jobs → Editor → review and approve.
Gameplay requires an authorized MP4 background. Center Crop is an explicit fixed
center fallback; automatic face tracking is not enabled in this adapter.
Longs supports explicit source intervals in `start,end` seconds, one per line,
assembled in chronological order. Source time controls use absolute seconds;
Editor candidates use offsets from the selected analysis interval.

Drive is enabled by default. Missing authorization leaves rendered artifacts in
BLOCKED with an actionable explanation. Retry resumes from local transcript/
render checkpoints and persisted Drive sessions. Every uploaded artifact is
verified by size and MD5 before local job scratch is removed. READY does not
depend on publishing. Local test/export mode is available by disabling Drive.

Publisher accepts only approved outputs with verified Drive metadata. It reads
Drive in bounded 8 MiB ranges directly into YouTube resumable uploads; it does
not create a complete local MP4 copy. Private is the default. Public/native
scheduled release requires explicitly enabling public publication for that
authenticated channel. Daily limits use UTC upload-day accounting. Browser
schedule inputs are converted from local time to timezone-aware UTC timestamps.
Automatic generation-to-publishing must be explicitly enabled in the selected
channel's policy and selected for the particular generation job. It assigns
future native YouTube slots at least two hours ahead, using the configured
cadence and daily limit. Manual jobs retain review-before-publication behavior.
There is no analytics-based posting optimizer or recurring calendar UI.

Duplicate queue requests share a unique job/output/channel identity. Retry first
queries the saved upload session, including after a lost final response. An
expired or uncertain session is blocked as UNCERTAIN and requires reconciliation
in YouTube Studio. It never blindly inserts another video. Real Google upload
acceptance remains unverified until valid authorized credentials are supplied.

## Resource and recovery policy

- 8 GiB scratch allowance and 4 GiB free reserve, configurable per worker.
- Inputs are limited to a 60-minute processing interval per job; choose another
  bounded interval for a longer VOD. No silent full-VOD download fallback.
- Audio-first remote analysis in chunks up to 15 minutes; selected video sections
  are fetched after ranking. If independent audio is unavailable, bounded muxed
  sections are used and the strategy is recorded. Downloads stop on budget limits.
- One heavy pipeline per worker ID; 120-second leases with renewal. Disconnected
  jobs become BLOCKED; manual retry can safely reassign and repeat bounded stages.
- Failed/blocked/cancelled unleased scratch expires after 72 hours by default;
  active jobs and recently touched workspaces are excluded. SQLite metadata is kept.
- Verified cloud outputs are cleaned locally. Uploaded local originals are not
  archived by default; once cleaned, layout edits requiring the original need a
  new upload. URL sources can be fetched again. Unverified local export jobs retain
  their output and consume the scratch budget until managed by the operator.
- Large caches are model caches, not a persistent full-source video cache.
- Progress percentages appear only when a measured numerator/denominator exists;
  otherwise the stage is indeterminate. No ETA is invented.

Check health and recent logs:

```powershell
docker compose --profile controller ps
docker compose --profile controller logs --tail=80 controller
docker compose --profile worker logs --tail=80 worker
```

Stop without deleting persistent data:

```powershell
docker compose --profile controller down
docker compose --profile worker down
```

Do not use `down -v` unless you deliberately intend to remove data/model volumes.
Back up the controller SQLite/data volume and keep OAuth files private.
