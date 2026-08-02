"""轻量市场情绪引擎：A股客观指标 + 公开讨论反向情绪。"""

from __future__ import annotations

import datetime as dt
import html
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import median
from typing import Any

import requests


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Referer": "https://finance.sina.com.cn/",
}
SINA_MARKET_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
SINA_KLINE_URL = "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_kline=/CN_MarketDataService.getKLineData"
GUBA_BOARDS = (
    ("nasdaq", "纳斯达克", "of159941"),
    ("gold", "黄金", "of518880"),
    ("cpo", "CPO通信", "of515880"),
    ("semiconductor", "半导体", "of512480"),
)
BUY_WORDS = ("上车", "冲", "梭哈", "满仓", "抄底", "加仓", "买入", "补仓", "还能买吗", "想买", "起飞", "暴涨")
SELL_WORDS = ("割肉", "止损", "清仓", "减仓", "卖了", "跑了", "亏麻", "套牢", "跌惨", "崩盘", "要不要走")
NEWBIE_WORDS = ("小白", "新手", "不懂", "请教", "怎么办", "该不该", "要不要", "能不能", "靠谱吗", "听说", "朋友说", "救命", "好慌", "稳赚", "必涨")
PRO_WORDS = ("PE", "PB", "ROE", "估值", "基本面", "财报", "仓位", "对冲", "资产配置", "风险")

_cache: tuple[float, dict[str, Any]] | None = None
_cache_lock = threading.Lock()


def _session_json(url: str, params: dict[str, Any] | None = None, timeout: int = 15) -> Any:
    for trust_env in (False, True):
        session = requests.Session()
        session.trust_env = trust_env
        try:
            response = session.get(url, params=params, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            continue
    return None


def _session_text(url: str, timeout: int = 15) -> str:
    for trust_env in (False, True):
        session = requests.Session()
        session.trust_env = trust_env
        try:
            response = session.get(url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            return response.text
        except requests.RequestException:
            continue
    return ""


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if number == number else None
    except (TypeError, ValueError):
        return None


def _normalize(value: float, minimum: float, maximum: float) -> float:
    if maximum <= minimum:
        return 50.0
    return max(0.0, min(100.0, (value - minimum) / (maximum - minimum) * 100))


def _fetch_market_page(page: int) -> list[dict[str, Any]]:
    payload = _session_json(
        SINA_MARKET_URL,
        {
            "page": page,
            "num": 100,
            "sort": "amount",
            "asc": 0,
            "node": "hs_a",
            "symbol": "",
            "_s_r_a": "page",
        },
        timeout=18,
    )
    return payload if isinstance(payload, list) else []


def fetch_active_market_sample(pages: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(5, pages)) as executor:
        futures = [executor.submit(_fetch_market_page, page) for page in range(1, pages + 1)]
        for future in as_completed(futures):
            try:
                rows.extend(future.result())
            except Exception:
                continue
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "")
        if symbol:
            unique[symbol] = row
    return list(unique.values())


def fetch_index_history(days: int = 40) -> list[dict[str, Any]]:
    text = _session_text(
        SINA_KLINE_URL
        + "?symbol=sh000001&scale=240&ma=no&datalen="
        + str(max(20, min(days, 120))),
        timeout=18,
    )
    match = re.search(r"=\((\[.*\])\)\s*;?", text, re.S)
    if not match:
        return []
    try:
        import json

        payload = json.loads(match.group(1))
    except (ValueError, TypeError):
        return []
    return payload if isinstance(payload, list) else []


def calculate_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    window = changes[-period:]
    gains = sum(max(change, 0) for change in window) / period
    losses = sum(max(-change, 0) for change in window) / period
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    return round(100 - 100 / (1 + gains / losses), 1)


def calculate_a_share_sentiment(
    rows: list[dict[str, Any]], history: list[dict[str, Any]]
) -> dict[str, Any]:
    changes = [value for row in rows if (value := _number(row.get("changepercent"))) is not None]
    advances = sum(value > 0 for value in changes)
    declines = sum(value < 0 for value in changes)
    flat = len(changes) - advances - declines
    breadth_score = round(advances / max(advances + declines, 1) * 100, 1)
    limit_up = sum(value >= 9.8 for value in changes)
    limit_down = sum(value <= -9.8 for value in changes)
    limit_score = round(limit_up / max(limit_up + limit_down, 1) * 100, 1) if limit_up + limit_down else 50.0
    active_median = round(median(changes), 2) if changes else 0.0
    momentum_score = round(_normalize(active_median, -3.0, 3.0), 1)

    closes = [value for row in history if (value := _number(row.get("close"))) is not None]
    volumes = [value for row in history if (value := _number(row.get("volume"))) is not None]
    rsi = calculate_rsi(closes)
    volume_ratio = None
    if len(volumes) >= 6:
        baseline = sum(volumes[-21:-1]) / max(len(volumes[-21:-1]), 1)
        if baseline > 0:
            volume_ratio = round(volumes[-1] / baseline, 2)
    volume_score = round(_normalize(volume_ratio or 1.0, 0.6, 1.8), 1)

    components = [breadth_score, limit_score, rsi if rsi is not None else 50.0, volume_score, momentum_score]
    score = round(sum(components) / len(components), 1) if rows else None
    label = sentiment_label(score)
    return {
        "available": bool(rows),
        "score": score,
        "label": label,
        "summary": sentiment_summary(score, breadth_score, active_median),
        "sample_size": len(changes),
        "method": "成交额前500只活跃A股样本；五项等权合成",
        "components": [
            {"key": "breadth", "name": "上涨广度", "value": breadth_score, "display": f"{advances}涨 / {declines}跌", "note": f"平盘 {flat}"},
            {"key": "limit", "name": "涨跌停强度", "value": limit_score, "display": f"{limit_up}涨停 / {limit_down}跌停", "note": "活跃样本近似统计"},
            {"key": "rsi", "name": "上证 RSI(14)", "value": rsi, "display": f"{rsi:.1f}" if rsi is not None else "--", "note": "日线动量"},
            {"key": "volume", "name": "量能偏离", "value": volume_score, "display": f"{volume_ratio:.2f}倍" if volume_ratio is not None else "--", "note": "相对20日均量"},
            {"key": "momentum", "name": "活跃股中位涨幅", "value": momentum_score, "display": f"{active_median:+.2f}%", "note": "降低极端个股干扰"},
        ],
        "source_name": "新浪财经公开行情",
        "source_url": "https://finance.sina.com.cn/stock/",
    }


def sentiment_label(score: float | None) -> str:
    if score is None:
        return "数据不足"
    if score < 20:
        return "极度低迷"
    if score < 40:
        return "偏冷"
    if score < 60:
        return "中性"
    if score < 80:
        return "偏热"
    return "极度亢奋"


def sentiment_summary(score: float | None, breadth: float, median_change: float) -> str:
    if score is None:
        return "客观数据不足，暂不生成情绪结论。"
    direction = "多数活跃个股上涨" if breadth >= 55 else "多数活跃个股下跌" if breadth <= 45 else "涨跌分布接近平衡"
    return f"{direction}，活跃样本中位涨幅 {median_change:+.2f}%。指数仅描述当下状态，不代表后续方向。"


def _extract_titles(board_code: str) -> list[str]:
    text = _session_text(f"https://guba.eastmoney.com/list,{board_code}.html", timeout=18)
    titles = [html.unescape(title).strip() for title in re.findall(r'<a[^>]+title="([^"]+)"', text, re.I)]
    return list(dict.fromkeys(title for title in titles if 4 <= len(title) <= 100))[:100]


def _analyze_titles(key: str, name: str, code: str, titles: list[str]) -> dict[str, Any]:
    scores: list[float] = []
    buy_posts = 0
    sell_posts = 0
    newbie_posts = 0
    for title in titles:
        lowered = title.lower()
        newbie_hits = sum(word.lower() in lowered for word in NEWBIE_WORDS)
        pro_hits = sum(word.lower() in lowered for word in PRO_WORDS)
        buy_hits = sum(word.lower() in lowered for word in BUY_WORDS)
        sell_hits = sum(word.lower() in lowered for word in SELL_WORDS)
        score = max(0.0, min(100.0, 10 + newbie_hits * 18 + (buy_hits + sell_hits) * 8 - pro_hits * 10))
        scores.append(score)
        newbie_posts += score >= 28
        buy_posts += buy_hits > sell_hits
        sell_posts += sell_hits > buy_hits
    total = len(titles)
    newbie_ratio = newbie_posts / max(total, 1) * 100
    avg_score = sum(scores) / max(len(scores), 1)
    extreme_ratio = (buy_posts + sell_posts) / max(total, 1) * 100
    activity = min(100.0, total / 80 * 100)
    index = round(newbie_ratio * 0.4 + avg_score * 0.25 + extreme_ratio * 0.2 + activity * 0.15, 1) if total else None
    buy_index = round(buy_posts / max(total, 1) * 100, 1)
    sell_index = round(sell_posts / max(total, 1) * 100, 1)
    return {
        "key": key,
        "name": name,
        "index": index,
        "label": retail_label(index),
        "buy": buy_index,
        "sell": sell_index,
        "sample_size": total,
        "source_url": f"https://guba.eastmoney.com/list,{code}.html",
    }


def retail_label(score: float | None) -> str:
    if score is None:
        return "无数据"
    if score < 20:
        return "冷清"
    if score < 40:
        return "正常"
    if score < 60:
        return "升温"
    if score < 75:
        return "警惕"
    return "狂热"


def fetch_retail_sentiment() -> dict[str, Any]:
    sectors: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        jobs = {
            executor.submit(_extract_titles, code): (key, name, code)
            for key, name, code in GUBA_BOARDS
        }
        for future in as_completed(jobs):
            key, name, code = jobs[future]
            try:
                sectors.append(_analyze_titles(key, name, code, future.result()))
            except Exception:
                sectors.append(_analyze_titles(key, name, code, []))
    order = {item[0]: index for index, item in enumerate(GUBA_BOARDS)}
    sectors.sort(key=lambda item: order[item["key"]])
    available = [item for item in sectors if item["index"] is not None]
    overall = round(sum(item["index"] for item in available) / len(available), 1) if available else None
    buy = round(sum(item["buy"] for item in available) / len(available), 1) if available else None
    sell = round(sum(item["sell"] for item in available) / len(available), 1) if available else None
    return {
        "available": bool(available),
        "index": overall,
        "label": retail_label(overall),
        "buy": buy,
        "sell": sell,
        "sample_size": sum(item["sample_size"] for item in sectors),
        "sectors": sectors,
        "method": "公开讨论标题关键词规则；仅作反向情绪辅助观察",
        "source_name": "东方财富股吧公开页面",
    }


def get_market_sentiment(force: bool = False) -> dict[str, Any]:
    global _cache
    if not force:
        with _cache_lock:
            if _cache and time.time() - _cache[0] < 300:
                return _cache[1]
    with ThreadPoolExecutor(max_workers=3) as executor:
        market_future = executor.submit(fetch_active_market_sample)
        history_future = executor.submit(fetch_index_history)
        retail_future = executor.submit(fetch_retail_sentiment)
        rows = market_future.result()
        history = history_future.result()
        retail = retail_future.result()
    market = calculate_a_share_sentiment(rows, history)
    result = {
        "status": "success" if market["available"] else "partial",
        "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "a_share": market,
        "retail": retail,
    }
    with _cache_lock:
        _cache = (time.time(), result)
    return result
