"""Test contract for current portal payload shapes."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from scrapy.http import HtmlResponse, Request

from scrapyrealestate.spiders.fotocasa_spider import FotocasaSpider
from scrapyrealestate.spiders.pisoscom_spider import PisoscomSpider

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def make_response(url: str, body: str) -> HtmlResponse:
    return HtmlResponse(url=url, body=body, encoding="utf-8", request=Request(url))


def test_fotocasa_spider_uses_current_results_v2_shape():
    payload = {
        "initialSearch": {
            "result": {
                "realEstates": [{"propertyId": 999}],
                "resultsV2": {
                    "items": [
                        {
                            "propertyId": 189937271,
                            "price": 100000,
                            "features": [
                                {"key": "surface", "value": 70},
                                {"key": "rooms", "value": 2},
                                {"key": "bathrooms", "value": 1},
                            ],
                            "address": {
                                "municipality": "Madrid",
                                "province": "Madrid",
                                "neighborhood": "Centro",
                                "coordinates": {"lat": 40.4, "lng": -3.7},
                            },
                            "detail": {"es-ES": "/es/comprar/vivienda/madrid/ascensor/189937271/d"},
                        }
                    ]
                },
            }
        }
    }
    html = f'<script id="__initial_props__">{json.dumps(payload)}</script>'
    url = "https://www.fotocasa.es/es/comprar/viviendas/madrid/todas-las-zonas/ascensor/l"
    spider = FotocasaSpider()
    spider.start_urls = url

    items = list(spider.parse(make_response(url, html)))

    assert len(items) == 1
    assert items[0]["id"] == "189937271"
    assert items[0]["price"] == 100000
    assert items[0]["m2"] == 70
    assert items[0]["rooms"] == 2
    assert items[0]["town"] == "Madrid"
    assert items[0]["href"].endswith("/189937271/d")
    assert items[0]["elevator"] is True


def test_pisoscom_spider_extracts_real_listing_id_and_sale_price():
    html = """
    <div class="ad-preview__info">
      <span class="ad-preview__price">99.999 €</span>
      <a class="ad-preview__title"
         href="/comprar/piso-centro-65098413759.100200/">Piso en Centro</a>
      <p class="ad-preview__subtitle">Centro (Madrid)</p>
      <p class="ad-preview__char p-sm">2 habs.</p>
      <p class="ad-preview__char p-sm">65 m²</p>
    </div>
    """
    url = "https://www.pisos.com/venta/pisos-madrid/ascensor/hasta-100000"
    spider = PisoscomSpider()
    spider.start_urls = url

    items = list(spider.parse(make_response(url, html)))

    assert len(items) == 1
    assert items[0]["id"] == "65098413759.100200"
    assert items[0]["price"] == "99.999 €"
    assert "/mes" not in items[0]["price"]
    assert items[0]["type"] == "buy"
    assert items[0]["elevator"] is True
