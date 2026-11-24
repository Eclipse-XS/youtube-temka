# Factory 10 acceptance

The release is in draft. This checklist records the behavior each test covers.
The [machine-readable acceptance file](ACCEPTANCE.json) lists source files,
test names, evidence and remaining limitations.

## Satisfied checks

- **A1–A2.** Rendering uses a saved timeline revision. A decoded MP4 confirms
  that moving a hook and SFX moves their appearance and sound. The compiler
  checks source bounds, dependencies, overlap and supported operations.
- **B1.** Gameplay Longs can alternate sources within a theme, fit source
  limits and leave unsupported beats empty.
- **C1–C3.** Tests decode effects, freezes, replays, slow motion and overlays.
  A transition test measures both source colors and both audio frequencies
  during the overlap. Optional automatic edits require visible payoff evidence.
- **D1.** Audio tests exercise preservation, gain, fades, synchronized procedural
  accents, peak headroom, and music mixing. Existing recovery checks cover
  licensed library asset transfer to workers.
- **E1.** Decoded sample frames verify the cold-open, intro and outro order and
  the resulting duration. The editor can save channel styling in the browser.
- **F1.** Gameplay ranking works on silent footage. Hook suggestions use a
  supported event inside the selected interval, and the operator can opt out.
- **G1.** Manual caption cues, timing and styles persist in their own track
  revisions. The correction test explicitly prevents a new ASR call.
- **H1.** A 640×360 draft preview contains the timeline's rendered hook,
  captions and audio cue. Final export reuses the prepared source range.
- **I1.** A repeated gameplay job reuses probe, signal, selection and render
  checkpoints while producing the identical output hash.
- **I3.** Repeated live Qwen text selection used zero new requests for one
  fixed transcript and returned the same accepted selection. End-to-end model
  request reduction remains an open measurement.
- **J1.** A repeat of an approved local revision reuses the cached encode and
  returns identical output bytes. Reproduction evidence records the inputs and
  settings that can be verified on the worker.
- **J3.** The full Linux run passed 2,307 tests with 66 skips and zero failures,
  including both previously blocked subtitle API checks. [Regression commands](REGRESSION_RESULTS.md)
- **K1.** Two locally recorded Neverball levels produced three validated
  Shorts and a 20-second compilation. A revised compilation and its proxy
  visibly show the new opening and hook.
- **M1.** The implementation was delivered to the existing draft.
  [Factory 10 PR](https://github.com/Eclipse-XS/youtube-temka/pull/4)

## Open checks

- **I2 — FAIL.** Cold-cache median improved 8.2%. Repeated identical jobs
  improved 57.6%. The cold result remains below the 30% target.
- **I4 — BLOCKED.** The available RTX 3050 has 6 GiB. The requested physical
  4 GiB residency and live vision-model comparison are still pending.
- **J2 — BLOCKED.** Live Drive was unavailable. Mocked upload and publication
  recovery are covered by tests.
- **K2 — UNVERIFIED.** A human must review the intended GTA categories and
  compare the output against authorized source intervals. The record must
  distinguish technical playback from editorial quality.
