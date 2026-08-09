"""每日前沿资讯聚合：科技、AI、政治三个独立频道。"""

from __future__ import annotations

import datetime as dt
import email.utils
import html
import re
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import requests


HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PersonalNewsReader/1.0)"}


def _google_url(query: str) -> str:
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"}
    )


@dataclass(frozen=True)
class FeedSource:
    channel: str
    name: str
    url: str
    tier: str = "secondary"


FEEDS = (
    FeedSource("technology", "Apple Newsroom", "https://www.apple.com/newsroom/rss-feed.rss", "first_party"),
    FeedSource("technology", "Microsoft 官方博客", "https://blogs.microsoft.com/feed/", "first_party"),
    FeedSource("technology", "NVIDIA Newsroom", "https://nvidianews.nvidia.com/rss.xml", "first_party"),
    FeedSource("technology", "36氪", "https://36kr.com/feed"),
    FeedSource("technology", "IT之家", "https://www.ithome.com/rss/"),
    FeedSource("technology", "Solidot", "https://www.solidot.org/index.rss"),
    FeedSource("technology", "科技新闻聚合", _google_url("科技 OR 半导体 OR 芯片 OR 机器人")),
    FeedSource("ai", "36氪 AI筛选", "https://36kr.com/feed"),
    FeedSource("ai", "IT之家 AI筛选", "https://www.ithome.com/rss/"),
    FeedSource("ai", "AI中文新闻聚合", _google_url("大模型 OR OpenAI OR Anthropic OR DeepMind OR 生成式AI OR AI智能体")),
    FeedSource("ai", "OpenAI 官方", "https://openai.com/news/rss.xml", "first_party"),
    FeedSource("ai", "Google DeepMind", "https://deepmind.google/blog/rss.xml", "first_party"),
    FeedSource("ai", "Google AI 官方", "https://blog.google/technology/ai/rss/", "first_party"),
    FeedSource("ai", "NVIDIA Newsroom AI筛选", "https://nvidianews.nvidia.com/rss.xml", "first_party"),
    FeedSource("politics", "政治新闻聚合", _google_url("国际政治 OR 外交 OR 地缘政治 OR 国际关系")),
    FeedSource("politics", "BBC 中文", "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"),
    FeedSource("politics", "联合国新闻", "https://news.un.org/feed/subscribe/en/news/all/rss.xml", "first_party"),
    FeedSource("politics", "美国国务院", "https://www.state.gov/rss-feed/press-releases/feed/", "first_party"),
    FeedSource("politics", "欧盟新闻发布", "https://ec.europa.eu/commission/presscorner/api/rss?language=en", "first_party"),
    FeedSource("politics", "中国新闻网国际", "https://www.chinanews.com.cn/rss/world.xml"),
    FeedSource("politics", "人民网国际", "http://www.people.com.cn/rss/world.xml"),
)

# 移动端首屏优先使用大陆网络可快速访问的来源。Google News、OpenAI、
# DeepMind 和 BBC 等跨境 RSS 在国内 VPS 上常触发长时间 DNS/连接等待，
# 后续可由定时后台任务补充，不能阻塞 CloudBase 的同步请求。
FAST_FEEDS = tuple(
    feed
    for feed in FEEDS
    if feed.name
    in {
        "36氪",
        "IT之家",
        "Solidot",
        "36氪 AI筛选",
        "IT之家 AI筛选",
        "中国新闻网国际",
        "人民网国际",
    }
)

# 所有跨境源并行、短超时抓取；任意一个慢源最多拖延约 4 秒，而不是逐个累加。
# 这样冷启动也能尝试一手来源，失败时仍由 FAST_FEEDS 中的国内源补位。
REQUEST_FEEDS = FEEDS

CHANNELS = (
    {"key": "technology", "name": "科技", "description": "芯片、硬件、互联网与前沿产品"},
    {"key": "ai", "name": "AI", "description": "模型、研究、产品与产业动态"},
    {"key": "politics", "name": "政治", "description": "国际政治、外交与地缘事件"},
)

_cache: tuple[float, dict[str, Any]] | None = None
_cache_lock = threading.Lock()
_translation_cache: dict[str, str] = {}


def _fetch_bytes(url: str) -> bytes:
    # CloudBase 网关不适合等待多个慢源。每个源只尝试一次，连接和读取分别限时；
    # 失败源由其他 RSS 补位，成功结果缓存 5 分钟。
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(url, headers=HEADERS, timeout=(2, 4))
        response.raise_for_status()
        if b"<rss" in response.content[:1000].lower() or b"<feed" in response.content[:1000].lower():
            return response.content
    except requests.RequestException:
        pass
    return b""


def _text(element: ET.Element | None, name: str) -> str:
    if element is None:
        return ""
    direct = element.find(name)
    if direct is not None and direct.text:
        return direct.text.strip()
    for child in element:
        if child.tag.rsplit("}", 1)[-1] == name and child.text:
            return child.text.strip()
    return ""


def _clean_html(value: str, limit: int = 220) -> str:
    clean = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:limit] + ("…" if len(clean) > limit else "")


def _timestamp(value: str) -> int:
    if not value:
        return 0
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return int(parsed.timestamp())
    except (TypeError, ValueError, OverflowError):
        try:
            return int(dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
        except (ValueError, OverflowError):
            return 0


def _source_from_item(item: ET.Element, fallback: str) -> str:
    source = _text(item, "source")
    return source or fallback


def parse_feed(content: bytes, feed: FeedSource) -> list[dict[str, Any]]:
    if not content:
        return []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    entries = root.findall(".//item")
    if not entries:
        entries = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "entry"]
    results = []
    for entry in entries[:30]:
        title = _clean_html(_text(entry, "title"), 160)
        link = _text(entry, "link")
        if not link:
            for child in entry:
                if child.tag.rsplit("}", 1)[-1] == "link" and child.attrib.get("href"):
                    link = child.attrib["href"]
                    break
        published_raw = _text(entry, "pubDate") or _text(entry, "published") or _text(entry, "updated")
        summary = _text(entry, "description") or _text(entry, "summary") or _text(entry, "content")
        if not title or not link:
            continue
        results.append(
            {
                "channel": feed.channel,
                "title": title,
                "summary": _clean_html(summary),
                "url": link.strip(),
                "source": _source_from_item(entry, feed.name),
                "feed_name": feed.name,
                "source_tier": feed.tier,
                "published_at": published_raw,
                "timestamp": _timestamp(published_raw),
            }
        )
    return results


def _fetch_feed(feed: FeedSource) -> tuple[FeedSource, list[dict[str, Any]]]:
    return feed, parse_feed(_fetch_bytes(feed.url), feed)


def _dedupe_key(title: str) -> str:
    normalized = re.sub(r"\s+-\s+[^-]{1,40}$", "", title)
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", normalized).lower()[:90]


def _is_relevant(channel: str, title: str) -> bool:
    lowered = title.lower()
    if channel == "ai":
        keywords = ("ai", "人工智能", "大模型", "模型", "openai", "chatgpt", "deepmind", "anthropic", "英伟达", "智能体", "agent")
        noise = ("ppt", "青少年", "培训班", "招生", "考试", "大赛决赛", "概念股涨停")
        return any(word in lowered for word in keywords) and not any(word in lowered for word in noise)
    if channel == "politics":
        noise = ("娱乐", "电视剧", "综艺", "体育比赛")
        return not any(word in lowered for word in noise)
    return True


def _time_text(timestamp: int) -> str:
    if not timestamp:
        return "时间未知"
    now = int(time.time())
    seconds = max(0, now - timestamp)
    if seconds < 3600:
        return f"{max(1, seconds // 60)}分钟前"
    if seconds < 86400:
        return f"{seconds // 3600}小时前"
    local = dt.datetime.fromtimestamp(timestamp)
    if seconds < 172800:
        return "昨天 " + local.strftime("%H:%M")
    return local.strftime("%m-%d %H:%M")


def _has_chinese(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value or ""))


def _translate_titles(items: list[dict[str, Any]]) -> None:
    """批量把一手英文标题译成中文；翻译失败时保留原文，绝不伪造摘要。"""
    for item in items:
        item["translation_status"] = (
            "original_zh" if _has_chinese(str(item.get("title") or "")) else "untranslated"
        )
    pending = [
        item for item in items
        if item.get("title") and not _has_chinese(str(item["title"]))
    ]
    missing = list(dict.fromkeys(
        str(item["title"])
        for item in pending
        if str(item["title"]) not in _translation_cache
    ))

    def translate_batch(originals: list[str]) -> dict[str, str]:
        marker = "\n998877665544332211\n"
        translated_rows: dict[str, str] = {}
        try:
            response = requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={
                    "client": "gtx",
                    "sl": "auto",
                    "tl": "zh-CN",
                    "dt": "t",
                    "q": marker.join(originals),
                },
                headers=HEADERS,
                timeout=(2, 4),
            )
            translated_text = "".join(
                str(part[0] or "")
                for part in (response.json()[0] or [])
                if isinstance(part, list) and part
            )
            translated = [part.strip() for part in translated_text.split(marker.strip())]
            if len(translated) == len(originals):
                for original, value in zip(originals, translated):
                    if _has_chinese(value):
                        translated_rows[original] = value
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
            pass
        return translated_rows

    def translate_single_fallback(original: str) -> tuple[str, str]:
        """Google 不可达时使用 MyMemory 官方 REST API 翻译单条标题。"""
        try:
            response = requests.get(
                "https://api.mymemory.translated.net/get",
                params={"q": original[:480], "langpair": "en|zh-CN", "mt": 1},
                headers=HEADERS,
                timeout=(2, 5),
            )
            translated = str(
                (response.json().get("responseData") or {}).get("translatedText")
                or ""
            ).strip()
            if _has_chinese(translated):
                return original, translated
        except (requests.RequestException, ValueError, AttributeError, TypeError):
            pass
        return original, ""

    batches = [missing[start : start + 8] for start in range(0, len(missing), 8)]
    if batches:
        with ThreadPoolExecutor(max_workers=min(4, len(batches))) as executor:
            futures = [executor.submit(translate_batch, batch) for batch in batches]
            for future in as_completed(futures):
                _translation_cache.update(future.result())

    remaining = [title for title in missing if title not in _translation_cache]
    if remaining:
        with ThreadPoolExecutor(max_workers=min(6, len(remaining))) as executor:
            futures = [executor.submit(translate_single_fallback, title) for title in remaining]
            for future in as_completed(futures):
                original, translated = future.result()
                if translated:
                    _translation_cache[original] = translated

    for item in pending:
        original = str(item["title"])
        item["original_title"] = original
        translated = _translation_cache.get(original)
        if translated:
            item["title"] = translated
            item["translation_status"] = "translated"
    if len(_translation_cache) > 2000:
        _translation_cache.clear()


def fetch_daily_news(force: bool = False) -> dict[str, Any]:
    global _cache
    if not force:
        with _cache_lock:
            if _cache and time.time() - _cache[0] < 300:
                return _cache[1]

    collected: dict[str, list[dict[str, Any]]] = {item["key"]: [] for item in CHANNELS}
    source_status: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(16, len(REQUEST_FEEDS))) as executor:
        futures = [executor.submit(_fetch_feed, feed) for feed in REQUEST_FEEDS]
        for future in as_completed(futures):
            try:
                feed, items = future.result()
            except Exception:
                continue
            collected[feed.channel].extend(items)
            source_status.append({"name": feed.name, "channel": feed.channel, "available": bool(items), "count": len(items)})

    output: dict[str, list[dict[str, Any]]] = {}
    for channel in collected:
        seen: set[str] = set()
        source_counts: dict[str, int] = {}
        items = []
        for item in sorted(collected[channel], key=lambda row: row["timestamp"], reverse=True):
            key = _dedupe_key(item["title"])
            source = item["feed_name"]
            source_limit = 4 if channel == "technology" else 5 if channel == "ai" else 8
            if not key or key in seen or not _is_relevant(channel, item["title"]):
                continue
            if source_counts.get(source, 0) >= source_limit:
                continue
            seen.add(key)
            source_counts[source] = source_counts.get(source, 0) + 1
            item["time"] = _time_text(item["timestamp"])
            item["date"] = dt.datetime.fromtimestamp(item["timestamp"]).strftime("%Y-%m-%d") if item["timestamp"] else ""
            items.append(item)
            if len(items) >= 15:
                break
        output[channel] = items

    _translate_titles(
        [item for channel_items in output.values() for item in channel_items]
    )

    channel_rows = []
    for meta in CHANNELS:
        items = output[meta["key"]]
        channel_rows.append({**meta, "count": len(items), "items": items})
    total = sum(row["count"] for row in channel_rows)
    result = {
        "status": "success" if total else "partial",
        "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": dt.date.today().isoformat(),
        "channels": channel_rows,
        "source_status": source_status,
        "summary": f"今日已汇总 {total} 条前沿资讯，按发布时间排序并自动去重。",
        "disclaimer": "政治资讯保留原始来源，仅作信息索引；重要事实请交叉核验。",
    }
    with _cache_lock:
        _cache = (time.time(), result)
    return result
