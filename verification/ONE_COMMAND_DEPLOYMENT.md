# One-command deployment verification — 2026-11-19

Upstream synchronized and re-fetched: `d0d7bd9ec8fb5196a3876edce8490843d54f7f0a`.
The original feature branch was preserved; local `main` was fast-forwarded.
No reset, clean, force push, credential replacement or volume deletion occurred.

## Operator command

```powershell
.\scripts\start-factory.ps1
```

Controller is the default. `-Role Worker`, `-CpuOnly`, `-Rebuild`, `-Status`,
`-WithTTS`, and `-TestInference` are supported. Stop/restart/logs/update scripts
are included. Existing configuration is never automatically migrated or rewritten;
invalid required settings stop startup with an error. New `.env` creation is tested
in isolation with simulated Docker, not by deleting the operator's real file.

## Verified application behavior

- Windows Docker Desktop Linux engine 29.7.2; WSL2 kernel
  `6.6.87.2-microsoft-standard-WSL2`; physical RTX 3050 Laptop, 4096 MiB.
- Startup from stopped controller services and a repeated startup passed using
  existing volumes. Unchanged images were reused without a build; cached Ollama
  and Whisper models were reused. The production frontend and authenticated
  API proxy responded. Anonymous jobs access returned 401; authenticated settings
  returned 200. Browser sign-in and Settings integration checks passed.
- Controller/local worker, publisher and analytics lifecycle threads were running.
  Actual container data/scratch/model mounts and read-only secrets mount were
  verified. SQLite quick_check, writable paths and scratch reserve passed.
- Final Drive, YouTube and Analytics checks: CONNECTED. After the operator
  supplied a Desktop OAuth client and confirmed two separate Google consent
  flows, one publishing channel and one read-only Analytics connection were
  discovered. Analytics completed a real sync with a saved report and no errors.
  Public and automatic publishing policies remain disabled. No new YouTube
  publication was attempted. Optional TTS was not downloaded or enabled.
- The `.env` and two existing OAuth files matched their private SHA256 baseline
  after rebuilds and service restarts. Two new consented tokens were created
  exclusively under ignored secrets paths; the supplied client was not copied
  into source control. Consistent SQLite backups were created
  using SQLite's online backup API, including a tested WAL-backed database.
- An isolated remote worker authenticated and registered a fresh heartbeat on
  the private Compose network. It started no controller/UI/publisher. It was
  stopped after the check; persistent volumes were retained.

## Physical inference and video acceptance

A generated, authorized 23.75-second English speech/video fixture was uploaded
through the real API. No mocked ASR, LLM, renderer or Drive transport was used.
Each output independently decoded as 315 frames / 10.5 seconds, 1080x1920,
with audio, and passed the application's media checks and verified Drive delivery.

| Mode | Jobs | Actual ASR | End-to-end seconds | Result |
|---|---:|---|---|---|
| NVIDIA | 2 sequential | small / CUDA / int8_float16 | 131.22; 120.44 | PASS |
| Explicit CPU | 1 | small / CPU / int8 | 299.20 | PASS |

The final Ollama inference returned a valid response and `/api/ps` confirmed
2122726768 bytes of GPU offload; the model was explicitly unloaded afterward.
A cold restart had logged a transient GPU-discovery timeout before that successful
verification.

Sampled GPU peak: 2055 MiB of 4096 MiB. No accumulated-allocation failure appeared
in these two sequential jobs. ASR exited between stages and the existing Ollama
unload lifecycle was retained. This is bounded acceptance, not a long stress test.

## Controlled recovery acceptance

The controller was restarted during a disposable render. Eight checkpoint files
existed before interruption; they survived. The durable lease expired into
BLOCKED, then an explicit API retry completed READY with one output. Total test
time was 235.06 seconds. No production job or publication was interrupted.

## CUDA download/build repair

The pinned cuBLAS/cuDNN versions were retained. Their authentic Linux x86_64
PyPI distributions built and executed successfully with the existing pinned
Python 3.12 / CTranslate2 / Faster-Whisper stack. NVRTC, a declared cuBLAS
transitive dependency, is now pinned too. The reported historical integrity and
timeout failures concern download transport; the available historical evidence
cannot distinguish a CDN, proxy or local partial-cache cause. A version/ABI
incompatibility was not reproduced on this physical machine.

The Factory-specific lock and manifest record authentic SHA256/size values from
PyPI, with TLS verification, bounded retries, failed-part cleanup, a persistent
BuildKit wheel cache, optional locally prefilled wheels, and an offline
`pip --require-hashes` installation. Tests reject corrupt content and prove cache
reuse. Subsequent GPU builds reused verified local wheels without network
redownloads. The separate upstream/cloud `requirements-gpu.lock` was preserved.

Authoritative distribution metadata:
- [cuBLAS PyPI metadata](https://pypi.org/pypi/nvidia-cublas-cu12/12.9.3.13/json)
- [cuDNN PyPI metadata](https://pypi.org/pypi/nvidia-cudnn-cu12/9.28.0.42/json)
- [NVRTC PyPI metadata](https://pypi.org/pypi/nvidia-cuda-nvrtc-cu12/12.9.86/json)

## Regression evidence

- Linux: 291 tests passed in the full Factory + retained-module run. The newly
  added readiness/PowerShell JSON compatibility test passed separately; 292
  distinct Python tests passed in total (135 Factory, 157 retained).
- Windows: all 135 Factory tests passed across the full and added focused runs.
  The combined native run reported 280 passed / 11 failed before the final
  added API test. Those retained-module failures involve Windows permissions,
  shell/probe and host-locking behavior; the same tests pass in Linux. No tests
  were disabled. Initial missing tzdata was installed at its already locked version.
- A real complete startup passed under Windows PowerShell 5.1 from the parent
  directory, reusing images and reporting all integrations CONNECTED / READY.
- Four launcher checks passed under Windows PowerShell 5.1: secure first run,
  repeated configuration preservation, invalid configuration preservation and
  active-job protection. A live active CPU job also rejected deployment changes
  with exit 1 while read-only status remained usable.
- Production frontend builds, CPU/GPU Compose configuration, compileall and
  tracked-source secret scans passed. Logs maintenance returned exit 0.
- The updater's dirty-worktree guard returned exit 1 without changing Git or data.

Raw logs, job IDs, credential hashes and media remain ignored under
`verification/runtime/`; they are not public release artifacts.

## Limits

Physical PC B acceptance remains UNVERIFIED. Restarting the entire Docker Desktop
engine was not performed because unrelated stacks are running; the Factory
services were stopped and restarted. A live post-merge GitHub upgrade remains
UNVERIFIED until this implementation is merged upstream. OAuth consent is
complete on this machine; other installations require their own consent. These
limits do not block local video generation and verified Drive output.
