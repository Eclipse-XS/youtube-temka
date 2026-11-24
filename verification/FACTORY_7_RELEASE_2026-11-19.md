# Factory 7 — release verification, 19 November 2026

## Release status

**READY WITH LIMITATIONS.** The application is running and usable locally.
Implementation and automated verification are complete for the scope described
below. Live YouTube publication, real Drive trash operations, physical 4 GiB
GPU acceptance and the browser file-picker path are not certified by this run.

## Git and delivery

- Branch: `codex/factory-7-memory`, pushed to `denusbtw/youtube-temka`.
- Implementation SHA: `57c0be3530ddfe7f673eb5d031c6af8849a81e02`.
- PR: <https://github.com/denusbtw/youtube-temka/pull/3>; open, not merged.
- Existing startup work from PR #2 was merged into this branch without rewriting
  history. OAuth, database, model caches and persistent media were preserved.
- Implementation CI is green: [run 44568650140](https://github.com/denusbtw/youtube-temka/actions/runs/44568650140).
  The documentation-only delivery commit receives its own PR checks.

## Milestone and feature verification

### A — reliability and publication

IMPLEMENTED / TESTED: shared reentrant host lock, bounded subprocess/log handling,
RAM admission, persisted ASR chunk plans, safe retries, approval/render identity,
manual versus automatic publication policies, resumable upload reconciliation,
channel-timezone scheduling and read-only reconciliation of due schedules.
E2E VERIFIED: actual cancel/retry reused a completed transcript checkpoint;
one-command startup, CUDA inference and unchanged-image restart succeeded.
NOT VERIFIED: new live YouTube upload or scheduled public release. No upload was
queued in this verification. Publication uncertainty preserves the existing
remote video identity instead of automatically uploading another copy.

### B — editor and interface

IMPLEMENTED / TESTED: five primary navigation sections; layout/text previews;
five text modes; bounded text rendering; six original CC0 starter backgrounds;
library uploads, presets, selected-video preview, source editing, immutable
render versions, subtitle styling, logos and end CTA. Browser checks exercised
Create, Settings, Editor and Publish, metadata editing and approval. Metadata
editing preserved the rendered hash and revoked approval, verified through API.
E2E VERIFIED: split layout, subtitles, static hook, logo/CTA and two-segment edit
using owned media; verified Drive persistence. Final UI console had no captured
errors. Browser file selection remains NOT VERIFIED; see limitations.

### C — AI and video intelligence

IMPLEMENTED / TESTED: structured hooks and metadata, deterministic candidate
ranking, neutral fallback with review, bounded subtitle translation, connected
series from one continuous event, ordered Longs timeline, technical decode/audio
and endpoint synchronization validation. E2E VERIFIED: real Ollama selection and
metadata, five hook candidates returned by Ollama with review required; connected
three-part Shorts with exactly 3-second overlap; chronological Longs with logo/CTA.
AI text remains an editorial draft: schema/quoted support cannot guarantee that
every generated sentence is grounded or complete. Review is visible in the UI.

Longs editing uses hard cuts and source intervals. Optional first/last intervals
serve as intro/outro; arbitrary external intro/outro tracks, transitions and a
professional multitrack editor are outside the implemented boundary.

### D — storage and release

IMPLEMENTED / TESTED: package retention, default OFF, 50-package limit, 7-day
grace, protection, dry-run, history, shared manual/automatic eligibility policy,
live publication recheck, ownership/hash/size checks, verified recoverable trash
and retryable deletion failures. No folders or untracked files are recursively
removed. E2E VERIFIED: real Drive saves and checksums. NOT VERIFIED: actual trash
operations; no real package was removed. Documentation, Docker images, startup,
Git delivery and automated regression checks are complete.

## Tests and actual media runs

- Exact implementation CI: 176 Factory tests; 160 retained core tests; 42 native
  Windows tests, plus PowerShell launcher/updater/maintenance checks; production
  frontend build, secret scan, compilation and Docker configuration checks passed.
- Docker controller/web images built; controller, web and Ollama healthy. Runtime
  source hashes for API/media/pipeline/hooks/publisher/heavy match implementation.
- Actual CUDA Whisper inference succeeded in a process which then exited.
- Short + hook/subtitles: 20-second output, 108.42 seconds processing.
- Connected split Shorts: three 8.666667-second outputs, 208.84 seconds processing.
- Longs timeline + logo/CTA: 16.021333-second output, 131.34 seconds processing.
- Automatic selection: 5.366667-second output, 216.92 seconds processing; selection
  and metadata used Ollama. Initial controlled runs used visible extractive
  metadata fallback; later automatic and two-hour runs verified the corrected AI path.
- Two-hour source: 7280.064026 seconds, 25 ASR chunks, one 7.233333-second output,
  221.25 seconds processing, 228.52 seconds including harness overhead. Cancel/retry
  after completed chunks preserved the first transcript's size and modification
  time. Output validation and Drive verification succeeded.
- Queue processing states, editorial review/approval and publication states remain
  separate: a READY render is not proof of publication. SCHEDULED is reconciled
  to PUBLISHED only after public/processed confirmation; uncertainty stays explicit.

## Measured resources

Measurements sampled Docker working sets every roughly 2–3 seconds, including
command overhead. They may miss short peaks and exclude Windows/WSL VM cache,
other applications and most host processes. Per-container individual maxima
must not be added as if they occurred simultaneously.

- Three sequential media cases: combined controller/Ollama/web peak
  **4,213,866,234 bytes (3.924 GiB)**; system GPU maximum 2544 MiB; 149 samples.
- Automatic selection case: combined peak 3,681,609,057 bytes; GPU 2524 MiB.
- Two-hour case: combined peak 3,317,642,035 bytes; GPU 2571 MiB; 72 samples.
- GPU measurements are system-wide and include the desktop. Actual GPU is an
  RTX 3050 with **6 GiB**, so these are not physical 4 GiB acceptance results.
- After the three-job run, controller RSS was about 165 MiB, Ollama RSS about
  364 MiB. Larger idle working-set readings included cgroup file cache: roughly
  1.59 GB controller file pages and 2.91 GB Ollama file pages. No global WSL cache
  settings were changed. Final Ollama `/api/ps` returned no loaded models.
- Both service cgroups reported `oom=0` and `oom_kill=0`. Ollama reported 2817
  `max` events (memory-limit pressure/reclaim); these are not OOM kills.
- Two-hour input fixture: 2,149,705 bytes, 160×90 at 1 FPS, sparse synthetic
  speech and long silent stretches. This tests duration/chunk/recovery behavior;
  its processing time does not predict a dense real two-hour VOD's speed.
- Peak temporary disk consumption was NOT MEASURED. Successful Drive-backed job
  scratch directories had already been removed when inspected after completion.
  Persisted exports and editable sources remain available through Drive.
- Verified final MP4 sizes: Short 9,175,629 bytes; connected parts 5,801,602,
  5,747,728 and 5,827,879 bytes; Longs 8,530,112 bytes; automatic Short 2,086,872
  bytes; two-hour-source Short 585,523 bytes.
- Raw job records, size/checksum responses, memory samples, CI summary, startup
  log and UI screenshot are retained locally under ignored `verification/runtime`;
  they are not published with credentials or remote file identities.

## Remaining limitations and reproduction

- **Live publication — acceptance limitation.** This run intentionally did not
  upload to YouTube or queue a release. To verify, approve a controlled render,
  choose the intended channel and visibility, then perform an explicitly
  authorized upload. Public/scheduled visibility also depends on channel/API
  project permissions; only remote status can establish actual release.
- **Live retention — acceptance limitation.** Dry-run and policy tests cannot
  establish real trash permissions. Verification requires an explicitly disposable
  owned package which is public, past grace, unprotected and unreferenced, followed
  by inspection of its verified trash status. Retention remains disabled.
- **4 GiB GPU/whole-host RAM — measurement limitation.** Run the same controlled
  harness on physical 4 GiB hardware and collect Windows/WSL counters to certify
  that target. Existing Docker limits do not prove model fit on every machine.
- **Browser upload — UI verification limitation.** The automation file chooser
  stalled and its continuation expired. Local HTTP upload and real processing
  succeeded repeatedly; the native chooser was not reattempted. Manually choose
  an owned local file in Create to verify the remaining browser-specific path.
- **AI quality — operator review required.** Generate hooks/metadata to inspect
  potentially weak or incomplete candidates. Technical/schema validation does
  not establish factuality or entertainment value. Review text before approval.
- **Video quality — coverage limitation.** Synthetic clips and automated decode,
  black/silence/clipping and endpoint checks do not certify every real VOD's
  framing, lip synchronization or narrative quality. Review a representative VOD.

## Running application

- URL: <http://127.0.0.1:5175/factory.html>.
- Services: controller, local worker, web proxy/UI and Ollama healthy; Publisher
  and Analytics loops running. Existing Drive/YouTube/Analytics connections passed
  read-only readiness probes. Public/automatic publication remains disabled.
- Start: `./scripts/start-factory.ps1 -TimeoutSeconds 600`.
- Repeated startup reused unchanged images, backed up SQLite, reused assets and
  reached OVERALL READY. This is service readiness, separate from the external
  acceptance limitations above. The application is left running.
