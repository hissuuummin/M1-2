from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid
from fastapi import HTTPException, status
from app.core.firebase import get_firestore_client
from app.models.schemas import DataCreate, DataUpdate, TradeCreate, TradeUpdate

logger = logging.getLogger("investment_mirror.data_service")


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
    def add_trade(cls, date_id: str, trade_req: TradeCreate) -> Dict[str, Any]:
        col = cls._get_collection()
        doc_ref = col.document(date_id)
        doc = doc_ref.get()

        now_iso = datetime.now(timezone.utc).isoformat()
        trade_id = trade_req.id or f"tr_{uuid.uuid4().hex[:8]}"

        trade_dict = trade_req.model_dump()
        trade_dict["id"] = trade_id
        trade_dict["reason_recorded_at"] = now_iso
        trade_dict["review_7d_done"] = False
        trade_dict["review_30d_done"] = False

        if not doc.exists:
            # Create date doc if missing, using dummy or fetched kospi
            record = {
                "date": date_id,
                "value": 2600.0,  # default fallback if not yet synced
                "memo": f"매매 기록 ({trade_req.name} {trade_req.side})",
                "trades": [trade_dict],
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

        for k, v in req.model_dump(exclude_unset=True).items():
            target_trade[k] = v

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
