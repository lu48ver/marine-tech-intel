"""LR FOBAS crawler.

The LR knowledge hub renders its listing client-side, so instead of scraping
HTML we call the same JSON search API the site itself uses:

    POST https://www.lr.org/api/search/
    body: {"query": "FOBAS", "page": 1, "pageSize": N, ...}

We keep items whose mainCategory is press-release-like, sorted by date desc.
"""

from crawlers.base import BaseCrawler, run_from_cli

API_URL = "https://www.lr.org/api/search/"
BASE_URL = "https://www.lr.org"

# Categories worth surfacing to engineers (skip podcasts, people stories, etc.)
WANTED_CATEGORIES = {"Press release", "Class News", "Insight article", "Fuel For Thought"}


class LrFobasCrawler(BaseCrawler):
    source_id = "lr_fobas"
    source_name = "LR FOBAS"
    source_url = "https://www.lr.org/en/knowledge/press-room/"

    def fetch(self) -> list[dict]:
        body = {
            "query": "FOBAS",
            "categories": [],
            "page": 1,
            "pageSize": 50,
            "language": "en",
            "sortOrder": 1,
            "includeRecommendations": False,
        }
        resp = self.session.post(API_URL, json=body, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        items = []
        for entry in data.get("items", []):
            category = (entry.get("mainCategory") or "").strip()
            if category not in WANTED_CATEGORIES:
                continue
            published = (entry.get("published") or "")[:10]  # ISO datetime -> date
            if not published:
                continue
            items.append(
                {
                    "title": entry.get("heading", "").strip(),
                    "url": BASE_URL + entry.get("url", ""),
                    "published_at": published,
                    "summary": (entry.get("description") or "").strip()[:300],
                    "tags": ["fobas", "fuel", category.lower()],
                }
            )

        items.sort(key=lambda x: x["published_at"], reverse=True)
        return items


if __name__ == "__main__":
    run_from_cli(LrFobasCrawler)
