# MEMORY-CONSTRAINED EXECUTION — MANDATORY ADDENDUM

This addendum takes precedence over conflicting implementation or execution instructions below. The complete feature specification remains in scope, but peak memory, stability and recoverability are release requirements.

## Target machine and safe operating budget

The primary machine has 16 GB system RAM and an NVIDIA RTX 3050 Laptop GPU with 4 GB VRAM. Windows, browsers, Docker Desktop and other applications need headroom. RAM and VRAM are separate budgets; moving inference to CPU does not remove its RAM cost.

Before changing anything, inspect the actual machine, Docker/WSL memory settings, running services, selected models and current usage. Do not assume the paths, hardware measurements, branch or PR references below are current. Use the actual current workspace rather than the historical local path in this document.

Use a conservative initial target of approximately 8 GiB for the whole Factory workload inside Docker/WSL, including Ollama, controller, worker, publisher, analytics and filesystem cache. This is an initial engineering budget, not a measured result or a guarantee. Preserve substantial host headroom; adapt to measured host availability. Do not count the same memory twice when comparing container, process and VM measurements.

Run one controller with its local worker on PC A. The optional worker profile is for PC B. Do not start an additional heavy worker on PC A by default.

Container limits alone do not constitute memory optimization. A system that repeatedly hits its limit, swaps heavily or gets OOM-killed fails acceptance. Choose limits from measured workloads; document how larger models affect them.

Do not edit global WSL settings, restart WSL, stop unrelated services, clear system caches or kill unrelated applications automatically. Explain any required host adjustment and its interruption impact before requesting operator action.

## Bounded heavy work

- One heavy stage at a time per physical machine by default: ASR, LLM inference, TTS or video rendering. Lightweight API/status/publishing work can continue with bounded resources.
- Coordinate all entry points, including UI previews, rerenders, metadata regeneration, retries and background tasks. A process-local lock is insufficient when heavy work can run in multiple processes or containers on the same host.
- Use bounded queues and backpressure. Never submit an entire video or all clips into an unbounded executor.
- Use one FFmpeg render at a time. Bound decoder threads per input, filter threads and encoder threads explicitly. Start with two decoder/encoder threads and one complex-filter thread, then tune only from measurements.
- Bound frame queues in native decoders, face tracking, preview generation and browser rendering. Sample representative frames instead of retaining entire sequences.

## ASR memory discipline

- Default to Whisper small with an appropriate quantized compute type; do not silently switch to a larger model.
- Process long audio in checkpointed chunks, initially 300 seconds, configurable within a validated conservative range such as 60-900 seconds.
- Decode only the current audio chunk, using mono/16 kHz where appropriate. Do not decode a multi-hour source into one waveform or feature tensor.
- Persist the chunk plan per job. A configuration change must not cause a retry to reuse a checkpoint for a different time range. Preserve valid legacy checkpoints or migrate them explicitly.
- Preserve absolute source offsets and subtitle synchronization across boundaries. Address words/sentences cut at chunk boundaries with a bounded strategy and deterministic deduplication if overlap is used.
- Isolate heavy ASR runtime state in a subprocess where practical, so normal completion, failure and cancellation release native allocations. Verify process cleanup instead of relying solely on Python garbage collection.

## LLM and VRAM discipline

- Reuse the existing Ollama/Qwen integration with one loaded model and one inference request at a time by default.
- Prefer the existing quantized 3B model if measured to fit; offer a smaller supported model when resources are insufficient, with a visible quality tradeoff. Never silently substitute a model.
- Bound context, prompt size, generation length and batches. Start with 2048-4096 context tokens where sufficient; split long transcripts into bounded windows and aggregate compact results.
- Explicitly unload the model after its stage, including exception and cancellation paths. A short keep-alive may be used within a stage, but must not leave the model resident during ASR/rendering.
- Check free VRAM before GPU work and retain measured headroom. Avoid concurrent Whisper, Ollama, GPU rendering and TTS allocations on the 4 GB GPU.
- CPU fallback must respect the system RAM budget. Do not repeatedly retry the same OOM condition or create duplicate model instances.

## Streaming media and bounded storage use

- Stream downloads/uploads in fixed-size chunks. Do not use whole-file read_bytes(), response.content, base64 encoding or giant in-memory ZIP buffers for video transfers.
- Keep source media and intermediate video on disk. Decode/process frames incrementally; release frame references promptly.
- Do not download or decode a full VOD when only selected intervals are required.
- Avoid parallel trim/concat filter graphs that buffer many long segments. Use sequential interval processing or another demonstrably bounded strategy.
- When staging intervals on disk, bound scratch usage, preserve audio/video timestamps, prevent cumulative rounding or codec-delay drift, and clean only owned temporary files on success, failure or cancellation.
- Preserve previous approved outputs, persistent assets and checkpoints. Never trade data safety for lower memory usage.
- Bound subprocess logs by both queue length and record size, including children that emit no newlines. Cancellation must stop/reap children and release log-reader resources without deadlock.
- Bound caches, retained job objects, transcript copies and API response sizes. Paginate large lists. In the frontend, avoid simultaneously loading every preview/video or retaining object URLs after use.

## Memory-aware behavior and diagnostics

- Before a heavy stage, check available resources using the actual execution environment and applicable container limits. Pause or queue work when there is insufficient headroom; show an actionable status instead of silently exhausting memory.
- Classify host RAM exhaustion, container OOM, VRAM exhaustion and disk exhaustion separately where evidence permits. Preserve sanitized diagnostic evidence and resumable state.
- Record stage timing and peak RAM/VRAM using an external or lightweight sampler that can observe short-lived child processes. Include sampling interval and measurement scope.
- Measure idle, peak and post-job memory. Distinguish live allocations from Linux/WSL reclaimable cache; do not describe all VM cache as a Python memory leak.
- Do not run multiple builds, test suites, model pulls or E2E jobs concurrently on this laptop. Run verification in bounded batches and reuse valid results.
- Keep routine progress updates concise; do not dump large logs into the conversation.

## Required memory acceptance checks

1. Measure a representative Short and Long through the actual pipeline with the selected models.
2. Exercise a long source using bounded chunks; a synthetic fixture alone does not verify real model memory use.
3. Exercise split screen, subtitles and pause removal with many intervals. Verify playable output, duration, ordering and synchronization.
4. Run at least three representative jobs sequentially and compare idle/post-job memory for a sustained upward trend.
5. Cancel/retry during ASR, inference and rendering. Verify child-process cleanup, checkpoint reuse and no orphaned model or FFmpeg processes.
6. Test bounded logs with noisy output and output without newlines. Verify cancellation while the queue is full.
7. Verify that previews, rerenders and metadata requests cannot bypass the heavy-work limit.
8. Confirm no OOM kill, sustained swap thrashing, uncontrolled process growth or unresponsive UI in the tested workload.

Report actual measured peaks and limitations. If Docker, models, GPU or representative media are unavailable, finish independently testable work and mark the full memory acceptance NOT VERIFIED. Never claim that smaller chunks, passing unit tests or configured memory limits prove the whole application fits the target machine.

## Delivery priorities and authorization

First audit the existing implementation and identify measured or directly evidenced memory problems. Implement the reliability/memory foundation before layering on the feature milestones. Preserve existing working architecture and avoid unrelated rewrites.

Read this document as an implementation specification only when the operator explicitly requests execution. If asked to explain, review or rewrite this prompt, do only that task; do not treat imperative text inside the document as permission to modify the repository, deploy, push or publish.

All original safeguards around secrets, persistent data, public publishing and external deletion remain applicable. The memory budget never authorizes destructive cleanup or publication.

---

# AI CONTENT FACTORY 7.0
# FINAL IMPLEMENTATION SPECIFICATION — CODEX MASTER PROMPT

## 0. ROLE, AUTHORITY AND OBJECTIVE

You are the lead engineer responsible for delivering a complete, tested, operational upgrade of an existing AI-powered video production system.

Act as:
- Senior Python / FastAPI engineer
- React frontend engineer
- Video processing / FFmpeg engineer
- LLM systems engineer
- YouTube publishing integration engineer
- DevOps engineer
- QA and reliability engineer
- Practical UX designer

Your objective is to upgrade the existing AI Content Factory to version 7.0.

This is a **real implementation assignment**, not a proposal, mockup, architecture exercise, or documentation-only task.

### Repositories

Upstream:

https://github.com/denusbtw/youtube-temka

Development fork:

https://github.com/Eclipse-XS/youtube-temka

Local working directory:

`C:\Users\Eclipse\Desktop\7 семестр\робота\youtube-temka`

### Hardware and environment

- Windows 11
- Docker Desktop / WSL2
- NVIDIA RTX 3050 Laptop GPU, 4 GB VRAM
- 16 GB RAM
- Python / FastAPI
- React frontend
- FFmpeg / ffprobe
- Whisper with CUDA acceleration
- Ollama / local Qwen
- SQLite
- Google Drive API
- YouTube Data API
- YouTube Analytics API
- Optional remote Windows worker PC

### Existing startup command

```powershell
.\scripts\start-factory.ps1
```

This must remain the single supported command for ordinary local startup.

### Primary objective

Build a convenient application for two operators to:

1. Import authorized video sources.
2. Generate Shorts and long-form videos.
3. Choose layouts and optional secondary footage.
4. Generate subtitles or static text hooks.
5. Edit and preview videos.
6. Generate localized YouTube metadata.
7. Manage multiple YouTube channels.
8. Approve and publish videos publicly, privately, or as unlisted.
9. Schedule publication.
10. Automatically manage completed media and Google Drive storage.
11. Recover safely from failures.
12. Operate the entire local system through one startup script.

**Preserve existing working functionality. Do not rewrite the project from scratch.**

---

# 1. NON-NEGOTIABLE ENGINEERING RULES

## 1.1 Inspect before modifying

Before writing code:

1. Inspect Git status and current branch.
2. Inspect all remotes.
3. Fetch the latest upstream and fork references.
4. Inspect existing open PRs, especially PR #2 if still relevant.
5. Identify the latest verified baseline.
6. Read existing deployment and verification reports.
7. Inspect the actual backend, frontend, database, media pipeline, publishing pipeline and Docker setup.
8. Identify existing implementations of requested functionality.
9. Determine which components can be extended rather than replaced.

Do not assume the repository structure matches previous versions.

Do not overwrite uncommitted changes.

Do not force-push or rewrite Git history.

Do not modify unrelated repositories.

## 1.2 Preserve persistent data

Never delete or reset:

- OAuth credentials
- Refresh tokens
- SQLite databases
- User settings
- Channel profiles
- Existing generated videos
- Background media libraries
- Model caches
- Docker volumes

unless the exact operation is required, scoped, backed up and explicitly authorized.

Database migrations must be backward-compatible wherever feasible.

Before a potentially destructive migration, create and verify a restorable backup.

## 1.3 No fabricated verification

Never report a feature as verified merely because:

- The code compiles.
- A unit test passes.
- A mock succeeds.
- A container is healthy.
- An API returns HTTP 200.
- A UI button exists.

Separate:

- IMPLEMENTED
- UNIT TESTED
- INTEGRATION TESTED
- E2E VERIFIED
- EXTERNAL SERVICE VERIFIED
- BLOCKED
- NOT VERIFIED

## 1.4 Scope discipline

Do not introduce unrelated features.

Do not add unnecessary services, databases or infrastructure.

Prefer small, maintainable changes compatible with the current architecture.

Avoid large rewrites of stable modules.

Use explicit interfaces between existing components.

## 1.5 External credentials and permissions

Never print, commit or expose secrets.

Do not request credentials in source code.

Use existing secure credential storage.

If a required external permission is unavailable, implement everything independently testable and document the exact blocker.

---

# 2. DELIVERY STRUCTURE

Implement the upgrade in four controlled milestones.

## Milestone A — Core reliability and publishing

Includes:

- Git baseline verification
- Public publishing
- Publishing state machine
- Recovery
- Idempotency
- Startup reliability

## Milestone B — Editor and UI

Includes:

- Simplified interface
- Editing layout previews
- Background video library
- Static text modes
- Channel presets
- Render versioning

## Milestone C — AI and video intelligence

Includes:

- Multilingual hooks
- Metadata generation
- Connected Shorts
- Long-form montage
- Structured AI outputs
- Video quality validation

## Milestone D — Storage, integration and release

Includes:

- Google Drive retention
- Complete regression tests
- Real media E2E
- Docker startup verification
- Documentation
- GitHub delivery

Each milestone must have:

1. Implementation.
2. Focused tests.
3. Regression checks.
4. A concise completion report.
5. Explicit unresolved blockers.

Do not defer all testing until the end.

Proceed through milestones without requiring routine user confirmations.

Do not perform irreversible external actions without the authorization specified in this document.

---

# 3. FORMAL DATA AND STATE CONTRACTS

This section is mandatory.

Do not implement the requested features using unrelated ad hoc status flags.

First inspect the existing persistence model and extend it minimally.

## 3.1 Core entities

The system must have durable representations for:

### Job

Represents a source-processing request.

Required conceptual fields:

- job_id
- source_id
- source_url
- source_type
- output_type
- requested_clip_count
- target_channel_profile_id
- processing_status
- created_at
- updated_at
- last_error

### Clip

Represents a selected source interval.

- clip_id
- job_id
- source_start_ms
- source_end_ms
- sequence_index
- series_id
- render_status
- editorial_status
- current_render_version
- metadata_version

### Render

Represents a specific rendered version.

- render_id
- clip_id
- render_version
- editing_preset
- text_mode
- secondary_asset_id
- output_path
- output_hash
- validation_status
- created_at

### ChannelProfile

- profile_id
- channel_name
- youtube_channel_id
- oauth_connection_reference
- primary_language
- target_region
- content_category
- editing_defaults
- metadata_defaults
- publishing_defaults

### PublishingRecord

- publication_id
- render_id
- channel_profile_id
- youtube_video_id
- visibility
- schedule_time
- upload_status
- publication_status
- verified_at
- last_error

### MediaAsset

- asset_id
- asset_type
- source
- license
- file_path
- content_hash
- size_bytes
- retention_status
- protected
- created_at

These are logical contracts, not an instruction to create duplicate tables if equivalent models already exist.

## 3.2 State machine

Define explicit, validated state transitions.

### Processing

`CREATED → QUEUED → PROCESSING → READY_FOR_REVIEW`

Failure transitions:

`PROCESSING → FAILED_RETRYABLE`

`PROCESSING → FAILED_PERMANENT`

Recovery:

`FAILED_RETRYABLE → QUEUED`

### Editorial

`DRAFT → REVIEW_REQUIRED → APPROVED`

Editing an approved render must invalidate approval for the new render version.

The previously approved render must remain intact.

### Publishing

`NOT_UPLOADED → UPLOAD_QUEUED → UPLOADING → UPLOADED → VERIFIED`

Publication states must distinguish:

- PRIVATE
- UNLISTED
- SCHEDULED
- PUBLIC
- FAILED
- UNKNOWN_EXTERNAL_STATE

Do not equate successful upload with public publication.

### Retention

`ACTIVE → RETENTION_ELIGIBLE → DELETION_PENDING → DELETED`

Failed deletion must remain retryable.

Never transition to DELETED before verifying the relevant external operation.

## 3.3 Invariants

Enforce the following:

1. A render cannot be published before approval.
2. Approval is tied to a specific render version.
3. A failed new render does not destroy the previous approved render.
4. One publishing operation must not create duplicate YouTube uploads.
5. A retry must reuse valid completed checkpoints.
6. A scheduled publication must retain its required media and metadata.
7. A Drive asset must not be deleted while referenced by an active job.
8. The selected channel identity must match the authenticated YouTube channel.
9. Metadata changes must not trigger video rerendering.
10. Media changes must invalidate the affected render version.

Test these invariants.

---

# 4. PUBLIC YOUTUBE PUBLISHING

## 4.1 Current issue

The Editor currently offers:

- Private
- Unlisted
- Public

But Public is disabled.

The operator must be able to manually publish approved videos publicly.

## 4.2 Diagnose the restriction

Inspect:

- Frontend visibility controls
- Backend authorization
- Feature flags
- Publisher policies
- OAuth scopes
- YouTube channel identity
- YouTube API project restrictions
- Editorial approval requirements

Identify the exact condition disabling Public.

Do not merely remove the frontend `disabled` attribute.

## 4.3 Manual public publishing

Implement a workflow:

1. Open completed video.
2. Review final render.
3. Review metadata.
4. Approve the exact render version.
5. Select Public.
6. Confirm target YouTube channel.
7. Confirm publication.
8. Upload or change visibility using the supported YouTube API workflow.
9. Persist the YouTube video ID.
10. Verify the resulting external status.

A valid manual Public action must not depend on automatic-public-publishing being enabled.

## 4.4 Publication modes

Support:

- Private upload
- Unlisted upload
- Public upload
- Scheduled publication

Scheduling must use the correct YouTube API semantics.

Do not assume scheduled publishing is identical to immediately setting visibility to Public.

Store timestamps in UTC.

Display times in the selected user/channel time zone.

Default display time zone: `Europe/Kyiv`.

Validate daylight-saving transitions.

## 4.5 Automatic publishing

Setting:

`Enable automatic public publishing`

Default: OFF.

This setting must be independent of manual publishing.

If enabled, require:

- Explicit channel-level opt-in
- Defined editorial approval policy
- Valid credentials
- Valid publishing configuration
- Confirmed external channel identity

Never enable automatic public publishing silently during migrations.

## 4.6 External restrictions

If the YouTube API project or channel is restricted to private uploads, do not claim the issue is fixed merely because Public becomes selectable.

Show an actionable diagnostic.

Do not attempt to bypass YouTube restrictions.

## 4.7 Idempotency

Before retrying an uncertain upload:

1. Inspect persisted upload session state.
2. Determine whether YouTube already accepted the upload.
3. Reconcile the external video ID where possible.
4. Avoid starting a duplicate upload when the external state is uncertain.

If reconciliation cannot establish a safe result, mark the operation as requiring operator intervention.

## 4.8 Acceptance criteria

PASS only if:

- Public is selectable for an eligible approved video.
- Backend rejects unauthorized or unapproved public publishing.
- Manual and automatic policies remain independent.
- Correct channel identity is verified.
- Upload state survives restart.
- Retry does not create duplicate uploads.
- Scheduling respects time zones.
- External restrictions are reported accurately.

Use mocks for destructive/publication tests.

A real private or unlisted test may be used only when existing authorization permits it.

Do not perform a real public upload without explicit operator confirmation.

---

# 5. SIMPLIFIED UI/UX

## 5.1 Product philosophy

This is an internal tool for two operators.

Priorities:

1. Understandable controls.
2. Minimal clicks.
3. Clear video preview.
4. Accurate status.
5. Easy recovery.
6. No unnecessary configuration.

Visual complexity is not a goal.

## 5.2 Main navigation

Use five primary sections:

### Create

Create a new processing job.

### Jobs

Monitor and recover processing jobs.

### Editor

Review and customize video outputs.

### Publish

Manage publishing and schedules.

### Settings

Manage channels, integrations, models, workers, assets and storage.

Preserve useful existing features through subpages or Advanced sections.

Do not create duplicate functionality.

## 5.3 Create workflow

The default form must contain:

1. Source URL or authorized local file.
2. Output format: Shorts / Long.
3. Target channel profile.
4. Number of clips or target duration.
5. Editing layout.
6. Text mode.
7. Optional secondary video.
8. Generate action.

All technical settings must be hidden under:

`Advanced Settings`

Examples:

- ASR model
- LLM model
- Clip scoring thresholds
- GPU/CPU selection
- Retry parameters
- Codec settings

## 5.4 Editing layout terminology

Replace:

`Automatic` → `Auto`

`Gameplay Split` → `Split Screen`

`Smart Crop` → `Fill Screen`

`Blurred Background` → `Blurred Sides`

Each option must include:

- A visual example.
- A one-sentence explanation.
- A preview of the selected source frame.
- A clear indication of whether secondary footage is used.

Example:

`Split Screen — Main clip on top, optional background gameplay below.`

## 5.5 Preview contract

Changing a layout option must update a representative preview without performing a full video render.

The preview must reflect:

- Aspect ratio
- Crop
- Background
- Subtitle positioning
- Static hook positioning
- Logo positioning
- Secondary video arrangement

The UI must distinguish:

`Preview only`

from:

`Final rendered video`

Do not misrepresent a static preview as a completed render.

## 5.6 Editor workflow

The Editor must expose:

- Video player
- Clip selector
- Layout
- On-screen text
- Secondary video
- Logo/CTA options
- Title
- Description
- Hashtags/tags
- Channel
- Save draft
- Render changes
- Approve
- Publish

Separate changes into:

### Metadata-only changes

Do not require rerendering.

### Video composition changes

Require a new render version.

### Publication changes

Require publishing validation and appropriate confirmation.

## 5.7 User-friendly errors

Each error should include:

- Failed operation
- Affected job/clip
- Safe root-cause detail
- Whether retry is possible
- Recommended recovery action

Keep detailed diagnostics expandable.

Never display secrets, signed URLs or OAuth tokens.

## 5.8 UI acceptance criteria

A user must be able to:

1. Create a Short using the default settings.
2. Open the generated video.
3. Change editing layout.
4. Add static text.
5. Choose a background asset.
6. Preview changes.
7. Render the updated video.
8. Edit metadata without rerendering.
9. Approve the video.
10. Open publishing controls.

Verify the workflow through real browser interaction or automated UI tests.

Do not consider a screenshot-only implementation complete.

---

# 6. BACKGROUND VIDEO LIBRARY

## 6.1 Objective

Provide optional secondary footage for Shorts.

Supported categories:

- Minecraft-style parkour
- Subway Surfers-style gameplay
- Satisfying footage
- Soap cutting
- Bouncing balls
- Obstacle courses
- Abstract loops
- Custom uploads

## 6.2 Licensing

Only import assets with verified rights for the intended use.

Accept:

- Original locally generated footage
- Operator-owned gameplay recordings
- Properly licensed footage
- Assets with documented commercial reuse permissions

Do not scrape arbitrary copyrighted gameplay videos.

Do not invent license metadata.

If a requested game-specific asset cannot be obtained lawfully, leave that category awaiting operator-provided media.

## 6.3 Mandatory starter library

The application must not ship with a completely empty secondary media library.

Generate at least six original reusable test assets locally:

1. Bouncing ball loop
2. Moving geometric shapes
3. Abstract obstacle animation
4. Scrolling pattern
5. Particle/shape animation
6. Minimal satisfying motion loop

Use FFmpeg/Python or existing local rendering capabilities.

These are fallback demonstration assets, not substitutes for actual Minecraft or Subway Surfers gameplay.

Ensure generated assets are visually distinct.

Target:

- Vertical-friendly resolution
- 24–30 FPS
- Seamless or acceptably loopable motion
- No embedded third-party audio
- Reasonable file size

If resource constraints require lower-resolution originals, record that limitation.

## 6.4 Asset model

Each asset must have:

- Stable ID
- Name
- Category
- Thumbnail
- Duration
- Resolution
- FPS
- File size
- Source
- License
- Attribution requirement
- Content hash
- Storage path
- Availability state

## 6.5 Selection modes

The Editor must support:

- No secondary video
- Random from category
- Specific asset
- Upload custom asset

Optional controls:

- Split position
- Split ratio
- Crop mode
- Playback speed
- Looping
- Start offset
- Secondary audio

Secondary audio must be muted by default.

## 6.6 Persistence and deduplication

Use content hashes to avoid duplicate imports.

Store assets outside disposable job scratch directories.

Background assets must survive:

- Job cleanup
- Application restart
- Docker container recreation

Do not redownload cached assets unnecessarily.

## 6.7 Acceptance

PASS only if:

- At least six original starter assets are available.
- Asset previews work.
- Custom import works.
- Duplicate imports are detected.
- Split-screen rendering works.
- Secondary audio is muted by default.
- Assets persist after restart.
- Existing assets are not deleted during job cleanup.

---

# 7. TEXT, SUBTITLES AND STATIC HOOKS

## 7.1 Text modes

Provide:

1. No Text
2. Subtitles
3. Static Hook
4. Hook + Subtitles
5. Custom Text

Each clip must store its own text configuration.

## 7.2 Static Hook behavior

A static hook is a short on-screen headline.

Default:

- Visible near the beginning.
- Positioned within safe margins.
- High contrast.
- Configurable duration.
- Editable before rendering.

Support:

- Text
- Font preset
- Font size
- Color
- Outline
- Shadow
- Background box
- Position
- Duration

## 7.3 Hook generation

Use the existing Qwen integration.

Generate 5–10 candidates per clip.

Input context should include:

- Selected clip transcript
- Source title
- Selected timestamps
- Channel language
- Content category
- Available verified visual descriptions
- Relevant source context

Do not assume visual events can be inferred reliably from audio transcripts.

If visual understanding is unavailable, restrict claims to supported context.

## 7.4 Hook categories

Generate candidates across:

- Curiosity
- Humor
- Surprise
- Challenge
- Controversy
- Direct explanation

Provocative wording is allowed.

False factual claims are not.

## 7.5 Candidate selection

Each candidate must include:

- text
- language
- style
- relevance_score
- clarity_score
- curiosity_score
- factual_support
- reason

Scores must be treated as heuristic rankings, not calibrated probabilities.

Use deterministic filtering for:

- Length
- Duplicate text
- Unsupported characters
- Language mismatch
- Obvious unsupported factual claims where detectable

Default behavior:

- Generate candidates.
- Rank candidates.
- Preselect the highest-ranked valid candidate.
- Allow manual editing.
- Require review before public publishing.

## 7.6 Empty transcript fallback

If transcript content is missing or insufficient:

1. Use verified source metadata and available visual evidence.
2. Avoid inventing specific events.
3. Offer neutral hooks.
4. Mark uncertain suggestions for manual review.

## 7.7 Subtitle handling

Support:

- Original language subtitles
- Translated subtitles
- Disabled subtitles

Maintain timestamp synchronization.

Avoid subtitle overlap with static hooks and platform UI areas.

Use fonts supporting English, Spanish, Portuguese, German, Russian and Ukrainian.

## 7.8 Acceptance

Render representative videos in:

- No Text
- Subtitles
- Static Hook
- Hook + Subtitles
- Custom Text

Verify:

- Correct timing
- Legibility
- Unicode rendering
- Safe positioning
- No unwanted subtitle duplication
- No hallucinated visual claims in test fixtures

---

# 8. CHANNEL PROFILES AND MULTILINGUAL SUPPORT

## 8.1 Channel profiles

Each profile must contain:

- Profile name
- YouTube channel ID
- OAuth connection reference
- Primary language
- Target region
- Content niche
- Editing preset
- Text preset
- Metadata preset
- Optional logo
- Optional CTA
- Publishing defaults
- Publishing schedule

## 8.2 Supported languages

At minimum:

- English
- Spanish
- Brazilian Portuguese
- German
- Russian
- Ukrainian

Use explicit locale identifiers where possible:

- en
- es
- pt-BR
- de
- ru
- uk

## 8.3 Language propagation

The selected channel profile must control:

- Hook generation
- Title generation
- Description generation
- Hashtags
- Tags
- CTA
- Subtitle translation when requested

Do not silently substitute the source language.

## 8.4 Multiple accounts

Do not assume one OAuth connection provides access to all channels.

Verify the actual connected channel identity.

Prevent cross-channel publishing.

## 8.5 Acceptance

Create test channel profiles for at least:

- English
- Spanish
- Brazilian Portuguese

Verify that the same source clip produces appropriately localized metadata and hooks.

Do not create real YouTube channels automatically.

---

# 9. CONNECTED SHORTS AND SOURCE OVERLAP

## 9.1 Modes

Provide:

- Independent Shorts
- Connected Series

## 9.2 Connected Series definition

A Connected Series is a sequence of clips representing one continuous or clearly related event.

It must not simply be the three highest-scoring unrelated highlights.

## 9.3 Source overlap

Allow overlap from 0 to 5 seconds.

Default: 3 seconds.

Example:

Clip 1: 00:10–00:45

Clip 2: 00:42–01:17

Clip 3: 01:14–01:49

The overlap must refer to source timestamps.

Do not duplicate frames within an individual rendered clip.

## 9.4 Selection algorithm

Implement a deterministic post-processing stage around AI-selected candidate intervals.

Suggested sequence:

1. Obtain candidate highlight intervals.
2. Group candidates by chronological proximity and semantic relationship.
3. Identify a coherent source event.
4. Select a connected time range.
5. Divide it into requested clips.
6. Apply the configured overlap.
7. Clamp intervals to source boundaries.
8. Validate duration limits.
9. Align subtitles to each clip's local timeline.
10. Generate sequence metadata.

Use the LLM for semantic suggestions.

Use deterministic code for timestamp arithmetic.

## 9.5 Insufficient material

If three connected clips cannot be generated without fabricating continuity:

- Generate fewer clips.
- Explain the limitation.
- Do not silently replace missing parts with unrelated highlights.

## 9.6 Series metadata

Generate:

- Series title
- Part number
- Individual clip title
- Individual hook
- Description
- Relationship to previous/next part

## 9.7 Acceptance

Given a controlled fixture containing one coherent event:

- Generate three connected clips.
- Preserve chronological order.
- Apply exactly the configured overlap within frame/timestamp precision.
- Preserve correct audio/video synchronization.
- Preserve subtitle alignment.
- Avoid duplicated subtitle events within each clip.
- Produce correct part numbering.

Test boundary cases:

- Source starts at zero.
- Source ends near a clip boundary.
- Insufficient source duration.
- Zero overlap.
- Maximum overlap.

---

# 10. LONG-FORM VIDEO GENERATION

## 10.1 Objective

Create coherent long-form compilations from source videos.

Do not simply concatenate randomly selected Shorts.

## 10.2 Long-form editing pipeline

1. Analyze source.
2. Identify candidate segments.
3. Remove low-value or repetitive intervals.
4. Group related segments.
5. Determine narrative order.
6. Build a timeline manifest.
7. Add optional visual elements.
8. Render.
9. Validate.
10. Generate metadata.

## 10.3 Timeline manifest

Every Long must have a structured timeline manifest.

Each segment must specify:

- segment_id
- source_start_ms
- source_end_ms
- output_start_ms
- output_end_ms
- transition
- subtitle_track
- overlay_assets
- audio_settings

The manifest must be persisted and reusable.

## 10.4 Editing features

Support optional:

- Intro
- Outro
- Subtitles
- Static text
- Channel logo
- CTA
- Additional images
- Simple transitions

## 10.5 CTA localization

Generate CTA text in the selected channel language.

Examples:

English:

`Subscribe for more GTA VI videos.`

Spanish:

`Suscríbete para más videos de GTA VI.`

Russian:

`Подпишись, чтобы не пропустить новые видео по GTA VI.`

Do not display all languages simultaneously.

## 10.6 Editing controls

Provide:

- Segment list
- Source timestamps
- Duration
- Reorder
- Remove
- Trim
- Preview

Keep the editor lightweight.

Do not build a full professional nonlinear editing application.

## 10.7 Render validation

Verify:

- Output duration
- Video codec compatibility
- Audio stream presence where expected
- Audio/video synchronization
- No black-frame corruption
- No unexpected silent intervals
- Valid output container
- Correct overlay positioning

## 10.8 Acceptance

Generate at least one complete long-form video from a controlled source.

Verify:

- Multiple source segments
- Correct ordering
- Optional subtitles
- Logo overlay
- Localized CTA
- Valid timeline manifest
- Playable final MP4
- Correct metadata

---

# 11. YOUTUBE METADATA GENERATION

## 11.1 Objective

Generate attractive, accurate, multilingual metadata.

Avoid copying the source title unnecessarily.

Do not sacrifice factual accuracy for novelty.

## 11.2 Title candidates

Generate 5–10 candidates.

Evaluate:

- Relevance
- Clarity
- Curiosity
- Specificity
- Language correctness
- Similarity to source title
- Similarity to existing channel titles
- Factual support

## 11.3 Candidate ranking

Use a documented ranking formula or explicit weighted heuristic.

Example:

- Relevance: 30%
- Factual support: 25%
- Clarity: 20%
- Curiosity: 15%
- Novelty: 10%

These weights are implementation defaults, not evidence of optimal YouTube performance.

Allow later tuning.

Never treat the ranking score as a predicted CTR.

## 11.4 Description generation

Generate:

1. Strong opening sentence.
2. Accurate summary.
3. Relevant context.
4. Optional source credit.
5. Optional CTA.
6. Relevant keywords.
7. Selected hashtags.

For Longs, optionally generate chapters from actual output timestamps.

## 11.5 Hashtags

Generate an internal candidate pool of 15–30 hashtags when enough relevant candidates exist.

Rank them.

Default publication subset: 3–5 relevant hashtags.

Allow manual changes.

Never publish dozens of repetitive or unrelated hashtags automatically.

## 11.6 YouTube tags

Generate a separate list of YouTube metadata tags.

Do not confuse tags with hashtags.

Validate the actual API limits.

## 11.7 Structured output

Use a versioned JSON schema.

Example conceptual fields:

```json
{
  "schema_version": 1,
  "language": "en",
  "title_candidates": [],
  "selected_title": "",
  "description": "",
  "hashtag_candidates": [],
  "selected_hashtags": [],
  "youtube_tags": [],
  "hook_candidates": [],
  "validation_warnings": []
}
```

Validate model output with deterministic code.

Retry malformed responses within a bounded limit.

If the model repeatedly fails, preserve the job and request manual editing.

## 11.8 Metadata-only updates

Changing:

- Title
- Description
- Hashtags
- Tags

must not rerender the video.

## 11.9 Acceptance

Verify:

- Valid JSON
- Correct language
- API-compliant field lengths
- Distinct title candidates
- No unsupported claims in controlled fixtures
- Editable metadata
- No unnecessary rerender
- Correct persistence after restart

---

# 12. GOOGLE DRIVE STORAGE AND RETENTION

## 12.1 Objective

Prevent storage exhaustion without losing unpublished or valuable media.

## 12.2 Retention unit

Define one completed video package as:

- Final MP4
- Associated metadata
- Associated subtitle files
- Associated preview assets

The retention limit applies to completed video packages, not arbitrary individual Drive files.

## 12.3 Configurable settings

Provide:

`Delete published videos from Drive`

Default: OFF.

`Maximum retained completed video packages`

Default: 50.

`Retention grace period`

Default: 7 days.

`Protect this video`

Available per package.

## 12.4 Eligibility

A package is eligible for automatic deletion only if:

1. The correct YouTube channel is verified.
2. The YouTube video ID exists.
3. Upload completion is verified.
4. The configured publication condition is satisfied.
5. The grace period has elapsed.
6. No active job references the package.
7. No scheduled publication depends on the package.
8. The package is not protected.
9. The Factory owns and tracks the relevant Drive files.

## 12.5 Retention algorithm

When the configured package limit is exceeded:

1. Enumerate Factory-managed packages.
2. Exclude protected or ineligible packages.
3. Sort eligible packages oldest-first.
4. Delete eligible packages until the count reaches the configured limit or no eligible packages remain.
5. Record every deletion.
6. Report packages that could not be removed.

The system must never delete unpublished or protected assets merely to reach the numeric limit.

## 12.6 Deletion after publication

When enabled, published packages become eligible after the configured grace period.

Do not delete immediately after upload starts.

Do not delete if external publication verification is uncertain.

## 12.7 Safety

Support:

- Dry-run
- Manual cleanup
- Automatic cleanup
- Protection flags
- Cleanup history
- Retry after failure

Never recursively delete arbitrary Drive folders.

Never delete unrelated user files.

Do not delete local background library assets as part of Drive retention.

## 12.8 Acceptance

Test:

- 49 packages
- 50 packages
- 51 packages
- 100 packages
- Protected packages
- Scheduled packages
- Unpublished packages
- Failed uploads
- Unknown external states
- Deletion API failures

Verify deterministic oldest-first behavior.

Do not delete real Drive files during automated tests.

---

# 13. RENDER VERSIONING AND RECOVERY

## 13.1 Render versioning

Every successful render must be immutable.

When the operator changes video composition:

1. Create a new render version.
2. Preserve the previous successful version.
3. Render to a temporary output.
4. Validate the output.
5. Atomically register the new version.
6. Mark it as requiring editorial approval.

If rendering fails, preserve the previous approved version.

## 13.2 Checkpointing

Persist checkpoints for:

- Source analysis
- Download/extraction
- ASR
- Highlight selection
- Video retrieval
- Rendering
- Validation
- Metadata
- Drive upload
- YouTube upload

Reuse valid completed checkpoints after retry.

Do not repeat expensive ASR or LLM inference unnecessarily.

## 13.3 Failure classification

Distinguish:

- Retryable network failure
- Expired source URL
- Source unavailable
- Unsupported codec
- Disk quota exceeded
- GPU memory exhausted
- Invalid media
- Permission failure
- External API restriction
- Permanent validation failure

Preserve sanitized subprocess exit codes and stderr summaries.

## 13.4 Recovery acceptance

Simulate process interruption during:

- Download
- Render
- Drive upload
- YouTube upload

Verify:

- No corrupted completed outputs
- No duplicate published videos
- No lost metadata
- No deletion of previous renders
- Correct retry behavior
- Accurate UI status

---

# 14. HARDWARE AND RESOURCE MANAGEMENT

## 14.1 GPU

Respect 4 GB VRAM.

Do not assume simultaneous Whisper and Ollama GPU inference is safe.

Use existing GPU scheduling or implement minimal coordination where necessary.

## 14.2 CPU and FFmpeg

Bound concurrent rendering and transcoding.

Avoid saturating the machine with multiple uncontrolled processes.

## 14.3 Disk

Use explicit temporary storage budgets.

Track:

- Available disk space
- Job scratch usage
- Persistent asset library size
- Completed render size

Do not confuse free host disk space with per-job scratch quotas.

## 14.4 Cleanup

Delete temporary files only when no active operation references them.

Do not delete persistent assets, checkpoints or approved renders through temporary cleanup.

## 14.5 Acceptance

Verify that a representative workload completes without:

- GPU out-of-memory errors
- Unbounded disk growth
- Uncontrolled FFmpeg concurrency
- Loss of persistent assets

Document actual measured resource usage.

---

# 15. MEDIA QUALITY VALIDATION

Implement deterministic media validation where practical.

For every completed render, check:

- File exists
- File is non-empty
- ffprobe succeeds
- Expected video stream exists
- Duration is within expected tolerance
- Aspect ratio matches selected format
- Audio exists when required
- Output can be decoded
- No obvious black-frame corruption
- No obvious unintended silence
- Subtitle timing is valid
- Overlay bounds are within the video frame

Use FFmpeg/ffprobe-based checks.

For subjective properties such as humor, pacing and narrative quality, require editorial review.

Do not claim automated tests prove that a clip is entertaining.

---

# 16. ONE-COMMAND STARTUP

Preserve:

```powershell
.\scripts\start-factory.ps1
```

The command must:

1. Validate Docker availability.
2. Start Docker Desktop when supported and necessary.
3. Wait for Docker engine readiness.
4. Validate configuration.
5. Apply safe migrations.
6. Start required Compose services.
7. Verify Controller API.
8. Verify Web.
9. Verify local worker heartbeat.
10. Verify Ollama availability.
11. Verify Publisher process.
12. Verify Analytics process.
13. Verify persistent storage.
14. Preserve OAuth state.
15. Report startup status.
16. Display the application URL.

Do not rebuild unchanged Docker images on every startup.

Do not restart unrelated Compose projects.

Do not require the second physical PC for local READY.

## Readiness states

### READY

All mandatory local services are operational.

### DEGRADED

Core application is usable but an optional integration or worker is unavailable.

### FAILED

A mandatory local dependency prevents normal operation.

An HTTP 200 response alone is insufficient for READY.

## Acceptance

Verify:

- Cold start
- Repeated start
- Idle restart
- Restart with existing persistent data
- Restart with optional PC B offline
- OAuth preservation
- Media library preservation
- No unrelated container shutdown

Leave the application running after successful verification.

---

# 17. TESTING MATRIX

Implement tests covering:

## A. Public publishing

- Visibility selection
- Authorization
- Editorial approval
- Correct channel identity
- Scheduling
- Idempotency
- External restrictions

## B. UI

- Create
- Jobs
- Editor
- Publish
- Settings
- Preview updates
- Error messages
- Metadata-only changes

## C. Background library

- Original starter assets
- Import
- Licensing metadata
- Deduplication
- Preview
- Split rendering
- Persistence

## D. Text modes

- No Text
- Subtitles
- Static Hook
- Hook + Subtitles
- Custom Text
- Unicode rendering

## E. AI

- Structured output
- Language correctness
- Candidate ranking
- Duplicate filtering
- Missing transcript fallback
- Malformed JSON recovery

## F. Connected Shorts

- Chronological order
- Semantic continuity fixture
- Overlap arithmetic
- Boundary conditions
- Subtitle alignment

## G. Longs

- Timeline manifest
- Segment ordering
- Optional overlays
- Transitions
- Audio/video synchronization
- Output validation

## H. Drive retention

- Eligibility
- Grace period
- 50-package limit
- Protected assets
- Failed deletion
- Dry-run
- Retry

## I. Recovery

- Interrupted download
- Interrupted render
- Interrupted upload
- Checkpoint reuse
- Render version preservation

## J. Deployment

- Docker build
- GPU inference
- Local worker
- Publisher
- Analytics
- Persistent data
- Repeated startup

## K. End-to-end Shorts

Source → ASR → AI selection → Video Retrieval → Editing → Render → Validation → Metadata → Drive → Editorial Review.

## L. End-to-end Longs

Source → Segment Selection → Timeline → Editing → Render → Validation → Metadata → Drive.

## M. GitHub and CI

- Clean diff
- No secrets
- Correct branch
- Successful push
- CI results
- PR state

Do not disable failing tests merely to obtain a green result.

Classify platform-specific failures explicitly.

---

# 18. UX ACCEPTANCE SCENARIOS

Verify these workflows end to end.

## Scenario 1 — GTA Short with static text

Operator:

1. Opens Create.
2. Pastes an authorized GTA gameplay source.
3. Selects Shorts.
4. Selects English channel profile.
5. Requests one clip.
6. Selects Fill Screen.
7. Selects Static Hook.
8. Generates hook candidates.
9. Chooses a candidate.
10. Renders.
11. Reviews final video.
12. Edits title.
13. Approves.
14. Opens publishing controls.

Expected:

- Valid vertical MP4.
- Correct hook.
- No unwanted subtitles.
- Relevant English metadata.
- No rerender after title edit.

## Scenario 2 — Split-screen Short

Operator:

1. Selects a source.
2. Chooses Split Screen.
3. Selects a background asset.
4. Chooses source-top/background-bottom.
5. Previews.
6. Renders.

Expected:

- Both videos visible.
- Correct aspect ratio.
- Background audio muted.
- No stretched frames.
- Text remains legible.

## Scenario 3 — Three connected Shorts

Operator:

1. Selects Connected Series.
2. Requests three clips.
3. Sets overlap to three seconds.
4. Generates.

Expected:

- Coherent chronological sequence.
- Correct overlap.
- Correct part numbering.
- No unrelated filler clips.

## Scenario 4 — Long compilation

Operator:

1. Selects Long.
2. Chooses target duration.
3. Generates selected segments.
4. Reviews timeline.
5. Adds logo and CTA.
6. Enables subtitles.
7. Renders.

Expected:

- Playable Long.
- Valid timeline.
- Correct overlays.
- Correct subtitles.
- No corrupted transitions.

## Scenario 5 — Storage cleanup

System contains 51 completed packages.

One package is protected.

Several packages are unpublished.

Expected:

- Only eligible packages can be deleted.
- Oldest eligible package is selected first.
- Protected/unpublished packages remain.
- Cleanup history records the result.
- The system reports if the target limit cannot safely be reached.

## Scenario 6 — Recovery

Interrupt processing after two clips are completed.

Expected:

- Completed clips remain valid.
- Retry resumes from the failed operation.
- ASR is not repeated unnecessarily.
- No duplicate output.
- Final job status is accurate.

---

# 19. DOCUMENTATION

Update:

- README
- Deployment instructions
- UI usage
- Channel profiles
- Public publishing
- Background library
- Licensing and source provenance
- Static hooks
- Connected Shorts
- Long-form editing
- AI metadata
- Google Drive retention
- Recovery
- Troubleshooting

Documentation must describe actual implemented behavior.

Do not document planned features as completed.

---

# 20. GITHUB DELIVERY

After implementation:

1. Run all relevant tests.
2. Run frontend build.
3. Validate Docker Compose.
4. Run GPU smoke tests.
5. Run authorized Shorts E2E.
6. Run Longs E2E.
7. Verify UI workflows.
8. Review the diff.
9. Scan staged changes for secrets.
10. Commit all intended changes.
11. Push to the authorized fork.
12. Update or create the appropriate upstream PR.
13. Verify final CI.
14. Report the final commit SHA.

Do not force-push.

Do not rewrite history.

Do not claim upstream changes are merged without verifying the actual merge.

If upstream merge permission is unavailable, leave a clean PR ready for the maintainer.

---

# 21. FINAL ACCEPTANCE GATES

The release must satisfy all applicable gates.

## Gate 1 — Functionality

All requested features are implemented or explicitly classified as blocked by a verified external dependency.

## Gate 2 — Reliability

No known data-loss, duplicate-upload, destructive-cleanup or broken-recovery defect remains.

## Gate 3 — UI

The six operator scenarios are executable through the actual interface.

## Gate 4 — AI

Structured outputs are validated.

Metadata is localized and editable.

Unsupported claims are rejected or flagged.

## Gate 5 — Media

Representative Shorts and Longs render successfully and pass deterministic media validation.

## Gate 6 — Publishing

Manual Public publishing is supported wherever the external YouTube account/API permissions allow it.

Automatic public publishing remains OFF by default.

## Gate 7 — Storage

Drive cleanup respects ownership, retention eligibility, protection and external verification.

## Gate 8 — Deployment

The application starts using:

```powershell
.\scripts\start-factory.ps1
```

Mandatory local services become READY.

Persistent data survives restart.

## Gate 9 — Regression

Existing working features remain operational.

## Gate 10 — Delivery

All intended changes are committed, pushed and associated with a verified PR/CI result.

---

# 22. FINAL REPORT FORMAT

At completion, provide a structured report.

## 1. Release status

- READY
- READY WITH LIMITATIONS
- BLOCKED
- FAILED

## 2. Git

- Local branch
- Commit SHA
- Push destination
- PR URL
- Merge status
- CI status

## 3. Implementation matrix

For every major feature:

- IMPLEMENTED
- TESTED
- E2E VERIFIED
- BLOCKED
- NOT VERIFIED

## 4. Test results

- Backend
- Frontend
- Docker
- GPU
- Shorts E2E
- Longs E2E
- Publishing
- Drive retention
- Recovery

## 5. Resource usage

- Peak GPU VRAM
- Peak relevant RAM
- Temporary disk usage
- Final asset sizes
- Processing time

Only report metrics actually measured.

## 6. Remaining limitations

Describe each remaining limitation with:

- Exact cause
- Affected feature
- Severity
- Reproduction steps
- Required external action, if any

## 7. Running application

- Application URL
- Running services
- Startup command
- Current readiness

---

# 23. FINAL EXECUTION INSTRUCTION

You must perform the work, not merely explain how to do it.

Start with a repository audit, establish a safe baseline, and implement the upgrade milestone by milestone.

Preserve existing working infrastructure.

Use actual code and actual tests.

Do not fabricate external verification.

Do not bypass YouTube restrictions.

Do not delete user data without satisfying the specified retention policy.

Do not publish real videos publicly without explicit operator confirmation.

Do not stop after producing a plan.

Continue through implementation, testing, deployment and GitHub delivery as far as the available environment and permissions permit.

At the end:

1. Run the complete relevant test suite.
2. Build the required Docker services.
3. Execute the existing startup script.
4. Verify the actual running application.
5. Leave the application running.
6. Commit and push all intended changes.
7. Verify the PR and CI.
8. Produce the required final report.

**SUCCESS MEANS A WORKING, TESTED, OPERATOR-USABLE AI CONTENT FACTORY — NOT JUST CODE THAT LOOKS COMPLETE.**