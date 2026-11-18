# Content Factory integration provenance

Base: [mutonby/openshorts](https://github.com/mutonby/openshorts), commit
`7f3eae66330d2aa3e580562769eccfc0fa9d8e1d`, MIT core, Copyright (c) 2024 OpenShorts.
Original LICENSE and NOTICE are preserved. The original repository remains in
Git history and the factory changes preserve the existing main-branch history.

The deployed adapter directly reuses `transcribe_backends.py`, `subtitles.py`,
`ffmpeg_utils.py`, `gpu_decode.py`, `jsonfile.py`, `security_utils.py` and
`ssrf_guard.py`. React, Vite, Lucide and the upstream dashboard dependency lock
are reused. Only the factory entry point is compiled in the production image.

The current upstream default server cannot meet the requested MIT-only runtime
unchanged: app.py imports `cloud.queue_mode` at module scope (line 171 at the
base commit), and `cloud.owner_cache` at line 893, even with billing disabled.
`cloud/LICENSE` explicitly excludes that directory from MIT. The adapter API
avoids those imports; the Dockerfile copies an explicit allowlist and does not
copy `cloud/`. The restricted directory is retained in the upstream checkout,
but is not part of the runtime image or active deployment. No commercial cloud
source has been copied into the adapter.

References inspected locally, not merged as applications:

- [Chopify](https://github.com/mehbul/chopify), commit
  `d576927bf3b764733c97ac1ad324aa9957b0885d`, MIT, Copyright (c) 2026 Mehbul Islam.
  Reviewed `ingest.py` audio discovery and bounded `download_section`, and
  `download_and_transcribe.py` chunked transcription. Our adapter follows the
  audio-first/chunk/selective-section approach; it intentionally excludes the
  reference's full-source fallback.
- [Clipper](https://github.com/Steezy-code/clipper), commit
  `518afe7dedeb1bccd83152e688feaed2f4d0adef`, MIT, Copyright (c) 2026 Steezy-code.
  Reviewed `clipper/layout.py`: even split dimensions, looped background,
  `vstack`, subtitles, and source-only audio. The adapter uses standard FFmpeg
  equivalents; it does not copy or launch a second job engine.

No code from ClippyMe or Reelit was needed. Reference checkouts are ignored under
`.reference/` and excluded from build contexts.

Other runtime components retain their respective upstream licenses, including
FFmpeg (Debian build), faster-whisper, CTranslate2, PyAV, yt-dlp, Ollama, and
Qwen2.5 model weights. Qwen model weights are downloaded separately by Ollama;
they are not embedded in this repository. Deployment does not grant rights to
source videos, gameplay assets, fonts, or third-party services.

Smart framing reuses the MIT sendcmd de-duplication idea from reframe_v2.py, with
a CPU OpenCV Haar detector and smoothed camera trajectory. Optional Kokoro runtime,
weights, voice selection and GPL dependency boundaries are documented in
[the TTS provenance](docs/licenses/TTS.md).
