# Factory 10 implementation milestone

## Job telemetry and recovery

Existing SQLite job and stage records remain readable. The additive
`job_operations` table records source, stage, operation, lease attempt, wall
time, units, model fields and errors. Lease expiry and operator cancellation
close running records while preserving completed work. The controller exposes
paginated details at `GET /api/jobs/{job_id}/operations` and the dashboard loads
them when the operator expands the operation history.

Ollama generation streams during Factory processing and collects a complete
response for existing callers to validate. Ollama's terminal records supply
token counts and timing. The running UI displays received fragments, whose
count can differ from the eventual token count. Placement comes from Ollama's
loaded-model inventory when available. CPU fallback and exhausted budgets have
separate operation records. Reservations count context size, output token
limits, requests and observed elapsed time, including previous leases. The
blocking HTTP client can still wait for its read timeout when the model stops
sending events.

## Sources and media

Compilation extra inputs have independent range controls, stable identifiers,
priority, contribution caps and excluded intervals. Exclusion affects selected
and manually revised output segments. The scanner still samples the selected
source range, including excluded intervals. Preflight estimates work from
the underlying range, audio availability and job settings. Local previews use
the existing source endpoint. Remote clips use the source page for review.

The local compilation path seeks and normalizes the requested range in one
encode. Network sources retain the bounded retrieval path. Normalization uses
the common encoder selector. A completed render is reusable without another
full decode when its content hash and validation profile match. Fresh final
media still goes through stream, duration, decode and synchronization checks.

## Gameplay workflow

Select **Gameplay Only** in Highlights or Longs Compilation. The scanner
covers the chosen time range in bounded windows at 1, 2 or 4 grayscale frames
per second, with aligned audio-energy bins when sound is available. Ranking
scores visual change against nearby activity, discounts possible cuts and
records follow-through and low-signal proposals. Coordinates are relative to
the selected range unless a field explicitly refers to source frame times.
Gameplay discovery precedes speech analysis. The worker transcribes selected
clips when captions or transcript-derived narration need it.

For optional local vision review, enter an already installed Ollama vision
model. The review supplies three low-resolution frames for each bounded
request. A schema check rejects invalid frame references and nonchronological
payoffs. Model categories and payoff estimates remain hypotheses requiring
operator review. Each model's availability and safe offload depend on its
installed model and host configuration.

## Output styling and timeline

Hooks retain timing, pinning, position offsets, opacity, padding and optional
exact line breaks in the stored job request. New caption styles use different
word grouping, colors, casing, backgrounds and effects in the shared ASS
renderer. Edits on retained sources can reuse the original timed transcript
when the source alignment and ASR settings match. Older exports without a
retained per-output transcript may still require ASR.

The worker compiles a persisted timeline before retrieving and rendering its
scenes. The timeline includes stable event identities, source and output
intervals, scene dependencies and revision metadata. Editing an event changes
the compiled video, audio or caption filters. The same decisions feed the
draft proxy and final export. Approved local revisions can be replayed.

The gameplay planner retains source provenance and visible evidence for beats.
Procedural branding, timed effects, audio overlap, and manually versioned
captions are rendered into the MP4. Cross-job caching on the same volume reuses
eligible analysis and rendered scenes. A reproducibility file records source
checksums where available, the compiled revision, encoder, validation and
sampled resources.
