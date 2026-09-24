"""Helpers for safe ingestion of normalized scraper items."""
from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def numeric_price(value: Any) -> int | None:
    """Parse a Spanish/English display price into an integer.

    Returns None for consultation prices and other non-numeric values.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text or "consult" in text.lower():
        return None
    # Keep digits and decimal separators, then interpret Spanish formatting.
    normalized = re.sub(r"[^0-9.,]", "", text)
    if not normalized:
        return None
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    else:
        normalized = normalized.replace(".", "")
    try:
        return int(float(normalized))
    except ValueError:
        return None


def _normalized_href(href: str) -> str:
    parsed = urlsplit((href or "").strip())
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))


def listing_key(item: dict[str, Any]) -> str:
    """Return the canonical per-source key used for deduplication."""
    source = str(item.get("site") or item.get("source") or "unknown").strip().lower()
    external_id = str(item.get("id") or "").strip()
    if external_id:
        return f"{source}:{external_id}"
    href = _normalized_href(str(item.get("href") or ""))
    digest = hashlib.sha1(href.encode("utf-8")).hexdigest()[:20]
    return f"{source}:url:{digest}"
