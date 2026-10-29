import pytest
from app.services.analytics_service import calculate_data_statistics
from app.services.summary_service import calculate_data_summary


def test_calculate_data_summary_basic():
    # Empty case
    empty_summary = calculate_data_summary([])
    assert empty_summary.count == 0
    assert empty_summary.period == "데이터 없음"

    # Sample dataset
    sample = [
        {"date": "2024-01-01", "value": 2500.0, "trades": []},
        {"date": "2024-01-02", "value": 2550.0, "trades": []},
        {
            "date": "2024-01-03",
            "value": 2600.0,
            "trades": [
                {
                    "id": "tr_1",
                    "side": "buy",
                    "name": "삼성전자",
                    "code": "005930",
                    "qty": 10,
                    "price": 70000.0,
                    "reason": "성장성",
                    "reason_timing": "당시 기록"
                }
            ]
        },
        {"date": "2024-01-04", "value": 2650.0, "trades": []},
    ]

    res = calculate_data_summary(sample)
    assert res.count == 4
    assert res.period == "2024-01-01 ~ 2024-01-04"
    assert res.metrics.latest == 2650.0
    assert res.metrics.min == 2500.0
    assert res.metrics.max == 2650.0
    assert res.metrics.min_date == "2024-01-01"
    assert res.metrics.max_date == "2024-01-04"
    assert res.position == 100.0  # At max
    assert res.my_trades.buy_count == 1
    assert res.my_trades.sell_count == 0
    assert res.my_trades.at_time == 1
    assert res.my_trades.reason_counts["성장성"] == 1


def test_calculate_data_statistics():
    sample = [
        {"date": "2024-01-01", "value": 2500.0, "trades": []},
        {"date": "2024-01-02", "value": 2550.0, "trades": []},
        {"date": "2024-02-01", "value": 2600.0, "trades": []},
    ]

    stats = calculate_data_statistics(sample)
    assert stats.count == 3
    assert "2024-01" in stats.monthly_kospi_returns
    assert stats.volatility_daily >= 0.0


def test_summary_with_single_record_does_not_crash():
    res = calculate_data_summary([{"date": "2024-01-02", "value": 2550.0, "trades": []}])
    assert res.count == 1
    assert res.trend.label == "횡보"
    assert res.trend.avg_diff == 0.0
