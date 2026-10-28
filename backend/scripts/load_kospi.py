"""
KOSPI 1-year Historical Data and Sample Trades Seeder Script.
Seeds ~245 trading days of KOSPI index and realistic sample trades into Firestore (or Local DB).
"""

from datetime import datetime, timedelta
import math
import os
import random
import sys

# Ensure app package is importable
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
root_dir = os.path.dirname(backend_dir)
for p in [backend_dir, root_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from app.core.firebase import get_firestore_client
    from app.models.schemas import DataCreate, TradeCreate
    from app.services.conversation_service import ConversationService
    from app.services.data_service import DataService
except ImportError:
    from backend.app.core.firebase import get_firestore_client
    from backend.app.models.schemas import DataCreate, TradeCreate
    from backend.app.services.conversation_service import ConversationService
    from backend.app.services.data_service import DataService


# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def seed_data():
    print("[INFO] Starting KOSPI 1-year Data & Sample Trades Seeding...")
    db = get_firestore_client()

    # Generate 245 trading days (excluding weekends) ending today or recent date
    end_date = datetime.now().date()
    trading_dates = []

    curr = end_date
    while len(trading_dates) < 245:
        if curr.weekday() < 5:  # Weekday
            trading_dates.append(curr.strftime("%Y-%m-%d"))
        curr -= timedelta(days=1)

    trading_dates.reverse()  # Oldest to newest

    # Realistic KOSPI historical simulation around 2500 ~ 2750 pts
    base_val = 2520.0
    random.seed(20241028)

    sample_trades_dates = {
        trading_dates[-80]: [
            {
                "id": "tr_init_01",
                "side": "buy",
                "name": "삼성전자",
                "code": "005930",
                "qty": 10,
                "price": 71000.0,
                "broker": "키움",
                "reason": "성장성",
                "reason_timing": "당시 기록"
            }
        ],
        trading_dates[-45]: [
            {
                "id": "tr_init_02",
                "side": "buy",
                "name": "SK하이닉스",
                "code": "000660",
                "qty": 5,
                "price": 165000.0,
                "broker": "키움",
                "reason": "시장 흐름",
                "reason_timing": "당시 기록"
            }
        ],
        trading_dates[-32]: [
            {
                "id": "tr_init_03",
                "side": "buy",
                "name": "카카오",
                "code": "035720",
                "qty": 15,
                "price": 42000.0,
                "broker": "신한",
                "reason": "가격 하락",
                "reason_timing": "당시 기록"
            }
        ],
        trading_dates[-12]: [
            {
                "id": "tr_init_04",
                "side": "sell",
                "name": "삼성전자",
                "code": "005930",
                "qty": 5,
                "price": 74500.0,
                "broker": "키움",
                "reason": "뉴스·이슈",
                "reason_timing": "당시 기록"
            }
        ],
        trading_dates[-3]: [
            {
                "id": "tr_init_05",
                "side": "buy",
                "name": "현대차",
                "code": "005380",
                "qty": 4,
                "price": 245000.0,
                "broker": "신한",
                "reason": "성장성",
                "reason_timing": "당시 기록"
            }
        ]
    }

    count = 0
    val = base_val

    for i, dt_str in enumerate(trading_dates):
        # Subtle trend + random walk
        drift = 0.4 * math.sin(i / 15.0)
        noise = (random.random() - 0.495) * 22.0
        val = max(2350.0, min(2850.0, round(val + drift + noise, 2)))

        trades = []
        memo = "일반 정규장 마감"
        if dt_str in sample_trades_dates:
            trades = sample_trades_dates[dt_str]
            t = trades[0]
            memo = f"{t['name']} {t['side']} {t['qty']}주 기록"

        # Check existing before saving to handle idempotency
        try:
            DataService.create_record(
                DataCreate(
                    date=dt_str,
                    value=val,
                    memo=memo,
                    trades=trades
                ),
                source="sync"
            )
            count += 1
        except Exception:
            # Already exists
            pass

    print(f"[OK] Successfully seeded {count} KOSPI daily records (Total trading days: {len(trading_dates)})")

    # Seed an initial conversation session
    try:
        conversations = ConversationService.list_conversations()
        if not conversations:
            print("[INFO] Seeding sample conversation session...")
            now_iso = datetime.now().isoformat()
            ConversationService.create_conversation(
                title="삼성전자 매수 및 시장 흐름 점검",
                messages=[
                    {
                        "role": "user",
                        "content": "최근 코스피 시장 분위기 어때?",
                        "created_at": now_iso
                    },
                    {
                        "role": "assistant",
                        "content": "현재 코스피 지수는 최근 20영업일 동안 완만한 상승 추세를 유지하고 있습니다. 등록된 245영업일 중 1년 변동 범위의 약 64% 지점에 위치하고 있으며, 전체적인 지수 흐름은 안정적인 박스권 상단 돌파를 시도하고 있어요.",
                        "created_at": now_iso
                    }
                ]
            )
            print("[OK] Initial conversation created.")
    except Exception as e:
        print(f"Conversation seed notice: {e}")

    print("[DONE] Seeding completed successfully!")


if __name__ == "__main__":
    seed_data()
