import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { sendAnprEvent } from "../api/anpr";
import {
  useActiveSessions,
  useConfirmPaymentMock,
  useCreatePayment,
  useKaspiCheck,
  useKaspiInfo,
  useKaspiPay,
  useKaspiSimulateExit,
  useTariffs,
} from "../api/hooks";
import type { Direction, ParkingSession, Tariff } from "../api/types";
import { PaymentPanel } from "../components/PaymentPanel";
import { PlateReadout } from "../components/PlateReadout";
import { formatDuration } from "../lib/format";
import { amountDue, estimatePrice, formatMoney } from "../lib/tariff";
import { RecognizePage } from "./RecognizePage";
import { StreamPanel } from "./StreamPanel";

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
  kaspi_check: { label: "Kaspi check", cls: "bg-sky-100 text-sky-700" },
  kaspi_paid: { label: "💳 Kaspi оплачено", cls: "bg-emerald-100 text-emerald-700" },
  kaspi_already: { label: "уже оплачено", cls: "bg-amber-100 text-amber-700" },
  kaspi_autopay: { label: "💳 автосписание", cls: "bg-emerald-100 text-emerald-700" },
  kaspi_autopay_denied: {
    label: "автосписание отклонено",
    cls: "bg-rose-100 text-rose-700",
  },
  kaspi_error: { label: "ошибка Kaspi", cls: "bg-rose-100 text-rose-700" },
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
  note?: string;
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

// Пресеты «машина уже стоит N» — для теста неоплаченных сессий.
const BACKDATE_PRESETS: { label: string; min: number }[] = [
  { label: "Сейчас", min: 0 },
  { label: "30 мин", min: 30 },
  { label: "2 ч", min: 120 },
  { label: "5 ч", min: 300 },
  { label: "1 сутки", min: 1440 },
];

export function StudioPage() {
  const qc = useQueryClient();
  const parking = useActiveSessions();
  const tariffs = useTariffs();
  const createPayment = useCreatePayment();
  const confirmPayment = useConfirmPaymentMock();
  const kaspiInfo = useKaspiInfo();
  const kaspiCheck = useKaspiCheck();
  const kaspiPay = useKaspiPay();
  const kaspiSim = useKaspiSimulateExit();
  const counter = useRef(0);

  const [tab, setTab] = useState<"kpp" | "cv" | "kaspi">("kpp");
  const paying = createPayment.isPending || confirmPayment.isPending;
  // Открытое окно оплаты (QR + кнопка) — как на странице /pay
  const [payTarget, setPayTarget] = useState<{
    session: ParkingSession;
    due: number;
  } | null>(null);

  const [plate, setPlate] = useState("127AST02");
  const [confidence, setConfidence] = useState(0.95);
  // «Стоит уже» — на сколько минут состарить въезд (0 = сейчас)
  const [backMin, setBackMin] = useState(0);
  const [log, setLog] = useState<LogRow[]>([]);
  const [busy, setBusy] = useState(false);

  const activeTariff: Tariff | null =
    tariffs.data?.find((t) => t.is_active) ?? null;

  const pushLog = (row: Omit<LogRow, "key" | "time">) => {
    counter.current += 1;
    const time = new Date().toLocaleTimeString("ru-RU");
    setLog((prev) => [{ ...row, key: counter.current, time }, ...prev].slice(0, 25));
  };

  // Оплата (mock): создать платёж -> подтвердить webhook -> лог + закрыть окно
  const payFor = (session: ParkingSession) => {
    const fail = (e: unknown) => {
      pushLog({
        plate: session.plate_number,
        action: "payment_error",
        sessionId: session.id,
        error: e instanceof Error ? e.message : "ошибка",
      });
      setPayTarget(null);
    };
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
            setPayTarget(null);
          },
          onError: fail,
        }),
      onError: fail,
    });
  };

  async function fire(
    p: string,
    dir: Direction,
    conf = confidence,
    backMinutes = 0,
  ) {
    // Въезд можно «состарить»: entry_time = сейчас − backMinutes → сразу долг.
    // Выезд всегда «сейчас» (иначе выезд оказался бы раньше въезда).
    const at =
      dir === "ENTRY" && backMinutes > 0
        ? new Date(Date.now() - backMinutes * 60_000)
        : undefined;
    try {
      const res = await sendAnprEvent({
        plateNumber: p,
        direction: dir,
        confidence: conf,
        deviceName: "Студия",
        at,
      });
      pushLog({
        plate: p,
        direction: dir,
        action: res.session_action,
        sessionId: res.session_id,
        note: at ? `стоит ${formatDuration(backMinutes * 60)}` : undefined,
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

  // Уникальный txn_id для эмуляции запросов Kaspi (одинаковый → проверка идемпотентности)
  const genTxn = () =>
    `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  const errMsg = (e: unknown) => (e instanceof Error ? e.message : "ошибка");

  // Kaspi online: check — узнать сумму долга по номеру (эмулируем запрос Kaspi)
  const kaspiDoCheck = (s: ParkingSession) =>
    run(async () => {
      try {
        const res = await kaspiCheck.mutateAsync({
          plate: s.plate_number,
          txnId: genTxn(),
        });
        pushLog({
          plate: s.plate_number,
          action: "kaspi_check",
          sessionId: s.id,
          amount: res.sum ? Number(res.sum) : undefined,
          note: `result=${res.result}`,
        });
      } catch (e) {
        pushLog({
          plate: s.plate_number,
          action: "kaspi_error",
          sessionId: s.id,
          error: errMsg(e),
        });
      }
    });

  // Kaspi online: pay — провести оплату по номеру (идемпотентно по txn_id)
  const kaspiDoPay = (s: ParkingSession, due: number) =>
    run(async () => {
      try {
        const res = await kaspiPay.mutateAsync({
          plate: s.plate_number,
          sum: due,
          txnId: genTxn(),
        });
        const action =
          res.result === 0
            ? "kaspi_paid"
            : res.result === 3
              ? "kaspi_already"
              : "kaspi_error";
        pushLog({
          plate: s.plate_number,
          action,
          sessionId: s.id,
          amount: res.sum ? Number(res.sum) : due,
          note: res.prv_txn_id
            ? `result=${res.result} · prv_txn ${res.prv_txn_id}`
            : `result=${res.result}`,
        });
        qc.invalidateQueries();
      } catch (e) {
        pushLog({
          plate: s.plate_number,
          action: "kaspi_error",
          sessionId: s.id,
          error: errMsg(e),
        });
      }
    });

  // Kaspi autopay: пробное автосписание при выезде (что вернул бы Kaspi)
  const kaspiDoSimulate = (s: ParkingSession) =>
    run(async () => {
      try {
        const res = await kaspiSim.mutateAsync(s.id);
        pushLog({
          plate: s.plate_number,
          action: res.is_success ? "kaspi_autopay" : "kaspi_autopay_denied",
          sessionId: s.id,
          amount: res.amount,
          note: res.is_success
            ? res.transaction_id
              ? `txn ${res.transaction_id}`
              : undefined
            : (res.error_code ?? res.error_message ?? "ошибка"),
        });
      } catch (e) {
        pushLog({
          plate: s.plate_number,
          action: "kaspi_autopay_denied",
          sessionId: s.id,
          error: errMsg(e),
        });
      }
    });

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
          { id: "kaspi" as const, label: "Kaspi" },
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

      {tab === "cv" && (
        <div className="space-y-8">
          <StreamPanel />
          <div className="border-t border-line pt-8">
            <RecognizePage />
          </div>
        </div>
      )}

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
                  className="animate-fade-up rounded-xl border border-line bg-paper px-3 py-2.5"
                >
                  <div className="flex items-center justify-between gap-3">
                    <PlateReadout plate={s.plate_number} size="sm" />
                    {activeTariff && (
                      <span className="font-mono text-sm font-semibold text-ink">
                        {formatMoney(
                          estimatePrice(s.parked_seconds ?? 0, activeTariff),
                          activeTariff.currency,
                        )}
                      </span>
                    )}
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-ink-500/60">
                      {formatDuration(s.parked_seconds)}
                    </span>
                    {activeTariff && <PaidBadge session={s} tariff={activeTariff} />}
                  </div>
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
                    onClick={() => setPayTarget({ session: s, due })}
                    className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white transition hover:bg-brand-dark"
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

          <div className="block text-sm">
            <span className="mb-1 block text-xs font-medium text-ink-500/70">
              Стоит уже{" "}
              <span className="text-ink-500/50">
                (применяется к въезду — для теста неоплаченных)
              </span>
            </span>
            <div className="flex flex-wrap items-center gap-1.5">
              {BACKDATE_PRESETS.map((p) => (
                <button
                  key={p.min}
                  onClick={() => setBackMin(p.min)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                    backMin === p.min
                      ? "bg-sky text-white"
                      : "border border-line text-ink-600 hover:border-sky"
                  }`}
                >
                  {p.label}
                </button>
              ))}
              <label className="ml-auto flex items-center gap-1 text-xs text-ink-500/60">
                <input
                  type="number"
                  min={0}
                  value={backMin}
                  onChange={(e) =>
                    setBackMin(Math.max(0, Math.floor(Number(e.target.value) || 0)))
                  }
                  className="input w-20 py-1 font-mono"
                />
                мин
              </label>
            </div>
            {backMin > 0 && (
              <p className="mt-1.5 text-xs text-amber-600">
                Въезд запишется задним числом на {formatDuration(backMin * 60)}
                {activeTariff && (
                  <>
                    {" "}
                    → сразу долг ≈{" "}
                    <span className="font-mono font-semibold">
                      {formatMoney(
                        estimatePrice(backMin * 60, activeTariff),
                        activeTariff.currency,
                      )}
                    </span>
                  </>
                )}
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() =>
                run(() =>
                  fire(plate.trim().toUpperCase(), "ENTRY", confidence, backMin),
                )
              }
              disabled={busy || !plate.trim()}
              className="rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-50"
            >
              Въезд{backMin > 0 ? " (задним числом)" : ""}
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
              label={
                backMin > 0
                  ? `Въезд (−${formatDuration(backMin * 60)}) → Выезд — упрётся в долг`
                  : "Въезд → Выезд (полный цикл)"
              }
              busy={busy}
              onClick={() =>
                run(async () => {
                  const p = randomKzPlate();
                  await fire(p, "ENTRY", confidence, backMin);
                  await sleep(900);
                  await fire(p, "EXIT");
                })
              }
            />
            <Scenario
              label={
                backMin > 0
                  ? `Только въезд — стоит уже ${formatDuration(backMin * 60)}`
                  : "Только въезд (оставить на парковке)"
              }
              busy={busy}
              onClick={() =>
                run(() => fire(randomKzPlate(), "ENTRY", confidence, backMin))
              }
            />
            <Scenario
              label="Неоплаченная машина (стоит 2 ч)"
              busy={busy}
              onClick={() => run(() => fire(randomKzPlate(), "ENTRY", 0.95, 120))}
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
            Сценарии используют случайные номера. «Стоит уже» выше задаёт, на
            сколько состарить въезд. Результат — в логе ниже и на «Сейчас на
            парковке».
          </p>
        </div>
      </div>

      {/* Лог */}
      <LogCard log={log} onClear={() => setLog([])} />
        </div>
      )}

      {tab === "kaspi" && (
        <div className="space-y-6">
          {/* Статус интеграции Kaspi */}
          <div className="card flex flex-wrap items-center gap-x-8 gap-y-3 p-5">
            <div>
              <div className="eyebrow">Kaspi.kz</div>
              <div className="mt-1 font-display text-lg font-semibold text-ink">
                Интеграция оплаты
              </div>
            </div>
            <TariffFact
              label="Активный провайдер"
              value={kaspiInfo.data?.payment_provider ?? "…"}
            />
            <TariffFact
              label="Онлайн-протокол"
              value={
                kaspiInfo.data
                  ? kaspiInfo.data.provider_enabled
                    ? "включён"
                    : "выключен"
                  : "…"
              }
            />
            <TariffFact
              label="Автосписание"
              value={
                kaspiInfo.data
                  ? kaspiInfo.data.autopay_enabled
                    ? "включено"
                    : "выключено"
                  : "…"
              }
            />
          </div>

          {/* Онлайн-протокол: оплата в приложении Kaspi по номеру авто */}
          <div className="card p-5">
            <div className="eyebrow">Онлайн-протокол · оплата по номеру</div>
            <p className="mt-1 text-sm text-ink-500/70">
              Эмулирует запросы, которые Kaspi шлёт нам, когда водитель платит в
              приложении: <b>check</b> — узнать сумму долга по номеру,{" "}
              <b>pay</b> — провести оплату (идемпотентно: повтор с тем же txn_id
              не спишет дважды).
            </p>
            <div className="mt-4">
              {owing.length === 0 ? (
                <p className="rounded-xl border border-dashed border-line py-8 text-center text-sm text-ink-500/50">
                  Долгов нет — оплачивать нечего
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
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => kaspiDoCheck(s)}
                          disabled={busy}
                          className="rounded-lg border border-line px-3 py-1.5 text-sm font-medium text-ink transition hover:border-sky disabled:opacity-50"
                        >
                          check
                        </button>
                        <button
                          onClick={() => kaspiDoPay(s, due)}
                          disabled={busy}
                          className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white transition hover:bg-brand-dark disabled:opacity-50"
                        >
                          pay
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* AutomaticPayments: автосписание при выезде */}
          <div className="card p-5">
            <div className="eyebrow">AutomaticPayments · автосписание</div>
            <p className="mt-1 text-sm text-ink-500/70">
              Пробный вызов Kaspi «exit» — что вернул бы банк при списании долга с
              привязанной карты. Реальное автосписание срабатывает при выезде,
              если включён <span className="font-mono">KASPI_AUTOPAY_ENABLED</span>.
            </p>
            <div className="mt-4">
              {owing.length === 0 ? (
                <p className="rounded-xl border border-dashed border-line py-8 text-center text-sm text-ink-500/50">
                  Долгов нет — списывать нечего
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
                      </div>
                      <button
                        onClick={() => kaspiDoSimulate(s)}
                        disabled={busy}
                        className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
                      >
                        Симулировать списание
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <LogCard log={log} onClear={() => setLog([])} />
        </div>
      )}

      {/* Окно оплаты (QR + mock-кнопка) — как на странице /pay */}
      {payTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-ink/50 backdrop-blur-sm"
            onClick={() => !paying && setPayTarget(null)}
          />
          <div className="relative w-full max-w-sm rounded-2xl bg-surface p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <div className="eyebrow">Оплата парковки</div>
              <button
                onClick={() => setPayTarget(null)}
                disabled={paying}
                className="text-lg text-ink-500/50 transition hover:text-ink disabled:opacity-40"
              >
                ✕
              </button>
            </div>
            <PaymentPanel
              plate={payTarget.session.plate_number}
              amount={payTarget.due}
              paidAmount={payTarget.session.paid_amount}
              onPay={() => payFor(payTarget.session)}
              paying={paying}
            />
          </div>
        </div>
      )}
    </div>
  );
}

// Лог событий стенда — общий для вкладок «КПП» и «Kaspi».
function LogCard({ log, onClear }: { log: LogRow[]; onClear: () => void }) {
  return (
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
            onClick={onClear}
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
              {row.note && (
                <span className="rounded bg-amber-50 px-1.5 py-0.5 font-mono text-[11px] text-amber-700">
                  {row.note}
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
  );
}

// Бейдж «оплачено / не оплачено» для карточки авто на парковке.
function PaidBadge({ session, tariff }: { session: ParkingSession; tariff: Tariff }) {
  const due = amountDue(session, tariff);
  if (due > 0.009) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
        ● не оплачено
      </span>
    );
  }
  if (session.paid_amount > 0) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
        ✓ оплачено
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">
      бесплатно
    </span>
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
