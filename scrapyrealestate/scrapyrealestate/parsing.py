"""Pure parsing helpers shared by the spiders and the ingestion layer."""
from __future__ import annotations

import hashlib
import re
from typing import Any


def _clean_href(href: str) -> str:
    return (href or "").split("#", 1)[0].split("?", 1)[0].rstrip("/")


def extract_listing_id(source: str, href: str) -> str:
    """Return a stable, source-specific ID for a listing URL.

    Portal-specific IDs are preferred. When a portal only exposes a URL, the
    normalized path is hashed so a later run can still deduplicate the listing.
    """
    source_name = (source or "").lower().strip()
    path = _clean_href(href)

    if source_name in {"pisos", "pisos.com", "pisoscom"}:
        match = re.search(r"-(\d+(?:\.\d+|\.\d+_\d+))(?:/|$)", path)
        if match:
            return match.group(1)
        match = re.search(r"-(\d+_\d+)(?:/|$)", path)
        if match:
            return match.group(1)
        match = re.search(r"-(\d+\.\d+)(?:/|$)", path)
        if match:
            return match.group(1)
        match = re.search(r"-(\d+)(?:/|$)", path)
        if match:
            return match.group(1)

    if source_name in {"fotocasa", "fotocasa.es"}:
        match = re.search(r"/(\d+)(?:/d)?$", path)
        if match:
            return match.group(1)

    if source_name in {"idealista", "idealista.com"}:
        match = re.search(r"/inmueble/(\d+)(?:/|$)", path)
        if match:
            return match.group(1)

    if source_name in {"yaencontre", "yaencontre.com"}:
        match = re.search(r"-(\d+)(?:/|$)", path)
        if match:
            return match.group(1)

    digest = hashlib.sha1((source_name + ":" + path).encode("utf-8")).hexdigest()[:20]
    return f"{source_name or 'source'}:{digest}"


def extract_fotocasa_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the current Fotocasa item collection with a legacy fallback."""
    result = (
        (payload.get("initialSearch") or {}).get("result") or {}
    )
    current = ((result.get("resultsV2") or {}).get("items") or [])
    if current:
        return list(current)
    return list(result.get("realEstates") or [])


def format_price(value: Any, transaction: str = "buy") -> str:
    """Format a displayed price without applying rental semantics to sales."""
    text = str(value or "").strip()
    if not text:
        return ""
    if transaction == "rent" and "/mes" not in text.lower() and "€" in text:
        return f"{text}/mes"
    return text


def has_elevator_filter(url: str) -> bool:
    """Whether a search URL visibly requests the elevator filter."""
    text = (url or "").lower()
    return any(token in text for token in ("ascensor", "elevator", "lift"))


def append_url_fragment(url: str, fragment: str) -> str:
    """Append a query or path fragment without producing a double slash/question."""
    base = (url or "").strip()
    extra = (fragment or "").strip()
    if not extra:
        return base
    if extra.startswith("?"):
        extra = extra[1:]
    if "?" in base:
        if extra.startswith("&"):
            extra = extra[1:]
        return f"{base}&{extra}"
    if extra.startswith("&"):
        return f"{base}?{extra[1:]}"
    if extra.startswith("/"):
        return f"{base.rstrip('/')}/{extra.lstrip('/')}"
    if extra.startswith("?") or "=" in extra.split("?", 1)[0]:
        return f"{base}{'&' if '?' in base else '?'}{extra}"
    return f"{base.rstrip('/')}/{extra}"
