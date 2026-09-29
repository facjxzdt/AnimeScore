"""Collect MAL's work rating with independently paced official and Jikan sources."""

import asyncio
import re
import time

import httpx
from bs4 import BeautifulSoup

from services.providers import normalize_id, site_url
from services.http import retry_deadline


def parse_page(html, identifier):
    from services.ratings import numeric_score

    soup = BeautifulSoup(html, "html.parser")
    canonical = soup.select_one('link[rel="canonical"]')
    title = soup.select_one("h1.title-name")
    block = soup.select_one('[itemprop="aggregateRating"]')
    unrated = soup.select_one('.stats-block .score[data-title="score"] .score-label.score-na')
    explicit_unrated = unrated is not None and unrated.get_text(strip=True) == "N/A"
    if not canonical or normalize_id("mal", canonical.get("href", "")) != identifier or not title or (not block and not explicit_unrated):
        raise ValueError("MAL work identity or aggregate rating section missing")

    def value(prop):
        node = block.select_one(f'[itemprop="{prop}"]') if block else None
        return (node.get("content") or node.get_text(strip=True)) if node else None

    raw = value("ratingValue")
    if raw is None and explicit_unrated:
        raw = "N/A"
    score = numeric_score(raw)
    if score is None and raw not in {"N/A", "Not yet scored", "-", "0", "0.0"}:
        raise ValueError("MAL work rating missing or invalid")
    votes = value("ratingCount")
    if votes is not None:
        votes = votes.replace(",", "")
        if not re.fullmatch(r"[0-9]+", votes):
            raise ValueError("MAL rating count invalid")
        votes = int(votes)
    rank_node = soup.select_one(".numbers.ranked strong")
    rank = re.fullmatch(r"#([0-9,]+)", rank_node.get_text(strip=True)) if rank_node else None
    poster = soup.select_one('img[itemprop="image"]')
    summary = soup.select_one('[itemprop="description"]')
    labels = {node.get_text(strip=True): node.parent for node in soup.select("span.dark_text")}
    episodes = labels.get("Episodes:")
    episode_text = episodes.get_text(" ", strip=True).partition(":")[2].strip() if episodes else ""
    studios = labels.get("Studios:")
    return {"score": score, "votes": votes,
            "rank": int(rank.group(1).replace(",", "")) if rank else None,
            "title": title.get_text(" ", strip=True),
            "details": {"poster": (poster.get("data-src") or poster.get("src")) if poster else None,
                        "summary": summary.get_text(" ", strip=True) if summary else None,
                        "episodes": int(episode_text) if re.fullmatch(r"[0-9]+", episode_text) else None,
                        "studio": ", ".join(node.get_text(strip=True) for node in studios.select('a[href*="/anime/producer/"]')) if studios else None}}


def parse_jikan(payload, identifier):
    from services.ratings import numeric_score

    data = payload["data"]
    if str(data["mal_id"]) != identifier:
        raise ValueError("Jikan returned a different MAL ID")
    score = numeric_score(data["score"])
    if data["score"] is not None and score is None:
        raise ValueError("Jikan work rating invalid")
    return {"score": score, "votes": data.get("scored_by"), "rank": data.get("rank"), "title": data.get("title"),
            "details": {"poster": ((data.get("images") or {}).get("jpg") or {}).get("large_image_url"),
                        "summary": data.get("synopsis"), "episodes": data.get("episodes"),
                        "studio": ", ".join(studio["name"] for studio in data.get("studios", []) or [] if studio.get("name"))}}


class MALUnavailable(ValueError):
    def __init__(self, errors, retry_at):
        self.source_errors = errors
        self.http_status = errors[-1].get("http_status")
        self.retry_at = retry_at
        super().__init__("Both MAL rating sources are unavailable")


class MALSource:
    def __init__(self, client, interval=2):
        self.client, self.interval = client, interval
        self.last_request = {"myanimelist": 0.0, "jikan": 0.0}
        self.blocked_until = {"myanimelist": 0.0, "jikan": 0.0}
        self.blocked_errors = {}

    async def _request(self, source, url):
        if self.blocked_until[source] > time.time():
            raise self.blocked_errors[source]
        delay = self.interval - (time.monotonic() - self.last_request[source])
        if delay > 0:
            await asyncio.sleep(delay)
        self.last_request[source] = time.monotonic()
        response = await self.client.get(url, timeout=15, follow_redirects=False)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if response.status_code in {403, 429}:
                self.blocked_until[source] = retry_deadline(response.headers.get("Retry-After", "60"))
                self.blocked_errors[source] = exc
            raise
        if response.status_code != 200:
            raise ValueError("Unexpected MAL source response")
        return response

    async def fetch(self, identifier):
        identifier = normalize_id("mal", identifier)
        errors = []
        sources = (("myanimelist", site_url("mal", identifier)),
                   ("jikan", f"https://api.jikan.moe/v4/anime/{identifier}"))
        for source, url in sources:
            try:
                response = await self._request(source, url)
                data = (await asyncio.to_thread(parse_page, response.text, identifier)
                        if source == "myanimelist" else parse_jikan(response.json(), identifier))
                return {**data, "source": source, "source_url": url}
            except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
                status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                errors.append({"source": source, "error": f"HTTP {status}" if status else type(exc).__name__,
                               "http_status": status})
        # A limited host must not stall the other host or the entire hourly queue.
        raise MALUnavailable(errors, max(time.time() + 60, min(self.blocked_until.values())))
