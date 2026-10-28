"""
투자거울 (Investment Mirror) MCP (Model Context Protocol) Server
Claude Desktop, Cursor 등 외부 MCP 클라이언트에서 투자거울 도구를 호출할 수 있도록 표준 JSON-RPC 프로토콜을 제공합니다.
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict

# Add backend directory to sys.path so app modules can be loaded
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(os.path.dirname(current_dir))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.services.analytics_service import calculate_data_statistics
from app.services.data_service import DataService
from app.services.market_service import MarketService
from app.services.news_service import NewsService
from app.services.summary_service import calculate_data_summary

# Tool definitions
TOOLS = [
    {
        "name": "get_data_summary",
        "description": "최신 코스피 시장 요약 및 사용자의 매매 기록 요약을 반환합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_stock_change",
        "description": "특정 종목과 코스피의 등락률을 비교하고 차이가 2%p 이상이면 공시와 뉴스를 함께 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name_or_code": {"type": "string", "description": "종목명(예: 삼성전자) 또는 종목코드(예: 005930)"},
                "date": {"type": "string", "description": "조회 날짜 (YYYY-MM-DD, 선택사항)"}
            },
            "required": ["name_or_code"]
        }
    },
    {
        "name": "get_data_statistics",
        "description": "코스피 일간 변동성, 월별 수익률, 매매 횟수 등 상세 통계 지표를 반환합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "record_trade",
        "description": "새로운 주식 매매 내역(후보)을 생성합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "side": {"type": "string", "enum": ["buy", "sell"], "description": "매수 또는 매도"},
                "name": {"type": "string", "description": "종목명"},
                "qty": {"type": "integer", "description": "수량"},
                "price": {"type": "number", "description": "단가"},
                "reason": {"type": "string", "description": "매매 이유 (성장성, 시장 흐름 등)"}
            },
            "required": ["side", "name", "qty", "price"]
        }
    }
]


async def handle_tool_call(name: str, arguments: Dict[str, Any]) -> Any:
    records = DataService.get_all_records()

    if name == "get_data_summary":
        summary = calculate_data_summary(records)
        return summary.model_dump()

    elif name == "get_stock_change":
        name_or_code = arguments.get("name_or_code", "삼성전자")
        dt = arguments.get("date")
        change_info = MarketService.get_stock_change(name_or_code, dt)
        if change_info.get("is_significant"):
            news = await NewsService.search_news_and_disclosures(
                stock_name=change_info["stock_name"],
                stock_code=change_info["stock_code"],
                target_date=change_info["date"]
            )
            change_info["news_and_disclosures"] = news
        return change_info

    elif name == "get_data_statistics":
        stats = calculate_data_statistics(records)
        return stats.model_dump()

    elif name == "record_trade":
        return {
            "status": "candidate_created",
            "details": arguments,
            "message": "매매 후보가 생성되었습니다. 투자거울 웹 화면에서 확인 후 등록할 수 있습니다."
        }

    raise ValueError(f"Unknown tool: {name}")


async def run_stdio_server():
    """Runs a standard MCP stdio JSON-RPC loop"""
    while True:
        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        try:
            req = json.loads(line.strip())
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if method == "initialize":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "investment-mirror-mcp", "version": "1.0.0"}
                    }
                }
            elif method == "tools/list":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": TOOLS}
                }
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                content = await handle_tool_call(tool_name, tool_args)
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(content, ensure_ascii=False, indent=2)}]
                    }
                }
            else:
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method {method} not found"}
                }

            sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"MCP Server Error: {e}\n")


if __name__ == "__main__":
    asyncio.run(run_stdio_server())
