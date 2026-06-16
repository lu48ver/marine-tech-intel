"""CIMAC WG7 (Fuels) crawler.

The working-group page lists guideline/FAQ PDFs directly, each as an <li> whose
link text ends with the publication date in parentheses, e.g.
"... ISO 8217:2024 - FAQ (02/2024)". We parse that "(MM/YYYY)" for the date and
fall back to a bare year for older items.
"""

import re
from urllib.parse import urljoin

from crawlers.base import BaseCrawler, run_from_cli

PAGE_URL = "https://www.cimac.com/working-groups/wg7-fuels/index.html"

# Dates render as "(MM/YYYY)" and sometimes carry a version, e.g. "(09/2024 v2)"
MONTH_YEAR_RE = re.compile(r"\((\d{1,2})/(\d{4})")
YEAR_PAREN_RE = re.compile(r"\((\d{4})[\s)]")
YEAR_ANY_RE = re.compile(r"(20\d{2})")
TRAILING_DATE_RE = re.compile(r"\s*\((?:\d{1,2}/)?\d{4}[^)]*\)\s*$")


class CimacCrawler(BaseCrawler):
    source_id = "cimac_wg7"
    source_name = "CIMAC WG7 Fuels"
    source_url = PAGE_URL

    def fetch(self) -> list[dict]:
        soup = self.get_soup(self.source_url)
        # CIMAC sets <base href=".../cms/">, so relative links resolve against
        # that, not the page URL.
        base_tag = soup.find("base", href=True)
        base_url = base_tag["href"] if base_tag else self.source_url
        items = []
        seen = set()

        for a in soup.find_all("a", href=True):
            if not a["href"].lower().endswith(".pdf"):
                continue
            # The visible "(MM/YYYY)" date sits in the <li>, not the <a> itself
            container = a.find_parent("li") or a
            text = " ".join(container.get_text(" ", strip=True).split())
            url = urljoin(base_url, a["href"])
            if not text or url in seen:
                continue

            published = self._parse_date(text, a["href"])
            if not published:
                continue
            seen.add(url)

            # Drop the trailing "(MM/YYYY)" / "(YYYY)" and a trailing [PDF] tag
            title = TRAILING_DATE_RE.sub("", text)
            title = re.sub(r"\s*\[PDF\)?\]?\s*$", "", title, flags=re.I).strip()

            items.append(
                {
                    "title": title,
                    "url": url,
                    "published_at": published,
                    "summary": "",
                    "tags": ["cimac", "fuel", "guideline"],
                }
            )

        items.sort(key=lambda x: x["published_at"], reverse=True)
        return items

    @staticmethod
    def _parse_date(text: str, href: str) -> str:
        """Best-effort ISO date from link text, then filename. '' if none."""
        m = MONTH_YEAR_RE.search(text)
        if m:
            month, year = int(m.group(1)), m.group(2)
            return f"{year}-{month:02d}-01"
        m = YEAR_PAREN_RE.search(text) or YEAR_ANY_RE.search(href)
        if m:
            return f"{m.group(1)}-01-01"
        return ""


if __name__ == "__main__":
    run_from_cli(CimacCrawler)
