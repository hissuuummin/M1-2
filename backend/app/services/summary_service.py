import logging
from typing import Any, Dict, List, Optional
from app.models.schemas import SummaryMetrics, SummaryResponse, SummaryTrend, TradeSummaryInfo

logger = logging.getLogger("investment_mirror.summary")


def calculate_data_summary(records: List[Dict[str, Any]]) -> SummaryResponse:
    """
    Computes time-series metrics, trend, range position, and trade metrics
    based on the guidelines in the Investment Mirror project plan.
    Records should be dictionaries containing 'date', 'value', and optional 'trades'.
    """
    if not records:
        return SummaryResponse(
            period="데이터 없음",
            count=0,
            metrics=SummaryMetrics(
                latest=0.0,
                average=0.0,
                max=0.0,
                min=0.0,
                max_date=None,
                min_date=None,
                period_return=0.0
            ),
            trend=SummaryTrend(
                label="횡보",
                avg_recent=0.0,
                avg_prev=0.0,
                avg_diff=0.0,
                description="분석 가능한 데이터가 없습니다."
            ),
            position=0.0,
            my_trades=TradeSummaryInfo(
                buy_count=0,
                sell_count=0,
                reason_counts={},
                at_time=0,
                recalled=0,
                recent_trades=[],
                buy_position=None
            )
        )

    # Sort chronological (oldest to newest)
    sorted_records = sorted(records, key=lambda x: x["date"])
    values = [float(r["value"]) for r in sorted_records]
    n = len(sorted_records)

    start_date = sorted_records[0]["date"]
    end_date = sorted_records[-1]["date"]
    period_str = f"{start_date} ~ {end_date}"

    latest = round(values[-1], 2)
    average = round(sum(values) / n, 2)
    min_val = min(values)
    max_val = max(values)

    min_idx = values.index(min_val)
    max_idx = values.index(max_val)
    min_date = sorted_records[min_idx]["date"]
    max_date = sorted_records[max_idx]["date"]

    first_val = values[0]
    period_return = round(((latest - first_val) / first_val) * 100, 2) if first_val > 0 else 0.0

    # Trend: Recent 20 business days avg vs previous 20 business days avg
    window = 20
    if n >= window * 2:
        recent_vals = values[-window:]
        prev_vals = values[-window * 2:-window]
        avg_recent = round(sum(recent_vals) / window, 2)
        avg_prev = round(sum(prev_vals) / window, 2)
    elif n >= window:
        recent_vals = values[-window:]
        prev_vals = values[:n - window]
        avg_recent = round(sum(recent_vals) / window, 2)
        avg_prev = round(sum(prev_vals) / len(prev_vals), 2) if prev_vals else avg_recent
    else:
        half = max(1, n // 2)
        prev_vals = values[:half]
        recent_vals = values[half:]
        avg_recent = round(sum(recent_vals) / len(recent_vals), 2)
        avg_prev = round(sum(prev_vals) / len(prev_vals), 2)

    if avg_prev > 0:
        avg_diff = round(((avg_recent - avg_prev) / avg_prev) * 100, 2)
    else:
        avg_diff = 0.0

    if avg_diff >= 1.0:
        trend_label = "상승"
        trend_desc = f"최근 20일 평균이 직전 20일 대비 +{avg_diff}% 상승 추세입니다."
    elif avg_diff <= -1.0:
        trend_label = "하락"
        trend_desc = f"최근 20일 평균이 직전 20일 대비 {avg_diff}% 하락 추세입니다."
    else:
        trend_label = "횡보"
        trend_desc = f"최근 20일 평균과 직전 20일 차이가 {avg_diff}%로 횡보 흐름입니다."

    # Position in 1-year range: (종가 - 1년 최저) / (1년 최고 - 1년 최저) * 100
    if max_val > min_val:
        position = round(((latest - min_val) / (max_val - min_val)) * 100, 1)
    else:
        position = 50.0

    # Trade summary extraction
    all_trades: List[Dict[str, Any]] = []
    buy_positions: List[float] = []

    for r in sorted_records:
        r_date = r["date"]
        r_val = float(r["value"])
        for t in r.get("trades", []):
            trade_dict = dict(t)
            trade_dict["date"] = r_date
            all_trades.append(trade_dict)

            # If it's a buy trade, compute position in range up to this date (max 250 records prior)
            if trade_dict.get("side") == "buy":
                idx = sorted_records.index(r)
                window_records = sorted_records[max(0, idx - 250):idx + 1]
                w_vals = [float(x["value"]) for x in window_records]
                w_min = min(w_vals)
                w_max = max(w_vals)
                if w_max > w_min:
                    b_pos = ((r_val - w_min) / (w_max - w_min)) * 100
                    buy_positions.append(b_pos)

    buy_count = sum(1 for t in all_trades if t.get("side") == "buy")
    sell_count = sum(1 for t in all_trades if t.get("side") == "sell")

    reason_counts: Dict[str, int] = {}
    at_time_count = 0
    recalled_count = 0

    for t in all_trades:
        reason = t.get("reason") or "미기재"
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        timing = t.get("reason_timing")
        if timing == "당시 기록":
            at_time_count += 1
        elif timing == "이후 회상":
            recalled_count += 1

    # Most recent 3 trades
    recent_trades = sorted(all_trades, key=lambda x: x.get("date", ""), reverse=True)[:3]

    avg_buy_position = (
        round(sum(buy_positions) / len(buy_positions), 1) if buy_positions else None
    )

    return SummaryResponse(
        period=period_str,
        count=n,
        metrics=SummaryMetrics(
            latest=latest,
            average=average,
            max=round(max_val, 2),
            min=round(min_val, 2),
            max_date=max_date,
            min_date=min_date,
            period_return=period_return
        ),
        trend=SummaryTrend(
            label=trend_label,
            avg_recent=avg_recent,
            avg_prev=avg_prev,
            avg_diff=avg_diff,
            description=trend_desc
        ),
        position=position,
        my_trades=TradeSummaryInfo(
            buy_count=buy_count,
            sell_count=sell_count,
            reason_counts=reason_counts,
            at_time=at_time_count,
            recalled=recalled_count,
            recent_trades=recent_trades,
            buy_position=avg_buy_position
        )
    )
