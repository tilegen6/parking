import { useState } from "react";
import { recognizePlate, type RecognizeResult } from "../api/cv";

export function RecognizePage() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<RecognizeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pick = (f: File | null) => {
    setFile(f);
    setResult(null);
    setError(null);
  };

  const run = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      setResult(await recognizePlate(file));
    } catch (e) {
      setError(
        e instanceof Error
          ? `${e.message}. Запущен ли CV-сервис? (python cv/service.py)`
          : "Ошибка распознавания",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Тест распознавания</h2>
        <p className="text-sm text-slate-500">
          Загрузите фото номера — CV-сервис вернёт распознанный номер с рамкой.
          Сервис:{" "}
          <code className="rounded bg-slate-100 px-1">python cv/service.py</code>
        </p>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <label
          className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-slate-300 px-6 py-10 text-center text-slate-500 transition hover:border-brand"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            pick(e.dataTransfer.files?.[0] ?? null);
          }}
        >
          <span className="text-3xl">📷</span>
          {file ? (
            <span className="font-medium text-slate-700">{file.name}</span>
          ) : (
            <span>Перетащите фото сюда или нажмите, чтобы выбрать</span>
          )}
          <input
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
          />
        </label>
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={run}
            disabled={!file || loading}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-dark disabled:opacity-50"
          >
            {loading ? "Распознаю…" : "Распознать"}
          </button>
          {error && <span className="text-sm text-rose-500">{error}</span>}
        </div>
      </div>

      {result && (
        <div className="grid gap-6 md:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="text-xs uppercase text-slate-400">Номер</div>
            <div className="mt-1 text-3xl font-bold tracking-wide text-slate-800">
              {result.plate_number ?? "НЕ РАСПОЗНАН"}
            </div>
            <div className="mt-3 flex items-center gap-2">
              <FlagBadge flag={result.flag} />
              {result.confidence != null && (
                <span className="text-sm text-slate-500">
                  confidence {(result.confidence * 100).toFixed(0)}%
                </span>
              )}
            </div>
            {result.candidates.length > 1 && (
              <div className="mt-4 text-sm text-slate-500">
                Также найдено на фото: {result.candidates.join(", ")}
              </div>
            )}
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-2">
            <img
              src={result.annotated_image}
              alt="Размеченное фото"
              className="w-full rounded-lg"
            />
          </div>
        </div>
      )}
    </div>
  );
}

function FlagBadge({ flag }: { flag: string }) {
  const ok = flag === "ok";
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-medium ${
        ok ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
      }`}
    >
      {ok ? "распознан" : "low_confidence"}
    </span>
  );
}
