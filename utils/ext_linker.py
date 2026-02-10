#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BangumiExtLinker mapping loader.

Provides lookup by bgm_id or mal_id.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from functools import lru_cache
from typing import Dict, Optional, Tuple

import httpx

from data.config import work_dir


MAP_PATH = os.path.join(work_dir, "mapping", "anime_map.json")
MAP_URL_ENV = "ANIME_MAP_URL"
DEFAULT_MAP_URL = "https://github.com/Rhilip/BangumiExtLinker/blob/main/data/anime_map.json"


def _normalize_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


@lru_cache()
def _load_entries() -> list:
    if not os.path.exists(MAP_PATH):
        return []
    with open(MAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache()
def _build_index() -> Tuple[Dict[str, dict], Dict[str, dict]]:
    by_bgm: Dict[str, dict] = {}
    by_mal: Dict[str, dict] = {}

    for item in _load_entries():
        bgm_id = _normalize_id(item.get("bgm_id"))
        if bgm_id and bgm_id not in by_bgm:
            by_bgm[bgm_id] = item

        mal_id = _normalize_id(item.get("mal_id"))
        if mal_id and mal_id not in by_mal:
            by_mal[mal_id] = item

    return by_bgm, by_mal


def lookup_ext_ids(bgm_id: Optional[str] = None, mal_id: Optional[str] = None) -> Optional[dict]:
    """
    Lookup external IDs from mapping.
    Prefer bgm_id, fallback to mal_id.
    """
    by_bgm, by_mal = _build_index()

    key_bgm = _normalize_id(bgm_id)
    if key_bgm and key_bgm in by_bgm:
        return by_bgm[key_bgm]

    key_mal = _normalize_id(mal_id)
    if key_mal and key_mal in by_mal:
        return by_mal[key_mal]

    return None


def clear_ext_linker_cache() -> None:
    """Clear in-memory mapping cache after map file updates."""
    _load_entries.cache_clear()
    _build_index.cache_clear()


def _normalize_map_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        return text
    # Accept GitHub blob URLs and convert to raw content URL.
    if "github.com/" in text and "/blob/" in text:
        text = text.replace("https://github.com/", "https://raw.githubusercontent.com/")
        text = text.replace("/blob/", "/")
    return text


def refresh_map_file(
    *,
    source_url: Optional[str] = None,
    force: bool = False,
    max_age_hours: int = 24,
    timeout: int = 20,
) -> Tuple[bool, str]:
    """
    Refresh mapping file from remote source.

    Returns:
      (updated, message)
      updated=True when local file was replaced.
    """
    url = source_url or os.getenv(MAP_URL_ENV, "").strip() or DEFAULT_MAP_URL
    url = _normalize_map_url(url)
    if not url:
        return False, f"skip: missing {MAP_URL_ENV}"

    if not force and os.path.exists(MAP_PATH):
        try:
            age_seconds = int(max_age_hours) * 3600
            mtime = os.path.getmtime(MAP_PATH)
            if (mtime + age_seconds) > time.time():
                return False, "skip: local map is fresh"
        except Exception:
            pass

    try:
        resp = httpx.get(url, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        return False, f"download_failed: {e}"

    if not isinstance(payload, list):
        return False, "invalid_payload: expected list"

    os.makedirs(os.path.dirname(MAP_PATH), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="anime_map_", suffix=".json", dir=os.path.dirname(MAP_PATH))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp_path, MAP_PATH)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    clear_ext_linker_cache()
    return True, f"updated: {len(payload)} entries"
