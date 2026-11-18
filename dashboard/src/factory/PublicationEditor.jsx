import React, { useState } from "react";

export default function PublicationEditor({ publication, api, act, refresh }) {
  const [title, setTitle] = useState(publication.metadata.snippet.title);
  const [description, setDescription] = useState(
    publication.metadata.snippet.description || "",
  );
  const [privacy, setPrivacy] = useState(
    publication.metadata.status.privacyStatus,
  );
  const [when, setWhen] = useState(() => {
    const value = publication.metadata.status.publishAt;
    if (!value) return "";
    const date = new Date(value);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16);
  });
  return (
    <details>
      <summary>Редагувати перед завантаженням</summary>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          act(async () => {
            await api("/publisher/" + publication.id, {
              method: "PATCH",
              body: JSON.stringify({
                title,
                description,
                privacy,
                publish_at: when ? new Date(when).toISOString() : null,
              }),
            });
            await refresh();
          });
        }}
      >
        {publication.metadata.strict_metadata && (
          <p>
            Назву й опис змінюйте в редакторі метаданих із повторним схваленням
            версії.
          </p>
        )}
        <label>
          Назва
          <input
            required
            readOnly={!!publication.metadata.strict_metadata}
            maxLength={100}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label>
          Опис
          <textarea
            readOnly={!!publication.metadata.strict_metadata}
            maxLength={5000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <label>
          Видимість
          <select value={privacy} onChange={(e) => setPrivacy(e.target.value)}>
            <option value="private">Приватне</option>
            <option value="unlisted">За посиланням</option>
            <option value="public">Публічне</option>
          </select>
        </label>
        <label>
          Час публікації (місцевий)
          <input
            type="datetime-local"
            value={when}
            onChange={(e) => setWhen(e.target.value)}
          />
        </label>
        <p className="muted">
          Запланована публікація потребує дозволу каналу. Порожній час залишає
          вибрану видимість. Збереження повертає завдання до черги.
        </p>
        <button type="submit">Зберегти й поставити в чергу</button>
      </form>
    </details>
  );
}
