# Factory 8.0 — Editorial & Technical Acceptance Matrix

Status vocabulary: `NOT_STARTED` | `IN_PROGRESS` | `IMPLEMENTED` | `TECHNICALLY_TESTED` | `EDITORIALLY_VERIFIED` | `BLOCKED`

| Criterion | Target | Baseline (`aef60f1`) | Factory 8.0 Current | Status |
|---|---|---|---|---|
| GTA Regression: Candidate A (`554.12–600.26`) end card removed | 0% end-card contamination | FAILED (PUMBA end card at 598.5–600.26 s) | Pending Phase 3/5/11 | `NOT_STARTED` |
| GTA Regression: Candidate B (`172.98–216.98`) unrelated scenes separated | 0% multi-clip merge | FAILED (car → street → boat → night foot) | Pending Phase 3/5/11 | `NOT_STARTED` |
| GTA Regression: Candidate C (`5.42–52.50`) intro card & unrelated clips separated | 0% title-card contamination | FAILED (PUMBA PRESENTS + 5 clips) | Pending Phase 3/5/11 | `NOT_STARTED` |
| Temporal correctness | 100% valid timestamps & durations | PASS | Pending Phase 11 | `NOT_STARTED` |
| Technical render validity (1080×1920, audio, sync, no black frames) | 100% pass | PASS | Pending Phase 11 | `NOT_STARTED` |
| Semantic grounding (no unsupported claims presented as verified) | 0 unsupported verified claims | Partial (generic titles) | Pending Phase 7/11 | `NOT_STARTED` |
| Source-aware layouts (no forced 65/35 split without secondary video) | Adaptive layout per source | FAILED (65/35 default with background) | Pending Phase 6/11 | `NOT_STARTED` |
| 30 mandatory regression test cases | 30/30 passing | Not implemented | Pending Phase 11 | `NOT_STARTED` |
| GPU stability on RTX 3050 4 GB (no OOM) | 0 OOMs under default config | PASS (CPU/3B text only) | Pending Phase 4/10 | `NOT_STARTED` |
| Cross-source Precision@3 on independently annotated holdout set (15–20 sources) | ≥ 70% | No holdout dataset | Pending external authorized sources & human annotators | `BLOCKED` |
| Final Human Editorial Approval (≥ 2/3 GTA highlights) | Human reviewer sign-off | 0/3 approved | Pending Phase 11 human review package | `NOT_STARTED` |
