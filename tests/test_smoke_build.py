"""Smoke test: build_site.main() must produce a site from fixture data.

Catches template/pipeline breakage (renamed context keys, template syntax,
missing files) before CI deploys a broken page. Uses the real templates/ and
static/ but fixture data in a temp dir.
"""

import json

from scripts import build_site as bs

SOURCES = [{
    "source_id": "fixture",
    "source_name": "Fixture Source",
    "source_url": "https://example.com",
    "category": "Test",
    "enabled": True,
}]

TOPICS = [{
    "id": "t1", "name": "Topic One", "priority": "high",
    "summary": "test topic", "keywords": ["fixture"],
}]

UPDATE = {
    "source_id": "fixture",
    "source_name": "Fixture Source",
    "source_url": "https://example.com",
    "last_crawled_at": "2026-07-06T08:00:00+08:00",
    "last_success_at": "2026-07-06T08:00:00+08:00",
    "crawl_status": "success",
    "items": [{
        "title": "A fixture article",
        "url": "https://example.com/a",
        "published_at": "2026-07-05",
        "first_seen_at": "2026-07-05T08:00:00+08:00",
        "summary": "mentions fixture keyword",
        "tags": [],
        "importance": "action",
        "category": "regulation",
    }],
}


def test_main_builds_site_from_fixtures(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    updates_dir = data_dir / "updates"
    build_dir = tmp_path / "build"
    updates_dir.mkdir(parents=True)

    (data_dir / "sources.json").write_text(json.dumps(SOURCES), encoding="utf-8")
    (data_dir / "topics.json").write_text(json.dumps(TOPICS), encoding="utf-8")
    (updates_dir / "fixture.json").write_text(
        json.dumps(UPDATE, ensure_ascii=False), encoding="utf-8"
    )

    monkeypatch.setattr(bs, "DATA_DIR", data_dir)
    monkeypatch.setattr(bs, "UPDATES_DIR", updates_dir)
    monkeypatch.setattr(bs, "BUILD_DIR", build_dir)

    assert bs.main() == 0

    html = (build_dir / "index.html").read_text(encoding="utf-8")
    assert "A fixture article" in html
    assert "須行動" in html  # action badge rendered
    assert (build_dir / "topic-t1.html").exists()
    assert (build_dir / "static" / "style.css").exists()

    index = json.loads((build_dir / "search.json").read_text(encoding="utf-8"))
    assert index and index[0]["url"] == "https://example.com/a"


def test_main_fails_cleanly_without_data(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    (data_dir / "updates").mkdir(parents=True)
    (data_dir / "sources.json").write_text("[]", encoding="utf-8")
    (data_dir / "topics.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(bs, "DATA_DIR", data_dir)
    monkeypatch.setattr(bs, "UPDATES_DIR", data_dir / "updates")
    monkeypatch.setattr(bs, "BUILD_DIR", tmp_path / "build")
    assert bs.main() == 1
