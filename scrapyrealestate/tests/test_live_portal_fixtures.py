import json
from pathlib import Path

from scrapy.http import HtmlResponse, Request

from scrapyrealestate.spiders.fotocasa_spider import FotocasaSpider
from scrapyrealestate.spiders.pisoscom_spider import PisoscomSpider

ROOT = Path("C:/Users/nicoi/AppData/Local/hermes/cache/scratch")


def _response(url: str, path: Path) -> HtmlResponse:
    body = path.read_text(encoding="utf-8", errors="replace")
    return HtmlResponse(url=url, body=body, encoding="utf-8", request=Request(url))


def test_current_live_fotocasa_fixture_extracts_v2_items():
    path = ROOT / "current_fotocasa.html"
    if not path.exists():
        return
    url = "https://www.fotocasa.es/es/comprar/viviendas/asturias-provincia/todas-las-zonas/ascensor/l?maxPrice=100000"
    spider = FotocasaSpider()
    spider.start_urls = url
    items = list(spider.parse(_response(url, path)))
    assert len(items) >= 5
    assert all(item["id"] and item["price"] is not None for item in items)
    assert all(item["elevator"] is True for item in items)


def test_current_live_pisos_fixture_extracts_stable_ids():
    path = ROOT / "current_pisos.html"
    if not path.exists():
        return
    url = "https://www.pisos.com/venta/pisos-asturias/ascensor/hasta-100000"
    spider = PisoscomSpider()
    spider.start_urls = url
    items = list(spider.parse(_response(url, path)))
    assert len(items) >= 5
    assert len({item["id"] for item in items}) == len(items)
    assert all("/mes" not in item["price"] for item in items)
