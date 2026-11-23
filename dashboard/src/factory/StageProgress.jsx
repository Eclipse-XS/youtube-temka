import React, { useEffect, useState } from "react";
const stages = [
  ["source", "Source Analysis"],
  ["extraction", "Download / Extraction"],
  ["transcription", "Transcription"],
  ["language", "Language Detection"],
  ["highlights", "AI Highlight Selection"],
  ["signals", "Media Signal Scan"],
  ["hooks", "Hook Candidates"],
  ["retrieval", "Video Retrieval"],
  ["captions_audio", "Audio / Captions"],
  ["rendering", "Rendering"],
  ["validation", "Validation"],
  ["thumbnail", "Thumbnail"],
  ["metadata", "Metadata Generation"],
  ["editorial", "Editorial Validation"],
  ["drive", "Drive Upload / Verification"],
  ["approval", "Approval / Publishing"],
];
const stageLabels = Object.fromEntries(stages);
const pageSize = 100;

function OperationHistory({ job, api, terminal }) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  const [operations, setOperations] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    let stopped = false;
    let timer;
    async function load() {
      try {
        const result = await api(`/jobs/${job.id}/operations?limit=${pageSize}&offset=${page * pageSize}`);
        if (!stopped) {
          setOperations(result);
          setError("");
        }
      } catch (failure) {
        if (!stopped) setError(failure.message);
      } finally {
        if (!stopped && !terminal && page === 0) timer = setTimeout(load, 2500);
      }
    }
    load();
    return () => { stopped = true; clearTimeout(timer); };
  }, [api, job.id, open, page, terminal]);

  const sources = new Map();
  for (const operation of operations) {
    const source = operation.source_id;
    if (!sources.has(source)) sources.set(source, []);
    sources.get(source).push(operation);
  }

  return (
    <details onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>Операції за джерелами</summary>
      {error && <p className="error">{error}</p>}
      {operations.length === 0 && !error && <small>Операції ще не записані.</small>}
      {[...sources].map(([source, rows]) => (
        <details key={source} open={rows.some((row) => row.status === "running")}>
          <summary>{job.result.sources?.[source]?.metadata?.title || source || "Завдання"}</summary>
          <ul>
            {rows.map((row) => {
              const details = row.details || {};
              return (
                <li key={`${row.stage_id}/${row.operation_id}/${row.attempt}`}>
                  <span>{stageLabels[row.stage_id] || row.stage_id} · {row.operation_id} · спроба {row.attempt}</span>
                  <small>
                    {row.status} · {row.elapsed_seconds.toFixed(1)} с
                    {row.processed_units != null && row.total_units != null && ` · ${Math.floor(row.processed_units)} / ${Math.ceil(row.total_units)} ${row.unit_type || ""}`}
                    {details.model && ` · ${details.model}`}
                    {details.device && details.device !== "unknown" && ` · ${details.device}`}
                    {details.encoder && ` · ${details.encoder}`}
                    {details.eval_count != null && ` · ${details.eval_count} токенів`}
                    {details.eval_count == null && details.received_fragments > 0 && ` · ${details.received_fragments} фрагментів`}
                    {details.tokens_per_second != null && ` · ${details.tokens_per_second} токенів/с`}
                    {row.error_code && ` · ${row.error_code}`}
                  </small>
                  {details.retry_reason && <small>{details.retry_reason}</small>}
                </li>
              );
            })}
          </ul>
        </details>
      ))}
      {(page > 0 || operations.length === pageSize) && (
        <div>
          <button disabled={page === 0} onClick={() => setPage(page - 1)}>Новіші</button>
          <button disabled={operations.length < pageSize} onClick={() => setPage(page + 1)}>Старіші</button>
        </div>
      )}
    </details>
  );
}

export default function StageProgress({ job, api }) {
  const entries = Object.fromEntries((job.stages || []).map((s) => [s.key, s]));
  const terminal = ["READY", "FAILED", "BLOCKED", "CANCELLED"].includes(
    job.state,
  );
  const elapsed = Math.max(
    0,
    Math.floor(
      ((terminal ? job.seen || job.created : Date.now() / 1000) - job.created) /
        60,
    ),
  );
  if (!job.stages?.length && terminal)
    return (
      <small className="stage-panel">
        Архівне завдання · докладні етапи не записувалися цією версією
      </small>
    );
  return (
    <details
      className="stage-panel"
      open={!["READY", "CANCELLED"].includes(job.state)}
    >
      <summary>
        Етапи · {elapsed} хв · {job.result.outputs?.length || 0} готових кліпів
        · {job.worker || "черга"}
      </summary>
      <ol>
        {stages.map(([key, label]) => {
          const s = entries[key];
          const pct =
            s?.current != null && s.total > 0
              ? Math.min(100, Math.floor((s.current / s.total) * 100))
              : null;
          const status =
            key === "approval" && job.state === "READY"
              ? job.result.outputs?.every((o) => o.approved)
                ? "approved"
                : "awaiting review"
              : s?.status || "pending";
          return (
            <li key={key} className={"stage-" + status}>
              <span>{label}</span>
              <small>
                {status}
                {pct !== null ? ` · ${pct}%` : ""}
                {s?.unit && s.current != null
                  ? ` · ${Number(s.current).toFixed(0)} / ${s.total ?? "…"} ${s.unit}`
                  : ""}
              </small>
              {status === "running" &&
                (pct !== null ? (
                  <progress value={s.current} max={s.total} />
                ) : (
                  <progress />
                ))}
              {s?.message && <small>{s.message}</small>}
            </li>
          );
        })}
      </ol>
      <OperationHistory job={job} api={api} terminal={terminal} />
      {job.result.failure && <p>
        <code>{job.result.failure.code}</code> · {job.result.failure.stage}
        {job.result.failed_source_id && <> · {job.result.failed_source_id}</>}
      </p>}
      {job.result.retry_at && job.state==='QUEUED' && <p role="status">
        Повторна спроба після {new Date(job.result.retry_at*1000).toLocaleTimeString()}.
      </p>}
      {job.error && <p className="error">{job.error}</p>}
    </details>
  );
}
