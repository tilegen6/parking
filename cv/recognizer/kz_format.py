"""Приведение распознанного номера к казахстанскому формату.

Зачем. OCR путает символы, похожие начертанием: `O` и `0`, `I` и `1`, `S` и `5`.
Порогом уверенности это не лечится — модель выдаёт неверный символ с
уверенностью 0.97 (замеры в experiments/fast-alpr/README.md). Зато у номеров
РК позиции символов known заранее: в `237BLM01` первые три места — только
цифры, следующие три — только буквы. Значит `O` на цифровой позиции
однозначно `0`, а `0` на буквенной — `O`.

Модуль чистый: без cv2, без сети, без состояния. Всё решается на строке.
"""

from __future__ import annotations

from dataclasses import dataclass

# Коды регионов РК: 01 Астана, 02 Алматы, ... 20 Улытауская область.
# Последние две цифры номера — это область, и они не бывают больше 20.
# Ещё одна жёсткая проверка: `O1` в конце — гарантированно `01`.
VALID_REGIONS: frozenset[str] = frozenset(f"{i:02d}" for i in range(1, 21))

# Что во что превращать, когда позиция требует ЦИФРУ, а OCR отдал букву.
LETTER_TO_DIGIT: dict[str, str] = {
    "O": "0",
    "Q": "0",
    "D": "0",
    "I": "1",
    "L": "1",
    "Z": "2",
    "A": "4",
    "S": "5",
    "G": "6",
    "T": "7",
    "B": "8",
}

# Обратное направление: позиция требует БУКВУ, а OCR отдал цифру.
# Для `0` кандидатов несколько (O/Q/D) — берём самый частый по начертанию.
DIGIT_TO_LETTER: dict[str, str] = {
    "0": "O",
    "1": "I",
    "2": "Z",
    "4": "A",
    "5": "S",
    "6": "G",
    "7": "T",
    "8": "B",
}

# Сколько символов готовы поправить.
#
# Три, а не два: путаница начертаний СИСТЕМНАЯ. Модель, которая читает `0`
# как `O`, делает это по всему номеру сразу — у `AQ00301` три нуля, значит
# три ошибки в одном чтении. Лимит в две правки отсекал именно тот случай,
# ради которого модуль и написан.
#
# Риск перекоса при этом мал: заменять разрешено ТОЛЬКО пары из таблиц ниже
# (`W` цифрой стать не может), а сверху ещё работают длина шаблона и код
# региона. Четыре и больше правок — это уже другой номер, а не помарка.
MAX_CORRECTIONS = 3

# Ниже какой уверенности символ разрешено править.
#
# Замеры на реальных фото показали главную опасность: маппер уверенно
# переписывал символы, в которых OCR не сомневался, и выдавал выдумку с
# отметкой «достоверно». Если модель на 0.99 читает `B`, превращать его
# в `8` нельзя — ошибка не в начертании, а где-то раньше (номер обрезан,
# двухрядный прочитан не в том порядке, вставился лишний символ).
# Правим только то, в чём модель сама не уверена.
CORRECT_BELOW_CONFIDENCE = 0.90


@dataclass(frozen=True)
class PlateFormat:
    """Шаблон номера. `D` — цифра, `L` — буква."""

    pattern: str
    name: str
    # Последние две цифры — код региона. У старых советских и у жёлтых
    # с шестизначным номером региона нет, там проверку включать нельзя.
    has_region: bool

    def __len__(self) -> int:
        return len(self.pattern)


# Базовый набор, подтверждённый по фото образцов.
# Порядок важен: при равной стоимости правок побеждает тот, что выше.
FORMATS: tuple[PlateFormat, ...] = (
    PlateFormat("DDDLLLDD", "классический", has_region=True),  # 237BLM01
    PlateFormat("DDDLLDD", "классический короткий", has_region=True),  # 040BS01
    PlateFormat("LLDDDDD", "новый", has_region=True),  # AQ00301
    PlateFormat("LDDDLLL", "старый", has_region=False),  # A724CBM
    PlateFormat("LDDDDDD", "жёлтый/дипломатический", has_region=False),  # H444501
)

# Статусы разбора.
STATUS_OK = "ok"  # совпало без правок
STATUS_CORRECTED = "corrected"  # подошло после замены символов
STATUS_AMBIGUOUS = "ambiguous"  # два формата дали разный результат
STATUS_UNKNOWN = "unknown_format"  # ни один шаблон не подошёл


@dataclass(frozen=True)
class FormatResult:
    """Результат приведения к формату."""

    plate: str  # что использовать дальше
    original: str  # что пришло от OCR (канонизированное)
    format_name: str | None  # какой шаблон сработал
    corrections: int  # сколько символов заменено
    status: str
    region: str | None = None  # код области, если формат его содержит

    @property
    def is_trusted(self) -> bool:
        """Можно ли открывать шлагбаум без ручной проверки."""
        return self.status in (STATUS_OK, STATUS_CORRECTED)


def canonicalize(text: str) -> str:
    """Только буквы и цифры, верхний регистр. Пробелы и дефисы прочь."""
    return "".join(ch for ch in (text or "").upper() if ch.isalnum())


def _may_fix(index: int, confidences: list[float] | None, threshold: float) -> bool:
    """Можно ли трогать символ на этой позиции.

    Без данных об уверенности правим вслепую (старое поведение). Если
    уверенность известна — только там, где модель сомневалась.
    """
    if confidences is None:
        return True
    if index >= len(confidences):
        return True
    return confidences[index] < threshold


def _apply(
    canon: str,
    fmt: PlateFormat,
    confidences: list[float] | None = None,
    threshold: float = CORRECT_BELOW_CONFIDENCE,
) -> tuple[str, int] | None:
    """Натянуть строку на шаблон. None — не лезет ни при каких правках."""
    out: list[str] = []
    fixes = 0

    for i, (ch, want) in enumerate(zip(canon, fmt.pattern)):
        if want == "D":
            if ch.isdigit():
                out.append(ch)
            elif ch in LETTER_TO_DIGIT and _may_fix(i, confidences, threshold):
                out.append(LETTER_TO_DIGIT[ch])
                fixes += 1
            else:
                return None
        else:  # want == "L"
            if ch.isalpha():
                out.append(ch)
            elif ch in DIGIT_TO_LETTER and _may_fix(i, confidences, threshold):
                out.append(DIGIT_TO_LETTER[ch])
                fixes += 1
            else:
                return None

    if fixes > MAX_CORRECTIONS:
        return None

    repaired = "".join(out)

    # Код региона — дополнительный фильтр. Если последние две цифры дают
    # несуществующую область, значит шаблон подобран неверно.
    if fmt.has_region and repaired[-2:] not in VALID_REGIONS:
        return None

    return repaired, fixes


def normalize_kz(
    text: str,
    char_confidences: list[float] | None = None,
    correct_below: float = CORRECT_BELOW_CONFIDENCE,
) -> FormatResult:
    """Привести номер к формату РК.

    Перебирает шаблоны, выбирает тот, что требует меньше всего замен.
    Если два шаблона дают РАЗНЫЕ строки при одинаковой стоимости — ничего
    не меняет и помечает `ambiguous`: лучше отдать оператору сомнительный
    номер, чем уверенно подставить чужой.

    `char_confidences` — уверенность модели по каждому символу (та самая,
    что уже считает `ocr.py`). Если передана, правится только то, где
    модель сомневалась. Настоятельно рекомендуется: без неё маппер
    переписывает и уверенно прочитанные символы, а это даёт правдоподобную
    выдумку вместо честного «не разобрал».
    """
    canon = canonicalize(text)
    if not canon:
        return FormatResult("", "", None, 0, STATUS_UNKNOWN)

    candidates: list[tuple[int, int, str, PlateFormat]] = []
    for order, fmt in enumerate(FORMATS):
        if len(canon) != len(fmt):
            continue
        applied = _apply(canon, fmt, char_confidences, correct_below)
        if applied is not None:
            repaired, fixes = applied
            candidates.append((fixes, order, repaired, fmt))

    if not candidates:
        return FormatResult(canon, canon, None, 0, STATUS_UNKNOWN)

    candidates.sort(key=lambda c: (c[0], c[1]))
    fixes, _, repaired, fmt = candidates[0]

    # Ничья по стоимости, но разный результат — не угадываем.
    tied = [c for c in candidates if c[0] == fixes]
    if len({c[2] for c in tied}) > 1:
        return FormatResult(canon, canon, None, 0, STATUS_AMBIGUOUS)

    region = repaired[-2:] if fmt.has_region else None
    status = STATUS_OK if fixes == 0 else STATUS_CORRECTED
    return FormatResult(repaired, canon, fmt.name, fixes, status, region)
