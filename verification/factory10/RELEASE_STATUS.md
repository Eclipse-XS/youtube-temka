# Factory 10 release status

Factory 10 remains a draft. The head is `denusbtw/youtube-temka:codex/factory-10`.
The existing review targets `Eclipse-XS/youtube-temka:main`.
[Factory 10 draft PR](https://github.com/Eclipse-XS/youtube-temka/pull/4)

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

- `690042548c3be7854571776425828e5cddc3540f` approved timeline rendering
- `9e2c525ee2d861b48e0d2757ea84d258a756818f` gameplay narrative planning
- `278d49a2a4168942022ed718b3cbe1d3cc5c4228` effects, mixer and crossfades
- `9ed68170540290131801313d78d52cf89c6854a9` branding and gameplay hooks
- `b1c389b969caf35c2d957efec8f170c1e47b766e` independent caption revisions
- `e1dc01086b88117d5aea8bebd71251a03f906288` draft video proxies
- `7f42aabf58a027d3c3378557d7413b16946b4fd4` reusable checkpoints and reproducibility
- `dbe0f229fb3276f074aa4de64abbdfc4a6d27e17` evidence-led effects, profiles and asset compatibility
