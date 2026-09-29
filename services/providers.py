"""Supported rating sites and canonical, strictly validated public URLs."""

import re
from urllib.parse import urlparse

SITES = {
    "bgm": {"name": "Bangumi", "field": "bgm_id", "site": "bangumi", "url": "https://bgm.tv/subject/{}", "region": "中文社区", "example": "501963", "color": "#dc7394", "default_weight": 5},
    "mal": {"name": "MyAnimeList", "field": "mal_id", "site": "mal", "url": "https://myanimelist.net/anime/{}", "region": "国际社区", "example": "59193", "color": "#417eb3", "default_weight": 2},
    "anilist": {"name": "AniList", "field": "anilist_id", "site": "aniList", "url": "https://anilist.co/anime/{}", "region": "国际社区", "example": "178789", "color": "#db9b41", "default_weight": 0},
    "filmarks": {"name": "Filmarks", "field": "filmarks_id", "site": "filmarks", "url": "https://filmarks.com/animes/{}", "region": "日本社区", "example": "1431/6089", "color": "#9a79ba", "default_weight": 0},
    "anikore": {"name": "Anikore", "field": "anikore_id", "site": "anikore", "url": "https://www.anikore.jp/anime/{}/", "region": "日本社区", "example": "14266", "color": "#428d92", "default_weight": 0},
}
PROVIDERS = {key: site["field"] for key, site in SITES.items()}
DEFAULT_WEIGHTS = {key: float(site["default_weight"]) for key, site in SITES.items()}


def normalize_id(provider, value):
    if provider not in SITES or not isinstance(value, str):
        raise ValueError("不支持的评分站点")
    value = value.strip()
    if len(value) > 300:
        raise ValueError("ID 或链接过长")
    if "://" in value:
        parsed = urlparse(value)
        hosts = {"bgm": {"bgm.tv", "bangumi.tv", "chii.in"}, "mal": {"myanimelist.net", "www.myanimelist.net"},
                 "anilist": {"anilist.co", "www.anilist.co"}, "filmarks": {"filmarks.com", "www.filmarks.com"},
                 "anikore": {"anikore.jp", "www.anikore.jp"}}
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in hosts[provider] or parsed.username or parsed.password or parsed.port:
            raise ValueError("请使用该站点的作品链接")
        pattern = {"bgm": r"/subject/([1-9]\d*)/?", "mal": r"/anime/([1-9]\d*)(?:/[^/]*)?/?",
                   "anilist": r"/anime/([1-9]\d*)(?:/[^/]*)?/?", "filmarks": r"/animes/([1-9]\d*/[1-9]\d*)/?",
                   "anikore": r"/anime/([1-9]\d*)/?"}[provider]
        match = re.fullmatch(pattern, parsed.path)
        if not match:
            raise ValueError("作品链接格式不正确；请勿填写评论或搜索页")
        value = match.group(1)
    pattern = r"[1-9]\d{0,11}/[1-9]\d{0,11}" if provider == "filmarks" else r"[1-9]\d{0,11}"
    if not re.fullmatch(pattern, value):
        raise ValueError("Filmarks 需要系列 ID/季度 ID" if provider == "filmarks" else "ID 必须为正整数")
    return value


def site_url(provider, identifier):
    return SITES[provider]["url"].format(normalize_id(provider, identifier))


def public_providers():
    return [{"key": key, **value} for key, value in SITES.items()]
