"""Export every crawled article into an Obsidian vault as one .md per article.

The archive is APPEND-ONLY and lives in the vault at
"marine engineer/TechNews/": the website shows only the recent slice
(items beyond each source's latest-20 fall off), while this folder keeps
everything forever. Re-running never overwrites or deletes an existing note.

Dedupe is by article URL via an index file (.archive_index.json) inside the
target folder, so renaming a note in Obsidian does not cause re-export.

Runs in the daily GitHub workflow against a checkout of the vault repo, or
locally against the real vault:

    python scripts/export_obsidian.py --vault D:/Nick_obsidian
"""

import argparse
import glob
import hashlib
import json
import logging
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UPDATES_DIR = PROJECT_ROOT / "data" / "updates"

ARCHIVE_SUBDIR = Path("marine engineer") / "TechNews"
INDEX_NAME = ".archive_index.json"

TAIPEI_TZ = timezone(timedelta(hours=8))

# Windows-illegal filename characters plus a few that confuse Obsidian links
SANITIZE_RE = re.compile(r'[\\/:*?"<>|#^\[\]\r\n]+')
MAX_TITLE_LEN = 80

logger = logging.getLogger("export_obsidian")


def safe_filename(item: dict) -> str:
    """`YYYY-MM-DD title.md`, sanitized; URL hash suffix avoids collisions."""
    title = SANITIZE_RE.sub(" ", item.get("title", "untitled")).strip()
    title = re.sub(r"\s+", " ", title)[:MAX_TITLE_LEN].strip()
    date = item.get("published_at", "") or "undated"
    suffix = hashlib.md5(item["url"].encode("utf-8")).hexdigest()[:6]
    return f"{date} {title} [{suffix}].md"


def yaml_str(value: str) -> str:
    """JSON double-quoted strings are valid YAML scalars — safe for any title."""
    return json.dumps(value, ensure_ascii=False)


def render_note(item: dict, source_name: str) -> str:
    lines = [
        "---",
        f"title: {yaml_str(item.get('title', ''))}",
        f"source: {yaml_str(source_name)}",
        f"url: {yaml_str(item.get('url', ''))}",
        f"published: {item.get('published_at', '')}",
        f"archived: {datetime.now(TAIPEI_TZ).date().isoformat()}",
    ]
    if item.get("importance"):
        lines.append(f"importance: {item['importance']}")
    tags = ["TechNews"]
    if item.get("category"):
        tags.append(item["category"])
    tags += item.get("topic_ids", [])
    lines.append("tags: " + json.dumps(tags, ensure_ascii=False))
    lines.append("---")
    lines.append("")

    summary = item.get("summary_zh") or item.get("summary") or ""
    if summary:
        lines.append(summary.strip())
        lines.append("")
    lines.append(f"[原文連結]({item.get('url', '')}) · {source_name}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", required=True, help="path to the Obsidian vault repo root")
    parser.add_argument("--dry-run", action="store_true", help="report what would be written")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    target = Path(args.vault) / ARCHIVE_SUBDIR
    if not target.parent.exists():
        logger.error("vault folder not found: %s", target.parent)
        return 1
    target.mkdir(parents=True, exist_ok=True)

    index_path = target / INDEX_NAME
    index = {}
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("archive index corrupt — rebuilding from scratch")

    written = 0
    for path in sorted(glob.glob(str(UPDATES_DIR / "*.json"))):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        source_name = data.get("source_name", "")
        for item in data.get("items", []):
            url = item.get("url", "")
            if not url or url in index:
                continue
            filename = safe_filename(item)
            note_path = target / filename
            if note_path.exists():  # same date+title from another URL — hash differs, but be safe
                logger.warning("skip, file exists: %s", filename)
                index[url] = filename
                continue
            if args.dry_run:
                logger.info("[dry-run] would write %s", filename)
                written += 1
                continue
            note_path.write_text(render_note(item, source_name), encoding="utf-8")
            index[url] = filename
            written += 1

    if not args.dry_run:
        index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    logger.info("archived %d new article(s), index now %d entries", written, len(index))
    return 0


if __name__ == "__main__":
    sys.exit(main())
