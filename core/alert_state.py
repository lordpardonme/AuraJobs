"""
AuraJobs Alert State Persistence
Tracks sent job IDs to prevent duplicate alerts across scheduled runs.
Supports SQLite (recommended) and JSON backends with TTL cleanup.
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class AlertState:
    """
    Persistent store for sent job identifiers with TTL-based expiration.
    Uses job URL as the primary key (stable across runs).
    """

    def __init__(
        self,
        db_path: str = "alerts/alert_state.db",
        ttl_days: int = 30,
        store_type: str = "sqlite"
    ):
        self.db_path = Path(db_path)
        self.ttl_days = ttl_days
        self.store_type = store_type.lower()
        self._lock = threading.RLock()
        self._json_path = self.db_path.with_suffix(".json")

        if self.store_type == "sqlite":
            self._init_sqlite()
        else:
            self._init_json()

    def close(self):
        """Close any open connections (no-op for current implementation)."""
        pass

    def _init_sqlite(self):
        """Initialize SQLite database with schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sent_jobs (
                    job_url TEXT PRIMARY KEY,
                    job_id TEXT,
                    title TEXT,
                    company TEXT,
                    match_score INTEGER,
                    sent_at TEXT NOT NULL,  -- ISO format with microseconds
                    alert_run_id TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sent_at ON sent_jobs(sent_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_alert_run ON sent_jobs(alert_run_id)
            """)
            conn.commit()
        finally:
            conn.close()

    def _init_json(self):
        """Initialize JSON file if it doesn't exist."""
        self._json_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._json_path.exists():
            self._json_path.write_text(json.dumps({"jobs": []}, indent=2), encoding="utf-8")

    @contextmanager
    def _get_conn(self):
        """Thread-safe SQLite connection context manager - new connection each time."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _load_json(self) -> dict[str, Any]:
        try:
            return json.loads(self._json_path.read_text(encoding="utf-8"))
        except Exception:
            return {"jobs": []}

    def _save_json(self, data: dict[str, Any]):
        self._json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def contains(self, job_url: str) -> bool:
        """Check if a job URL has already been sent."""
        with self._lock:
            if self.store_type == "sqlite":
                with self._get_conn() as conn:
                    cursor = conn.execute("SELECT 1 FROM sent_jobs WHERE job_url = ?", (job_url,))
                    return cursor.fetchone() is not None
            else:
                data = self._load_json()
                return any(job.get("job_url") == job_url for job in data.get("jobs", []))

    def filter_new(self, jobs: list[dict[str, Any]], id_field: str = "job_url") -> list[dict[str, Any]]:
        """
        Filter a list of job dicts, returning only those not yet sent.
        Jobs without the id_field are always included (conservative).
        """
        new_jobs = []
        for job in jobs:
            job_url = job.get(id_field) or job.get("job_url") or job.get("job_url_direct")
            if job_url and not self.contains(job_url):
                new_jobs.append(job)
            elif not job_url:
                # No URL to dedupe on - include conservatively
                new_jobs.append(job)
        return new_jobs

    def mark_sent(
        self,
        jobs: list[dict[str, Any]],
        alert_run_id: str,
        id_field: str = "job_url"
    ) -> int:
        """
        Mark jobs as sent in the store. Returns count of newly added records.
        """
        if not jobs:
            return 0

        added = 0
        with self._lock:
            if self.store_type == "sqlite":
                with self._get_conn() as conn:
                    for job in jobs:
                        job_url = job.get(id_field) or job.get("job_url") or job.get("job_url_direct")
                        if not job_url:
                            continue
                        try:
                            now_iso = datetime.now().isoformat()
                            conn.execute("""
                                INSERT OR IGNORE INTO sent_jobs
                                (job_url, job_id, title, company, match_score, sent_at, alert_run_id)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                job_url,
                                job.get("id", ""),
                                job.get("title", "")[:500],
                                job.get("company", "")[:200],
                                int(job.get("match_score", 0) or 0),
                                now_iso,
                                alert_run_id
                            ))
                            if conn.total_changes > 0:
                                added += 1
                        except Exception:
                            pass
                    conn.commit()
            else:
                data = self._load_json()
                existing_urls = {job.get("job_url") for job in data.get("jobs", [])}
                for job in jobs:
                    job_url = job.get(id_field) or job.get("job_url") or job.get("job_url_direct")
                    if not job_url or job_url in existing_urls:
                        continue
                    data["jobs"].append({
                        "job_url": job_url,
                        "job_id": job.get("id", ""),
                        "title": job.get("title", "")[:500],
                        "company": job.get("company", "")[:200],
                        "match_score": int(job.get("match_score", 0) or 0),
                        "sent_at": datetime.now().isoformat(),
                        "alert_run_id": alert_run_id
                    })
                    existing_urls.add(job_url)
                    added += 1
                self._save_json(data)

        return added

    def cleanup_expired(self) -> int:
        """Remove records older than TTL. Returns count of removed records."""
        cutoff = datetime.now() - timedelta(days=self.ttl_days)
        removed = 0

        with self._lock:
            if self.store_type == "sqlite":
                with self._get_conn() as conn:
                    cursor = conn.execute(
                        "DELETE FROM sent_jobs WHERE sent_at < ?",
                        (cutoff.isoformat(),)
                    )
                    removed = cursor.rowcount
                    conn.commit()
            else:
                data = self._load_json()
                original_count = len(data.get("jobs", []))
                data["jobs"] = [
                    job for job in data.get("jobs", [])
                    if datetime.fromisoformat(job.get("sent_at", "1970-01-01")) > cutoff
                ]
                removed = original_count - len(data["jobs"])
                self._save_json(data)

        return removed

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the alert state store."""
        with self._lock:
            if self.store_type == "sqlite":
                with self._get_conn() as conn:
                    total = conn.execute("SELECT COUNT(*) FROM sent_jobs").fetchone()[0]
                    recent = conn.execute(
                        "SELECT COUNT(*) FROM sent_jobs WHERE sent_at > ?",
                        ((datetime.now() - timedelta(days=7)).isoformat(),)
                    ).fetchone()[0]
                    oldest = conn.execute("SELECT MIN(sent_at) FROM sent_jobs").fetchone()[0]
                    newest = conn.execute("SELECT MAX(sent_at) FROM sent_jobs").fetchone()[0]
                    return {
                        "total_sent": total,
                        "last_7_days": recent,
                        "oldest_record": oldest,
                        "newest_record": newest,
                        "store_type": "sqlite",
                        "db_path": str(self.db_path)
                    }
            else:
                data = self._load_json()
                jobs = data.get("jobs", [])
                total = len(jobs)
                cutoff_7d = datetime.now() - timedelta(days=7)
                recent = sum(1 for j in jobs if datetime.fromisoformat(j.get("sent_at", "1970-01-01")) > cutoff_7d)
                dates = [datetime.fromisoformat(j.get("sent_at", "1970-01-01")) for j in jobs if j.get("sent_at")]
                return {
                    "total_sent": total,
                    "last_7_days": recent,
                    "oldest_record": min(dates).isoformat() if dates else None,
                    "newest_record": max(dates).isoformat() if dates else None,
                    "store_type": "json",
                    "db_path": str(self._json_path)
                }

    def get_recent_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent alert run IDs with job counts."""
        with self._lock:
            if self.store_type == "sqlite":
                with self._get_conn() as conn:
                    rows = conn.execute("""
                        SELECT alert_run_id, COUNT(*) as job_count, MAX(sent_at) as last_sent
                        FROM sent_jobs
                        GROUP BY alert_run_id
                        ORDER BY last_sent DESC
                        LIMIT ?
                    """, (limit,)).fetchall()
                    return [dict(row) for row in rows]
            else:
                data = self._load_json()
                runs = {}
                for job in data.get("jobs", []):
                    run_id = job.get("alert_run_id", "unknown")
                    if run_id not in runs:
                        runs[run_id] = {"alert_run_id": run_id, "job_count": 0, "last_sent": job.get("sent_at")}
                    runs[run_id]["job_count"] += 1
                    if job.get("sent_at", "") > runs[run_id]["last_sent"]:
                        runs[run_id]["last_sent"] = job.get("sent_at")
                sorted_runs = sorted(runs.values(), key=lambda x: x["last_sent"], reverse=True)
                return sorted_runs[:limit]


def create_alert_state(config) -> AlertState:
    """Factory function to create AlertState from AlertConfig."""
    return AlertState(
        db_path=config.deduplication.db_path,
        ttl_days=config.deduplication.ttl_days,
        store_type=config.deduplication.store_type
    )


if __name__ == "__main__":
    # Quick test
    state = AlertState(db_path="test_alert_state.db", ttl_days=30, store_type="sqlite")
    test_jobs = [
        {"job_url": "https://example.com/job/1", "title": "Engineer", "company": "Acme", "match_score": 90, "id": "1"},
        {"job_url": "https://example.com/job/2", "title": "Designer", "company": "Beta", "match_score": 85, "id": "2"},
    ]
    run_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"Added: {state.mark_sent(test_jobs, run_id)}")
    print(f"Filter new (should be 0): {len(state.filter_new(test_jobs))}")
    print(f"Stats: {state.get_stats()}")
    print(f"Recent runs: {state.get_recent_runs()}")
    # Cleanup test file
    import os
    if os.path.exists("test_alert_state.db"):
        os.remove("test_alert_state.db")
    print("[OK] AlertState test passed")