"""
코스피 실제 종가 초기 적재 스크립트.

FinanceDataReader(실패하면 금융위원회 시세 API)에서 최근 1년치 코스피 종가를 받아
data 컬렉션(Firestore, 또는 로컬 개발 시 .local_db)에 넣습니다.
예시 매매나 예시 대화는 만들지 않습니다.

사용법 (backend 폴더에서):
    python scripts/load_kospi.py              # 최근 365일, 빠진 날짜만 채움
    python scripts/load_kospi.py --days 400   # 기간 변경
    python scripts/load_kospi.py --fix-all    # 직접 입력(manual) 값까지 실제 종가로 덮어씀 (매매·메모는 유지)
"""

import argparse
import os
import sys

# Ensure app package is importable
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
root_dir = os.path.dirname(backend_dir)
for p in [backend_dir, root_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app.core.timeutil import today_kst  # noqa: E402
from app.services.data_service import DataService  # noqa: E402
from app.services.market_service import KOSPI_SYMBOL, MarketDataError, MarketService, get_series  # noqa: E402

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="코스피 실제 종가 적재")
    parser.add_argument("--days", type=int, default=365, help="오늘부터 며칠 전까지 받을지 (기본 365)")
    parser.add_argument("--fix-all", action="store_true", help="직접 입력한 값까지 실제 종가로 덮어쓰기")
    args = parser.parse_args()

    print(f"[INFO] 최근 {args.days}일 코스피 종가를 불러옵니다...")
    try:
        result = MarketService.sync_kospi(days_back=args.days)
    except MarketDataError as e:
        print(f"[ERROR] {e}")
        print("        인터넷 연결, FinanceDataReader 설치, 또는 DATA_GO_KR_KEY 설정을 확인하세요.")
        return 1

    print(f"[OK] 새로 넣은 거래일 {result['created']}일, 실제 종가로 고친 날 {result['updated']}일")

    if args.fix_all:
        from datetime import timedelta
        today = today_kst()
        series = get_series(KOSPI_SYMBOL, today - timedelta(days=args.days), today)
        fixed = 0
        for r in DataService.get_all_records():
            actual = series.get(r["date"])
            if actual is not None and abs(float(r.get("value", 0)) - actual) > 0.005:
                DataService.set_market_value(r["date"], actual)
                fixed += 1
        print(f"[OK] --fix-all: 직접 입력 값 포함 {fixed}일을 실제 종가로 맞췄어요.")

    total = len(DataService.get_all_records())
    print(f"[DONE] 현재 저장된 데이터: {total}일")
    if total < 100:
        print("[WARN] 과제 최소 기준(100개)보다 적어요. --days 값을 늘려 보세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
