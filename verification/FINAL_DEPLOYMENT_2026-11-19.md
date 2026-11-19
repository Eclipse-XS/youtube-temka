# Final merge/update/deployment verification — 2026-11-19

## Git integration

Upstream main was fetched: `d0d7bd9ec8fb5196a3876edce8490843d54f7f0a`.
PR [#2](https://github.com/denusbtw/youtube-temka/pull/2) was conflict-free, with
all checks successful at the requested original HEAD
`61b4f7dda2f25c5424dadf4e73296b8346064b2b`.

The merge command with exact-head matching was rejected by GitHub:
`Eclipse-XS does not have the correct permissions to execute MergePullRequest`.
Repository permissions were pull=true, push=false. PR #2 is NOT merged. An upstream
maintainer with merge/write permission must perform the integration. Local main
and upstream were not falsely advanced to the feature implementation.

Actual remotes were preserved:
- origin: https://github.com/denusbtw/youtube-temka.git
- delivery: https://github.com/Eclipse-XS/youtube-temka.git

The updated updater supports canonical origin, fork/upstream and fork-only
bootstrap. Seven isolated real-Git cases passed under Windows PowerShell 5.1:
fork-only bootstrap, configured upstream fast-forward, repeated update, canonical
origin, local-ahead preservation, dirty protection and divergence protection.
Docker and startup were substituted only inside those temporary Git fixtures.
A real post-merge production update cannot be certified while merge is denied.

## Windows failures investigated

Four genuine native compatibility failures were repaired without disabling tests:
- Three host-ASR-slot tests failed because unavailable fcntl silently disabled
  host locking on Windows. Descriptor byte locks now provide exclusive slots,
  while Linux retains its original flock implementation.
- quality_probe returned unknown quality because importing yt_account raised
  ModuleNotFoundError for fcntl. The account module now uses the portable lock
  adapter, and the original guarded single-video probe test passes on Windows.

New tests verify unchanged file contents/position, mutual exclusion across
processes, OS release after a process crash and account cooldown state updates.
References: [Python msvcrt](https://docs.python.org/3/library/msvcrt.html),
[Microsoft descriptor locking semantics](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfile).

Seven unchanged native Windows tests still fail:
- One Unix permission-mode assertion: Windows chmod does not preserve arbitrary
  POSIX 0640/0644 mode bits. The Linux named-volume implementation passes it.
- Six tests execute the POSIX bin/ffmpeg wrapper using `sh`, absent from this
  PowerShell PATH. The wrapper is a Linux deployment component and all six pass
  in the Linux test environment. Native Factory rendering uses the installed
  FFmpeg executable and passed the real smoke test.

No test was skipped, disabled or weakened by these changes. The combined native
run reported 288 passed / 7 failed. The targeted Windows compatibility suite
reported 42 passed. The full Linux suite reported 295 passed (135 Factory plus
160 retained-module tests). Four launcher checks, seven updater checks and four
maintenance checks passed under Windows PowerShell 5.1.

## Actual deployment execution

The exact root command was executed after repairing deployment code:

```powershell
.\scripts\start-factory.ps1
```

It returned READY. Startup from stopped Factory services, repeated startup and
an idle maintenance restart passed. Cached images/models were reused. Stop and
restart now verify processing/publishing idleness. During the disposable smoke
job, an attempted restart returned exit 1 and the controller StartedAt timestamp
remained unchanged; the job continued to completion.

The physical RTX 3050 Laptop 4 GB ran Whisper small/CUDA/int8_float16. A real
23.75-second authorized generated speech source was uploaded through the API,
processed and rendered to a verified 1080x1920 MP4 with audio. The output was
independently decoded (315 frames, 10.5 seconds) and verified in Google Drive.
That smoke test completed READY in 180.83 seconds. No public upload was attempted.
A separate real Qwen inference returned a valid response, and /api/ps verified
2122726768 bytes of GPU offload. The model was then unloaded; nvidia-smi returned
to zero CUDA memory usage. Cold discovery warnings remain observable in Ollama
logs, but the explicit inference/offload check passed.
The normal Factory sequential ASR/LLM lifecycle was preserved; the portable
host-slot adapter was separately verified by the concurrency tests.

The production browser page at http://localhost:5175/factory.html displayed the
connected controller, completed job and online local worker. Authenticated API
checks passed; anonymous jobs access returned 401. SQLite integrity, writable
scratch reserve, persistent data/model mounts and read-only OAuth mounts passed.
The original .env and all OAuth token hashes remained unchanged across execution.

Final required services: controller, web and ollama. Local worker, publisher and
analytics lifecycle threads were RUNNING. Drive, YouTube and Analytics were
CONNECTED. Public and automatic publishing policies remained false.

## Boundaries

Local service readiness is READY. Upstream integration is blocked by repository
merge permissions, not represented as complete. A full Docker Desktop engine
restart was deliberately not performed because unrelated projects are running;
Factory-only stop/start/restart was verified. Physical PC B remains UNVERIFIED.
The final containers are retained running. Current delivered HEAD and CI are
reported by PR #2 and the final operator report; raw logs and private evidence
remain ignored under verification/runtime/.
