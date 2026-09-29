"""Durable user submissions, shared review cache, and atomic daily error quota."""

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException

from services.analytics import AnalyticsStore
from services.catalog import CATALOG_TZ
from services.llm_review import ModelReviewer
from services.mapping_evidence import MappingEvidence
from services.mappings import MappingConflict, MappingStore, identity
from services.providers import PROVIDERS, normalize_id, site_url
from services.ratings import merge_ratings


def today(now=None):
    return datetime.fromtimestamp(time.time() if now is None else now, CATALOG_TZ).date().isoformat()


class Contributions:
    def __init__(self, repository, ratings):
        self.repository, self.ratings, self.cache = repository, ratings, ratings.cache
        self.mappings, self.analytics = MappingStore(self.cache), AnalyticsStore(self.cache)
        self.evidence, self.reviewer = MappingEvidence(ratings), ModelReviewer(ratings.client)
        with self.cache.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS contributions (
                    id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, username TEXT NOT NULL, catalog_id TEXT NOT NULL,
                    entity TEXT NOT NULL, provider TEXT NOT NULL, identifier TEXT NOT NULL, status TEXT NOT NULL,
                    day TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    owner TEXT, lease REAL DEFAULT 0, reason TEXT, decision TEXT, evidence TEXT, cache_key TEXT NOT NULL,
                    score_status TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS one_submission_per_user ON contributions(user_id) WHERE status IN ('queued','reviewing');
                CREATE UNIQUE INDEX IF NOT EXISTS one_review_per_mapping ON contributions(entity,provider) WHERE status IN ('queued','reviewing');
                CREATE INDEX IF NOT EXISTS contributions_user_date ON contributions(user_id, created_at);
                CREATE TABLE IF NOT EXISTS mapping_review_cache (key TEXT PRIMARY KEY, expires_at REAL NOT NULL, decision TEXT NOT NULL, evidence TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS contribution_errors (
                    user_id INTEGER, day TEXT, entity TEXT, provider TEXT, identifier TEXT,
                    PRIMARY KEY(user_id,day,entity,provider,identifier));
            """)

    def quota(self, user_id, now=None):
        day = today(now)
        with self.cache.connect() as db:
            used = db.execute("SELECT COUNT(*) FROM contribution_errors WHERE user_id=? AND day=?", (user_id, day)).fetchone()[0]
            busy = bool(db.execute("SELECT 1 FROM contributions WHERE user_id=? AND status IN ('queued','reviewing')", (user_id,)).fetchone())
        reset = datetime.fromisoformat(day).replace(tzinfo=CATALOG_TZ) + timedelta(days=1)
        return {"limit": 5, "errors": used, "remaining": max(0, 5 - used), "day": day, "resets_at": reset.isoformat(), "pending": busy}

    @staticmethod
    def public(row):
        value = dict(row)
        for field in ("owner", "lease", "cache_key", "entity"):
            value.pop(field, None)
        for field in ("decision", "evidence"):
            value[field] = json.loads(value[field]) if value[field] else None
        value["url"] = site_url(value["provider"], value["identifier"])
        return value

    def list(self, user_id=None, *, offset=0, catalog_id=None):
        with self.cache.connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("""SELECT * FROM contributions WHERE (? IS NULL OR user_id=?)
                AND (? IS NULL OR catalog_id=?) ORDER BY created_at DESC LIMIT 50 OFFSET ?""",
                              (user_id, user_id, catalog_id, catalog_id, offset)).fetchall()
        return [self.public(row) for row in rows]

    def get(self, submission_id, user_id=None):
        with self.cache.connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM contributions WHERE id=? AND (? IS NULL OR user_id=?)", (submission_id, user_id, user_id)).fetchone()
        if not row:
            raise HTTPException(404, "投稿不存在")
        return self.public(row)

    def submit(self, user, item, provider, raw_id):
        if not self.reviewer.enabled:
            raise HTTPException(503, "映射审核服务尚未配置")
        try:
            identifier = normalize_id(provider, raw_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        mapped = self.mappings.apply(self.repository.snapshot().entries)
        current = next(value for value in mapped if value["catalog_id"] == item["catalog_id"])
        if current["mapping_sources"][provider] != "missing":
            raise HTTPException(409, "该站点已有映射或已被管理员禁用")
        if any(value["ids"].get(PROVIDERS[provider]) == identifier for value in mapped):
            raise HTTPException(409, "该 ID 已关联其他动画，请联系管理员核对")
        now, day, entity = time.time(), today(), identity(item)
        submission_id = uuid.uuid4().hex
        try:
            with self.cache.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                previous = db.execute("""SELECT id,status,created_at FROM contributions WHERE user_id=? AND entity=? AND provider=?
                    AND identifier=? AND day=? ORDER BY created_at DESC LIMIT 1""", (user["id"], entity, provider, identifier, day)).fetchone()
                if previous and (previous[1] in {"queued", "reviewing", "rejected", "uncertain"} or now - previous[2] < 30):
                    submission_id = previous[0]
                else:
                    count = db.execute("SELECT COUNT(*) FROM contribution_errors WHERE user_id=? AND day=?", (user["id"], day)).fetchone()[0]
                    if count >= 5:
                        raise HTTPException(429, "今日五次错误机会已用完，请在北京时间零点后再提交")
                    last = db.execute("SELECT MAX(created_at) FROM contributions WHERE user_id=?", (user["id"],)).fetchone()[0]
                    if last and now - last < 30:
                        raise HTTPException(429, "请间隔 30 秒后再提交")
                    db.execute("""INSERT INTO contributions(id,user_id,username,catalog_id,entity,provider,identifier,status,day,
                        created_at,updated_at,cache_key) VALUES (?,?,?,?,?,?,?,'queued',?,?,?,?)""",
                               (submission_id, user["id"], user["username"], item["catalog_id"], entity, provider, identifier, day, now, now,
                                self.reviewer.cache_key(item, provider, identifier)))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "您或该动画仍有一项投稿正在审核，请等待结果") from None
        return self.get(submission_id, user["id"])

    def _claim(self):
        now, owner = time.time(), uuid.uuid4().hex
        with self.cache.connect() as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE contributions SET status='error',reason='审核中断，未扣除错误次数，可重试',updated_at=?,lease=0 WHERE status='reviewing' AND lease<?", (now, now))
            db.execute("UPDATE contributions SET score_status='pending' WHERE status='accepted' AND score_status='collecting' AND lease<?", (now,))
            if db.execute("SELECT 1 FROM contributions WHERE (status='reviewing' OR score_status='collecting') AND lease>?", (now,)).fetchone():
                return None
            row = db.execute("SELECT * FROM contributions WHERE status='accepted' AND score_status='pending' ORDER BY created_at LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE contributions SET score_status='collecting',owner=?,lease=? WHERE id=?", (owner, now + 180, row["id"]))
                return {**dict(row), "owner": owner, "status": "accepted"}
            row = db.execute("SELECT * FROM contributions WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("UPDATE contributions SET status='reviewing',owner=?,lease=?,updated_at=? WHERE id=?", (owner, now + 180, now, row["id"]))
            return {**dict(row), "owner": owner, "status": "reviewing"}

    def _error(self, job, reason, status="error"):
        with self.cache.connect() as db:
            db.execute("UPDATE contributions SET status=?,reason=?,updated_at=?,lease=0 WHERE id=? AND owner=? AND status='reviewing'",
                       (status, reason, time.time(), job["id"], job["owner"]))

    def _complete(self, job, item, decision, evidence):
        status = {"match": "accepted", "mismatch": "rejected", "uncertain": "uncertain"}[decision["verdict"]]
        with self.cache.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM contributions WHERE id=? AND owner=? AND status='reviewing'", (job["id"], job["owner"])).fetchone():
                return
            # Recheck inside the same transaction that commits the mapping and attribution.
            snapshot = self.mappings._snapshot(db)
            current = self.mappings._apply(item, snapshot)
            if current["mapping_sources"][job["provider"]] != "missing":
                status = "conflict"
            if status == "accepted":
                credit = {"bgm_id": job["user_id"], "username": job["username"], "profile_url": f"https://bgm.tv/user/{job['user_id']}"}
                db.execute("SAVEPOINT accept_mapping")
                try:
                    self.mappings.save(item, {job["provider"]: {"mode": "manual", "id": job["identifier"], "note": "用户投稿，模型审核通过"}},
                                       current["mapping_revision"], self.repository.snapshot().entries, source="community", contributor=credit, connection=db)
                except MappingConflict:
                    db.execute("ROLLBACK TO accept_mapping")
                    status = "conflict"
                finally:
                    db.execute("RELEASE accept_mapping")
            if status == "rejected":
                db.execute("INSERT OR IGNORE INTO contribution_errors VALUES (?,?,?,?,?)", (job["user_id"], job["day"], job["entity"], job["provider"], job["identifier"]))
            reason = "映射已发生变化，请刷新条目；未扣除错误次数" if status == "conflict" else decision["reason"]
            db.execute("UPDATE contributions SET status=?,reason=?,decision=?,evidence=?,score_status=?,updated_at=?,lease=0 WHERE id=?",
                       (status, reason, json.dumps(decision), json.dumps(evidence), "pending" if status == "accepted" else None, time.time(), job["id"]))

    async def _collect(self, job, item):
        status = "unavailable"
        try:
            await asyncio.to_thread(self.analytics.track, item["catalog_id"])
            current = self.mappings.apply([item])[0]
            if current["ids"].get(PROVIDERS[job["provider"]]) != job["identifier"]:
                status = "mapping_changed"
            elif self.ratings.blocked_until[job["provider"]] <= time.time():
                rating = await asyncio.wait_for(self.ratings.get(job["provider"], job["identifier"]), timeout=35)
                status = rating["status"]
                await asyncio.to_thread(self.analytics.record, [merge_ratings(current, self.cache.all())])
        except asyncio.CancelledError:
            with self.cache.connect() as db:
                db.execute("UPDATE contributions SET score_status='pending',lease=0 WHERE id=? AND owner=?", (job["id"], job["owner"]))
            raise
        except Exception:
            pass
        with self.cache.connect() as db:
            db.execute("UPDATE contributions SET score_status=?,updated_at=?,lease=0 WHERE id=? AND owner=?", (status, time.time(), job["id"], job["owner"]))

    async def run_once(self):
        job = await asyncio.to_thread(self._claim)
        if not job:
            return False
        item = next((value for value in self.repository.snapshot().entries if value["catalog_id"] == job["catalog_id"]), None)
        if not item:
            if job["status"] == "accepted":
                with self.cache.connect() as db:
                    db.execute("UPDATE contributions SET score_status='mapping_changed',lease=0 WHERE id=?", (job["id"],))
            else:
                await asyncio.to_thread(self._error, job, "目录条目已变更，请重新查找后提交；未扣次数", "conflict")
            return True
        if job["status"] == "accepted":
            await self._collect(job, item)
            return True
        try:
            current = self.mappings.apply([item])[0]
            if current["mapping_sources"][job["provider"]] != "missing":
                await asyncio.to_thread(self._error, job, "该站点已有映射；未扣除错误次数", "conflict")
                return True
            review_key = self.reviewer.cache_key(item, job["provider"], job["identifier"])
            with self.cache.connect() as db:
                db.execute("UPDATE contributions SET cache_key=? WHERE id=? AND owner=? AND status='reviewing'", (review_key, job["id"], job["owner"]))
                cached = db.execute("SELECT decision,evidence FROM mapping_review_cache WHERE key=? AND expires_at>?", (review_key, time.time())).fetchone()
            if cached:
                decision, evidence = map(json.loads, cached)
            else:
                evidence = await self.evidence.get(job["provider"], job["identifier"])
                decision = await self.reviewer.review(item, evidence)
                with self.cache.connect() as db:
                    db.execute("INSERT OR REPLACE INTO mapping_review_cache VALUES (?,?,?,?)", (review_key, time.time() + (86400 if decision["verdict"] == "uncertain" else 7 * 86400), json.dumps(decision), json.dumps(evidence)))
            await asyncio.to_thread(self._complete, job, item, decision, evidence)
        except asyncio.CancelledError:
            await asyncio.to_thread(self._error, job, "审核中断，未扣除错误次数，可重试")
            raise
        except Exception:
            # Never return upstream bodies, model credentials or OAuth tokens in errors.
            await asyncio.to_thread(self._error, job, "站点资料或模型审核暂不可用，未扣除错误次数，可稍后重试")
        return True

    async def run(self):
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                logging.getLogger(__name__).warning("Submission worker will retry after storage error: %s", type(exc).__name__)
                await asyncio.sleep(5)
            await asyncio.sleep(1)

    def approve(self, submission_id, actor):
        with self.cache.connect() as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM contributions WHERE id=?", (submission_id,)).fetchone()
            if not row:
                raise HTTPException(404, "投稿不存在")
            if row["status"] not in {"uncertain", "error", "rejected"}:
                raise HTTPException(409, "此投稿不能再次审核，请刷新记录")
            item = next((value for value in self.repository.snapshot().entries if value["catalog_id"] == row["catalog_id"]), None)
            if not item:
                raise HTTPException(409, "目录条目已变更")
            current = self.mappings._apply(item, self.mappings._snapshot(db))
            credit = {"bgm_id": row["user_id"], "username": row["username"], "profile_url": f"https://bgm.tv/user/{row['user_id']}"}
            try:
                self.mappings.save(item, {row["provider"]: {"mode": "manual", "id": row["identifier"], "note": f"用户投稿，管理员 {actor} 确认"}},
                                   current["mapping_revision"], self.repository.snapshot().entries, source="community", contributor=credit, connection=db)
            except MappingConflict as exc:
                raise HTTPException(409, str(exc)) from None
            db.execute("DELETE FROM contribution_errors WHERE user_id=? AND day=? AND entity=? AND provider=? AND identifier=?",
                       (row["user_id"], row["day"], row["entity"], row["provider"], row["identifier"]))
            db.execute("DELETE FROM mapping_review_cache WHERE key=?", (row["cache_key"],))
            db.execute("UPDATE contributions SET status='accepted',reason=?,score_status='pending',updated_at=? WHERE id=?",
                       (f"管理员 {actor} 已确认", time.time(), submission_id))
        return self.get(submission_id)
