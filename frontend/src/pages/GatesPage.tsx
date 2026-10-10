import { useState } from "react";
import {
  useCreateGate,
  useDeleteGate,
  useGates,
  useUpdateGate,
} from "../api/hooks";
import type { Gate, GateInput } from "../api/types";
import { StatTile } from "../components/StatTile";

interface FormState {
  name: string;
  zone: string;
  level: string;
  is_active: boolean;
}

const EMPTY: FormState = { name: "", zone: "", level: "1", is_active: true };

export function GatesPage() {
  const { data, isLoading, isError } = useGates();
  const createGate = useCreateGate();
  const updateGate = useUpdateGate();
  const deleteGate = useDeleteGate();

  const [form, setForm] = useState<FormState>(EMPTY);
  const [editId, setEditId] = useState<number | null>(null);

  const busy = createGate.isPending || updateGate.isPending;

  const reset = () => {
    setForm(EMPTY);
    setEditId(null);
  };

  const startEdit = (g: Gate) => {
    setEditId(g.id);
    setForm({
      name: g.name,
      zone: g.zone ?? "",
      level: String(g.level),
      is_active: g.is_active,
    });
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    const payload: GateInput = {
      name: form.name.trim(),
      zone: form.zone.trim() || null,
      level: Number(form.level) || 1,
      is_active: form.is_active,
    };
    if (editId != null) {
      updateGate.mutate({ id: editId, patch: payload }, { onSuccess: reset });
    } else {
      createGate.mutate(payload, { onSuccess: reset });
    }
  };

  const remove = (g: Gate) => {
    if (confirm(`Удалить шлагбаум «${g.name}»? Камеры/сессии останутся без зоны.`))
      deleteGate.mutate(g.id);
  };

  const total = data?.length ?? 0;
  const zones = new Set((data ?? []).map((g) => g.zone).filter(Boolean)).size;

  return (
    <div className="space-y-6">
      <div>
        <div className="eyebrow">Инфраструктура</div>
        <h2 className="font-display text-xl font-semibold text-ink">Шлагбаумы</h2>
        <p className="mt-1 text-sm text-ink-500/70">
          Точки доступа с зонами. Камеры и сессии привязываются к шлагбауму —
          учёт раздельный. Уровень 1 — внешний КПП, 2 — внутренний (напр. отель).
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile
          eyebrow="Всего шлагбаумов"
          value={isLoading ? "…" : total}
          hint="в системе"
        />
        <StatTile eyebrow="Зон" value={isLoading ? "…" : zones} hint="уникальных" />
        <StatTile
          eyebrow="Активных"
          value={isLoading ? "…" : (data?.filter((g) => g.is_active).length ?? 0)}
          hint="работают"
        />
      </div>

      {/* Форма */}
      <form onSubmit={submit} className="card space-y-4 p-5">
        <div className="flex items-center justify-between">
          <div className="eyebrow">
            {editId != null ? "Редактирование шлагбаума" : "Новый шлагбаум"}
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

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Название *">
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="КПП двор"
              className="input w-full"
              required
            />
          </Field>
          <Field label="Зона">
            <input
              value={form.zone}
              onChange={(e) => setForm({ ...form, zone: e.target.value })}
              placeholder="Двор / Отель"
              className="input w-full"
            />
          </Field>
          <Field label="Уровень">
            <select
              value={form.level}
              onChange={(e) => setForm({ ...form, level: e.target.value })}
              className="input w-full"
            >
              <option value="1">1 — внешний КПП</option>
              <option value="2">2 — внутренний</option>
            </select>
          </Field>
          <label className="flex items-end gap-2 pb-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              className="h-4 w-4 accent-sky"
            />
            <span className="text-ink-500/80">Активен</span>
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={busy || !form.name.trim()}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-dark disabled:opacity-50"
          >
            {busy
              ? "Сохранение…"
              : editId != null
                ? "Сохранить изменения"
                : "Создать шлагбаум"}
          </button>
          {(createGate.isError || updateGate.isError) && (
            <span className="text-sm text-rose-500">
              Ошибка сохранения — запущен ли backend?
            </span>
          )}
        </div>
      </form>

      {/* Таблица */}
      <div className="card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-paper text-xs uppercase tracking-wide text-ink-500/60">
            <tr>
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3">Название</th>
              <th className="px-4 py-3">Зона</th>
              <th className="px-4 py-3">Уровень</th>
              <th className="px-4 py-3">Статус</th>
              <th className="px-4 py-3 text-right">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {isLoading && <Row text="Загрузка…" />}
            {isError && <Row text="Ошибка загрузки — запущен ли backend?" error />}
            {!isLoading && data?.length === 0 && (
              <Row text="Шлагбаумы ещё не созданы" />
            )}
            {data?.map((g) => (
              <tr key={g.id} className="animate-fade-up hover:bg-paper">
                <td className="px-4 py-3 font-mono text-ink-500/70">{g.id}</td>
                <td className="px-4 py-3 font-medium text-ink">{g.name}</td>
                <td className="px-4 py-3 text-ink-500/70">{g.zone ?? "—"}</td>
                <td className="px-4 py-3">
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                    ур. {g.level}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <ActiveBadge active={g.is_active} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => startEdit(g)}
                      className="rounded-md border border-line px-2.5 py-1 text-xs font-medium text-ink-500/80 transition hover:border-sky hover:text-sky-700"
                    >
                      изменить
                    </button>
                    <button
                      onClick={() => remove(g)}
                      disabled={deleteGate.isPending}
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

function Row({ text, error }: { text: string; error?: boolean }) {
  return (
    <tr>
      <td
        colSpan={6}
        className={`px-4 py-12 text-center ${
          error ? "text-rose-500" : "text-ink-500/50"
        }`}
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
      {active ? "активен" : "выключен"}
    </span>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-ink-500/70">{label}</span>
      {children}
    </label>
  );
}
