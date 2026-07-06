"""DNV Technical & Regulatory News crawler.

The TRN listing is client-rendered by a "DynamicList" component that fetches
/api/listing/news?blockId=<id>. We read that same JSON API. The blockId is
extracted from the page's data-props so we adapt if DNV changes it.

Since 2026-06 dnv.com sits behind Cloudflare bot protection that blocks
plain python-requests by TLS fingerprint (403 "Just a moment..." on every
path, headers don't help). curl_cffi impersonating Chrome's TLS/JA3
fingerprint passes, so this crawler swaps its HTTP session for a curl_cffi
one — the rest of the pipeline is unchanged.
"""

import html as htmlmod
import re

from curl_cffi import requests as curl_requests

from crawlers.base import BaseCrawler, normalize_date, run_from_cli

BASE_URL = "https://www.dnv.com"
PAGE_URL = "https://www.dnv.com/maritime/technical-regulatory-news/"
API_URL = "https://www.dnv.com/api/listing/news"
FALLBACK_BLOCK_ID = "4983"

BLOCK_ID_RE = re.compile(r'"listingType":"News".*?"blockId":(\d+)', re.S)


class DnvCrawler(BaseCrawler):
    source_id = "dnv_trn"
    source_name = "DNV Technical & Regulatory News"
    source_url = PAGE_URL

    def __init__(self) -> None:
        super().__init__()
        # requests-compatible session with a real-browser TLS fingerprint.
        # No custom headers: Cloudflare cross-checks the User-Agent string
        # against the TLS fingerprint, so curl_cffi's own matched set must
        # be left as-is (overriding it gets 403 again).
        self.session = curl_requests.Session(impersonate="chrome")

    def fetch(self) -> list[dict]:
        block_id = self._block_id()
        resp = self.get(API_URL, params={"blockId": block_id})
        results = resp.json().get("results", [])

        items = []
        for entry in results:
            title = (entry.get("title") or "").strip()
            url = entry.get("url") or ""
            if not title or not url:
                continue
            dates = entry.get("date") or []
            raw_date = dates[0] if isinstance(dates, list) and dates else (entry.get("date") or "")
            try:
                published = normalize_date(raw_date)
            except (ValueError, TypeError):
                continue
            items.append(
                {
                    "title": title,
                    "url": url if url.startswith("http") else BASE_URL + url,
                    "published_at": published,
                    "summary": (entry.get("text") or "").strip()[:300],
                    "tags": ["dnv", "class", "regulatory"],
                }
            )

        items.sort(key=lambda x: x["published_at"], reverse=True)
        return items

    def _block_id(self) -> str:
        """Read the News listing blockId from the page, or fall back."""
        try:
            page = self.get(PAGE_URL).text
            match = BLOCK_ID_RE.search(htmlmod.unescape(page))
            if match:
                return match.group(1)
        except Exception as exc:
            self.logger.warning("block_id lookup failed, using fallback: %s", exc)
        return FALLBACK_BLOCK_ID


if __name__ == "__main__":
    run_from_cli(DnvCrawler)
