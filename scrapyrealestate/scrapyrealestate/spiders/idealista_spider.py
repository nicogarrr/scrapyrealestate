import logging
import re

import scrapy
from bs4 import BeautifulSoup
from scrapy_playwright.page import PageMethod

from scrapyrealestate.items import ScrapyrealestateItem
from scrapyrealestate.parsing import extract_listing_id, has_elevator_filter


class IdealistaSpider(scrapy.Spider):
    name = "idealista"
    allowed_domains = ["idealista.com"]

    def start_requests(self):
        # DataDome can render the listing even when the initial HTTP response is
        # a 403. Keep the browser path and the explicit errback for auditability.
        yield scrapy.Request(
            f"{self.start_urls}",
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    PageMethod("wait_for_selector", "main.listing-items", timeout=45000),
                ],
            },
            errback=self.on_error,
        )

    def on_error(self, failure):
        logging.error("Error al obtener datos de idealista.com: %s", failure.value)

    @staticmethod
    def _transaction(url: str) -> str:
        path = (url or "").lower().split("/")
        if "alquiler" in path:
            return "rent"
        if "venta" in path:
            return "buy"
        return ""

    @staticmethod
    def _location(title: str) -> tuple[str, str, str, str]:
        parts = [part.strip() for part in title.split(",") if part.strip()]
        if not parts:
            return "", "", "", ""
        town = parts[-1]
        if len(parts) == 4:
            return town, parts[2], parts[0].split(" en ")[-1], parts[1]
        if len(parts) == 3:
            return town, parts[1], parts[0].split(" en ")[-1], ""
        if len(parts) == 2:
            return town, parts[0].split(" en ")[-1], "", ""
        return town, "", parts[0].split(" en ")[-1], ""

    @staticmethod
    def _details(card) -> tuple[str, str, str, bool]:
        rooms = m2 = floor = ""
        elevator = False
        for detail in card.select(".item-detail"):
            text = detail.get_text(" ", strip=True)
            lower = text.lower()
            if "hab" in lower:
                rooms = text
            elif "m²" in lower or "m2" in lower:
                m2 = text
            elif "planta" in lower or "bajo" in lower or "sótano" in lower or "entreplanta" in lower:
                floor = text
            if "ascensor" in lower:
                elevator = True
        return rooms, m2, floor, elevator

    def parse(self, response):
        soup = BeautifulSoup(response.text, "lxml")
        transaction = self._transaction(self.start_urls)
        elevator_filter = has_elevator_filter(self.start_urls)
        seen_ids = set()

        for card in soup.select("article.item"):
            link = card.select_one("a.item-link[href*='/inmueble/']")
            if link is None:
                continue
            href = link.get("href", "")
            listing_id = extract_listing_id("idealista", href)
            if not listing_id or listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)

            title = link.get_text(" ", strip=True)
            town, neighbour, street, number = self._location(title)
            price_el = card.select_one(".item-price")
            price = price_el.get_text(" ", strip=True) if price_el else ""
            rooms, m2, floor, elevator = self._details(card)
            if elevator_filter:
                elevator = True

            item = ScrapyrealestateItem()
            item["id"] = listing_id
            item["price"] = price
            item["m2"] = m2
            item["rooms"] = rooms
            item["bathrooms"] = ""
            item["floor"] = floor
            item["elevator"] = elevator if elevator_filter else None
            item["town"] = town
            item["neighbour"] = neighbour
            item["street"] = street
            item["number"] = number
            item["type"] = transaction
            item["title"] = title
            item["href"] = "https://www.idealista.com" + href
            item["site"] = "idealista"
            yield item

    parse_start_url = parse
