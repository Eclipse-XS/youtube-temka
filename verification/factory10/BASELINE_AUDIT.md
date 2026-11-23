# Factory 10 baseline audit

The clean Windows checkout was `codex/factory-9-reliability` at
`7cdcf19474e4089ac6ad6617b76a9b1a1789a0fb`. The new `codex/factory-10`
branch starts at that commit. GitHub reported PR #2 open and unmerged, with the
same head. The authorized Eclipse-XS repository's `main`,
`d0d7bd9ec8fb5196a3876edce8490843d54f7f0a`, is an ancestor. The local
`origin` points to the denusbtw fork. The configured `upstream` is OpenShorts.

## Runtime and verification

- The Factory dashboard baseline built successfully with `npm run build -- --config vite.factory.config.js`.
- `docker compose config --quiet` accepted the baseline configuration. Docker's Linux engine pipe was unavailable, so the running deployment, images, and container Ollama endpoint could not be verified. WSL enumeration returned access denied.
- The visible GPU is an NVIDIA GeForce RTX 3050 6GB Laptop GPU with 6,144 MiB VRAM. This host cannot establish the 4 GB release gate.
- The workspace has a Windows virtual environment and a bundled FFmpeg. `ffprobe` is absent from the shell PATH.
- The Factory 9 report records a 219.64-second CPU x264 run for a 900-second controlled compilation. This is historical evidence. The matched local baseline run and test suite were started before editing the pipeline.
- The baseline suite passed 191 Factory tests in 215.24 seconds with restricted Windows loopback access lifted for FastAPI TestClient. The command was `.venv/Scripts/python.exe -m pytest factory_tests -q -p no:cacheprovider --basetemp scratch/f10-baseline-verified`.
- The local baseline `python -m verification.check_v9` run validated a 900-second compilation in 293.22 seconds and three connected story parts in 7.75 seconds. Input settings and measured durations are retained in the local baseline `report.json`. The benchmark shared the host with a test run, so these times are individual observations.

## Existing behavior and gaps

- Factory 9 already ships bounded ingest, recoverable audio chunks, visual/audio signal proposals, connected stories, independent compilation intervals, editable plans, validation, Drive storage and publishing workflows.
- The existing `job_stages` table is keyed only by job and stage. A second source or retry overwrites the current status and units for the first. The original start timestamp survives those overwrites, so calculating per-source elapsed times from it would be incorrect.
- Signal scanning analyzes up to 12 one-minute windows per source. On longer sources, the intervening ranges are unsampled. The current motion and audio thresholds do not establish what actually happened in gameplay.
- Compilation extracts and normalizes selected media, renders excerpts, and validates both the excerpts and the assembled file. These are observed processing passes. Their individual contribution to elapsed time requires measurement.
- FFmpeg progress currently repeats a recursive scratch quota scan during media runs. Ollama generation uses synchronous, non-streaming calls in highlight ranking, hook suggestions and metadata. The worker heartbeat does not report model activity.
- Compilation currently selects ranked fragments, balances across sources and then groups them chronologically within each source. This does not encode a cross-source narrative.
- Regression risks include old job rows and checkpoints, timed captions across source boundaries, partial upload reconciliation, remote worker lease fencing, and legacy highlight ranking.

## 280-minute incident

No attributable job ID, logs, or complete timing manifest was identified in the repository verification reports. The reported incident cannot be decomposed into download, ASR, inference, rendering, validation, and upload time from the available evidence.
