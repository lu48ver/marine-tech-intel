"""Generate Traditional-Chinese key-point summaries + importance ratings.

Runs AFTER the crawlers and BEFORE build_site. For every item that lacks a
Chinese summary it gathers the real source text — the existing English summary,
the linked PDF, or the linked HTML page — and asks an LLM to condense it into
2-4 Traditional-Chinese key points aimed at a ship engineering superintendent,
plus an importance rating for that same audience:

  action     須行動 — new rule entering force, PSC/CIC campaign, required
             documents/equipment, fuel-quality alert affecting operations
  notice     須知悉 — technical/regulatory development worth knowing
  reference  參考   — commercial/PR/crew/market news with no direct 工務 impact

The rating is what lets the site rank "important" above merely "new" (BRIEF)
instead of treating every article equally.

Anti-hallucination: the model is grounded strictly on the fetched text. If no
usable text can be obtained, the item is skipped (never summarized from its
title alone). Results are cached in data/summaries.json keyed by URL so the
same article is never paid for twice across daily runs. Cached entries from
before the importance field existed are backfilled with a cheap
classify-only call (title + cached summary, no re-fetch).

Env:
  OPENAI_API_KEY   required unless --dry-run
  OPENAI_MODEL     optional, default "gpt-4o-mini"

Usage:
  python scripts/summarize.py             # summarize new items, write back
  python scripts/summarize.py --dry-run   # gather text only, no API calls/cost
  python scripts/summarize.py --limit 3   # cap API calls (for cheap testing)
"""

import argparse
import glob
import io
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
UPDATES_DIR = DATA_DIR / "updates"
CACHE_PATH = DATA_DIR / "summaries.json"

TAIPEI_TZ = timezone(timedelta(hours=8))
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MIN_SOURCE_CHARS = 40   # below this, an existing summary is treated as "missing"
MAX_SOURCE_CHARS = 6000  # truncate long PDFs/pages to control token cost

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

IMPORTANCE_LEVELS = ("action", "notice", "reference")

IMPORTANCE_RUBRIC = (
    "Rate the article's importance FOR A SHIP ENGINEERING SUPERINTENDENT "
    "(工務監督, technical fleet management):\n"
    '- "action": requires action or scheduling — a regulation with an entry-'
    "into-force date, a PSC/CIC inspection campaign, documents or equipment "
    "that must be prepared, or a fuel-quality alert affecting operations.\n"
    '- "notice": technical, regulatory or machinery-related development the '
    "superintendent should know about, but with nothing to do yet.\n"
    '- "reference": commercial, contractual, PR, crew-welfare, security or '
    "market news with no direct technical-management impact."
)

SYSTEM_PROMPT = (
    "You are a maritime technical analyst writing for a ship engineering "
    "superintendent (工務監督). Summarize the SOURCE TEXT into Traditional "
    "Chinese (繁體中文) as 2 to 4 short, practical key-point sentences. "
    "Use ONLY facts stated in the source text; never invent regulation "
    "numbers, dates, or figures.\n\n" + IMPORTANCE_RUBRIC + "\n\n"
    "Respond in JSON only: {\"summary_zh\": \"<the summary>\", "
    "\"importance\": \"action|notice|reference\"}. If the source text is too "
    "short or irrelevant to summarize, use {\"summary_zh\": \"\", "
    "\"importance\": \"reference\"}."
)

CLASSIFY_PROMPT = (
    "You are a maritime technical analyst.\n\n" + IMPORTANCE_RUBRIC + "\n\n"
    "You are given an article title and its existing Chinese summary. "
    "Respond in JSON only: {\"importance\": \"action|notice|reference\"}."
)

logger = logging.getLogger("summarize")


def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("cache file corrupt — starting fresh")
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def extract_pdf_text(content: bytes) -> str:
    """Extract text from the first pages of a PDF byte stream."""
    import pdfplumber

    text_parts = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages[:6]:  # first pages carry the summary/outcome
            text_parts.append(page.extract_text() or "")
            if sum(len(p) for p in text_parts) > MAX_SOURCE_CHARS:
                break
    return "\n".join(text_parts).strip()


def extract_html_text(html: str) -> str:
    """Extract main paragraph text from an article page."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    container = soup.find("article") or soup.find("main") or soup.body
    if container is None:
        return ""
    paras = [p.get_text(" ", strip=True) for p in container.find_all("p")]
    return "\n".join(p for p in paras if len(p) > 30).strip()


def gather_source_text(item: dict) -> tuple[str, str]:
    """Return (source_text, source_kind) for an item, or ("", "") if none.

    Some sources (e.g. Tokyo MoU bulletins) serve a PDF from a URL that does
    not end in .pdf, so the response content-type / magic bytes decide the
    parser, not the URL extension.
    """
    existing = (item.get("summary") or "").strip()
    if len(existing) >= MIN_SOURCE_CHARS:
        return existing, "summary"

    url = item.get("url", "")
    if not url:
        return "", ""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=40)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "").lower()
        is_pdf = "pdf" in ctype or resp.content[:5] == b"%PDF-" or url.lower().endswith(".pdf")
        if is_pdf:
            return extract_pdf_text(resp.content)[:MAX_SOURCE_CHARS], "pdf"
        resp.encoding = resp.apparent_encoding
        return extract_html_text(resp.text)[:MAX_SOURCE_CHARS], "html"
    except Exception as exc:  # network/parse errors must not crash the run
        logger.warning("could not fetch source for %s: %s", url, exc)
    return "", ""


def _normalize_importance(value: object) -> str:
    """Clamp a model-provided importance to a known level (default notice)."""
    value = str(value or "").strip().lower()
    return value if value in IMPORTANCE_LEVELS else "notice"


def summarize_text(client, title: str, text: str) -> tuple[str, str]:
    """Call the LLM; return (summary_zh, importance). Empty summary = declined."""
    resp = client.chat.completions.create(
        model=DEFAULT_MODEL,
        temperature=0.2,
        max_tokens=400,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"TITLE: {title}\n\nSOURCE TEXT:\n{text}"},
        ],
    )
    try:
        data = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return "", "notice"
    summary = (data.get("summary_zh") or "").strip()
    if "NO_SUMMARY" in summary:
        summary = ""
    return summary, _normalize_importance(data.get("importance"))


def classify_only(client, title: str, summary_zh: str) -> str:
    """Backfill importance for an already-summarized item (no source re-fetch)."""
    resp = client.chat.completions.create(
        model=DEFAULT_MODEL,
        temperature=0,
        max_tokens=20,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": CLASSIFY_PROMPT},
            {"role": "user", "content": f"TITLE: {title}\n\nSUMMARY:\n{summary_zh}"},
        ],
    )
    try:
        data = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return "notice"
    return _normalize_importance(data.get("importance"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="gather text only, no API calls")
    parser.add_argument("--limit", type=int, default=0, help="cap number of API calls (0 = no cap)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cache = load_cache()
    now = datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")

    client = None
    if not args.dry_run:
        from openai import OpenAI

        # Key from env (GitHub Actions secret) or a local gitignored file
        # (.openai_key) for local testing without exposing it on the command line.
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            key_file = PROJECT_ROOT / ".openai_key"
            if key_file.exists():
                api_key = key_file.read_text(encoding="utf-8").strip()
        if not api_key:
            logger.error(
                "no API key: set OPENAI_API_KEY or create .openai_key "
                "(use --dry-run to test without a key)"
            )
            return 1
        client = OpenAI(api_key=api_key)

    calls = 0
    stats = {
        "cached": 0,
        "summarized": 0,
        "backfilled": 0,
        "skipped": 0,
        "would_summarize": 0,
        "would_backfill": 0,
    }

    for path in sorted(glob.glob(str(UPDATES_DIR / "*.json"))):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        changed = False
        for item in data.get("items", []):
            url = item.get("url", "")
            if not url:
                continue

            if url in cache:  # already summarized in a previous run
                record = cache[url]
                item["summary_zh"] = record["summary_zh"]
                if not record.get("importance"):
                    # Pre-importance cache entry: cheap classify-only backfill
                    if args.dry_run:
                        stats["would_backfill"] += 1
                    elif not args.limit or calls < args.limit:
                        record["importance"] = classify_only(
                            client, item.get("title", ""), record["summary_zh"]
                        )
                        calls += 1
                        stats["backfilled"] += 1
                        logger.info(
                            "backfilled importance=%s %s",
                            record["importance"], item.get("title", "")[:60],
                        )
                if record.get("importance"):
                    item["importance"] = record["importance"]
                stats["cached"] += 1
                changed = True
                continue

            text, kind = gather_source_text(item)
            if not text:
                stats["skipped"] += 1
                continue

            if args.dry_run:
                stats["would_summarize"] += 1
                logger.info("[dry-run] would summarize (%s) %s", kind, item.get("title", "")[:60])
                continue

            if args.limit and calls >= args.limit:
                continue

            summary_zh, importance = summarize_text(client, item.get("title", ""), text)
            calls += 1
            if not summary_zh:
                stats["skipped"] += 1
                continue

            cache[url] = {
                "summary_zh": summary_zh,
                "importance": importance,
                "model": DEFAULT_MODEL,
                "source_kind": kind,
                "generated_at": now,
            }
            item["summary_zh"] = summary_zh
            item["importance"] = importance
            stats["summarized"] += 1
            changed = True
            logger.info("summarized (%s, %s) %s", kind, importance, item.get("title", "")[:60])

        if changed and not args.dry_run:
            Path(path).write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    if not args.dry_run:
        save_cache(cache)

    logger.info("done: %s", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
