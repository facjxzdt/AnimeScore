"""Legacy precise-search interface backed exclusively by bangumi-data IDs."""

from services.catalog import CatalogUnavailable, get_repository
from services.mappings import MappingStore
from services.ratings import RatingCache


def lookup_ext_ids(bgm_id=None, mal_id=None):
    try:
        catalog = get_repository().snapshot()
    except CatalogUnavailable:
        return None
    items = MappingStore(RatingCache()).apply(catalog.entries)
    item = next((entry for entry in items if entry["ids"].get("bgm_id") == str(bgm_id)), None) if bgm_id else None
    if not item and mal_id:
        item = next((entry for entry in items if entry["ids"].get("mal_id") == str(mal_id)), None)
    return dict(item["ids"]) if item else None


def clear_ext_linker_cache():
    # The repository reloads the catalog when its file signature changes.
    pass
