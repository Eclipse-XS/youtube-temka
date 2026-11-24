# Factory 10 editorial acceptance

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
