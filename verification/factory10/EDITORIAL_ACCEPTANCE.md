# Factory 10 editorial acceptance

## Release candidate retest

Five exports of the same authorized Neverball captures reached `READY` on the release candidate. The three Shorts were 10.00 seconds at 1080×1920. The original and revised two-source compilations were 20.021 seconds at 1280×720. The edited proxy was 640×360. A decoded contact sheet of the previous intermediate build exposed a black lead-in on the automatic Short. That build selected source 0–10 seconds and sampled 20% black frames. The candidate selected 2–12 seconds and sampled zero black frames. The fall and its on-screen result remained visible. The five candidate MP4s each sampled zero black frames.

A separate invocation of the new runner completed a Short, a multi-source export, and a proxy plus rerender using the same authorized development inputs. The raw results are private in `verification/test-output/f10-release-runner-20261125-010350/results.json`. The media rerun is in `verification/test-output/f10-stable-neverball-release-20261125-010906`.

In a fresh Chromium profile against an isolated controller, a pre-staged local recording went through browser creation and an approved export. The new limits persisted as four proposals and zero model calls. The job retained a manual hook, caption cue and punch-in through its 540×960 proxy and final 1080×1920 export. The final export decoded 299 frames at 9.967 seconds with zero sampled black frames. See `verification/test-output/f10-browser-20261125-012450/browser-results.json` and the corresponding `browser-preview.png`.

No held-out GTA output or independent editorial rating was available. GTA Precision@K, Recall@K, low-motion recall, payoff preservation, accepted Shorts and the two Longs ratings remain unverified.

## Freeze the GTA inputs

Use [ACCEPTANCE_CORPUS.json](ACCEPTANCE_CORPUS.json) as the manifest template. The checked-in file contains no media or ground-truth entries. In a private copy, use the following schema.

- `sources` entries have `id`, `session`, `game` (`GTA V` or `GTA VI`), `authorized: true`, and exactly one `file` under the corpus root or authorized HTTPS `url`.
- `jobs` entries have `id`, `split` (`development`, `acceptance`, or `benchmark`), `kind` (`shorts`, `longs`, or `edit`), and `windows`. Each window provides its `source` ID, `start`, and `end` in source seconds. Longs windows also accept the usual source exclusions, preference and contribution settings. Use a frozen `k` on each Shorts job. Default to five ranked candidates per ten minutes of selected material and record any deviations in advance. Job `settings` can exercise supported profiles, for example `{"text_mode":"hook_subtitles"}`. Mark authorized storage jobs with `drive: true`.
- `positive_events` entries have `id`, `source`, `original_timestamp`, `setup`, `trigger`, `essential`, `payoff` (or `null`), `category`, `description`, `speech_necessary`, `reframing_risk`, `low_motion_or_silent`, and `delayed_payoff`. Intervals are two-element arrays in source seconds. The required categories are `npc_behavior`, `vehicle_crash`, `stunt_fail`, `ragdoll`, `physics_glitch`, `unexpected_survival`, and `silent_visual_comedy`.
- `negative_examples` entries have `id`, `source`, `interval`, and `category`. Include `ordinary_driving`, `continuous_gunfire`, `camera_rotation`, `walking`, `scene_transition`, `routine_gameplay`, and `loud_uneventful`.

Use independent development and held-out recordings. Hold out at least eight independent sessions or intervals, 30 positive and 20 negative labels, five silent or low-motion events, and five delayed payoffs. Include different FPS values, resolutions and audio characteristics. Prepare two independent multi-source Longs workloads, at least ten automatic Shorts, an edited rerender and an authorized remote workflow. Keep the input hashes and manifest fixed during acceptance.

The runner uses one-to-one matching by source, trigger coverage, at least 80% essential-interval coverage, and full annotated payoff coverage. To expose cut-off payoffs, it also measures full payoff coverage over the candidates eligible on trigger and essential interval before imposing the payoff requirement. It reports returned candidate count, frozen K, negative overlaps, per-category counts and the low-motion subset.

## Independent review of automatic outputs

Review the original automatic files before opening the edited outputs. Record an ID, source timestamp, editorial decision and any substantial edits required for every Short in the frozen sample. Check its setup, trigger, payoff, essential action, original audio, effect relevance and timing, and hook and caption grounding and readability. At least nine of the ten prespecified Shorts must be accepted. Include failed or missing exports in the sample denominator.

Each of the two Longs must be 8–15 minutes. Independently score opening, scene selection, context, continuity, pacing, comedic timing, diversity, transitions, audio consistency and ending from 0 to 5. Record timestamps for issues. Each Longs requires at least 43/50 points and every item must score at least 3/5. Check source timestamps, duplicated scenes and irrelevant padding before accepting. Save reviewer identity and notes with the results.

## Real gameplay export

The fixtures use two locally recorded 25-second Neverball runs, Bumps and
Corners. The ball rolls off the course in both runs. The capture uses the
Debian Neverball package, a virtual display and scripted keyboard input.
The speech-bearing export adds the project's original synthesized English
speech fixture. [Neverball project](https://neverball.org/) ·
[Neverball Debian manual and credits](https://manpages.debian.org/testing/neverball/neverball.6.en.html)

- `silent-no-hook.mp4` and `manual-full-duration-hook.mp4` are 10.00-second
  1080×1920 Shorts from source 1, 2.50–12.50 s. Both have zero audio tracks.
  The selected visual-activity marker was 6.00 s and scored 22.711.
- `spoken-audio.mp4` uses the same gameplay interval with the locally added
  speech. The decoded audio peak was approximately 0.571 on a full-scale
  linear scale. This run exercises speech-bearing media delivery.
- `multi-source.mp4` is a validated 1280×720, 20.021-second export. The planner
  first used source 2 at 3.00–13.00 s, with a visual-activity score of 39.234
  and marker at 6.50 s. It then used source 1 at 2.50–12.50 s.
- `revised-multi-source.mp4` reverses those scenes and adds a hook at 0.50–2.00 s
  and a zoom at 1.00–2.00 s. `revised-preview.mp4` shows the same change at
  640×360. Decoded stills confirm the revised opening and hook in both exports.
  The export reported 9.579 s in render stages, including a reused scene.
- The review package records source hashes, exact events, results, and sampled
  resources in `gameplay-results.json`. CPU x264 was used. Peak sampled
  device-wide VRAM was 631 MiB. Peak sampled host RAM in this run was about
  14.0 GiB, across host processes.

The gameplay test ran without a vision model. Payoff fields remain unknown.
The 20-second compilation met technical checks. A longer 8–15-minute corpus,
GTA-specific glitches and NPC comedy, and independent editorial review remain
open.

### Reproduce the local package

```powershell
$captureScript=(Resolve-Path verification/factory10/capture_neverball.sh).Path
$captureOut=(New-Item -ItemType Directory -Path verification/test-output/gameplay-inputs -Force).FullName
docker run --rm --user root --mount "type=bind,source=$captureScript,target=/capture.sh,readonly" --mount "type=bind,source=$captureOut,target=/capture" --entrypoint sh youtube-temka-worker:latest /capture.sh
.venv/Scripts/python.exe verification/factory10/accept_gameplay.py verification/test-output/gameplay-inputs/neverball-1.mp4 verification/test-output/gameplay-inputs/neverball-2.mp4 --speech verification/speech-en.wav --workspace verification/test-output/f10-real-gameplay --rights-confirmed
```

Select a new output directory for each export run. The original English speech
fixture can be omitted when only silent gameplay is being reviewed.

### Human review rubric

Reviewers compare each selected interval against the original recording and
score each category 0, 1, or 2. A score of 0 marks a missed requirement, 1 marks
an adequately handled requirement with a visible problem, and 2 marks a clear
pass. Save timestamped evidence and any proposed trim.

- **Context and payoff.** Setup, trigger and visible consequence are present
  and understandable before the viewer sees the result.
- **Framing and text.** Important action remains visible. The hook describes
  the specific event, and captions match audible speech or visible action.
- **Audio and pacing.** Original gameplay audio is understandable when present.
  Effects, silence and cuts support the action. Loud peaks have headroom.
- **Multi-source continuity.** The opening attracts attention, adjacent scenes
  have a recognizable relationship, and the ending has a distinct payoff.
- **Selection accuracy.** Annotate missed events and false positives separately
  for each desired GTA category. Use those annotations for recall@K and review
  whether the automatic crop or hook hid any payoff.

## Earlier controlled fixtures

The automated gameplay fixture is generated locally with moving graphics and
sound. It exercises all selected scan windows, keeps original audio, and
produces a technically valid Short without speech recognition. The output
requires review and the selected movement remains `unknown_event`.

The controlled Longs fixture uses three generated sources with distinct frame
rates and dimensions. It verifies playable assembly, timing and source
identity. It cannot establish comedic payoff, cross-source narrative quality
or an editorial preference.

The earlier Ollama streaming protocol test used a mocked response. The visual
review schema was tested separately. Real vision-model quality and target GPU
throughput remain open.
