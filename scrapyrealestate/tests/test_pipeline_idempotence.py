import sys
from pathlib import Path

from scrapyrealestate.pipeline import merge_listing_dicts

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_merge_listing_dicts_is_idempotent():
    rows = [{"site": "a", "id": "1", "price": 100}]
    assert merge_listing_dicts(merge_listing_dicts(rows)) == rows
