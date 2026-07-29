"""LOF 套利监控引擎。

只使用公开行情与基金公开资料进行机会筛选，不接触券商账号、交易密码，
也不自动下单。任何缺少可靠申购状态或限额口径的数据都不会标记为
``executable``。
"""

from __future__ import annotations

import datetime as dt
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any

import requests


REQUEST_TIMEOUT = 8
EASTMONEY_HEADERS = {
    "Referer": "https://fund.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

# 用户确认的账户与费用配置。
INVESTOR_COUNT = 8
ON_EXCHANGE_CHANNELS_PER_INVESTOR = 6
OFF_EXCHANGE_CHANNELS_PER_INVESTOR = 1
CASH_PER_INVESTOR = 10_000.0
SELL_COMMISSION_RATE = 0.0001  # 万一免五
SUBSCRIPTION_FEE_DISCOUNT = 0.10  # 申购费一折
DEFAULT_SOURCE_SUBSCRIPTION_RATE = 0.012
DEFAULT_SLIPPAGE_RATE = 0.001

MAX_RESULT_ITEMS = 40
DETAIL_CANDIDATE_COUNT = 50


@dataclass(frozen=True)
class AccountCapacity:
    investors: int = INVESTOR_COUNT
    on_exchange_per_investor: int = ON_EXCHANGE_CHANNELS_PER_INVESTOR
    off_exchange_per_investor: int = OFF_EXCHANGE_CHANNELS_PER_INVESTOR
    cash_per_investor: float = CASH_PER_INVESTOR

    @property
    def total_channels(self) -> int:
        return self.investors * (
            self.on_exchange_per_investor + self.off_exchange_per_investor
        )

    @property
    def total_cash(self) -> float:
        return self.investors * self.cash_per_investor


ACCOUNT_CAPACITY = AccountCapacity()


_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str, ttl: int) -> Any | None:
    with _cache_lock:
        hit = _cache.get(key)
        if not hit:
            return None
        created_at, value = hit
        if time.time() - created_at > ttl:
            _cache.pop(key, None)
            return None
        return value


def _cache_set(key: str, value: Any) -> Any:
    with _cache_lock:
        _cache[key] = (time.time(), value)
    return value


def _safe_get_json(url: str, params: dict[str, Any] | None = None) -> dict | None:
    for attempt in range(2):
        try:
            response = requests.get(
                url,
                params=params,
                headers=EASTMONEY_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                return response.json()
        except (requests.RequestException, json.JSONDecodeError, ValueError):
            pass
        if attempt == 0:
            time.sleep(0.25)
    return None


def _safe_get_bytes(url: str, params: dict[str, Any] | None = None) -> bytes | None:
    for attempt in range(2):
        try:
            response = requests.get(
                url,
                params=params,
                headers=EASTMONEY_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code == 200 and response.content:
                return response.content
        except requests.RequestException:
            pass
        if attempt == 0:
            time.sleep(0.25)
    return None


def _to_float(value: Any) -> float | None:
    if value in (None, "", "--", "-"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_percent(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    text = str(value).strip().replace("%", "")
    number = _to_float(text)
    return None if number is None else number / 100


def _market_prefix(code: str) -> str:
    return "sh" if code.startswith("5") else "sz"


def _is_qdii(fund_type: str, name: str) -> bool:
    text = f"{fund_type} {name}".lower()
    terms = (
        "海外",
        "qdii",
        "纳斯达克",
        "标普",
        "德国",
        "日本",
        "印度",
        "越南",
        "恒生",
        "港股",
        "油气",
        "原油",
        "黄金",
        "白银",
    )
    return any(term in text for term in terms)


def _risk_buffer(fund_type: str, name: str, nav_is_estimate: bool) -> float:
    if _is_qdii(fund_type, name):
        return 0.025
    if not nav_is_estimate:
        return 0.012
    return 0.006


def _fetch_eastmoney_lof_quotes() -> list[dict]:
    results = []
    page = 1
    total = 1
    while len(results) < total and page <= 6:
        payload = _safe_get_json(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": page,
                "pz": 100,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f6",
                "fs": "b:MK0404",
                "fields": "f12,f14,f2,f3,f4,f5,f6,f15,f16,f17,f18,f124",
            },
        )
        data = (payload or {}).get("data") or {}
        total = int(data.get("total") or 0)
        rows = data.get("diff") or []
        if not rows:
            break
        for raw in rows:
            code = str(raw.get("f12") or "")
            price = _to_float(raw.get("f2"))
            if len(code) != 6 or price is None or price <= 0:
                continue
            results.append(
                {
                    "code": code,
                    "name": str(raw.get("f14") or code),
                    "market": _market_prefix(code),
                    "price": price,
                    "preclose": _to_float(raw.get("f18")),
                    "change_pct": _to_float(raw.get("f3")),
                    "amount": _to_float(raw.get("f6")) or 0.0,
                    "quote_time": raw.get("f124"),
                }
            )
        page += 1
    return results


def _fetch_lof_catalog_codes() -> list[str]:
    """从全量基金目录提取可能上市的沪深 LOF 代码。"""
    cached = _cache_get("lof:catalog-codes", ttl=21600)
    if cached is not None:
        return cached
    content = _safe_get_bytes("https://fund.eastmoney.com/js/fundcode_search.js")
    if not content:
        return []
    try:
        text = content.decode("utf-8-sig", errors="replace")
        start, end = text.find("["), text.rfind("]")
        rows = json.loads(text[start : end + 1])
    except (ValueError, json.JSONDecodeError):
        return []
    # 深市 LOF 主要使用 16xxxx，沪市 LOF 主要使用 50xxxx。
    codes = sorted(
        {
            str(row[0])
            for row in rows
            if isinstance(row, list)
            and row
            and len(str(row[0])) == 6
            and str(row[0]).startswith(("16", "50"))
        }
    )
    return _cache_set("lof:catalog-codes", codes)


def _fetch_sina_lof_quotes() -> list[dict]:
    codes = _fetch_lof_catalog_codes()
    if not codes:
        return []
    results: list[dict] = []
    headers = {
        "Referer": "https://finance.sina.com.cn",
        "User-Agent": EASTMONEY_HEADERS["User-Agent"],
    }
    for start in range(0, len(codes), 80):
        batch = codes[start : start + 80]
        symbols = [
            ("sh" if code.startswith("5") else "sz") + code for code in batch
        ]
        try:
            response = requests.get(
                "https://hq.sinajs.cn/list=" + ",".join(symbols),
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                continue
            text = response.content.decode("gb18030", errors="ignore")
        except requests.RequestException:
            continue

        for line in text.splitlines():
            if "=" not in line:
                continue
            head, body = line.split("=", 1)
            symbol = head.rsplit("_", 1)[-1]
            code = symbol[-6:]
            fields = body.strip().rstrip(";").strip('"').split(",")
            if len(fields) < 10 or not fields[0]:
                continue
            price = _to_float(fields[3])
            if price is None or price <= 0:
                continue
            results.append(
                {
                    "code": code,
                    "name": fields[0],
                    "market": symbol[:2],
                    "price": price,
                    "preclose": _to_float(fields[2]),
                    "change_pct": (
                        (price / float(fields[2]) - 1) * 100
                        if _to_float(fields[2])
                        else 0.0
                    ),
                    "amount": _to_float(fields[9]) or 0.0,
                    "bid1": _to_float(fields[11]) if len(fields) > 11 else None,
                    "ask1": _to_float(fields[21]) if len(fields) > 21 else None,
                    "quote_time": (
                        f"{fields[30]} {fields[31]}" if len(fields) > 31 else ""
                    ),
                }
            )
    return results


def fetch_lof_quotes() -> list[dict]:
    """获取沪深 LOF 快照；主源失败时自动切换基金目录 + 新浪盘口。"""
    quotes = _fetch_eastmoney_lof_quotes()
    if len(quotes) >= 150:
        return quotes
    fallback = _fetch_sina_lof_quotes()
    return fallback if len(fallback) > len(quotes) else quotes


def fetch_fund_nav_batch(codes: list[str]) -> dict[str, dict]:
    """批量获取最新官方净值与盘中估值；每批最多 200 只。"""
    if not codes:
        return {}
    result: dict[str, dict] = {}
    for start in range(0, len(codes), 180):
        batch = codes[start : start + 180]
        payload = _safe_get_json(
            "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNFInfo",
            params={
                "pageIndex": 1,
                "pageSize": len(batch),
                "appType": "ttjj",
                "product": "EFund",
                "plat": "Android",
                "deviceid": "miniapp-arbitrage-monitor",
                "Version": 1,
                "Fcodes": ",".join(batch),
            },
        )
        for raw in (payload or {}).get("Datas") or []:
            code = str(raw.get("FCODE") or "")
            if not code:
                continue
            estimate = _to_float(raw.get("GSZ"))
            official_nav = _to_float(raw.get("NAV"))
            result[code] = {
                "name": str(raw.get("SHORTNAME") or code),
                "official_nav": official_nav,
                "nav_date": str(raw.get("PDATE") or ""),
                "estimated_nav": estimate,
                "estimate_time": str(raw.get("GZTIME") or ""),
            }
    return result


def fetch_fund_basic(code: str) -> dict:
    cache_key = f"basic:{code}"
    cached = _cache_get(cache_key, ttl=1800)
    if cached is not None:
        return cached
    payload = _safe_get_json(
        "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNNBasicInformation",
        params={
            "FCODE": code,
            "deviceid": "miniapp-arbitrage-monitor",
            "plat": "Android",
            "product": "EFund",
            "version": "6.3.8",
        },
    )
    raw = (payload or {}).get("Datas") or {}
    data = {
        "fund_type": str(raw.get("FTYPE") or "LOF"),
        "subscription_status": str(raw.get("SGZT") or "未知"),
        "redemption_status": str(raw.get("SHZT") or "未知"),
        "source_rate": _parse_percent(raw.get("SOURCERATE")),
        "display_rate": _parse_percent(raw.get("RATE")),
        "min_subscription": _to_float(raw.get("MINSG")),
        "max_subscription": _to_float(raw.get("MAXSG")),
        "exchange": str(raw.get("LISTTEXCHMARK") or ""),
        "is_listed": str(raw.get("ISLISTTRADE") or "") == "1",
    }
    return _cache_set(cache_key, data)


def _fetch_candidate_details(codes: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_fund_basic, code): code for code in codes}
        for future in as_completed(futures):
            code = futures[future]
            try:
                result[code] = future.result()
            except Exception:
                result[code] = {}
    return result


def _limit_scope_and_capacity(
    max_subscription: float | None,
    subscription_status: str,
) -> dict[str, Any]:
    """公开接口未给出公告限额口径时，按“每名投资者”保守计算。"""
    open_for_subscription = "开放" in subscription_status or "限额" in subscription_status
    if not open_for_subscription:
        return {
            "limit_scope": "暂停或未知",
            "per_investor_limit": 0.0,
            "total_capacity": 0.0,
            "eligible_channels": 0,
            "limit_confirmed": False,
        }

    if max_subscription is None or max_subscription <= 0:
        per_investor = ACCOUNT_CAPACITY.cash_per_investor
        limit_scope = "未披露，按资金上限"
    else:
        per_investor = min(max_subscription, ACCOUNT_CAPACITY.cash_per_investor)
        limit_scope = "公开平台参考，按单个投资者保守计算"

    return {
        "limit_scope": limit_scope,
        "per_investor_limit": round(per_investor, 2),
        "total_capacity": round(
            min(
                per_investor * ACCOUNT_CAPACITY.investors,
                ACCOUNT_CAPACITY.total_cash,
            ),
            2,
        ),
        "eligible_channels": ACCOUNT_CAPACITY.total_channels,
        # 正式执行前仍需用基金公告或银河证券页面确认。
        "limit_confirmed": False,
    }


def _assess_item(quote: dict, nav: dict, basic: dict) -> dict | None:
    if basic.get("is_listed") is False:
        return None
    official_nav = _to_float(nav.get("official_nav"))
    estimated_nav = _to_float(nav.get("estimated_nav"))
    reference_nav = estimated_nav or official_nav
    if reference_nav is None or reference_nav <= 0:
        return None

    price = float(quote["price"])
    exit_price = _to_float(quote.get("bid1")) or price
    gross_premium = exit_price / reference_nav - 1
    name = str(quote.get("name") or nav.get("name") or quote["code"])
    fund_type = str(basic.get("fund_type") or "LOF")
    nav_is_estimate = estimated_nav is not None

    source_rate = basic.get("source_rate")
    subscription_fee_rate = (
        source_rate * SUBSCRIPTION_FEE_DISCOUNT
        if source_rate is not None
        else DEFAULT_SOURCE_SUBSCRIPTION_RATE * SUBSCRIPTION_FEE_DISCOUNT
    )
    safety_buffer = _risk_buffer(fund_type, name, nav_is_estimate)
    net_edge = (
        gross_premium
        - subscription_fee_rate
        - SELL_COMMISSION_RATE
        - DEFAULT_SLIPPAGE_RATE
        - safety_buffer
    )

    capacity = _limit_scope_and_capacity(
        basic.get("max_subscription"),
        str(basic.get("subscription_status") or "未知"),
    )
    published_capacity = float(capacity["total_capacity"])
    turnover = float(quote.get("amount") or 0.0)
    # 单个策略计划量不超过当日场内成交额的 5%，避免“有价差、卖不掉”。
    liquidity_capacity = max(0.0, turnover * 0.05)
    total_capacity = round(min(published_capacity, liquidity_capacity), 2)
    suggested_per_investor = round(
        min(
            float(capacity["per_investor_limit"]),
            total_capacity / ACCOUNT_CAPACITY.investors,
        ),
        2,
    )
    subscription_open = published_capacity > 0
    expected_profit = max(0.0, total_capacity * net_edge)

    nav_label = "盘中估值" if nav_is_estimate else "最新官方净值"
    data_confidence = "medium" if nav_is_estimate else "low"
    if _is_qdii(fund_type, name) and not nav_is_estimate:
        data_confidence = "low"

    if not subscription_open:
        signal = "closed"
        signal_text = "暂停申购"
    elif net_edge <= 0:
        signal = "none"
        signal_text = "无净空间"
    elif not capacity["limit_confirmed"]:
        signal = "verify"
        signal_text = "需核实限额"
    elif data_confidence == "low":
        signal = "watch"
        signal_text = "估值待校准"
    else:
        signal = "opportunity"
        signal_text = "可执行"

    return {
        "code": quote["code"],
        "name": name,
        "market": quote["market"],
        "fund_type": fund_type,
        "price": round(price, 4),
        "exit_price": round(exit_price, 4),
        "pricing_basis": "买一价" if quote.get("bid1") else "最新价",
        "change_pct": round(float(quote.get("change_pct") or 0.0), 4),
        "amount": round(float(quote.get("amount") or 0.0), 2),
        "reference_nav": round(reference_nav, 6),
        "nav_label": nav_label,
        "nav_date": nav.get("estimate_time") or nav.get("nav_date") or "",
        "gross_premium_pct": round(gross_premium * 100, 3),
        "subscription_fee_pct": round(subscription_fee_rate * 100, 3),
        "sell_fee_pct": round(SELL_COMMISSION_RATE * 100, 3),
        "slippage_pct": round(DEFAULT_SLIPPAGE_RATE * 100, 3),
        "safety_buffer_pct": round(safety_buffer * 100, 3),
        "net_edge_pct": round(net_edge * 100, 3),
        "subscription_status": str(basic.get("subscription_status") or "未知"),
        "redemption_status": str(basic.get("redemption_status") or "未知"),
        "published_per_investor_limit": capacity["per_investor_limit"],
        "per_investor_limit": suggested_per_investor,
        "published_total_capacity": published_capacity,
        "liquidity_capacity": round(liquidity_capacity, 2),
        "total_capacity": total_capacity,
        "eligible_channels": capacity["eligible_channels"],
        "limit_scope": capacity["limit_scope"],
        "limit_confirmed": capacity["limit_confirmed"],
        "expected_profit": round(expected_profit, 2),
        "data_confidence": data_confidence,
        "signal": signal,
        "signal_text": signal_text,
        "source": "public-live",
    }


def build_arbitrage_snapshot() -> dict[str, Any]:
    started = time.time()
    quotes = fetch_lof_quotes()
    if not quotes:
        stale_snapshot = _cache_get("snapshot:last-success", ttl=1800)
        if stale_snapshot:
            return {
                **stale_snapshot,
                "status": "stale",
                "message": "实时行情暂不可用，当前显示最近一次成功快照",
                "stale": True,
            }
        return {
            "category": "A股基金套利",
            "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "unavailable",
            "message": "公开行情暂不可用，未输出模拟套利机会",
            "account": asdict(ACCOUNT_CAPACITY)
            | {
                "total_channels": ACCOUNT_CAPACITY.total_channels,
                "total_cash": ACCOUNT_CAPACITY.total_cash,
            },
            "summary": {
                "market_total": 0,
                "analyzed": 0,
                "opportunities": 0,
                "watching": 0,
            },
            "items": [],
        }

    nav_map = fetch_fund_nav_batch([item["code"] for item in quotes])
    rough_candidates = []
    for quote in quotes:
        nav = nav_map.get(quote["code"]) or {}
        reference_nav = _to_float(nav.get("estimated_nav")) or _to_float(
            nav.get("official_nav")
        )
        if not reference_nav:
            continue
        rough_premium = quote["price"] / reference_nav - 1
        rough_candidates.append((rough_premium, quote))

    rough_candidates.sort(
        key=lambda row: (row[0], float(row[1].get("amount") or 0.0)),
        reverse=True,
    )
    detail_quotes = [row[1] for row in rough_candidates[:DETAIL_CANDIDATE_COUNT]]
    details = _fetch_candidate_details([item["code"] for item in detail_quotes])

    items = []
    for quote in detail_quotes:
        item = _assess_item(
            quote,
            nav_map.get(quote["code"]) or {},
            details.get(quote["code"]) or {},
        )
        if item is not None:
            items.append(item)

    signal_priority = {
        "opportunity": 5,
        "verify": 4,
        "watch": 3,
        "none": 2,
        "closed": 1,
    }
    items.sort(
        key=lambda item: (
            signal_priority.get(item["signal"], 0),
            item["net_edge_pct"],
            item["amount"],
        ),
        reverse=True,
    )
    items = items[:MAX_RESULT_ITEMS]

    snapshot = {
        "category": "A股基金套利",
        "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "success",
        "message": "公开数据仅作筛选；执行前请以基金公告及银河证券申购页为准",
        "account": asdict(ACCOUNT_CAPACITY)
        | {
            "total_channels": ACCOUNT_CAPACITY.total_channels,
            "total_cash": ACCOUNT_CAPACITY.total_cash,
            "subscription_fee_discount": SUBSCRIPTION_FEE_DISCOUNT,
            "sell_commission_rate": SELL_COMMISSION_RATE,
        },
        "summary": {
            "market_total": len(quotes),
            "analyzed": len(detail_quotes),
            "opportunities": sum(
                item["signal"] == "opportunity" for item in items
            ),
            "need_verification": sum(item["signal"] == "verify" for item in items),
            "watching": sum(item["signal"] == "watch" for item in items),
            "elapsed_ms": round((time.time() - started) * 1000),
        },
        "items": items,
    }
    _cache_set("snapshot:last-success", snapshot)
    return snapshot
