import math
from typing import Any, Dict, List
from app.models.schemas import StatisticsResponse


def calculate_data_statistics(records: List[Dict[str, Any]]) -> StatisticsResponse:
    """
    Computes advanced statistical indicators for Bonus Task (GET /api/data/statistics)
    including daily volatility, monthly breakdown, reasons, and top stocks.
    """
    if not records:
        return StatisticsResponse(
            period="데이터 없음",
            count=0,
            volatility_daily=0.0,
            monthly_kospi_returns={},
            monthly_trade_counts={},
            trades_by_reason={},
            avg_buy_position=None,
            top_traded_stocks=[]
        )

    sorted_records = sorted(records, key=lambda x: x["date"])
    values = [float(r["value"]) for r in sorted_records]
    n = len(sorted_records)

    start_date = sorted_records[0]["date"]
    end_date = sorted_records[-1]["date"]

    # Daily percentage changes for volatility
    daily_returns = []
    for i in range(1, n):
        prev = values[i - 1]
        curr = values[i]
        if prev > 0:
            daily_returns.append((curr - prev) / prev)

    if len(daily_returns) > 1:
        mean_ret = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        volatility_daily = round(math.sqrt(variance) * 100, 2)
    else:
        volatility_daily = 0.0

    # Monthly KOSPI grouping
    monthly_data: Dict[str, List[float]] = {}
    monthly_trades: Dict[str, int] = {}
    reason_counts: Dict[str, int] = {}
    stock_counts: Dict[str, Dict[str, Any]] = {}
    buy_positions = []

    for r in sorted_records:
        r_date = r["date"]
        r_val = float(r["value"])
        month_key = r_date[:7]  # YYYY-MM
        monthly_data.setdefault(month_key, []).append(r_val)

        for t in r.get("trades", []):
            monthly_trades[month_key] = monthly_trades.get(month_key, 0) + 1
            reason = t.get("reason") or "기타"
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

            code = t.get("code", "")
            name = t.get("name", "")
            if code or name:
                key = f"{name}({code})"
                if key not in stock_counts:
                    stock_counts[key] = {"name": name, "code": code, "count": 0, "total_qty": 0}
                stock_counts[key]["count"] += 1
                stock_counts[key]["total_qty"] += int(t.get("qty", 0))

            if t.get("side") == "buy":
                # calculate position
                idx = sorted_records.index(r)
                window_records = sorted_records[max(0, idx - 250):idx + 1]
                w_vals = [float(x["value"]) for x in window_records]
                w_min = min(w_vals)
                w_max = max(w_vals)
                if w_max > w_min:
                    b_pos = ((r_val - w_min) / (w_max - w_min)) * 100
                    buy_positions.append(b_pos)

    # Monthly returns: (end - start) / start * 100
    monthly_kospi_returns: Dict[str, float] = {}
    for m_key, vals in monthly_data.items():
        if vals and vals[0] > 0:
            ret = round(((vals[-1] - vals[0]) / vals[0]) * 100, 2)
            monthly_kospi_returns[m_key] = ret

    avg_buy_pos = round(sum(buy_positions) / len(buy_positions), 1) if buy_positions else None

    # Top traded stocks sorted by transaction count
    top_stocks = sorted(stock_counts.values(), key=lambda x: x["count"], reverse=True)[:5]

    return StatisticsResponse(
        period=f"{start_date} ~ {end_date}",
        count=n,
        volatility_daily=volatility_daily,
        monthly_kospi_returns=monthly_kospi_returns,
        monthly_trade_counts=monthly_trades,
        trades_by_reason=reason_counts,
        avg_buy_position=avg_buy_pos,
        top_traded_stocks=top_stocks
    )
