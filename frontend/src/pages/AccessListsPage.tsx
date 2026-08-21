import { useState } from "react";
import type { AccessEntry, AccessEntryInput, AccessListType } from "../api/types";
import {
  useAccessEntries,
  useAckAlert,
  useAlerts,
  useCreateAccessEntry,
  useDeleteAccessEntry,
  useGates,
  useUpdateAccessEntry,
} from "../api/hooks";
import { PlateReadout } from "../components/PlateReadout";
import { StatTile } from "../components/StatTile";
import { formatDateTime } from "../lib/format";

const LIST_META: Record<AccessListType, { label: string; cls: string; hint: string }> =
  {
    green: {
      label: "Зелёный",
      cls: "bg-emerald-100 text-emerald-700",
      hint: "всегда пускать, без оплаты (скорая, полиция, сотрудники)",
    },
    yellow: {
      label: "Жёлтый",
      cls: "bg-amber-100 text-amber-700",
      hint: "бесплатно до указанного времени, далее по тарифу (гости, брони)",
    },
    red: {
      label: "Красный",
      cls: "bg-rose-100 text-rose-700",
      hint: "не пускать + сигнал ответственному (мошенники)",
    },
  };

export function AccessListsPage() {
  const gates = useGates();
  const { data, isLoading } = useAccessEntries();
  const create = useCreateAccessEntry();
  const update = useUpdateAccessEntry();
  const del = useDeleteAccessEntry();
  const alerts = useAlerts();
  const ack = useAckAlert();

  const EMPTY = {
    plate: "",
    list_type: "green" as AccessListType,
    gate_id: "" as string,
    valid_until: "",
    note: "",
  };
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [fType, setFType] = useState<AccessListType | "">("");
  const [fPlate, setFPlate] = useState("");

  const busy = create.isPending || update.isPending;

  const gateName = (id: number | null) =>
    id == null ? "все шлагбаумы" : (gates.data?.find((g) => g.id === id)?.name ?? `#${id}`);

  const reset = () => {
    setForm(EMPTY);
    setEditId(null);
    setErr(null);
  };

  const startEdit = (en: AccessEntry) => {
    setEditId(en.id);
    setErr(null);
    setForm({
      plate: en.plate,
      list_type: en.list_type,
      gate_id: en.gate_id == null ? "" : String(en.gate_id),
      valid_until: en.valid_until ? en.valid_until.slice(0, 16) : "",
      note: en.note ?? "",
    });
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    const payload: AccessEntryInput = {
      plate: form.plate.trim(),
      list_type: form.list_type,
      gate_id: form.gate_id ? Number(form.gate_id) : null,
      valid_until:
        form.list_type === "yellow" && form.valid_until ? form.valid_until : null,
      note: form.note.trim() || null,
    };
    const onError = (e2: unknown) =>
      setErr(e2 instanceof Error ? e2.message : "Ошибка");
    if (editId != null) {
      update.mutate(
        { id: editId, patch: payload },
        { onSuccess: reset, onError },
      );
    } else {
      create.mutate(payload, { onSuccess: reset, onError });
    }
  };

  const remove = (en: AccessEntry) => {
    if (confirm(`Удалить ${en.plate} из ${LIST_META[en.list_type].label} списка?`))
      del.mutate(en.id);
  };

  const toggle = (en: AccessEntry) =>
    update.mutate({ id: en.id, patch: { is_active: !en.is_active } });

  const counts = (t: AccessListType) =>
    data?.filter((e) => e.list_type === t).length ?? 0;

  const rows = (data ?? []).filter(
    (e) =>
      (!fType || e.list_type === fType) &&
      (!fPlate || e.plate.includes(fPlate.toUpperCase().replace(/[^A-Z0-9]/g, ""))),
  );

  return (
    <div className="space-y-6">
      <div>
        <div className="eyebrow">Доступ</div>
        <h2 className="font-display text-xl font-semibold text-ink">
          Списки доступа
        </h2>
        <p className="mt-1 text-sm text-ink-500/70">
          Зелёный — бесплатный проезд; жёлтый — бесплатно до срока; красный — не
          пускать и сигнал. На конкретный шлагбаум или на все. Действия пишутся в
          аудит.
        </p>
      </div>

      {/* Сигналы по красному списку */}
      {(alerts.data?.length ?? 0) > 0 && (
        <div className="card border-rose-200 bg-rose-50 p-5">
          <div className="eyebrow text-rose-600">🚨 Красный список — сигнал</div>
          <ul className="mt-2 space-y-2">
            {alerts.data?.map((a) => (
              <li
                key={a.id}
                className="flex items-center gap-3 rounded-lg bg-surface px-3 py-2"
              >
                <PlateReadout plate={a.plate} size="sm" />
                <span className="text-sm text-rose-700">{a.message}</span>
                <span className="ml-auto font-mono text-[11px] text-ink-500/50">
                  {formatDateTime(a.created_at)}
                </span>
                <button
                  onClick={() => ack.mutate(a.id)}
                  disabled={ack.isPending}
                  className="rounded-md border border-rose-200 px-2.5 py-1 text-xs font-medium text-rose-600 transition hover:bg-rose-100 disabled:opacity-50"
                >
                  принято
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile eyebrow="Зелёный" value={counts("green")} hint="без оплаты" />
        <StatTile eyebrow="Жёлтый" value={counts("yellow")} hint="льгота по времени" />
        <StatTile eyebrow="Красный" value={counts("red")} hint="не пускать" />
      </div>

      {/* Форма */}
      <form onSubmit={submit} className="card space-y-4 p-5">
        <div className="flex items-center justify-between">
          <div className="eyebrow">
            {editId != null ? "Редактирование записи" : "Добавить в список"}
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
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Field label="Номер *">
            <input
              value={form.plate}
              onChange={(e) => setForm({ ...form, plate: e.target.value })}
              placeholder="127AST02"
              className="input w-full font-mono uppercase"
              required
            />
          </Field>
          <Field label="Список">
            <select
              value={form.list_type}
              onChange={(e) =>
                setForm({ ...form, list_type: e.target.value as AccessListType })
              }
              className="input w-full"
            >
              <option value="green">Зелёный</option>
              <option value="yellow">Жёлтый</option>
              <option value="red">Красный</option>
            </select>
          </Field>
          <Field label="Шлагбаум">
            <select
              value={form.gate_id}
              onChange={(e) => setForm({ ...form, gate_id: e.target.value })}
              className="input w-full"
            >
              <option value="">Все шлагбаумы</option>
              {gates.data?.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Бесплатно до (жёлтый)">
            <input
              type="datetime-local"
              value={form.valid_until}
              disabled={form.list_type !== "yellow"}
              onChange={(e) => setForm({ ...form, valid_until: e.target.value })}
              className="input w-full disabled:opacity-40"
            />
          </Field>
          <Field label="Заметка">
            <input
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
              placeholder="кто/зачем"
              className="input w-full"
            />
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={busy || !form.plate.trim()}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-dark disabled:opacity-50"
          >
            {busy
              ? "Сохранение…"
              : editId != null
                ? "Сохранить"
                : "Добавить"}
          </button>
          <span className="text-xs text-ink-500/50">
            {LIST_META[form.list_type].hint}
          </span>
          {err && <span className="text-sm text-rose-500">{err}</span>}
        </div>
      </form>

      {/* Фильтры */}
      <div className="card flex flex-wrap items-end gap-3 p-4">
        <Field label="Список">
          <select
            value={fType}
            onChange={(e) => setFType(e.target.value as AccessListType | "")}
            className="input"
          >
            <option value="">Все</option>
            <option value="green">Зелёный</option>
            <option value="yellow">Жёлтый</option>
            <option value="red">Красный</option>
          </select>
        </Field>
        <Field label="Номер">
          <input
            value={fPlate}
            onChange={(e) => setFPlate(e.target.value)}
            placeholder="поиск"
            className="input font-mono uppercase"
          />
        </Field>
        {(fType || fPlate) && (
          <button
            onClick={() => {
              setFType("");
              setFPlate("");
            }}
            className="rounded-lg border border-line px-3 py-1.5 text-sm text-ink-600 transition hover:border-sky"
          >
            Сбросить
          </button>
        )}
        <span className="ml-auto self-center text-xs text-ink-500/50">
          показано {rows.length} из {data?.length ?? 0}
        </span>
      </div>

      {/* Таблица */}
      <div className="card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-paper text-xs uppercase tracking-wide text-ink-500/60">
            <tr>
              <th className="px-4 py-3">Номер</th>
              <th className="px-4 py-3">Список</th>
              <th className="px-4 py-3">Шлагбаум</th>
              <th className="px-4 py-3">Бесплатно до</th>
              <th className="px-4 py-3">Заметка</th>
              <th className="px-4 py-3">Статус</th>
              <th className="px-4 py-3">Добавил</th>
              <th className="px-4 py-3 text-right">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {isLoading && (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-ink-500/50">
                  Загрузка…
                </td>
              </tr>
            )}
            {!isLoading && rows.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-ink-500/50">
                  {data?.length ? "Ничего не найдено" : "Списки пусты"}
                </td>
              </tr>
            )}
            {rows.map((en) => (
              <tr
                key={en.id}
                className={`animate-fade-up hover:bg-paper ${
                  en.is_active ? "" : "opacity-50"
                }`}
              >
                <td className="px-4 py-3">
                  <PlateReadout plate={en.plate} size="sm" />
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-medium ${LIST_META[en.list_type].cls}`}
                  >
                    {LIST_META[en.list_type].label}
                  </span>
                </td>
                <td className="px-4 py-3 text-ink-500/70">{gateName(en.gate_id)}</td>
                <td className="px-4 py-3 font-mono text-ink-500/70">
                  {en.valid_until ? formatDateTime(en.valid_until) : "—"}
                </td>
                <td className="px-4 py-3 text-ink-500/70">{en.note ?? "—"}</td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-medium ${
                      en.is_active
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-slate-100 text-slate-500"
                    }`}
                  >
                    {en.is_active ? "активна" : "выключена"}
                  </span>
                </td>
                <td className="px-4 py-3 text-ink-500/60">
                  {en.created_by_username ?? "—"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => startEdit(en)}
                      className="rounded-md border border-line px-2.5 py-1 text-xs font-medium text-ink-500/80 transition hover:border-sky hover:text-sky-700"
                    >
                      изменить
                    </button>
                    <button
                      onClick={() => toggle(en)}
                      disabled={update.isPending}
                      className="rounded-md border border-line px-2.5 py-1 text-xs font-medium text-ink-500/80 transition hover:border-sky disabled:opacity-50"
                    >
                      {en.is_active ? "выключить" : "включить"}
                    </button>
                    <button
                      onClick={() => remove(en)}
                      disabled={del.isPending}
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-ink-500/70">{label}</span>
      {children}
    </label>
  );
}
