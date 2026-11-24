# Factory 10 defect register

Current implementation: `ac32ab0f2780e83d5b60e19a83cd7474eb28d122`.

## Corrected defects

- **F10-001 · P1 · Localized motion was dropped.** A visible change confined to one small tile could fall below the 2.5% whole-frame motion threshold. A separate local-motion signal now yields bounded proposals alongside high-motion peaks. `test_gameplay_keeps_local_motion_separate_from_motion_peaks` verifies that both enter the pool. The held-out GTA recall remains pending.
- **F10-002 · P1 · The first source could spend the whole visual budget.** The prior compilation loop ran model review before discovering the next source. The shared review now assigns an initial opportunity to each viable source and reserves any expansion until after that phase. `test_gameplay_visual_budget_reviews_each_source_before_expansion` verifies source order, shared budgets and the expanded frame indices with a controlled model response.
- **F10-003 · P1 · Unrelated events could receive the same category hook.** The prior generator assembled suggestions solely from the predicted event class. New reviews can supply short phrases tied to the action, contrast or visible result with trigger and payoff timestamps. The render selects distinct normalized automatic hooks within a job. Existing legacy review suggestions remain readable. GTA language and presentation ratings remain pending.
- **F10-004 · P1 · One recording could contribute overlapping scenes under two source IDs.** The planner now checks overlap per underlying recording, preserves source-order continuity after the cold open and applies source contribution limits. `test_gameplay_compilation_rejects_duplicate_recording_ranges_across_source_ids` covers the duplicate range.
- **F10-005 · P1 · Automatic selection could lead with dead air.** The Neverball Short included black frames from its source preroll. The gameplay scan now records runs of black frames and trims candidate boundaries around them within the request's duration limits. `test_gameplay_proposals_trim_black_lead_in_without_losing_the_event` reproduces the original failure. [Decoded media evidence](EDITORIAL_ACCEPTANCE.md)
- **F10-011 · P1 · Vision requests could exceed the configured context.** The real Ollama server rejected a three-frame Neverball request requiring 3,283 tokens at the old 2,048-token limit. The initial and six-frame review now reserve 4,096 and 8,192 tokens respectively. The retest reached model execution. The instance then exceeded the old first-token deadline, so the next revision reduced the thumbnail size and set a bounded 180-second read window. [Performance](PERFORMANCE.md)
- **F10-012 · P1 · Gameplay streams with a 100–250 ms difference could pass validation.** A controlled MP4 with roughly 200 ms of end skew passed the legacy check. Gameplay validation now checks 100 ms and invalidates old validation records for that profile. `test_gameplay_validation_enforces_100ms_stream_end_alignment` verifies the behavior with decoded A/V.

## Open P1 release gaps

1. **F10-006 · Editorial acceptance.** The authorized GTA development and held-out sets with annotations are missing. Run the corpus acceptance and independent review for detection, automatic editing, full Longs, hooks, captions and final media. [Editorial acceptance](EDITORIAL_ACCEPTANCE.md)
2. **F10-007 · Live vision, target environment and throughput.** The available RTX 3050 reports 6,144 MiB. The final development probe timed out after 180 seconds without a visual response fragment. The first-token delay needs investigation on the 4,096 MiB target before awarding production time or model quality points. The 280-minute incident lacks a reproducible input and log pair. [Performance](PERFORMANCE.md) · [Target hardware](TARGET_HARDWARE.md)
3. **F10-008 · Live Drive.** The private destination and authorized credential pair are unavailable. Run one Short and one Longs upload and verify the checksums. [Deployment and rollback](DEPLOYMENT_AND_ROLLBACK.md)
4. **F10-009 · Reliability pilot.** The predeclared ten consecutive representative jobs have not run. Include the remote, captioned, silent, Longs, edited and Drive cases with one tested build. [Regression results](REGRESSION_RESULTS.md)
5. **F10-010 · Deployment lifecycle.** The browser smoke and an isolated backup and restore of copied test state passed. Complete three starts through the supported launcher and verify an upgrade and rollback with deployed services and replayable approved jobs. [Deployment and rollback](DEPLOYMENT_AND_ROLLBACK.md)

No P0 defect was observed in these tests.

**P2 observation · Timing-sensitive queue regression.** The first candidate run measured a 163 ms event-loop stall versus a 150 ms test limit. The targeted test and the full suite passed on the same candidate in a repeat with the separate vision and browser workloads stopped. Preserve both results in the release evidence. [Regression results](REGRESSION_RESULTS.md)
