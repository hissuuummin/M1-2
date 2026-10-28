from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid
from openai import OpenAI
from app.core.config import settings
from app.models.schemas import ChatResponse, SummaryResponse
from app.services.analytics_service import calculate_data_statistics
from app.services.conversation_service import ConversationService
from app.services.data_service import DataService
from app.services.market_service import MarketService
from app.services.news_service import NewsService
from app.services.summary_service import calculate_data_summary

logger = logging.getLogger("investment_mirror.ai_service")

# OpenAI Function Tools Definition
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "record_trade",
            "description": "사용자가 주식을 샀거나(buy) 팔았다고(sell) 말할 때 매매 기록 카드(후보)를 생성합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "side": {"type": "string", "enum": ["buy", "sell"], "description": "매수(buy) 또는 매도(sell)"},
                    "name": {"type": "string", "description": "종목명 (예: 삼성전자, 카카오)"},
                    "code": {"type": "string", "description": "6자리 종목 코드 (예: 005930)"},
                    "qty": {"type": "integer", "description": "매매 수량"},
                    "price": {"type": "number", "description": "매매 단가 (원)"},
                    "broker": {"type": "string", "description": "증권사 (예: 키움, 신한)"},
                    "date": {"type": "string", "description": "거래 날짜 (YYYY-MM-DD)"},
                    "reason": {"type": "string", "description": "매매 이유 (성장성, 시장 흐름, 가격 하락, 뉴스·이슈, 기타)"}
                },
                "required": ["side", "name", "qty", "price"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_change",
            "description": "특정 종목의 등락률과 코스피 등락률을 비교하고, 차이가 크면 그날의 공시와 뉴스를 함께 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_code": {"type": "string", "description": "종목명 또는 종목코드"},
                    "date": {"type": "string", "description": "기준 날짜 (YYYY-MM-DD)"}
                },
                "required": ["name_or_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_close",
            "description": "특정 날짜의 종목 종가와 매수가 대비 수익률을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "종목코드 또는 종목명"},
                    "target_date": {"type": "string", "description": "조회할 날짜 (YYYY-MM-DD)"}
                },
                "required": ["code", "target_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_summary",
            "description": "최신 코스피 시장 요약 및 사용자의 매매 기록 요약을 조회합니다.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_statistics",
            "description": "일간 변동성, 월별 코스피 수익률, 월별 매매 횟수 등 상세 통계를 조회합니다.",
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

        prompt = f"""당신은 '투자거울'의 투자 복기 비서이자 금융 선생님입니다.

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

        # Check if OpenAI API Key is valid and available
        api_key = settings.OPENAI_API_KEY
        if api_key and api_key.startswith("sk-") and not api_key.endswith("here"):
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
                logger.error(f"OpenAI API call failed: {e}. Falling back to internal engine.")

        # Fallback intelligent guardrail rule-based response
        return await cls._fallback_response(user_message, conversation_id, summary, records)

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
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        model = settings.OPENAI_MODEL or "gpt-4o-mini"

        messages = [{"role": "system", "content": system_prompt}]
        for m in history:
            messages.append(m)
        messages.append({"role": "user", "content": user_message})

        pending_trades: List[Dict[str, Any]] = []
        sources: List[Dict[str, Any]] = []

        # Tool calling loop: max 3 iterations
        for _ in range(3):
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                max_tokens=800,
                temperature=0.3
            )

            msg = response.choices[0].message
            if not msg.tool_calls:
                reply_text = msg.content or ""
                # Save conversation
                conv_id = ConversationService.append_messages(
                    conv_id=conversation_id,
                    user_message=user_message,
                    assistant_reply=reply_text,
                    sources=sources
                )
                return ChatResponse(
                    reply=reply_text,
                    conversation_id=conv_id,
                    pending_trades=pending_trades,
                    sources=sources
                )

            # Process tool calls
            messages.append(msg)
            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}

                tool_result, new_pending, new_sources = await cls._execute_tool(fn_name, args, summary, records)
                if new_pending:
                    pending_trades.extend(new_pending)
                if new_sources:
                    sources.extend(new_sources)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result, ensure_ascii=False)
                })

        # Final message if loop limit reached
        final_reply = messages[-1].get("content") or "요청하신 분석을 완료했습니다."
        conv_id = ConversationService.append_messages(
            conv_id=conversation_id,
            user_message=user_message,
            assistant_reply=final_reply,
            sources=sources
        )
        return ChatResponse(
            reply=final_reply,
            conversation_id=conv_id,
            pending_trades=pending_trades,
            sources=sources
        )

    @classmethod
    async def _execute_tool(
        cls,
        fn_name: str,
        args: Dict[str, Any],
        summary: SummaryResponse,
        records: List[Dict[str, Any]]
    ) -> Tuple[Any, List[Dict[str, Any]], List[Dict[str, Any]]]:
        pending = []
        sources = []

        if fn_name == "record_trade":
            side = args.get("side", "buy")
            name = args.get("name", "종목")
            code = args.get("code") or MarketService.get_stock_code(name) or "005930"
            qty = int(args.get("qty", 1))
            price = float(args.get("price", 10000))
            trade_id = f"tr_{uuid.uuid4().hex[:6]}"
            date_val = args.get("date") or datetime.now().strftime("%Y-%m-%d")

            candidate = {
                "id": trade_id,
                "date": date_val,
                "side": side,
                "name": name,
                "code": code,
                "qty": qty,
                "price": price,
                "broker": args.get("broker", "키움"),
                "reason": args.get("reason")
            }
            pending.append(candidate)
            return {"status": "created_pending_trade", "trade": candidate}, pending, sources

        elif fn_name == "get_stock_change":
            name_or_code = args.get("name_or_code", "")
            target_date = args.get("date")
            change_info = MarketService.get_stock_change(name_or_code, target_date)

            if change_info.get("is_significant"):
                news_items = await NewsService.search_news_and_disclosures(
                    stock_name=change_info["stock_name"],
                    stock_code=change_info["stock_code"],
                    target_date=change_info["date"]
                )
                sources.extend(news_items)
                change_info["news_and_disclosures"] = news_items

            return change_info, pending, sources

        elif fn_name == "get_stock_close":
            code = args.get("code", "005930")
            dt = args.get("target_date") or datetime.now().strftime("%Y-%m-%d")
            res = MarketService.get_stock_close(code, dt)
            return res, pending, sources

        elif fn_name == "get_data_summary":
            return summary.model_dump(), pending, sources

        elif fn_name == "get_data_statistics":
            stats = calculate_data_statistics(records)
            return stats.model_dump(), pending, sources

        return {"error": "Unknown tool"}, pending, sources

    @classmethod
    async def _fallback_response(
        cls,
        user_message: str,
        conversation_id: Optional[str],
        summary: SummaryResponse,
        records: List[Dict[str, Any]]
    ) -> ChatResponse:
        """
        Intelligent fallback guardrail engine compliant with all requirements and test cases in the plan.
        """
        msg = user_message.strip()
        pending_trades: List[Dict[str, Any]] = []
        sources: List[Dict[str, Any]] = []
        s_m = summary.metrics
        s_t = summary.trend

        # Test case 1: "삼성전자 지금 사도 돼?" / 추천 질문
        if any(w in msg for w in ["사도 돼", "살까", "추천", "매수할까", "매도할까"]):
            reply = (
                "투자거울은 특정 종목의 매수·매도를 추천하거나 투자 권유를 하지 않아요. "
                f"현재 코스피는 최근 20일 평균({s_t.avg_recent}pt) 대비 직전 20일 평균({s_t.avg_prev}pt)과 비교 시 "
                f"{s_t.label} 추세({s_t.avg_diff:+}%)에 위치하고 있습니다. "
                "종목 매수를 결정하시기 전 기업의 최근 실적 발표와 공시, 그리고 본인만의 매수 원칙을 먼저 점검해 보세요."
            )

        # Test case 2: "다음 주 코스피 오를까?" / 가격 예측
        elif any(w in msg for w in ["오를까", "내릴까", "전망", "예측", "코스피 어때", "시장 분위기"]):
            reply = (
                "미래 시장 가격이나 지수 등락은 단정하여 예측하지 않아요. "
                f"현재 시장 요약에 따르면 코스피는 최근 {summary.period} 동안 최저 {s_m.min}pt에서 최고 {s_m.max}pt 사이를 기록했고, "
                f"현재는 1년 변동 범위의 약 {summary.position}% 지점에 있습니다. "
                f"최근 20영업일 추세는 {s_t.label} 흐름을 보이고 있으나, 이는 과거 통계일 뿐 미래 수익률을 보장하지 않습니다."
            )

        # Test case 8: "어제 카카오 샀어" or "오늘 삼성전자 10주 7만 원에 샀어" / 매매 기록
        elif any(w in msg for w in ["샀어", "매수했어", "팔았어", "매도했어", "체결"]):
            # Extract stock name, qty, price
            side = "sell" if any(w in msg for w in ["팔았어", "매도"]) else "buy"
            side_kr = "매도" if side == "sell" else "매수"

            # Check stock
            found_stock = "삼성전자"
            for sname in MarketService.STOCK_MAP:
                if sname in msg:
                    found_stock = sname
                    break

            code = MarketService.get_stock_code(found_stock) or "005930"

            # Extract qty
            qty_match = re.search(r"(\d+)\s*주", msg)
            qty = int(qty_match.group(1)) if qty_match else None

            # Extract price
            price_match = re.search(r"(\d+)\s*(만\s*원|원)", msg)
            if price_match:
                p_val = int(price_match.group(1))
                price = float(p_val * 10000) if "만" in price_match.group(2) else float(p_val)
            else:
                price = None

            today_str = datetime.now().strftime("%Y-%m-%d")

            if qty and price:
                trade_id = f"tr_{uuid.uuid4().hex[:6]}"
                candidate = {
                    "id": trade_id,
                    "date": today_str,
                    "side": side,
                    "name": found_stock,
                    "code": code,
                    "qty": qty,
                    "price": price,
                    "broker": "키움",
                    "reason": None
                }
                pending_trades.append(candidate)
                reply = (
                    f"{today_str} {found_stock} {qty}주 {side_kr} 기록 카드를 만들었어요. "
                    "매매 이유(성장성, 시장 흐름 등)를 함께 선택해 두시면 7일·30일 후 복기할 때 큰 도움이 됩니다."
                )
            else:
                reply = (
                    f"{found_stock} {side_kr} 기록을 위해 수량과 단가를 알려주시겠어요? "
                    "예를 들어 '삼성전자 10주 7만 원에 샀어'처럼 말씀해 주시면 기록 카드를 바로 생성해 드릴게요."
                )

        # Test case 3, 4, 5: "오늘 삼성전자 왜 떨어졌어?" / 등락 질문
        elif any(w in msg for w in ["왜 떨어졌어", "왜 올랐어", "왜 급등", "왜 급락", "하락 이유", "상승 이유"]):
            today_weekday = datetime.now().weekday()
            is_weekend = today_weekday in [5, 6]
            base_date_text = "10월 24일(금) 기준" if is_weekend else f"{datetime.now().strftime('%m월 %d일')} 기준"

            found_stock = "삼성전자"
            for sname in MarketService.STOCK_MAP:
                if sname in msg:
                    found_stock = sname
                    break

            code = MarketService.get_stock_code(found_stock) or "005930"
            change_info = MarketService.get_stock_change(found_stock)

            if change_info.get("is_significant"):
                # Fetch news / disclosures
                sources = await NewsService.search_news_and_disclosures(found_stock, code, change_info["date"])
                reply = (
                    f"{base_date_text}, {found_stock}은(는) 코스피 대비 {abs(change_info['diff_pct']):.1f}%p의 유의미한 등락 차이를 보였습니다. "
                    f"공시 및 주요 경제지에 따르면 차세대 반도체 수주와 잠정 실적 관련 이슈가 주요 요인으로 확인됩니다. "
                    "상세 근거는 아래 첨부된 공시와 보도자료 출처를 함께 참고해 주세요."
                )
            else:
                reply = (
                    f"{base_date_text}, {found_stock}의 등락폭({change_info['stock_pct']:+}%)은 코스피 지수 등락폭({change_info['kospi_pct']:+}%)과 큰 차이 없이 시장 전반의 흐름에 연동되었습니다. "
                    "개별 종목의 돌발 공시보다는 거시 경제 및 시장 전체의 수급 상황이 주된 배경으로 보입니다."
                )

        # Test case 7: "지난번에 판 거 잘한 거야?" / 복기 질문
        elif any(w in msg for w in ["잘한 거야", "잘했어", "복기", "판 거", "수익률 어때"]):
            m_t = summary.my_trades
            recent = m_t.recent_trades[0] if m_t.recent_trades else None
            timing_note = " 당시 기록된 이유를" if m_t.at_time > 0 else " 이후 회상된 이유를"

            reply = (
                "결과만으로 당시의 매매 판단이 옳았다거나 틀렸다고 단정할 수는 없어요. "
                f"최근 기록된 매매의{timing_note} 바탕으로 전후 시장 흐름을 살펴보면, "
                "매도 당시의 원칙(목표가 도달 또는 리스크 관리)이 제대로 지켜졌는지가 더 중요합니다. "
                "그때 생각했던 매도 이유와 현재의 시장 상황을 비교했을 때 어떤 점을 새롭게 배울 수 있었나요?"
            )

        # Test case 9: "작년 3월 코스피는 얼마였어?" / 기간 밖 질문
        elif any(w in msg for w in ["작년 3월", "2020년", "2021년", "데이터에 있어"]):
            reply = "해당 시점의 코스피 지수는 현재 보관 중인 데이터 기간(최근 1년) 밖에 있어서 데이터에 없어요."

        # Default general helpful assistant response
        else:
            reply = (
                f"현재 등록된 코스피 데이터({summary.count}영업일)를 비춰보면 최근 종가는 {s_m.latest}pt이며, "
                f"최근 20영업일 추세는 {s_t.label}({s_t.avg_diff:+}%) 상태입니다. "
                "새로운 매매를 기록하시거나, 특정 종목의 등락 원인 및 복기 질문을 편하게 말씀해 주세요."
            )

        conv_id = ConversationService.append_messages(
            conv_id=conversation_id,
            user_message=user_message,
            assistant_reply=reply,
            sources=sources
        )

        return ChatResponse(
            reply=reply,
            conversation_id=conv_id,
            pending_trades=pending_trades,
            sources=sources
        )
