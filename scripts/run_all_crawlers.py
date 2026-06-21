"""Run every enabled crawler in sequence.

A single crawler failing must NOT abort the others (spec section 10), so each
run is isolated. BaseCrawler.run() already preserves the previous JSON on
failure, so a bad crawl never wipes good data.

Usage:
    python scripts/run_all_crawlers.py
"""

import json
import logging
import sys
from pathlib import Path

# Allow running as a plain script (python scripts/run_all_crawlers.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawlers.base import DATA_DIR  # noqa: E402
from crawlers.bimco import BimcoCrawler  # noqa: E402
from crawlers.cimac import CimacCrawler  # noqa: E402
from crawlers.classnk import ClassNkCrawler  # noqa: E402
from crawlers.dnv import DnvCrawler  # noqa: E402
from crawlers.gard import GardCrawler  # noqa: E402
from crawlers.lr_fobas import LrFobasCrawler  # noqa: E402
from crawlers.paris_mou import ParisMouCrawler  # noqa: E402
from crawlers.tokyo_mou import TokyoMouCrawler  # noqa: E402

logger = logging.getLogger("run_all")

# Maps source_id -> crawler class. Only MVP sources are wired up for now;
# add Phase 2 crawlers here as they are built.
CRAWLER_CLASSES = {
    "lr_fobas": LrFobasCrawler,
    "tokyo_mou": TokyoMouCrawler,
    "classnk": ClassNkCrawler,
    "cimac_wg7": CimacCrawler,
    "paris_mou": ParisMouCrawler,
    "gard_insight": GardCrawler,
    "dnv_trn": DnvCrawler,
    "bimco_news": BimcoCrawler,
}


def enabled_source_ids() -> list[str]:
    """Return source ids marked enabled in data/sources.json."""
    with open(DATA_DIR / "sources.json", encoding="utf-8") as f:
        sources = json.load(f)
    return [s["source_id"] for s in sources if s.get("enabled")]


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    results = []
    for source_id in enabled_source_ids():
        crawler_cls = CRAWLER_CLASSES.get(source_id)
        if crawler_cls is None:
            logger.warning("no crawler class registered for '%s' — skipping", source_id)
            continue
        # Isolate each crawler; run() handles its own errors but guard anyway
        try:
            result = crawler_cls().run()
            results.append((source_id, result["crawl_status"], len(result.get("items", []))))
        except Exception:
            logger.exception("unexpected failure running '%s'", source_id)
            results.append((source_id, "error", 0))

    logger.info("=== summary ===")
    failures = 0
    for source_id, status, count in results:
        logger.info("  %-12s %-8s %d items", source_id, status, count)
        if status != "success":
            failures += 1

    # Non-zero exit only if EVERY crawler failed; partial success is still OK
    return 1 if results and failures == len(results) else 0


if __name__ == "__main__":
    sys.exit(main())
