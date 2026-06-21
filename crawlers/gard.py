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
RECENT_LIMIT = 12  # newest articles regardless of topic
TOPIC_LIMIT = 18   # extra newest articles whose slug matches a watch topic
MAX_TOTAL = 30     # hard cap on article-page fetches per crawl

# Only use specific keywords (len >= 5) for slug matching to avoid noise from
# short tokens like "cii"/"ghg"; Chinese keywords never match English slugs.
MIN_SLUG_KEYWORD_LEN = 5


class GardCrawler(BaseCrawler):
    source_id = "gard_insight"
    source_name = "Gard Insight"
    source_url = "https://www.gard.no/insights"
    max_items = MAX_TOTAL  # keep topic-relevant (older) items, not just newest 20

    def fetch(self) -> list[dict]:
        items = []
        for url in self._select_article_urls():
            item = self._parse_article(url)
            if item:
                items.append(item)
        items.sort(key=lambda x: x["published_at"], reverse=True)
        return items

    def _sitemap_entries(self) -> list[str]:
        """All insight article URLs from the sitemap, newest-first."""
        index = BeautifulSoup(self.get(SITEMAP_INDEX).text, "xml")
        insights_sm = next(
            (loc.get_text(strip=True) for loc in index.find_all("loc") if "insights" in loc.get_text()),
            None,
        )
        if not insights_sm:
            return []
        sm = BeautifulSoup(self.get(insights_sm).text, "xml")
        return [u.find("loc").get_text(strip=True) for u in sm.find_all("url") if u.find("loc")]

    def _select_article_urls(self) -> list[str]:
        """Newest articles PLUS older ones matching a watch topic.

        Gard publishes ~800 insights; the newest few rarely cover evergreen
        watch topics (biofouling, gas detection, fuel sampling), so we also
        pull the newest articles whose slug matches a topic keyword.
        """
        entries = self._sitemap_entries()
        selected, seen = [], set()

        for url in entries[:RECENT_LIMIT]:
            if url not in seen:
                seen.add(url)
                selected.append(url)

        keywords = [
            kw.lower()
            for topic in self.topics
            for kw in topic.get("keywords", [])
            if len(kw) >= MIN_SLUG_KEYWORD_LEN
        ]
        topic_added = 0
        for url in entries:
            if topic_added >= TOPIC_LIMIT or len(selected) >= MAX_TOTAL:
                break
            if url in seen:
                continue
            slug_text = url.rstrip("/").split("/")[-1].replace("-", " ").lower()
            if any(kw in slug_text for kw in keywords):
                seen.add(url)
                selected.append(url)
                topic_added += 1
        return selected

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
