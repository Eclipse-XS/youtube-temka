# Factory 10 performance observations

## Stable-candidate development run

The isolated runner processed the authorized Neverball development inputs with CPU libx264. A 20-second source scan and one 1080×1920 Short took 20.613 seconds. A 40-second two-source scan and 20-second 720p export took 23.418 seconds. One edit workflow, including the initial render, edited proxy and final rerender, took 40.241 seconds. These are individual observations on a shared 6 GiB host with vision disabled for this run. `verification/test-output/f10-release-runner-20261125-010350/results.json` contains the per-stage timings and cache activity.

The baseline Neverball smoke showed rendering as the largest single stage for the Shorts. The two-source export also spent 7.610 seconds retrieving and normalizing selected ranges and 9.064 seconds rendering. The five-output repeat does not form a matched cold-cache median. The production Workload S, Workload L and Workload E requirements are still pending. The historical approximately 280-minute Longs execution could not be reconstructed from an input, configuration and job-log pair in this checkout.

### Live development model probe

A dedicated Docker Ollama 0.40.16 server loaded `qwen3-vl:2b`, digest prefix `0635d9d857d4`, from a separate model cache. The original three-frame request exceeded 2,048 context tokens. The server reported 3,283 required tokens. At 4,096 context the request progressed to image decoding and later timed out. With bounded thumbnails, a 180-second read deadline and one allowed visual call, the repeat again timed out before receiving a response fragment. The fallback was skipped by the one-call budget. The Short still reached `READY` with heuristic selection and no automatic hook in 207.081 seconds. Peak sampled host RAM was 16,166,412,288 bytes and peak device-wide VRAM was 2,038 MiB. Twenty-four GPU layers were requested. The run has no reported actual model placement. The host was shared with verification processes. Evidence is in `verification/test-output/f10-release-vision-bounded-20261125-012328/results.json`.

Use the [target hardware commands](TARGET_HARDWARE.md) to run three fresh-cache and three warm-cache samples per benchmark workload. Establish the matched baseline separately using the same input, model and profile. Report matched cold median reduction and confirmed avoidable inference independently. Preserve the complete sample and include retry time, failures and maximums.

## Matched 12-second timeline benchmark

Three runs per condition compared the initial continuation commit `bb066c6`
with `7f42aab`. Both used the same generated 640×360, 30 fps input and audio
tone, two six-second scenes, 720p delivery, libx264, and disabled text model
calls. Every output passed video and audio decoding and duration checks.

- Fresh cache per run: median 15.300 s at baseline and 14.043 s with the new
  renderer, an 8.2% reduction.
- Repeated identical jobs after a priming run: median 14.189 s at baseline
  and 6.013 s with shared checkpoints, a 57.6% reduction. The worker reported
  hits for source metadata, both selected ranges and both rendered scenes.
- The fresh-cache workload missed the 30% target. Live LLM call savings and
  gameplay recall require separate measurements.
- The Windows host reported an NVIDIA GeForce RTX 3050 Laptop GPU with 6,144
  MiB. The requested physical 4,096 MiB device was unavailable. Job evidence
  samples host RAM, device-wide VRAM and worker cgroup memory when available.

```powershell
New-Item -ItemType Directory -Path scratch/f10-baseline-src -Force
git archive --format=tar -o scratch/f10-baseline-src.tar bb066c6
tar.exe -xf scratch/f10-baseline-src.tar -C scratch/f10-baseline-src
.venv/Scripts/python.exe verification/factory10/benchmark_timeline.py --repo scratch/f10-baseline-src --workspace verification/test-output/f10-bench-baseline
.venv/Scripts/python.exe verification/factory10/benchmark_timeline.py --repo . --workspace verification/test-output/f10-bench-current
```

Each destination must be a new directory. `results.json` records each run and
its MP4 path. `--source` can supply the same saved authorized input to both
variants. The measurements above used the generated fixture.

## Live repeated text selection

The test ran two identical requests against each revision using CPU Ollama
and `qwen2.5:3b`. The model digest was
`357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`.
All four accepted selections were identical. Each live inference evaluated
497 input tokens and generated 119 tokens.

- Baseline first and repeated selection: 1 request in 74.817 s, then 1 request
  in 63.835 s.
- Current first and repeated selection: 1 request in 60.067 s, then 0 requests
  in 0.048 s. The second selection hit the persisted cache.
- This eliminates 100% of repeat-call tokens for this fixed transcript and
  50% of the text requests across the first and second selections together.
  The broader end-to-end and vision-model workload targets remain unverified.

With a local Ollama instance exposing that model, use `--ollama` to select
the endpoint. The example uses the isolated verification server's port.

```powershell
.venv/Scripts/python.exe verification/factory10/benchmark_llm.py --repo scratch/f10-baseline-src --workspace verification/test-output/f10-llm-baseline --transcript verification/transcript-en.json --ollama http://127.0.0.1:11445
.venv/Scripts/python.exe verification/factory10/benchmark_llm.py --repo . --workspace verification/test-output/f10-llm-current --transcript verification/transcript-en.json --ollama http://127.0.0.1:11445
```

## Earlier 900-second and connected-story observations

Both runs used `python -m verification.check_v9`, the same generated media and
request settings, CPU libx264, and the same Windows machine. Each run was one
observation and shared the host with tests. The edited run measured the local
normalization refactor and initial telemetry. Subsequent caption, validation
checkpoint and manifest changes were tested separately.

- 900-second compilation: 293.22 seconds baseline and 275.11 seconds with the new path, about 6.2% less elapsed time in these runs. Both outputs validated at 900 seconds.
- Connected story: 7.75 seconds baseline and 10.26 seconds with the new path. Both produced parts of 5.67, 5.50 and 5.67 seconds.
- Windows reported 16.31 GB installed memory. Start and end available-memory readings were 4.93 and 5.76 GB on baseline, and 4.92 and 7.10 GB on the edited run. These snapshots do not provide job peaks.
- The detected GPU was an RTX 3050 Laptop GPU with 6,144 MiB VRAM. The benchmark used the CPU encoder. Docker's Linux engine was unavailable. Target GPU and container peaks remain unmeasured.

Machine-local reports can be reproduced in ignored `verification/test-output`.
The observed compilation improvement does not establish a median reduction or
reach the 30% target. Matched text-model workload reduction and real-gameplay
editorial comparisons remain unmeasured.

### RTX 3050 Laptop, 4 GiB, Windows 11 and Docker Desktop

The original `qwen3-vl:2b` tag on Windows Ollama 0.40.17 reported GPU model placement. A cold one-image request returned `red` in 46.59 s and a resident three-image request returned it in 54.36 s. The cold three-image schema request timed out at 90 s. The 4.74 s repeat consumed all 400 tokens on thinking and returned no JSON. Smaller JPEGs still incurred about 1,034 tokens per image in the runner.

Factory used Docker Ollama 0.40.16 at `http://ollama:11434`, with a 4 GiB memory limit for each service and capacity for one resident model. The initial container had only the text model. The installed `qwen3-vl:2b-instruct` probe timed out at 90.06 s after GPU discovery reused a stale 645 MiB free-memory estimate. Ollama loaded 19/29 layers on CUDA and placed the projector on CPU. With the model unloaded and 3,962 MiB free reported by nvidia-smi, restarting Ollama restored CUDA projector execution. The runner loaded 26/29 layers on CUDA, with 1,863,361,494 of 2,338,198,648 model bytes in VRAM. On three 256 px gameplay frames at 4,096 context the cold result completed in 44.57 s (first content 38.35 s, 3,199 prompt tokens). The repeated 6.72 s response failed evidence validation, so reliable warm structured generation remains open. The Windows Instruct attempt timed out at 90.02 s with sampled peak host RAM of 15,482 MiB and VRAM of 1,723 MiB. No container OOM kill was observed.

The Shorts profile uses the Instruct tag with automatic placement, a 90 s request timeout, 60 s residency within a serialized stage and a two-equivalent-failure cutoff. The vision stage skips explicit CPU retries and leaves existing heuristic selection available. The existing manual, caption-only and no-text modes remain selectable. Automatic publishing stays disabled.

The launched controller's API job `355aaea5fb1141938f753595a9280a4e` used VoxeLibre's [MineClone2 0.84 gameplay](https://commons.wikimedia.org/wiki/File:MineClone2_-_Release_0.84_-_The_Very_Nice_Release.webm) under CC BY 3.0. GPU discovery regressed to 19/29 layers and a CPU projector during the job. Vision timed out in 90.092 and 89.901 s. Selection retained 36–48 s, then rendered with no automatic hook in 261.61 s including the immediate review-to-render transition. The 42.30 s hook revision reused source metadata and selected media and repeated neither ASR nor vision. The revised MP4 at `scratch/controller/355aaea5fb1141938f753595a9280a4e/clip-1.mp4` carries the exact manual label from 0–12 s. FFprobe and full FFmpeg decode verified 1080×1920, 30 fps, H.264/AAC and 12.00 s duration. Peak sampled Windows RAM and device VRAM during this run were 15,360 MiB and 1,239 MiB. The technical run leaves GTA editorial acceptance, reliable visual placement and the warm structured target open. Launcher readiness reported existing Drive credentials invalid.

#### Follow-up: bounded preload and repeated evidence validation

On the same Qwen3-VL Instruct artifact, the old warm result used evidence indices `[0,1,2]` for a payoff on frame 3 and returned focus coordinates `(100,100)`. The request now constrains frame indices to the supplied set and explicitly asks for fractional coordinates. Semantic validation still rejects invalid evidence. On Docker Ollama 0.40.16 with CUDA 12, the cold request took **68.76 s** and warm repeats took **7.62 s** and **7.53 s** (median **7.58 s**). All three validated and remained uncertain. Ollama logged a CUDA projector and 26/29 GPU layers, with 1,863,361,494 bytes allocated in VRAM for the model. The identical warm input reused its prompt cache. A one-off CUDA 13 check was reverted after the model preload exceeded 60 s.

The original controller's Windows scratch bind returned `EIO`, so job `865fee213ada42b882acd9bb849af254` ran in an isolated controller with the same running Ollama endpoint, model, 4 GiB cap and Factory worker. Ollama was not restarted between the measured request sequence and this job. The resident model had expired. The [Ollama discovery watchdog](https://github.com/ollama/ollama/blob/v0.40.16/discover/runner.go) timed out on reload and the server used a stale 1.5 GiB free-VRAM estimate. It logged 19/29 GPU layers and a CPU projector. The worker made one image-free preload attempt, timed out after **60.06 s**, sent zero generation fragments and skipped further vision. It rendered source seconds **46.3–58.3** via the heuristic path in **118.53 s**. FFmpeg decoded both streams of the resulting 12 s H.264/AAC clip at 1080×1920 and 30 fps. No automatic hook was produced. Peak sampled Windows RAM and device VRAM across this diagnostic and worker sequence were **15,556 MiB** and **2,723 MiB**. No container OOM kill was observed. Artifact: `verification/runtime/factory10-rtx3050-stabilization.mp4`.

The worker now reports preload timeout separately, checks observed allocation before image generation, and allows expansion when RAM, measured VRAM and job budgets permit it. Targeted regression results: 22 passed. Production cold placement after residency expires, a grounded automatic hook in a live job, and the Windows scratch bind remain open.
