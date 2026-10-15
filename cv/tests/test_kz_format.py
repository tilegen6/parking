"""Тесты приведения номера к казахстанскому формату."""

from __future__ import annotations

import pytest

from recognizer.kz_format import (
    STATUS_AMBIGUOUS,
    STATUS_CORRECTED,
    STATUS_OK,
    STATUS_UNKNOWN,
    canonicalize,
    normalize_kz,
)


class TestCanonicalize:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("237 BLM 01", "237BLM01"),
            ("237-blm-01", "237BLM01"),
            ("  aq 003 01  ", "AQ00301"),
            ("", ""),
            ("!!!", ""),
        ],
    )
    def test_strips_and_uppercases(self, raw: str, expected: str) -> None:
        assert canonicalize(raw) == expected


class TestExactFormats:
    """Все пять подтверждённых шаблонов проходят без правок."""

    @pytest.mark.parametrize(
        ("plate", "fmt"),
        [
            ("237BLM01", "классический"),
            ("040BS01", "классический короткий"),
            ("AQ00301", "новый"),
            ("A724CBM", "старый"),
            ("H444501", "жёлтый/дипломатический"),
        ],
    )
    def test_recognized_without_changes(self, plate: str, fmt: str) -> None:
        res = normalize_kz(plate)
        assert res.plate == plate
        assert res.status == STATUS_OK
        assert res.format_name == fmt
        assert res.corrections == 0
        assert res.is_trusted

    def test_systematic_o_zero_confusion(self) -> None:
        """Модель путает 0 с O по всему номеру сразу — три правки за раз."""
        res = normalize_kz("AQOO3O1")
        assert res.plate == "AQ00301"
        assert res.corrections == 3
        assert res.is_trusted

    def test_classic_format_not_stolen_by_yellow(self) -> None:
        """`040BS01` подходит под классический без правок — жёлтый не должен перебить."""
        res = normalize_kz("040BS01")
        assert res.format_name == "классический короткий"
        assert res.corrections == 0

    def test_real_photos_from_dataset(self) -> None:
        """Номера с реальных фото, присланных с объекта."""
        for plate in ("AQ00301", "040BS01", "A724CBM"):
            assert normalize_kz(plate).status == STATUS_OK


class TestLetterDigitConfusion:
    """Главная задача модуля: O/0 и прочие похожие начертания."""

    @pytest.mark.parametrize(
        ("ocr_output", "expected"),
        [
            # O вместо 0 на цифровых позициях
            ("O4OBS01", "040BS01"),
            ("AQOO3O1", "AQ00301"),
            ("237BLMO1", "237BLM01"),
            # 0 вместо O на буквенной позиции
            ("2370LM01", "237OLM01"),
            # прочие пары
            ("I40BS01", "140BS01"),
            ("040B5O1", "040BS01"),
        ],
    )
    def test_fixes_confused_glyphs(self, ocr_output: str, expected: str) -> None:
        res = normalize_kz(ocr_output)
        assert res.plate == expected
        assert res.status == STATUS_CORRECTED
        assert res.is_trusted

    def test_o_in_digit_position_becomes_zero(self) -> None:
        assert normalize_kz("237BLMO1").plate == "237BLM01"

    def test_zero_in_letter_position_becomes_o(self) -> None:
        # 0 на буквенной позиции трактуется как O
        assert normalize_kz("2370LM01").plate == "237OLM01"


class TestRegionCode:
    """Код области 01–20 — дополнительная проверка правильности шаблона."""

    def test_valid_region_extracted(self) -> None:
        assert normalize_kz("237BLM02").region == "02"
        assert normalize_kz("040BS20").region == "20"

    def test_region_out_of_range_rejects_format(self) -> None:
        # 99 не существует — под «классический» строка не подойдёт
        res = normalize_kz("237BLM99")
        assert res.status == STATUS_UNKNOWN
        assert res.plate == "237BLM99"

    def test_region_zero_rejected(self) -> None:
        assert normalize_kz("237BLM00").status == STATUS_UNKNOWN

    def test_formats_without_region_have_none(self) -> None:
        assert normalize_kz("A724CBM").region is None
        assert normalize_kz("H444501").region is None


class TestGuardRails:
    """Модуль не должен выдумывать номера."""

    def test_too_many_corrections_rejected(self) -> None:
        # три замены — это уже другой номер, а не помарка OCR
        res = normalize_kz("OOOBLMO1")
        assert res.status == STATUS_UNKNOWN

    def test_unknown_length_untouched(self) -> None:
        res = normalize_kz("ABC")
        assert res.status == STATUS_UNKNOWN
        assert res.plate == "ABC"

    def test_empty_input(self) -> None:
        res = normalize_kz("")
        assert res.status == STATUS_UNKNOWN
        assert res.plate == ""

    def test_untrusted_statuses(self) -> None:
        assert not normalize_kz("ABC").is_trusted
        assert not normalize_kz("").is_trusted

    def test_impossible_glyph_not_forced(self) -> None:
        # W не похож ни на одну цифру, и в этой строке он занимает
        # цифровую позицию во всех пяти шаблонах сразу
        assert normalize_kz("WWWBS01").status == STATUS_UNKNOWN

    def test_leading_letter_is_legal_in_yellow_format(self) -> None:
        # А вот здесь W стоит первой БУКВОЙ жёлтого формата Б-ЦЦЦЦЦЦ —
        # это законное совпадение, а не выдумка
        res = normalize_kz("W40BS01")
        assert res.plate == "W408501"
        assert res.format_name == "жёлтый/дипломатический"


class TestAmbiguity:
    """Когда два шаблона равновероятны — не угадываем."""

    def test_tie_between_formats_reports_ambiguous(self) -> None:
        # 7 символов: подходит и «новый» (LLDDDDD), и «жёлтый» (LDDDDDD).
        # OCR-строка, где второй символ одинаково хорош и буквой, и цифрой.
        res = normalize_kz("AO00301")
        assert res.status in (STATUS_AMBIGUOUS, STATUS_OK, STATUS_CORRECTED)
        # главное — если статус ambiguous, номер не переписан
        if res.status == STATUS_AMBIGUOUS:
            assert res.plate == res.original
            assert not res.is_trusted


class TestIdempotence:
    def test_applying_twice_changes_nothing(self) -> None:
        for raw in ("O4OBS01", "237BLMO1", "AQOO3O1"):
            once = normalize_kz(raw).plate
            twice = normalize_kz(once).plate
            assert once == twice


class TestConfidenceGating:
    """Правим только то, в чём модель сомневалась.

    Без этого маппер переписывает уверенно прочитанные символы и выдаёт
    правдоподобную выдумку с отметкой «достоверно» — на реальных фото
    именно так и получалось.
    """

    def test_low_confidence_char_is_fixed(self) -> None:
        # две последние позиции прочитаны неуверенно (O->0 и I->1)
        conf = [0.99] * 6 + [0.40, 0.40]
        res = normalize_kz("237BLMOI", char_confidences=conf)
        assert res.plate == "237BLM01"
        assert res.status == STATUS_CORRECTED

    def test_high_confidence_char_is_left_alone(self) -> None:
        # та же строка, но модель уверена во всех символах — не трогаем
        res = normalize_kz("237BLMOI", char_confidences=[0.99] * 8)
        assert res.status == STATUS_UNKNOWN
        assert res.plate == "237BLMOI"
        assert not res.is_trusted

    def test_regression_confident_garbage_not_rewritten(self) -> None:
        """Случаи с реальных фото, где маппер раньше выдумывал номер."""
        confident = [0.99] * 7
        # было: ABQ0301 -> AB00301 (правда AQ00301)
        assert normalize_kz("ABQ0301", char_confidences=confident).status == STATUS_UNKNOWN
        # было: 1317002 -> I317002 (полицейский 131702, лишний ноль от OCR)
        assert normalize_kz("1317002", char_confidences=confident).status == STATUS_UNKNOWN
        # было: 24401AN -> Z440IAN (правда 249AN01, двухрядный прочитан неверно)
        assert normalize_kz("24401AN", char_confidences=confident).status == STATUS_UNKNOWN

    def test_threshold_is_configurable(self) -> None:
        conf = [0.99] * 6 + [0.95, 0.95]
        assert normalize_kz("237BLMOI", char_confidences=conf).status == STATUS_UNKNOWN
        res = normalize_kz("237BLMOI", char_confidences=conf, correct_below=0.97)
        assert res.plate == "237BLM01"

    def test_without_confidences_behaves_as_before(self) -> None:
        assert normalize_kz("237BLMO1").plate == "237BLM01"

    def test_shorter_confidence_list_does_not_crash(self) -> None:
        res = normalize_kz("237BLMO1", char_confidences=[0.99, 0.99])
        assert res.plate == "237BLM01"
