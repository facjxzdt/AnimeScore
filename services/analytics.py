"""Persistent observations, collection leases and user-selectable aggregation."""

import json
import sqlite3
import time
import uuid
from collections import Counter
from datetime import datetime, timezone

from services.ratings import PROVIDERS, weighted_score
from services.providers import DEFAULT_WEIGHTS

PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value else None


def anime_key(item):
    if item.get("history_key"):
        return item["history_key"]
    ids = item.get("ids", {})
    for provider, field in PROVIDERS.items():
        if ids.get(field):
            return f"{provider}:{ids[field]}"
    return f"catalog:{item['catalog_id']}"


class AnalyticsStore:
    def __init__(self, cache):
        self.cache = cache
        with cache.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS observations (
                    anime_key TEXT, bucket INTEGER, observed_at REAL NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(anime_key, bucket));
                CREATE TABLE IF NOT EXISTS tracked (
                    catalog_id TEXT PRIMARY KEY, expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS collection_state (
                    id INTEGER PRIMARY KEY CHECK(id=1), owner TEXT, lease_until REAL DEFAULT 0,
                    last_started REAL, last_finished REAL, next_run REAL DEFAULT 0,
                    completed INTEGER DEFAULT 0, total INTEGER DEFAULT 0,
                    failures INTEGER DEFAULT 0, error TEXT);
                INSERT OR IGNORE INTO collection_state(id) VALUES (1);
            """)

    def record(self, items, now=None):
        now = time.time() if now is None else now
        with self.cache.connect() as db:
            for item in items:
                states = item.get("score_status", {})
                timestamps = [datetime.fromisoformat(state["updated_at"]).timestamp()
                              for state in states.values() if state.get("updated_at") and state["status"] in {"ok", "no_score"}]
                if not timestamps:
                    continue
                observed = max(timestamps)
                if now - observed > 3600:
                    continue
                # Stale fallback scores are useful in a list but are not new observations.
                scores = {provider: item["scores"].get(provider) if states.get(provider, {}).get("status") == "ok" else None
                          for provider in PROVIDERS}
                votes = {provider: item.get("votes", {}).get(provider)
                         if states.get(provider, {}).get("status") in {"ok", "no_score"} else None
                         for provider in PROVIDERS}
                payload = {"scores": scores, "votes": votes, "source_times": states, "source_ids": item.get("ids", {})}
                db.execute("""INSERT INTO observations VALUES (?, ?, ?, ?)
                    ON CONFLICT(anime_key, bucket) DO UPDATE SET observed_at=excluded.observed_at, payload=excluded.payload
                    WHERE excluded.observed_at > observations.observed_at""",
                           (anime_key(item), int(observed // 3600), observed, json.dumps(payload)))
            db.execute("DELETE FROM observations WHERE observed_at < ?", (now - 400 * 86400,))

    def track(self, catalog_id):
        with self.cache.connect() as db:
            db.execute("INSERT OR REPLACE INTO tracked VALUES (?, ?)", (catalog_id, time.time() + 365 * 86400))

    def tracked(self):
        with self.cache.connect() as db:
            return {row[0] for row in db.execute("SELECT catalog_id FROM tracked WHERE expires_at > ?", (time.time(),))}

    def history(self, item, period, weights, now=None):
        now = time.time() if now is None else now
        start = now - PERIOD_DAYS[period] * 86400
        with self.cache.connect() as db:
            rows = db.execute("SELECT observed_at, payload FROM observations WHERE anime_key=? AND observed_at>=? AND observed_at<=? ORDER BY observed_at",
                              (anime_key(item), start, now)).fetchall()
            first = db.execute("SELECT MIN(observed_at) FROM observations WHERE anime_key=?", (anime_key(item),)).fetchone()[0]
        points = []
        for timestamp, raw in rows:
            data = json.loads(raw)
            scores = data["scores"]
            votes = data.get("votes", {})
            historical_ids = data.get("source_ids", item.get("base_ids", item.get("ids", {})))
            for provider, field in PROVIDERS.items():
                if historical_ids.get(field) != item.get("ids", {}).get(field):
                    scores[provider] = None
                    votes[provider] = None
            points.append({"timestamp": iso(timestamp), "scores": {**scores, "total": weighted_score(scores, weights)},
                           "votes": votes})
        # Long windows use the last real observation of each UTC day; never interpolate missing days.
        if period in {"90d", "1y"}:
            daily = {point["timestamp"][:10]: point for point in points}
            points = list(daily.values())
        return {"period": period, "points": points, "collected_since": iso(first), "weights": weights,
                "from": iso(start), "to": iso(now), "resolution": "day" if period in {"90d", "1y"} else "hour"}

    def claim(self, now=None, force=False):
        now = time.time() if now is None else now
        owner = uuid.uuid4().hex
        with self.cache.connect() as db:
            updated = db.execute("""UPDATE collection_state SET owner=?, lease_until=?, last_started=?,
                completed=0, total=0, failures=0, error=NULL WHERE id=1 AND lease_until<=? AND (next_run<=? OR ?)""",
                                 (owner, now + 300, now, now, now, force)).rowcount
        return owner if updated else None

    def progress(self, owner, completed, total, failures, now=None):
        now = time.time() if now is None else now
        with self.cache.connect() as db:
            return bool(db.execute("UPDATE collection_state SET completed=?, total=?, failures=?, lease_until=? WHERE id=1 AND owner=?",
                                   (completed, total, failures, now + 300, owner)).rowcount)

    def renew(self, owner):
        with self.cache.connect() as db:
            return bool(db.execute("UPDATE collection_state SET lease_until=? WHERE id=1 AND owner=?",
                                   (time.time() + 300, owner)).rowcount)

    def finish(self, owner, error=None, now=None):
        now = time.time() if now is None else now
        with self.cache.connect() as db:
            db.execute("""UPDATE collection_state SET lease_until=0, owner=NULL, last_finished=?,
                next_run=CASE WHEN ? IS NOT NULL THEN ? + 60 ELSE MAX(last_started + 3600, ? + 1) END,
                error=? WHERE id=1 AND owner=?""", (now, error, now, now, error, owner))

    def status(self):
        with self.cache.connect() as db:
            db.row_factory = sqlite3.Row
            row = dict(db.execute("SELECT * FROM collection_state WHERE id=1").fetchone())
            count, first = db.execute("SELECT COUNT(*), MIN(observed_at) FROM observations").fetchone()
        running = row["lease_until"] > time.time()
        return {"running": running, "last_started": iso(row["last_started"]), "last_finished": iso(row["last_finished"]),
                "next_run": iso(row["next_run"]), "completed": row["completed"], "total": row["total"],
                "failures": row["failures"], "error": row["error"], "observations": count, "collected_since": iso(first),
                "interval_seconds": 3600}


def rank_items(items, weights, min_platforms=1, min_votes=0):
    for item in items:
        item["scores"]["total"] = weighted_score(item["scores"], weights)
        item["coverage"] = sum(item["scores"].get(provider) is not None for provider in PROVIDERS)
        item["vote_count"] = sum(item.get("votes", {}).get(provider) or 0 for provider in PROVIDERS)
    visible = [item for item in items if item["coverage"] >= min_platforms and item["vote_count"] >= min_votes]
    visible.sort(key=lambda item: (-(item["scores"]["total"] if item["scores"]["total"] is not None else -1), -item["vote_count"], item["name"]))
    rank, previous = 0, None
    for index, item in enumerate(visible, 1):
        score = item["scores"]["total"]
        if score is not None and score != previous:
            rank = index
        item["rank"] = rank if score is not None else None
        previous = score
    return visible


def summarize(items):
    rated = [item for item in items if item["scores"].get("total") is not None]
    distribution = Counter(min(int(item["scores"]["total"]), 9) for item in rated)
    coverage = {provider: sum(item["scores"].get(provider) is not None for item in items) for provider in PROVIDERS}
    return {"total": len(items), "rated": len(rated), "average": round(sum(item["scores"]["total"] for item in rated) / len(rated), 2) if rated else None,
            "distribution": [{"range": f"{i}-{i+1}", "count": distribution[i]} for i in range(10)],
            "coverage": coverage, "votes": sum(item.get("vote_count", 0) for item in items)}
