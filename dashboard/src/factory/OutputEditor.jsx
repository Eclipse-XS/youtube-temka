import React, { useState } from "react";
export default function OutputEditor({
  job,
  output,
  index,
  act,
  post,
  onCreated,
}) {
  const [start, setStart] = useState(0),
    [end, setEnd] = useState(output.edit_duration || output.duration),
    [preset, setPreset] = useState(job.request.preset),
    [captions, setCaptions] = useState(job.request.captions),
    [hook, setHook] = useState(job.request.hook || ""),
    [style, setStyle] = useState(job.request.caption_style || "pop");
  if (!output.edit_source)
    return (
      <small>
        Цей старіший результат не має збереженого вихідного уривка. Для повного
        редагування повторно додайте джерело.
      </small>
    );
  return (
    <details>
      <summary>Редагувати збережений вихідний уривок</summary>
      <p>
        Діапазон від початку уривка. Оригінальний звук і відео будуть
        завантажені з Drive з перевіркою checksum.
      </p>
      <div className="grid">
        <label>
          Початок, сек
          <input
            type="number"
            min="0"
            max={end}
            step=".1"
            value={start}
            onChange={(e) => setStart(+e.target.value)}
          />
        </label>
        <label>
          Кінець, сек
          <input
            type="number"
            min={start}
            max={output.edit_duration || output.duration}
            step=".1"
            value={end}
            onChange={(e) => setEnd(+e.target.value)}
          />
        </label>
        <label>
          Монтаж
          <select value={preset} onChange={(e) => setPreset(e.target.value)}>
            {["auto", "smart", "blur", "gameplay", "crop"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          Субтитри
          <select value={style} onChange={(e) => setStyle(e.target.value)}>
            {["pop", "karaoke", "clean"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Opening hook
        <input
          value={hook}
          maxLength="120"
          onChange={(e) => setHook(e.target.value)}
        />
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={captions}
          onChange={(e) => setCaptions(e.target.checked)}
        />
        Субтитри
      </label>
      <button
        disabled={end <= start}
        onClick={() =>
          act(async () =>
            onCreated(
              await post("/jobs", {
                ...job.request,
                source: `edit:${job.id}:${index}`,
                start: 0,
                end: output.edit_duration || output.duration,
                intervals: [[start, end]],
                preset,
                captions,
                caption_style: style,
                hook,
                count: 1,
                publish_automatic: false,
                audio_mode: "original",
                tts_text: "",
              }),
            ),
          )
        }
      >
        Створити нову версію
      </button>
    </details>
  );
}
