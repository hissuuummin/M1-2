from datetime import datetime
import io
import logging
import uuid
from typing import Any, Dict, List
import pandas as pd
from app.services.data_service import DataService
from app.services.market_service import MarketService

logger = logging.getLogger("investment_mirror.importer_service")


class ImporterService:
    @classmethod
    def import_trades_file(cls, file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
        """
        Parses brokerage trade history file (CSV or Excel) and cross-references existing trades to flag duplicates.
        """
        try:
            if filename.endswith(".xlsx") or filename.endswith(".xls"):
                df = pd.read_excel(io.BytesIO(file_bytes))
            else:
                # Try UTF-8 and CP949 (Korean encoding common in brokerage exports)
                try:
                    df = pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8")
                except Exception:
                    df = pd.read_csv(io.BytesIO(file_bytes), encoding="cp949")
        except Exception as e:
            logger.error(f"Failed to read trade file {filename}: {e}")
            raise ValueError(f"파일을 읽을 수 없습니다: {str(e)}")

        existing_records = DataService.get_all_records()
        existing_trade_signatures = set()
        for r in existing_records:
            r_date = r.get("date", "")
            for t in r.get("trades", []):
                sig = f"{r_date}_{t.get('code')}_{t.get('side')}_{t.get('qty')}_{t.get('price')}"
                existing_trade_signatures.add(sig)

        candidates: List[Dict[str, Any]] = []

        # Normalize column names
        cols = {str(c).strip(): c for c in df.columns}

        # Identify key columns by common Korean names
        date_col = next((c for c in cols if any(k in c for k in ["일자", "거래일", "날짜", "체결일"])), None)
        name_col = next((c for c in cols if any(k in c for k in ["종목명", "상품명", "종목"])), None)
        code_col = next((c for c in cols if any(k in c for k in ["종목코드", "단축코드", "코드"])), None)
        side_col = next((c for c in cols if any(k in c for k in ["구분", "매매", "거래구분", "종류"])), None)
        qty_col = next((c for c in cols if any(k in c for k in ["수량", "체결수량", "거래수량"])), None)
        price_col = next((c for c in cols if any(k in c for k in ["단가", "체결단가", "가격"])), None)

        for _, row in df.iterrows():
            try:
                # Date parsing
                raw_date = str(row[date_col]) if date_col else datetime.now().strftime("%Y-%m-%d")
                clean_date = raw_date.replace(".", "-").replace("/", "-")[:10]

                # Stock name & code
                name = str(row[name_col]).strip() if name_col else "종목"
                if code_col and pd.notna(row[code_col]):
                    code = str(row[code_col]).strip().zfill(6)
                else:
                    code = MarketService.get_stock_code(name) or "005930"

                # Side
                raw_side = str(row[side_col]) if side_col else "매수"
                side = "sell" if any(k in raw_side for k in ["매도", "sell", "출고"]) else "buy"

                # Qty & price
                qty = abs(int(row[qty_col])) if qty_col and pd.notna(row[qty_col]) else 1
                price = float(row[price_col]) if price_col and pd.notna(row[price_col]) else 50000.0

                sig = f"{clean_date}_{code}_{side}_{qty}_{price}"
                is_duplicate = sig in existing_trade_signatures

                candidates.append({
                    "id": f"tr_{uuid.uuid4().hex[:6]}",
                    "date": clean_date,
                    "side": side,
                    "name": name,
                    "code": code,
                    "qty": qty,
                    "price": price,
                    "broker": "증권사 파일",
                    "reason": None,
                    "is_already_saved": is_duplicate
                })
            except Exception as row_err:
                logger.warning(f"Row parsing skipped: {row_err}")

        return candidates
