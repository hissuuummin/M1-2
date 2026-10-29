from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid
from fastapi import HTTPException, status
from app.core.firebase import get_firestore_client
from app.core.timeutil import fmt_date, is_weekend, now_kst, parse_date, today_kst
from app.models.schemas import DataCreate, DataUpdate, TradeCreate, TradeUpdate

logger = logging.getLogger("investment_mirror.data_service")


def reason_timing_for(trade_date: str, recorded_at_kst_date) -> str:
    """이유를 남긴 날이 거래일 당일이면 '당시 기록', 아니면 '이후 회상'."""
    return "당시 기록" if fmt_date(recorded_at_kst_date) == trade_date else "이후 회상"


class DataService:
    @staticmethod
    def _get_collection():
        db = get_firestore_client()
        return db.collection("data")

    @classmethod
    def get_all_records(
        cls,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        col = cls._get_collection()
        docs = col.order_by("date", direction="DESCENDING").stream()

        results = []
        for d in docs:
            data = d.to_dict()
            if not data:
                continue
            if "date" not in data:
                data["date"] = d.id

            dt = data["date"]
            if start_date and dt < start_date:
                continue
            if end_date and dt > end_date:
                continue
            results.append(data)

        # Ensure sorted descending by date
        results.sort(key=lambda x: x["date"], reverse=True)
        return results

    @classmethod
    def get_record_by_id(cls, date_id: str) -> Optional[Dict[str, Any]]:
        col = cls._get_collection()
        doc = col.document(date_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        if "date" not in data:
            data["date"] = doc.id
        return data

    @classmethod
    def create_record(cls, req: DataCreate, source: str = "manual") -> Dict[str, Any]:
        col = cls._get_collection()
        doc_ref = col.document(req.date)
        existing = doc_ref.get()

        if existing.exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{req.date} 날짜의 데이터가 이미 존재합니다."
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        trades_data = [t.model_dump() for t in req.trades] if req.trades else []

        record = {
            "date": req.date,
            "value": float(req.value),
            "memo": req.memo or "",
            "trades": trades_data,
            "source": source,
            "created_at": now_iso,
            "updated_at": now_iso
        }
        doc_ref.set(record)
        return record

    @classmethod
    def update_record(cls, date_id: str, req: DataUpdate) -> Dict[str, Any]:
        col = cls._get_collection()
        doc_ref = col.document(date_id)
        existing = doc_ref.get()

        if not existing.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{date_id} 날짜의 데이터를 찾을 수 없습니다."
            )

        curr = existing.to_dict()
        now_iso = datetime.now(timezone.utc).isoformat()

        if req.value is not None:
            curr["value"] = float(req.value)
        if req.memo is not None:
            curr["memo"] = req.memo
        curr["updated_at"] = now_iso

        doc_ref.set(curr)
        return curr

    @classmethod
    def delete_record(cls, date_id: str) -> bool:
        col = cls._get_collection()
        doc_ref = col.document(date_id)
        existing = doc_ref.get()

        if not existing.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{date_id} 날짜의 데이터를 찾을 수 없습니다."
            )

        doc_ref.delete()
        return True

    @classmethod
    def create_market_record(cls, date_str: str, close: float) -> Dict[str, Any]:
        """시세 동기화로 코스피 종가 문서를 만듭니다."""
        now_iso = datetime.now(timezone.utc).isoformat()
        record = {
            "date": date_str,
            "value": float(close),
            "memo": "",
            "trades": [],
            "source": "sync",
            "created_at": now_iso,
            "updated_at": now_iso
        }
        cls._get_collection().document(date_str).set(record)
        return record

    @classmethod
    def set_market_value(cls, date_str: str, close: float) -> None:
        doc_ref = cls._get_collection().document(date_str)
        doc = doc_ref.get()
        if not doc.exists:
            return
        curr = doc.to_dict()
        curr["value"] = float(close)
        curr["source"] = "sync"
        curr["updated_at"] = datetime.now(timezone.utc).isoformat()
        doc_ref.set(curr)

    @classmethod
    def _kospi_for_new_trade_date(cls, date_id: str) -> float:
        """
        매매를 처음 기록하는 날짜의 코스피 종가를 실제 시세에서 가져옵니다.
        값을 지어내지 않으며, 휴장일이면 422, 시세를 못 가져오면 503을 냅니다.
        """
        from app.services.market_service import MarketDataError, MarketService  # 순환 import 방지

        try:
            d = parse_date(date_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="날짜는 YYYY-MM-DD 형식이어야 해요.")
        today = today_kst()
        if d > today:
            raise HTTPException(status_code=422, detail="미래 날짜에는 매매를 기록할 수 없어요.")
        if is_weekend(d):
            raise HTTPException(status_code=422, detail=f"{date_id}은(는) 주말이라 거래일이 아니에요.")

        try:
            close = MarketService.kospi_close_on(d)
            if close:
                return close
            if d == today:
                # 오늘 장중이면 아직 종가가 없을 수 있음 → 최근 종가로 두고, 동기화 때 실제 종가로 고침
                latest = MarketService.latest_kospi()
                if latest:
                    return latest[1]
        except MarketDataError:
            raise HTTPException(
                status_code=503,
                detail="코스피 종가를 가져오지 못해 기록하지 못했어요. 잠시 후 다시 시도해 주세요."
            )
        raise HTTPException(status_code=422, detail=f"{date_id}은(는) 휴장일이라 거래일이 아니에요.")

    @classmethod
    def add_trade(cls, date_id: str, trade_req: TradeCreate) -> Dict[str, Any]:
        col = cls._get_collection()
        doc_ref = col.document(date_id)
        doc = doc_ref.get()

        now_iso = datetime.now(timezone.utc).isoformat()
        trade_id = trade_req.id or f"tr_{uuid.uuid4().hex[:8]}"

        trade_dict = trade_req.model_dump()
        if not trade_dict.get("code"):
            from app.services.market_service import MarketService  # 순환 import 방지
            code = MarketService.get_stock_code(trade_dict["name"])
            if not code:
                raise HTTPException(
                    status_code=422,
                    detail=f"'{trade_dict['name']}' 종목을 찾지 못했어요. 종목코드 6자리를 함께 입력해 주세요."
                )
            trade_dict["code"] = code
        trade_dict["id"] = trade_id
        trade_dict["review_7d_done"] = False
        trade_dict["review_30d_done"] = False
        if trade_dict.get("reason"):
            now = now_kst()
            trade_dict["reason_recorded_at"] = now.isoformat()
            trade_dict["reason_timing"] = reason_timing_for(date_id, now.date())
        else:
            trade_dict["reason_recorded_at"] = None
            trade_dict["reason_timing"] = None

        if not doc.exists:
            kospi_close = cls._kospi_for_new_trade_date(date_id)
            record = {
                "date": date_id,
                "value": float(kospi_close),
                "memo": "",
                "trades": [trade_dict],
                # 자동으로 채운 코스피 값이라는 표시. 시세 동기화 때 실제 종가로 덮어씁니다.
                "source": "trade_entry",
                "created_at": now_iso,
                "updated_at": now_iso
            }
            doc_ref.set(record)
            return trade_dict

        curr = doc.to_dict()
        trades = curr.get("trades", [])

        # Idempotence: check if trade_id already exists to prevent duplicate insertion
        for t in trades:
            if t.get("id") == trade_id:
                logger.info(f"Trade {trade_id} already exists. Returning existing trade.")
                return t

        trades.append(trade_dict)
        curr["trades"] = trades
        curr["updated_at"] = now_iso
        doc_ref.set(curr)
        return trade_dict

    @classmethod
    def update_trade(cls, date_id: str, trade_id: str, req: TradeUpdate) -> Dict[str, Any]:
        col = cls._get_collection()
        doc_ref = col.document(date_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise HTTPException(status_code=404, detail=f"{date_id} 날짜를 찾을 수 없습니다.")

        curr = doc.to_dict()
        trades = curr.get("trades", [])

        target_trade = None
        for t in trades:
            if t.get("id") == trade_id:
                target_trade = t
                break

        if not target_trade:
            raise HTTPException(status_code=404, detail=f"매매 ID {trade_id}를 찾을 수 없습니다.")

        changes = req.model_dump(exclude_unset=True)
        reason_changed = "reason" in changes and changes["reason"] != target_trade.get("reason")
        for k, v in changes.items():
            target_trade[k] = v
        if reason_changed:
            if target_trade.get("reason"):
                now = now_kst()
                target_trade["reason_recorded_at"] = now.isoformat()
                target_trade["reason_timing"] = reason_timing_for(date_id, now.date())
            else:
                target_trade["reason_recorded_at"] = None
                target_trade["reason_timing"] = None

        curr["updated_at"] = datetime.now(timezone.utc).isoformat()
        doc_ref.set(curr)
        return target_trade

    @classmethod
    def delete_trade(cls, date_id: str, trade_id: str) -> bool:
        col = cls._get_collection()
        doc_ref = col.document(date_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise HTTPException(status_code=404, detail=f"{date_id} 날짜를 찾을 수 없습니다.")

        curr = doc.to_dict()
        trades = curr.get("trades", [])
        initial_len = len(trades)
        trades = [t for t in trades if t.get("id") != trade_id]

        if len(trades) == initial_len:
            raise HTTPException(status_code=404, detail=f"매매 ID {trade_id}를 찾을 수 없습니다.")

        curr["trades"] = trades
        curr["updated_at"] = datetime.now(timezone.utc).isoformat()
        doc_ref.set(curr)
        return True
