# Factory 8.0 — Implementation Status Tracker

Status vocabulary: `NOT_STARTED` | `IN_PROGRESS` | `IMPLEMENTED` | `TECHNICALLY_TESTED` | `EDITORIALLY_VERIFIED` | `BLOCKED`

| Phase | Component | Status | Evidence / Notes |
|---|---|---|---|
| Phase 0 | Active Factory Pipeline Audit | `IMPLEMENTED` | Audited all core `factory/*.py`, `deploy/factory.Dockerfile`, `requirements-factory.lock`, `dashboard/src/factory/*.jsx`, baseline `222 passed` |
| Phase 0 | Legacy OpenShorts & External Reuse Audit | `IMPLEMENTED` | Verified MIT core vs AGPL-3.0 (`clips-studio`, `reelsaw`); reuse matrix documented in `UPSTREAM_REUSE_AUDIT.md` |
| Phase 1 | Reproducible Editorial Benchmark (`factory/benchmark.py`) | `TECHNICALLY_TESTED` | Schema v2 evaluator (`factory/benchmark.py`), GTA regression fixture (`verification/benchmarks/gta_yux8s3lwLss_v2.json`), 4/4 tests passing; cross-source human holdout pending external sources |
| Phase 2 | Unified Source Intelligence (`factory/source_intelligence.py`) | `NOT_STARTED` | Sequential PyAV shot/audio/HUD/OCR-fallback evidence engine |
| Phase 3 | Semantic Event Graph (`factory/semantic_events.py`) | `NOT_STARTED` | Shot continuity graph, format-break detection, event grouping, anti-padding boundary refinement |
| Phase 4 | Practical Multimodal Vision (`factory/vision_vlm.py`) | `IN_PROGRESS` | Pulling `qwen3-vl:2b` & `moondream` into local Ollama for empirical 10-case RTX 3050 4 GB VRAM/accuracy benchmark |
| Phase 5 | Multi-Stage Highlight Discovery & Ranking (`factory/discovery.py`) | `NOT_STARTED` | Map → Pool → Verify → Score (12-dim) → Pairwise Rank → Select |
| Phase 6 | Intelligent Editing & EditManifest (`factory/edit_manifest.py`, `framing.py`, `media.py`) | `NOT_STARTED` | Source-aware layouts, scene-aware crops, curated presets, hook/caption safe placement |
| Phase 7 | Contextual Metadata & Hook Intelligence (`metadata.py`, `hooks.py`, `drafts.py`) | `NOT_STARTED` | Grounded event-specific metadata + manual edit preservation |
| Phase 8 | Editorial Review UX & Feedback Persistence (`api.py`, `store.py`, React UI) | `NOT_STARTED` | Visual timeline, evidence cards, trim/split/merge, feedback storage, honest review states |
| Phase 9 | Business, Rights & Monetization Readiness | `NOT_STARTED` | Rights provenance schema, reused-content warnings, production economics tracking |
| Phase 10 | Performance Engineering & Resource Bounds | `NOT_STARTED` | Measured VRAM/RAM/latency/cache reuse report |
| Phase 11 | Exhaustive Editorial Acceptance & Full GTA Evaluation | `NOT_STARTED` | 30+ regression cases + full 618 s GTA reanalysis + rendered MP4 visual inspection |
| Phase 12 | Integration, CI & Release Candidate | `NOT_STARTED` | Full test suite, frontend build, launcher tests, safe push to `feat/factory-quality-rebuild` |
