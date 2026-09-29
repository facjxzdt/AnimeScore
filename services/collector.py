"""Hourly collection survives browser closure and coordinates multiple workers."""

import asyncio
import logging
import os
from contextlib import suppress

from services.analytics import AnalyticsStore
from services.catalog import current_season

logger = logging.getLogger(__name__)


class Collector:
    def __init__(self, repository, ratings):
        self.repository, self.ratings = repository, ratings
        self.store = AnalyticsStore(ratings.cache)
        self.enabled = os.getenv("SCORE_AUTO_UPDATE", "1").lower() in {"1", "true", "yes", "on"}

    async def run_once(self, force=False):
        owner = await asyncio.to_thread(self.store.claim, force=force)
        if not owner:
            return False
        async def keep_lease():
            while True:
                await asyncio.sleep(60)
                if not await asyncio.to_thread(self.store.renew, owner):
                    return

        heartbeat = asyncio.create_task(keep_lease())
        error = None
        try:
            catalog = await asyncio.to_thread(self.repository.snapshot)
            season = catalog.season(*current_season())
            tracked = await asyncio.to_thread(self.store.tracked)
            by_key = {item["catalog_id"]: item for item in season}
            by_key.update({item["catalog_id"]: item for item in catalog.entries if item["catalog_id"] in tracked})
            items = list(by_key.values())
            failures = 0
            for start in range(0, len(items), 5):
                if not await asyncio.to_thread(self.store.progress, owner, start, len(items), failures):
                    return False
                result = await self.ratings.enrich(items[start:start + 5])
                failures += sum(state["status"] in {"unavailable", "stale"} for item in result for state in item["score_status"].values())
                await asyncio.to_thread(self.store.progress, owner, min(start + 5, len(items)), len(items), failures)
        except asyncio.CancelledError:
            error = "Collection interrupted; retry after restart"
            raise
        except Exception as exc:
            logger.exception("Score collection failed")
            error = type(exc).__name__
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
            await asyncio.to_thread(self.store.finish, owner, error)
        return error is None

    async def run(self):
        if not self.enabled:
            return
        while True:
            await self.run_once()
            await asyncio.sleep(30)
