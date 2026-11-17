import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  Film,
  FolderOpen,
  ListVideo,
  Plus,
  Settings,
  Upload,
  Scissors,
} from "lucide-react";
import "./factory.css";

async function api(path, options = {}) {
  const response = await fetch("/api" + path, {
    ...options,
    headers:
      options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" },
  });
  const body = response.headers.get('content-type')?.includes('application/json')
    ? await response.json()
    : {detail:'Контролер тимчасово недоступний. Перевірте стан контейнерів і повторіть дію.'};
  if (!response.ok)
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : JSON.stringify(body.detail),
    );
  return body;
}
const post = (path, body = {}) =>
  api(path, { method: "POST", body: JSON.stringify(body) });
const pages = [
  ["Dashboard", Activity],
  ["Create", Plus],
  ["Jobs", ListVideo],
  ["Editor", Scissors],
  ["Library", FolderOpen],
  ["Publisher", Upload],
  ["Settings", Settings],
];
const defaults = {
  source: "",
  rights_confirmed: false,
  mode: "shorts",
  resolution: 720,
  start: 0,
  end: 1800,
  count: 5,
  minimum: 20,
  maximum: 60,
  preset: "blur",
  background: null,
  language: null,
  captions: true,
  save_drive: true,
  intervals: [],
};

function PublisherPanel({ outputs, settings, act }) {
  const [data, setData] = useState({ channels: [], publications: [] }),
    [channel, setChannel] = useState(""),
    [output, setOutput] = useState(""),
    [title, setTitle] = useState(""),
    [description, setDescription] = useState(""),
    [privacy, setPrivacy] = useState("private"),
    [when, setWhen] = useState(""),
    [daily, setDaily] = useState(3),
    [automatic, setAutomatic] = useState(false),
    [cadence, setCadence] = useState(120),
    [allowPublic, setAllowPublic] = useState(false);
  const refresh = async () => setData(await api("/publisher"));
  useEffect(() => {
    refresh().catch(() => {});
    const interval = setInterval(() => refresh().catch(() => {}), 3000);
    return () => clearInterval(interval);
  }, []);
  const eligible = outputs.filter(
    (o) => o.approved && o.job.result.cloud_verified,
  );
  const current = eligible.find((o) => o.job.id + ":" + o.index === output);
  const policy = data.channels.find((c) => c.id === channel);
  return (
    <>
      <section>
        <h2>Підключені YouTube-канали</h2>
        <p>{settings?.publishing.reason}</p>
        <button
          onClick={() =>
            act(async () => {
              const result = await post("/publisher/discover");
              await refresh();
              if (result.errors.length)
                throw new Error(
                  result.errors.map((e) => e.alias + ": " + e.error).join("; "),
                );
            })
          }
        >
          Перевірити OAuth і знайти канали
        </button>
        <label>
          Канал
          <select
            value={channel}
            onChange={(e) => {
              setChannel(e.target.value);
              const p = data.channels.find((c) => c.id === e.target.value);
              setDaily(p?.daily_limit || 3);
              setAllowPublic(!!p?.public_allowed);
              setAutomatic(!!p?.automatic);
              setCadence(p?.interval_minutes || 120);
            }}
          >
            <option value="">Виберіть авторизований канал</option>
            {data.channels.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
        </label>
        {policy && (
          <>
            <label>
              Ліміт завантажень на добу
              <input
                type="number"
                min="1"
                max="20"
                value={daily}
                onChange={(e) => setDaily(+e.target.value)}
              />
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={allowPublic}
                onChange={(e) => setAllowPublic(e.target.checked)}
              />
              Я явно дозволяю публічні та заплановані публікації на цьому каналі
            </label>
            <button
              onClick={() =>
                act(async () => {
                  await post("/publisher/channels/" + channel + "/policy", {
                    daily_limit: daily,
                    public_allowed: allowPublic,
                    automatic,
                    interval_minutes: cadence,
                  });
                  await refresh();
                })
              }
            >
              Зберегти політику каналу
            </button>
            <label className="check">
              <input
                type="checkbox"
                checked={automatic}
                onChange={(e) => setAutomatic(e.target.checked)}
              />
              Я явно вмикаю автоматичну чергу для нових завдань цього каналу
            </label>
            <label>
              Інтервал автоматичних релізів, хвилини
              <input
                type="number"
                min="30"
                max="1440"
                value={cadence}
                onChange={(e) => setCadence(+e.target.value)}
              />
            </label>
            <small>
              Автоматичний режим призначає майбутні слоти щонайменше через 2
              години з урахуванням інтервалу та добового ліміту.
            </small>
          </>
        )}
      </section>
      <section>
        <h2>Review before publication</h2>
        <p>
          До черги потрапляють схвалені відео з перевіреною копією в Drive. За
          замовчуванням YouTube-відео буде приватним.
        </p>
        <label>
          Схвалене відео
          <select
            value={output}
            onChange={(e) => {
              setOutput(e.target.value);
              const o = eligible.find(
                (o) => o.job.id + ":" + o.index === e.target.value,
              );
              setTitle((o?.title || "").slice(0, 100));
            }}
          >
            <option value="">Виберіть відео</option>
            {eligible.map((o) => (
              <option key={o.job.id + o.name} value={o.job.id + ":" + o.index}>
                {o.title}
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
          Опис / хештеги
          <textarea
            maxLength="5000"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <div className="grid">
          <label>
            Видимість
            <select
              value={privacy}
              onChange={(e) => setPrivacy(e.target.value)}
            >
              <option value="private">Private</option>
              <option value="unlisted">Unlisted</option>
              <option value="public" disabled={!policy?.public_allowed}>
                Public
              </option>
            </select>
          </label>
          <label>
            Публічний реліз за місцевим часом
            <input
              type="datetime-local"
              disabled={!policy?.public_allowed}
              value={when}
              onChange={(e) => setWhen(e.target.value)}
            />
          </label>
        </div>
        <button
          className="primary"
          disabled={!current || !policy || !title}
          onClick={() =>
            act(async () => {
              await post("/publisher/queue", {
                job: current.job.id,
                output: current.index,
                channel,
                title,
                description,
                privacy,
                publish_at: when ? new Date(when).toISOString() : null,
              });
              await refresh();
            })
          }
        >
          Додати до черги YouTube
        </button>
      </section>
      <h2>Черга та історія</h2>
      {data.publications.map((p) => (
        <section key={p.id}>
          <b>{p.metadata.snippet.title}</b>
          <p>
            {p.state} ·{" "}
            {p.metadata.status.publishAt || p.metadata.status.privacyStatus}
          </p>
          {p.total > 0 && (
            <>
              <progress max={p.total} value={p.current} />
              <small>
                {p.current.toLocaleString()} / {p.total.toLocaleString()} bytes
              </small>
            </>
          )}
          {p.error && <p className="error">{p.error}</p>}
          {p.video_id && (
            <a
              target="_blank"
              rel="noreferrer"
              href={"https://www.youtube.com/watch?v=" + p.video_id}
            >
              YouTube
            </a>
          )}
          {p.state === "FAILED" && (
            <button
              onClick={() =>
                act(async () => {
                  await post("/publisher/" + p.id + "/retry");
                  await refresh();
                })
              }
            >
              Продовжити збережену сесію
            </button>
          )}
          {p.state === "UNCERTAIN" && (
            <p className="warning">
              Перевірте YouTube Studio перед новим завантаженням. Автоматичний
              повтор заблоковано.
            </p>
          )}
        </section>
      ))}
    </>
  );
}

function ModelConfiguration({ settings, act }) {
  const [ollama, setOllama] = useState(settings?.ollama_model || "qwen2.5:3b");
  const [whisper, setWhisper] = useState(settings?.whisper_model || "small");
  return (
    <>
      <div className="grid">
        <label>
          Модель Ollama
          <input value={ollama} onChange={(e) => setOllama(e.target.value)} />
        </label>
        <label>
          Модель Whisper
          <select value={whisper} onChange={(e) => setWhisper(e.target.value)}>
            {[
              "tiny",
              "base",
              "small",
              "medium",
              "large-v3",
              "large-v3-turbo",
            ].map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
        </label>
      </div>
      <button
        onClick={() =>
          act(() =>
            post("/settings/models", {
              ollama_model: ollama,
              whisper_model: whisper,
            }),
          )
        }
      >
        Зберегти вибір моделей
      </button>
      <p className="muted">
        Для 4 GB VRAM рекомендовано small/int8 або CPU. Великі моделі потребують
        додаткової RAM. Зміна застосовується до нових завдань.
      </p>
    </>
  );
}

function JobEvents({job}){
  const [open,setOpen]=useState(false),[events,setEvents]=useState([]);
  useEffect(()=>{if(open)api('/jobs/'+job.id+'/events').then(setEvents).catch(()=>{})},[open,job.id,job.state]);
  return <details onToggle={e=>setOpen(e.currentTarget.open)}><summary>Етапи та помилки</summary>{events.map((event,i)=><p key={i}><small>{new Date(event.at*1000).toLocaleString()} · {event.state}</small>{event.message}</p>)}</details>
}

function App() {
  const [page, setPage] = useState("Dashboard"),
    [jobs, setJobs] = useState([]),
    [settings, setSettings] = useState(null),
    [backgrounds, setBackgrounds] = useState([]);
  const [auth, setAuth] = useState(false),
    [token, setToken] = useState(""),
    [error, setError] = useState(""),
    [connectionError,setConnectionError]=useState(''),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const [form, setForm] = useState(defaults),
    [metadata, setMetadata] = useState(null),
    [selected, setSelected] = useState(null),
    [edits, setEdits] = useState({});
  const [longIntervals, setLongIntervals] = useState("");
  const [libraryQuery, setLibraryQuery] = useState("");
  const [libraryMode, setLibraryMode] = useState("all");
  const act = async (fn) => {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      return await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const refresh = async () => {
    const [j, s, b] = await Promise.all([
      api("/jobs"),
      api("/settings"),
      api("/backgrounds"),
    ]);
    setJobs(j);
    setSettings(s);
    setBackgrounds(b);
    setAuth(true);
    setConnectionError('');
  };
  useEffect(() => {
    refresh().catch(() => setAuth(false));
  }, []);
  useEffect(() => {
    if (!auth) return;
    const interval = setInterval(
      () => refresh().catch((e) => setConnectionError(e.message)),
      3000,
    );
    return () => clearInterval(interval);
  }, [auth]);
  const field = (name, value) => setForm((f) => ({ ...f, [name]: value }));
  const active = jobs.filter(
    (j) => !["READY", "FAILED", "BLOCKED", "CANCELLED"].includes(j.state),
  );
  const ready = jobs.filter((j) => j.state === "READY");
  const chosen = jobs.find((j) => j.id === selected) || ready[0] || jobs[0];
  const outputs = jobs.flatMap((j) =>
    (j.result.outputs || []).map((o, i) => ({ ...o, job: j, index: i })),
  );
  const upload = async (file, background = false) => {
    if (!form.rights_confirmed)
      throw new Error(
        "Підтвердьте права на джерело та фон перед завантаженням.",
      );
    const body = new FormData();
    body.append("file", file);
    body.append("rights_confirmed", "true");
    body.append("background", String(background));
    const result = await api("/uploads", { method: "POST", body });
    if (background) {
      field("background", result.name);
      await refresh();
    } else {
      field("source", result.source);
      setMetadata(result.metadata);
    }
  };
  const jobRow = (j) => (
    <article className="job" key={j.id}>
      <div>
        <b>{j.result.source?.title || j.request.source}</b>
        <small>
          {j.id.slice(0, 12)} · {j.worker || "Очікує воркера"} ·{" "}
          {j.request.mode}
        </small>
        {j.error && <p className="error">{j.error}</p>}
      </div>
      <span className={"state " + j.state.toLowerCase()}>{j.state}</span>
      <div>
        {j.current != null && j.total > 0 ? (
          <>
            <progress value={j.current} max={j.total} />
            <small>
              {Math.min(100, Math.round((j.current / j.total) * 100))}%
              поточного етапу
            </small>
          </>
        ) : (
          <small>
            {["READY", "FAILED", "BLOCKED", "CANCELLED", "QUEUED"].includes(
              j.state,
            )
              ? ""
              : "Виконується · тривалість невідома"}
          </small>
        )}
      </div>
      <div className="actions">
        <JobEvents job={j}/>
        <button
          onClick={() => {
            setSelected(j.id);
            setPage("Editor");
          }}
        >
          Відкрити
        </button>
        {["FAILED", "BLOCKED", "CANCELLED"].includes(j.state) ? (
          <button
            onClick={() =>
              act(async () => {
                await post("/jobs/" + j.id + "/retry");
                await refresh();
              })
            }
          >
            Повторити
          </button>
        ) : (
          !["READY"].includes(j.state) && (
            <button
              onClick={() =>
                act(async () => {
                  await post("/jobs/" + j.id + "/cancel");
                  await refresh();
                })
              }
            >
              Скасувати
            </button>
          )
        )}
      </div>
    </article>
  );
  if (!auth)
    return (
      <main className="login">
        <Film size={36} />
        <h1>AI Content Factory</h1>
        <p>Приватний контролер · увійдіть із FACTORY_TOKEN</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            act(async () => {
              await post("/session", { token });
              setToken("");
              await refresh();
            });
          }}
        >
          <input
            type="password"
            aria-label="Controller token"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            required
          />
          <button disabled={busy}>Увійти</button>
        </form>
        {error && <p className="error">{error}</p>}
      </main>
    );
  return (
    <div className="shell">
      <aside>
        <div className="brand">
          <Film />
          <span>
            CONTENT
            <br />
            <b>FACTORY</b>
          </span>
        </div>
        <nav>
          {pages.map(([p, Icon]) => (
            <button
              className={page === p ? "selected" : ""}
              key={p}
              onClick={() => setPage(p)}
            >
              <Icon size={18} />
              {p}
            </button>
          ))}
        </nav>
        <small>Self-hosted · OpenShorts MIT core</small>
        <button
          onClick={() =>
            act(async () => {
              await api("/session", { method: "DELETE" });
              setAuth(false);
            })
          }
        >
          Вийти
        </button>
      </aside>
      <main>
        <header>
          <div>
            <small>WORKSPACE / {page.toUpperCase()}</small>
            <h1>{page}</h1>
          </div>
          <span className="connection">Контролер підключений</span>
        </header>
        {(error||connectionError) && (
          <div role="alert" className="banner error">
            {error||connectionError}
          </div>
        )}
        {notice && (
          <div role="status" className="banner">
            {notice}
          </div>
        )}
        {page === "Dashboard" && (
          <>
            <div className="stats">
              <section>
                <small>Активні завдання</small>
                <strong>{active.length}</strong>
              </section>
              <section>
                <small>Готові завдання</small>
                <strong>{ready.length}</strong>
              </section>
              <section>
                <small>Вільне місце</small>
                <strong>
                  {((settings?.storage.free_bytes || 0) / 1024 ** 3).toFixed(1)}
                  <em> GB</em>
                </strong>
              </section>
            </div>
            <div className="section-title">
              <h2>Останні завдання</h2>
              <button className="primary" onClick={() => setPage("Create")}>
                Створити відео
              </button>
            </div>
            {jobs.slice(0, 8).map(jobRow)}
            {jobs.length === 0 && (
              <p className="muted">
                Ще немає завдань. Додайте своє відео або URL завершеного VOD.
              </p>
            )}
            <h2>Воркери</h2>
            {settings?.workers.map((w) => (
              <p key={w.id}>
                {w.id} ·{" "}
                {Date.now() / 1000 - w.seen < 120 ? "онлайн" : "немає зв’язку"}
              </p>
            ))}
          </>
        )}
        {page === "Create" && (
          <form
            className="create"
            onSubmit={(e) => {
              e.preventDefault();
              act(async () => {
                const intervals =
                  longIntervals.trim() && form.mode === "longs"
                    ? longIntervals
                        .trim()
                        .split("\n")
                        .map((line) => {
                          const parts = line.split(",").map(Number);
                          if (
                            parts.length !== 2 ||
                            parts.some((n) => !Number.isFinite(n))
                          )
                            throw new Error(
                              "Інтервали Longs: один рядок start,end у секундах.",
                            );
                          return parts;
                        })
                    : [];
                const j = await post("/jobs", { ...form, intervals });
                setSelected(j.id);
                await refresh();
                setPage("Jobs");
              });
            }}
          >
            <section>
              <h2>Джерело</h2>
              <label>
                Посилання YouTube / Twitch VOD
                <input
                  value={form.source}
                  onChange={(e) => {
                    field("source", e.target.value);
                    setMetadata(null);
                  }}
                  required
                  placeholder="https://www.youtube.com/watch?v=…"
                />
              </label>
              <div className="actions">
                <button
                  type="button"
                  disabled={busy || !form.source}
                  onClick={() =>
                    act(async () =>
                      setMetadata(
                        await post("/probe", { source: form.source }),
                      ),
                    )
                  }
                >
                  Перевірити джерело
                </button>
                <label className="file">
                  Завантажити файл
                  <input
                    type="file"
                    accept=".mp4,.mkv,.mov"
                    onChange={(e) =>
                      e.target.files[0] && act(() => upload(e.target.files[0]))
                    }
                  />
                </label>
              </div>
              {metadata && (
                <div className="metadata">
                  <b>{metadata.title}</b>
                  <p>
                    {metadata.platform} · {(metadata.duration / 60).toFixed(1)}{" "}
                    хв · {metadata.resolutions.join(", ")}p
                  </p>
                  <p>
                    Вибрано:{" "}
                    {metadata.resolutions
                      .filter(
                        (r) =>
                          form.resolution === "best" || r <= form.resolution,
                      )
                      .sort((a, b) => b - a)[0] || "недоступно"}
                    p · інтервал {form.start}–
                    {Math.min(form.end, metadata.duration)} сек
                  </p>
                </div>
              )}
              <label className="check">
                <input
                  type="checkbox"
                  checked={form.rights_confirmed}
                  onChange={(e) => field("rights_confirmed", e.target.checked)}
                />
                Я маю права на джерело та вибраний фон
              </label>
            </section>
            <section>
              <h2>Монтаж</h2>
              <label>
                Швидкий вибір інтервалу
                <select
                  defaultValue="1800"
                  onChange={(e) => {
                    if (e.target.value === "custom") return;
                    field("start", 0);
                    field(
                      "end",
                      e.target.value === "entire"
                        ? metadata?.duration || 1800
                        : Number(e.target.value),
                    );
                  }}
                >
                  <option value="600">Перші 10 хвилин</option>
                  <option value="1800">Перші 30 хвилин</option>
                  <option value="3600">Перші 60 хвилин</option>
                  <option
                    value="entire"
                    disabled={!metadata || metadata.duration > 3600}
                  >
                    Повністю · до 60 хвилин
                  </option>
                  <option value="custom">Власний інтервал нижче</option>
                </select>
              </label>
              {form.mode === "longs" && (
                <label>
                  Інтервали для хронологічного з’єднання · source start,end у
                  секундах
                  <textarea
                    value={longIntervals}
                    onChange={(e) => setLongIntervals(e.target.value)}
                    placeholder="0,45&#10;120,180"
                  />
                  <small>
                    Залиште порожнім для всього вибраного інтервалу.
                  </small>
                </label>
              )}
              <div className="grid">
                <label>
                  Режим
                  <select
                    value={form.mode}
                    onChange={(e) => field("mode", e.target.value)}
                  >
                    <option value="shorts">Shorts · 9:16</option>
                    <option value="longs">Longs · 16:9</option>
                  </select>
                </label>
                <label>
                  Якість джерела
                  <select
                    value={form.resolution}
                    onChange={(e) =>
                      field(
                        "resolution",
                        e.target.value === "best" ? "best" : +e.target.value,
                      )
                    }
                  >
                    <option value="best">Best available</option>
                    {[480, 720, 1080].map((r) => (
                      <option key={r} value={r}>
                        {r}p
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Початок, сек
                  <input
                    type="number"
                    min="0"
                    value={form.start}
                    onChange={(e) => field("start", +e.target.value)}
                  />
                </label>
                <label>
                  Кінець, сек
                  <input
                    type="number"
                    min="1"
                    value={form.end}
                    onChange={(e) => field("end", +e.target.value)}
                  />
                </label>
                <label>
                  Кількість кліпів
                  <input
                    type="number"
                    min="1"
                    max="20"
                    value={form.count}
                    disabled={form.mode === "longs"}
                    onChange={(e) => field("count", +e.target.value)}
                  />
                </label>
                <label>
                  Мова
                  <select
                    value={form.language || ""}
                    onChange={(e) => field("language", e.target.value || null)}
                  >
                    <option value="">Автоматично</option>
                    {["en", "uk", "ru", "es", "de", "fr"].map((l) => (
                      <option key={l}>{l}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Мінімум, сек
                  <input
                    type="number"
                    min="5"
                    value={form.minimum}
                    disabled={form.mode === "longs"}
                    onChange={(e) => field("minimum", +e.target.value)}
                  />
                </label>
                <label>
                  Максимум, сек
                  <input
                    type="number"
                    min="5"
                    value={form.maximum}
                    disabled={form.mode === "longs"}
                    onChange={(e) => field("maximum", +e.target.value)}
                  />
                </label>
              </div>
              <div className="grid">
                <label>
                  Бітрейт MP4, Mbps
                  <input
                    type="number"
                    min="1"
                    max="50"
                    value={(form.bitrate || 8000000) / 1000000}
                    onChange={(e) =>
                      field("bitrate", +e.target.value * 1000000)
                    }
                  />
                </label>
                <label>
                  Стиль субтитрів
                  <select
                    value={form.caption_style || "pop"}
                    onChange={(e) => field("caption_style", e.target.value)}
                  >
                    <option value="pop">Pop</option>
                    <option value="karaoke">Karaoke</option>
                    <option value="clean">Clean</option>
                  </select>
                </label>
                {form.mode === "longs" && (
                  <label>
                    Висота Longs
                    <select
                      value={form.output_height || 720}
                      onChange={(e) => field("output_height", +e.target.value)}
                    >
                      <option value="720">720p</option>
                      <option value="1080">1080p</option>
                    </select>
                  </label>
                )}
              </div>
              <label>
                Композиція
                <select
                  value={form.preset}
                  disabled={form.mode === "longs"}
                  onChange={(e) => field("preset", e.target.value)}
                >
                  <option value="blur">Blurred Background</option>
                  <option value="crop">Center Crop · без трекінгу облич</option>
                  <option value="gameplay">Gameplay Split · 50/50</option>
                </select>
              </label>
              {form.preset === "gameplay" && (
                <>
                  <label>
                    Авторизований фон
                    <select
                      value={form.background || ""}
                      onChange={(e) =>
                        field("background", e.target.value || null)
                      }
                    >
                      <option value="">Виберіть MP4</option>
                      {backgrounds.map((b) => (
                        <option key={b}>{b}</option>
                      ))}
                    </select>
                  </label>
                  <label className="file">
                    Додати MP4-фон
                    <input
                      type="file"
                      accept=".mp4"
                      onChange={(e) =>
                        e.target.files[0] &&
                        act(() => upload(e.target.files[0], true))
                      }
                    />
                  </label>
                </>
              )}
              <label className="check">
                <input
                  type="checkbox"
                  checked={form.captions}
                  onChange={(e) => field("captions", e.target.checked)}
                />
                Синхронізовані karaoke-субтитри
              </label>
              <label>
                Текст на початку відео · до 120 символів
                <input
                  maxLength="120"
                  value={form.hook || ""}
                  onChange={(e) => field("hook", e.target.value)}
                />
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  checked={form.preserve_fps || false}
                  onChange={(e) => field("preserve_fps", e.target.checked)}
                />
                Зберегти FPS джерела замість 30 FPS
              </label>
              {form.mode === "shorts" && form.preset === "gameplay" && (
                <label>
                  Частка головного відео:{" "}
                  {Math.round((form.split_ratio || 0.5) * 100)}%
                  <input
                    type="range"
                    min="0.2"
                    max="0.8"
                    step="0.05"
                    value={form.split_ratio || 0.5}
                    onChange={(e) => field("split_ratio", +e.target.value)}
                  />
                </label>
              )}
              <label className="check">
                <input
                  type="checkbox"
                  checked={form.save_drive}
                  onChange={(e) => field("save_drive", e.target.checked)}
                />
                Зберегти й перевірити в Google Drive
              </label>
              <label>
                Канал для автоматичної черги
                <select
                  value={form.publish_channel || ""}
                  onChange={(e) => {
                    field("publish_channel", e.target.value || null);
                    field("publish_automatic", false);
                  }}
                >
                  <option value="">
                    Review only · без автоматичної публікації
                  </option>
                  {settings?.channels
                    ?.filter((c) => c.automatic && c.public_allowed)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.title}
                      </option>
                    ))}
                </select>
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  disabled={!form.publish_channel || !form.save_drive}
                  checked={form.publish_automatic || false}
                  onChange={(e) => field("publish_automatic", e.target.checked)}
                />
                Автоматично поставити результати у дозволену чергу після
                перевірки Drive
              </label>
              {!settings?.drive_configured && form.save_drive && (
                <p className="warning">
                  Drive не налаштовано. Результати залишаться локально в BLOCKED
                  до підключення авторизації.
                </p>
              )}
              <p className="muted">
                Публікація потребує окремого налаштування YouTube. Генерація не
                публікує відео.
              </p>
              <button
                className="primary"
                disabled={
                  busy ||
                  !form.rights_confirmed ||
                  !metadata ||
                  (form.preset === "gameplay" && !form.background)
                }
              >
                Generate
              </button>
            </section>
          </form>
        )}
        {page === "Jobs" && (
          <>
            {jobs.map(jobRow)}
            {jobs.length === 0 && <p className="muted">Черга порожня.</p>}
          </>
        )}
        {page === "Editor" && (
          <>
            {chosen ? (
              <>
                <select
                  value={chosen.id}
                  onChange={(e) => {
                    setSelected(e.target.value);
                    setEdits({});
                  }}
                >
                  {jobs.map((j) => (
                    <option key={j.id} value={j.id}>
                      {j.result.source?.title || j.id}
                    </option>
                  ))}
                </select>
                <p>
                  {chosen.result.analysis === "heuristic"
                    ? "Heuristic fallback: локальний LLM недоступний або повернув некоректні дані. Потрібен редакторський перегляд."
                    : chosen.result.analysis}
                </p>
                {chosen.error && <p className="error">{chosen.error}</p>}
                <div className="outputs">
                  {(chosen.result.outputs || []).map((o, i) => (
                    <section key={o.name}>
                      <video
                          controls
                          preload="metadata"
                          src={"/api/jobs/" + chosen.id + "/files/" + o.name}
                        />
                      {o.drive && (
                        <a
                          target="_blank"
                          rel="noreferrer"
                          href={
                            o.drive?.webViewLink ||
                            "https://drive.google.com/file/d/" +
                              o.drive?.id +
                              "/view"
                          }
                        >
                          Переглянути в Google Drive
                        </a>
                      )}
                      <h3>{o.title}</h3>
                      <div className="actions">
                        <a href={"/api/jobs/" + chosen.id + "/files/" + o.name}>
                          MP4
                        </a>
                        <button
                          disabled={chosen.state !== "READY"}
                          onClick={() =>
                            act(async () => {
                              await post(
                                `/jobs/${chosen.id}/outputs/${i}/approve`,
                                { approved: !o.approved },
                              );
                              await refresh();
                            })
                          }
                        >
                          {o.approved ? "Скасувати схвалення" : "Схвалити"}
                        </button>
                      </div>
                    </section>
                  ))}
                </div>
                <h2>Кандидати та повторний монтаж</h2>
                {(chosen.result.candidates || []).map((c, i) => (
                  <section className="candidate" key={i}>
                    <b>{c.title}</b>
                    <small>
                      Оцінка: {c.score ?? "ручний інтервал"} · {c.reason}
                    </small>
                    <div className="grid">
                      <label>
                        Початок від початку аналізу, сек
                        <input
                          type="number"
                          step="0.1"
                          value={edits[i]?.[0] ?? c.start_seconds}
                          onChange={(e) =>
                            setEdits((v) => ({
                              ...v,
                              [i]: [
                                +e.target.value,
                                v[i]?.[1] ?? c.end_seconds,
                              ],
                            }))
                          }
                        />
                      </label>
                      <label>
                        Кінець, сек
                        <input
                          type="number"
                          step="0.1"
                          value={edits[i]?.[1] ?? c.end_seconds}
                          onChange={(e) =>
                            setEdits((v) => ({
                              ...v,
                              [i]: [
                                v[i]?.[0] ?? c.start_seconds,
                                +e.target.value,
                              ],
                            }))
                          }
                        />
                      </label>
                    </div>
                    <button
                      disabled={
                        chosen.result.cloud_verified &&
                        chosen.request.source.startsWith("upload:")
                      }
                      title={
                        chosen.result.cloud_verified &&
                        chosen.request.source.startsWith("upload:")
                          ? "Локальне джерело очищено після Drive upload; завантажте його повторно."
                          : ""
                      }
                      onClick={() =>
                        act(async () => {
                          const range = edits[i] || [
                            c.start_seconds,
                            c.end_seconds,
                          ];
                          const j = await post("/jobs", {
                            ...chosen.request,
                            intervals: [
                              [
                                range[0] + chosen.request.start,
                                range[1] + chosen.request.start,
                              ],
                            ],
                          });
                          setSelected(j.id);
                          await refresh();
                          setPage("Jobs");
                        })
                      }
                    >
                      Рендер цього інтервалу
                    </button>
                  </section>
                ))}
                {["json", "srt", "vtt"].map((ext) => (
                    <a
                      className="export"
                      key={ext}
                      href={
                        "/api/jobs/" + chosen.id + "/files/transcript." + ext
                      }
                    >
                      Transcript {ext.toUpperCase()}
                    </a>
                  ))}
              </>
            ) : (
              <p className="muted">Створіть завдання, щоб відкрити редактор.</p>
            )}
          </>
        )}
        {page === "Library" && (
          <>
            <div className="grid">
              <label>
                Пошук у бібліотеці
                <input
                  value={libraryQuery}
                  onChange={(e) => setLibraryQuery(e.target.value)}
                  placeholder="Назва, мова або джерело"
                />
              </label>
              <label>
                Формат
                <select
                  value={libraryMode}
                  onChange={(e) => setLibraryMode(e.target.value)}
                >
                  <option value="all">Усі</option>
                  <option value="shorts">Shorts</option>
                  <option value="longs">Longs</option>
                </select>
              </label>
            </div>
            <div className="outputs">
              {outputs
                .filter(
                  (o) =>
                    (libraryMode === "all" ||
                      o.job.request.mode === libraryMode) &&
                    [o.title, o.job.result.language, o.job.request.source]
                      .join(" ")
                      .toLocaleLowerCase()
                      .includes(libraryQuery.toLocaleLowerCase()),
                )
                .map((o) => (
                  <section key={o.job.id + o.name}>
                    {o.thumbnail&&<img alt={o.title} style={{width:'100%',maxHeight:240,objectFit:'contain'}} src={'/api/jobs/'+o.job.id+'/files/'+o.thumbnail.name}/>}
                    <h3>{o.title}</h3>
                    <p>
                      {o.job.result.language} · {o.job.request.mode} ·{" "}
                      {o.approved ? "Схвалено" : "Очікує перевірки"}
                    </p>
                    <button
                      onClick={() => {
                        setSelected(o.job.id);
                        setPage("Editor");
                      }}
                    >
                      Відкрити
                    </button>
                    {o.drive && (
                      <a
                        target="_blank"
                        rel="noreferrer"
                        href={
                          o.drive.webViewLink ||
                          "https://drive.google.com/file/d/" +
                            o.drive.id +
                            "/view"
                        }
                      >
                        Google Drive
                      </a>
                    )}
                  </section>
                ))}
            </div>
            {outputs.length === 0 && (
              <p className="muted">Готових відео ще немає.</p>
            )}
          </>
        )}
        {page === "Publisher" && (
          <PublisherPanel outputs={outputs} settings={settings} act={act} />
        )}
        {page === "Settings" && (
          <>
            <section>
              <h2>Google Drive</h2>
              <p>
                {settings?.drive_configured
                  ? "Файл авторизації підключено; перевірте доступ."
                  : "Авторизацію не підключено. Вкажіть DRIVE_TOKEN_FILE з наявним authorized-user JSON; файл монтується read-only."}
              </p>
              <button
                onClick={() =>
                  act(async () => {
                    await post("/settings/check-drive");
                    setNotice("Google Drive: доступ підтверджено");
                  })
                }
              >
                Перевірити доступ
              </button>
            </section>
            <section>
              <h2>Local AI</h2>
              <ModelConfiguration settings={settings} act={act} />
              <p>Ollama · {settings?.ollama_model} · CPU inference</p>
              <button
                onClick={() =>
                  act(async () => {
                    const result = await post("/settings/check-ollama");
                    setNotice(
                      result.available ? "Модель доступна" : result.action,
                    );
                  })
                }
              >
                Перевірити модель
              </button>
              <button
                disabled={["CONNECTING", "DOWNLOADING"].includes(
                  settings?.model_setup?.state,
                )}
                onClick={() =>
                  act(async () => {
                    await post("/settings/setup-model");
                    setNotice(
                      "Завантаження моделі запущено. Прогрес з’явиться нижче.",
                    );
                  })
                }
              >
                Завантажити налаштовану модель
              </button>
              {settings?.model_setup && (
                <p>
                  {settings.model_setup.state} ·{" "}
                  {settings.model_setup.status || settings.model_setup.error}
                </p>
              )}
              {settings?.model_setup?.total > 0 && (
                <progress
                  value={settings.model_setup.current || 0}
                  max={settings.model_setup.total}
                />
              )}
            </section>
            <section>
              <h2>Ресурси та обмеження</h2>
              <p>
                Scratch:{" "}
                {((settings?.storage.scratch_bytes || 0) / 1024 ** 3).toFixed(
                  2,
                )}{" "}
                /{" "}
                {((settings?.storage.budget_bytes || 0) / 1024 ** 3).toFixed(0)}{" "}
                GB
              </p>
              {settings?.notes.map((n) => (
                <p key={n}>{n}</p>
              ))}
              <p>
                Налаштування моделей, лімітів та авторизації: файл .env і
                перезапуск Compose.
              </p>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")).render(<App />);
