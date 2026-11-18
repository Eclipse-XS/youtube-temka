import React, { useEffect, useState } from "react";
const categories = {
  1: "Film & Animation",
  2: "Autos & Vehicles",
  10: "Music",
  15: "Pets & Animals",
  17: "Sports",
  19: "Travel & Events",
  20: "Gaming",
  22: "People & Blogs",
  23: "Comedy",
  24: "Entertainment",
  25: "News & Politics",
  26: "Howto & Style",
  27: "Education",
  28: "Science & Technology",
  29: "Nonprofits & Activism",
};
export default function MetadataEditor({
  job,
  output,
  index,
  api,
  post,
  act,
  onSaved,
}) {
  const metadata = output.publishing_metadata;
  const [title, setTitle] = useState(""),
    [description, setDescription] = useState(""),
    [tags, setTags] = useState(""),
    [hashtags, setHashtags] = useState(""),
    [category, setCategory] = useState("22"),
    [language, setLanguage] = useState("und"),
    [thumbnail, setThumbnail] = useState(""),
    [history, setHistory] = useState(null),
    [saving, setSaving] = useState(false);
  useEffect(() => {
    if (metadata) {
      setTitle(metadata.title);
      setDescription(metadata.description);
      setTags(metadata.tags.join(", "));
      setHashtags(metadata.hashtags.join(" "));
      setCategory(metadata.category_id);
      setLanguage(metadata.metadata_language);
      setThumbnail(metadata.thumbnail_text || "");
    }
  }, [metadata?.version]);
  const run = async (fn) => {
    setSaving(true);
    try {
      await act(fn);
    } finally {
      setSaving(false);
    }
  };
  const editorial = output.editorial;
  if (!metadata)
    return (
      <section>
        <h3>Публікаційна чернетка</h3>
        <p>
          Для цього старішого результату метадані ще не створено. Відео
          збережене незалежно від YouTube-авторизації.
        </p>
        <button
          disabled={saving || job.state !== "READY"}
          onClick={() =>
            run(async () => {
              await post(`/jobs/${job.id}/metadata`);
              await onSaved();
            })
          }
        >
          Створити метадані автоматично
        </button>
      </section>
    );
  return (
    <section className="metadata-editor">
      <h3>Публікаційна чернетка</h3>
      <p>
        {editorial?.status || "READY_FOR_REVIEW"} ·{" "}
        {metadata.provenance?.method === "ollama"
          ? "Локальна AI-модель"
          : "Відбір із тексту · потрібен перегляд"}{" "}
        · мова аудіо: {metadata.audio_language || "без мовлення"}
      </p>
      {(editorial?.issues?.length > 0 ||
        metadata.validation_issues?.length > 0) && (
        <div className="warning">
          <b>Перевірте зміст перед публікацією</b>
          <ul>
            {[
              ...new Set([
                ...(editorial?.issues || []),
                ...(metadata.validation_issues || []),
              ]),
            ].map((issue) => (
              <li key={issue}>{issue.replaceAll("_", " ")}</li>
            ))}
          </ul>
        </div>
      )}
      {editorial?.technical_issues?.length > 0 && (
        <p className="error">{editorial.technical_issues.join("; ")}</p>
      )}
      <label>
        Варіанти назви
        <select value="" onChange={(e) => setTitle(e.target.value)}>
          <option value="">Обрати варіант</option>
          {[metadata.title, ...metadata.alternative_titles].map((v, i) => (
            <option key={i} value={v}>
              {v}
            </option>
          ))}
        </select>
      </label>
      <label>
        Назва
        <input
          maxLength="100"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </label>
      <label>
        Опис
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <small>
          {new TextEncoder().encode(description).length} / 5000 UTF-8 bytes
        </small>
      </label>
      <label>
        Теги YouTube · через кому
        <input value={tags} onChange={(e) => setTags(e.target.value)} />
      </label>
      <label>
        Хештеги опису
        <input value={hashtags} onChange={(e) => setHashtags(e.target.value)} />
      </label>
      <div className="grid">
        <label>
          Категорія
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {Object.entries(categories).map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Мова метаданих
          <input
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            placeholder="uk / en / es"
          />
        </label>
      </div>
      <label>
        Текст мініатюри
        <input
          value={thumbnail}
          maxLength="60"
          onChange={(e) => setThumbnail(e.target.value)}
        />
      </label>
      <p className="muted">
        Авторство зберігається автоматично. Зміна чернетки скасовує попереднє
        схвалення. Мова метаданих не змінює оригінальний голос.
      </p>
      <button
        disabled={saving || job.state !== "READY"}
        onClick={() =>
          run(async () => {
            await api(`/jobs/${job.id}/outputs/${index}/metadata`, {
              method: "PATCH",
              body: JSON.stringify({
                title,
                description,
                tags: tags
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
                hashtags: hashtags.split(/\s+/).filter(Boolean),
                category_id: category,
                metadata_language: language,
                thumbnail_text: thumbnail,
              }),
            });
            await onSaved();
          })
        }
      >
        Зберегти нову версію
      </button>
      <button
        disabled={saving || job.state !== "READY"}
        onClick={() =>
          run(async () => {
            await post(`/jobs/${job.id}/metadata`);
            await onSaved();
          })
        }
      >
        Повторити AI-генерацію
      </button>
      <button
        onClick={() =>
          run(async () =>
            setHistory(
              await api(`/jobs/${job.id}/outputs/${index}/metadata/history`),
            ),
          )
        }
      >
        Походження та історія
      </button>
      {history && (
        <details open>
          <summary>Версії: {history.length}</summary>
          {history.map((h) => (
            <div key={h.version}>
              <p>
                {new Date(h.created * 1000).toLocaleString()} ·{" "}
                {h.manual ? "Ручна правка" : h.metadata.provenance?.method} ·{" "}
                {h.metadata.title}
              </p>
              <details>
                <summary>Фактичний текст вибраного уривка</summary>
                <p>
                  {h.provenance?.input?.transcript ||
                    "Доказ тексту недоступний для цієї старішої версії."}
                </p>
              </details>
            </div>
          ))}
        </details>
      )}
    </section>
  );
}
