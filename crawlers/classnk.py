"""ClassNK Topics crawler.

The index page is only a hub; the actual dated content lives in
topics_imo.html, which lists ClassNK's summaries of IMO meeting outcomes
(MSC / MEPC "Outcome of ..." and "Preliminary Report of ..."), each a PDF
whose title carries the meeting month/year in parentheses, e.g.
"Outcome of MEPC83 (April 2025)".

The companion topics_iacs.html is a static explainer with no dated items,
so it is intentionally not crawled.
"""

import re

from crawlers.base import BaseCrawler, normalize_date, run_from_cli

TOPICS_IMO_URL = "https://www.classnk.com/hp/en/info_service/imo_and_iacs/topics_imo.html"

# Meeting month/year in the link title, e.g. "(April 2025)"
DATE_RE = re.compile(r"\(([A-Za-z]+)\s+(\d{4})\)")


class ClassNkCrawler(BaseCrawler):
    source_id = "classnk"
    source_name = "ClassNK Topics"
    source_url = "https://www.classnk.com/hp/en/info_service/imo_and_iacs/index.html"

    def fetch(self) -> list[dict]:
        resp = self.get(TOPICS_IMO_URL)
        resp.encoding = resp.apparent_encoding  # page declares latin-1 but is utf-8
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(resp.text, "lxml")

        items = []
        seen = set()
        for a in soup.find_all("a", href=True):
            if not a["href"].lower().endswith(".pdf"):
                continue
            title = " ".join(a.get_text(" ", strip=True).split())
            # Skip non-English duplicate summaries
            if "Korean Version" in title or "Japanese Version" in title:
                continue
            match = DATE_RE.search(title)
            if not match:
                continue

            month, year = match.groups()
            try:
                # No day is given; pin to the 1st of the meeting month
                published = normalize_date(f"{month} 1, {year}")
            except ValueError:
                continue

            # Resolve relative ../ segments against the page URL
            url = self._resolve(resp.url, a["href"])
            if url in seen:
                continue
            seen.add(url)

            meeting = "mepc" if "MEPC" in title else ("msc" if "MSC" in title else "imo")
            items.append(
                {
                    "title": title,
                    "url": url,
                    "published_at": published,
                    "summary": "",
                    "tags": ["imo", "iacs", "regulatory", meeting],
                }
            )

        items.sort(key=lambda x: x["published_at"], reverse=True)
        return items

    @staticmethod
    def _resolve(base: str, href: str) -> str:
        """Resolve a possibly-relative href against the page URL."""
        from urllib.parse import urljoin

        return urljoin(base, href)


if __name__ == "__main__":
    run_from_cli(ClassNkCrawler)
