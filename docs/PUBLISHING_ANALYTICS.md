# Automatic metadata, publishing and Analytics

Generation and Drive storage work without YouTube OAuth. New finished outputs
receive a publishing draft automatically. Older READY outputs offer **Create
metadata** in Editor/Publisher. No paid metadata API is used.

## Drafts and review

The existing local Ollama/Qwen model receives the selected clip's actual
transcript and source attribution. Titles and factual descriptions must quote
the selected evidence. An invalid answer receives one corrective retry, then an
extractive draft with a visible review warning. Translation always requires
review and never changes the claimed audio language.

Drafts include a title and two alternatives, description, tags, two to five
hashtags, category, audio/metadata languages and optional thumbnail text.
Category IDs are checked against assignable YouTube categories before insertion.
Descriptions enforce the 5000 UTF-8 byte budget, including source credit.

Editor shows transcript provenance and version history. A manual revision clears
approval and stops any queue item that has no remote session or video identity.
After an external effect, the publication's original metadata remains immutable.
Source transcripts, versions and Drive manifests survive local file cleanup.
Updating draft thumbnail text does not replace an already rendered JPEG; create
a new edited output to change that image. Review the saved JPEG before approval.

Technical checks decode video/audio, verify format/duration, measure waveform
clipping/silence and sample black frames. Editorial checks flag weak/heuristic
highlights, incomplete boundaries, contextual uncertainty and duplicate text.
These checks cannot establish human editorial quality. Review-first is the
default; channel auto-approval requires explicit consent and passing safeguards.

## One-time YouTube consent

Enable YouTube Data API in the owner's Google project. Create/download a
**Desktop app** OAuth client. Keep the JSON outside Git. Run on the host:

```powershell
.venv/Scripts/python.exe -m factory.youtube_oauth --client C:/private/client.json --output secrets/youtube/main.json --open-browser
```

The owner completes consent in the system browser. Existing credentials are never
overwritten. This requests `youtube.upload` and `youtube.readonly`; it performs
no upload. Mount the secrets directory read-only and use Publisher **Discover**.
See Google's [desktop OAuth guide](https://developers.google.com/identity/protocols/oauth2/native-app).

Approve an output in Editor, select the connected channel in Publisher, then
queue its generated metadata. Private is the default. Public/native scheduled
publishing requires explicit channel policy and an explicit queue/job request.
The calendar enforces local daily limits and UTC spacing. Observations from
Analytics never silently enable public publishing or change policy.

Interrupted transfers retain their resumable session. Returned video IDs are
saved before verification. If metadata has not propagated yet, **Check already
uploaded video** rechecks that same ID without any new insert. An uncertain
session without an ID requires Studio inspection; never create a replacement
publication merely to clear an uncertain result.

Thumbnails use sampled real frames ranked by sharpness, brightness and detected
faces; they do not generate scenes. A bounded JPEG is verified against its Drive
checksum before `thumbnails.set`. The background publisher waits for successful
video processing, including Shorts. Account/API rejection leaves `ASSET_ONLY`
and the JPEG on Drive; use Studio if that channel permits it. A thumbnail failure
does not change the video's upload success. See the current
[thumbnail API requirements](https://developers.google.com/youtube/v3/docs/thumbnails/set).

## Separate read-only Analytics consent

Enable YouTube Analytics API and YouTube Data API in the same project. Run a
separate consent and destination; do not replace the upload token:

```powershell
.venv/Scripts/python.exe -m factory.youtube_oauth --client C:/private/client.json --output secrets/analytics/main.json --analytics --open-browser
```

This requests only `youtube.readonly` and `yt-analytics.readonly`. In Analytics,
discover the channel, then sync. Container configuration mounts
`YOUTUBE_ANALYTICS_TOKEN_DIR=/run/secrets/analytics`. Background refresh is bounded
to six-hour intervals, or the operator can request a sync explicitly.

The dashboard shows actual sync progress, freshness, 30 daily reporting days,
up to 250 recent/known videos, period metrics and separate lifetime counters.
The reporting period ends two UTC days before sync to avoid presenting fresh
reporting delays as final results. Unsupported fields remain unavailable/null;
supported metrics survive an incompatible metric combination. Failed syncs keep
the last successful snapshot. Impressions, CTR and retention curves are not
fabricated from Data API statistics. See the available
[channel reports](https://developers.google.com/youtube/analytics/channel_reports).

Recommendations require at least 20 eligible videos with at least 30 views,
and at least five videos per compared group. They describe observed associations,
not causal effects or guaranteed reach. Sparse channels show `INSUFFICIENT_DATA`.

## Repeatable verification

Run `python -m pytest factory_tests -q` on Windows. The full retained-module suite
in `.github/workflows/ci.yml` runs on Linux because some tests require POSIX
permissions, bash and file locks. Build `factory.html` with
`npm run build -- --config vite.factory.config.js` in `dashboard/`.
The current report distinguishes live Google/Twitch checks from protocol fixtures.
Credentials, private video/Drive identities and raw runtime evidence are ignored
by Git; only sanitized aggregate evidence is published.
