"""Build the static site from crawled JSON + Jinja2 templates.

Reads data/sources.json, data/topics.json and every data/updates/*.json,
assembles the three views (BRIEF / SOURCES / HOT TOPICS), renders
templates/index.html and copies static/ into build/.

Usage:
    python scripts/build_site.py
"""

import json
import logging
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
UPDATES_DIR = DATA_DIR / "updates"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"
BUILD_DIR = PROJECT_ROOT / "build"

TAIPEI_TZ = timezone(timedelta(hours=8))

# Staleness thresholds (days since last successful crawl)
WARN_AFTER_DAYS = 7
CRIT_AFTER_DAYS = 30

BRIEF_LIMIT = 10  # cross-source items on the front page
SOURCE_ITEM_LIMIT = 5  # items shown per source card

logger = logging.getLogger("build_site")


def load_json(path: Path) -> object:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO 8601 string into an aware datetime, or None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def staleness(last_success_at: str | None, now: datetime) -> tuple[str, str]:
    """Return (css_class, human_label) describing how fresh a source is."""
    dt = parse_dt(last_success_at)
    if dt is None:
        return "crit", "從未成功"
    days = (now - dt).days
    if days >= CRIT_AFTER_DAYS:
        return "crit", f"{days} 天前"
    if days >= WARN_AFTER_DAYS:
        return "warn", f"{days} 天前"
    if days <= 0:
        return "ok", "今日"
    return "ok", f"{days} 天前"


def load_source_data() -> list[dict]:
    """Load each enabled source's crawled JSON, in sources.json order."""
    sources_meta = load_json(DATA_DIR / "sources.json")
    out = []
    for meta in sources_meta:
        if not meta.get("enabled"):
            continue
        update_path = UPDATES_DIR / f"{meta['source_id']}.json"
        if not update_path.exists():
            logger.warning("no data file for %s — skipping", meta["source_id"])
            continue
        data = load_json(update_path)
        data["category"] = meta.get("category", "")
        out.append(data)
    return out


def build_brief(sources: list[dict]) -> list[dict]:
    """Merge all items across sources, newest first, capped at BRIEF_LIMIT."""
    merged = []
    for src in sources:
        for item in src.get("items", []):
            merged.append({**item, "source_name": src["source_name"], "source_id": src["source_id"]})
    merged.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return merged[:BRIEF_LIMIT]


def build_sources_view(sources: list[dict], now: datetime) -> list[dict]:
    """One card per source with its latest items and freshness indicator."""
    view = []
    for src in sources:
        css_class, label = staleness(src.get("last_success_at"), now)
        view.append(
            {
                "source_id": src["source_id"],
                "source_name": src["source_name"],
                "source_url": src["source_url"],
                "category": src.get("category", ""),
                "crawl_status": src.get("crawl_status", "unknown"),
                "error_message": src.get("error_message", ""),
                "last_success_at": (src.get("last_success_at") or "")[:10],
                "staleness_class": css_class,
                "staleness_label": label,
                "items": src.get("items", [])[:SOURCE_ITEM_LIMIT],
            }
        )
    return view


def build_topics_view(topics: list[dict], sources: list[dict]) -> list[dict]:
    """For each topic, gather matching items across all sources, newest first."""
    view = []
    for topic in topics:
        matched = []
        for src in sources:
            for item in src.get("items", []):
                if topic["id"] in item.get("topic_ids", []):
                    matched.append(
                        {**item, "source_name": src["source_name"], "source_id": src["source_id"]}
                    )
        matched.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        view.append({**topic, "items": matched, "item_count": len(matched)})
    return view


def render(context: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    return env.get_template("index.html").render(**context)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    now = datetime.now(TAIPEI_TZ)

    sources = load_source_data()
    topics = load_json(DATA_DIR / "topics.json")
    if not sources:
        logger.error("no source data found — run crawlers first")
        return 1

    context = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        # Cache-buster appended to static asset URLs so browsers never serve a
        # stale style.css / main.js after a rebuild or daily Pages deploy.
        "asset_version": now.strftime("%Y%m%d%H%M%S"),
        "brief_items": build_brief(sources),
        "sources": build_sources_view(sources, now),
        "topics": build_topics_view(topics, sources),
    }

    html = render(context)

    # Fresh build dir each time
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)
    (BUILD_DIR / "index.html").write_text(html, encoding="utf-8")
    shutil.copytree(STATIC_DIR, BUILD_DIR / "static")

    logger.info(
        "built build/index.html — %d brief, %d sources, %d topics",
        len(context["brief_items"]),
        len(context["sources"]),
        len(context["topics"]),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
