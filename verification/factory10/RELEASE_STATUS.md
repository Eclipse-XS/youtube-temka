# Factory 10 release status

This branch delivers a draft implementation milestone based on the open
Factory 9 pull request. Keep it out of production pending completion of the
remaining implementation and acceptance gates.

GitHub reported no write access to `Eclipse-XS/youtube-temka` and confirmed
write access to the configured `denusbtw/youtube-temka` fork, which also hosts
the Factory 9 PR head. Factory 10 uses `codex/factory-10` in that fork as its
head branch and targets `Eclipse-XS/youtube-temka:main` for review.

## Implemented in this milestone

- Source and attempt operation telemetry, streaming Ollama observations, and bounded request budgets.
- Independent ranges and source controls for compilation, plus estimated work before processing.
- Full-range sampling in Gameplay Only, visual candidate evidence, optional frame review, and ASR after selection when needed.
- One-pass local range normalization, verified render replay, and encoder information for final clip renders.
- Editable hook timing and presentation, caption styles and retained ASR reuse, and rendered Longs track export.

## Remaining implementation

- Gameplay rank profiles beyond Gameplay Only and general highlights, richer grounded hook generation, and a manual versioned caption track editor.
- A narrative planner for cross-source Longs and a multitrack editor that renders directly from its edited timeline. The current manifest describes the existing clip renderer's output.
- A composited proxy preview, additional editing effects and transitions, expanded audio direction, and configurable intro/outro and branding tracks.
- Persistent reusable caches for all processing stages and a richer resource and throughput profiler.

## Open verification gates

- Human review and ranking metrics on authorized real GTA footage.
- Live vision-model, 4 GB RTX 3050 and Docker/WSL acceptance, with peak process, container and GPU measurements.
- Repeated comparable real-media benchmarks, including model workload reduction and the 30% median wall-time target.
- Live Drive workflow and the two upstream subtitle API checks that require a POSIX runtime.
