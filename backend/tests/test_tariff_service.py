"""Тесты расчёта стоимости парковки (ТЗ §3.4 + краевые случаи)."""

from src.modules.tariff import calculate_price

HOUR = 3600
MIN = 60


def test_free_period_returns_zero():
    # 10 мин при бесплатных 15 → бесплатно
    assert (
        calculate_price(10 * MIN, free_minutes=15, price_per_hour=100, daily_cap=1000)
        == 0
    )


def test_exactly_free_minutes_is_zero():
    assert (
        calculate_price(15 * MIN, free_minutes=15, price_per_hour=100, daily_cap=1000)
        == 0
    )


def test_one_billable_hour():
    # ровно час, без бесплатного периода, 100/ч → 100
    assert (
        calculate_price(60 * MIN, free_minutes=0, price_per_hour=100, daily_cap=10000)
        == 100
    )


def test_partial_hour_rounds_up():
    # 61 мин → ceil(61/60) = 2 часа → 200
    assert (
        calculate_price(61 * MIN, free_minutes=0, price_per_hour=100, daily_cap=10000)
        == 200
    )


def test_hourly_ceil_after_free_period():
    # 90 мин, 15 беспл → ceil((90-15)/60)=ceil(1.25)=2 → 200
    assert (
        calculate_price(90 * MIN, free_minutes=15, price_per_hour=100, daily_cap=10000)
        == 200
    )


def test_daily_cap_applies():
    # 20 ч × 100 = 2000, но суточный максимум 1000 → 1000
    assert (
        calculate_price(20 * HOUR, free_minutes=0, price_per_hour=100, daily_cap=1000)
        == 1000
    )


def test_no_daily_cap_is_uncapped():
    # daily_cap=None → без ограничения: 20 ч × 100 = 2000
    assert (
        calculate_price(20 * HOUR, free_minutes=0, price_per_hour=100, daily_cap=None)
        == 2000
    )


def test_daily_cap_is_per_day_for_multi_day():
    # 2 полных суток, суточный максимум 1000 → 2 × 1000 = 2000
    assert (
        calculate_price(48 * HOUR, free_minutes=0, price_per_hour=100, daily_cap=1000)
        == 2000
    )


def test_multi_day_with_remainder():
    # 25 ч: 1 сутки (cap 1000) + 1 ч (100) = 1100
    assert (
        calculate_price(25 * HOUR, free_minutes=0, price_per_hour=100, daily_cap=1000)
        == 1100
    )


def test_zero_duration_is_free():
    assert calculate_price(0, free_minutes=15, price_per_hour=100, daily_cap=1000) == 0
