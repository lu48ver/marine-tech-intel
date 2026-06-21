"""Gard Insights crawler.

Gard's insights listing is client-rendered, so we discover article URLs from
the insights sitemap (newest first by lastmod) and read each article's
JSON-LD (headline / datePublished / description) — all server-rendered for SEO,
so no JavaScript is required.
"""

import json

from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, normalize_date, run_from_cli

SITEMAP_INDEX = "https://www.gard.no/sitemap.xml"
ARTICLE_LIMIT = 15  # newest articles to fetch per crawl


class GardCrawler(BaseCrawler):
    source_id = "gard_insight"
    source_name = "Gard Insight"
    source_url = "https://www.gard.no/insights"

    def fetch(self) -> list[dict]:
        items = []
        for url in self._recent_article_urls():
            item = self._parse_article(url)
            if item:
                items.append(item)
        items.sort(key=lambda x: x["published_at"], reverse=True)
        return items

    def _recent_article_urls(self) -> list[str]:
        """Return the most recent insight article URLs from the sitemap.

        Recency-only by design: the website tracks NEW information. Older
        evergreen articles are kept in the Obsidian archive instead.
        """
        index = BeautifulSoup(self.get(SITEMAP_INDEX).text, "xml")
        insights_sm = next(
            (loc.get_text(strip=True) for loc in index.find_all("loc") if "insights" in loc.get_text()),
            None,
        )
        if not insights_sm:
            return []
        sm = BeautifulSoup(self.get(insights_sm).text, "xml")
        # Sitemap is ordered newest-first; keep that order
        urls = [u.find("loc").get_text(strip=True) for u in sm.find_all("url") if u.find("loc")]
        return urls[:ARTICLE_LIMIT]

    def _parse_article(self, url: str) -> dict | None:
        """Extract title/date/summary from an article's JSON-LD."""
        try:
            soup = BeautifulSoup(self.get(url).text, "lxml")
            ld_tag = soup.find("script", type="application/ld+json")
            if not ld_tag:
                return None
            data = json.loads(ld_tag.get_text())
            title = (data.get("headline") or "").strip()
            published_raw = data.get("datePublished")
            if not title or not published_raw:
                return None
            return {
                "title": title,
                "url": url,
                "published_at": normalize_date(published_raw[:10]),
                "summary": (data.get("description") or "").strip()[:300],
                "tags": ["gard", "p&i", "insight"],
            }
        except Exception as exc:  # one bad article must not sink the crawl
            self.logger.warning("skip %s: %s", url, exc)
            return None


if __name__ == "__main__":
    run_from_cli(GardCrawler)
