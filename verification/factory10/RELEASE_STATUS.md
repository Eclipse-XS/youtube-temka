# Factory 10 release status

**FACTORY_10_RELEASE_CANDIDATE_BLOCKED**

The stable candidate adds localized-motion proposals, separate proposal and visual review limits, cross-source model scheduling, bounded evidence expansion, grounded hooks, source-aware Longs ordering, and automatic trimming of black preroll. The Windows Neverball rerun produced five decoded exports and a revised proxy. The verified release criteria, known defects, and target-machine procedure are maintained in the following files.

- [Release scorecard](RELEASE_SCORECARD.md) · [JSON](RELEASE_SCORECARD.json) · [Defect register](DEFECT_REGISTER.md)
- [Acceptance corpus](ACCEPTANCE_CORPUS.json) · [Editorial review](EDITORIAL_ACCEPTANCE.md) · [Runner](accept_release.py) · [Stable profile](STABLE_PROFILE.json)
- [Regression](REGRESSION_RESULTS.md) · [Performance](PERFORMANCE.md) · [Target hardware](TARGET_HARDWARE.md) · [Deployment and rollback](DEPLOYMENT_AND_ROLLBACK.md)

Factory 10 remains a draft. The head is `denusbtw/youtube-temka:codex/factory-10`.
The existing review targets `Eclipse-XS/youtube-temka:main`.
[Factory 10 draft PR](https://github.com/Eclipse-XS/youtube-temka/pull/4)

GitHub confirmed the pushed implementation commit `ac32ab0` on the draft PR branch. The GitHub checks API listed zero check runs for that commit. The isolated Linux repeat passed 2,313 tests, skipped 66 and failed zero. [Regression results](REGRESSION_RESULTS.md)

## Delivered

- Reviewed timeline revisions drive source selection, ordering, trim, visual
  effects, crossfades, mixing, hooks, captions, and branding. The worker saves
  approved revisions and can replay the current approved local edit.
- Gameplay Longs use a source-aware planner with visible evidence, contribution
  limits, and explicit uncertainty. Operators can revise the order and timing.
- Longs support rendered title cards, chapter labels, and audio/video fades.
  Gameplay editing profiles can use visible payoff evidence for optional effects.
- Caption cues and styles are versioned per scene. Composited proxies use the
  same edit decisions, and a later render can reuse analysis and selected ranges.
- Persistent checkpoints reuse eligible analysis and scene outputs. The report
  records timeline and input hashes, settings, runtime measurements and checks.

## Open release gates

- Review on authorized GTA recordings, including silent physics anomalies,
  NPC comedy, and other specified events. Human editorial quality remains open.
- Live vision and end-to-end model benchmarking on the target 4 GiB GPU.
  The measured cold-cache CPU workload improved 8.2%, below the 30% target.
- Live Drive acceptance and external publishing are pending. Recovery and
  idempotency were exercised against controlled test clients.

The local Neverball review package covers three Shorts, a two-source export,
and an edited revision with a composited preview.
Linux regression passed 2,307 tests with 66 skips and zero failures.

See [acceptance evidence](ACCEPTANCE.md), [machine-readable requirements](ACCEPTANCE.json),
[performance](PERFORMANCE.md), and [editorial acceptance](EDITORIAL_ACCEPTANCE.md).

## Implementation commits

- `ac32ab0f2780e83d5b60e19a83cd7474eb28d122` bounded vision thumbnails and first-token wait
- `3a713c91885caed50c082d092fe99c1af3d16ab2` measured vision context budget and 100 ms gameplay stream-end validation
- `ce1035424e95016df0ec866113f4c14208d9fc3d` separated gameplay proposals, shared visual review and release runner
- `690042548c3be7854571776425828e5cddc3540f` approved timeline rendering
- `9e2c525ee2d861b48e0d2757ea84d258a756818f` gameplay narrative planning
- `278d49a2a4168942022ed718b3cbe1d3cc5c4228` effects, mixer and crossfades
- `9ed68170540290131801313d78d52cf89c6854a9` branding and gameplay hooks
- `b1c389b969caf35c2d957efec8f170c1e47b766e` independent caption revisions
- `e1dc01086b88117d5aea8bebd71251a03f906288` draft video proxies
- `7f42aabf58a027d3c3378557d7413b16946b4fd4` reusable checkpoints and reproducibility
- `dbe0f229fb3276f074aa4de64abbdfc4a6d27e17` evidence-led effects, profiles and asset compatibility
