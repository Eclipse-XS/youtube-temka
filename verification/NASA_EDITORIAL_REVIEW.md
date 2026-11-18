# Editorial benchmark: observed results and limits

Technical completion and editorial quality are separate acceptance criteria.
No generated clip was publicly published. Scores and confidence are uncalibrated
model estimates, not human ratings or predicted audience success.

## NASA failure evidence and correction

The [Crew-9 conference](https://www.youtube.com/watch?v=wwhfph1vGdE) is an English
press conference, not a podcast. Its full 3025-second audio produced 701 real
ASR segments. A recovered run used that actual checkpoint, analyzed all 14
windows, and produced three verified Drive-backed clips with original audio and
burned captions. These are technical passes, **not accepted editorial highlights**.

| Absolute source interval | Output duration | Observed editorial defect |
|---|---|---|
| 318.52–348.44 s | 29.933333 s | Suggested title misinterpreted LEO as a person named Leo |
| 810.90–832.34 s | 21.466667 s | Generic/repetitive explanation; relevance requires human review |
| 1189.80–1230.36 s | 40.566667 s | Generic/repetitive explanation; context requires human review |

All three received raw score 9/100 and confidence 1.0. These contradictory
estimates were retained rather than silently rescaled. Earlier density fallback
also began an interval with a continuation. Sentence/pause boundaries improve
that behavior without proving that every thought is self-contained.

The updated implementation asks for 0–100 scores, a short concrete explanation
and a title quoted from the selected transcript. An unsupported title is replaced
with a source excerpt, its proposed value is retained as `suggested_title`, and
the result is visibly marked for review. Low scores, low confidence, heuristic
selection and unsupported titles require approval even with automatic publishing.
This is a title-grounding guard; ASR errors and inaccurate explanations can remain.

A fresh real first-300-second probe after that correction analyzed 51 segments in
54.83 s. It selected one of two requested intervals, 153.38–177.16 s, score 8,
confidence 0.9. Its unsupported title was replaced with a transcript quote and
review was required. This validates the guard, not editorial judgment.

## Authorized category matrix

Every row below reached READY, verified video and editable source on Drive,
cleaned its workspace, and served a Drive-backed preview with HTTP 206. Outputs
are 1080×1920. Spoken tests rendered captions. Human listening, transcription
accuracy and subjective highlight value remain unscored.

| Category / actual input | Technical output | Editorial acceptance |
|---|---|---|
| Ukrainian: real Wikitongues Vira video, first 120 s | Detected `uk`; 1667 transcript characters; 27.333333 s / 820 frames / audio; face detections 55 of 55 samples | Real pipeline PASS; ASR spelling errors observed; unsupported title replaced; review required |
| Russian: real Wikitongues Amir video, first 90 s | Detected `ru`; 1216 characters; 23.766667 s / 713 frames / audio; face detections 48 of 48 | Real pipeline PASS; mixed Russian/Hebrew source; spelling errors observed; review required |
| Gaming commentary: licensed VoxeLibre footage with original controlled SAPI commentary | 23.833333 s / 715 frames / audio; Gameplay Split with licensed 3 s looping background | Controlled technical PASS; real human gaming editorial acceptance UNVERIFIED |
| Reaction: original controlled David/Zira dialogue over test pattern | 24.433333 s / 733 frames / original audio; blur framing | Controlled technical PASS; real conversational reaction acceptance UNVERIFIED |
| Limited speech: real licensed gameplay, first 30 s, explicit Silent/no captions | 30.033333 s / 901 frames / no audio; crop; no ASR or AI highlight claim | Real visual technical PASS; subjective visual highlight quality UNVERIFIED |
| Interview/podcast | NASA is a press conference; controlled dialogue is synthetic | UNVERIFIED as a genuine podcast/interview benchmark |

Face-detection counts establish that tracking ran, not that framing was
subjectively correct. RU/UK source quotes can preserve recognition errors.
Inspected output frames show readable Cyrillic/Latin captions and the expected
crop/split/blur layouts. One Russian frame had no caption during a real SRT pause;
another frame at 15 s showed the expected Cyrillic text. These spot checks do not
establish full audio/subtitle alignment or temporal framing quality.
Gameplay music was replaced for controlled commentary; Silent explicitly removes
audio in the limited-speech test. Source licenses and adaptations were credited.

## Audio measurements and repaired overshoot

FFmpeg EBU R128/astats measurements of the decoded benchmark outputs:

| Output | Integrated loudness | True peak |
|---|---|---|
| Ukrainian | −16.1 LUFS | −1.9 dBFS |
| Russian | −13.9 LUFS | −2.1 dBFS |
| Controlled gameplay commentary | −17.7 LUFS | −0.8 dBFS |
| Controlled reaction, original run | −16.7 LUFS | **+0.3 dBFS: defect** |
| Controlled reaction, corrected rerender | −16.7 LUFS | **−4.7 dBFS** |

The original runs contained no NaN/infinite samples. Loudnorm alone did not
prevent AAC overshoot. The correction formats final output as 48 kHz stereo,
limits peaks with makeup gain disabled and latency compensated, and encodes AAC
at 192 kbit/s. A real decoded transient regression verifies headroom. Initial
Linux tests caught a channel-layout negotiation failure in the first correction;
the explicit stereo format resolved it and real Linux renders passed.
The corrected reaction output retains 24.433333 s / 733 frames / audio. This
objective check does not establish natural speech, absence of all artifacts or
full subtitle synchronization. The first multi-hour attempt uses the image it
started on; it is not relabeled as having this later audio correction.

## Source and license evidence

- Ukrainian: [Vira source and CC BY-SA 4.0 record](https://commons.wikimedia.org/wiki/File:WIKITONGUES-_Vira_speaking_Ukrainian.webm), Wikitongues / Kristen Tcherneshoff. Actual URL ingestion used [the linked video](https://www.youtube.com/watch?v=e_dh1q75LSo).
- Russian: [Amir source and CC BY-SA 4.0 record](https://commons.wikimedia.org/wiki/File:WIKITONGUES-_Amir_speaking_Russian_and_Hebrew.webm), Wikitongues / Bogreudell. Downloaded 38,613,211 bytes; SHA-256 `66ef68c22a0de477173ef44fc24e33ebd85a90530814825491476074583278ff`. A bounded first-90-second MP4 conversion was uploaded for processing.
- Gameplay: [VoxeLibre source and CC BY 3.0 record](https://commons.wikimedia.org/wiki/File:MineClone2_-_Release_0.84_-_The_Very_Nice_Release.webm). Downloaded 54,174,478 bytes; SHA-256 `0bc335ebea20dacf3deb95cfa17be42281cf6e5ca72a14c6238d55faf8f211b1`. Original music credit identifies Jordach; commentary replaced that soundtrack, and limited-speech output was explicitly silent.
- NASA: informational testing under [NASA media guidance](https://www.nasa.gov/nasa-brand-center/images-and-media/), with credit, no endorsement claim and no public publication. This is not a blanket license for third-party material shown by NASA.
- Multi-hour source provenance: the [official Webb launch video](https://www.youtube.com/watch?v=7nT7JGZMbtM) is also documented as a NASA/ESA production by [NASA Goddard's complete-broadcast record](https://svs.gsfc.nasa.gov/14060), which requests credit to NASA's Goddard Space Flight Center. [ESA's media terms](https://www.esa.int/terms-and-conditions/terms-and-conditions-for-images-and-videos) permit credited informational uses of its material and exclude blanket authorization for third-party rights. This acceptance test is private informational use; commercial reuse is not asserted.

No arbitrary stream was treated as authorized. Raw sources, transcripts, Google
identifiers and private artifact manifests remain ignored locally.
