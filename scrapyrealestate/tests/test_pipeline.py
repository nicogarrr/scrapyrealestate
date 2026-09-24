import json
from pathlib import Path

import pytest

from scrapyrealestate.pipeline import merge_crawl_files, merge_listing_dicts, read_json_items, write_json_items


def test_merge_listing_dicts_deduplicates_by_source_and_id():
    first = {"site": "fotocasa", "id": "1", "price": 100, "town": "Madrid"}
    second = {"site": "fotocasa", "id": "1", "price": 90, "title": "Piso"}
    assert merge_listing_dicts([first, second]) == [
        {"site": "fotocasa", "id": "1", "price": 90, "town": "Madrid", "title": "Piso"}
    ]


def test_merge_listing_dicts_does_not_merge_same_id_across_sources():
    rows = [
        {"site": "fotocasa", "id": "1", "price": 100},
        {"site": "pisoscom", "id": "1", "price": 90000},
    ]
    assert len(merge_listing_dicts(rows)) == 2


def test_write_and_read_json_items_round_trip(tmp_path):
    path = tmp_path / "items.json"
    rows = [{"site": "pisoscom", "id": "a", "price": "100.000 €"}]
    write_json_items(path, rows)
    assert read_json_items(path) == rows


def test_merge_crawl_files_ignores_missing_file_and_merges_existing(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps([{"site": "a", "id": "1"}]), encoding="utf-8")
    second.write_text(json.dumps([{"site": "a", "id": "1", "price": 2}]), encoding="utf-8")
    assert merge_crawl_files([first, tmp_path / "missing.json", second]) == [
        {"site": "a", "id": "1", "price": 2}
    ]


def test_merge_crawl_files_rejects_malformed_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("[", encoding="utf-8")
    with pytest.raises(ValueError, match="broken.json"):
        merge_crawl_files([path])


def test_merge_listing_dicts_is_idempotent():
    rows = [{"site": "a", "id": "1", "price": 100}]
    assert merge_listing_dicts(merge_listing_dicts(rows)) == rows
