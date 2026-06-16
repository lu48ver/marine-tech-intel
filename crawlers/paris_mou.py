"""Paris MoU crawler.

Crawls the Paris MoU "Press releases" publication category (committee
meetings, CIC campaigns, annual reports, focused-inspection results) rather
than the full /publications feed, which is dominated by per-ship banning
notices of little daily value to a superintendent.

Each listing row (.views-row) carries the title link and a date rendered with
an ordinal, e.g. "2nd of June 2026", which we normalise to ISO.
"""

import re

from crawlers.base import BaseCrawler, normalize_date, run_from_cli

BASE_URL = "https://parismou.org"
# field_news_category_target_id=2 == "Press releases"
LISTING_URL = "https://parismou.org/publications?field_news_category_target_id=2"

ORDINAL_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)", re.I)


class ParisMouCrawler(BaseCrawler):
    source_id = "paris_mou"
    source_name = "Paris MoU"
    source_url = LISTING_URL

    def fetch(self) -> list[dict]:
        soup = self.get_soup(self.source_url)
        items = []
        seen = set()

        for row in soup.select(".views-row"):
            link = row.find("a", href=True)
            if not link:
                continue
            url = BASE_URL + link["href"] if link["href"].startswith("/") else link["href"]
            title = " ".join(link.get_text(" ", strip=True).split())
            if not title or url in seen:
                continue
            seen.add(url)

            date_el = row.select_one(".views-field-field-news-date")
            published = self._parse_date(date_el.get_text(" ", strip=True)) if date_el else ""
            if not published:
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

    @staticmethod
    def _parse_date(raw: str) -> str:
        """'2nd of June 2026' -> '2026-06-02'. '' if unparseable."""
        cleaned = ORDINAL_RE.sub(r"\1", raw).replace(" of ", " ").strip()
        try:
            return normalize_date(cleaned)
        except (ValueError, OverflowError):
            return ""


if __name__ == "__main__":
    run_from_cli(ParisMouCrawler)
