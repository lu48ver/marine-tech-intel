"""Base crawler class and shared utilities for Marine Tech Intel.

Every concrete crawler inherits BaseCrawler, implements fetch(), and gets
for free: HTTP session with sane headers, topic auto-tagging, error handling
that preserves the previous successful JSON, and unified output schema
(see spec.md section 5).
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import logging

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# Taiwan local time, used for last_crawled_at timestamps
TAIPEI_TZ = timezone(timedelta(hours=8))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
UPDATES_DIR = DATA_DIR / "updates"

# Some sites block default python-requests UA; use a browser-like one
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def load_topics() -> list[dict]:
    """Load topic definitions (with keyword rules) from data/topics.json."""
    with open(DATA_DIR / "topics.json", encoding="utf-8") as f:
        return json.load(f)


def match_topic_ids(text: str, topics: list[dict]) -> list[str]:
    """Return topic ids whose keywords appear in the given text (case-insensitive)."""
    lowered = text.lower()
    matched = []
    for topic in topics:
        if any(kw in lowered for kw in topic.get("keywords", [])):
            matched.append(topic["id"])
    return matched


def normalize_date(raw: str) -> str:
    """Parse a free-form date string into ISO 8601 (YYYY-MM-DD).

    Raises ValueError if the string cannot be parsed.
    """
    return date_parser.parse(raw, dayfirst=False).date().isoformat()


class BaseCrawler(ABC):
    """Abstract base class for all source crawlers."""

    source_id: str
    source_name: str
    source_url: str
    timeout: int = 30
    max_items: int = 20  # cap items per source to keep JSON small

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.logger = logging.getLogger(f"crawler.{self.source_id}")
        self.topics = load_topics()

    # ---------- HTTP helpers ----------

    def get(self, url: str, **kwargs) -> requests.Response:
        """GET a URL with timeout and raise on HTTP errors."""
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp

    def get_soup(self, url: str, **kwargs) -> BeautifulSoup:
        """GET a URL and parse the HTML with lxml."""
        return BeautifulSoup(self.get(url, **kwargs).text, "lxml")

    # ---------- item helpers ----------

    def assign_topics(self, item: dict) -> dict:
        """Fill item['topic_ids'] by keyword-matching title/summary/tags."""
        haystack = " ".join(
            [item.get("title", ""), item.get("summary", ""), " ".join(item.get("tags", []))]
        )
        item["topic_ids"] = match_topic_ids(haystack, self.topics)
        return item

    @abstractmethod
    def fetch(self) -> list[dict]:
        """Return a list of item dicts (schema: spec.md section 5)."""

    # ---------- main entry ----------

    def run(self) -> dict:
        """Run the crawler, assemble the final JSON, and write it to disk.

        On failure, the previous successful items are preserved and only
        crawl_status / error_message / last_crawled_at are updated.
        """
        output_path = UPDATES_DIR / f"{self.source_id}.json"
        now = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")

        try:
            items = [self.assign_topics(item) for item in self.fetch()][: self.max_items]
            if not items:
                raise RuntimeError("fetch() returned 0 items — page structure may have changed")
            result = {
                "source_id": self.source_id,
                "source_name": self.source_name,
                "source_url": self.source_url,
                "last_crawled_at": now,
                "last_success_at": now,
                "crawl_status": "success",
                "items": items,
            }
            self.logger.info("success: %d items", len(items))
        except Exception as exc:
            self.logger.exception("crawl failed")
            result = self._load_previous(output_path)
            result.update(
                {
                    "source_id": self.source_id,
                    "source_name": self.source_name,
                    "source_url": self.source_url,
                    "last_crawled_at": now,
                    "crawl_status": "error",
                    "error_message": str(exc),
                }
            )

        UPDATES_DIR.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return result

    @staticmethod
    def _load_previous(path: Path) -> dict:
        """Load the previous output JSON so old items survive a failed crawl."""
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    previous = json.load(f)
                return {
                    "last_success_at": previous.get("last_success_at"),
                    "items": previous.get("items", []),
                }
            except (OSError, json.JSONDecodeError):
                pass
        return {"last_success_at": None, "items": []}


def run_from_cli(crawler_cls: type[BaseCrawler]) -> None:
    """Entry point for `python -m crawlers.<name>` single-crawler testing."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    result = crawler_cls().run()
    logger = logging.getLogger("crawler.cli")
    logger.info("crawl_status=%s, items=%d", result["crawl_status"], len(result.get("items", [])))
    logger.info("output: data/updates/%s.json", result["source_id"])
