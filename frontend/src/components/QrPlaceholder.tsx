// Декоративный «QR» (не сканируется) — просто для вида на экране оплаты.
// Узор детерминирован по value, с угловыми «глазами» как у настоящего QR.

export function QrPlaceholder({
  value,
  size = 168,
}: {
  value: string;
  size?: number;
}) {
  const N = 25;
  const cell = size / N;

  // Псевдослучайный генератор с сидом из value (стабильный узор)
  let h = 2166136261;
  for (let i = 0; i < value.length; i++) {
    h = (h ^ value.charCodeAt(i)) >>> 0;
    h = (h * 16777619) >>> 0;
  }
  const rng = () => {
    h = (h * 1103515245 + 12345) >>> 0;
    return h / 0xffffffff;
  };

  const finder = (x: number, y: number): boolean | null => {
    const local = (bx: number, by: number): boolean | null => {
      const lx = x - bx;
      const ly = y - by;
      if (lx < 0 || lx > 6 || ly < 0 || ly > 6) return null;
      const ring = lx === 0 || lx === 6 || ly === 0 || ly === 6;
      const center = lx >= 2 && lx <= 4 && ly >= 2 && ly <= 4;
      return ring || center;
    };
    return local(0, 0) ?? local(N - 7, 0) ?? local(0, N - 7);
  };

  const rects: React.ReactNode[] = [];
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const f = finder(x, y);
      const fill = f !== null ? f : rng() > 0.52;
      if (fill) {
        rects.push(
          <rect
            key={`${x}-${y}`}
            x={x * cell}
            y={y * cell}
            width={cell}
            height={cell}
          />,
        );
      }
    }
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="rounded-lg bg-white p-2 text-ink shadow-inner ring-1 ring-line"
      fill="currentColor"
      aria-label="QR для оплаты (демо)"
    >
      {rects}
    </svg>
  );
}
