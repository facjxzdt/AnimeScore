"""Resumable, single-owner mapping jobs with daily current-season discovery."""

import asyncio
import json
import os
import time
import uuid
from contextlib import suppress

from services.catalog import current_season
from services.mappings import MappingConflict


class FilmarksJobs:
    def __init__(self, mapper):
        self.mapper, self.cache = mapper, mapper.cache
        self.enabled = os.getenv("FILMARKS_AUTO_MAP", os.getenv("SCORE_AUTO_UPDATE", "1")).lower() in {"1", "true", "yes", "on"}
        with self.cache.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS filmarks_job (
                id INTEGER PRIMARY KEY CHECK(id=1), status TEXT, owner TEXT, lease REAL DEFAULT 0,
                cancelled INTEGER DEFAULT 0, next_auto REAL DEFAULT 0, payload TEXT)""")
            db.execute("INSERT OR IGNORE INTO filmarks_job(id, status, payload) VALUES (1, 'idle', '{}')")

    def status(self):
        with self.cache.connect() as db:
            status, cancelled, payload, next_auto = db.execute("SELECT status, cancelled, payload, next_auto FROM filmarks_job WHERE id=1").fetchone()
        result = json.loads(payload)
        result.pop("ids", None)
        return {**result, "status": status, "cancel_requested": bool(cancelled), "automatic": self.enabled, "next_auto": next_auto,
                "current_year": current_season()[0], "current_season": current_season()[1]}

    def start(self, items, *, apply=True, force=False, automatic=False, limit=100):
        mapped = self.mapper.store.apply(items)
        ids = [item["catalog_id"] for item in mapped if item.get("mapping_sources", {}).get("filmarks") == "missing"][:limit]
        payload = {"ids": ids, "apply": apply, "force": force, "total": len(ids), "completed": 0,
                   "counts": {}, "recent": [], "created_at": time.time(), "started_at": None, "finished_at": None, "error": None}
        with self.cache.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            status, next_auto = db.execute("SELECT status, next_auto FROM filmarks_job WHERE id=1").fetchone()
            if status in {"queued", "running"}:
                raise MappingConflict("已有自动映射任务正在运行")
            if automatic and next_auto > time.time():
                return self.status()
            db.execute("UPDATE filmarks_job SET status=?, owner=NULL, lease=0, cancelled=0, payload=?, next_auto=? WHERE id=1",
                       ("queued" if ids else "completed", json.dumps(payload), max(next_auto, time.time() + 86400)))
        return self.status()

    def cancel(self):
        with self.cache.connect() as db:
            db.execute("UPDATE filmarks_job SET cancelled=1 WHERE id=1 AND status IN ('queued','running')")
        return self.status()

    def _claim(self):
        owner = uuid.uuid4().hex
        with self.cache.connect() as db:
            changed = db.execute("UPDATE filmarks_job SET status='running', owner=?, lease=? WHERE id=1 AND (status='queued' OR (status='running' AND lease<?))",
                                 (owner, time.time() + 90, time.time())).rowcount
            row = db.execute("SELECT payload FROM filmarks_job WHERE id=1").fetchone()
        return (owner, json.loads(row[0])) if changed else (None, None)

    def _renew(self, owner):
        with self.cache.connect() as db:
            return bool(db.execute("UPDATE filmarks_job SET lease=? WHERE id=1 AND owner=? AND status='running'", (time.time() + 90, owner)).rowcount)

    def _cancelled(self, owner):
        with self.cache.connect() as db:
            row = db.execute("SELECT cancelled FROM filmarks_job WHERE id=1 AND owner=?", (owner,)).fetchone()
        return row is None or bool(row[0])

    def _progress(self, owner, payload, status="running"):
        with self.cache.connect() as db:
            db.execute("UPDATE filmarks_job SET payload=?, status=?, lease=? WHERE id=1 AND owner=?",
                       (json.dumps(payload), status, time.time() + 90 if status == "running" else 0, owner))

    async def run_once(self):
        owner, payload = await asyncio.to_thread(self._claim)
        if not owner:
            return False
        async def heartbeat():
            while True:
                await asyncio.sleep(20)
                if not await asyncio.to_thread(self._renew, owner):
                    return
        task = asyncio.create_task(heartbeat())
        status = "completed"
        try:
            entries = {item["catalog_id"]: item for item in self.mapper.repository.snapshot().entries}
            payload["started_at"] = payload.get("started_at") or time.time()
            for identifier in payload["ids"][payload["completed"]:]:
                if await asyncio.to_thread(self._cancelled, owner):
                    status = "cancelled"
                    break
                item = entries.get(identifier)
                payload["current"] = item["name"] if item else identifier
                await asyncio.to_thread(self._progress, owner, payload)
                result = await self.mapper.discover(item, apply=payload["apply"], force=payload["force"]) if item else {"status": "skipped"}
                state = result["status"]
                payload["counts"][state] = payload["counts"].get(state, 0) + 1
                payload["completed"] += 1
                payload["recent"] = [{"catalog_id": identifier, "name": (item.get("name_cn") or item["name"]) if item else identifier, "status": state}, *payload["recent"]][:12]
                await asyncio.to_thread(self._progress, owner, payload)
                if self.mapper.ratings.blocked_until["filmarks"] > time.time():
                    status = "failed"
                    payload["error"] = "Filmarks 访问受限，任务已停止；冷却后可重新启动。"
                    break
        except asyncio.CancelledError:
            # Leave the saved cursor queued for the next process after shutdown.
            await asyncio.to_thread(self._progress, owner, payload, "queued")
            raise
        except Exception as exc:
            status, payload["error"] = "failed", str(exc)[:250]
        else:
            payload["current"] = None
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        payload["finished_at"] = time.time()
        await asyncio.to_thread(self._progress, owner, payload, status)
        return True

    async def run(self):
        while True:
            state = await asyncio.to_thread(self.status)
            if self.enabled and state["status"] not in {"queued", "running"} and state["next_auto"] <= time.time():
                try:
                    items = self.mapper.repository.snapshot().season(*current_season())
                    await asyncio.to_thread(self.start, items, automatic=True, limit=250)
                except MappingConflict:
                    pass
            await self.run_once()
            await asyncio.sleep(5)
