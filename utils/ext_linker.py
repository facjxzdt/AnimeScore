#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BangumiExtLinker mapping loader.

Provides lookup by bgm_id or mal_id.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Dict, Optional, Tuple

from data.config import work_dir


MAP_PATH = os.path.join(work_dir, "mapping", "anime_map.json")


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
