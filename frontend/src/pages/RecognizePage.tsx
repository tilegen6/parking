import { useCallback, useEffect, useState } from "react";
import {
  getPipelineVersions,
  recognizePlate,
  type PipelineOption,
  type RecognizeResult,
} from "../api/cv";
import { PlateReadout } from "../components/PlateReadout";
import { StatTile } from "../components/StatTile";
import { formatConfidence } from "../lib/format";

export function RecognizePage() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<RecognizeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [threshold, setThreshold] = useState(0.4);
  // Две независимые оси: детектор (находит номер) и OCR (читает символы).
  const [detectors, setDetectors] = useState<PipelineOption[]>([]);
  const [engines, setEngines] = useState<PipelineOption[]>([]);
  const [detector, setDetector] = useState("plate");
  const [engine, setEngine] = useState("fastplate");

  // каталог осей пайплайна с сервиса (для выпадающих списков)
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

  const pick = (f: File | null) => {
    setFile(f);
    setResult(null);
    setError(null);
  };

  const recognize = useCallback(
    async (f: File, eng: string, det: string) => {
      setLoading(true);
      setError(null);
      try {
        setResult(await recognizePlate(f, { engine: eng, detector: det }));
      } catch (e) {
        setError(
          e instanceof Error
            ? `${e.message}. Запущен ли CV-сервис? (python cv/service.py)`
            : "Ошибка распознавания",
        );
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const run = () => {
    if (file) recognize(file, engine, detector);
  };

  // Вставка фото из буфера обмена (Ctrl+V / Cmd+V) — где угодно на странице
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      for (const it of Array.from(items)) {
        if (it.type.startsWith("image/")) {
          const f = it.getAsFile();
          if (f) {
            e.preventDefault();
            setFile(f);
            setResult(null);
            recognize(f, engine, detector);
          }
          return;
        }
      }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [recognize, engine, detector]);

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
              Перетащите фото, вставьте из буфера (Ctrl/Cmd+V) или нажмите, чтобы
              выбрать
            </span>
          )}
          <input
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
          />
        </label>

        {(detectors.length > 0 || engines.length > 0) && (
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-ink-500/70">
                Детектор (находит номер)
              </span>
              <select
                value={detector}
                onChange={(e) => setDetector(e.target.value)}
                title={detectors.find((d) => d.name === detector)?.desc}
                className="w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink transition focus:border-sky focus:outline-none"
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
                title={engines.find((en) => en.name === engine)?.desc}
                className="w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink transition focus:border-sky focus:outline-none"
              >
                {engines.map((en) => (
                  <option key={en.name} value={en.name} disabled={!en.available}>
                    {en.label}
                    {en.available ? "" : " — не установлен"}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}

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

        <label className="block">
          <span className="mb-1 block text-xs font-medium text-ink-500/70">
            Порог уверенности:{" "}
            <span className="font-mono text-ink">{threshold.toFixed(2)}</span>
          </span>
          <input
            type="range"
            min={0.1}
            max={0.95}
            step={0.05}
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            className="w-full max-w-xs accent-sky"
          />
        </label>
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
                <ConfBadge
                  ok={result.confidence != null && result.confidence >= threshold}
                />
              </div>
              {result.version && (
                <p className="mt-2 text-xs text-ink-500/60">
                  Версия:{" "}
                  <span className="font-mono text-ink-500/80">
                    {result.version}
                  </span>{" "}
                  · {result.engine}/{result.detector}
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <StatTile
                eyebrow="Уверенность"
                value={formatConfidence(result.confidence)}
                hint={`порог ${Math.round(threshold * 100)}%`}
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

function ConfBadge({ ok }: { ok: boolean }) {
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-medium ${
        ok ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
      }`}
    >
      {ok ? "распознан" : "низкая уверенность"}
    </span>
  );
}
