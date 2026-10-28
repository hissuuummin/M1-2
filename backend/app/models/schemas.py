from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class TradeItem(BaseModel):
    id: str = Field(description="고유 거래 ID")
    side: Literal["buy", "sell"] = Field(description="매수(buy) 또는 매도(sell)")
    name: str = Field(min_length=1, max_length=30, description="종목명 (예: 삼성전자)")
    code: str = Field(description="6자리 종목 코드 (예: 005930)")
    qty: int = Field(gt=0, description="매매 수량 (양의 정수)")
    price: float = Field(gt=0, description="매매 단가 (양의 실수)")
    broker: Optional[str] = Field(default="키움", description="증권사 (키움, 신한 등)")
    reason: Optional[str] = Field(
        default=None,
        description="매매 이유 (성장성, 시장 흐름, 가격 하락, 뉴스·이슈, 기타)"
    )
    reason_note: Optional[str] = Field(default=None, max_length=100, description="상세 메모")
    reason_recorded_at: Optional[str] = Field(default=None, description="이유 기록 시각")
    reason_timing: Optional[Literal["당시 기록", "이후 회상"]] = Field(
        default="당시 기록",
        description="당시 기록 또는 이후 회상"
    )
    review_7d_done: bool = Field(default=False, description="7일 복기 완료 여부")
    review_30d_done: bool = Field(default=False, description="30일 복기 완료 여부")
    source: Optional[Literal["chat", "file", "capture", "manual"]] = Field(
        default="manual",
        description="기록 출처"
    )

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        clean = v.strip().zfill(6)
        if not clean.isdigit() or len(clean) != 6:
            raise ValueError("종목 코드는 6자리 숫자여야 합니다.")
        return clean


class TradeCreate(BaseModel):
    id: Optional[str] = Field(default=None, description="서버 또는 클라이언트 거래 ID")
    side: Literal["buy", "sell"] = Field(description="buy 또는 sell")
    name: str = Field(min_length=1, max_length=30)
    code: str = Field(description="6자리 종목코드")
    qty: int = Field(gt=0, description="수량")
    price: float = Field(gt=0, description="단가")
    broker: Optional[str] = "키움"
    reason: Optional[str] = None
    reason_note: Optional[str] = Field(default=None, max_length=100)
    reason_timing: Optional[Literal["당시 기록", "이후 회상"]] = "당시 기록"
    source: Optional[Literal["chat", "file", "capture", "manual"]] = "manual"

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        clean = v.strip().zfill(6)
        if not clean.isdigit() or len(clean) != 6:
            raise ValueError("종목 코드는 6자리 숫자여야 합니다.")
        return clean


class TradeUpdate(BaseModel):
    side: Optional[Literal["buy", "sell"]] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=30)
    code: Optional[str] = None
    qty: Optional[int] = Field(default=None, gt=0)
    price: Optional[float] = Field(default=None, gt=0)
    broker: Optional[str] = None
    reason: Optional[str] = None
    reason_note: Optional[str] = Field(default=None, max_length=100)
    reason_timing: Optional[Literal["당시 기록", "이후 회상"]] = None
    review_7d_done: Optional[bool] = None
    review_30d_done: Optional[bool] = None


class DataCreate(BaseModel):
    date: str = Field(description="거래일 (YYYY-MM-DD)")
    value: float = Field(gt=0, description="코스피 종가 (0보다 큰 실수)")
    memo: str = Field(default="", max_length=300, description="그날의 메모 (최대 300자)")
    trades: Optional[List[TradeItem]] = Field(default_factory=list)

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            d = datetime.strptime(v, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("날짜는 YYYY-MM-DD 형식이어야 합니다.")
        today = date.today()
        if d > today:
            raise ValueError(f"미래 날짜는 입력할 수 없습니다. (입력: {v}, 오늘: {today})")
        return v


class DataUpdate(BaseModel):
    value: Optional[float] = Field(default=None, gt=0, description="코스피 종가")
    memo: Optional[str] = Field(default=None, max_length=300, description="메모 (최대 300자)")


class DataResponse(BaseModel):
    date: str
    value: float
    memo: str = ""
    trades: List[TradeItem] = []
    source: Optional[str] = "sync"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SummaryMetrics(BaseModel):
    latest: float
    average: float
    max: float
    min: float
    max_date: Optional[str] = None
    min_date: Optional[str] = None
    period_return: float


class SummaryTrend(BaseModel):
    label: Literal["상승", "하락", "횡보"]
    avg_recent: float
    avg_prev: float
    avg_diff: float
    description: str


class TradeSummaryInfo(BaseModel):
    buy_count: int
    sell_count: int
    reason_counts: Dict[str, int]
    at_time: int
    recalled: int
    recent_trades: List[Dict[str, Any]]
    buy_position: Optional[float] = None


class SummaryResponse(BaseModel):
    period: str
    count: int
    metrics: SummaryMetrics
    trend: SummaryTrend
    position: float
    my_trades: TradeSummaryInfo


class StatisticsResponse(BaseModel):
    period: str
    count: int
    volatility_daily: float
    monthly_kospi_returns: Dict[str, float]
    monthly_trade_counts: Dict[str, int]
    trades_by_reason: Dict[str, int]
    avg_buy_position: Optional[float]
    top_traded_stocks: List[Dict[str, Any]]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    sources: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    created_at: Optional[str] = None


class ConversationCreate(BaseModel):
    title: Optional[str] = None
    messages: List[ChatMessage] = Field(default_factory=list)


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: Optional[str] = None
    messages: List[ChatMessage] = []


class ConversationListItem(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: Optional[str] = None
    message_count: int


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000, description="사용자 질문 (1~1000자)")
    conversation_id: Optional[str] = Field(default=None, description="대화 세션 ID (선택)")


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    pending_trades: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []


class PendingReviewItem(BaseModel):
    trade_id: str
    date: str
    side: str
    name: str
    code: str
    qty: int
    price: float
    reason: Optional[str]
    days_passed: int
    review_type: Literal["7d", "30d"]
    kospi_then: float
    kospi_now: float
    kospi_change: float
    suggested_question: str


class StockPricePoint(BaseModel):
    date: str
    stock_close: float
    kospi_close: float
    stock_indexed: float  # Normalized to 100 on start date
    kospi_indexed: float  # Normalized to 100 on start date


class StockPricesResponse(BaseModel):
    code: str
    name: str
    start_date: str
    end_date: str
    data: List[StockPricePoint]
    trades: List[TradeItem] = []
