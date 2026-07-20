import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { sendAnprEvent } from "../api/anpr";
import { useActiveSessions, useCameras } from "../api/hooks";
import type { Direction } from "../api/types";
import { PlateReadout } from "../components/PlateReadout";
import { formatDuration } from "../lib/format";

const PRESET_PLATES = ["127AST02", "845BCA02", "010KX02", "333ABC02"];

const ACTION_META: Record<string, { label: string; cls: string }> = {
  created: { label: "создана сессия", cls: "bg-emerald-100 text-emerald-700" },
  closed: { label: "закрыта сессия", cls: "bg-sky-100 text-sky-700" },
  updated_last_seen: { label: "дубль въезда", cls: "bg-amber-100 text-amber-700" },
  duplicate_exit: { label: "дубль выезда", cls: "bg-amber-100 text-amber-700" },
  event_without_session: { label: "выезд без сессии", cls: "bg-rose-100 text-rose-700" },
  low_confidence: { label: "низкая уверенность", cls: "bg-amber-100 text-amber-700" },
  ignored: { label: "проигнорировано", cls: "bg-slate-100 text-slate-500" },
};

interface LogRow {
  key: number;
  time: string;
  plate: string;
  direction: Direction;
  action: string;
  sessionId: number | null;
  error?: string;
}

function randomKzPlate(): string {
  const D = "0123456789";
  const L = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const pick = (s: string) => s[Math.floor(Math.random() * s.length)];
  return (
    pick(D) + pick(D) + pick(D) + pick(L) + pick(L) + pick(L) + pick(D) + pick(D)
  );
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function SimulatorPage() {
  const qc = useQueryClient();
  const cameras = useCameras();
  const parking = useActiveSessions();
  const counter = useRef(0);

  const [plate, setPlate] = useState("127AST02");
  const [direction, setDirection] = useState<Direction>("ENTRY");
  const [confidence, setConfidence] = useState(0.95);
  const [device, setDevice] = useState("Симулятор");
  const [log, setLog] = useState<LogRow[]>([]);
  const [busy, setBusy] = useState(false);

  const pushLog = (row: Omit<LogRow, "key" | "time">) => {
    counter.current += 1;
    const time = new Date().toLocaleTimeString("ru-RU");
    setLog((prev) => [{ ...row, key: counter.current, time }, ...prev].slice(0, 25));
  };

  async function fire(p: string, dir: Direction, conf = confidence) {
    try {
      const res = await sendAnprEvent({
        plateNumber: p,
        direction: dir,
        confidence: conf,
        deviceName: device,
      });
      pushLog({
        plate: p,
        direction: dir,
        action: res.session_action,
        sessionId: res.session_id,
      });
    } catch (e) {
      pushLog({
        plate: p,
        direction: dir,
        action: "error",
        sessionId: null,
        error: e instanceof Error ? e.message : "ошибка",
      });
    }
    qc.invalidateQueries();
  }

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  }

  const sendOne = () =>
    run(() => fire(plate.trim().toUpperCase(), direction));

  const scenarios: { label: string; run: () => Promise<void> }[] = [
    {
      label: "Въезд → Выезд",
      run: async () => {
        const p = randomKzPlate();
        await fire(p, "ENTRY");
        await sleep(900);
        await fire(p, "EXIT");
      },
    },
    {
      label: "Двойной въезд",
      run: async () => {
        const p = randomKzPlate();
        await fire(p, "ENTRY");
        await sleep(700);
        await fire(p, "ENTRY");
      },
    },
    {
      label: "Выезд без въезда",
      run: () => fire(randomKzPlate(), "EXIT"),
    },
    {
      label: "Низкая уверенность",
      run: () => fire(randomKzPlate(), "ENTRY", 0.5),
    },
    {
      label: "Повторный въезд после выезда",
      run: async () => {
        const p = randomKzPlate();
        await fire(p, "ENTRY");
        await sleep(700);
        await fire(p, "EXIT");
        await sleep(700);
        await fire(p, "ENTRY");
      },
    },
  ];

  const cameraNames = cameras.data?.map((c) => c.name) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <div className="eyebrow">Тестирование</div>
        <h2 className="font-display text-xl font-semibold text-ink">Симулятор КПП</h2>
        <p className="mt-1 text-sm text-ink-500/70">
          Прогоняй машины через шлагбаум и смотри, что делает система. События идут в
          тот же бэкенд, что и камера — Дашборд и Сессии обновляются автоматически.
        </p>
      </div>

      {/* Живое состояние парковки — кто сейчас внутри */}
      <div className="card p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="eyebrow">Сейчас на парковке</div>
            <div className="mt-1 font-display text-2xl font-bold text-ink">
              {parking.isLoading ? "…" : (parking.data?.length ?? 0)}{" "}
              <span className="text-sm font-medium text-ink-500/50">авто</span>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-emerald-700">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-emerald-400" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
            </span>
            live
          </span>
        </div>
        <div className="mt-4">
          {!parking.data || parking.data.length === 0 ? (
            <p className="rounded-xl border border-dashed border-line py-8 text-center text-sm text-ink-500/50">
              {parking.isError
                ? "Не удалось загрузить — запущен ли backend?"
                : "Парковка пуста — отправь «Въезд»"}
            </p>
          ) : (
            <div className="flex flex-wrap gap-3">
              {parking.data.map((s) => (
                <div
                  key={s.id}
                  className="flex animate-fade-up items-center gap-3 rounded-xl border border-line bg-paper px-3 py-2"
                >
                  <PlateReadout plate={s.plate_number} size="sm" />
                  <span className="font-mono text-xs font-medium text-emerald-700">
                    {formatDuration(s.parked_seconds)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Ручная отправка */}
        <div className="card space-y-4 p-5">
          <div className="eyebrow">Одно событие</div>

          <div className="flex flex-wrap gap-2">
            {PRESET_PLATES.map((p) => (
              <button
                key={p}
                onClick={() => setPlate(p)}
                className={`rounded-md transition ${
                  plate === p ? "ring-2 ring-sky" : "opacity-80 hover:opacity-100"
                }`}
              >
                <PlateReadout plate={p} size="sm" />
              </button>
            ))}
          </div>

          <label className="block text-sm">
            <span className="mb-1 block text-xs font-medium text-ink-500/70">Номер</span>
            <input
              value={plate}
              onChange={(e) => setPlate(e.target.value)}
              className="input w-full font-mono uppercase tracking-wide"
              placeholder="127AST02"
            />
          </label>

          <div className="flex flex-wrap items-end gap-4">
            <div>
              <span className="mb-1 block text-xs font-medium text-ink-500/70">
                Направление
              </span>
              <div className="inline-flex overflow-hidden rounded-lg border border-line">
                {(["ENTRY", "EXIT"] as Direction[]).map((d) => (
                  <button
                    key={d}
                    onClick={() => setDirection(d)}
                    className={`px-4 py-2 text-sm font-medium transition ${
                      direction === d
                        ? "bg-sky text-white"
                        : "bg-surface text-ink-500/70 hover:bg-paper"
                    }`}
                  >
                    {d === "ENTRY" ? "Въезд" : "Выезд"}
                  </button>
                ))}
              </div>
            </div>

            {cameraNames.length > 0 && (
              <label className="text-sm">
                <span className="mb-1 block text-xs font-medium text-ink-500/70">
                  Камера
                </span>
                <select
                  value={device}
                  onChange={(e) => setDevice(e.target.value)}
                  className="input"
                >
                  <option value="Симулятор">Симулятор</option>
                  {cameraNames.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          <label className="block text-sm">
            <span className="mb-1 block text-xs font-medium text-ink-500/70">
              Уверенность: <span className="font-mono text-ink">{confidence.toFixed(2)}</span>
              {confidence < 0.85 && (
                <span className="ml-2 text-amber-600">→ ниже порога 0.85</span>
              )}
            </span>
            <input
              type="range"
              min={0.5}
              max={1}
              step={0.01}
              value={confidence}
              onChange={(e) => setConfidence(Number(e.target.value))}
              className="w-full accent-sky"
            />
          </label>

          <button
            onClick={sendOne}
            disabled={busy || !plate.trim()}
            className="w-full rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-dark disabled:opacity-50"
          >
            {busy ? "Отправка…" : "Отправить событие"}
          </button>
        </div>

        {/* Быстрые сценарии */}
        <div className="card space-y-3 p-5">
          <div className="eyebrow">Быстрые сценарии · 1 клик</div>
          <div className="space-y-2">
            {scenarios.map((s) => (
              <button
                key={s.label}
                onClick={() => run(s.run)}
                disabled={busy}
                className="flex w-full items-center justify-between rounded-lg border border-line bg-surface px-4 py-3 text-left text-sm font-medium text-ink transition hover:border-sky hover:bg-paper disabled:opacity-50"
              >
                {s.label}
                <span className="text-ink-500/40">→</span>
              </button>
            ))}
          </div>
          <p className="text-xs text-ink-500/60">
            Сценарии используют случайные номера, чтобы не пересекаться. Результат — в
            логе ниже и на Дашборде.
          </p>
        </div>
      </div>

      {/* Живой лог */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <div>
            <div className="eyebrow">Результат</div>
            <h3 className="font-display text-sm font-semibold text-ink">Лог событий</h3>
          </div>
          {log.length > 0 && (
            <button
              onClick={() => setLog([])}
              className="text-xs text-ink-500/60 hover:text-sky-700"
            >
              очистить
            </button>
          )}
        </div>
        <ul className="divide-y divide-line">
          {log.length === 0 && (
            <li className="px-5 py-10 text-center text-sm text-ink-500/50">
              Отправь событие или запусти сценарий
            </li>
          )}
          {log.map((row) => {
            const meta = ACTION_META[row.action];
            return (
              <li key={row.key} className="flex animate-fade-up items-center gap-4 px-5 py-3">
                <span className="w-20 font-mono text-xs text-ink-500/50">{row.time}</span>
                <PlateReadout plate={row.plate} size="sm" />
                <span className="text-sm text-ink-500/70">
                  {row.direction === "ENTRY" ? "Въезд" : "Выезд"}
                </span>
                <span className="ml-auto">
                  {row.error ? (
                    <span className="rounded px-2 py-0.5 text-xs font-medium bg-rose-100 text-rose-700">
                      ошибка: {row.error}
                    </span>
                  ) : (
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-medium ${
                        meta?.cls ?? "bg-slate-100 text-slate-500"
                      }`}
                    >
                      {meta?.label ?? row.action}
                      {row.sessionId ? ` · #${row.sessionId}` : ""}
                    </span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
