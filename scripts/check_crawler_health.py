"""Post-deploy crawler health check — make silent failures visible.

Runs as the LAST step of the daily workflow (after the site is deployed, so a
failure here never blocks publishing). Reads every enabled source's update
JSON and:

  1. writes a per-source status table to the GitHub Actions run summary
     ($GITHUB_STEP_SUMMARY), and
  2. exits non-zero if ANY enabled source errored or has no data file,
     which turns the run red and triggers GitHub's failure notification —
     so a broken crawler gets noticed the same day instead of after 30.

Sources that succeeded but haven't updated in a while get a staleness warning
in the table (informational only; "no news from a slow source" is normal).

Usage:
    python scripts/check_crawler_health.py
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
UPDATES_DIR = DATA_DIR / "updates"

TAIPEI_TZ = timezone(timedelta(hours=8))
STALE_WARN_DAYS = 7  # warn (not fail) when last success is older than this


def check() -> tuple[list[dict], list[str]]:
    """Return (per-source rows, failure messages)."""
    with open(DATA_DIR / "sources.json", encoding="utf-8") as f:
        sources = json.load(f)
    now = datetime.now(TAIPEI_TZ)

    rows = []
    failures = []
    for meta in sources:
        if not meta.get("enabled"):
            continue
        source_id = meta["source_id"]
        path = UPDATES_DIR / f"{source_id}.json"
        if not path.exists():
            rows.append({"id": source_id, "status": "missing", "items": 0,
                         "last_success": "-", "note": "no data file"})
            failures.append(f"{source_id}: data file missing")
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        status = data.get("crawl_status", "unknown")
        last_success = (data.get("last_success_at") or "")[:10]
        note = ""
        if status != "success":
            note = (data.get("error_message") or "")[:120]
            failures.append(f"{source_id}: crawl_status={status} — {note}")
        else:
            try:
                age = (now - datetime.fromisoformat(data["last_success_at"])).days
                if age >= STALE_WARN_DAYS:
                    note = f"⚠️ last success {age} days ago"
            except (KeyError, TypeError, ValueError):
                note = "⚠️ no last_success_at"
        rows.append({"id": source_id, "status": status,
                     "items": len(data.get("items", [])),
                     "last_success": last_success, "note": note})
    return rows, failures


def write_github_summary(rows: list[dict], failures: list[str]) -> None:
    """Append a markdown table to the Actions run summary, if running in CI."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = ["## Crawler health", "",
             "| Source | Status | Items | Last success | Note |",
             "|---|---|---:|---|---|"]
    for r in rows:
        icon = "✅" if r["status"] == "success" else "❌"
        lines.append(
            f"| {r['id']} | {icon} {r['status']} | {r['items']} "
            f"| {r['last_success']} | {r['note']} |"
        )
    if failures:
        lines += ["", f"**{len(failures)} source(s) failing** — the site was "
                      "still deployed with the last-known-good data."]
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    rows, failures = check()
    write_github_summary(rows, failures)
    for r in rows:
        print(f"{r['id']:14s} {r['status']:8s} {r['items']:3d} items  "
              f"{r['last_success']}  {r['note']}")
    if failures:
        print(f"\nFAIL: {len(failures)} source(s) not healthy:", file=sys.stderr)
        for msg in failures:
            print(f"  - {msg}", file=sys.stderr)
        return 1
    print("\nall sources healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
