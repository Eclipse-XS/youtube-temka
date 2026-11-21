# Editorial & Technical Review of Generated Video Outputs

This document records the technical and editorial evaluation of all video outputs produced during the unified Factory 8 + Factory 9 integration validation on `integration/factory-8-9-unified`.

---

## 1. Source Footage Fingerprints

| Local Filename / Container Path | SHA-256 | Duration | Resolution | FPS | Audio | Content Profile |
| --- | --- | --- | --- | --- | --- | --- |
| `a90eb6ae10bf426b9e60a14025428dc1.mp4` (`/data/uploads/a90eb6ae10bf426b9e60a14025428dc1.mp4`) | `1a66b8c9cdf61a1246bcb262ab9f85f01fe0a4216629fd92e41dec53ecb8aeb8` | `617.91s` (`10m 17.9s`) | `1280x720` | `30.0` | Stereo AAC `44.1 kHz` | GTA compilation with mixed streamer facecams, animal attacks, plane crash, and highway stunts |
| `qa-gta-721.mp4` (`/scratch/qa-gta-721.mp4`) | `ccad22b4e0b8d7fc1422f2639ef386ffb7aed28f52247c6a60ef00e254a0c22d` | `720.75s` (`12m 00.7s`) | `1280x720` | `30.0` | Stereo AAC `44.1 kHz` | GTA V mission & stunt footage (`0–344s` active gameplay; `344–720s` dark post-video screen/credits with music) |

---

## 2. Repaired Smart Highlights (`gta_repaired` vs Previous `gta`)

### 2.1 Root Cause of Previous Early GTA Highlight Failures

In the earlier baseline run (`job_id = 3a6e62ae3dbf4a2d8e24d2ee3b2a6291`, exported to `%LOCALAPPDATA%\Factory89-unified\exports\gta`), `clip-1.mp4` (`99.0–115.5s`) and `clip-2.mp4` (`120.0–140.5s`) contained abrupt mid-clip scene jumps:
1. **`99.0–115.5s` (`Shot 19 -> Shot 20` cut at `111.0s`)**:
   - `95.0–111.0s` shows a GTA mountain-road tiger attack with a two-person couch webcam overlay in the `bottom_right` corner (both people turned in side profile toward the screen).
   - At `111.0s`, the source compilation cuts to an unrelated clip of a red sports car driving away without a webcam (`111.0–120.0s`).
   - Because the single frontal Haar cascade missed the side-profile faces in `Shot 19`, `corner_face_presence["bottom_right"]` was `0.0` on both shots, and the 4-corner averaged HUD L1 similarity (`0.81`) allowed the continuity scorer to merge `Shot 19` and `Shot 20`.
2. **`120.0–140.5s` (`Shot 26 -> Shot 27` cut at `127.0s`)**:
   - `120.0–127.0s` shows a daytime bridge stunt with streamer xQc's webcam in `bottom_left`.
   - At `127.0s`, the source compilation cuts to a nighttime police shootout without a webcam (`127.0–140.5s`).
   - Although `bottom_left` face presence dropped from `0.5` to `0.0`, the heuristic score remained inside the uncertain VLM edge-verification band (`0.38 <= score <= 0.72`), and `qwen3-vl:2b-instruct` falsely joined the pair as *"two shots of a nighttime urban environment"*.

### 2.2 Repair Verification (`job_id = 7781118af0794efab72ddfb3f1669fe5`)

With multi-cascade corner webcam detection (`haarcascade_frontalface_default`, `haarcascade_frontalface_alt2`, and `haarcascade_profileface` + horizontal flip at `1.5s` intervals) and the hard `facecam_contradiction` continuity barrier in `factory/semantic_events.py`:
- `Shot 19` (`95.0–111.0s`) is now isolated as `event_9` (`corner_face_presence["bottom_right"] = 0.636`), cleanly separated from `Shot 20` (`event_10`, `111.0–120.0s`, `bottom_right = 0.0`) with reason `"Facecam layout changed across shots (bottom_right)"`.
- `Shot 26` (`120.0–127.0s`) is isolated as `event_11` (`corner_face_presence["bottom_left"] = 0.80`), cleanly separated from `Shot 27` (`event_12`, `127.0–140.5s`, `bottom_left = 0.0`) with reason `"Facecam layout changed across shots (bottom_left)"`.

#### Exported Repaired Smart Highlights (`%LOCALAPPDATA%\Factory89-unified\exports\gta_repaired`)

| File | Window | Duration | Resolution / FPS | Integrated Loudness / True Peak | Editorial Coherence Assessment |
| --- | --- | --- | --- | --- | --- |
| `clip-1.mp4` | `95.0s – 111.0s` | `16.00s` (`480` frames) | `1080x1920` @ `30 fps` (`h264` / `aac`) | `-14.4 LUFS` / `-1.0 dBTP` | **Coherent Single Event**: Full tiger encounter on the dirt road from initial reaction (`"Oh my god, a tiger!"`) through the attack and vehicle escape, ending exactly at the `111.0s` compilation cut before the red car clip. |
| `clip-2.mp4` | `30.5s – 47.0s` | `16.50s` (`495` frames) | `1080x1920` @ `30 fps` (`h264` / `aac`) | `-14.3 LUFS` / `-1.0 dBTP` | **Coherent Single Event**: Continuous alligator ambush sequence in the swamp (`30.5–47.0s`) with consistent streamer overlay and complete action-payoff arc. |

---

## 3. Real AI-Verified Story Outputs (`ai_story_p1` & `ai_story_p3`)

Two real multi-part `AI-Verified Story` jobs were processed end-to-end through `qwen3-vl:2b-instruct` verification, editorial approval, and FFmpeg vertical rendering (`1080x1920`, `30 fps`).

### 3.1 Job `c8f4a90f77164f8a85b9c3996475bcfa` (`P1` Bridge Jump & Water Impact Story)

- **Source**: `a90eb6ae10bf426b9e60a14025428dc1.mp4` (`412.0s – 445.0s`, total story span `33.0s`)
- **AI Story Verdict**: `VERIFIED_COHERENT` (`confidence = 0.90`, 2-pass 8-frame adaptive inspection)
- **Narrative Beats Grounded in Visual Panels & Audio**:
  - *Setup*: `"white vehicle driving down a bridge road"`
  - *Development*: `"white vehicle colliding with a red truck on the bridge"`
  - *Climax*: `"white vehicle airborne after launching off a bridge"`
  - *Payoff*: `"Wait until the end. Wait, wait, wait! / white vehicle submerged in water"`
- **Export Directory**: `%LOCALAPPDATA%\Factory89-unified\exports\ai_story_p1`

| Part | File | Source Window | Overlap | Duration | Resolution / FPS | Loudness / Peak | Editorial Assessment |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Part 1 | `clip-1.mp4` | `412.0s – 429.5s` | — | `17.50s` (`525` frames) | `1080x1920` @ `30 fps` | `-14.2 LUFS` / `-1.3 dBTP` | Shows the white off-road truck accelerating onto the bridge, swerving into the red truck, and launching over the bridge railing (cliffhanger midpoint). |
| Part 2 | `clip-2.mp4` | `427.5s – 445.0s` | `2.0s` (`427.5–429.5s`) | `17.50s` (`525` frames) | `1080x1920` @ `30 fps` | `-13.3 LUFS` / `-1.2 dBTP` | Recaps the bridge launch (`2.0s` overlap), follows the airborne descent and explosion/splash into the river below, and captures the streamer's payoff reaction. |

### 3.2 Job `383316f996ca4cf7848d0ea7f0908840` (`P3` Highway Truck Swap Story)

- **Source**: `a90eb6ae10bf426b9e60a14025428dc1.mp4` (`545.67s – 589.0s`, total story span `43.33s`)
- **AI Story Verdict**: `VERIFIED_COHERENT` (`confidence = 0.88`, 2-pass 8-frame adaptive inspection)
- **Narrative Beats Grounded in Visual Panels & Audio**:
  - *Setup*: `"character standing on the roof of a red semi-truck moving down a highway"`
  - *Development*: `"character jumping from a red truck onto a blue flatbed truck on a highway"`
  - *Climax*: `"character landing on the blue flatbed truck while driving down the highway"`
  - *Payoff*: `"character driving a red vehicle down a highway with a person in a yellow top in the bottom left corner"`
- **Export Directory**: `%LOCALAPPDATA%\Factory89-unified\exports\ai_story_p3`

| Part | File | Source Window | Overlap | Duration | Resolution / FPS | Loudness / Peak | Editorial Assessment |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Part 1 | `clip-1.mp4` | `545.67s – 568.83s` | — | `23.17s` (`695` frames) | `1080x1920` @ `30 fps` | `-19.1 LUFS` / `-1.5 dBTP` | Establishes the player climbing atop the moving red semi-truck cab on the highway and timing the jump toward the adjacent flatbed truck. |
| Part 2 | `clip-2.mp4` | `565.83s – 589.00s` | `3.0s` (`565.83–568.83s`) | `23.17s` (`695` frames) | `1080x1920` @ `30 fps` | `-15.6 LUFS` / `-1.5 dBTP` | Recaps the mid-air jump (`3.0s` overlap), completes the landing on the blue flatbed truck, and finishes the highway stunt sequence cleanly before the end card. |

---

## 4. Multi-Source Long-Form Compilation (`compilation_longform`)

### 4.1 Job `0d65a6ed4849425dbcb2e28087db6839`

- **Workflow**: `Longs Compilation` (`workflow_mode = compilation`, `editorial_Format = longs_16_9`, `target_duration_sec = 600`)
- **Sources Combined**:
  - `src_1`: `a90eb6ae10bf426b9e60a14025428dc1.mp4` (`617.91s`)
  - `src_2`: `qa-gta-721.mp4` (`720.75s`)
- **Segment Curation & Edit Plan**:
  - Selected **20 coherent, non-overlapping action/dialogue segments** (`14` from `src_1`, `6` from `src_2`) after excluding title/intro cards (`0–28s`), end cards (`598–618s`), and the static post-video dark screen/credits region (`344–720s` in `src_2`).
  - Tested manual editorial operations on the unified edit plan:
    - Segment reordering (`seg_02` and `seg_01` swapped at the opening).
    - Segment trimming (`0.25s` trim on `seg_02`).
    - Per-segment transitions (`fade` transitions applied across source boundaries and chapter breaks).
    - Optimistic concurrency control: verified that submitting a stale `plan_revision` (`revision 1` after advancing to `revision 2`) is rejected with `HTTP 409 Conflict`, and approved `plan_revision = 3`.
- **Technical QA Metrics (`%LOCALAPPDATA%\Factory89-unified\exports\compilation_longform\long.mp4`)**:
  - **Duration**: `392.622722s` (**6 minutes 32.62 seconds**, `11,778` frames)
  - **Resolution & Aspect Ratio**: `1280x720` (`16:9` progressive)
  - **Frame Rate**: `30.0 fps` (`r_frame_rate = 30/1`, `avg_frame_rate = 30/1`)
  - **Codecs**: `h264 (High)` video (`2,487 kbps`), `aac (LC)` stereo audio (`48 kHz`, `189 kbps`)
  - **Audio Loudness**: Integrated `-14.8 LUFS`, True Peak `-0.2 dBTP`, LRA `8.9 LU` (right on the `-14 LUFS` YouTube long-form target)
  - **Timeline Manifest**: Exported alongside the master video at `%LOCALAPPDATA%\Factory89-unified\exports\compilation_longform\timeline.json` (`plan_revision = 3`, `duration_shortfall = true` honestly flagged against the `600s` target because the remaining raw footage in `src_2` after `344s` consists of non-editorial dark end-screen audio).

---

## 5. Honest Assessment of Remaining Editorial Weaknesses

While the technical defects (`AI-Verified Story` false rejections and `Smart Highlights` webcam-cut merges) are resolved and verified on real media, the following editorial limitations remain inherent to a `2B` local vision model on 4 GB VRAM:

1. **Fine-Grained Gameplay Semantics in `qwen3-vl:2b-instruct`**:
   - The `2B` parameter model reliably identifies vehicles, road environments, crashes, water splashes, character positions, and text/title cards, which is sufficient for 4-panel + 4-panel temporal progression verification.
   - However, it occasionally simplifies complex game physics (for example, describing a truck cabin roof ride as `"character standing on the roof of a red semi-truck"` in panel 1 and `"driving a red vehicle"` in panel 4 when the camera returns to standard third-person driving view).
2. **Dark Interior Scenes vs Low-Luma Menus**:
   - Nighttime car-interior dialogue scenes (`186–205s` in `qa-gta-721.mp4`) have very low mean luminance (`mean_luma ~ 33–38`) and low global motion (`peak_motion ~ 0.021–0.025`), sitting close to static pause/menu screens (`peak_motion <= 0.018` or `static_fraction >= 0.88`). The refined threshold separates them accurately on the benchmarked GTA clips, but ultra-dark stealth gameplay with almost zero camera movement may still require manual review (`PLAUSIBLE_NEEDS_REVIEW`).
3. **Human Editorial Sign-Off Requirement**:
   - In accordance with project governance, automated technical and VLM verification authorizes `AI_STORY_VERIFIED` and `PENDING_HUMAN_EDITORIAL_APPROVAL`, while final `EDITORIALLY_APPROVED` status for public channel publishing remains reserved for the human operator in the Selection Review / Editor UI.
