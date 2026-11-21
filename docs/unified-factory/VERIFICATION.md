# Integration verification

The two incoming heads, local snapshot and shared ancestor are recorded in
[INTEGRATION_BASELINE.md](INTEGRATION_BASELINE.md). This branch targets
`feat/factory-7.2` and is delivered in draft PR #3.

## Regression commands

The Factory test command in the offline Docker regression run was
`python -m pytest -p no:cacheprovider -q factory_tests` from the checked-out
source. GitHub CI ran `python -m pytest factory_tests -q` on Linux and reported
287 passes. Its shared-module run reported 161 passes:

```
python -m pytest tests/test_jsonfile.py tests/test_ffmpeg_utils.py tests/test_subtitles.py tests/test_ssrf_guard.py tests/test_ssrf_connect_guard.py tests/test_transcribe_backends.py tests/test_file_locks.py -q
```

`npm ci --no-audit --no-fund` and `npm run build` in `dashboard` built the web
app. Edge browser checks exercised the Create modes, additional source ranges,
Jobs, Editor, Selection Review, Library preview, Publish profiles and Settings.

## Runtime and evidence

The loopback unified deployment uses Docker volumes for isolated SQLite and
scratch data. It preserves the five original history entries, uses the model
cache read-only, and mounts OAuth records read-only. The controller and web
ports are 28082 and 25175. The original staging deployment retains its ports
and volumes.

Drive authorization succeeded. The application verified the exact YouTube
identity for Leonida Mayhem and TheViceScope. Both Analytics synchronizations
reached READY. Each of the 21 background MP4s had registered license metadata
and returned HTTP 206 to a byte-range request. Publication was off throughout.

The GTA Smart Highlights run recorded seven completed Qwen3-VL requests and
exported two H.264/AAC Shorts at 1080x1920 and 30 fps. Measured durations were
16.5 and 20.5 seconds. A focused bridge-stunt run exported another 32.5-second
Short. Frame sampling showed the approach and the fall into water. The two
earlier excerpts contain abrupt scene changes. All outputs require human
editorial review.

Chronological splitting covered 28.5–160.0 seconds in three files with 3.0
seconds of overlap between adjacent parts. The first segment's SHA-256 remained
identical after the real Docker lease expired and the job recovered.

The three-source compilation used three authorized files derived from a common
GTA benchmark. A revised plan reordered the inputs, trimmed 0.25 seconds,
selected fades and rejected a stale render revision with HTTP 409. The final
H.264/AAC MP4 was 67.888 seconds at 1280x720 and nominal 30 fps. Its recorded
source lineage was source-2 (6.45–30 s), source-3 (13.47–35.77 s), source-1
(4–26 s). It measured −14.7 LUFS. The simulated assembly failure reused all
three rendered segments on retry.
