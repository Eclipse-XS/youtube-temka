import React, { useState } from "react";
export default function VoiceSettings({ settings, post, act }) {
  const [voice, setVoice] = useState("af_heart"),
    [sample, setSample] = useState("");
  const tts = settings?.tts;
  return (
    <section>
      <h2>Необов’язковий AI Voice-over</h2>
      <p>
        Оригінальне мовлення — типовий режим. Kokoro: природні голоси EN / ES на
        CPU, окремий процес.
      </p>
      <p>{tts?.ready && tts?.runtime ? "Готовий" : tts?.setup_instruction}</p>
      <label>
        Голос
        <select
          value={voice}
          onChange={(e) => {
            setVoice(e.target.value);
            setSample("");
          }}
        >
          {Object.entries(tts?.voices || {}).map(([v, lang]) => (
            <option key={v} value={v}>
              {v} · {lang.toUpperCase()}
            </option>
          ))}
        </select>
      </label>
      <button
        disabled={!tts?.runtime || tts?.progress?.state === "DOWNLOADING"}
        onClick={() => act(() => post("/tts/setup"))}
      >
        Завантажити голосову модель
      </button>
      <button
        disabled={!tts?.runtime || !tts?.ready}
        onClick={() =>
          act(async () =>
            setSample((await post("/tts/preview", { voice })).url),
          )
        }
      >
        Послухати голос
      </button>
      {sample && <audio controls autoPlay src={sample} />}
      <p>
        {tts?.progress?.state} {tts?.progress?.asset}{" "}
        {tts?.progress?.current
          ? `${Math.round(tts.progress.current / 1024 ** 2)} MB`
          : ""}{" "}
        {tts?.progress?.error}
      </p>
      <small>
        Runtime MIT · weights Apache-2.0 · optional phonemizer/eSpeak worker
        GPL-3.0. RU/UK narration unavailable; original audio and multilingual
        captions remain supported.
      </small>
    </section>
  );
}
