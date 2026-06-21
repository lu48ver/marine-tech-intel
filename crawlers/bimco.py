"""BIMCO News crawler.

The news listing is client-rendered, so we discover article URLs from the
sitemap (their path encodes the date: /bimco-news/YYYY/MM/DD-slug/), take the
most recent, and read each article's Open Graph title/description.
"""

import re

from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, run_from_cli

SITEMAP_URL = "https://www.bimco.org/sitemap.xml"
ARTICLE_RE = re.compile(r"/news-insights/bimco-news/(\d{4})/(\d{2})/(\d{2})-")
ARTICLE_LIMIT = 15


class BimcoCrawler(BaseCrawler):
    source_id = "bimco_news"
    source_name = "BIMCO News"
    source_url = "https://www.bimco.org/news-insights/bimco-news/"

    def fetch(self) -> list[dict]:
        articles = self._recent_articles()
        items = []
        for published, url in articles:
            item = self._parse_article(url, published)
            if item:
                items.append(item)
        items.sort(key=lambda x: x["published_at"], reverse=True)
        return items

    def _recent_articles(self) -> list[tuple[str, str]]:
        """Return [(published_date, url)] for recent news, newest first."""
        sm = BeautifulSoup(self.get(SITEMAP_URL).text, "xml")
        found = []
        for loc in sm.find_all("loc"):
            url = loc.get_text(strip=True)
            m = ARTICLE_RE.search(url)
            if m:
                found.append((f"{m.group(1)}-{m.group(2)}-{m.group(3)}", url))
        found.sort(reverse=True)
        return found[:ARTICLE_LIMIT]

    def _parse_article(self, url: str, published: str) -> dict | None:
        try:
            soup = BeautifulSoup(self.get(url).text, "lxml")

            def meta(prop: str) -> str:
                el = soup.find("meta", attrs={"property": prop}) or soup.find(
                    "meta", attrs={"name": prop}
                )
                return el["content"].strip() if el and el.has_attr("content") else ""

            title = meta("og:title") or (soup.title.get_text(strip=True) if soup.title else "")
            if not title:
                return None
            return {
                "title": title.strip(),
                "url": url,
                "published_at": published,
                "summary": (meta("og:description") or meta("description"))[:300],
                "tags": ["bimco", "industry", "regulatory"],
            }
        except Exception as exc:  # one bad article must not sink the crawl
            self.logger.warning("skip %s: %s", url, exc)
            return None


if __name__ == "__main__":
    run_from_cli(BimcoCrawler)
