"""Parse only work-level ratings, never individual reviews or search guesses."""

import json
import re

from bs4 import BeautifulSoup


def count(value):
    if value is None:
        return None
    match = re.fullmatch(r"\s*([\d,]+)\s*", str(value))
    return int(match.group(1).replace(",", "")) if match else None


def parse_rating(provider, html):
    soup = BeautifulSoup(html, "html.parser")
    entities = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
            entities.extend(data if isinstance(data, list) else data.get("@graph", [data]))
        except (ValueError, AttributeError):
            continue
    allowed = {"TVSeason", "TVSeries", "Movie", "CreativeWork"}
    work = next((entity for entity in entities if isinstance(entity, dict) and entity.get("@type") in allowed), {})
    rating = work.get("aggregateRating") or {}
    raw = rating.get("ratingValue")
    votes = count(rating.get("ratingCount") or rating.get("reviewCount"))
    scale = float(rating.get("bestRating", 5))
    title = work.get("name") or work.get("title")
    if provider == "filmarks":
        node = soup.select_one(".c2-rating-l__text, .p-content-detail__rating .c-rating__score")
        if raw is None and node:
            raw = node.get_text(strip=True)
        total = soup.select_one(".p-mark-histogram__total-count")
        if total:
            match = re.fullmatch(r"\s*([\d,]+)件のレビュー\s*", total.get_text(strip=True))
            if match:
                votes = count(match.group(1))
    else:
        block = soup.select_one(".l-animeDetailHeader_pointAndButtonBlock_starBlock")
        node = block.select_one("strong, [itemprop=ratingValue]") if block else None
        if raw is None and node:
            raw = node.get("content") or node.get_text(strip=True)
        if votes is None and block:
            vote_node = block.select_one("[itemprop=ratingCount], [itemprop=reviewCount]")
            if vote_node:
                votes = count(vote_node.get("content") or vote_node.get_text(strip=True))
            else:
                match = re.search(r"[（(]\s*([\d,]+)\s*[）)]", block.get_text(" ", strip=True))
                votes = count(match.group(1)) if match else None
    if raw is None and not work and node is None:
        raise ValueError("Upstream rating section missing or access restricted")
    heading = soup.find("h1")
    title = title or (heading.get_text(" ", strip=True) if heading else None)
    from services.ratings import numeric_score
    score = numeric_score(raw, scale)
    if score is None and raw is not None and str(raw).strip() not in {"", "-", "—", "0", "0.0"}:
        raise ValueError("Invalid work-level rating")
    image = work.get("image")
    if isinstance(image, dict):
        image = image.get("url")
    return {"score": score, "votes": votes, "rank": None, "title": title,
            "details": {"poster": image if isinstance(image, str) else None}}
