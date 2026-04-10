from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import difflib
import html
import json
import logging
import os
import sqlite3
import ssl
import textwrap
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib import error, parse, request

import feedparser

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import certifi
except ImportError:
    certifi = None

try:
    from google.cloud import bigquery
except ImportError:
    bigquery = None


DEFAULT_KEYWORDS = [
    "總統",
    "副總統",
    "立委",
    "立法院",
    "國會",
    "選舉",
    "罷免",
    "補選",
    "民調",
    "聲量",
    "輿情",
    "支持度",
    "滿意度",
    "政黨",
    "民進黨",
    "國民黨",
    "民眾黨",
    "時代力量",
    "基進",
    "新黨",
    "親民黨",
    "賴清德",
    "蕭美琴",
    "侯友宜",
    "趙少康",
    "柯文哲",
    "黃國昌",
    "朱立倫",
    "蔣萬安",
    "盧秀燕",
    "陳其邁",
    "韓國瑜",
    "國安",
    "兩岸",
    "外交",
    "內閣",
    "政策",
    "造勢",
    "提名",
    "初選",
    "爭議",
    "弊案",
    "失言",
    "檢調",
    "起訴",
    "預算",
    "法案",
]

DEFAULT_PRIORITY_KEYWORDS = [
    "總統",
    "選舉",
    "罷免",
    "民調",
    "聲量",
    "國安",
    "兩岸",
    "外交",
    "起訴",
    "檢調",
    "法案",
    "總預算",
]

DEFAULT_ENTITY_HINTS = {
    "民進黨": [
        "民進黨",
        "賴清德", "蕭美琴", "卓榮泰", "柯建銘",
        "吳思瑤", "王世堅", "吳沛憶", "林淑芬", "李坤城", "吳秉叡", "蘇巧慧", "張宏陸", "吳琪銘",
        "蔡其昌", "何欣純", "何志偉", "郭國文", "陳亭妃", "林宜瑾", "林俊憲", "王定宇",
        "邱議瑩", "邱志偉", "李柏毅", "林岱樺", "李昆澤", "黃捷", "許智傑", "賴瑞隆",
        "王美惠", "陳秀寳", "黃秀芳", "陳素月", "劉建國", "蔡易餘", "陳冠廷", "鍾佳濱",
        "徐富癸", "陳俊宇", "楊曜", "林月琴", "沈伯洋", "范雲", "林楚茵", "郭昱晴",
        "陳培瑜", "莊瑞雄", "沈發惠", "羅美玲", "陳瑩", "伍麗華", "伍麗華Saidhai",
        "黃偉哲", "陳其邁", "翁章梁", "周春米", "陳光復",
        "林世宗", "林延鳳", "陳賢蔚", "陳慈慧", "鍾佩玲",
        "王孝維", "何孟樺", "李建昌",
        "許淑華", "洪健益", "陳聖文", "張文潔",
        "陳怡君", "林亮君", "劉耀仁",
        "王閔生", "簡舒培", "蔡英文"
    ],
    "國民黨": ["國民黨", "侯友宜", "朱立倫", "蔣萬安", "盧秀燕", "韓國瑜"],
    "民眾黨": ["民眾黨", "柯文哲", "黃國昌", "吳欣盈"],
    "中央政府": ["行政院", "內閣", "部會", "卓榮泰"],
}

DEFAULT_TOPIC_HINTS = {
    "民調聲量": ["民調", "聲量", "支持度", "滿意度", "好感度", "反感度"],
    "選戰攻防": ["選舉", "罷免", "補選", "造勢", "提名", "初選", "輔選"],
    "國會攻防": ["立院", "立法院", "國會", "表決", "法案", "總預算", "朝野"],
    "兩岸外交": ["兩岸", "中國", "美國", "外交", "國安", "軍演"],
    "政策輿情": ["政策", "能源", "健保", "勞工", "房價", "居住正義", "國防"],
    "爭議事件": ["爭議", "質疑", "弊案", "失言", "起訴", "檢調", "搜索"],
}

DEFAULT_POSITIVE_HINTS = ["宣布", "支持", "主打", "推出", "領先", "看好", "回升"]
DEFAULT_NEGATIVE_HINTS = ["質疑", "爭議", "弊案", "失言", "起訴", "檢調", "下滑", "暴跌"]

DEFAULT_ALLOWED_SOURCE_NAMES = [
    "Google News 台灣政治",
    "Google News 輿情聲量",
    "Google News 爭議觀測",
    "中央社政治",
    "中央社兩岸",
    "自由時報政治",
    "自由時報軍武",
]

DEFAULT_ALLOWED_PUBLISHERS = [
    "中央社",
    "中央社 CNA",
    "自由時報",
    "風傳媒",
    "三立新聞網",
    "Newtalk新聞",
    "聯合新聞網",
    "TVBS新聞網",
    "ETtoday新聞雲",
    "NOWnews今日新聞",
    "Yahoo新聞",
    "公視新聞網PNN",
    "鏡新聞",
    "上報",
]

DEFAULT_AGGREGATOR_DOMAINS = [
    "news.google.com",
    "tw.news.yahoo.com",
    "ynews.page.link",
]

DEFAULT_ALLOWED_SOURCE_DOMAINS = [
    "news.google.com",
    "tw.news.yahoo.com",
    "ynews.page.link",
    "www.cna.com.tw",
    "www.cna.com.tw",
    "news.ltn.com.tw",
    "www.storm.mg",
    "www.setn.com",
    "www.nownews.com",
    "newtalk.tw",
    "news.tvbs.com.tw",
    "www.ettoday.net",
    "udn.com",
    "www.cw.com.tw",
    "www.upmedia.mg",
]

DEFAULT_RSS_FEEDS = [
    {
        "name": "Google News 台灣政治",
        "url": "https://news.google.com/rss/search?q=%E5%8F%B0%E7%81%A3%E6%94%BF%E6%B2%BB+OR+%E9%81%B8%E8%88%89+OR+%E7%AB%8B%E6%B3%95%E9%99%A2+OR+%E7%B8%BD%E7%B5%B1+OR+%E6%94%BF%E9%BB%A8&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "kind": "politics",
    },
    {
        "name": "Google News 輿情聲量",
        "url": "https://news.google.com/rss/search?q=%E8%BC%BF%E6%83%85+OR+%E8%81%B2%E9%87%8F+OR+%E6%B0%91%E8%AA%BF+OR+%E6%BB%BF%E6%84%8F%E5%BA%A6+OR+%E6%94%AF%E6%8C%81%E5%BA%A6&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "kind": "opinion",
    },
    {
        "name": "Google News 爭議觀測",
        "url": "https://news.google.com/rss/search?q=%E7%88%AD%E8%AD%B0+OR+%E5%BC%8A%E6%A1%88+OR+%E5%A4%B1%E8%A8%80+OR+%E8%B3%AA%E7%96%91+OR+%E6%AA%A2%E8%AA%BF&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "kind": "controversy",
    },
    {
        "name": "中央社政治",
        "url": "https://feeds.feedburner.com/rsscna/politics",
        "kind": "politics",
    },
    {
        "name": "中央社兩岸",
        "url": "https://feeds.feedburner.com/rsscna/mainland",
        "kind": "security",
    },
    {
        "name": "自由時報政治",
        "url": "https://news.ltn.com.tw/rss/politics.xml",
        "kind": "politics",
    },
    {
        "name": "自由時報軍武",
        "url": "https://news.ltn.com.tw/rss/def.xml",
        "kind": "security",
    },
]

NOISE_PATTERNS = [
    "yahoo新聞",
    "yahoo",
    "facebookcom",
    "facebook",
    "ettoday新聞雲",
    "鏡週刊mirrormedia",
    "聯合新聞網",
    "遠見雜誌",
    "linetoday",
    "line today",
]

SSL_CONTEXT: ssl.SSLContext | None = None


def load_dotenv(env_path: str | None = None) -> None:
    path = Path(env_path) if env_path else Path(__file__).resolve().with_name(".env")
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and (key not in os.environ or not os.environ.get(key)):
            os.environ[key] = value


load_dotenv()


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def env_csv(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_json_dict(name: str, default: dict[str, list[str]]) -> dict[str, list[str]]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return default

    parsed: dict[str, list[str]] = {}
    if not isinstance(payload, dict):
        return default
    for key, value in payload.items():
        if isinstance(key, str) and isinstance(value, list):
            parsed[key] = [str(item).strip() for item in value if str(item).strip()]
    return parsed or default


DB_PATH = os.getenv("POLITICAL_INTEL_DB", os.getenv("OPINION_INTEL_DB", "political_intel.db"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DAILY_COMMENTARY_MODEL = os.getenv("DAILY_COMMENTARY_MODEL", "gpt-5.4-mini")
MONITOR_NAME = os.getenv("MONITOR_NAME", "台灣輿情監控")
MAX_ITEMS_PER_RUN = env_int("MAX_ITEMS_PER_RUN", 10)
ENABLE_TELEGRAM = env_bool("ENABLE_TELEGRAM", True)
DAILY_REPORT_LIMIT = env_int("DAILY_REPORT_LIMIT", 12)
HTTP_TIMEOUT = env_int("HTTP_TIMEOUT", 20)
SSL_VERIFY = env_bool("SSL_VERIFY", True)
SSL_CA_BUNDLE = os.getenv("SSL_CA_BUNDLE", "")
DEDUPE_HOURS = env_int("DEDUPE_HOURS", 24)
TELEGRAM_PREVIEW = env_bool("TELEGRAM_PREVIEW", True)
MAX_FEED_WORKERS = env_int("MAX_FEED_WORKERS", 4)
RECENT_NEWS_HOURS = env_float("RECENT_NEWS_HOURS", 1.5)
MIN_PUSH_IMPORTANCE = float(os.getenv("MIN_PUSH_IMPORTANCE", "6.5"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_PATH = Path(os.getenv("NEWS_MONITOR_LOG", str(Path(__file__).resolve().with_name("news_monitor.log"))))
BIGQUERY_PROJECT_ID = os.getenv("BIGQUERY_PROJECT_ID", "").strip()
BIGQUERY_DATASET = os.getenv("BIGQUERY_DATASET", "").strip()
BIGQUERY_TABLE = os.getenv("BIGQUERY_TABLE", "").strip()
USER_AGENT = os.getenv(
    "NEWS_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)
KEYWORDS = env_csv("MONITOR_KEYWORDS", DEFAULT_KEYWORDS)
ALLOWED_SOURCE_NAMES = env_csv("ALLOWED_SOURCE_NAMES", DEFAULT_ALLOWED_SOURCE_NAMES)
ALLOWED_PUBLISHERS = env_csv("ALLOWED_PUBLISHERS", DEFAULT_ALLOWED_PUBLISHERS)
AGGREGATOR_DOMAINS = env_csv("AGGREGATOR_DOMAINS", DEFAULT_AGGREGATOR_DOMAINS)
ALLOWED_SOURCE_DOMAINS = env_csv("ALLOWED_SOURCE_DOMAINS", DEFAULT_ALLOWED_SOURCE_DOMAINS)
PRIORITY_KEYWORDS = env_csv("PRIORITY_KEYWORDS", DEFAULT_PRIORITY_KEYWORDS)
POSITIVE_HINTS = env_csv("POSITIVE_HINTS", DEFAULT_POSITIVE_HINTS)
NEGATIVE_HINTS = env_csv("NEGATIVE_HINTS", DEFAULT_NEGATIVE_HINTS)
ENTITY_HINTS = env_json_dict("ENTITY_HINTS_JSON", DEFAULT_ENTITY_HINTS)
TOPIC_HINTS = env_json_dict("TOPIC_HINTS_JSON", DEFAULT_TOPIC_HINTS)
RSS_FEEDS = DEFAULT_RSS_FEEDS


def setup_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("news_monitor")
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    logger.handlers.clear()

    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False

    for noisy_logger in ("httpx", "httpcore", "openai"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    return logger


logger = setup_logging()


def get_openai_client() -> Any:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        logger.warning("OpenAI client unavailable; fallback analysis will be used.")
        return None
    return OpenAI(api_key=api_key)


def get_bigquery_client() -> Any:
    if not (BIGQUERY_PROJECT_ID and BIGQUERY_DATASET and BIGQUERY_TABLE):
        return None
    if bigquery is None:
        logger.warning("BigQuery env is configured but google-cloud-bigquery is not installed.")
        return None
    try:
        return bigquery.Client(project=BIGQUERY_PROJECT_ID)
    except Exception:
        logger.exception("Failed to initialize BigQuery client.")
        return None


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row[1] for row in rows}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        conn.commit()


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dedupe_key TEXT UNIQUE,
            source_name TEXT NOT NULL,
            title TEXT NOT NULL,
            link TEXT NOT NULL,
            published_at TEXT,
            summary TEXT,
            category TEXT,
            topic TEXT,
            entities TEXT,
            importance REAL,
            angle TEXT,
            raw_analysis TEXT,
            impact_analysis TEXT,
            action_suggest TEXT,
            sent_to_telegram INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    ensure_column(conn, "articles", "matched_keywords", "TEXT")
    ensure_column(conn, "articles", "source_kind", "TEXT")
    ensure_column(conn, "articles", "impact_analysis", "TEXT")
    ensure_column(conn, "articles", "action_suggest", "TEXT")
    return conn


def normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def normalize_title_for_event(title: str) -> str:
    cleaned = title.lower()
    cleaned = cleaned.split(" - ")[0]
    for old, new in {
        "「": "",
        "」": "",
        "『": "",
        "』": "",
        "【": "",
        "】": "",
        "（": "",
        "）": "",
        "(": "",
        ")": "",
        "，": "",
        "。": "",
        "！": "",
        "!": "",
        "?": "",
        "？": "",
        "：": "",
        ":": "",
        "、": "",
        "　": "",
        " ": "",
        "“": "",
        "”": "",
        '"': "",
        "'": "",
        ".": "",
        ",": "",
    }.items():
        cleaned = cleaned.replace(old, new)

    for pattern in NOISE_PATTERNS:
        cleaned = cleaned.replace(pattern, "")

    return cleaned.strip()


def build_dedupe_key(title: str, link: str) -> str:
    return f"{normalize_text(title)}::{normalize_text(link)}"


def build_runtime_dedupe_key(title: str, link: str) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    return f"{build_dedupe_key(title, link)}::{timestamp}"


def keyword_matches(text: str) -> list[str]:
    return [keyword for keyword in KEYWORDS if keyword in text]


def keyword_score(text: str) -> int:
    matches = keyword_matches(text)
    priority_bonus = sum(1 for keyword in matches if keyword in PRIORITY_KEYWORDS)
    return len(matches) + priority_bonus


def infer_entities(text: str) -> list[str]:
    matches = []
    for label, hints in ENTITY_HINTS.items():
        if any(hint in text for hint in hints):
            matches.append(label)
    return matches or ["未明確對象"]


def infer_topic(text: str) -> str:
    best_topic = "一般輿情"
    best_score = 0
    for topic, hints in TOPIC_HINTS.items():
        score = sum(1 for hint in hints if hint in text)
        if score > best_score:
            best_score = score
            best_topic = topic
    return best_topic


def infer_category(text: str) -> str:
    if any(word in text for word in ["民調", "聲量", "支持度", "滿意度", "好感度", "反感度"]):
        return "民調聲量"
    if any(word in text for word in ["選舉", "罷免", "補選", "初選", "提名", "造勢"]):
        return "選戰動態"
    if any(word in text for word in ["立法院", "立院", "國會", "法案", "預算"]):
        return "國會攻防"
    if any(word in text for word in ["外交", "兩岸", "國安", "中國", "美國"]):
        return "兩岸外交"
    if any(word in text for word in ["政策", "健保", "勞工", "國防", "能源", "房價"]):
        return "政策議題"
    if any(word in text for word in ["爭議", "弊案", "失言", "起訴", "檢調"]):
        return "爭議事件"
    return "一般輿情"


def infer_angle(text: str) -> str:
    if any(word in text for word in NEGATIVE_HINTS):
        return "負面"
    if any(word in text for word in POSITIVE_HINTS):
        return "正面"
    return "中性"


def fallback_analysis(title: str, matched_keywords: list[str]) -> dict[str, Any]:
    topic = infer_topic(title)
    entities = infer_entities(title)
    category = infer_category(title)
    angle = infer_angle(title)
    importance = min(9.8, 4.0 + keyword_score(title) * 0.55)
    keyword_text = "、".join(matched_keywords[:5]) if matched_keywords else "未命中關鍵字"
    summary = (
        f"這則消息偏向 {topic}，主要關注對象為 {', '.join(entities)}。"
        f" 目前歸類為 {category}，風向判定偏 {angle}。"
        f" 命中的觀測關鍵字有：{keyword_text}，建議持續追蹤後續聲量與各方回應。"
    )
    impact_analysis = f"短期內可能牽動{topic}相關攻防與聲量變化，建議持續追蹤後續回應。"
    action_suggest = f"優先監看{keyword_text}與主要對象後續表態。"
    return {
        "summary": summary,
        "category": category,
        "topic": topic,
        "entities": entities,
        "importance": round(importance, 1),
        "angle": angle,
        "impact_analysis": impact_analysis[:50],
        "action_suggest": action_suggest[:50],
        "matched_keywords": matched_keywords,
    }


def analyze_news(client: Any, title: str, matched_keywords: list[str]) -> dict[str, Any]:
    if client is None:
        return fallback_analysis(title, matched_keywords)

    prompt = textwrap.dedent(
        f"""
        你是台灣輿情監控分析師。請只根據標題做保守推論，不要虛構細節。
        請回傳 JSON，格式如下：
        {{
          "summary": "3句內摘要",
          "category": "民調聲量/選戰動態/國會攻防/兩岸外交/政策議題/爭議事件/一般輿情 其中一種或相近值",
          "topic": "最主要議題",
          "entities": ["人物、政黨或機構"],
          "importance": 1 到 10 的數字,
          "angle": "正面/負面/中性",
          "impact_analysis": "這則新聞對政治局勢可能造成的後續影響，限50字內",
          "action_suggest": "給幕僚或觀測者的下一步建議，限50字內"
        }}

        已命中關鍵字：{', '.join(matched_keywords) if matched_keywords else '無'}
        新聞標題：{title}
        """
    ).strip()

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "你負責台灣政治輿情監測，擅長分類、摘要、估算重要度、風向、後續影響與行動建議。",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.choices[0].message.content)
        payload["entities"] = payload.get("entities") or ["未標記"]
        payload["importance"] = float(payload.get("importance", 5))
        payload["angle"] = payload.get("angle") or infer_angle(title)
        payload["category"] = payload.get("category") or infer_category(title)
        payload["topic"] = payload.get("topic") or infer_topic(title)
        payload["impact_analysis"] = (payload.get("impact_analysis") or f"此事可能牽動{payload['topic']}後續攻防與聲量。")[:50]
        payload["action_suggest"] = (payload.get("action_suggest") or "建議持續觀察當事人回應與媒體延燒。")[:50]
        payload["matched_keywords"] = matched_keywords
        return payload
    except Exception:
        logger.exception("OpenAI analysis failed; using fallback analysis.")
        return fallback_analysis(title, matched_keywords)


def build_ssl_context() -> ssl.SSLContext:
    global SSL_CONTEXT
    if SSL_CONTEXT is not None:
        return SSL_CONTEXT
    if not SSL_VERIFY:
        SSL_CONTEXT = ssl._create_unverified_context()
        return SSL_CONTEXT
    if SSL_CA_BUNDLE:
        SSL_CONTEXT = ssl.create_default_context(cafile=SSL_CA_BUNDLE)
        return SSL_CONTEXT
    if certifi is not None:
        SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
        return SSL_CONTEXT
    SSL_CONTEXT = ssl.create_default_context()
    return SSL_CONTEXT


def parse_datetime_text(value: str) -> datetime | None:
    if not value:
        return None

    try:
        parsed_dt = datetime.fromisoformat(value)
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        return parsed_dt.astimezone(timezone.utc)
    except ValueError:
        pass

    try:
        parsed_dt = parsedate_to_datetime(value)
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        return parsed_dt.astimezone(timezone.utc)
    except Exception:
        return None


def sqlite_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def published_time_for_storage(raw_value: str) -> str:
    parsed_dt = parse_datetime_text(raw_value)
    if parsed_dt is None:
        return sqlite_utc_now()
    return parsed_dt.strftime("%Y-%m-%d %H:%M:%S")


def parse_entry_datetime(entry: Any) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                continue

    for attr in ("published", "updated"):
        raw_value = getattr(entry, attr, "")
        if not raw_value:
            continue
        parsed_dt = parse_datetime_text(raw_value)
        if parsed_dt is not None:
            return parsed_dt
    return None


def is_recent_entry(entry: Any, hours: float = RECENT_NEWS_HOURS) -> bool:
    published_dt = parse_entry_datetime(entry)
    if published_dt is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return published_dt >= cutoff


def extract_domain(link: str) -> str:
    try:
        return parse.urlparse(link).netloc.lower()
    except Exception:
        return ""


def extract_publisher(title: str) -> str:
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    if "｜" in title:
        return title.rsplit("｜", 1)[-1].strip()
    if "|" in title:
        return title.rsplit("|", 1)[-1].strip()
    return ""


def is_allowed_source(feed_name: str, link: str, title: str) -> bool:
    domain = extract_domain(link)
    publisher = extract_publisher(title)
    allowed_name = not ALLOWED_SOURCE_NAMES or feed_name in ALLOWED_SOURCE_NAMES
    allowed_domain = not ALLOWED_SOURCE_DOMAINS or any(
        domain == allowed or domain.endswith(f".{allowed}")
        for allowed in ALLOWED_SOURCE_DOMAINS
    )
    allowed_publisher = not ALLOWED_PUBLISHERS or any(
        publisher == allowed or publisher.endswith(allowed) or allowed in publisher
        for allowed in ALLOWED_PUBLISHERS
    )
    is_aggregator = any(
        domain == allowed or domain.endswith(f".{allowed}")
        for allowed in AGGREGATOR_DOMAINS
    )
    if is_aggregator:
        return allowed_name and allowed_publisher
    return allowed_name and allowed_domain


def load_feed(url: str) -> Any:
    req = request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        },
    )
    with request.urlopen(req, timeout=HTTP_TIMEOUT, context=build_ssl_context()) as resp:
        content = resp.read()
    return feedparser.parse(content)


def fetch_feed_items(feed_config: dict[str, str], recent_hours: int = RECENT_NEWS_HOURS) -> tuple[list[dict[str, Any]], str | None]:
    try:
        feed = load_feed(feed_config["url"])
    except Exception as exc:
        return [], f"[RSS 讀取失敗] {feed_config['name']} | {repr(exc)}"

    if getattr(feed, "bozo", 0) and not getattr(feed, "entries", []):
        return [], (
            f"[RSS 讀取失敗] {feed_config['name']} | "
            f"{repr(getattr(feed, 'bozo_exception', 'unknown error'))}"
        )

    items: list[dict[str, Any]] = []
    for entry in feed.entries:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        published_dt = parse_entry_datetime(entry)
        published = published_dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT") if published_dt else getattr(entry, "published", "")
        if not title or not link:
            continue
        if not is_recent_entry(entry, hours=recent_hours):
            logger.info(f"[舊聞略過] {feed_config['name']} | {title}")
            continue
        if not is_allowed_source(feed_config["name"], link, title):
            logger.info(
                f"[白名單略過] {feed_config['name']} | {title} | domain={extract_domain(link)} | publisher={extract_publisher(title)}"
            )
            continue

        matched = keyword_matches(title)
        if not matched:
            continue

        items.append(
            {
                "source_name": feed_config["name"],
                "source_kind": feed_config.get("kind", "general"),
                "title": title,
                "link": link,
                "published_at": published,
                "keyword_score": keyword_score(title),
                "matched_keywords": matched,
                "event_key": normalize_title_for_event(title),
            }
        )

    return items, None


def fetch_news(recent_hours: int = RECENT_NEWS_HOURS) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    failed_sources = 0
    worker_count = max(1, min(MAX_FEED_WORKERS, len(RSS_FEEDS)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(fetch_feed_items, feed, recent_hours) for feed in RSS_FEEDS]
        for future in as_completed(futures):
            feed_items, error_message = future.result()
            if error_message:
                failed_sources += 1
                logger.error(error_message)
                continue
            items.extend(feed_items)

    items.sort(key=lambda item: item["keyword_score"], reverse=True)
    deduped_items = []
    seen_links = set()
    seen_events = set()
    for item in items:
        normalized_link = normalize_text(item["link"])
        event_key = item["event_key"]
        if normalized_link in seen_links:
            continue
        if event_key and event_key in seen_events:
            continue
        seen_links.add(normalized_link)
        if event_key:
            seen_events.add(event_key)
        deduped_items.append(item)

    if failed_sources == len(RSS_FEEDS):
        logger.error("[診斷] 所有 RSS 來源都讀取失敗，這通常是網路、DNS、代理或防火牆問題。")
    return deduped_items[:MAX_ITEMS_PER_RUN]


def article_exists(conn: sqlite3.Connection, dedupe_key: str, hours: int = DEDUPE_HOURS) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM articles
        WHERE dedupe_key = ?
          AND created_at >= datetime('now', ?)
        LIMIT 1
        """,
        (dedupe_key, f"-{hours} hours"),
    ).fetchone()
    return row is not None


def load_recent_titles(conn: sqlite3.Connection, hours: int = DEDUPE_HOURS) -> list[str]:
    rows = conn.execute(
        """
        SELECT title
        FROM articles
        WHERE created_at >= datetime('now', ?)
        ORDER BY created_at DESC
        LIMIT 200
        """,
        (f"-{hours} hours",),
    ).fetchall()
    return [title for (title,) in rows]


def find_similar_title_in_memory(existing_titles: list[str], title: str) -> str | None:
    normalized_title = normalize_title_for_event(title)
    if not normalized_title:
        return None

    for existing_title in existing_titles:
        existing_normalized = normalize_title_for_event(existing_title)
        if not existing_normalized:
            continue
        ratio = difflib.SequenceMatcher(None, normalized_title, existing_normalized).ratio()
        shorter_len = min(len(normalized_title), len(existing_normalized))
        contains_match = (
            shorter_len >= 12
            and (
                normalized_title in existing_normalized
                or existing_normalized in normalized_title
            )
        )
        if ratio >= 0.72 or contains_match:
            return existing_title
    return None


def save_article(conn: sqlite3.Connection, item: dict[str, Any], analysis: dict[str, Any]) -> int:
    entities_json = json.dumps(analysis.get("entities", []), ensure_ascii=False)
    keywords_json = json.dumps(analysis.get("matched_keywords", item.get("matched_keywords", [])), ensure_ascii=False)
    cursor = conn.execute(
        """
        INSERT INTO articles (
            dedupe_key, source_name, title, link, published_at, summary, category,
            topic, entities, importance, angle, raw_analysis, impact_analysis,
            action_suggest, matched_keywords, source_kind, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["dedupe_key"],
            item["source_name"],
            item["title"],
            item["link"],
            item["published_at"],
            analysis.get("summary", ""),
            analysis.get("category", "一般輿情"),
            analysis.get("topic", "一般輿情"),
            entities_json,
            float(analysis.get("importance", 5)),
            analysis.get("angle", "中性"),
            json.dumps(analysis, ensure_ascii=False),
            analysis.get("impact_analysis", ""),
            analysis.get("action_suggest", ""),
            keywords_json,
            item.get("source_kind", "general"),
            published_time_for_storage(item.get("published_at", "")),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def upload_to_bigquery(item: dict[str, Any], analysis: dict[str, Any]) -> tuple[bool, str]:
    client = get_bigquery_client()
    if client is None:
        return False, "BigQuery 未設定或不可用"

    table_id = f"{BIGQUERY_PROJECT_ID}.{BIGQUERY_DATASET}.{BIGQUERY_TABLE}"
    row = {
        "source_name": item["source_name"],
        "source_kind": item.get("source_kind", "general"),
        "title": item["title"],
        "link": item["link"],
        "published_at": item.get("published_at") or "",
        "summary": analysis.get("summary", ""),
        "category": analysis.get("category", "一般輿情"),
        "topic": analysis.get("topic", "一般輿情"),
        "entities": analysis.get("entities", []),
        "importance": float(analysis.get("importance", 5)),
        "angle": analysis.get("angle", "中性"),
        "impact_analysis": analysis.get("impact_analysis", ""),
        "action_suggest": analysis.get("action_suggest", ""),
        "matched_keywords": analysis.get("matched_keywords", item.get("matched_keywords", [])),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        job_config = bigquery.LoadJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_APPEND)
        job = client.load_table_from_json([row], table_id, job_config=job_config)
        job.result()
    except Exception:
        logger.exception("BigQuery upload failed.")
        return False, "BigQuery upload exception"
    return True, "uploaded"


def send_telegram_message(message: str) -> tuple[bool, str]:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not ENABLE_TELEGRAM:
        return False, "Telegram 推送已關閉"
    if not bot_token or not chat_id:
        return False, "缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": "false" if TELEGRAM_PREVIEW else "true",
        }
    ).encode("utf-8")
    req = request.Request(url, data=payload, method="POST")
    try:
        with request.urlopen(req, timeout=20, context=build_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return bool(data.get("ok")), data.get("description", "sent")
    except error.URLError as exc:
        return False, f"Telegram 發送失敗: {exc}"


def mark_as_sent(conn: sqlite3.Connection, article_id: int) -> None:
    conn.execute("UPDATE articles SET sent_to_telegram = 1 WHERE id = ?", (article_id,))
    conn.commit()


def escape_html(value: str) -> str:
    return html.escape(str(value or ""), quote=False)


def importance_label(score: float) -> str:
    if score >= 8.5:
        return "高"
    if score >= 6.5:
        return "中"
    return "低"


def clean_headline(title: str, max_length: int = 34) -> str:
    headline = title.strip()
    for separator in (" - ", " | ", "｜"):
        if separator in headline:
            headline = headline.split(separator)[0].strip()
            break
    if len(headline) <= max_length:
        return headline
    return headline[: max_length - 1].rstrip() + "…"


def compact_list(values: list[str], limit: int = 2, fallback: str = "未標記") -> str:
    cleaned = [value.strip() for value in values if value and str(value).strip()]
    if not cleaned:
        return fallback
    return "、".join(cleaned[:limit])


def compact_count_summary(counts: dict[str, int], limit: int = 3, separator: str = "、") -> str:
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]
    if not ranked:
        return "無"
    return separator.join(f"{name}{count}" for name, count in ranked)


def limit_text(text: str, max_length: int) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"


def detect_parties(title: str, entities: list[str]) -> set[str]:
    lowered = title.lower()
    parties: set[str] = set()
    for party in ("國民黨", "民進黨"):
        if party in entities:
            parties.add(party)
            continue
        for alias in ENTITY_HINTS.get(party, []):
            if alias.lower() in lowered:
                parties.add(party)
                break
    return parties


def fallback_daily_commentary(recent_articles: list[sqlite3.Row]) -> tuple[str, str]:
    party_scores = {"國民黨": 0.0, "民進黨": 0.0}
    mention_counts = {"國民黨": 0, "民進黨": 0}
    angle_weights = {"正面": 1.0, "中性": 0.0, "負面": -1.0}

    for row in recent_articles:
        title = row["title"] or ""
        entities = json.loads(row["entities"]) if row["entities"] else []
        parties = detect_parties(title, entities)
        if not parties:
            continue

        weight = max(1.0, float(row["importance"] or 0))
        delta = angle_weights.get(row["angle"] or "中性", 0.0) * weight
        for party in parties:
            party_scores[party] += delta
            mention_counts[party] += 1

    diff = party_scores["國民黨"] - party_scores["民進黨"]
    if abs(diff) < 2.0:
        winner = "互有攻防"
        commentary = (
            "今日日報中藍綠互有攻防，焦點多集中在表態、回應與議題延伸，"
            "雙方皆有聲量，但仍未形成足以定調全天輿論的單邊優勢。"
        )
    elif diff > 0:
        winner = "國民黨略占上風"
        commentary = (
            "今日相關標題中，國民黨在高聲量焦點與議題主導上較占版面優勢，"
            "但目前仍偏短線攻防，是否能轉成穩定加分仍待後續觀察。"
        )
    else:
        winner = "民進黨略占上風"
        commentary = (
            "今日相關標題中，民進黨在回應節奏與議題主導上較有存在感，"
            "但現階段仍偏短線優勢，是否延續仍要看後續新聞與聲量變化。"
        )

    if mention_counts["國民黨"] == 0 and mention_counts["民進黨"] == 0:
        winner = "互有攻防"
        commentary = "今日日報焦點較分散，藍綠皆未形成明確得分主軸，整體更像零星攻防與議題交錯，後續仍需觀察聲量是否集中。"

    return winner, limit_text(commentary, 85)


def generate_daily_commentary(client: Any | None, recent_articles: list[sqlite3.Row]) -> tuple[str, str]:
    fallback_winner, fallback_commentary = fallback_daily_commentary(recent_articles)
    if client is None or not recent_articles:
        return fallback_winner, fallback_commentary

    focus_lines: list[str] = []
    for index, row in enumerate(recent_articles[:8], start=1):
        entities = json.loads(row["entities"]) if row["entities"] else []
        parties = "、".join(sorted(detect_parties(row["title"] or "", entities))) or "未明"
        focus_lines.append(
            f"{index}. 標題：{row['title']}｜類別：{row['category']}｜風向：{row['angle']}｜"
            f"對象：{parties}｜分數：{float(row['importance'] or 0):.1f}"
        )

    prompt = textwrap.dedent(
        f"""
        你是台灣政治輿情分析師，請只根據以下新聞標題與簡單標記做保守判讀。
        任務是判斷今天整體輿論對國民黨、民進黨誰相對得分，若無明顯差距就寫平手。
        不要過度推論，不要下選舉結論。
        請回傳 JSON：
        {{
          "winner": "國民黨略占上風/民進黨略占上風/互有攻防",
          "commentary": "55到85字，客觀講評"
        }}

        今日焦點：
        {chr(10).join(focus_lines)}
        """
    ).strip()

    try:
        response = client.chat.completions.create(
            model=DAILY_COMMENTARY_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "你負責撰寫台灣政治輿情簡報，口吻客觀、保守、精煉。",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.choices[0].message.content)
        winner = payload.get("winner") or fallback_winner
        commentary = payload.get("commentary") or fallback_commentary
        return limit_text(winner, 14), limit_text(commentary, 85)
    except Exception:
        logger.exception("Daily commentary generation failed; using fallback commentary.")
        return fallback_winner, fallback_commentary


def format_message(item: dict[str, Any], analysis: dict[str, Any]) -> str:
    entities = compact_list(analysis.get("entities", []), limit=3)
    keywords = compact_list(analysis.get("matched_keywords", item.get("matched_keywords", [])), limit=4)
    published = item.get("published_at") or "未知時間"
    score = float(analysis.get("importance", 5))
    headline = clean_headline(item["title"], max_length=42)
    return textwrap.dedent(
        f"""
        <b>{escape_html(MONITOR_NAME)}快報</b>
        <b>{escape_html(headline)}</b>

        <b>評級</b>：{importance_label(score)}｜{score:.1f}/10
        <b>類別</b>：{escape_html(analysis.get('category', '一般輿情'))}
        <b>風向</b>：{escape_html(analysis.get('angle', '中性'))}
        <b>對象</b>：{escape_html(entities)}
        <b>關鍵字</b>：{escape_html(keywords)}
        <b>來源</b>：{escape_html(item['source_name'])}
        <b>時間</b>：{escape_html(published)}

        <b>摘要</b>
        {escape_html(analysis.get('summary', '無摘要'))}

        <b>後續影響</b>
        {escape_html(analysis.get('impact_analysis', '無'))}

        <b>應對建議</b>
        {escape_html(analysis.get('action_suggest', '無'))}

        <a href="{escape_html(item['link'])}">查看原文</a>
        """
    ).strip()


def fetch_recent_articles(conn: sqlite3.Connection, hours: int, limit: int) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT title, source_name, category, topic, entities, importance, angle,
               summary, link, created_at, matched_keywords, impact_analysis
        FROM articles
        WHERE created_at >= datetime('now', ?)
        ORDER BY importance DESC, created_at DESC
        LIMIT ?
        """,
        (f"-{hours} hours", limit),
    ).fetchall()
    return rows


def build_daily_report(
    conn: sqlite3.Connection,
    hours: int = 24,
    limit: int = DAILY_REPORT_LIMIT,
    client: Any | None = None,
) -> str:
    recent_articles = fetch_recent_articles(conn, hours=hours, limit=limit)
    if not recent_articles:
        return ""

    category_counts: dict[str, int] = {}
    angle_counts: dict[str, int] = {}
    keyword_counts: dict[str, int] = {}
    top_lines: list[str] = []
    high_priority_count = 0

    for index, row in enumerate(recent_articles, start=1):
        category = row["category"] or "一般輿情"
        angle = row["angle"] or "中性"
        category_counts[category] = category_counts.get(category, 0) + 1
        angle_counts[angle] = angle_counts.get(angle, 0) + 1
        score = float(row["importance"] or 0)
        if score >= 8.0:
            high_priority_count += 1

        entities = json.loads(row["entities"]) if row["entities"] else []
        entity_text = compact_list(entities, limit=1, fallback="")
        keywords = json.loads(row["matched_keywords"]) if row["matched_keywords"] else []
        for keyword in keywords[:3]:
            keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1

        if index <= min(limit, 6):
            headline = clean_headline(row["title"], max_length=36)
            meta_parts = [category]
            if entity_text:
                meta_parts.append(entity_text)
            meta_parts.append(f"{score:.1f}/10")
            top_lines.append(
                f"{index}. {headline}\n"
                f"　{'｜'.join(meta_parts)}"
            )

    category_summary = compact_count_summary(category_counts, limit=2)
    angle_summary = compact_count_summary(angle_counts, limit=2)
    keyword_summary = compact_count_summary(keyword_counts, limit=3)
    top_section = "\n\n".join(top_lines) if top_lines else "今日無重點新聞。"
    commentary_winner, commentary_text = generate_daily_commentary(client, recent_articles)

    report = textwrap.dedent(
        f"""
        <b>{escape_html(MONITOR_NAME)}日報</b>

        <b>⭐ 觀測區間</b>
        最近 {hours} 小時

        <b>⭐ 摘要</b>
        情報數：{len(recent_articles)} 則
        高關注：{high_priority_count} 則
        ⭐ 主戰場：{escape_html(category_summary)}
        🌪️ 風向：{escape_html(angle_summary)}
        🔥 熱詞：{escape_html(keyword_summary)}

        <b>⭐ 今日焦點</b>

        {escape_html(top_section)}

        <b>🧠 AI講評</b>
        今日判讀：{escape_html(commentary_winner)}
        {escape_html(commentary_text)}
        """
    ).strip()
    return report


def send_daily_report(conn: sqlite3.Connection, hours: int = 24, limit: int = DAILY_REPORT_LIMIT) -> None:
    client = get_openai_client()
    report = build_daily_report(conn, hours=hours, limit=limit, client=client)
    if not report:
        logger.info("最近沒有可彙整的情報。")
        return
    sent, result = send_telegram_message(report)
    if sent:
        logger.info("每日輿情報告已推送。")
    else:
        logger.warning(f"每日輿情報告未推送 | {result}")


def run_monitor_with_options(ignore_dedupe: bool = False) -> None:
    conn = init_db()
    try:
        client = get_openai_client()
        news_items = fetch_news(recent_hours=RECENT_NEWS_HOURS)
        if not news_items:
            logger.info("沒有抓到符合條件的輿情新聞。")
            return

        logger.info(f"本次抓到 {len(news_items)} 則候選新聞。")
        duplicate_count = 0
        similar_count = 0
        new_count = 0
        sent_count = 0
        recent_titles = [] if ignore_dedupe else load_recent_titles(conn, hours=DEDUPE_HOURS)

        for item in news_items:
            base_dedupe_key = build_dedupe_key(item["title"], item["link"])
            item["dedupe_key"] = base_dedupe_key
            if not ignore_dedupe and article_exists(conn, base_dedupe_key, hours=DEDUPE_HOURS):
                duplicate_count += 1
                continue
            if not ignore_dedupe:
                similar_title = find_similar_title_in_memory(recent_titles, item["title"])
                if similar_title is not None:
                    similar_count += 1
                    logger.info(f"[相似略過] {item['title']} | 類似於: {similar_title}")
                    continue
            if ignore_dedupe:
                item["dedupe_key"] = build_runtime_dedupe_key(item["title"], item["link"])

            analysis = analyze_news(client, item["title"], item.get("matched_keywords", []))
            try:
                article_id = save_article(conn, item, analysis)
            except sqlite3.IntegrityError:
                duplicate_count += 1
                continue
            recent_titles.insert(0, item["title"])
            recent_titles = recent_titles[:200]
            new_count += 1

            bq_uploaded, bq_result = upload_to_bigquery(item, analysis)
            if bq_uploaded:
                logger.info(f"[BigQuery 已同步] {item['title']}")
            else:
                logger.info(f"[BigQuery 未同步] {item['title']} | {bq_result}")

            score = float(analysis.get("importance", 5))
            if score < MIN_PUSH_IMPORTANCE:
                logger.info(f"[低分未推送] {item['title']} | importance={score:.1f}")
                continue

            message = format_message(item, analysis)
            sent, result = send_telegram_message(message)
            if sent:
                mark_as_sent(conn, article_id)
                sent_count += 1
                logger.info(f"[已推送] {item['title']}")
            else:
                logger.warning(f"[已儲存未推送] {item['title']} | {result}")

        logger.info("-" * 50)
        logger.info(f"候選新聞: {len(news_items)} 則")
        logger.info(f"重複略過: {duplicate_count} 則")
        logger.info(f"相似略過: {similar_count} 則")
        logger.info(f"新增情報: {new_count} 則")
        logger.info(f"Telegram 已推送: {sent_count} 則")
        logger.info(f"資料庫: {DB_PATH}")
        logger.info(f"日誌檔: {LOG_PATH}")
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"{MONITOR_NAME}程式")
    parser.add_argument(
        "--mode",
        choices=["monitor", "daily-report"],
        default="monitor",
        help="monitor: 抓新消息並推送；daily-report: 彙整最近資料做日報",
    )
    parser.add_argument("--hours", type=int, default=24, help="daily-report 模式的時間範圍")
    parser.add_argument("--limit", type=int, default=DAILY_REPORT_LIMIT, help="daily-report 模式最多納入幾則情報")
    parser.add_argument("--list-only", action="store_true", help="只列出本次抓到的標題，不做 AI 分析與 Telegram 推送")
    parser.add_argument("--ignore-dedupe", action="store_true", help="忽略資料庫去重檢查，適合測試推送")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.mode == "monitor":
        if args.list_only:
            news_items = fetch_news(recent_hours=RECENT_NEWS_HOURS)
            logger.info(f"本次抓到 {len(news_items)} 則候選新聞。")
            for index, item in enumerate(news_items, start=1):
                keywords = "、".join(item.get("matched_keywords", [])[:4])
                logger.info(f"{index}. ({item['source_name']}) {item['title']} | 關鍵字: {keywords}")
        else:
            run_monitor_with_options(ignore_dedupe=args.ignore_dedupe)
    else:
        conn = init_db()
        try:
            send_daily_report(conn, hours=args.hours, limit=args.limit)
        finally:
            conn.close()
