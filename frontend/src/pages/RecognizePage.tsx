import { useState } from "react";
import { recognizePlate, type RecognizeResult } from "../api/cv";
import { PlateReadout } from "../components/PlateReadout";
import { StatTile } from "../components/StatTile";
import { formatConfidence } from "../lib/format";

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
        <div className="eyebrow">Тестирование</div>
        <h2 className="font-display text-xl font-semibold text-ink">
          Тест распознавания
        </h2>
        <p className="mt-1 text-sm text-ink-500/70">
          Загрузите фото номера — CV-сервис вернёт распознанный знак с рамкой.
          Сервис:{" "}
          <code className="rounded bg-paper px-1.5 py-0.5 font-mono text-xs text-ink-500/70">
            python cv/service.py
          </code>
        </p>
      </div>

      {/* Загрузка фото */}
      <div className="card space-y-4 p-5">
        <div className="eyebrow">Фото с КПП</div>

        <label
          className="flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-line bg-paper px-6 py-12 text-center text-ink-500/60 transition hover:border-sky hover:text-ink-500/80"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            pick(e.dataTransfer.files?.[0] ?? null);
          }}
        >
          <span className="text-3xl">📷</span>
          {file ? (
            <span className="font-mono text-sm font-medium text-ink">
              {file.name}
            </span>
          ) : (
            <span className="text-sm">
              Перетащите фото сюда или нажмите, чтобы выбрать
            </span>
          )}
          <input
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
          />
        </label>

        <div className="flex items-center gap-3">
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
          {/* Результат распознавания */}
          <div className="card space-y-5 p-5">
            <div>
              <div className="eyebrow">Распознанный номер</div>
              <div className="mt-3">
                <PlateReadout plate={result.plate_number} size="lg" />
              </div>
              <div className="mt-3">
                <FlagBadge flag={result.flag} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <StatTile
                eyebrow="Уверенность"
                value={formatConfidence(result.confidence)}
                hint="порог распознавания 85%"
              />
              <StatTile
                eyebrow="Валидность KZ"
                value={result.is_valid ? "ДА" : "НЕТ"}
                hint="формат NNNLLLNN"
              />
            </div>

            {result.candidates.length > 1 && (
              <div>
                <div className="eyebrow mb-2">Также найдено на фото</div>
                <div className="flex flex-wrap gap-2">
                  {result.candidates.map((c, i) => (
                    <PlateReadout key={`${c}-${i}`} plate={c} size="sm" />
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Размеченное фото */}
          <div className="card overflow-hidden p-2">
            <img
              src={result.annotated_image}
              alt="Размеченное фото"
              className="w-full rounded-xl"
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
