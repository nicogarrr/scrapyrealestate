"""Safe JSON merge helpers for independent portal crawl outputs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .ingest import listing_key


def read_json_items(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid crawl JSON: {target.name}") from exc
    if not isinstance(payload, list):
        raise ValueError(f"Invalid crawl JSON root: {target.name}")
    return [item for item in payload if isinstance(item, dict)]


def write_json_items(path: str | Path, items: Iterable[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(list(items), ensure_ascii=False, indent=1), encoding="utf-8")


def merge_listing_dicts(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = listing_key(item)
        merged[key] = {**merged.get(key, {}), **item}
    return list(merged.values())


def merge_crawl_files(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        target = Path(path)
        if not target.exists():
            continue
        rows.extend(read_json_items(target))
    return merge_listing_dicts(rows)
