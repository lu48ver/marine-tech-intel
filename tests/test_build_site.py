"""Unit tests for the pure view-building logic in scripts/build_site.py.

These pin down the content rules the site's value depends on: the BRIEF
ranking (importance-first, per-source cap, recency window), the 12-month
window on topics/search, NEW detection, and topic keyword matching.
"""

from datetime import datetime, timedelta, timezone

from scripts import build_site as bs

TAIPEI = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 6, 12, 0, tzinfo=TAIPEI)

_counter = 0


def mk(days_ago=0, importance="notice", **kw):
    """Build a minimal item published `days_ago` days before NOW."""
    global _counter
    _counter += 1
    item = {
        "title": kw.pop("title", f"item {_counter}"),
        "url": kw.pop("url", f"https://example.com/{_counter}"),
        "published_at": (NOW - timedelta(days=days_ago)).date().isoformat(),
        "importance": importance,
    }
    item.update(kw)
    return item


def src(items, source_id="s1", name="Source 1"):
    return {"source_id": source_id, "source_name": name, "items": items}


# ---------- staleness ----------

def test_staleness_levels():
    assert bs.staleness(None, NOW) == ("crit", "從未成功")
    assert bs.staleness(NOW.isoformat(), NOW)[0] == "ok"
    assert bs.staleness((NOW - timedelta(days=10)).isoformat(), NOW)[0] == "warn"
    assert bs.staleness((NOW - timedelta(days=40)).isoformat(), NOW)[0] == "crit"
    assert bs.staleness("not-a-date", NOW) == ("crit", "從未成功")


# ---------- topic matching ----------

def test_match_topics_is_case_insensitive_for_keywords():
    topics = [{"id": "cii", "keywords": ["CII", "碳強度"]}]
    assert bs.match_topics({"title": "New cii rating rules"}, topics) == ["cii"]


def test_match_topics_uses_ai_chinese_summary():
    topics = [{"id": "fuel", "keywords": ["甲醇"]}]
    item = {"title": "Methanol as fuel", "summary_zh": "甲醇動力船舶的注意事項"}
    assert bs.match_topics(item, topics) == ["fuel"]


def test_match_topics_no_match():
    topics = [{"id": "cii", "keywords": ["cii"]}]
    assert bs.match_topics({"title": "unrelated"}, topics) == []


def test_resolve_topic_ids_prefers_ai_assignment():
    topics = [{"id": "cii", "keywords": ["cii"]}]
    # AI said no topics — keyword hit in the title must NOT override it
    item = {"title": "cii rating", "watch_topics": []}
    assert bs.resolve_topic_ids(item, topics) == []
    item = {"title": "unrelated", "watch_topics": ["cii"]}
    assert bs.resolve_topic_ids(item, topics) == ["cii"]


def test_resolve_topic_ids_falls_back_to_keywords():
    topics = [{"id": "cii", "keywords": ["cii"]}]
    assert bs.resolve_topic_ids({"title": "New CII rules"}, topics) == ["cii"]


# ---------- is_new ----------

def test_is_new_within_window():
    assert bs.is_new({"first_seen_at": (NOW - timedelta(hours=3)).isoformat()}, NOW)


def test_is_new_outside_window_or_missing():
    assert not bs.is_new({"first_seen_at": (NOW - timedelta(days=3)).isoformat()}, NOW)
    assert not bs.is_new({}, NOW)


def test_is_new_accepts_naive_date_only_string():
    # backfilled items carry a bare published date (read as Taipei midnight)
    assert bs.is_new({"first_seen_at": NOW.date().isoformat()}, NOW)


# ---------- BRIEF ----------

def test_brief_excludes_old_and_reference_items():
    sources = [src([
        mk(days_ago=100, importance="action", title="too old"),
        mk(days_ago=1, importance="reference", title="commercial noise"),
        mk(days_ago=1, importance="notice", title="keep me"),
    ])]
    titles = [i["title"] for i in bs.build_brief(sources, NOW)]
    assert titles == ["keep me"]


def test_brief_caps_items_per_source():
    sources = [src([mk(days_ago=d) for d in range(6)])]
    assert len(bs.build_brief(sources, NOW)) == bs.BRIEF_PER_SOURCE


def test_brief_ranks_action_above_newer_notice():
    sources = [src([
        mk(days_ago=1, importance="notice", title="newer notice"),
        mk(days_ago=10, importance="action", title="older action"),
    ])]
    titles = [i["title"] for i in bs.build_brief(sources, NOW)]
    assert titles == ["older action", "newer notice"]


def test_brief_per_source_cap_prefers_important_over_newest():
    items = [mk(days_ago=d, importance="notice") for d in range(3)]
    items.append(mk(days_ago=30, importance="action", title="buried action"))
    sources = [src(items)]
    titles = [i["title"] for i in bs.build_brief(sources, NOW)]
    assert titles[0] == "buried action"
    assert len(titles) == bs.BRIEF_PER_SOURCE


def test_brief_unrated_items_rank_as_notice():
    item = mk(days_ago=1)
    del item["importance"]
    assert [i["title"] for i in bs.build_brief([src([item])], NOW)] == [item["title"]]


def test_brief_falls_back_when_window_filters_everything():
    sources = [src([mk(days_ago=200, title="old but only content")])]
    assert [i["title"] for i in bs.build_brief(sources, NOW)] == ["old but only content"]


# ---------- topics / categories / search windows ----------

def test_topics_view_applies_12_month_window():
    topics = [{"id": "t1", "name": "T1", "keywords": []}]
    sources = [src([
        mk(days_ago=30, topic_ids=["t1"], title="recent"),
        mk(days_ago=400, topic_ids=["t1"], title="ancient"),
    ])]
    view = bs.build_topics_view(topics, sources, NOW)
    assert [i["title"] for i in view[0]["items"]] == ["recent"]
    assert view[0]["item_count"] == 1


def test_categories_view_buckets_and_hides_empty_fallback():
    sources = [src([
        mk(days_ago=1, category="fuel"),
        mk(days_ago=2, category="fuel"),
        mk(days_ago=3, category="regulation"),
    ])]
    view = bs.build_categories_view(sources, NOW)
    counts = {c["id"]: c["item_count"] for c in view}
    assert counts["fuel"] == 2 and counts["regulation"] == 1
    assert "" not in counts  # everything classified → no 未分類 bucket


def test_categories_view_collects_unclassified():
    item = mk(days_ago=1)  # no category field
    view = bs.build_categories_view([src([item])], NOW)
    fallback = [c for c in view if c["id"] == ""]
    assert fallback and fallback[0]["item_count"] == 1


def test_search_index_dedupes_and_windows():
    shared = "https://example.com/shared"
    sources = [
        src([mk(days_ago=1, url=shared), mk(days_ago=400, title="ancient")], "a", "A"),
        src([mk(days_ago=2, url=shared)], "b", "B"),
    ]
    index = bs.build_search_index(sources, NOW)
    assert len(index) == 1
    assert index[0]["url"] == shared
    assert index[0]["importance"] == "notice"
