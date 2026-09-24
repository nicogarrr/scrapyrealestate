import json
import sys
from pathlib import Path

from scrapy.http import HtmlResponse, Request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrapyrealestate.spiders.idealista_spider import IdealistaSpider


def test_idealista_real_fixture_has_unique_ids():
    fixture = Path("C:/Users/nicoi/AppData/Local/hermes/cache/scratch/idealista_audit_page1.html")
    if not fixture.exists():
        return
    url = "https://www.idealista.com/venta-viviendas/asturias/"
    response = HtmlResponse(
        url=url,
        body=fixture.read_text(encoding="utf-8", errors="replace"),
        encoding="utf-8",
        request=Request(url),
    )
    spider = IdealistaSpider()
    spider.start_urls = url
    items = list(spider.parse(response))
    assert len(items) >= 5
    assert len({item["id"] for item in items}) == len(items)
