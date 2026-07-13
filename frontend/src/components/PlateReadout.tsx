// Сигнатура интерфейса: распознанный номер показывается как настоящий
// казахстанский знак — белая пластина, моно-символы, синяя полоса «KZ» с флагом.

type Size = "lg" | "md" | "sm";

const SIZES: Record<
  Size,
  { text: string; pad: string; band: string; kz: string; dot: string }
> = {
  lg: {
    text: "text-[2rem]",
    pad: "px-4 py-2",
    band: "w-11",
    kz: "text-xs",
    dot: "h-2.5 w-2.5",
  },
  md: {
    text: "text-xl",
    pad: "px-3 py-1.5",
    band: "w-9",
    kz: "text-[10px]",
    dot: "h-2 w-2",
  },
  sm: {
    text: "text-sm",
    pad: "px-2 py-1",
    band: "w-7",
    kz: "text-[8px]",
    dot: "h-1.5 w-1.5",
  },
};

function formatPlate(plate: string): string {
  const c = plate.toUpperCase();
  // KZ-формат NNNLLLNN: отделяем код региона тонким пробелом (123ABC 02)
  if (/^\d{3}[A-Z]{3}\d{2}$/.test(c)) {
    return c.slice(0, 6) + " " + c.slice(6);
  }
  return c;
}

export function PlateReadout({
  plate,
  size = "md",
}: {
  plate: string | null | undefined;
  size?: Size;
}) {
  const s = SIZES[size];
  return (
    <div className="inline-flex select-none overflow-hidden rounded-md bg-white shadow-sm ring-2 ring-ink/85">
      <div
        className={`flex items-center font-mono font-extrabold tracking-[0.1em] text-ink ${s.text} ${s.pad}`}
      >
        {plate ? (
          formatPlate(plate)
        ) : (
          <span className="font-sans text-sm font-medium tracking-normal text-ink/30">
            не распознан
          </span>
        )}
      </div>
      <div
        className={`flex flex-col items-center justify-center gap-1 bg-sky text-white ${s.band}`}
        aria-hidden
      >
        <span
          className={`block rounded-full bg-gold shadow-[0_0_0_2px_rgba(255,255,255,0.3)] ${s.dot}`}
        />
        <span className={`font-mono font-bold leading-none ${s.kz}`}>KZ</span>
      </div>
    </div>
  );
}
