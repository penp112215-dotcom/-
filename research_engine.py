"""AI 投研模块的轻量数据层与异步任务层。

面向 2 核 2GB VPS：使用公开行情、SQLite 和单后台线程，不在服务器运行大模型。
模型接口遵循 OpenAI-compatible ``/chat/completions`` 协议，密钥仅从环境变量读取。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

import requests


REQUEST_TIMEOUT = 8
RESEARCH_DB_PATH = Path(
    os.getenv(
        "RESEARCH_DB_PATH",
        str(Path(__file__).resolve().parent / "data" / "research.db"),
    )
)
AI_BASE_URL = os.getenv("AI_BASE_URL", "").rstrip("/")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "")
AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "180"))
AI_PROVIDER = os.getenv("AI_PROVIDER", "未配置")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://quote.eastmoney.com/",
}

INDEX_SECIDS = (
    ("上证指数", "1.000001"),
    ("深证成指", "0.399001"),
    ("创业板指", "0.399006"),
    ("恒生指数", "100.HSI"),
    ("标普500", "100.SPX"),
    ("纳斯达克", "100.NDX"),
)
TENCENT_INDEX_SYMBOLS = (
    "sh000001",
    "sz399001",
    "sz399006",
    "hkHSI",
    "usINX",
    "usIXIC",
)

_db_lock = threading.Lock()
_worker_started = False
_worker_lock = threading.Lock()


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _connection() -> sqlite3.Connection:
    RESEARCH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(RESEARCH_DB_PATH, timeout=8)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS research_notes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            symbol TEXT NOT NULL DEFAULT '',
            note_type TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS research_tasks (
            id TEXT PRIMARY KEY,
            task_type TEXT NOT NULL,
            symbol TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            prompt TEXT NOT NULL,
            context_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            stage TEXT NOT NULL DEFAULT '',
            result TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _request_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> dict | None:
    try:
        response = requests.get(
            url,
            params=params,
            headers=headers or HEADERS,
            timeout=timeout,
        )
        if response.status_code == 200:
            return response.json()
    except (requests.RequestException, ValueError):
        pass
    return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _market_label(value: str) -> str:
    text = value.upper()
    if any(term in text for term in ("美股", "NASDAQ", "NYSE", "AMEX")):
        return "美股"
    if any(term in text for term in ("港股", "HK")):
        return "港股"
    return "A股"


def _normalize_search_row(raw: dict) -> dict | None:
    code = str(raw.get("Code") or raw.get("code") or "").strip()
    name = str(raw.get("Name") or raw.get("name") or code).strip()
    quote_code = str(
        raw.get("QuoteID")
        or raw.get("QuotationCode")
        or raw.get("quoteCode")
        or ""
    ).strip()
    market_num = str(raw.get("MktNum") or raw.get("market") or "").strip()
    security_type = str(
        raw.get("SecurityTypeName") or raw.get("Classify") or ""
    ).strip()
    if not code or not name:
        return None
    if not quote_code and market_num:
        quote_code = f"{market_num}.{code}"
    if not quote_code:
        if re.fullmatch(r"\d{6}", code):
            quote_code = ("1." if code.startswith(("5", "6", "9")) else "0.") + code
        else:
            return None
    return {
        "symbol": code.upper(),
        "name": name,
        "quote_code": quote_code,
        "market": _market_label(security_type),
        "security_type": security_type or "股票",
    }


def search_assets(query: str, limit: int = 12) -> dict[str, Any]:
    clean = str(query or "").strip()[:40]
    if not clean:
        return {"query": clean, "items": []}
    items = []
    seen = set()
    try:
        response = requests.get(
            "https://smartbox.gtimg.cn/s3/",
            params={"q": clean, "t": "all"},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        match = re.search(r'v_hint="(.*)"', response.text, re.S)
        decoded = json.loads(f'"{match.group(1)}"') if match else ""
    except (requests.RequestException, ValueError, json.JSONDecodeError):
        decoded = ""

    for record in decoded.split("^"):
        fields = record.split("~")
        if len(fields) < 5:
            continue
        market, raw_code, name, _pinyin, security_type = fields[:5]
        market = market.lower()
        security_type = security_type.upper()
        if not (security_type.startswith("GP") or security_type in {"ETF", "ZS"}):
            continue
        symbol = raw_code.upper()
        if market == "sh":
            quote_code, market_label = f"1.{symbol}", "A股"
        elif market == "sz":
            quote_code, market_label = f"0.{symbol}", "A股"
        elif market == "hk":
            quote_code, market_label = f"116.{symbol}", "港股"
        elif market == "us":
            parts = symbol.split(".", 1)
            suffix = parts[1].lower() if len(parts) > 1 else ""
            market_id = "105" if suffix == "oq" else "106" if suffix == "n" else "107"
            symbol = parts[0]
            quote_code, market_label = f"{market_id}.{symbol}", "美股"
        else:
            continue
        if quote_code in seen:
            continue
        item = {
            "symbol": symbol,
            "name": name,
            "quote_code": quote_code,
            "market": market_label,
            "security_type": (
                "指数" if security_type == "ZS" else "ETF" if security_type == "ETF" else "股票"
            ),
        }
        seen.add(quote_code)
        items.append(item)
        if len(items) >= limit:
            break
    return {"query": clean, "items": items}


def fetch_asset_snapshot(quote_code: str) -> dict[str, Any]:
    clean = re.sub(r"[^A-Za-z0-9.]", "", quote_code)[:32]
    if not re.fullmatch(r"(?:0|1|105|106|107|116)\.[A-Za-z0-9-]{1,15}", clean):
        return {"status": "invalid", "message": "缺少市场代码"}
    payload = _request_json(
        "https://push2.eastmoney.com/api/qt/stock/get",
        params={
            "secid": clean,
            "fltt": 2,
            "invt": 2,
            "fields": (
                "f57,f58,f43,f44,f45,f46,f47,f48,f60,f116,f117,"
                "f162,f167,f168,f170,f171,f292"
            ),
        },
    )
    data = (payload or {}).get("data") or {}
    if not data:
        return _fetch_tencent_asset(clean)
    price = _number(data.get("f43"))
    preclose = _number(data.get("f60"))
    change_pct = _number(data.get("f170"))
    if change_pct is None and price is not None and preclose:
        change_pct = (price / preclose - 1) * 100
    return {
        "status": "success",
        "updated_at": _now(),
        "symbol": str(data.get("f57") or clean.split(".", 1)[-1]),
        "name": str(data.get("f58") or clean),
        "quote_code": clean,
        "price": price,
        "preclose": preclose,
        "change_pct": round(change_pct or 0.0, 3),
        "high": _number(data.get("f44")),
        "low": _number(data.get("f45")),
        "open": _number(data.get("f46")),
        "volume": _number(data.get("f47")),
        "amount": _number(data.get("f48")),
        "market_cap": _number(data.get("f116")),
        "float_market_cap": _number(data.get("f117")),
        "pe": _number(data.get("f162")),
        "pb": _number(data.get("f167")),
        "turnover_rate": _number(data.get("f168")),
        "change_amount": _number(data.get("f171")),
        "market": str(data.get("f292") or ""),
        "source": "东方财富公开行情",
    }


def _fetch_tencent_asset(quote_code: str) -> dict[str, Any]:
    """东财单股接口异常时，使用腾讯公开行情作为备用源。"""
    market_id, symbol = quote_code.split(".", 1)
    prefix = {
        "1": "sh",
        "0": "sz",
        "116": "hk",
        "105": "us",
        "106": "us",
        "107": "us",
    }.get(market_id)
    if not prefix:
        return {"status": "unavailable", "message": "行情暂不可用"}
    try:
        response = requests.get(
            f"https://qt.gtimg.cn/q={prefix}{symbol}",
            headers={**HEADERS, "Referer": "https://gu.qq.com/"},
            timeout=REQUEST_TIMEOUT,
        )
        text = response.content.decode("gb18030", errors="ignore")
        body = text.split('="', 1)[1].rsplit('"', 1)[0]
        fields = body.split("~")
    except (requests.RequestException, IndexError):
        return {"status": "unavailable", "message": "行情暂不可用"}
    if len(fields) < 47 or _number(fields[3]) is None:
        return {"status": "unavailable", "message": "行情暂不可用"}

    market_cap_yi = _number(fields[44])
    float_market_cap_yi = _number(fields[45])
    return {
        "status": "success",
        "updated_at": _now(),
        "symbol": symbol.upper(),
        "name": fields[1] or symbol.upper(),
        "quote_code": quote_code,
        "price": _number(fields[3]),
        "preclose": _number(fields[4]),
        "change_pct": round(_number(fields[32]) or 0.0, 3),
        "high": _number(fields[33]),
        "low": _number(fields[34]),
        "open": _number(fields[5]),
        "volume": _number(fields[6]),
        "amount": (
            (_number(fields[37]) or 0.0) * 10_000
            if prefix in {"sh", "sz"}
            else _number(fields[37])
        ),
        "market_cap": market_cap_yi * 100_000_000 if market_cap_yi else None,
        "float_market_cap": (
            float_market_cap_yi * 100_000_000 if float_market_cap_yi else None
        ),
        "pe": _number(fields[39]),
        "pb": _number(fields[46]) if prefix in {"sh", "sz"} else None,
        "turnover_rate": _number(fields[38]),
        "change_amount": _number(fields[31]),
        "market": "A股" if prefix in {"sh", "sz"} else "港股" if prefix == "hk" else "美股",
        "source": "腾讯公开行情（备用）",
    }


def get_research_overview() -> dict[str, Any]:
    secids = ",".join(item[1] for item in INDEX_SECIDS)
    payload = _request_json(
        "https://push2.eastmoney.com/api/qt/ulist.np/get",
        params={
            "secids": secids,
            "fltt": 2,
            "invt": 2,
            "fields": "f12,f13,f14,f2,f3,f4,f6,f124",
        },
    )
    rows = ((payload or {}).get("data") or {}).get("diff") or []
    names = {code.split(".", 1)[-1]: name for name, code in INDEX_SECIDS}
    indices = []
    for raw in rows:
        code = str(raw.get("f12") or "")
        price = _number(raw.get("f2"))
        if price is None:
            continue
        indices.append(
            {
                "code": code,
                "name": names.get(code, str(raw.get("f14") or code)),
                "price": price,
                "change_pct": round(_number(raw.get("f3")) or 0.0, 3),
                "change": _number(raw.get("f4")),
                "amount": _number(raw.get("f6")),
            }
        )
    if len(indices) < 4:
        fallback = _fetch_tencent_indices()
        if len(fallback) > len(indices):
            indices = fallback
    configured = bool(AI_BASE_URL and AI_API_KEY and AI_MODEL)
    return {
        "status": "success" if indices else "partial",
        "updated_at": _now(),
        "indices": indices,
        "ai": {
            "configured": configured,
            "provider": AI_PROVIDER if configured else "未配置",
            "model": AI_MODEL if configured else "",
            "message": (
                "AI服务已就绪"
                if configured
                else "行情与研究记录可用；配置模型后启用AI复盘和多空辩论"
            ),
        },
        "features": [
            {"key": "review", "name": "今日复盘", "ready": True},
            {"key": "stock", "name": "个股研究", "ready": True},
            {"key": "debate", "name": "多空辩论", "ready": configured},
            {"key": "notes", "name": "研究记录", "ready": True},
        ],
    }


def _fetch_tencent_indices() -> list[dict[str, Any]]:
    try:
        response = requests.get(
            "https://qt.gtimg.cn/q=" + ",".join(TENCENT_INDEX_SYMBOLS),
            headers={**HEADERS, "Referer": "https://gu.qq.com/"},
            timeout=REQUEST_TIMEOUT,
        )
        text = response.content.decode("gb18030", errors="ignore")
    except requests.RequestException:
        return []
    results = []
    for line in text.splitlines():
        if '="' not in line:
            continue
        try:
            body = line.split('="', 1)[1].rsplit('"', 1)[0]
            fields = body.split("~")
            price = _number(fields[3])
            if price is None:
                continue
            results.append(
                {
                    "code": fields[2],
                    "name": fields[1],
                    "price": price,
                    "change_pct": round(_number(fields[32]) or 0.0, 3),
                    "change": _number(fields[31]),
                    "amount": _number(fields[37]),
                }
            )
        except IndexError:
            continue
    return results


def list_notes(limit: int = 30) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 100))
    with _db_lock, closing(_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM research_notes ORDER BY updated_at DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def create_note(
    title: str,
    content: str,
    symbol: str = "",
    note_type: str = "manual",
) -> dict[str, Any]:
    note_id = uuid.uuid4().hex
    now = _now()
    row = {
        "id": note_id,
        "title": str(title or "研究记录").strip()[:120],
        "content": str(content or "").strip()[:50_000],
        "symbol": str(symbol or "").strip()[:20].upper(),
        "note_type": str(note_type or "manual").strip()[:30],
        "created_at": now,
        "updated_at": now,
    }
    with _db_lock, closing(_connection()) as connection:
        connection.execute(
            """
            INSERT INTO research_notes
                (id, title, content, symbol, note_type, created_at, updated_at)
            VALUES (:id, :title, :content, :symbol, :note_type, :created_at, :updated_at)
            """,
            row,
        )
        connection.commit()
    return row


def delete_note(note_id: str) -> bool:
    with _db_lock, closing(_connection()) as connection:
        cursor = connection.execute(
            "DELETE FROM research_notes WHERE id = ?", (note_id,)
        )
        connection.commit()
        return cursor.rowcount > 0


def _task_row(task_id: str) -> dict[str, Any] | None:
    with _db_lock, closing(_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM research_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        try:
            result["context"] = json.loads(result.pop("context_json") or "{}")
        except ValueError:
            result["context"] = {}
        return result


def create_research_task(
    task_type: str,
    title: str,
    prompt: str,
    symbol: str = "",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_id = uuid.uuid4().hex
    now = _now()
    configured = bool(AI_BASE_URL and AI_API_KEY and AI_MODEL)
    status = "queued" if configured else "needs_config"
    stage = "等待后台处理" if configured else "需要配置AI服务"
    with _db_lock, closing(_connection()) as connection:
        connection.execute(
            """
            INSERT INTO research_tasks (
                id, task_type, symbol, title, prompt, context_json, status,
                progress, stage, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                str(task_type or "research")[:30],
                str(symbol or "").upper()[:20],
                str(title or "AI投研任务")[:120],
                str(prompt or "")[:20_000],
                json.dumps(context or {}, ensure_ascii=False),
                status,
                0,
                stage,
                now,
                now,
            ),
        )
        connection.commit()
    start_worker()
    return _task_row(task_id) or {"id": task_id, "status": status}


def get_research_task(task_id: str) -> dict[str, Any] | None:
    return _task_row(task_id)


def list_research_tasks(limit: int = 20) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 50))
    with _db_lock, closing(_connection()) as connection:
        rows = connection.execute(
            "SELECT id FROM research_tasks ORDER BY created_at DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    return [task for row in rows if (task := _task_row(row["id"]))]


def _update_task(task_id: str, **values: Any) -> None:
    allowed = {"status", "progress", "stage", "result", "error", "updated_at"}
    updates = {key: value for key, value in values.items() if key in allowed}
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    with _db_lock, closing(_connection()) as connection:
        connection.execute(
            f"UPDATE research_tasks SET {assignments} WHERE id = ?",
            [*updates.values(), task_id],
        )
        connection.commit()


def _claim_task() -> dict[str, Any] | None:
    with _db_lock, closing(_connection()) as connection:
        row = connection.execute(
            """
            SELECT id FROM research_tasks
            WHERE status IN ('queued', 'running')
            ORDER BY created_at ASC LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        connection.execute(
            """
            UPDATE research_tasks
            SET status='running', progress=10, stage='正在组织客观数据', updated_at=?
            WHERE id=?
            """,
            (_now(), row["id"]),
        )
        connection.commit()
    return _task_row(row["id"])


def _system_prompt(task_type: str) -> str:
    common = (
        "你是中立的个人投研助手。只依据提供的客观数据进行整理，不预测涨跌，"
        "不提供买卖指令，不承诺收益。明确区分事实、推断和数据缺口，并用中文回答。"
    )
    if task_type == "debate":
        return common + (
            "输出：多方论据、空方风险、双方共识、真正分歧、待验证清单。"
            "每条论据标明依据；没有数据支持必须明确说明。"
        )
    if task_type == "review":
        return common + "输出市场事实摘要、主要变化、需要继续跟踪的数据，不给方向性结论。"
    return common + "按估值、财务质量、资金面、行业景气、事件与风险五部分组织。"


def _call_ai(task: dict[str, Any]) -> str:
    context = task.get("context") or {}
    response = requests.post(
        f"{AI_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": AI_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": _system_prompt(task["task_type"])},
                {
                    "role": "user",
                    "content": (
                        f"任务：{task['prompt']}\n\n"
                        f"客观数据：\n{json.dumps(context, ensure_ascii=False, indent=2)}"
                    ),
                },
            ],
        },
        timeout=AI_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["choices"][0]["message"]["content"]).strip()


def _worker_loop() -> None:
    idle_rounds = 0
    while idle_rounds < 12:
        task = _claim_task()
        if not task:
            idle_rounds += 1
            time.sleep(5)
            continue
        idle_rounds = 0
        task_id = task["id"]
        try:
            _update_task(task_id, progress=35, stage="AI正在分析客观数据")
            result = _call_ai(task)
            _update_task(
                task_id,
                status="completed",
                progress=100,
                stage="分析完成",
                result=result,
                error="",
            )
        except Exception as exc:
            _update_task(
                task_id,
                status="failed",
                progress=100,
                stage="分析失败",
                error=str(exc)[:500],
            )
    global _worker_started
    with _worker_lock:
        _worker_started = False


def start_worker() -> None:
    global _worker_started
    if not (AI_BASE_URL and AI_API_KEY and AI_MODEL):
        return
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True
        thread = threading.Thread(
            target=_worker_loop,
            name="research-ai-worker",
            daemon=True,
        )
        thread.start()


# 确保数据库可用，并在服务重启后恢复未完成任务。
with closing(_connection()):
    pass
start_worker()
