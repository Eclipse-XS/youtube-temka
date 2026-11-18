# Optional speech synthesis provenance

Ordinary clipping preserves original audio and does not load a speech engine.
The optional converter runs through a text/PCM-WAV subprocess boundary on CPU.

- Runtime: [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx), 0.6.1, MIT.
- Weights: [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), Apache-2.0.
  Downloaded separately from the kokoro-onnx model-files-v1.1 release, with pinned
  SHA-256 in `factory/tts.py`; weights are not in Git or the application image.
- Voices: af_heart, af_bella, am_michael (EN); ef_dora, em_alex (ES).
- The runtime's phonemizer/eSpeak dependencies are GPL-3.0. The separate optional
  `factory/tts_worker.py` is GPL-3.0-or-later; its source and GPL text are supplied.
  This optional image is therefore **not an MIT-only dependency distribution**.
  The normal image excludes these dependencies. Preserve the source, notices and
  GPL obligations when redistributing the optional worker/dependencies.

RU/UK alternatives were investigated but not silently enabled:

- Piper [ru_RU-irina-medium](https://huggingface.co/rhasspy/piper-voices/blob/main/ru/ru_RU/irina/medium/MODEL_CARD)
  explicitly gives the dataset license as **Unknown**. Rejected for this release.
- Piper [uk_UA-lada-x_low](https://huggingface.co/rhasspy/piper-voices/blob/main/uk/uk_UA/lada/x_low/MODEL_CARD)
  lists Apache-2.0 training data, but is an extra 16 kHz x_low voice whose quality
  has not been evaluated here. Not presented as a verified natural voice.

RU/UK original speech and captions remain supported by Whisper; new RU/UK
narration is unavailable. No noncommercial voice pack is bundled. Voice preference
is subjective: the UI supplies real previews rather than promising a particular
perceived quality. See verification/tts-results.json for actual EN/ES synthesis.
