"""Tokyo MoU crawler.

The publications page is a WordPress block listing: each publication is an
<li> inside <ul class="wp-block-post-template">. Every article permalink
encodes its section and date as /{section}/{YYYY}/{MM}/{DD}/{slug}/, which we
use for both the published date and a human-readable category tag.

MVP only lists titles/links/dates (no PDF text extraction).
"""

import re

from crawlers.base import BaseCrawler, run_from_cli

# Map the URL section segment to a readable category label
SECTION_LABELS = {
    "press-releases": "Press Release",
    "safety-bulletin": "Safety Bulletin",
    "cic-results": "CIC Results",
    "annual-report": "Annual Report",
    "deficiency-photos": "Deficiency Photo",
}

# Match permalinks like /press-releases/2026/03/17/slug/
PERMALINK_RE = re.compile(r"/([a-z-]+)/(\d{4})/(\d{2})/(\d{2})/")


class TokyoMouCrawler(BaseCrawler):
    source_id = "tokyo_mou"
    source_name = "Tokyo MoU"
    source_url = "https://www.tokyo-mou.org/publications/"

    def fetch(self) -> list[dict]:
        soup = self.get_soup(self.source_url)
        items = []
        seen_urls = set()

        for li in soup.select("ul.wp-block-post-template > li"):
            link = li.find("a", href=True)
            if not link:
                continue
            url = link["href"]
            match = PERMALINK_RE.search(url)
            if not match or url in seen_urls:
                continue
            seen_urls.add(url)

            section, year, month, day = match.groups()
            title = " ".join(link.get_text(" ", strip=True).split())
            if not title:
                continue

            excerpt = ""
            p = li.find("p")
            if p:
                excerpt = " ".join(p.get_text(" ", strip=True).split())

            category = SECTION_LABELS.get(section, section.replace("-", " ").title())
            items.append(
                {
                    "title": title,
                    "url": url,
                    "published_at": f"{year}-{month}-{day}",
                    "summary": excerpt[:300],
                    "tags": ["psc", category.lower()],
                }
            )

        items.sort(key=lambda x: x["published_at"], reverse=True)
        return items


if __name__ == "__main__":
    run_from_cli(TokyoMouCrawler)
