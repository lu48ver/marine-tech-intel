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
        """Fetch and parse, retrying when the page comes back without rows.

        From CI the site sometimes answers 200 with a page that carries no
        listing rows at all (bot challenge / partial render), which BaseCrawler
        would otherwise record as "page structure may have changed".
        """
        for attempt in range(1, self.max_attempts + 1):
            items = self._parse_listing()
            if items:
                return items
            self.logger.warning(
                "listing had no rows (attempt %d/%d)", attempt, self.max_attempts
            )
            if attempt < self.max_attempts:
                time.sleep(self.retry_backoff_sec * attempt)
        return []

    def _parse_listing(self) -> list[dict]:
        soup = self.get_soup(self.source_url)
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

if __name__ == "__main__":
    run_from_cli(ParisMouCrawler)
