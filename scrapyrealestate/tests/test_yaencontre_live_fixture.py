import json
import sys
from pathlib import Path

from scrapy.http import HtmlResponse, Request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrapyrealestate.spiders.yaencontre_spider import YaencontreSpider


def test_yaencontre_real_fixture_uses_cards_and_elevator():
    fixture = Path("C:/Users/nicoi/AppData/Local/hermes/cache/scratch/yaencontre_gijon_page1.html")
    if not fixture.exists():
        return
    url = "https://www.yaencontre.com/venta/pisos/gijon/f-ascensor"
    response = HtmlResponse(
        url=url,
        body=fixture.read_text(encoding="utf-8", errors="replace"),
        encoding="utf-8",
        request=Request(url),
    )
    spider = YaencontreSpider()
    spider.start_urls = url
    items = list(spider.parse(response))
    assert len(items) >= 5
    assert all(item["id"] for item in items)
    assert all(item["elevator"] is True for item in items)
    assert all(item["type"] == "buy" for item in items)
    assert len({item["id"] for item in items}) == len(items)


def test_yaencontre_fixture_is_not_sale_price_as_rent():
    fixture = Path("C:/Users/nicoi/AppData/Local/hermes/cache/scratch/yaencontre_gijon_page1.html")
    if not fixture.exists():
        return
    url = "https://www.yaencontre.com/venta/pisos/gijon/f-ascensor"
    response = HtmlResponse(
        url=url,
        body=fixture.read_text(encoding="utf-8", errors="replace"),
        encoding="utf-8",
        request=Request(url),
    )
    spider = YaencontreSpider()
    spider.start_urls = url
    items = list(spider.parse(response))
    assert all("/mes" not in item["price"] for item in items)
