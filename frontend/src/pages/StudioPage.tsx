import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { sendAnprEvent } from "../api/anpr";
import {
  useActiveSessions,
  useConfirmPaymentMock,
  useCreatePayment,
  useTariffs,
} from "../api/hooks";
import type { Direction, ParkingSession, Tariff } from "../api/types";
import { PlateReadout } from "../components/PlateReadout";
import { formatDuration } from "../lib/format";
import { amountDue, estimatePrice, formatMoney } from "../lib/tariff";
import { RecognizePage } from "./RecognizePage";

const ACTION_META: Record<string, { label: string; cls: string }> = {
  created: { label: "создана сессия", cls: "bg-emerald-100 text-emerald-700" },
  closed: { label: "закрыта сессия", cls: "bg-sky-100 text-sky-700" },
  updated_last_seen: { label: "дубль въезда", cls: "bg-amber-100 text-amber-700" },
  duplicate_exit: { label: "дубль выезда", cls: "bg-amber-100 text-amber-700" },
  event_without_session: {
    label: "выезд без сессии",
    cls: "bg-rose-100 text-rose-700",
  },
  exit_denied_unpaid: {
    label: "🚧 выезд заблокирован — нужна оплата",
    cls: "bg-rose-100 text-rose-700",
  },
  low_confidence: { label: "низкая уверенность", cls: "bg-amber-100 text-amber-700" },
  ignored: { label: "проигнорировано", cls: "bg-slate-100 text-slate-500" },
  payment: { label: "💳 оплачено", cls: "bg-emerald-100 text-emerald-700" },
  payment_error: { label: "ошибка оплаты", cls: "bg-rose-100 text-rose-700" },
};

interface LogRow {
  key: number;
  time: string;
  plate: string;
  direction?: Direction;
  action: string;
  sessionId: number | null;
  amount?: number;
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

export function StudioPage() {
  const qc = useQueryClient();
  const parking = useActiveSessions();
  const tariffs = useTariffs();
  const createPayment = useCreatePayment();
  const confirmPayment = useConfirmPaymentMock();
  const counter = useRef(0);

  const [tab, setTab] = useState<"kpp" | "cv">("kpp");
  const paying = createPayment.isPending || confirmPayment.isPending;

  const [plate, setPlate] = useState("127AST02");
  const [confidence, setConfidence] = useState(0.95);
  const [log, setLog] = useState<LogRow[]>([]);
  const [busy, setBusy] = useState(false);

  const activeTariff: Tariff | null =
    tariffs.data?.find((t) => t.is_active) ?? null;

  const pushLog = (row: Omit<LogRow, "key" | "time">) => {
    counter.current += 1;
    const time = new Date().toLocaleTimeString("ru-RU");
    setLog((prev) => [{ ...row, key: counter.current, time }, ...prev].slice(0, 25));
  };

  // Оплата (mock): создать платёж -> подтвердить webhook -> лог + сессия PAID
  const payFor = (session: ParkingSession) => {
    const fail = (e: unknown) =>
      pushLog({
        plate: session.plate_number,
        action: "payment_error",
        sessionId: session.id,
        error: e instanceof Error ? e.message : "ошибка",
      });
    createPayment.mutate(session.id, {
      onSuccess: (payment) =>
        confirmPayment.mutate(payment.provider_payment_id, {
          onSuccess: () => {
            pushLog({
              plate: session.plate_number,
              action: "payment",
              sessionId: session.id,
              amount: payment.amount,
            });
            qc.invalidateQueries();
          },
          onError: fail,
        }),
      onError: fail,
    });
  };

  async function fire(p: string, dir: Direction, conf = confidence) {
    try {
      const res = await sendAnprEvent({
        plateNumber: p,
        direction: dir,
        confidence: conf,
        deviceName: "Студия",
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

  const cars = parking.data ?? [];
  // Должники: машины на парковке, у которых есть незакрытый долг по тарифу
  const owing = cars
    .map((s) => ({ session: s, due: amountDue(s, activeTariff) }))
    .filter((x) => x.due > 0);

  return (
    <div className="space-y-6">
      <div>
        <div className="eyebrow">Тестовый стенд</div>
        <h2 className="font-display text-xl font-semibold text-ink">
          Студия разработчика
        </h2>
        <p className="mt-1 text-sm text-ink-500/70">
          Единый пульт для теста всей системы: эмулируй въезд/выезд, смотри кто на
          парковке и сколько уже «набежало» по активному тарифу. События идут в тот
          же бэкенд, что и камера.
        </p>
      </div>

      {/* Вкладки */}
      <div className="flex gap-1 border-b border-line">
        {[
          { id: "kpp" as const, label: "Эмуляция КПП" },
          { id: "cv" as const, label: "Тест CV" },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition ${
              tab === t.id
                ? "border-sky text-ink"
                : "border-transparent text-ink-500/50 hover:text-ink-500/80"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "cv" && <RecognizePage />}

      {tab === "kpp" && (
        <div className="space-y-6">

      {/* Активный тариф */}
      {activeTariff ? (
        <div className="card flex flex-wrap items-center gap-x-8 gap-y-3 p-5">
          <div>
            <div className="eyebrow">Активный тариф</div>
            <div className="mt-1 font-display text-lg font-semibold text-ink">
              {activeTariff.name}
            </div>
          </div>
          <TariffFact label="Бесплатно" value={`${activeTariff.free_minutes} мин`} />
          <TariffFact
            label="Цена за час"
            value={formatMoney(activeTariff.price_per_hour, activeTariff.currency)}
          />
          <TariffFact
            label="Максимум / сутки"
            value={
              activeTariff.daily_cap == null
                ? "без ограничения"
                : formatMoney(activeTariff.daily_cap, activeTariff.currency)
            }
          />
        </div>
      ) : (
        <div className="card flex items-center justify-between gap-4 border-amber-200 bg-amber-50 p-5">
          <p className="text-sm text-amber-800">
            Нет активного тарифа — стоимость не рассчитывается. Создай тариф и
            отметь «активный».
          </p>
          <Link
            to="/tariffs"
            className="whitespace-nowrap rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white transition hover:bg-brand-dark"
          >
            К тарифам →
          </Link>
        </div>
      )}

      {/* Живая парковка со стоимостью */}
      <div className="card p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="eyebrow">Сейчас на парковке</div>
            <div className="mt-1 font-display text-2xl font-bold text-ink">
              {parking.isLoading ? "…" : cars.length}{" "}
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
          {cars.length === 0 ? (
            <p className="rounded-xl border border-dashed border-line py-8 text-center text-sm text-ink-500/50">
              {parking.isError
                ? "Не удалось загрузить — запущен ли backend?"
                : "Парковка пуста — отправь «Въезд»"}
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {cars.map((s) => (
                <div
                  key={s.id}
                  className="flex animate-fade-up items-center justify-between gap-3 rounded-xl border border-line bg-paper px-3 py-2.5"
                >
                  <div className="flex items-center gap-3">
                    <PlateReadout plate={s.plate_number} size="sm" />
                    <span className="font-mono text-xs text-ink-500/60">
                      {formatDuration(s.parked_seconds)}
                    </span>
                  </div>
                  {activeTariff && (
                    <span className="font-mono text-sm font-semibold text-ink">
                      {formatMoney(
                        estimatePrice(s.parked_seconds ?? 0, activeTariff),
                        activeTariff.currency,
                      )}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
        {activeTariff && cars.length > 0 && (
          <p className="mt-3 text-xs text-ink-500/50">
            Стоимость — предварительная оценка по активному тарифу (точный расчёт на
            бэкенде при выезде).
          </p>
        )}
      </div>

      {/* К оплате (долги) — оплата ДО выезда, mock */}
      <div className="card p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="eyebrow">К оплате · долги</div>
            <div className="mt-1 font-display text-2xl font-bold text-ink">
              {owing.length}{" "}
              <span className="text-sm font-medium text-ink-500/50">машин</span>
            </div>
          </div>
          {paying && (
            <span className="text-xs font-medium text-sky-700">оплата…</span>
          )}
        </div>
        <div className="mt-4">
          {owing.length === 0 ? (
            <p className="rounded-xl border border-dashed border-line py-8 text-center text-sm text-ink-500/50">
              Долгов нет — оплаченные могут выезжать
            </p>
          ) : (
            <div className="space-y-2">
              {owing.map(({ session: s, due }) => (
                <div
                  key={s.id}
                  className="flex animate-fade-up items-center justify-between gap-3 rounded-xl border border-line bg-paper px-3 py-2.5"
                >
                  <div className="flex items-center gap-3">
                    <PlateReadout plate={s.plate_number} size="sm" />
                    <span className="font-mono text-sm font-semibold text-ink">
                      {formatMoney(due, activeTariff?.currency ?? "KZT")}
                    </span>
                    {s.paid_amount > 0 && (
                      <span className="font-mono text-xs text-emerald-700">
                        доплата · уже {formatMoney(s.paid_amount)}
                      </span>
                    )}
                  </div>
                  <button
                    onClick={() => payFor(s)}
                    disabled={paying}
                    className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white transition hover:bg-brand-dark disabled:opacity-50"
                  >
                    Оплатить
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        <p className="mt-3 text-xs text-ink-500/50">
          Оплатить нужно ДО выезда — иначе шлагбаум не откроется. Сумма — текущий
          долг (цена за время минус уже оплачено).
        </p>
      </div>

      {/* Эмуляция въезда/выезда */}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card space-y-4 p-5">
          <div className="eyebrow">Эмуляция события</div>

          <label className="block text-sm">
            <span className="mb-1 block text-xs font-medium text-ink-500/70">
              Номер
            </span>
            <input
              value={plate}
              onChange={(e) => setPlate(e.target.value)}
              className="input w-full font-mono uppercase tracking-wide"
              placeholder="127AST02"
            />
          </label>

          <label className="block text-sm">
            <span className="mb-1 block text-xs font-medium text-ink-500/70">
              Уверенность:{" "}
              <span className="font-mono text-ink">{confidence.toFixed(2)}</span>
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

          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() =>
                run(() => fire(plate.trim().toUpperCase(), "ENTRY"))
              }
              disabled={busy || !plate.trim()}
              className="rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-50"
            >
              Въезд
            </button>
            <button
              onClick={() => run(() => fire(plate.trim().toUpperCase(), "EXIT"))}
              disabled={busy || !plate.trim()}
              className="rounded-lg bg-sky px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
            >
              Выезд
            </button>
          </div>
        </div>

        <div className="card space-y-3 p-5">
          <div className="eyebrow">Быстрые сценарии · 1 клик</div>
          <div className="space-y-2">
            <Scenario
              label="Въезд → Выезд (полный цикл)"
              busy={busy}
              onClick={() =>
                run(async () => {
                  const p = randomKzPlate();
                  await fire(p, "ENTRY");
                  await sleep(900);
                  await fire(p, "EXIT");
                })
              }
            />
            <Scenario
              label="Только въезд (оставить на парковке)"
              busy={busy}
              onClick={() => run(() => fire(randomKzPlate(), "ENTRY"))}
            />
            <Scenario
              label="Выезд без въезда"
              busy={busy}
              onClick={() => run(() => fire(randomKzPlate(), "EXIT"))}
            />
            <Scenario
              label="Низкая уверенность (сессия не создаётся)"
              busy={busy}
              onClick={() => run(() => fire(randomKzPlate(), "ENTRY", 0.5))}
            />
          </div>
          <p className="text-xs text-ink-500/60">
            Сценарии используют случайные номера. Результат — в логе ниже и на
            «Сейчас на парковке».
          </p>
        </div>
      </div>

      {/* Лог */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <div>
            <div className="eyebrow">Результат</div>
            <h3 className="font-display text-sm font-semibold text-ink">
              Лог событий
            </h3>
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
              <li
                key={row.key}
                className="flex animate-fade-up items-center gap-4 px-5 py-3"
              >
                <span className="w-20 font-mono text-xs text-ink-500/50">
                  {row.time}
                </span>
                <PlateReadout plate={row.plate} size="sm" />
                {row.direction && (
                  <span className="text-sm text-ink-500/70">
                    {row.direction === "ENTRY" ? "Въезд" : "Выезд"}
                  </span>
                )}
                {row.amount != null && (
                  <span className="font-mono text-sm font-semibold text-emerald-700">
                    {formatMoney(row.amount)}
                  </span>
                )}
                <span className="ml-auto">
                  {row.error ? (
                    <span className="rounded bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-700">
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
      )}
    </div>
  );
}

function TariffFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-ink-500/50">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-sm font-semibold text-ink">{value}</div>
    </div>
  );
}

function Scenario({
  label,
  busy,
  onClick,
}: {
  label: string;
  busy: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className="flex w-full items-center justify-between rounded-lg border border-line bg-surface px-4 py-3 text-left text-sm font-medium text-ink transition hover:border-sky hover:bg-paper disabled:opacity-50"
    >
      {label}
      <span className="text-ink-500/40">→</span>
    </button>
  );
}
