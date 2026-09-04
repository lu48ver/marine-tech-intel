"""ClassNK Topics crawler.

The index page is only a hub; the actual dated content lives in
topics_imo.html, which lists ClassNK's summaries of IMO meeting outcomes
(MSC / MEPC Outcomes and Preliminary Reports), each linking a PDF.

Since the 2026-07 site redesign each entry is a structured row —
<a class="p-imo-result__item" href="...pdf"> with __title (MEPC84),
__type (Outcome / Preliminary Report), and a <time class="__date">
("May 2026" / "Oct. 2025") — parsed field-by-field. The legacy layout
(plain PDF links titled "Outcome of MEPC83 (April 2025)") is kept as a
fallback in case the redesign is rolled back.

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
        items = self._fetch_structured(soup, resp.url)
        if items:
            return items
        self.logger.warning("no .p-imo-result__item rows — trying legacy layout")
        return self._fetch_legacy(soup, resp.url)

    def _fetch_structured(self, soup, page_url: str) -> list[dict]:
        """Parse the post-2026-07 redesign: one <a.p-imo-result__item> per report."""
        items = []
        seen = set()
        for row in soup.select("a.p-imo-result__item[href]"):
            if not row["href"].lower().endswith(".pdf"):
                continue
            title_el = row.select_one(".p-imo-result__title")
            type_el = row.select_one(".p-imo-result__type")
            date_el = row.select_one(".p-imo-result__date")
            if not (title_el and type_el and date_el):
                continue
            report_type = " ".join(type_el.get_text(" ", strip=True).split())
            if "Korean Version" in report_type or "Japanese Version" in report_type:
                continue
            meeting = " ".join(title_el.get_text(" ", strip=True).split())
            date_text = date_el.get_text(" ", strip=True)
            try:
                # No day is given; pin to the 1st of the meeting month
                published = normalize_date(f"1 {date_text}")
            except (ValueError, OverflowError):
                continue

            url = self._resolve(page_url, row["href"])
            if url in seen:
                continue
            seen.add(url)

            committee = "mepc" if "MEPC" in meeting else ("msc" if "MSC" in meeting else "imo")
            items.append(
                {
                    "title": f"{report_type} of {meeting} ({date_text})",
                    "url": url,
                    "published_at": published,
                    "summary": "",
                    "tags": ["imo", "iacs", "regulatory", committee],
                }
            )

        items.sort(key=lambda x: x["published_at"], reverse=True)
        return items

    def _fetch_legacy(self, soup, page_url: str) -> list[dict]:
        """Pre-redesign layout: plain PDF links titled '... (April 2025)'."""
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
            url = self._resolve(page_url, a["href"])
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
