// Миниатюра фото в таблице. По клику открывает модалку (через onOpen).

export function Thumb({
  url,
  alt,
  onOpen,
}: {
  url: string | null;
  alt: string;
  onOpen: (url: string) => void;
}) {
  if (!url) {
    return <span className="text-xs text-slate-400">нет фото</span>;
  }
  return (
    <button
      onClick={() => onOpen(url)}
      className="block h-12 w-16 overflow-hidden rounded border border-slate-200 transition hover:ring-2 hover:ring-brand"
    >
      <img src={url} alt={alt} className="h-full w-full object-cover" />
    </button>
  );
}
