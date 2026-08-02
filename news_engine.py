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


FEEDS = (
    FeedSource("technology", "36氪", "https://36kr.com/feed"),
    FeedSource("technology", "IT之家", "https://www.ithome.com/rss/"),
    FeedSource("technology", "Solidot", "https://www.solidot.org/index.rss"),
    FeedSource("technology", "科技新闻聚合", _google_url("科技 OR 半导体 OR 芯片 OR 机器人")),
    FeedSource("ai", "AI中文新闻聚合", _google_url("大模型 OR OpenAI OR Anthropic OR DeepMind OR 生成式AI OR AI智能体")),
    FeedSource("ai", "OpenAI 官方", "https://openai.com/news/rss.xml"),
    FeedSource("ai", "Google DeepMind", "https://deepmind.google/blog/rss.xml"),
    FeedSource("politics", "政治新闻聚合", _google_url("国际政治 OR 外交 OR 地缘政治 OR 国际关系")),
    FeedSource("politics", "BBC 中文", "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"),
)

CHANNELS = (
    {"key": "technology", "name": "科技", "description": "芯片、硬件、互联网与前沿产品"},
    {"key": "ai", "name": "AI", "description": "模型、研究、产品与产业动态"},
    {"key": "politics", "name": "政治", "description": "国际政治、外交与地缘事件"},
)

_cache: tuple[float, dict[str, Any]] | None = None
_cache_lock = threading.Lock()


def _fetch_bytes(url: str, timeout: int = 20) -> bytes:
    for trust_env in (False, True):
        session = requests.Session()
        session.trust_env = trust_env
        try:
            response = session.get(url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            if b"<rss" in response.content[:1000].lower() or b"<feed" in response.content[:1000].lower():
                return response.content
        except requests.RequestException:
            continue
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


def fetch_daily_news(force: bool = False) -> dict[str, Any]:
    global _cache
    if not force:
        with _cache_lock:
            if _cache and time.time() - _cache[0] < 300:
                return _cache[1]

    collected: dict[str, list[dict[str, Any]]] = {item["key"]: [] for item in CHANNELS}
    source_status: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(_fetch_feed, feed) for feed in FEEDS]
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
