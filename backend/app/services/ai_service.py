from datetime import timedelta
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid
from app.core.config import settings
from app.core.timeutil import fmt_date, is_weekend, label_kr, now_kst, parse_date, today_kst
from app.models.schemas import REASON_CHOICES, ChatResponse, SummaryResponse
from app.services.analytics_service import calculate_data_statistics
from app.services.conversation_service import ConversationService
from app.services.data_service import DataService
from app.services.market_service import MarketService
from app.services.news_service import NewsService
from app.services.summary_service import calculate_data_summary

logger = logging.getLogger("investment_mirror.ai_service")

MAX_TOOL_ROUNDS = 3
MAX_OUTPUT_TOKENS = 800

# OpenAI Function Tools Definition
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "record_trade",
            "description": "사용자가 주식을 샀다(buy)거나 팔았다(sell)고 말할 때 매매 기록 카드(후보)를 만듭니다. 저장은 사용자가 카드에서 확인할 때 됩니다. 수량·단가를 모르면 부르지 말고 먼저 물어보세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "side": {"type": "string", "enum": ["buy", "sell"], "description": "매수(buy) 또는 매도(sell)"},
                    "name": {"type": "string", "description": "종목명 (예: 삼성전자)"},
                    "code": {"type": "string", "description": "6자리 종목 코드. 모르면 비워 두세요."},
                    "qty": {"type": "integer", "description": "매매 수량"},
                    "price": {"type": "number", "description": "매매 단가 (원)"},
                    "broker": {"type": "string", "description": "증권사 (키움, 신한)"},
                    "date": {"type": "string", "description": "거래 날짜 YYYY-MM-DD. '오늘', '어제'는 시스템 프롬프트의 오늘 날짜로 계산하세요."},
                    "reason": {"type": "string", "enum": list(REASON_CHOICES), "description": "사용자가 말한 매매 이유. 말하지 않았으면 비워 두세요."}
                },
                "required": ["side", "name", "qty", "price"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_change",
            "description": "종목의 등락률을 코스피 등락률과 비교합니다. 차이가 기준 이상이면 그날 범위의 공시·뉴스도 함께 돌려줍니다. 기준일은 서버가 정합니다(휴장일이면 직전 거래일).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_code": {"type": "string", "description": "종목명 또는 종목코드"},
                    "date": {"type": "string", "description": "기준 날짜 YYYY-MM-DD (없으면 오늘)"}
                },
                "required": ["name_or_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_close",
            "description": "특정 날짜(휴장일이면 직전 거래일)의 종목 종가와 최신 종가, 그 사이 변화율을 조회합니다. buy_price를 주면 매매가 대비 변화율도 계산합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "종목코드 또는 종목명"},
                    "target_date": {"type": "string", "description": "조회할 날짜 YYYY-MM-DD"},
                    "buy_price": {"type": "number", "description": "비교할 매매 단가 (선택)"}
                },
                "required": ["code", "target_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_summary",
            "description": "최신 코스피 요약과 내 매매 요약을 다시 조회합니다.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_statistics",
            "description": "일간 변동성, 월별 코스피 수익률, 월별·이유별 매매 횟수 등 상세 통계를 조회합니다.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]


class AIService:
    @classmethod
    def build_system_prompt(cls, summary: SummaryResponse) -> str:
        s_m = summary.metrics
        s_t = summary.trend
        m_t = summary.my_trades

        # Format recent trades
        recent_trades_str = ""
        if m_t.recent_trades:
            items = []
            for t in m_t.recent_trades:
                items.append(f"{t.get('date')} {t.get('name')} {t.get('side')} {t.get('qty')}주({t.get('price')}원)")
            recent_trades_str = ", ".join(items)
        else:
            recent_trades_str = "없음"

        # Format reason counts
        reason_str = ", ".join([f"{k} {v}건" for k, v in m_t.reason_counts.items()]) if m_t.reason_counts else "없음"

        buy_pos_str = f"{m_t.buy_position}%" if m_t.buy_position is not None else "데이터 없음"

        now = now_kst()
        prompt = f"""당신은 '투자거울'의 투자 복기 비서이자 금융 선생님입니다.
오늘은 {fmt_date(now.date())} {label_kr(now.date())}, 한국 시간 {now.strftime('%H:%M')}입니다.

[시장 데이터 요약 · 코스피]
- 기간: {summary.period} (영업일 {summary.count}일)
- 최근 종가 {s_m.latest} / 평균 {s_m.average}
- 최고 {s_m.max} ({s_m.max_date}) / 최저 {s_m.min} ({s_m.min_date})
- 기간 수익률 {s_m.period_return}%
- 최근 추세: {s_t.label} (최근 20일 평균 {s_t.avg_recent}, 직전 20일 평균 {s_t.avg_prev}, 차이 {s_t.avg_diff}%)
- 최근 종가 위치: 1년 범위의 {summary.position}% 지점

[내 매매 요약]
- 매수 {m_t.buy_count}건, 매도 {m_t.sell_count}건, 이유별: {reason_str}
- 이유 기록 시점: 당시 기록 {m_t.at_time}건, 이후 회상 {m_t.recalled}건
- 최근 매매: {recent_trades_str}
- 내가 매수한 날 코스피의 평균 위치(매수일 이전 1년 기준): {buy_pos_str}

규칙:
1. 숫자는 위 요약과 도구 결과에 있는 것만 쓰고, 없으면 "데이터에 없어요"라고 답한다.
2. 시장(코스피)과 종목의 움직임을 구분해서 말한다. 코스피 흐름만으로 종목 매매를 평가하지 않는다.
3. 종목 추천, 매수·매도 권유, 가격 예측은 하지 않는다. 추세는 예측이 아니라고 밝힌다.
4. 결과만으로 판단이 옳았다·틀렸다 말하지 않는다. 당시 이유와 이후 흐름을 나란히 보여 주고, 다음에 확인해 볼 점을 질문으로 제시한다.
5. "이후 회상"으로 표시된 이유는 당시의 판단으로 단정하지 않는다.
6. 등락 이유는 도구가 넘긴 자료에 있는 내용만 "가능성 있는 요인"으로 말하고 출처를 단다. 가격 차이만으로 원인을 단정하지 않는다. 답변 첫 줄에 기준일을 밝힌다.
7. 사용자가 매매를 기록하려 하면 record_trade를 부르고, 빠진 정보는 되묻는다.
8. 금융 용어는 20대가 이해할 수 있게 쉬운 말로, 한국어 3~5문장 안에서 답한다.
9. 도구 결과에 error가 있으면 그 내용을 그대로 알리고, 숫자나 이유를 지어내지 않는다.
10. 공시·뉴스 결과의 checked가 false인 항목은 '확인하지 못했다'고 말하고, '이유가 없다'고 말하지 않는다. items가 비어 있고 checked가 true이면 "확인된 이유는 없어요"라고 답한다.
11. is_intraday가 true이면 장 마감 전 값이라고 밝힌다.
"""
        return prompt

    @classmethod
    async def process_chat(cls, user_message: str, conversation_id: Optional[str] = None) -> ChatResponse:
        records = DataService.get_all_records()
        summary = calculate_data_summary(records)
        system_prompt = cls.build_system_prompt(summary)

        # Retrieve recent messages of the conversation (up to recent 6)
        recent_messages: List[Dict[str, str]] = []
        if conversation_id:
            try:
                conv = ConversationService.get_conversation(conversation_id)
                for m in conv.messages[-6:]:
                    recent_messages.append({"role": m.role, "content": m.content})
            except Exception as e:
                logger.warning(f"Failed to fetch conversation history {conversation_id}: {e}")

        if not settings.openai_enabled:
            return cls._offline_response(user_message, conversation_id, summary, reason="no_key")

        try:
            return await cls._call_openai_with_tools(
                user_message=user_message,
                conversation_id=conversation_id,
                system_prompt=system_prompt,
                history=recent_messages,
                summary=summary,
                records=records
            )
        except Exception as e:
            logger.error("OpenAI API call failed: %s", type(e).__name__)
            return cls._offline_response(user_message, conversation_id, summary, reason="api_error")

    @classmethod
    def _offline_response(
        cls,
        user_message: str,
        conversation_id: Optional[str],
        summary: SummaryResponse,
        reason: str
    ) -> ChatResponse:
        """
        AI를 쓸 수 없을 때. 질문에 대한 답을 흉내 내지 않고, 상황을 알린 뒤 저장된 요약 숫자만 보여 줍니다.
        """
        if reason == "no_key":
            head = "지금은 AI가 연결되어 있지 않아(OPENAI_API_KEY 미설정) 질문에 직접 답하지 못해요."
        else:
            head = "AI 응답을 받지 못했어요. 잠시 후 다시 시도해 주세요."

        if summary.count:
            m, t, mt = summary.metrics, summary.trend, summary.my_trades
            body = (
                f" 대신 저장된 데이터 요약만 보여 드릴게요. 코스피 {summary.period}, {summary.count}거래일 기준 "
                f"최근 종가 {m.latest}, 최근 20일 평균 {t.avg_recent} / 직전 20일 평균 {t.avg_prev} "
                f"(차이 {t.avg_diff:+}%, 단순 분류 '{t.label}'이며 예측이 아니에요). "
                f"내 매매는 매수 {mt.buy_count}건, 매도 {mt.sell_count}건이에요."
            )
        else:
            body = " 저장된 데이터도 아직 없어요. 데이터 관리 탭에서 '최신 코스피 불러오기'를 먼저 해 주세요."

        reply = head + body
        conv_id = ConversationService.append_messages(
            conv_id=conversation_id,
            user_message=user_message,
            assistant_reply=reply,
            sources=[]
        )
        return ChatResponse(reply=reply, conversation_id=conv_id, pending_trades=[], sources=[], mode="offline")

    @classmethod
    async def _call_openai_with_tools(
        cls,
        user_message: str,
        conversation_id: Optional[str],
        system_prompt: str,
        history: List[Dict[str, str]],
        summary: SummaryResponse,
        records: List[Dict[str, Any]]
    ) -> ChatResponse:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        model = settings.OPENAI_MODEL or "gpt-4o-mini"

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        pending_trades: List[Dict[str, Any]] = []
        sources: List[Dict[str, Any]] = []
        reply_text: Optional[str] = None

        # 1) 도구 호출 반복: 모델이 도구를 부르면 서버가 실행하고 결과를 붙여 다시 호출 (최대 3번)
        for round_idx in range(MAX_TOOL_ROUNDS + 1):
            allow_tools = round_idx < MAX_TOOL_ROUNDS
            kwargs: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "temperature": 0.3,
            }
            # 마지막 라운드는 도구 정의는 그대로 두되 호출은 막고(tool_choice="none") 답만 받습니다.
            kwargs["tools"] = TOOLS_SCHEMA
            kwargs["tool_choice"] = "auto" if allow_tools else "none"
            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            msg = choice.message

            if not allow_tools or not msg.tool_calls:
                reply_text = msg.content or ""
                # 2) 답이 잘렸으면 그대로 보여 주지 않고 짧게 다시 요청
                if choice.finish_reason == "length":
                    messages.append({"role": "assistant", "content": reply_text})
                    messages.append({"role": "user", "content": "답변이 잘렸어요. 핵심만 3문장 이내로 다시 답해 주세요."})
                    retry = client.chat.completions.create(
                        model=model, messages=messages, max_tokens=MAX_OUTPUT_TOKENS, temperature=0.3,
                        tools=TOOLS_SCHEMA, tool_choice="none"
                    )
                    reply_text = retry.choices[0].message.content or reply_text
                break

            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            })
            for tool_call in msg.tool_calls:
                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_result, new_pending, new_sources = await cls._execute_tool(
                    tool_call.function.name, args, summary, records
                )
                pending_trades.extend(new_pending)
                sources.extend(new_sources)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result, ensure_ascii=False, default=str)
                })

        # 같은 링크가 여러 번 들어오지 않게 정리
        seen_links = set()
        unique_sources = []
        for src in sources:
            if src.get("link") and src["link"] not in seen_links:
                seen_links.add(src["link"])
                unique_sources.append(src)

        conv_id = ConversationService.append_messages(
            conv_id=conversation_id,
            user_message=user_message,
            assistant_reply=reply_text or "",
            sources=unique_sources
        )
        return ChatResponse(
            reply=reply_text or "",
            conversation_id=conv_id,
            pending_trades=pending_trades,
            sources=unique_sources,
            mode="ai"
        )

    @staticmethod
    def _build_trade_candidate(args: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        """record_trade 인자를 검증합니다. 빠진 값은 채우지 않고 missing으로 돌려줍니다."""
        missing: List[str] = []
        side = args.get("side")
        if side not in ("buy", "sell"):
            missing.append("매수/매도 구분")
        name = (args.get("name") or "").strip()
        if not name:
            missing.append("종목명")
        try:
            qty = int(args.get("qty"))
            if qty <= 0:
                raise ValueError
        except (TypeError, ValueError):
            qty = None
            missing.append("수량")
        try:
            price = float(args.get("price"))
            if price <= 0:
                raise ValueError
        except (TypeError, ValueError):
            price = None
            missing.append("단가")

        code = (args.get("code") or "").strip()
        if not (code.isdigit() and len(code) == 6):
            code = MarketService.get_stock_code(name) if name else None
            if name and not code:
                missing.append("종목코드(종목명을 찾지 못함)")

        today = today_kst()
        date_val = args.get("date") or fmt_date(today)
        try:
            d = parse_date(date_val)
            if d > today:
                missing.append("날짜(미래 날짜는 기록할 수 없음)")
            elif is_weekend(d):
                missing.append("날짜(주말은 거래일이 아님)")
        except ValueError:
            missing.append("날짜(YYYY-MM-DD)")

        if missing:
            return None, missing

        reason = args.get("reason")
        return {
            "id": f"tr_{uuid.uuid4().hex[:8]}",
            "date": date_val,
            "side": side,
            "name": name,
            "code": code,
            "qty": qty,
            "price": price,
            "broker": args.get("broker") if args.get("broker") in ("키움", "신한") else None,
            "reason": reason if reason in REASON_CHOICES else None,
            "source": "chat",
        }, []

    @classmethod
    async def _execute_tool(
        cls,
        fn_name: str,
        args: Dict[str, Any],
        summary: SummaryResponse,
        records: List[Dict[str, Any]]
    ) -> Tuple[Any, List[Dict[str, Any]], List[Dict[str, Any]]]:
        if fn_name == "record_trade":
            candidate, missing = cls._build_trade_candidate(args)
            if missing:
                return {"status": "need_more_info", "missing": missing,
                        "message": "기록 카드를 만들지 않았어요. 빠진 정보를 사용자에게 물어보세요."}, [], []
            return {"status": "created_pending_trade", "trade": candidate,
                    "message": "사용자가 카드에서 확인을 눌러야 저장돼요."}, [candidate], []

        if fn_name == "get_stock_change":
            change_info = MarketService.get_stock_change(args.get("name_or_code", ""), args.get("date"))
            if change_info.get("error") or not change_info.get("is_significant"):
                return change_info, [], []
            found = await NewsService.search_news_and_disclosures(
                stock_name=change_info["stock_name"],
                stock_code=change_info["stock_code"],
                base_date=change_info["date"],
                prev_date=change_info["prev_date"],
            )
            change_info["news_and_disclosures"] = found
            return change_info, [], found["items"]

        if fn_name == "get_stock_close":
            buy_price = args.get("buy_price")
            try:
                buy_price = float(buy_price) if buy_price is not None else None
            except (TypeError, ValueError):
                buy_price = None
            return MarketService.get_stock_close(
                args.get("code", ""), args.get("target_date") or fmt_date(today_kst()), buy_price
            ), [], []

        if fn_name == "get_data_summary":
            return summary.model_dump(), [], []

        if fn_name == "get_data_statistics":
            return calculate_data_statistics(records).model_dump(), [], []

        return {"error": f"알 수 없는 도구: {fn_name}"}, [], []
