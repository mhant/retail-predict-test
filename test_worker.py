"""
M2 Worker test — verifies the deployed Cloudflare Worker is reachable,
authenticates correctly, and can write rows to D1.

Usage:
    WORKER_URL=https://retail-predict-worker.<subdomain>.workers.dev \
    WRITE_TOKEN=<your-token> \
    python test_worker.py
"""
from __future__ import annotations

import os
import sys
import time

import requests

WORKER_URL  = os.environ.get("WORKER_URL", "").rstrip("/")
WRITE_TOKEN = os.environ.get("WRITE_TOKEN", "")

if not WORKER_URL:
    print("ERROR: Set WORKER_URL env var to your deployed Worker URL.")
    sys.exit(1)
if not WRITE_TOKEN:
    print("ERROR: Set WRITE_TOKEN env var.")
    sys.exit(1)

_auth = {"Authorization": f"Bearer {WRITE_TOKEN}", "Content-Type": "application/json"}
results: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    icon = "✅" if ok else "❌"
    msg = f"  {icon} {name}"
    if detail:
        msg += f": {detail}"
    print(msg)
    results.append({"name": name, "ok": ok})
    return ok


print(f"\nWorker: {WORKER_URL}\n")

# ── Health check ──────────────────────────────────────────────────────────────
print("── Health check ──")
try:
    r = requests.get(f"{WORKER_URL}/health", timeout=10)
    data = r.json()
    check("GET /health returns 200", r.status_code == 200)
    check("Response ok=true",        data.get("ok") is True)
    check("DB reachable",            "db" in data, data.get("db", ""))
except Exception as exc:
    check("GET /health", False, str(exc))

# ── Auth checks ───────────────────────────────────────────────────────────────
print("\n── Auth ──")
try:
    r = requests.post(f"{WORKER_URL}/ingest", json={"table": "pipeline_runs", "rows": []}, timeout=10)
    check("No auth → 401", r.status_code == 401)
except Exception as exc:
    check("No auth → 401", False, str(exc))

try:
    r = requests.post(f"{WORKER_URL}/ingest",
                      json={"table": "pipeline_runs", "rows": []},
                      headers={"Authorization": "Bearer wrongtoken", "Content-Type": "application/json"},
                      timeout=10)
    check("Wrong token → 401", r.status_code == 401)
except Exception as exc:
    check("Wrong token → 401", False, str(exc))

# ── Write a pipeline_run row ──────────────────────────────────────────────────
print("\n── Write pipeline_run ──")
now = time.time()
try:
    r = requests.post(f"{WORKER_URL}/ingest", headers=_auth, timeout=15, json={
        "table": "pipeline_runs",
        "rows": [{
            "started_at": now,
            "finished_at": now + 5,
            "status": "completed",
            "triggered_by": "m2-test",
            "mentions_scraped": 42,
            "new_mentions": 10,
            "predictions_written": 6,
        }],
    })
    data = r.json()
    check("POST /ingest returns 200",         r.status_code == 200, str(data))
    check("ok=true",                           data.get("ok") is True)
    check("inserted=1",                        data.get("inserted") == 1, str(data.get("inserted")))
except Exception as exc:
    check("POST /ingest pipeline_run", False, str(exc))

# ── Write raw_mentions rows (with upvote scores) ─────────────────────────────
print("\n── Write raw_mentions (Reddit posts with scores) ──")
try:
    sample_mentions = [
        {
            "source": "pullpush_reddit", "source_id": f"test_{i}",
            "subreddit": "wallstreetbets", "ticker": "GME",
            "title": f"GME to the moon #{i}",
            "selftext": "This is a test post about GameStop",
            "author": f"test_user_{i}",
            "score": 1000 + i * 50,
            "ups": 1100 + i * 50,
            "upvote_ratio": 0.92,
            "num_comments": 250 + i,
            "created_utc": now - i * 3600,
            "scraped_utc": now,
        }
        for i in range(5)
    ]
    r = requests.post(f"{WORKER_URL}/ingest", headers=_auth, timeout=15, json={
        "table": "raw_mentions",
        "rows": sample_mentions,
    })
    data = r.json()
    check("POST /ingest raw_mentions 200",    r.status_code == 200, str(data))
    check("inserted=5",                        data.get("inserted") == 5, str(data.get("inserted")))
except Exception as exc:
    check("POST /ingest raw_mentions", False, str(exc))

# ── Dedup check — inserting same rows again should skip ──────────────────────
print("\n── Deduplication (INSERT OR IGNORE) ──")
try:
    r = requests.post(f"{WORKER_URL}/ingest", headers=_auth, timeout=15, json={
        "table": "raw_mentions",
        "rows": sample_mentions,   # same rows as above
    })
    data = r.json()
    check("Re-insert returns 200",   r.status_code == 200)
    check("inserted=0 (all skipped)", data.get("inserted") == 0, str(data))
except Exception as exc:
    check("Dedup check", False, str(exc))

# ── Unknown table rejected ────────────────────────────────────────────────────
print("\n── Security ──")
try:
    r = requests.post(f"{WORKER_URL}/ingest", headers=_auth, timeout=10, json={
        "table": "sqlite_master",
        "rows": [{"x": 1}],
    })
    check("Unknown table → 400", r.status_code == 400)
except Exception as exc:
    check("Unknown table → 400", False, str(exc))

# ── Summary ───────────────────────────────────────────────────────────────────
passed = sum(1 for r in results if r["ok"])
total  = len(results)
print(f"\n{'─'*40}")
print(f"  {passed}/{total} checks passed")

if passed < total:
    print("\nFAIL")
    sys.exit(1)

print("\n✅ M2 COMPLETE — Worker deployed, D1 writes confirmed, dedup working.")
print("   Ready to proceed to M3: adapt Python scraper to write to D1 via this Worker.")
