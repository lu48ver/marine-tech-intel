"""AI editorial digest — surface emerging key themes from recent articles.

Reads the most recent crawled articles across all sources and asks the LLM to
identify a handful of key themes that are currently prominent but NOT already
covered by the fixed topics in topics.json ("選題"). The result is written to
data/digest.json and refreshes every run, like a rolling weekly brief.

Grounding: the model is given the real articles (numbered) and must cite the
indices it used; we map those back to real articles and drop anything invalid,
so the digest never references an article that doesn't exist.

Env: OPENAI_API_KEY (or local .openai_key), OPENAI_MODEL (default gpt-4o-mini).
"""

import argparse
import glob
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
UPDATES_DIR = DATA_DIR / "updates"
DIGEST_PATH = DATA_DIR / "digest.json"

TAIPEI_TZ = timezone(timedelta(hours=8))
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
RECENT_ITEMS = 45  # number of newest articles to analyze

logger = logging.getLogger("digest")

SYSTEM_PROMPT = (
    "You are the editor of a maritime technical intelligence brief for ship "
    "engineering superintendents. You are given recent articles (numbered) and "
    "a list of topics ALREADY tracked. Identify 4-6 KEY EMERGING THEMES that "
    "are prominent across these articles but are NOT already in the tracked "
    "list. Respond in JSON only: {\"themes\":[{\"name\":\"<Traditional Chinese, "
    "short>\",\"why\":\"<1-2 sentences Traditional Chinese>\","
    "\"articles\":[<indices>]}]}.\n"
    "The \"why\" must be CONCRETE: state the specific development and its "
    "practical implication for fleet technical management, using facts from "
    "the articles themselves (entry-into-force dates, regulation/instrument "
    "names, regions, figures). Do NOT write generic filler such as "
    "\"愈加重要\", \"至關重要\", \"構成挑戰\", \"造成重大影響\". Do NOT mention "
    "article index numbers inside \"why\" — indices belong ONLY in the "
    "\"articles\" array. Aim for 4-6 themes; it is fine if the \"why\" is "
    "modest, as long as it states specifics rather than platitudes. "
    "Use ONLY the provided articles; cite the index numbers that support each "
    "theme. Skip themes supported by fewer than 2 articles."
)


def load_all_items() -> list[dict]:
    """Every item across all sources, newest first, with source name attached."""
    items = []
    for path in glob.glob(str(UPDATES_DIR / "*.json")):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for it in data.get("items", []):
            items.append({**it, "source": data.get("source_name", "")})
    items.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return items


def load_recent_items() -> list[dict]:
    """Newest RECENT_ITEMS across all sources (input for theme discovery)."""
    return load_all_items()[:RECENT_ITEMS]


def load_topics() -> list[dict]:
    return json.loads((DATA_DIR / "topics.json").read_text(encoding="utf-8"))


TOPIC_STATUS_PROMPT = (
    "You are the editor of a maritime technical intelligence brief for ship "
    "engineering superintendents. For each TRACKED TOPIC below you are given "
    "its recent articles. Write a 2-3 sentence Traditional Chinese status "
    "update (現況) per topic: what concretely happened lately and what it "
    "means for fleet technical management. Cite facts from the articles "
    "(dates, instrument names, figures) — no generic filler like 愈加重要/"
    "構成挑戰. Respond in JSON only: {\"<topic_id>\": \"<status>\", ...}. "
    "Only include topics you were given."
)

TOPIC_STATUS_WINDOW_DAYS = 365
TOPIC_STATUS_MAX_ARTICLES = 8


def build_topic_status(client, topics: list[dict], items: list[dict]) -> dict:
    """One LLM call: per-tracked-topic current-status paragraphs.

    Groups articles by the AI-assigned watch_topics field (summarize.py);
    topics with no recent articles are skipped — the site then falls back to
    the static description.
    """
    cutoff = (datetime.now(TAIPEI_TZ) - timedelta(days=TOPIC_STATUS_WINDOW_DAYS)).date().isoformat()
    groups: dict[str, list[dict]] = {}
    for it in items:
        if it.get("published_at", "") < cutoff:
            continue
        for tid in it.get("watch_topics", []):
            groups.setdefault(tid, []).append(it)

    blocks = []
    for topic in topics:
        arts = groups.get(topic["id"], [])[:TOPIC_STATUS_MAX_ARTICLES]
        if not arts:
            continue
        lines = [f'TOPIC "{topic["id"]}" ({topic["name"]}): {topic["summary"]}']
        for a in arts:
            summary = (a.get("summary_zh") or a.get("summary") or "")[:140]
            lines.append(f'- ({a.get("published_at", "")}) {a.get("title", "")} — {summary}')
        blocks.append("\n".join(lines))
    if not blocks:
        return {}

    resp = client.chat.completions.create(
        model=DEFAULT_MODEL,
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": TOPIC_STATUS_PROMPT},
            {"role": "user", "content": "\n\n".join(blocks)},
        ],
    )
    try:
        data = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return {}
    valid = {t["id"] for t in topics}
    return {k: v.strip() for k, v in data.items()
            if k in valid and isinstance(v, str) and v.strip()}


def build_client():
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        key_file = PROJECT_ROOT / ".openai_key"
        if key_file.exists():
            api_key = key_file.read_text(encoding="utf-8").strip()
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="print prompt, no API call")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    all_items = load_all_items()
    items = all_items[:RECENT_ITEMS]
    if not items:
        logger.error("no items found — run crawlers first")
        return 1
    topics = load_topics()
    tracked = [t["name"] for t in topics]

    # Number the articles so the model can cite them by index
    lines = [
        f"[{i}] ({it['source']}) {it['title']} — {(it.get('summary_zh') or it.get('summary') or '')[:140]}"
        for i, it in enumerate(items)
    ]
    user_prompt = (
        "ALREADY TRACKED TOPICS:\n" + "\n".join(f"- {t}" for t in tracked) +
        "\n\nRECENT ARTICLES:\n" + "\n".join(lines)
    )

    if args.dry_run:
        print(SYSTEM_PROMPT)
        print("\n---\n")
        print(user_prompt[:2000])
        return 0

    client = build_client()
    if client is None:
        logger.error("no API key (set OPENAI_API_KEY or .openai_key)")
        return 1

    resp = client.chat.completions.create(
        model=DEFAULT_MODEL,
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    data = json.loads(resp.choices[0].message.content)

    # Map cited indices back to real articles; drop invalid/empty themes
    themes = []
    for theme in data.get("themes", []):
        refs = []
        for idx in theme.get("articles", []):
            if isinstance(idx, int) and 0 <= idx < len(items):
                it = items[idx]
                refs.append({"title": it["title"], "url": it["url"],
                             "source": it["source"], "published_at": it.get("published_at", "")})
        if len(refs) >= 2 and theme.get("name"):
            themes.append({"name": theme["name"].strip(), "why": (theme.get("why") or "").strip(),
                           "articles": refs})

    # Second call: per-tracked-topic status paragraphs for the watchlist view
    topic_status = {}
    try:
        topic_status = build_topic_status(client, topics, all_items)
    except Exception:
        logger.exception("topic status generation failed — keeping themes only")

    out = {
        "generated_at": datetime.now(TAIPEI_TZ).isoformat(timespec="seconds"),
        "model": DEFAULT_MODEL,
        "themes": themes,
        "topic_status": topic_status,
    }
    DIGEST_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "digest: %d themes, %d topic status from %d recent articles",
        len(themes), len(topic_status), len(items),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
