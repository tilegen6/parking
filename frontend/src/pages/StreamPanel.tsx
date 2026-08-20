import { useEffect, useRef, useState } from "react";
import {
  CV_URL,
  getPipelineVersions,
  getStreamEvents,
  getStreamPreview,
  getStreamStatus,
  startStream,
  stopStream,
  type PipelineOption,
  type StreamEvent,
  type StreamStatus,
} from "../api/cv";
import { PlateReadout } from "../components/PlateReadout";
import {
  guessName,
  loadPresets,
  maskUrl,
  newPresetId,
  savePresets,
  type StreamPreset,
} from "../lib/streamPresets";

const CAMERA = "cv-stream";

// как называется action бэкенда в ленте событий
const ACTION_LABEL: Record<string, { label: string; cls: string }> = {
  created: { label: "въезд · сессия создана", cls: "bg-emerald-100 text-emerald-700" },
  closed: { label: "выезд · сессия закрыта", cls: "bg-sky-100 text-sky-700" },
  updated_last_seen: { label: "дубль въезда", cls: "bg-amber-100 text-amber-700" },
  entry_restarted: {
    label: "⏱ старт сдвинут (дубль у шлагбаума)",
    cls: "bg-amber-100 text-amber-700",
  },
  access_denied_red: {
    label: "🚫 красный список — не пустили",
    cls: "bg-rose-100 text-rose-700",
  },
  reentry_new_session: {
    label: "⚠ старая зависла → закрыта, открыта новая",
    cls: "bg-rose-100 text-rose-700",
  },
  possible_misread: {
    label: "❓ похож на активный номер — проверка",
    cls: "bg-rose-100 text-rose-700",
  },
  duplicate_exit: { label: "дубль выезда", cls: "bg-amber-100 text-amber-700" },
  exit_denied_unpaid: {
    label: "🚧 выезд заблокирован — нужна оплата",
    cls: "bg-rose-100 text-rose-700",
  },
  event_without_session: {
    label: "выезд без сессии",
    cls: "bg-rose-100 text-rose-700",
  },
};

export function StreamPanel() {
  const [url, setUrl] = useState("demo");
  const [direction, setDirection] = useState<"entry" | "exit">("entry");
  // Две независимые оси пайплайна: детектор (находит рамку) и OCR (читает).
  const [detector, setDetector] = useState("plate");
  const [engine, setEngine] = useState("fastplate");
  const [detectors, setDetectors] = useState<PipelineOption[]>([]);
  const [engines, setEngines] = useState<PipelineOption[]>([]);
  const [active, setActive] = useState(false);
  const [status, setStatus] = useState<StreamStatus | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [presets, setPresets] = useState<StreamPreset[]>(() => loadPresets());
  const [nameDraft, setNameDraft] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const sinceRef = useRef(0);

  const isDemo = url.trim() === "demo";

  useEffect(() => savePresets(presets), [presets]);

  useEffect(() => {
    getPipelineVersions()
      .then((r) => {
        setDetectors(r.detectors);
        setEngines(r.engines);
        setDetector(r.default_detector);
        setEngine(r.default_engine);
      })
      .catch(() => {
        /* сервис не поднят — оставим дефолт */
      });
  }, []);

  // Поток крутится в CV-сервисе, а не в браузере: если уйти со страницы, он
  // продолжит лить события в боевую БД. Глушим при уходе и при закрытии вкладки.
  const activeRef = useRef(false);
  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  useEffect(() => {
    // Вернулись на страницу, а поток ещё жив — показываем его, а не «Старт».
    getStreamStatus()
      .then((st) => {
        const mine = st.streams.find((s) => s.camera === CAMERA);
        if (mine?.running) setActive(true);
      })
      .catch(() => {
        /* CV не поднят — оставляем как есть */
      });

    // beforeunload: обычный fetch не успеет — шлём маячок.
    const beacon = () => {
      if (!activeRef.current) return;
      navigator.sendBeacon?.(
        `${CV_URL}/stream/stop`,
        new Blob([JSON.stringify({ camera_name: CAMERA })], {
          type: "application/json",
        }),
      );
    };
    window.addEventListener("beforeunload", beacon);
    return () => {
      window.removeEventListener("beforeunload", beacon);
      if (activeRef.current) {
        void stopStream(CAMERA).catch(() => {
          /* уже остановлен/сервис недоступен */
        });
      }
    };
  }, []);

  // Поллинг статуса/событий/превью, пока поток активен
  useEffect(() => {
    if (!active) return;
    let alive = true;
    const tick = async () => {
      try {
        const st = await getStreamStatus();
        if (!alive) return;
        const mine = st.streams.find((s) => s.camera === CAMERA) ?? null;
        setStatus(mine);
        if (mine && !mine.running) setActive(false); // поток сам остановился

        const ev = await getStreamEvents(sinceRef.current);
        if (!alive) return;
        if (ev.events.length) {
          sinceRef.current = ev.last_seq;
          setEvents((prev) => [...ev.events.reverse(), ...prev].slice(0, 50));
        }

        const pv = await getStreamPreview(CAMERA);
        if (alive && pv.image) setPreview(pv.image);
      } catch {
        /* сервис недоступен — увидим по отсутствию обновлений */
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [active]);

  // Запуск: либо по полям формы, либо сразу по сохранённому подключению
  // (значения берём из пресета, а не из state — setState асинхронный).
  const start = async (preset?: StreamPreset) => {
    const target = (preset?.url ?? url).trim();
    const dir = preset?.direction ?? direction;
    setBusy(true);
    setError(null);
    setEvents([]);
    setPreview(null);
    sinceRef.current = 0;
    try {
      const body: Parameters<typeof startStream>[0] = {
        url: target,
        direction: dir,
        camera_name: CAMERA,
      };
      if (target === "demo") {
        // синтетика работает на template + весь кадр
        body.engine = "template";
        body.detector = "whole";
      } else if (preset) {
        // из пресета: новые оси либо старый version (совместимость)
        body.engine = preset.engine;
        body.detector = preset.detector;
        if (!preset.engine && !preset.detector) body.version = preset.version;
      } else {
        body.engine = engine;
        body.detector = detector;
      }
      await startStream(body);
      setActive(true);
      setActiveId(preset?.id ?? presets.find((p) => p.url === target)?.id ?? null);
    } catch (e) {
      setError(
        e instanceof Error
          ? `${e.message}. Запущен ли CV-сервис (:8090)?`
          : "Ошибка запуска потока",
      );
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setBusy(true);
    try {
      await stopStream(CAMERA);
    } catch {
      /* уже остановлен */
    }
    setActive(false);
    setActiveId(null);
    setBusy(false);
  };

  // ── Сохранённые подключения ───────────────────────────────────────────

  /** Перенести пресет в поля формы (можно поправить перед стартом). */
  const applyPreset = (p: StreamPreset) => {
    setUrl(p.url);
    setDirection(p.direction);
    if (p.detector) setDetector(p.detector);
    if (p.engine) setEngine(p.engine);
    setNameDraft(p.name);
  };

  /** Подключиться к сохранённому в один клик. */
  const connectPreset = async (p: StreamPreset) => {
    applyPreset(p);
    await start(p);
  };

  /** Сохранить то, что сейчас в полях. Тот же URL — обновляем, а не плодим. */
  const saveCurrent = () => {
    const value = url.trim();
    if (!value) return;
    const name = nameDraft.trim() || guessName(value);
    // demo → template + весь кадр; иначе — выбранные оси
    const eng = value === "demo" ? "template" : engine;
    const det = value === "demo" ? "whole" : detector;
    setPresets((list) => {
      const existing = list.find((p) => p.url === value);
      const fields = { name, direction, engine: eng, detector: det, version: undefined };
      if (existing) {
        return list.map((p) => (p.id === existing.id ? { ...p, ...fields } : p));
      }
      return [...list, { id: newPresetId(), url: value, ...fields }];
    });
    setNameDraft("");
  };

  const removePreset = (id: string) =>
    setPresets((list) => list.filter((p) => p.id !== id));

  return (
    <div className="space-y-5">
      <div>
        <div className="eyebrow">Живой поток</div>
        <h2 className="font-display text-xl font-semibold text-ink">
          Распознавание с камеры (RTSP / телефон)
        </h2>
        <p className="mt-1 text-sm text-ink-500/70">
          CV читает поток, трекает машину и шлёт <b>одно</b> событие на проезд (не
          спамит, пока едет). Телефон как камера: DroidCam →{" "}
          <code className="rounded bg-paper px-1 py-0.5 font-mono text-xs">
            http://&lt;ip-телефона&gt;:4747/video
          </code>
          , IP Webcam → порт <code className="font-mono text-xs">8080</code>. Без
          камеры — оставь <code className="font-mono text-xs">demo</code>.
        </p>
      </div>

      {/* Сохранённые подключения */}
      <div className="card p-4">
        <div className="flex items-center justify-between px-1">
          <div className="eyebrow">Сохранённые подключения</div>
          <span className="text-[11px] text-ink-500/50">
            хранятся в этом браузере
          </span>
        </div>

        {presets.length === 0 ? (
          <p className="px-1 py-4 text-sm text-ink-500/50">
            Пока пусто — впиши URL ниже, дай название и нажми «Сохранить».
          </p>
        ) : (
          <ul className="mt-2 divide-y divide-line">
            {presets.map((p) => {
              const live = active && activeId === p.id;
              return (
                <li key={p.id} className="flex items-center gap-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-ink">
                        {p.name}
                      </span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                          p.direction === "entry"
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-sky-100 text-sky-700"
                        }`}
                      >
                        {p.direction === "entry" ? "Въезд" : "Выезд"}
                      </span>
                      {live && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-700">
                          <span className="relative flex h-1.5 w-1.5">
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400" />
                            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                          </span>
                          подключено
                        </span>
                      )}
                    </div>
                    <div className="truncate font-mono text-xs text-ink-500/50">
                      {maskUrl(p.url)}
                    </div>
                  </div>

                  <button
                    onClick={() => applyPreset(p)}
                    className="rounded-lg border border-line px-2.5 py-1.5 text-xs text-ink-600 transition hover:border-sky"
                    title="Подставить в поля — можно поправить перед стартом"
                  >
                    Подставить
                  </button>
                  <button
                    onClick={() => void connectPreset(p)}
                    disabled={busy || active}
                    className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-40"
                  >
                    ▶ Подключить
                  </button>
                  <button
                    onClick={() => removePreset(p.id)}
                    disabled={live}
                    className="rounded-lg px-2 py-1.5 text-sm text-ink-500/40 transition hover:bg-rose-50 hover:text-rose-600 disabled:opacity-30 disabled:hover:bg-transparent"
                    title="Удалить"
                  >
                    ✕
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Управление */}
      <div className="card space-y-4 p-5">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-ink-500/70">
            URL потока
          </span>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={active}
            placeholder="demo · http://192.168.0.5:8080/video · rtsp://user:pass@ip:554/stream"
            className="w-full rounded-lg border border-line bg-paper px-3 py-2 font-mono text-sm text-ink transition focus:border-sky focus:outline-none disabled:opacity-60"
          />
        </label>

        {/* Сохранение текущего URL в закладки */}
        <div className="flex flex-wrap items-end gap-3">
          <label className="min-w-[200px] flex-1">
            <span className="mb-1 block text-xs font-medium text-ink-500/70">
              Название (как назвать это подключение)
            </span>
            <input
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              placeholder="Телефон · DroidCam"
              className="w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink transition focus:border-sky focus:outline-none"
            />
          </label>
          <button
            onClick={saveCurrent}
            disabled={!url.trim()}
            className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink-600 transition hover:border-sky disabled:opacity-40"
          >
            💾 Сохранить
          </button>
        </div>

        <div className="flex flex-wrap items-end gap-4">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ink-500/70">
              Направление (топология камеры)
            </span>
            <select
              value={direction}
              onChange={(e) => setDirection(e.target.value as "entry" | "exit")}
              disabled={active}
              className="rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink focus:border-sky focus:outline-none disabled:opacity-60"
            >
              <option value="entry">Въезд</option>
              <option value="exit">Выезд</option>
            </select>
          </label>

          {isDemo ? (
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-ink-500/70">
                Пайплайн
              </span>
              <div className="rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink-500/60">
                демо-синтетика (template)
              </div>
            </label>
          ) : (
            <>
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-ink-500/70">
                  Детектор (находит номер)
                </span>
                <select
                  value={detector}
                  onChange={(e) => setDetector(e.target.value)}
                  disabled={active}
                  title={detectors.find((d) => d.name === detector)?.desc}
                  className="rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink focus:border-sky focus:outline-none disabled:opacity-60"
                >
                  {detectors.map((d) => (
                    <option key={d.name} value={d.name} disabled={!d.available}>
                      {d.label}
                      {d.available ? "" : " — не установлен"}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="mb-1 block text-xs font-medium text-ink-500/70">
                  OCR (читает символы)
                </span>
                <select
                  value={engine}
                  onChange={(e) => setEngine(e.target.value)}
                  disabled={active}
                  title={engines.find((en) => en.name === engine)?.desc}
                  className="rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink focus:border-sky focus:outline-none disabled:opacity-60"
                >
                  {engines.map((en) => (
                    <option key={en.name} value={en.name} disabled={!en.available}>
                      {en.label}
                      {en.available ? "" : " — не установлен"}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}

          <div className="ml-auto flex items-center gap-3">
            {error && <span className="text-sm text-rose-500">{error}</span>}
            {!active ? (
              <button
                onClick={() => void start()}
                disabled={busy || !url.trim()}
                className="rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-50"
              >
                {busy ? "Запуск…" : "▶ Старт"}
              </button>
            ) : (
              <button
                onClick={stop}
                disabled={busy}
                className="rounded-lg bg-rose-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-rose-700 disabled:opacity-50"
              >
                {busy ? "Стоп…" : "■ Стоп"}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Живой вид: превью + статус + события */}
      {(active || events.length > 0) && (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Что видит камера */}
          <div className="card space-y-3 p-3">
            <div className="flex items-center justify-between px-2 pt-1">
              <div className="eyebrow">Кадр с камеры</div>
              {active && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-emerald-700">
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  </span>
                  live
                </span>
              )}
            </div>
            {preview ? (
              <img
                src={preview}
                alt="Кадр потока"
                className="w-full rounded-xl bg-ink/5"
              />
            ) : (
              <div className="flex h-48 items-center justify-center rounded-xl border border-dashed border-line text-sm text-ink-500/50">
                {active ? "ждём кадр…" : "поток не запущен"}
              </div>
            )}
            {status && (
              <div className="grid grid-cols-3 gap-2 px-1 pb-1 text-center">
                <Stat label="кадров" value={status.frames} />
                <Stat label="событий" value={status.events} />
                <Stat
                  label="реконнект"
                  value={status.reconnects ?? 0}
                  warn={(status.reconnects ?? 0) > 0}
                />
              </div>
            )}
            {status?.source_error && (
              <p className="px-2 pb-1 text-xs text-amber-600">
                источник: {status.source_error}
              </p>
            )}
          </div>

          {/* Лента событий (один проезд = одна строка) */}
          <div className="card overflow-hidden">
            <div className="border-b border-line px-5 py-3">
              <div className="eyebrow">События распознавания</div>
              <p className="mt-0.5 text-xs text-ink-500/60">
                одно событие на машину · улетает в тот же бэкенд, что и с камеры
              </p>
            </div>
            <ul className="max-h-80 divide-y divide-line overflow-y-auto">
              {events.length === 0 && (
                <li className="px-5 py-10 text-center text-sm text-ink-500/50">
                  проезжай мимо камеры номером — событие появится здесь
                </li>
              )}
              {events.map((e) => {
                const meta = e.backend_action
                  ? ACTION_LABEL[e.backend_action]
                  : undefined;
                return (
                  <li
                    key={e.seq}
                    className="flex animate-fade-up items-center gap-3 px-5 py-3"
                  >
                    <span className="w-16 font-mono text-[11px] text-ink-500/50">
                      {e.time
                        ? new Date(e.time).toLocaleTimeString("ru-RU")
                        : "—"}
                    </span>
                    <PlateReadout plate={e.plate} size="sm" />
                    <span className="text-xs text-ink-500/70">
                      {e.direction === "ENTRY" ? "Въезд" : "Выезд"}
                    </span>
                    <span className="ml-auto flex items-center gap-2">
                      {e.confidence != null && (
                        <span className="font-mono text-xs text-ink-500/50">
                          {Math.round(e.confidence * 100)}%
                        </span>
                      )}
                      {e.backend_error ? (
                        <span className="rounded bg-rose-100 px-2 py-0.5 text-[11px] font-medium text-rose-700">
                          ошибка бэка
                        </span>
                      ) : (
                        <span
                          className={`rounded px-2 py-0.5 text-[11px] font-medium ${
                            meta?.cls ?? "bg-slate-100 text-slate-500"
                          }`}
                        >
                          {meta?.label ?? e.backend_action ?? "—"}
                        </span>
                      )}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  warn,
}: {
  label: string;
  value: number;
  warn?: boolean;
}) {
  return (
    <div className="rounded-lg bg-paper py-2">
      <div
        className={`font-mono text-lg font-bold ${warn ? "text-amber-600" : "text-ink"}`}
      >
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-wider text-ink-500/50">
        {label}
      </div>
    </div>
  );
}
