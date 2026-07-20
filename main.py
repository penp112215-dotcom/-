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
from typing import Any

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# 全局配置
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = 6  # 单源请求超时（秒），抓不到就降级


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0",
}

# 机器人相关 ETF 清单：(名称, 新浪代码, 基金代码)
ROBOT_ETFS = [
    ("机器人ETF", "sh562500", "562500"),
    ("机器人ETF易方达", "sz159770", "159770"),
    ("机器人产业ETF", "sz159551", "159551"),
]

# 美股监控标的
US_STOCKS = [
    ("MSFT", "105.MSFT", "微软"),
    ("CEG", "105.CEG", "星座能源"),
    ("NVDA", "105.NVDA", "英伟达"),
]

# ---------------------------------------------------------------------------
# 兜底 / 占位数据：所有外部源失败/超时时使用，绝不返回 null
# 数值为贴近真实行情的模拟值，仅保证结构可用，source 标注 "placeholder"
# ---------------------------------------------------------------------------
FALLBACK_ETF = {
    "562500": {"name": "机器人ETF华夏", "price": 1.150, "preclose": 1.140, "open": 1.142, "high": 1.158, "low": 1.138, "iopv": 1.1480, "iopv_time": "", "premium_rate": 0.17},
    "159770": {"name": "机器人ETF易方达", "price": 1.190, "preclose": 1.180, "open": 1.182, "high": 1.198, "low": 1.178, "iopv": 1.1876, "iopv_time": "", "premium_rate": 0.20},
    "159551": {"name": "机器人产业ETF", "price": 1.490, "preclose": 1.475, "open": 1.478, "high": 1.498, "low": 1.472, "iopv": 1.4882, "iopv_time": "", "premium_rate": 0.12},
}

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
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, **kw)
        if resp.status_code == 200:
            return resp
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 1. A股 ETF 套利接口
# ---------------------------------------------------------------------------
def _fetch_sina_quote(codes: list[str]) -> dict[str, dict]:
    """新浪行情：返回 {code: {name, price, preclose, open, high, low}}"""
    url = "http://hq.sinajs.cn/list=" + ",".join(codes)
    resp = _safe_get(url, headers=SINA_HEADERS)
    out: dict[str, dict] = {}
    if not resp:
        return out
    for line in resp.text.strip().split("\n"):
        # var hq_str_sh562500="机器人ETF,昨收,今开,最新,最高,最低,...";
        if "=" not in line:
            continue
        head, body = line.split("=", 1)
        code = head.split("_")[-1].strip()
        body = body.strip().strip('"').rstrip(";").strip('"')
        if not body:
            continue
        f = body.split(",")
        try:
            out[code] = {
                "name": f[0],
                "open": float(f[1]),
                "preclose": float(f[2]),
                "price": float(f[3]),
                "high": float(f[4]),
                "low": float(f[5]),
            }
        except (IndexError, ValueError):
            continue
    return out


def _fetch_fund_iopv(fund_code: str) -> dict | None:
    """天天基金实时估值：返回 {gsz: 参考净值, gszzl: 估算涨跌幅, gztime}"""
    url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
    resp = _safe_get(url, headers=SINA_HEADERS)
    if not resp:
        return None
    txt = resp.text.strip()
    # jsonpgz({...});
    start, end = txt.find("{"), txt.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        import json

        data = json.loads(txt[start : end + 1])
        return {
            "iopv": float(data.get("gsz", 0)) or None,
            "estimate_change_pct": float(data.get("gszzl", 0)),
            "iopv_time": data.get("gztime", ""),
        }
    except (ValueError, TypeError):
        return None


@app.get("/api/arbitrage")
def arbitrage() -> dict[str, Any]:
    """A股机器人相关 ETF 盘中报价 + IOPV + 折溢价率"""
    sina_codes = [c for _, c, _ in ROBOT_ETFS]
    try:
        quotes = _fetch_sina_quote(sina_codes)
    except Exception:
        quotes = {}

    items = []
    for name, sina_code, fund_code in ROBOT_ETFS:
        try:
            q = quotes.get(sina_code)
            iopv = _fetch_fund_iopv(fund_code)
        except Exception:
            q, iopv = None, None

        if q and q.get("price") and q["price"] > 0 and iopv and iopv.get("iopv"):
            price = q["price"]
            preclose = q.get("preclose") or 0
            iopv_val = iopv["iopv"]
            premium_rate = (price - iopv_val) / iopv_val * 100
            change_pct = (price - preclose) / preclose * 100 if preclose else 0.0
            source = "live"
            item = {
                "code": fund_code,
                "name": q.get("name", name),
                "price": price,
                "preclose": preclose,
                "open": q.get("open"),
                "high": q.get("high"),
                "low": q.get("low"),
                "change_pct": round(change_pct, 4),
                "iopv": iopv_val,
                "iopv_time": iopv.get("iopv_time", ""),
                "premium_rate": round(premium_rate, 4),
                "source": source,
            }
        else:
            # 降级：使用兜底数据，绝不返回 null
            fb = FALLBACK_ETF.get(fund_code, {})
            price = fb.get("price", 0)
            preclose = fb.get("preclose", 0)
            change_pct = (price - preclose) / preclose * 100 if preclose else 0.0
            item = {
                "code": fund_code,
                "name": fb.get("name", name),
                "price": price,
                "preclose": preclose,
                "open": fb.get("open"),
                "high": fb.get("high"),
                "low": fb.get("low"),
                "change_pct": round(change_pct, 4),
                "iopv": fb.get("iopv"),
                "iopv_time": fb.get("iopv_time", ""),
                "premium_rate": fb.get("premium_rate"),
                "source": "placeholder",
            }
        items.append(item)

    return {
        "category": "A股ETF套利",
        "updated_at": _now(),
        "items": items,
    }


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


@app.get("/api/portfolio")
def portfolio() -> dict[str, Any]:
    """核心资产监控：美股最新价/涨跌幅 + SOL 永续合约 24h 波动"""
    stocks = []
    for symbol, secid, cn_name in US_STOCKS:
        try:
            s = _fetch_us_stock(secid)
        except Exception:
            s = None
        if s and s.get("price") is not None:
            s.update({"symbol": symbol, "cn_name": cn_name, "source": "live"})
        else:
            # 降级：使用兜底数据，绝不返回 null
            fb = FALLBACK_US.get(symbol, {})
            s = {
                "symbol": symbol,
                "cn_name": cn_name,
                "name": fb.get("name", cn_name),
                "price": fb.get("price"),
                "preclose": fb.get("preclose"),
                "change_pct": fb.get("change_pct"),
                "source": "placeholder",
            }
        stocks.append(s)

    crypto_assets = _crypto_assets()
    # 向后兼容旧版前端：保留 crypto_perp 作为 SOL 的别名。
    perp = next(asset for asset in crypto_assets if asset["symbol"] == "SOLUSDT")

    return {
        "category": "核心资产监控",
        "updated_at": _now(),
        "us_stocks": stocks,
        "crypto_perp": perp,
        "crypto_assets": crypto_assets,
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
from fastapi import HTTPException

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
            "/api/portfolio",
            "/api/news",
        ],
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": _now()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
