"""A minimal, explicit failure-mode contract for Fotocasa parsing."""
from scrapy.http import HtmlResponse, Request

from scrapyrealestate.spiders.fotocasa_spider import FotocasaSpider


def test_fotocasa_empty_payload_yields_no_items():
    url = "https://www.fotocasa.es/es/comprar/viviendas/asturias/todas-las-zonas/ascensor/l"
    html = '<script id="__initial_props__">{"initialSearch":{"result":{"resultsV2":{"items":[]}}}}</script>'
    response = HtmlResponse(url=url, body=html, encoding="utf-8", request=Request(url))
    spider = FotocasaSpider()
    spider.start_urls = url
    assert list(spider.parse(response)) == []


def test_fotocasa_missing_payload_does_not_crash():
    url = "https://www.fotocasa.es/es/comprar/viviendas/asturias/todas-las-zonas/ascensor/l"
    response = HtmlResponse(url=url, body="<html></html>", encoding="utf-8", request=Request(url))
    spider = FotocasaSpider()
    spider.start_urls = url
    assert list(spider.parse(response)) == []
