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
    "short>\",\"why\":\"<1 sentence Traditional Chinese on why it matters>\","
    "\"articles\":[<indices>]}]}. Use ONLY the provided articles; cite the index "
    "numbers that support each theme. Skip themes supported by fewer than 2 "
    "articles."
)


def load_recent_items() -> list[dict]:
    """Newest items across all sources, with source name attached."""
    items = []
    for path in glob.glob(str(UPDATES_DIR / "*.json")):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for it in data.get("items", []):
            items.append({**it, "source": data.get("source_name", "")})
    items.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return items[:RECENT_ITEMS]


def load_tracked_topics() -> list[str]:
    topics = json.loads((DATA_DIR / "topics.json").read_text(encoding="utf-8"))
    return [t["name"] for t in topics]


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

    items = load_recent_items()
    if not items:
        logger.error("no items found — run crawlers first")
        return 1
    tracked = load_tracked_topics()

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

    out = {
        "generated_at": datetime.now(TAIPEI_TZ).isoformat(timespec="seconds"),
        "model": DEFAULT_MODEL,
        "themes": themes,
    }
    DIGEST_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("digest: %d themes from %d recent articles", len(themes), len(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
