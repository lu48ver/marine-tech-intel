"""Paris MoU crawler.

parismou.org moved from Drupal to WordPress around 2026-08: the listing is
now /publications with <a class="blog-item"> rows (a .tagline date like
"28 August 2026" and an <h4> title). The old "Press releases" category
filter no longer exists, so per-ship banning notices ("M/V ... refused
access ...") — deliberately excluded before, of little daily value to a
superintendent — are filtered out by title instead.
"""

import re
import time

from crawlers.base import BaseCrawler, normalize_date, run_from_cli

BASE_URL = "https://parismou.org"
LISTING_URL = "https://parismou.org/publications"

# Per-ship banning notices, e.g. 'M/V "VULIN" - IMO no: 9015448 refused access'
BANNING_RE = re.compile(r"refused access|^M/V\b", re.I)


class ParisMouCrawler(BaseCrawler):
    source_id = "paris_mou"
    source_name = "Paris MoU"
    source_url = LISTING_URL
    # parismou.org is slow to answer from GitHub's runner IPs and sometimes
    # drops the first connection outright, so allow longer and retry.
    timeout = 60

    def fetch(self) -> list[dict]:
        soup = self._get_soup_with_retry(self.source_url)
        items = []
        seen = set()

        for row in soup.select("a.blog-item[href]"):
            url = row["href"]
            if url.startswith("/"):
                url = BASE_URL + url
            title_el = row.find("h4")
            date_el = row.select_one(".tagline")
            if not (title_el and date_el):
                continue
            title = " ".join(title_el.get_text(" ", strip=True).split())
            if not title or url in seen or BANNING_RE.search(title):
                continue
            seen.add(url)

            try:
                published = normalize_date(date_el.get_text(" ", strip=True))
            except (ValueError, OverflowError):
                continue

            items.append(
                {
                    "title": title,
                    "url": url,
                    "published_at": published,
                    "summary": "",
                    "tags": ["psc", "paris-mou"],
                }
            )

        items.sort(key=lambda x: x["published_at"], reverse=True)
        return items

    def _get_soup_with_retry(self, url: str, attempts: int = 3):
        """GET with retries — the host intermittently times out from CI."""
        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                return self.get_soup(url)
            except Exception as exc:
                last_exc = exc
                self.logger.warning("attempt %d/%d failed: %s", attempt, attempts, exc)
                if attempt < attempts:
                    time.sleep(5 * attempt)
        raise last_exc


if __name__ == "__main__":
    run_from_cli(ParisMouCrawler)
