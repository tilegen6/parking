"""analyze.py — разбор накопленных дампов из captures/.

Назначение: пройти по дампам, которые снял capture_server.py, и свести:
  * какие поля реально приходят (присутствие/заполненность);
  * есть ли direction (ENTRY/EXIT) или его придётся выводить по каналу;
  * повторные срабатывания одной машины (дубли) и интервалы между ними;
  * разброс confidence (для оценки ночь/день).

Закрывает задачи Integration/Hikvision #4 (повторные срабатывания) и
готовит факты для #11 (зафиксировать кейсы для backend).

Запуск:
    python analyze.py captures/
    python analyze.py captures/ --dups-window 10   # окно дублей, секунд
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import TypedDict


class AnalysisReport(TypedDict):
    captures_dir: str
    total_events: int
    field_presence: dict[str, int]
    direction_breakdown: dict[str, int]
    event_type_breakdown: dict[str, int]
    confidence_stats: dict[str, float]
    duplicates_window_s: float
    duplicates_found: int
    duplicates: list[dict[str, object]]
    direction_available: bool


# Поля, присутствие которых мы отслеживаем в summary.json
TRACKED = [
    "plate_number",
    "direction",
    "event_time",
    "confidence",
    "camera_name",
    "event_type",
]


def _load_summaries(root: Path) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for sf in sorted(root.glob("*/summary.json")):
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            data["_dir"] = sf.parent.name
            out.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"! пропуск {sf}: {exc}", file=sys.stderr)
    return out


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _find_duplicates(
    events: list[dict[str, object]], window_s: float
) -> list[dict[str, object]]:
    """Сгруппировать события по номеру и найти срабатывания в пределах окна."""
    by_plate: dict[str, list[datetime]] = defaultdict(list)
    for ev in events:
        plate = ev.get("plate_number")
        t = _parse_time(ev.get("event_time"))
        if isinstance(plate, str) and plate and t:
            by_plate[plate].append(t)

    dups: list[dict[str, object]] = []
    for plate, times in by_plate.items():
        times.sort()
        for prev, cur in zip(times, times[1:]):
            gap = (cur - prev).total_seconds()
            if gap <= window_s:
                dups.append(
                    {"plate": plate, "gap_s": round(gap, 2), "at": cur.isoformat()}
                )
    return dups


def analyze(root: Path, window_s: float) -> AnalysisReport:
    events = _load_summaries(root)
    n = len(events)

    presence = {f: sum(1 for e in events if e.get(f)) for f in TRACKED}
    directions = Counter(str(e.get("direction") or "MISSING") for e in events)
    event_types = Counter(str(e.get("event_type") or "MISSING") for e in events)

    confidences = []
    for e in events:
        try:
            confidences.append(float(str(e.get("confidence"))))
        except (TypeError, ValueError):
            pass
    conf_stats: dict[str, float] = {}
    if confidences:
        conf_stats = {
            "count": len(confidences),
            "min": min(confidences),
            "max": max(confidences),
            "avg": round(sum(confidences) / len(confidences), 2),
        }

    dups = _find_duplicates(events, window_s)

    return {
        "captures_dir": str(root),
        "total_events": n,
        "field_presence": presence,
        "direction_breakdown": dict(directions),
        "event_type_breakdown": dict(event_types),
        "confidence_stats": conf_stats,
        "duplicates_window_s": window_s,
        "duplicates_found": len(dups),
        "duplicates": dups[:50],
        "direction_available": directions.get("MISSING", 0) < n if n else False,
    }


def _print_report(rep: AnalysisReport) -> None:
    print(f"\n=== ANALYZE {rep['captures_dir']} ===")
    print(f"Событий всего: {rep['total_events']}")
    if not rep["total_events"]:
        print("Дампов нет. Сначала сними трафик: python capture_server.py")
        return
    print("\nЗаполненность полей:")
    for f, c in rep["field_presence"].items():
        print(f"  {f:<14} {c}/{rep['total_events']}")
    print(f"\nНаправления: {rep['direction_breakdown']}")
    print(f"Типы событий: {rep['event_type_breakdown']}")
    print(f"Confidence: {rep['confidence_stats'] or 'нет данных'}")
    print(
        f"\nDirection присылается камерой: "
        f"{'ДА' if rep['direction_available'] else 'НЕТ — выводить по каналу/IP'}"
    )
    print(f"Дубли (<= {rep['duplicates_window_s']}s): {rep['duplicates_found']}")
    for d in rep["duplicates"]:
        print(f"  {d['plate']}  +{d['gap_s']}s  @ {d['at']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Hikvision captures")
    parser.add_argument(
        "captures", nargs="?", default="captures", help="каталог дампов"
    )
    parser.add_argument(
        "--dups-window", type=float, default=10.0, help="окно дублей, сек"
    )
    parser.add_argument("--json", action="store_true", help="вывести отчёт как JSON")
    args = parser.parse_args()

    root = Path(args.captures)
    if not root.exists():
        print(f"Нет каталога {root}", file=sys.stderr)
        return 1

    rep = analyze(root, args.dups_window)
    if args.json:
        print(json.dumps(rep, indent=2, ensure_ascii=False))
    else:
        _print_report(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
