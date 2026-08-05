import { useState } from "react";
import {
  useCreateTariff,
  useDeleteTariff,
  useTariffs,
  useUpdateTariff,
} from "../api/hooks";
import type { Tariff, TariffInput } from "../api/types";
import { StatTile } from "../components/StatTile";
import { formatMoney } from "../lib/tariff";

interface FormState {
  name: string;
  free_minutes: string;
  price_per_hour: string;
  daily_cap: string;
  currency: string;
  is_active: boolean;
}

const EMPTY: FormState = {
  name: "",
  free_minutes: "15",
  price_per_hour: "",
  daily_cap: "",
  currency: "KZT",
  is_active: true,
};

export function TariffsPage() {
  const { data, isLoading, isError } = useTariffs();
  const createTariff = useCreateTariff();
  const updateTariff = useUpdateTariff();
  const deleteTariff = useDeleteTariff();

  const [form, setForm] = useState<FormState>(EMPTY);
  const [editId, setEditId] = useState<number | null>(null);

  const busy = createTariff.isPending || updateTariff.isPending;

  const reset = () => {
    setForm(EMPTY);
    setEditId(null);
  };

  const startEdit = (t: Tariff) => {
    setEditId(t.id);
    setForm({
      name: t.name,
      free_minutes: String(t.free_minutes),
      price_per_hour: String(t.price_per_hour),
      daily_cap: t.daily_cap == null ? "" : String(t.daily_cap),
      currency: t.currency,
      is_active: t.is_active,
    });
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() || form.price_per_hour === "") return;
    const payload: TariffInput = {
      name: form.name.trim(),
      free_minutes: Number(form.free_minutes) || 0,
      price_per_hour: Number(form.price_per_hour) || 0,
      daily_cap: form.daily_cap.trim() === "" ? null : Number(form.daily_cap),
      currency: form.currency.trim() || "KZT",
      is_active: form.is_active,
    };
    if (editId != null) {
      updateTariff.mutate({ id: editId, patch: payload }, { onSuccess: reset });
    } else {
      createTariff.mutate(payload, { onSuccess: reset });
    }
  };

  const remove = (t: Tariff) => {
    if (confirm(`Удалить тариф «${t.name}»?`)) deleteTariff.mutate(t.id);
  };

  const total = data?.length ?? 0;
  const active = data?.find((t) => t.is_active) ?? null;

  return (
    <div className="space-y-6">
      <div>
        <div className="eyebrow">Биллинг</div>
        <h2 className="font-display text-xl font-semibold text-ink">Тарифы</h2>
        <p className="mt-1 text-sm text-ink-500/70">
          Правила расчёта стоимости парковки: бесплатный период, цена за час и
          максимум за сутки. Активный тариф применяется к сессиям.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile
          eyebrow="Всего тарифов"
          value={isLoading ? "…" : total}
          hint="в системе"
        />
        <StatTile
          eyebrow="Активный тариф"
          value={active ? active.name : "—"}
          hint={active ? "применяется к сессиям" : "нет активного"}
        />
        <StatTile
          eyebrow="Цена за час"
          value={active ? formatMoney(active.price_per_hour, active.currency) : "—"}
          hint={active ? `первые ${active.free_minutes} мин бесплатно` : ""}
        />
      </div>

      {/* Форма создания / редактирования */}
      <form onSubmit={submit} className="card space-y-4 p-5">
        <div className="flex items-center justify-between">
          <div className="eyebrow">
            {editId != null ? "Редактирование тарифа" : "Новый тариф"}
          </div>
          {editId != null && (
            <button
              type="button"
              onClick={reset}
              className="text-xs text-ink-500/60 hover:text-sky-700"
            >
              отменить
            </button>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Название *">
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Стандартный"
              className="input w-full"
              required
            />
          </Field>
          <Field label="Бесплатно, мин">
            <input
              type="number"
              min={0}
              value={form.free_minutes}
              onChange={(e) => setForm({ ...form, free_minutes: e.target.value })}
              className="input w-full font-mono"
            />
          </Field>
          <Field label="Цена за час *">
            <input
              type="number"
              min={0}
              value={form.price_per_hour}
              onChange={(e) =>
                setForm({ ...form, price_per_hour: e.target.value })
              }
              placeholder="200"
              className="input w-full font-mono"
              required
            />
          </Field>
          <Field label="Максимум за сутки">
            <input
              type="number"
              min={0}
              value={form.daily_cap}
              onChange={(e) => setForm({ ...form, daily_cap: e.target.value })}
              placeholder="без ограничения"
              className="input w-full font-mono"
            />
          </Field>
          <Field label="Валюта">
            <input
              value={form.currency}
              onChange={(e) => setForm({ ...form, currency: e.target.value })}
              className="input w-full font-mono uppercase"
            />
          </Field>
          <label className="flex items-end gap-2 pb-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              className="h-4 w-4 accent-sky"
            />
            <span className="text-ink-500/80">Активный тариф</span>
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={busy || !form.name.trim() || form.price_per_hour === ""}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-dark disabled:opacity-50"
          >
            {busy
              ? "Сохранение…"
              : editId != null
                ? "Сохранить изменения"
                : "Создать тариф"}
          </button>
          {(createTariff.isError || updateTariff.isError) && (
            <span className="text-sm text-rose-500">
              Ошибка сохранения — запущен ли backend?
            </span>
          )}
        </div>
      </form>

      {/* Таблица тарифов */}
      <div className="card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-paper text-xs uppercase tracking-wide text-ink-500/60">
            <tr>
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3">Название</th>
              <th className="px-4 py-3">Беспл., мин</th>
              <th className="px-4 py-3">Цена / час</th>
              <th className="px-4 py-3">Макс / сутки</th>
              <th className="px-4 py-3">Статус</th>
              <th className="px-4 py-3 text-right">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {isLoading && (
              <Row colSpan={7} text="Загрузка…" muted />
            )}
            {isError && (
              <Row colSpan={7} text="Ошибка загрузки — запущен ли backend?" error />
            )}
            {!isLoading && data?.length === 0 && (
              <Row colSpan={7} text="Тарифы ещё не созданы" muted />
            )}
            {data?.map((t) => (
              <tr key={t.id} className="animate-fade-up hover:bg-paper">
                <td className="px-4 py-3 font-mono text-ink-500/70">{t.id}</td>
                <td className="px-4 py-3 font-medium text-ink">{t.name}</td>
                <td className="px-4 py-3 font-mono text-ink-500/70">
                  {t.free_minutes}
                </td>
                <td className="px-4 py-3 font-mono text-ink">
                  {formatMoney(t.price_per_hour, t.currency)}
                </td>
                <td className="px-4 py-3 font-mono text-ink-500/70">
                  {t.daily_cap == null ? "—" : formatMoney(t.daily_cap, t.currency)}
                </td>
                <td className="px-4 py-3">
                  <ActiveBadge active={t.is_active} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => startEdit(t)}
                      className="rounded-md border border-line px-2.5 py-1 text-xs font-medium text-ink-500/80 transition hover:border-sky hover:text-sky-700"
                    >
                      изменить
                    </button>
                    <button
                      onClick={() => remove(t)}
                      disabled={deleteTariff.isPending}
                      className="rounded-md border border-line px-2.5 py-1 text-xs font-medium text-rose-600 transition hover:border-rose-300 hover:bg-rose-50 disabled:opacity-50"
                    >
                      удалить
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Row({
  colSpan,
  text,
  muted,
  error,
}: {
  colSpan: number;
  text: string;
  muted?: boolean;
  error?: boolean;
}) {
  return (
    <tr>
      <td
        colSpan={colSpan}
        className={`px-4 py-12 text-center ${
          error ? "text-rose-500" : "text-ink-500/50"
        } ${muted ? "" : ""}`}
      >
        {text}
      </td>
    </tr>
  );
}

function ActiveBadge({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium ${
        active ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"
      }`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {active ? "активный" : "выключен"}
    </span>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-ink-500/70">{label}</span>
      {children}
    </label>
  );
}
