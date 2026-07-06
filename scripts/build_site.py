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
BRIEF_WINDOW_DAYS = 60  # BRIEF only considers items published within this window
BRIEF_PER_SOURCE = 3  # cap per source so one chatty source can't flood BRIEF
SOURCE_ITEM_LIMIT = 5  # items shown per source card
TOPIC_WINDOW_DAYS = 365  # topic cards / search only show the recent slice

# AI importance rating (scripts/summarize.py) → ranking tier. Items the AI has
# not rated yet rank alongside "notice" so the site degrades gracefully when
# the summarize step is skipped.
IMPORTANCE_ORDER = {"action": 0, "notice": 1, "reference": 2}
DEFAULT_IMPORTANCE_RANK = IMPORTANCE_ORDER["notice"]

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


def load_summary_cache() -> dict:
    """Load cached AI summaries (url -> record), or {} if none yet."""
    cache_path = DATA_DIR / "summaries.json"
    if cache_path.exists():
        try:
            return load_json(cache_path)
        except json.JSONDecodeError:
            logger.warning("summaries.json corrupt — ignoring")
    return {}


def match_topics(item: dict, topics: list[dict]) -> list[str]:
    """Topic ids whose keywords appear in the item's text.

    Matches against title + original summary + AI Chinese summary + tags, so
    terse-titled PDFs still get classified from their richer content. Keywords
    may be English or Chinese (substring, case-insensitive).
    """
    haystack = " ".join(
        [
            item.get("title", ""),
            item.get("summary", ""),
            item.get("summary_zh", ""),
            " ".join(item.get("tags", [])),
        ]
    ).lower()
    return [t["id"] for t in topics if any(kw.lower() in haystack for kw in t.get("keywords", []))]


def load_source_data(topics: list[dict]) -> list[dict]:
    """Load each enabled source's crawled JSON, in sources.json order.

    Re-applies cached AI summaries by URL so the site keeps showing them even
    when a fresh crawl overwrote the items and the summarize step did not run,
    then re-classifies topics using the (now richer) text incl. the AI summary.
    """
    sources_meta = load_json(DATA_DIR / "sources.json")
    summary_cache = load_summary_cache()
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
        for item in data.get("items", []):
            cached = summary_cache.get(item.get("url", ""))
            if cached:
                if not item.get("summary_zh"):
                    item["summary_zh"] = cached["summary_zh"]
                if not item.get("importance") and cached.get("importance"):
                    item["importance"] = cached["importance"]
            item["topic_ids"] = match_topics(item, topics)
        out.append(data)
    return out


def importance_rank(item: dict) -> int:
    return IMPORTANCE_ORDER.get(item.get("importance", ""), DEFAULT_IMPORTANCE_RANK)


def build_brief(sources: list[dict], now: datetime) -> list[dict]:
    """The front-page brief: recent AND important, not merely newest.

    Per source: keep items published within BRIEF_WINDOW_DAYS, drop AI-rated
    "reference" noise (commercial/PR), rank by importance then date, and cap
    at BRIEF_PER_SOURCE so a high-volume source cannot flood the page. The
    merged result is again ordered importance-first, newest within each tier.

    Falls back to the plain newest-first list if the filters leave nothing
    (e.g. every crawl has gone stale), so BRIEF never renders empty.
    """
    cutoff = (now - timedelta(days=BRIEF_WINDOW_DAYS)).date().isoformat()
    merged = []
    for src in sources:
        candidates = [
            item
            for item in src.get("items", [])
            if item.get("published_at", "") >= cutoff
            and item.get("importance") != "reference"
        ]
        candidates.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        candidates.sort(key=importance_rank)
        for item in candidates[:BRIEF_PER_SOURCE]:
            merged.append({**item, "source_name": src["source_name"], "source_id": src["source_id"]})

    if not merged:  # degrade to the old behaviour rather than show nothing
        for src in sources:
            for item in src.get("items", []):
                merged.append(
                    {**item, "source_name": src["source_name"], "source_id": src["source_id"]}
                )

    merged.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    merged.sort(key=importance_rank)
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


def build_search_index(sources: list[dict], now: datetime) -> list[dict]:
    """Flatten recent items across sources into a compact client-side search index.

    Powers the in-browser search (pure JS, no backend): one entry per article
    with the fields the front-end matches/renders against. Only the recent
    slice (TOPIC_WINDOW_DAYS) is indexed — the site tracks what's current;
    the long-term archive lives elsewhere (Obsidian export, planned).
    """
    cutoff = (now - timedelta(days=TOPIC_WINDOW_DAYS)).date().isoformat()
    index = []
    seen = set()
    for src in sources:
        for item in src.get("items", []):
            url = item.get("url", "")
            if url in seen or item.get("published_at", "") < cutoff:
                continue
            seen.add(url)
            index.append(
                {
                    "title": item.get("title", ""),
                    "summary": item.get("summary_zh") or item.get("summary", ""),
                    "source": src["source_name"],
                    "url": url,
                    "date": item.get("published_at", ""),
                    "tags": item.get("tags", []),
                    "topics": item.get("topic_ids", []),
                    "importance": item.get("importance", ""),
                }
            )
    index.sort(key=lambda x: x.get("date", ""), reverse=True)
    return index


def build_topics_view(topics: list[dict], sources: list[dict], now: datetime) -> list[dict]:
    """For each topic, gather matching RECENT items across sources, newest first.

    The site is a recency lens (an empty topic means "quiet lately" and that is
    useful signal), so items older than TOPIC_WINDOW_DAYS stay out even when a
    slow source's latest-20 stretches back a decade.
    """
    cutoff = (now - timedelta(days=TOPIC_WINDOW_DAYS)).date().isoformat()
    view = []
    for topic in topics:
        matched = []
        for src in sources:
            for item in src.get("items", []):
                if topic["id"] in item.get("topic_ids", []) and item.get("published_at", "") >= cutoff:
                    matched.append(
                        {**item, "source_name": src["source_name"], "source_id": src["source_id"]}
                    )
        matched.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        view.append({**topic, "items": matched, "item_count": len(matched)})
    return view


def make_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )


def render(context: dict) -> str:
    return make_env().get_template("index.html").render(**context)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    now = datetime.now(TAIPEI_TZ)

    topics = load_json(DATA_DIR / "topics.json")
    sources = load_source_data(topics)
    if not sources:
        logger.error("no source data found — run crawlers first")
        return 1

    digest = {}
    digest_path = DATA_DIR / "digest.json"
    if digest_path.exists():
        try:
            digest = load_json(digest_path)
        except json.JSONDecodeError:
            logger.warning("digest.json corrupt — ignoring")

    context = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        # Cache-buster appended to static asset URLs so browsers never serve a
        # stale style.css / main.js after a rebuild or daily Pages deploy.
        "asset_version": now.strftime("%Y%m%d%H%M%S"),
        "brief_items": build_brief(sources, now),
        "sources": build_sources_view(sources, now),
        "topics": build_topics_view(topics, sources, now),
        "digest": digest,
    }

    env = make_env()
    html = env.get_template("index.html").render(**context)

    # Fresh build dir each time
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)
    (BUILD_DIR / "index.html").write_text(html, encoding="utf-8")
    shutil.copytree(STATIC_DIR, BUILD_DIR / "static")

    # Client-side search index (all articles, searched in the browser)
    search_index = build_search_index(sources, now)
    (BUILD_DIR / "search.json").write_text(
        json.dumps(search_index, ensure_ascii=False), encoding="utf-8"
    )

    # One standalone brief page per topic (topic-<id>.html)
    brief_tmpl = env.get_template("topic_brief.html")
    for topic in context["topics"]:
        page = brief_tmpl.render(
            topic=topic,
            generated_at=context["generated_at"],
            asset_version=context["asset_version"],
        )
        (BUILD_DIR / f"topic-{topic['id']}.html").write_text(page, encoding="utf-8")

    logger.info(
        "built build/index.html + %d topic pages — %d brief, %d sources, %d topics",
        len(context["topics"]),
        len(context["brief_items"]),
        len(context["sources"]),
        len(context["topics"]),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
