"""Tests for BaseCrawler: first_seen_at tracking and failure preservation."""

import json

import pytest

from crawlers import base


class DummyCrawler(base.BaseCrawler):
    source_id = "dummy"
    source_name = "Dummy"
    source_url = "https://example.com"

    def __init__(self, items):
        super().__init__()
        self._items = items

    def fetch(self):
        if isinstance(self._items, Exception):
            raise self._items
        return [dict(it) for it in self._items]


@pytest.fixture
def updates_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "UPDATES_DIR", tmp_path)
    return tmp_path


ITEM = {"title": "A", "url": "https://example.com/a", "published_at": "2026-07-01"}


def read_output(updates_dir):
    return json.loads((updates_dir / "dummy.json").read_text(encoding="utf-8"))


def test_first_run_stamps_first_seen(updates_dir):
    result = DummyCrawler([ITEM]).run()
    assert result["crawl_status"] == "success"
    assert result["items"][0]["first_seen_at"]  # stamped with crawl time


def test_recrawl_preserves_first_seen(updates_dir):
    DummyCrawler([ITEM]).run()
    stamped = read_output(updates_dir)["items"][0]["first_seen_at"]
    DummyCrawler([ITEM]).run()  # same URL crawled again
    assert read_output(updates_dir)["items"][0]["first_seen_at"] == stamped


def test_recrawl_falls_back_to_published_for_legacy_items(updates_dir):
    # Simulate pre-first_seen_at data on disk: known URL must NOT flash as new
    legacy = {"last_success_at": "2026-07-01T08:00:00+08:00", "items": [dict(ITEM)]}
    (updates_dir / "dummy.json").write_text(json.dumps(legacy), encoding="utf-8")
    DummyCrawler([ITEM]).run()
    assert read_output(updates_dir)["items"][0]["first_seen_at"] == ITEM["published_at"]


def test_failure_preserves_previous_items(updates_dir):
    DummyCrawler([ITEM]).run()
    previous = read_output(updates_dir)
    result = DummyCrawler(RuntimeError("site changed")).run()
    assert result["crawl_status"] == "error"
    assert "site changed" in result["error_message"]
    assert result["items"] == previous["items"]  # old data survives
    assert result["last_success_at"] == previous["last_success_at"]


def test_empty_fetch_is_treated_as_failure(updates_dir):
    DummyCrawler([ITEM]).run()
    result = DummyCrawler([]).run()
    assert result["crawl_status"] == "error"
    assert result["items"]  # previous items kept


class _Resp:
    def __init__(self, status=200):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            err = Exception(f"HTTP {self.status_code}")
            err.response = self
            raise err


def test_get_retries_transient_failure(updates_dir, monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    crawler = DummyCrawler([ITEM])
    calls = []

    def flaky_get(url, **kwargs):
        calls.append(url)
        if len(calls) < 3:
            raise ConnectionError("connection reset")
        return _Resp()

    monkeypatch.setattr(crawler.session, "get", flaky_get)
    assert crawler.get("https://example.com").status_code == 200
    assert len(calls) == 3  # two failures, then success


def test_get_does_not_retry_client_error(updates_dir, monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    crawler = DummyCrawler([ITEM])
    calls = []

    def not_found(url, **kwargs):
        calls.append(url)
        return _Resp(404)

    monkeypatch.setattr(crawler.session, "get", not_found)
    with pytest.raises(Exception):
        crawler.get("https://example.com/missing")
    assert len(calls) == 1  # a 404 will not fix itself


def test_get_gives_up_after_max_attempts(updates_dir, monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    crawler = DummyCrawler([ITEM])
    calls = []

    def always_fail(url, **kwargs):
        calls.append(url)
        raise TimeoutError("timed out")

    monkeypatch.setattr(crawler.session, "get", always_fail)
    with pytest.raises(TimeoutError):
        crawler.get("https://example.com")
    assert len(calls) == crawler.max_attempts


def test_normalize_date():
    assert base.normalize_date("12 June 2026") == "2026-06-12"
    assert base.normalize_date("2026/06/12") == "2026-06-12"
    with pytest.raises(ValueError):
        base.normalize_date("not a date")
