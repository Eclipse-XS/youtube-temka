# Unified Factory 8 + Factory 9 — Final Release Acceptance Report

- **Branch**: `integration/factory-8-9-unified`
- **Pull Request**: [Draft PR #3](https://github.com/Eclipse-XS/youtube-temka/pull/3) (target: `feat/factory-7.2`)
- **Baseline Integration Commit**: `f870aee281a0e65e18fdb86f71c1897e4b938d2e`
- **Release Gate Status**: `AI_STORY_VERIFIED` / `PENDING_HUMAN_EDITORIAL_APPROVAL`

---

## 1. Executive Summary of Resolved Integration Blockers

1. **Blocker 1 — `AI-Verified Story` False Rejections on Real Gameplay Footage (`INTEGRATION_BLOCKED`)**:
   - **Root Cause**: The `story_output_version=2` prompt in `factory/vision_vlm.py` instructed `qwen3-vl:2b-instruct` that *"driving, similar landscapes or shared HUD alone do not establish a story... Use at most six words per evidence field"*, causing the 1.7B model to output `coherent_single_event: false` on 18/18 real calls even when it observed valid narrative progression at `0.85` confidence. Furthermore, `factory/connected_windows.py` required 4 lexically unique strings across 4 static frames (`len({b.strip().lower() for b in beats}) == 4`), rejecting any clip where two frames described the same vehicle, and missed fast payoffs occurring between coarse 4-frame samples.
   - **Fix**: Implemented a 5-stage adaptive verification pipeline in `factory/connected_windows.py` and `factory/vision_vlm.py` (`story_output_version=3`):
     - **Stage A**: Format-break & hard-discontinuity screening plus diversity-aware candidate ordering (`diverse_primary_heads`, `max_examined=8`, `max_calls=18`).
     - **Stage B**: Panel-first 4-frame storyboard inspection (`panel_1_observed .. panel_4_observed`, `event_progression_observed`, `setup/development/climax/payoff_observed`).
     - **Stage C**: Adaptive second 4-frame pass focused on interior cut boundaries and peak-action/payoff sub-windows (8 frames total across 2 bounded VLM calls, keeping VRAM at `2.67 GiB` on the 4 GB RTX 3050).
     - **Stage D & E**: Temporal synthesis combining visual panel observations with speech/event phases and transparent verdicts (`VERIFIED_COHERENT`, `PLAUSIBLE_NEEDS_REVIEW`, `INSUFFICIENT_EVIDENCE`, `VERIFIED_DISCONTINUITY`, `FORMAT_BREAK`).
2. **Blocker 2 — Abrupt Mid-Clip Cuts in Early GTA `Smart Highlights` (`99.0–115.5s` & `120.0–140.5s`)**:
   - **Root Cause**: Streamer compilation cuts where a corner facecam appeared or disappeared (`Shot 19 -> 20` at `111.0s` with side-profile couch webcam in `bottom_right`; `Shot 26 -> 27` at `127.0s` with xQc webcam in `bottom_left`) were merged because single frontal Haar cascade detection missed side-profile faces and VLM edge verification overrode the corner layout change.
   - **Fix**: Upgraded `_detect_corner_faces` in `factory/source_intelligence.py` (`CACHE_REVISION = 2`, `:v2` cache tag) to run multi-cascade detection (`frontalface_default`, `frontalface_alt2`, `profileface` + horizontal flip) every `1.5s` at `480x270`, and enforced a hard `facecam_contradiction` continuity barrier (`severity = "strong_semantic_contradiction"`) in `factory/semantic_events.py` that prevents merging across corner webcam appearance/disappearance.
3. **Blocker 3 — Selection Review UI Transparency**:
   - **Fix**: Enhanced `dashboard/src/factory/SelectionReview.jsx` to display analyzed candidate count, VLM-verified window count, VLM model/calls/cache telemetry, `story_verdict` badges, and an expandable `"Діагностика ШІ-верифікації сюжету"` table showing per-candidate rejection reasons and narrative beats.

---

## 2. Quantitative Acceptance Matrix

| Gate ID | Quality Gate | Requirement | Observed Evidence | Status |
| --- | --- | --- | --- | --- |
| **G1** | Repository & Backup Integrity | Clean worktree on `integration/factory-8-9-unified`; verified backup `%LOCALAPPDATA%\Factory89-integration-backup-0f2b0d3` (`5` jobs in `jobs.sqlite3`); original Factory 8 staging (`15175`/`18082`) untouched | Verified git state, SQLite backup integrity, and healthy `factory80-staging-*` containers | **PASS** |
| **G2** | Root-Cause Audit of 6 Blocked Jobs | Full 70-candidate diagnostic table for job `bda1428ea797403a9155244f6b8797e0` and audit of all 6 `INTEGRATION_BLOCKED` jobs | Documented in [AI_STORY_ROOT_CAUSE.md](file:///C:/Users/Eclipse/Desktop/7%20семестр/робота/youtube-temka-unified/docs/unified-factory/AI_STORY_ROOT_CAUSE.md) | **PASS** |
| **G3** | Real-Media AI Story Benchmark (`P1–P4`, `N1–N5`) | Live `qwen3-vl:2b-instruct` benchmark on real GTA footage with 0 simulated VLM calls | **4/4 Positive TP** (`P1–P4` `VERIFIED_COHERENT`), **5/5 Negative TN** (`N1–N5` rejected), **0 FP, 0 FN** ([AI_STORY_BENCHMARK.md](file:///C:/Users/Eclipse/Desktop/7%20семестр/робота/youtube-temka-unified/docs/unified-factory/AI_STORY_BENCHMARK.md)) | **PASS** |
| **G4** | Rendered AI-Verified Story Outputs | At least 1 real AI-Verified Story rendered end-to-end with verified overlap and audio loudness | **2 full jobs rendered** (`c8f4a90f77164f8a85b9c3996475bcfa` `P1` 2 parts @ `17.5s`; `383316f996ca4cf7848d0ea7f0908840` `P3` 2 parts @ `23.17s`) in `%LOCALAPPDATA%\Factory89-unified\exports\ai_story_p1` & `ai_story_p3` | **PASS** |
| **G5** | Early GTA Smart Highlights Repair | Eliminate false continuity merges at `111.0s` (`99–115.5s`) and `127.0s` (`120–140.5s`) and re-render | Job `7781118af0794efab72ddfb3f1669fe5` rendered clean coherent clips `95.0–111.0s` (`-14.4 LUFS`) and `30.5–47.0s` (`-14.3 LUFS`) in `%LOCALAPPDATA%\Factory89-unified\exports\gta_repaired` | **PASS** |
| **G6** | Multi-Source Long-Form Compilation E2E | Combine multiple real sources, test reorder/trim/fade/stale-revision 409, and render master 16:9 video | Job `0d65a6ed4849425dbcb2e28087db6839` combined `617.9s` + `720.7s` sources (20 coherent segments, `392.62s` / `6m 32.6s`, `1280x720`, `30 fps`, `-14.8 LUFS`, HTTP 409 verified on stale revision) | **PASS** |
| **G7** | Checkpoint & Interruption Recovery | Verify ASR chunk recovery, CV/VLM cache recovery, and schema/version invalidation without duplicate work | Verified via `factory_tests/test_recovery.py` (`16 passed`, including new mid-ASR and CV/VLM cache-invalidation tests) | **PASS** |
| **G8** | Hardware & 4 GB VRAM Compliance | Peak VRAM within 4096 MiB on RTX 3050 Laptop GPU during 2-pass VLM verification | Peak VRAM **`2667–2673 MiB`** (`65.3%` of 4096 MiB); avg VLM latency `11.1–11.6s/call` | **PASS** |
| **G9** | Full Automated Regression Suites | Backend (`factory_tests`), shared (`tests`), compilation, secrets check, PowerShell checks, frontend build, Docker Compose config | `291 passed` (`factory_tests`), `161 passed` (`tests`), `15 passed` (PS1 checks), `check-secrets.py` clean, `vite build` clean | **PASS** |
| **G10** | Live Staging UI & Workflow Verification | Browser verification of unified staging (`127.0.0.1:25175/factory.html`) across tabs and new AI Story diagnostics panel | Verified live in browser across `Create`, `Jobs`, `Editor` (Selection Review + AI Story diagnostics + Montage Plan), `Library`, `Publish`, `Settings` | **PASS** |

---

## 3. Hardware & Resource Telemetry

| Metric | Observed Value | Notes |
| --- | --- | --- |
| **GPU Model** | NVIDIA GeForce RTX 3050 Laptop GPU (`4096 MiB` total VRAM) | Detected via `nvidia-smi` |
| **Idle VRAM Before VLM Run** | `1027 MiB` | Windows desktop + background services |
| **Active VRAM During `qwen3-vl:2b-instruct` (2-pass 4+4 frames)** | `2667 – 2673 MiB` | Leaves `~1.4 GiB` safety headroom on 4 GB GPU |
| **Average VLM Call Latency (Cold Cache)** | `11.15s – 11.64s` per 4-frame storyboard call | Measured across 20 live benchmark & job calls |
| **Average VLM Call Latency (Warm SQLite Cache)** | `< 0.01s` (`cache_hits` served from `source_intelligence.sqlite3`) | Versioned by prompt hash + `story_output_version=3` |

---

## 4. Feature & External Integration Preservation Matrix

| Subsystem | Origin | Verification Method | Status |
| --- | --- | --- | --- |
| Multi-channel YouTube OAuth & Analytics Sync | Factory 8 | `factory_tests/test_Readiness.py`, `test_publish.py`, live `/api/channels` & `/api/settings` inspection (no credentials modified or exposed) | **Preserved** |
| Google Drive Ingestion & Export Integration | Factory 8 | `factory_tests/test_gdrive.py`, `/api/gdrive/status` endpoint check (no test uploads executed) | **Preserved** |
| Composition Presets, Dynamic Framing & Background Library | Factory 8 | `factory_tests/test_composition.py`, `exports/hook_and_background` QA (`1080x1920`, `-15.79 LUFS`) | **Preserved** |
| Source Intelligence, Semantic Event Graph & Local Qwen3-VL | Factory 8 + Unified Repair | `factory_tests/test_source_intelligence.py`, `test_semantic_events.py`, `test_editorial_engine_8.py` (`44 passed`), live benchmark | **Enhanced & Verified** |
| Chronological `Story Split` (Full-Range Part Splitting) | Factory 9 | `factory_tests/test_workflows.py`, `exports/split` (`3` chronological parts with `2.0s` overlap) | **Preserved** |
| Multi-Source `Longs Compilation` & Revisioned Edit Plans | Factory 9 | `factory_tests/test_edit_plan.py`, `test_workflows.py`, job `0d65a6ed4849425dbcb2e28087db6839` (`392.62s`, 20 segments, revision 3) | **Preserved & Verified** |
| Worker Lease Recovery, Checkpoints & Twitch HLS Support | Factory 9 | `factory_tests/test_recovery.py` (`16 passed`), `test_hardening.py` | **Preserved & Verified** |

---

## 5. Classification of Remaining Work & Release Decision

### 5.1 Remaining Work Classification
1. **Completed in This Release**:
   - Adaptive 2-pass bounded VLM verification for `AI-Verified Story` (`story_output_version=3`).
   - Multi-cascade corner facecam detection (`:v2`) and hard continuity barrier preventing unrelated streamer clip merges in `Smart Highlights`.
   - Frontend `SelectionReview.jsx` diagnostic transparency for `story_verdict`, VLM call/cache counts, and candidate rejection reasons.
   - Real-video positive/negative benchmark (`P1–P4`, `N1–N5`), rendered AI Story jobs (`P1`, `P3`), repaired Smart Highlights job, and 20-segment multi-source Longs Compilation (`392.62s`).
2. **Future Non-Blocking Enhancements (Post-PR #3)**:
   - Optional 8 GB+ GPU profile enabling `qwen3-vl:4b-instruct` or `8b-instruct` when `nvidia-smi` reports `>= 8192 MiB` VRAM, while keeping `qwen3-vl:2b-instruct` with 2-pass 4-frame storyboards as the default for 4 GB GPUs.
   - Optional acoustic music-bed fingerprinter to further assist compilation cut detection when neither clip contains a streamer webcam.

### 5.2 Formal Release Decision
- **Technical & AI Integration Gate**: **`AI_STORY_VERIFIED` / `READY_FOR_MERGE_REVIEW`**
- **Editorial Governance State**: **`PENDING_HUMAN_EDITORIAL_APPROVAL`** (human operator review of the rendered exports in `%LOCALAPPDATA%\Factory89-unified\exports\` before switching PR #3 from Draft to Ready-for-Merge).
