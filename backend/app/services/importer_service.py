from datetime import date, datetime
import io
import logging
import re
import uuid
from typing import Any, Dict, List, Optional
import pandas as pd
from fastapi import HTTPException, status
from app.core.timeutil import fmt_date, today_kst
from app.services.data_service import DataService
from app.services.market_service import MarketService

logger = logging.getLogger("investment_mirror.importer_service")

# 열 이름 후보 (앞쪽일수록 우선). 실제 영웅문·신한 파일을 받아 보고 필요하면 추가하세요.
COLUMN_CANDIDATES = {
    "date": ["체결일자", "거래일자", "매매일자", "주문일자", "체결일", "거래일", "일자", "날짜"],
    "name": ["종목명", "상품명", "종목"],
    "code": ["종목코드", "단축코드", "상품코드", "코드"],
    "side": ["매매구분", "거래구분", "매도매수구분", "매수매도", "구분"],
    "qty": ["체결수량", "거래수량", "수량"],
    "price": ["체결단가", "거래단가", "단가", "체결가"],
}


def find_columns(columns: List[str]) -> Dict[str, Optional[str]]:
    """정확히 같은 이름을 먼저 찾고, 없으면 포함하는 이름을 찾습니다. 한 열은 한 번만 씁니다."""
    cols = [str(c).strip() for c in columns]
    used = set()
    found: Dict[str, Optional[str]] = {}
    for key, candidates in COLUMN_CANDIDATES.items():
        match = None
        for cand in candidates:
            match = next((c for c in cols if c == cand and c not in used), None)
            if match:
                break
        if not match:
            for cand in candidates:
                match = next((c for c in cols if cand in c and c not in used), None)
                if match:
                    break
        found[key] = match
        if match:
            used.add(match)
    return found


def parse_number(value: Any) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = re.sub(r"[^\d.\-]", "", str(value))
    try:
        return float(text) if text else None
    except ValueError:
        return None


def parse_trade_date(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return fmt_date(value)
    digits = re.sub(r"\D", "", str(value))
    if len(digits) >= 8:
        try:
            return datetime.strptime(digits[:8], "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def parse_side(value: Any) -> Optional[str]:
    text = str(value or "")
    if "매도" in text or text.strip().lower() == "sell":
        return "sell"
    if "매수" in text or text.strip().lower() == "buy":
        return "buy"
    return None  # 입금·배당 등 매매가 아닌 행


class ImporterService:
    @classmethod
    def import_trades_file(cls, file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
        """
        증권사 거래내역 파일(CSV·엑셀)에서 매매 후보를 만듭니다.
        필수 값(날짜·매매구분·수량·단가, 종목명 또는 코드)이 없는 행은 건너뛰고, 값을 대신 채우지 않습니다.
        """
        try:
            if filename.endswith(".xlsx") or filename.endswith(".xls"):
                df = pd.read_excel(io.BytesIO(file_bytes))
            else:
                try:
                    df = pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8-sig")
                except UnicodeDecodeError:
                    df = pd.read_csv(io.BytesIO(file_bytes), encoding="cp949")
        except Exception as e:
            logger.warning("Failed to read trade file: %s", type(e).__name__)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="파일을 읽을 수 없어요. CSV 또는 엑셀 파일인지 확인해 주세요.")

        cols = find_columns(list(df.columns))
        missing = [k for k in ("date", "side", "qty", "price") if not cols[k]]
        if not cols["name"] and not cols["code"]:
            missing.append("name/code")
        if missing:
            labels = {"date": "날짜", "side": "매매구분", "qty": "수량", "price": "단가", "name/code": "종목명 또는 종목코드"}
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"필요한 열을 찾지 못했어요: {', '.join(labels[m] for m in missing)}. "
                    f"파일의 열: {', '.join(str(c) for c in df.columns)}"
                )
            )

        existing_signatures = set()
        for r in DataService.get_all_records():
            for t in r.get("trades", []):
                existing_signatures.add(
                    f"{r.get('date')}_{str(t.get('code')).zfill(6)}_{t.get('side')}_{int(t.get('qty') or 0)}_{float(t.get('price') or 0):.2f}"
                )

        today = today_kst()
        candidates: List[Dict[str, Any]] = []
        skipped = 0
        for _, row in df.iterrows():
            trade_date = parse_trade_date(row[cols["date"]])
            side = parse_side(row[cols["side"]])
            qty = parse_number(row[cols["qty"]])
            price = parse_number(row[cols["price"]])
            name = str(row[cols["name"]]).strip() if cols["name"] and pd.notna(row[cols["name"]]) else ""
            code = ""
            if cols["code"] and pd.notna(row[cols["code"]]):
                digits = re.sub(r"\D", "", str(row[cols["code"]]))
                code = digits[-6:].zfill(6) if digits else ""
            if not code and name:
                code = MarketService.get_stock_code(name) or ""
            if not name and code:
                name = MarketService.get_stock_name(code)

            if (
                not trade_date or trade_date > fmt_date(today) or side is None
                or not qty or qty <= 0 or not price or price <= 0 or not code or not name
            ):
                skipped += 1
                continue

            qty_i = int(abs(qty))
            sig = f"{trade_date}_{code}_{side}_{qty_i}_{price:.2f}"
            candidates.append({
                "id": f"tr_{uuid.uuid4().hex[:8]}",
                "date": trade_date,
                "side": side,
                "name": name[:30],
                "code": code,
                "qty": qty_i,
                "price": price,
                "broker": None,
                "reason": None,
                "source": "file",
                "is_already_saved": sig in existing_signatures,
            })

        logger.info("Trade file parsed: %d candidates, %d rows skipped", len(candidates), skipped)
        if not candidates:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"매매 내역으로 읽을 수 있는 행이 없어요. (건너뛴 행 {skipped}개)"
            )
        return candidates
