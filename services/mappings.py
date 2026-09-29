"""Manual overrides are stored separately from the upstream catalog."""

import copy
import json
import sqlite3
import time
from contextlib import nullcontext

from services.providers import PROVIDERS, SITES, normalize_id, site_url


class MappingConflict(ValueError):
    pass


def identity(item):
    for provider, field in PROVIDERS.items():
        if item.get("ids", {}).get(field):
            return f"{provider}:{item['ids'][field]}"
    return f"catalog:{item['catalog_id']}"


class MappingStore:
    def __init__(self, cache):
        self.cache = cache
        with cache.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS mapping_entities (
                    entity TEXT PRIMARY KEY, catalog_id TEXT NOT NULL,
                    anchors TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS mapping_overrides (
                    entity TEXT NOT NULL, provider TEXT NOT NULL, identifier TEXT,
                    note TEXT NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY(entity, provider));
                CREATE UNIQUE INDEX IF NOT EXISTS unique_manual_site_id
                    ON mapping_overrides(provider, identifier) WHERE identifier IS NOT NULL;
                CREATE TABLE IF NOT EXISTS mapping_audit (
                    id INTEGER PRIMARY KEY, entity TEXT NOT NULL, created_at REAL NOT NULL,
                    before_json TEXT NOT NULL, after_json TEXT NOT NULL);
            """)
            db.execute("BEGIN IMMEDIATE")
            if "source" not in {row[1] for row in db.execute("PRAGMA table_info(mapping_overrides)")}:
                db.execute("ALTER TABLE mapping_overrides ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
            if "contributor" not in {row[1] for row in db.execute("PRAGMA table_info(mapping_overrides)")}:
                db.execute("ALTER TABLE mapping_overrides ADD COLUMN contributor TEXT")

    def _snapshot(self, db):
        entities, aliases, overrides = {}, {}, {}
        for entity, catalog_id, anchors, revision in db.execute("SELECT * FROM mapping_entities"):
            entities[entity] = {"entity": entity, "catalog_id": catalog_id, "revision": revision}
            aliases[f"catalog:{catalog_id}"] = entity
            for field, value in json.loads(anchors).items():
                aliases[f"{field}:{value}"] = entity
        for entity, provider, identifier, note, updated, source, contributor in db.execute("SELECT entity, provider, identifier, note, updated_at, source, contributor FROM mapping_overrides"):
            overrides.setdefault(entity, {})[provider] = {"id": identifier, "note": note, "updated_at": updated, "source": source,
                                                         "contributor": json.loads(contributor) if contributor else None}
        return entities, aliases, overrides

    @staticmethod
    def _entity(item, snapshot):
        entities, aliases, _ = snapshot
        key = aliases.get(f"catalog:{item['catalog_id']}")
        if not key:
            key = next((aliases[f"{field}:{value}"] for field, value in item.get("ids", {}).items()
                        if f"{field}:{value}" in aliases), identity(item))
        return entities.get(key, {"entity": key, "catalog_id": item["catalog_id"], "revision": 0})

    def _apply(self, item, snapshot):
        if not item.get("catalog_id"):
            return copy.deepcopy(item)
        result = copy.deepcopy(item)
        entity = self._entity(item, snapshot)
        overrides = snapshot[2].get(entity["entity"], {})
        result["history_key"] = entity["entity"]
        result["base_ids"] = dict(item.get("ids", {}))
        result["mapping_sources"] = {}
        result["mapping_contributors"] = {}
        result["mapping_revision"] = entity["revision"]
        for provider, field in PROVIDERS.items():
            override = overrides.get(provider)
            if override is not None:
                result["ids"].pop(field, None)
                result["scores"].pop(provider, None)
                result["sites"] = [site for site in result.get("sites", []) if site["site"] != SITES[provider]["site"]]
                if override["id"]:
                    result["ids"][field] = override["id"]
                    result["sites"].append({"site": SITES[provider]["site"], "id": override["id"],
                                            "url": site_url(provider, override["id"]), "title": SITES[provider]["name"],
                                            "type": "info", "regions": []})
                result["mapping_sources"][provider] = override["source"] if override["id"] else "disabled"
                if override["id"] and override.get("contributor"):
                    result["mapping_contributors"][provider] = override["contributor"]
            else:
                result["mapping_sources"][provider] = "catalog" if result["ids"].get(field) else "missing"
        return result

    def apply(self, items):
        with self.cache.connect() as db:
            snapshot = self._snapshot(db)
        return [self._apply(item, snapshot) if "base_ids" not in item else copy.deepcopy(item) for item in items]

    def detail(self, item):
        with self.cache.connect() as db:
            snapshot = self._snapshot(db)
            entity = self._entity(item, snapshot)
            audit = [{"id": row[0], "timestamp": row[1], "before": json.loads(row[2]), "after": json.loads(row[3])}
                     for row in db.execute("SELECT id, created_at, before_json, after_json FROM mapping_audit WHERE entity=? ORDER BY id DESC LIMIT 30", (entity["entity"],))]
        return {"item": self._apply(item, snapshot), "revision": entity["revision"],
                "overrides": snapshot[2].get(entity["entity"], {}), "audit": audit}

    def save(self, item, changes, revision, catalog_entries, *, source="manual", contributor=None, connection=None):
        if source not in {"manual", "auto", "community"}:
            raise ValueError("Unknown mapping source")
        if source == "community" and not contributor:
            raise ValueError("Community mappings require a verified contributor")
        normalized = {}
        for provider, change in changes.items():
            if provider not in PROVIDERS or change["mode"] not in {"catalog", "manual", "disabled"}:
                raise ValueError("映射设置不正确")
            normalized[provider] = {**change, "id": normalize_id(provider, change.get("id", "")) if change["mode"] == "manual" else None}
        try:
            with (self.cache.connect() if connection is None else nullcontext(connection)) as db:
                if connection is None:
                    db.execute("BEGIN IMMEDIATE")
                snapshot = self._snapshot(db)
                entity = self._entity(item, snapshot)
                if revision != entity["revision"]:
                    raise MappingConflict("映射已被其他窗口修改，请重新加载后保存")
                before = snapshot[2].get(entity["entity"], {})
                current_ids = self._apply(item, snapshot)["ids"]
                if source in {"auto", "community"} and any(p in before or current_ids.get(PROVIDERS[p]) for p in normalized):
                    raise MappingConflict("自动或用户提交映射不能覆盖已有映射或人工禁用设置")
                effective = current_ids.copy()
                for provider, change in normalized.items():
                    field = PROVIDERS[provider]
                    effective[field] = item["ids"].get(field) if change["mode"] == "catalog" else change["id"]
                for other in catalog_entries:
                    if self._entity(other, snapshot)["entity"] == entity["entity"]:
                        continue
                    other_ids = self._apply(other, snapshot)["ids"] if snapshot[2] else other["ids"]
                    for provider in normalized:
                        field = PROVIDERS[provider]
                        if effective.get(field) == current_ids.get(field):
                            continue
                        if effective.get(field) and other_ids.get(field) == effective[field]:
                            raise MappingConflict(f"{SITES[provider]['name']} ID 已属于 {other.get('name_cn') or other['name']}")
                db.execute("INSERT INTO mapping_entities VALUES (?, ?, ?, 1) ON CONFLICT(entity) DO UPDATE SET catalog_id=excluded.catalog_id, revision=revision+1",
                           (entity["entity"], item["catalog_id"], json.dumps(item["ids"])))
                now = time.time()
                for provider, change in normalized.items():
                    if change["mode"] == "catalog":
                        db.execute("DELETE FROM mapping_overrides WHERE entity=? AND provider=?", (entity["entity"], provider))
                    else:
                        credit = contributor if source == "community" else before.get(provider, {}).get("contributor") if before.get(provider, {}).get("id") == change["id"] else None
                        db.execute("""INSERT INTO mapping_overrides(entity, provider, identifier, note, updated_at, source, contributor) VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(entity, provider) DO UPDATE SET identifier=excluded.identifier,
                            note=excluded.note, updated_at=excluded.updated_at, source=excluded.source, contributor=excluded.contributor""",
                                   (entity["entity"], provider, change["id"], change.get("note", ""), now, source, json.dumps(credit) if credit else None))
                after = self._snapshot(db)[2].get(entity["entity"], {})
                db.execute("INSERT INTO mapping_audit(entity, created_at, before_json, after_json) VALUES (?, ?, ?, ?)",
                           (entity["entity"], now, json.dumps(before), json.dumps(after)))
                if connection is not None:
                    return {"item": self._apply(item, self._snapshot(db))}
        except sqlite3.IntegrityError as exc:
            raise MappingConflict("该站点 ID 已被其他动画的映射使用") from exc
        return self.detail(item)

    def export(self):
        with self.cache.connect() as db:
            entities, _, overrides = self._snapshot(db)
        return {"version": 1, "exported_at": time.time(), "items": [{**entity, "overrides": overrides.get(key, {})}
                for key, entity in entities.items() if overrides.get(key)]}

    def updated_at(self):
        with self.cache.connect() as db:
            return db.execute("SELECT MAX(created_at) FROM mapping_audit").fetchone()[0]
