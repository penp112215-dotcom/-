"""
轻量级数据引擎 —— 为微信小程序提供 A股套利 / 美股持仓 / 资讯聚合 三个数据接口。

设计原则：
1. 每个接口都尝试抓取真实数据（新浪行情、天天金估值、东方财富、币安合约）。
2. 任意单源失败都不影响整体返回，降级为占位数据并标注 `source: "placeholder"`，
   保证小程序前端始终拿到结构稳定的 JSON。
3. 全程 try/except，对外不抛 500。
"""

from __future__ import annotations

import datetime as _dt
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from arbitrage_engine import build_arbitrage_snapshot, get_arbitrage_history
from research_engine import (
    create_note,
    create_research_task,
    delete_note,
    fetch_asset_snapshot,
    fetch_research_dossier,
    get_research_overview,
    get_research_task,
    list_notes,
    list_research_tasks,
    search_assets,
)

# ---------------------------------------------------------------------------
# 全局配置
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = 6  # 单源请求超时（秒），抓不到就降级


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 旧版默认美股监控标的；新版前端会通过 symbols 参数传入用户自选。
US_STOCKS = [
    ("MSFT", "105.MSFT", "微软"),
    ("CEG", "105.CEG", "星座能源"),
    ("NVDA", "105.NVDA", "英伟达"),
]

# ---------------------------------------------------------------------------
# 兜底 / 占位数据：所有外部源失败/超时时使用，绝不返回 null
# 数值为贴近真实行情的模拟值，仅保证结构可用，source 标注 "placeholder"
# ---------------------------------------------------------------------------
FALLBACK_US = {
    "MSFT": {"name": "微软", "price": 450.25, "preclose": 444.91, "change_pct": 1.20},
    "CEG": {"name": "Constellation Energy Corp", "price": 268.50, "preclose": 266.24, "change_pct": 0.85},
    "NVDA": {"name": "英伟达", "price": 199.50, "preclose": 198.47, "change_pct": 0.52},
}

FALLBACK_CRYPTO = {
    "BTCUSDT": {"symbol": "BTCUSDT", "name": "Bitcoin", "price": 104000.0, "change_pct_24h": 0.0, "high_24h": 105000.0, "low_24h": 102000.0, "quote_volume_24h": 0.0},
    "SOLUSDT": {"symbol": "SOLUSDT", "name": "Solana", "price": 150.0, "change_pct_24h": 0.0, "high_24h": 155.0, "low_24h": 145.0, "quote_volume_24h": 0.0},
}

FALLBACK_FEAR_GREED = {"value": 50, "classification": "Neutral", "updated_at": "unavailable"}

app = FastAPI(
    title="小程序数据引擎",
    version="0.1.0",
    description="A股套利 / 美股持仓 / 资讯聚合",
)

# 跨域：开发期放开所有源，便于本地小程序模拟器直接请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 通用抓取工具
# ---------------------------------------------------------------------------
def _safe_get(url: str, headers: dict | None = None, **kw) -> requests.Response | None:
    try:
        timeout = kw.pop("timeout", REQUEST_TIMEOUT)
        resp = requests.get(url, headers=headers, timeout=timeout, **kw)
        if resp.status_code == 200:
            return resp
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 1. A股基金套利接口
# ---------------------------------------------------------------------------
@app.get("/api/arbitrage")
def arbitrage() -> dict[str, Any]:
    """全市场 LOF 价差、申购状态、账户容量和净空间筛选。"""
    return build_arbitrage_snapshot()


@app.get("/api/arbitrage/history/{code}")
def arbitrage_history(code: str, days: int = 3) -> dict[str, Any]:
    """返回单只基金最近 1-30 天的溢价与状态历史。"""
    if not (code.isdigit() and len(code) == 6):
        raise HTTPException(status_code=400, detail="基金代码必须为6位数字")
    return get_arbitrage_history(code, days)


# ---------------------------------------------------------------------------
# AI 投研：市场复盘、跨市场搜索、研究记录和异步模型任务
# ---------------------------------------------------------------------------
class ResearchNoteInput(BaseModel):
    title: str = Field(default="研究记录", max_length=120)
    content: str = Field(min_length=1, max_length=50_000)
    symbol: str = Field(default="", max_length=20)
    note_type: str = Field(default="manual", max_length=30)


class ResearchTaskInput(BaseModel):
    task_type: str = Field(default="research", max_length=30)
    title: str = Field(default="AI投研任务", max_length=120)
    prompt: str = Field(min_length=1, max_length=20_000)
    symbol: str = Field(default="", max_length=20)
    context: dict[str, Any] = Field(default_factory=dict)


@app.get("/api/research/overview")
def research_overview() -> dict[str, Any]:
    return get_research_overview()


@app.get("/api/research/search")
def research_search(q: str = "") -> dict[str, Any]:
    return search_assets(q)


@app.get("/api/research/asset")
def research_asset(quote_code: str) -> dict[str, Any]:
    return fetch_asset_snapshot(quote_code)


@app.get("/api/research/dossier")
def research_dossier(quote_code: str, force: bool = False) -> dict[str, Any]:
    return fetch_research_dossier(quote_code, force)


@app.get("/api/research/notes")
def research_notes(limit: int = 30) -> dict[str, Any]:
    return {"items": list_notes(limit)}


@app.post("/api/research/notes")
def research_note_create(body: ResearchNoteInput) -> dict[str, Any]:
    return create_note(body.title, body.content, body.symbol, body.note_type)


@app.delete("/api/research/notes/{note_id}")
def research_note_delete(note_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-f0-9]{32}", note_id):
        raise HTTPException(status_code=400, detail="无效的记录编号")
    return {"deleted": delete_note(note_id)}


@app.get("/api/research/tasks")
def research_tasks(limit: int = 20) -> dict[str, Any]:
    return {"items": list_research_tasks(limit)}


@app.post("/api/research/tasks")
def research_task_create(body: ResearchTaskInput) -> dict[str, Any]:
    context = body.context
    quote_code = str(context.get("quote_code") or "")
    if quote_code:
        context = {"dossier": fetch_research_dossier(quote_code)}
    return create_research_task(
        body.task_type,
        body.title,
        body.prompt,
        body.symbol,
        context,
    )


@app.get("/api/research/tasks/{task_id}")
def research_task(task_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-f0-9]{32}", task_id):
        raise HTTPException(status_code=400, detail="无效的任务编号")
    task = get_research_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


# ---------------------------------------------------------------------------
# 2. 美股 + 加密合约 监控接口
# ---------------------------------------------------------------------------
def _fetch_us_stock(secid: str) -> dict | None:
    """东方财富美股行情：secid 形如 105.MSFT"""
    url = (
        "http://push2.eastmoney.com/api/qt/stock/get"
        f"?secid={secid}&fields=f43,f57,f58,f60,f169,f170&fltt=2"
    )
    resp = _safe_get(url)
    if not resp:
        return None
    try:
        d = resp.json().get("data") or {}
        return {
            "name": d.get("f58"),
            "price": d.get("f43"),
            "preclose": d.get("f60"),
            "change_pct": d.get("f170"),  # 涨跌幅 %
        }
    except (ValueError, KeyError):
        return None


_YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    )
}
_TRANSLATION_CACHE: dict[str, str] = {}
_NEWS_CACHE: dict[str, tuple[_dt.datetime, list[dict]]] = {}
_PUBLISHER_ZH = {
    "Yahoo Finance": "雅虎财经",
    "Reuters": "路透社",
    "Bloomberg": "彭博社",
    "The Motley Fool": "Motley Fool",
    "Associated Press Finance": "美联社",
}


def _normalize_us_symbol(value: str) -> str:
    """仅允许常见美股代码字符，防止把任意文本带入外部请求。"""
    symbol = re.sub(r"[^A-Za-z0-9.\-]", "", str(value or "")).upper()
    return symbol[:15]


def _has_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _translate_news_title(title: str) -> str:
    """把英文财经标题转换成中文；失败时返回空串，前端不展示英文兜底。"""
    title = str(title or "").strip()
    if not title:
        return ""
    if _has_chinese(title):
        return title
    cached = _TRANSLATION_CACHE.get(title)
    if cached:
        return cached
    resp = _safe_get(
        "https://translate.googleapis.com/translate_a/single",
        headers=_YAHOO_HEADERS,
        timeout=3,
        params={
            "client": "gtx",
            "sl": "auto",
            "tl": "zh-CN",
            "dt": "t",
            "q": title,
        },
    )
    if not resp:
        return ""
    try:
        translated = "".join(
            str(part[0] or "")
            for part in (resp.json()[0] or [])
            if isinstance(part, list) and part
        ).strip()
    except (ValueError, KeyError, IndexError, TypeError):
        return ""
    if not _has_chinese(translated):
        return ""
    if len(_TRANSLATION_CACHE) >= 1000:
        _TRANSLATION_CACHE.clear()
    _TRANSLATION_CACHE[title] = translated
    return translated


def _translate_news_titles(titles: list[str]) -> list[str]:
    """一只股票的新闻批量翻译，减少外部请求次数和首屏等待。"""
    results = [""] * len(titles)
    missing_indexes: list[int] = []
    missing_titles: list[str] = []
    for index, title in enumerate(titles):
        clean = str(title or "").strip()
        if _has_chinese(clean):
            results[index] = clean
        elif _TRANSLATION_CACHE.get(clean):
            results[index] = _TRANSLATION_CACHE[clean]
        elif clean:
            missing_indexes.append(index)
            missing_titles.append(clean)

    if not missing_titles:
        return results

    marker = "\n998877665544332211\n"
    resp = _safe_get(
        "https://translate.googleapis.com/translate_a/single",
        headers=_YAHOO_HEADERS,
        timeout=8,
        params={
            "client": "gtx",
            "sl": "auto",
            "tl": "zh-CN",
            "dt": "t",
            "q": marker.join(missing_titles),
        },
    )
    translated_parts: list[str] = []
    if resp:
        try:
            translated_text = "".join(
                str(part[0] or "")
                for part in (resp.json()[0] or [])
                if isinstance(part, list) and part
            )
            translated_parts = [
                part.strip() for part in translated_text.split(marker.strip())
            ]
        except (ValueError, KeyError, IndexError, TypeError):
            translated_parts = []

    if len(translated_parts) != len(missing_titles):
        translated_parts = [_translate_news_title(title) for title in missing_titles]

    for index, original, translated in zip(
        missing_indexes, missing_titles, translated_parts
    ):
        if _has_chinese(translated):
            results[index] = translated
            _TRANSLATION_CACHE[original] = translated
    if len(_TRANSLATION_CACHE) >= 1000:
        _TRANSLATION_CACHE.clear()
    return results


def _fetch_yahoo_quote(symbol: str) -> dict | None:
    """Yahoo Finance chart 行情，无需 API 密钥。"""
    resp = _safe_get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        headers=_YAHOO_HEADERS,
        params={"range": "5d", "interval": "1d"},
    )
    if not resp:
        return None
    try:
        result = (resp.json().get("chart", {}).get("result") or [])[0]
        meta = result.get("meta") or {}
        price = meta.get("regularMarketPrice")
        preclose = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price is None:
            return None
        change_pct = None
        if preclose not in (None, 0):
            change_pct = round((float(price) / float(preclose) - 1) * 100, 3)
        return {
            "symbol": symbol,
            "name": meta.get("longName") or meta.get("shortName") or symbol,
            "price": round(float(price), 4),
            "preclose": round(float(preclose), 4) if preclose is not None else None,
            "change_pct": change_pct,
            "currency": meta.get("currency") or "USD",
            "exchange": meta.get("exchangeName") or meta.get("fullExchangeName") or "",
            "market_time": meta.get("regularMarketTime"),
            "source": "yahoo",
        }
    except (ValueError, KeyError, IndexError, TypeError):
        return None


def _fetch_yahoo_news(symbol: str, limit: int = 10) -> list[dict]:
    """按股票代码获取关联新闻，失败时返回空数组而非演示新闻。"""
    cached = _NEWS_CACHE.get(symbol)
    if cached and (_dt.datetime.now() - cached[0]).total_seconds() < 600:
        return cached[1][:limit]
    resp = _safe_get(
        "https://query2.finance.yahoo.com/v1/finance/search",
        headers=_YAHOO_HEADERS,
        params={
            "q": symbol,
            "quotesCount": 1,
            "newsCount": max(limit * 2, 6),
            "enableFuzzyQuery": "false",
        },
    )
    if not resp:
        return []
    try:
        rows = resp.json().get("news") or []
    except ValueError:
        return []

    candidates: list[tuple[dict, list[str], str]] = []
    for row in rows:
        related = [str(item).upper() for item in (row.get("relatedTickers") or [])]
        if related and symbol not in related:
            continue
        original_title = str(row.get("title") or "").strip()
        if not original_title:
            continue
        candidates.append((row, related, original_title))
        if len(candidates) >= limit:
            break

    translated_titles = _translate_news_titles(
        [candidate[2] for candidate in candidates]
    )
    result: list[dict] = []
    for (row, related, original_title), title in zip(
        candidates, translated_titles
    ):
        if not title:
            continue
        published = row.get("providerPublishTime")
        try:
            published_text = _dt.datetime.fromtimestamp(int(published)).strftime("%m-%d %H:%M")
        except (TypeError, ValueError, OSError):
            published_text = ""
        publisher = str(row.get("publisher") or "Yahoo Finance")
        direct = len(related) == 1 or symbol in original_title.upper()
        result.append(
            {
                "title": title,
                "original_title": original_title,
                "publisher": _PUBLISHER_ZH.get(publisher, publisher),
                "published_at": published_text,
                "url": str(row.get("link") or ""),
                "impact_label": "直接相关" if direct else "行业关联",
            }
        )
    _NEWS_CACHE[symbol] = (_dt.datetime.now(), result)
    return result


def _search_us_stocks(query: str) -> list[dict]:
    query = str(query or "").strip()[:50]
    if not query:
        return []
    resp = _safe_get(
        "https://query2.finance.yahoo.com/v1/finance/search",
        headers=_YAHOO_HEADERS,
        params={
            "q": query,
            "quotesCount": 12,
            "newsCount": 0,
            "enableFuzzyQuery": "true",
        },
    )
    if not resp:
        return []
    try:
        quotes = resp.json().get("quotes") or []
    except ValueError:
        return []

    results: list[dict] = []
    seen: set[str] = set()
    allowed_types = {"EQUITY"}
    allowed_exchanges = {"NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "PNK"}
    for row in quotes:
        symbol = _normalize_us_symbol(row.get("symbol") or "")
        quote_type = str(row.get("quoteType") or "").upper()
        exchange = str(row.get("exchange") or "").upper()
        if (
            not symbol
            or symbol in seen
            or quote_type not in allowed_types
            or (exchange and exchange not in allowed_exchanges)
        ):
            continue
        seen.add(symbol)
        results.append(
            {
                "symbol": symbol,
                "name": str(
                    row.get("longname")
                    or row.get("shortname")
                    or row.get("longName")
                    or row.get("shortName")
                    or symbol
                ),
                "exchange": exchange,
                "type": "美股",
            }
        )
        if len(results) >= 8:
            break
    return results


def _build_portfolio_stock(symbol: str) -> dict:
    quote = _fetch_yahoo_quote(symbol)
    news = _fetch_yahoo_news(symbol)
    if quote:
        quote["news"] = news
        return quote
    return {
        "symbol": symbol,
        "name": symbol,
        "price": None,
        "preclose": None,
        "change_pct": None,
        "currency": "USD",
        "exchange": "",
        "source": "unavailable",
        "news": news,
    }


def _fetch_crypto_ticker(symbol: str) -> dict | None:
    """币安 USDT 永续 24h 行情。symbol 示例：BTCUSDT、SOLUSDT。"""
    url = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol}"
    resp = _safe_get(url)
    if not resp:
        return None
    try:
        d = resp.json()
        return {
            "symbol": symbol,
            "name": "Bitcoin" if symbol == "BTCUSDT" else "Solana",
            "price": float(d["lastPrice"]),
            "change_pct_24h": float(d["priceChangePercent"]),
            "high_24h": float(d["highPrice"]),
            "low_24h": float(d["lowPrice"]),
            "quote_volume_24h": round(float(d["quoteVolume"]) / 1e8, 2),  # 折算为「亿U」
        }
    except (ValueError, KeyError, TypeError):
        return None


def _crypto_assets() -> list[dict]:
    """统一输出 BTC / SOL；每项独立降级并标明来源。"""
    assets = []
    for symbol in ("BTCUSDT", "SOLUSDT"):
        ticker = _fetch_crypto_ticker(symbol)
        if ticker and ticker.get("price") is not None:
            ticker["source"] = "live"
        else:
            ticker = dict(FALLBACK_CRYPTO[symbol])
            ticker["source"] = "placeholder"
        assets.append(ticker)
    return assets


def _fetch_fear_greed() -> dict:
    """加密市场恐慌贪婪指数；不可用时返回可识别的降级状态。"""
    resp = _safe_get("https://api.alternative.me/fng/?limit=1&format=json")
    if not resp:
        return {**FALLBACK_FEAR_GREED, "source": "placeholder"}
    try:
        item = (resp.json().get("data") or [])[0]
        return {
            "value": int(item["value"]),
            "classification": str(item.get("value_classification", "Unknown")),
            "updated_at": _dt.datetime.fromtimestamp(int(item["timestamp"])).strftime("%Y-%m-%d %H:%M:%S"),
            "source": "live",
        }
    except (ValueError, KeyError, IndexError, TypeError, OSError):
        return {**FALLBACK_FEAR_GREED, "source": "placeholder"}


@app.get("/api/stocks/search")
def search_stocks(q: str = "") -> dict[str, Any]:
    """搜索可加入自选的美国上市股票。"""
    return {
        "status": "success",
        "query": str(q or "").strip(),
        "items": _search_us_stocks(q),
    }


@app.get("/api/portfolio")
def portfolio(symbols: str = "") -> dict[str, Any]:
    """按用户自选代码返回美股行情和每只股票的最新关联新闻。"""
    requested: list[str] = []
    seen: set[str] = set()
    raw_symbols = symbols.split(",") if symbols else [item[0] for item in US_STOCKS]
    for raw in raw_symbols:
        symbol = _normalize_us_symbol(raw)
        if symbol and symbol not in seen:
            seen.add(symbol)
            requested.append(symbol)
        if len(requested) >= 20:
            break

    if requested:
        workers = min(8, len(requested))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            stocks = list(pool.map(_build_portfolio_stock, requested))
    else:
        stocks = []
    return {
        "category": "美股持仓监控",
        "updated_at": _now(),
        "us_stocks": stocks,
    }


@app.get("/api/market")
def market() -> dict[str, Any]:
    """市场总览：BTC/SOL 行情与恐慌贪婪指数，供首页和告警引擎使用。"""
    fear_greed = _fetch_fear_greed()
    value = fear_greed["value"]
    risk_level = "极度恐慌" if value <= 25 else "恐慌" if value <= 45 else "中性" if value <= 55 else "贪婪" if value <= 75 else "极度贪婪"
    return {
        "category": "全球市场情绪",
        "updated_at": _now(),
        "crypto_assets": _crypto_assets(),
        "fear_greed": fear_greed,
        "risk_level": risk_level,
    }


# ---------------------------------------------------------------------------
# 3. 资讯聚合接口
# ---------------------------------------------------------------------------
import httpx

# 假设未来 Docker 里的 newsnow 运行在本地 3000 端口
NEWSNOW_API_URL = "http://127.0.0.1:3000/api/news"

@app.get("/api/news")
async def get_all_news():
    try:
        # 使用 httpx 去白嫖本地 Docker 抓好的全量新鲜数据 (设置 2 秒超时，防止卡死)
        async with httpx.AsyncClient() as client:
            response = await client.get(NEWSNOW_API_URL, timeout=2.0)
            
        if response.status_code == 200:
            raw_data = response.json()
            # 完美承接 newsnow 返回的各大源数据
            return {
                "status": "success",
                "sources": raw_data.get("sources", {}), 
                "updated_at": raw_data.get("updatedAt", "刚刚")
            }
    except Exception as e:
        print(f"Docker newsnow 服务未启动或连接失败，已自动切入硬核兜底模式")
        
    # 【完美兜底机制】当你本地没跑 Docker 时，绝对不白屏，依然展示硬核演示数据
    return {
        "status": "fallback",
        "updated_at": "演示模式",
        "sources": {
            "华尔街见闻": [
                {"title": "美联储偏爱的通胀指标超预期降温，降息大门正式敞开", "time": "2分钟前", "url": ""},
                {"title": "英伟达盘前大涨 4%，分析师集体调高目标价至新高", "time": "15分钟前", "url": ""}
            ],
            "36氪": [
                {"title": "大模型独角兽完成新一轮巨额融资，估值突破百亿美金", "time": "5分钟前", "url": ""},
                {"title": "消费电子巨头入局自动驾驶，首款极客网格新车谍照曝光", "time": "1小时前", "url": ""}
            ],
            "财联社": [
                {"title": "A股半天成交额破万亿，机器人ETF、核心资产全线爆发", "time": "刚刚", "url": ""},
                {"title": "多部门联合发文：加大对数字经济与自动化工具的政策红利", "time": "30分钟前", "url": ""}
            ],
            "AIHOT": [
                {"title": "OpenAI 秘密项目曝光：具备完全自主流式推理的智能 Agent 军团", "time": "10分钟前", "url": ""},
                {"title": "GitHub 开源自动化 RPA 框架爆火，一键托管全平台评论管理", "time": "45分钟前", "url": ""}
            ],
            "IT之家": [
                {"title": "极客掌上调试终端发布：内置定制 Ubuntu 核心，续航长达一整天", "time": "12分钟前", "url": ""},
                {"title": "最新指纹浏览器内核升级：重构 WebRTC 防穿透伪装隔离机制", "time": "3小时前", "url": ""}
            ]
        }
    }


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "小程序数据引擎",
        "version": "0.1.0",
        "endpoints": [
            "/api/arbitrage",
            "/api/arbitrage/history/{code}",
            "/api/research/overview",
            "/api/research/search?q=",
            "/api/research/asset?quote_code=",
            "/api/research/dossier?quote_code=",
            "/api/research/notes",
            "/api/research/tasks",
            "/api/portfolio",
            "/api/stocks/search",
            "/api/market",
            "/api/news",
        ],
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": _now()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
