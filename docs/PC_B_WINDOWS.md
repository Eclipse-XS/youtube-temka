# PC B: Windows processing worker

Physical deployment is **UNVERIFIED** because no address/remote access is available.
The controller/worker protocol is validated separately using isolated Docker
workers; this guide does not claim that your friend's PC has been configured.

## Obtain this release

Install Docker Desktop with the WSL2 Linux engine, Git and an appropriate NVIDIA
driver. In PowerShell on PC B:

```powershell
git clone https://github.com/denusbtw/youtube-temka.git
Set-Location youtube-temka
git fetch origin main
# Until PR #1 is merged, obtain its verified implementation from the target repo:
git fetch origin pull/1/head:factory-verified
git switch factory-verified
powershell -ExecutionPolicy Bypass -File scripts/setup-factory.ps1 -Role worker
```

After the PR is merged, normal `main` checkouts can use `git pull --ff-only`.
No legacy application, legacy database, or second controller is installed.

## One-time private connection

Connect both PCs to the same trusted LAN or authorized Tailscale network. On PC A,
set these ignored `.env` values to its **specific** private/Tailscale IPv4 address:

```dotenv
API_BIND=<PC-A-private-IP>
WEB_BIND=<PC-A-private-IP>
```

Keep the firewall restricted to PC B/the authorized private network. Tailscale
provides encrypted transport. Do not expose these ports through a public router.
Restart PC A using the controller command below. With `WEB_BIND` changed, both
operators open `http://<PC-A-private-IP>:5175` and use the controller token.

On PC B, edit its ignored `.env`:

```dotenv
CONTROLLER_URL=http://<PC-A-private-IP>:8000
FACTORY_TOKEN=<PC-A-existing-FACTORY_TOKEN>
WORKER_ID=worker-b
```

The newly generated PC B setup token must be replaced with PC A's existing token.
Do not commit `.env`, copy application databases, or run the controller profile
on PC B. Each worker must have a distinct ID.

## Drive and assets

Mount an existing, appropriately authorized standard Google authorized-user JSON
as `secrets/drive-token.json` on PC B. Alternatively configure its own read-only
legacy split-file mount exactly as described in `FACTORY_DEPLOYMENT.md`. No token
is invented, regenerated or overwritten by setup.

For a private shared destination, set `DRIVE_PARENT_ID` on both PCs to the same
authorized folder and ensure both credentials can access it. Drive-only consent
does not authorize YouTube; Publisher runs on PC A with its independently
authorized channel credentials.

Upload approved background/music assets once through PC A. Worker claims carry
only the required, version-pinned asset manifest. PC B downloads and verifies
those assets automatically, reuses intact cache files and prunes obsolete ones.
No full source VOD or unrelated library is copied between PCs.

## Start and check

```powershell
# PC A
docker compose -f docker-compose.yml -f compose.gpu.yml --profile controller up -d --build
# PC B
docker compose -f docker-compose.yml -f compose.gpu.yml --profile worker up -d --build
docker compose --profile worker exec ollama ollama pull qwen2.5:3b
docker compose --profile worker logs --tail 50 worker
```

Whisper small downloads once into the persistent worker model cache. The GPU
overlay uses CUDA 12 for Ollama; the tested Qwen 3B model uses 36 layers only when
measured free VRAM permits it. Other models retain the conservative cap. A
GPU error/timeout has one CPU fallback; GPU-heavy stages run sequentially.
Omit `-f compose.gpu.yml` to use the CPU-compatible deployment.

In PC A Settings, `worker-b` should register automatically with resources and an
online heartbeat. Submit two authorized URL+Drive jobs: independent workers can
claim independent jobs, with at most one active lease per worker. Uploaded local
sources stay on PC A. Inspect each job's actual worker assignment and stages.

If a worker dies, its lease expires into BLOCKED rather than replaying external
effects. After inspection, Retry preserves the controller's selected intervals
even when a different worker lacks the previous scratch directory. Verified Drive
files are never overwritten with mismatched content. A checksum or uncertain
external outcome requires review; it is not silently declared successful.

## Worker launcher

After configuring `.env` with PC A's private `CONTROLLER_URL`, its existing
`FACTORY_TOKEN`, and a unique `WORKER_ID`, run:

```powershell
.\scripts\start-factory.ps1 -Role Worker
```

This starts only local Ollama and the remote worker. The worker keeps its own
`worker_data` / `worker_models` volumes and authenticates to PC A. No credentials
are copied from PC A. Configure authorized Drive files under the read-only secrets
mount. The launcher verifies registration using PC A's reported heartbeat.
Use `-CpuOnly` to force CPU processing. The worker role starts no controller,
web UI, publisher or independent controller queue consumer.
Physical two-machine acceptance remains UNVERIFIED without access to PC B.
