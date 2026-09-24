import logging
import re

import scrapy
from bs4 import BeautifulSoup
from scrapy_playwright.page import PageMethod

from scrapyrealestate.items import ScrapyrealestateItem
from scrapyrealestate.parsing import extract_listing_id, has_elevator_filter


class YaencontreSpider(scrapy.Spider):
    name = "yaencontre"
    allowed_domains = ["yaencontre.com"]

    def start_requests(self):
        # The current list page renders 42 article.real-estate-map-list-card
        # elements. The public filtered URL is /f-ascensor; avoid the older
        # selector that returned an empty list.
        yield scrapy.Request(
            f"{self.start_urls}",
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    PageMethod(
                        "wait_for_selector",
                        "article.real-estate-map-list-card",
                        timeout=30000,
                    ),
                ],
            },
            errback=self.on_error,
        )

    def on_error(self, failure):
        logging.error("Error al obtener datos de yaencontre.com: %s", failure.value)

    @staticmethod
    def _transaction(url: str) -> str:
        parts = (url or "").lower().split("/")
        if "alquiler" in parts:
            return "rent"
        if "venta" in parts or "comprar" in parts:
            return "buy"
        return ""

    @staticmethod
    def _location(title: str) -> tuple[str, str, str]:
        parts = [part.strip() for part in title.split(",") if part.strip()]
        town = parts[-1] if parts else ""
        neighbour = parts[-2] if len(parts) >= 2 else ""
        street = parts[0].split(" en ")[-1].strip() if parts else ""
        return town, neighbour, street

    @staticmethod
    def _facts(card) -> tuple[str, str, str]:
        rooms = bathrooms = m2 = ""
        info = card.select_one(".media-info")
        if info is None:
            return rooms, bathrooms, m2
        for child in info.find_all("span"):
            text = child.get_text(" ", strip=True)
            lower = text.lower()
            if "hab" in lower:
                rooms = text
            elif "baño" in lower or "bano" in lower:
                bathrooms = text
            elif "m²" in lower or "m2" in lower:
                m2 = text
        return rooms, bathrooms, m2

    def parse(self, response):
        soup = BeautifulSoup(response.text, "lxml")
        transaction = self._transaction(self.start_urls)
        elevator_filter = has_elevator_filter(self.start_urls)
        seen_ids = set()

        for card in soup.select("article.real-estate-map-list-card"):
            link = card.select_one("a[href*='/inmueble-']")
            if link is None:
                continue
            href = link.get("href", "")
            listing_id = extract_listing_id("yaencontre", href)
            if not listing_id or listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)

            title = link.get_text(" ", strip=True)
            town, neighbour, street = self._location(title)
            price_el = card.select_one(".price-wrapper")
            price = price_el.get_text(" ", strip=True) if price_el else ""
            rooms, bathrooms, m2 = self._facts(card)
            elevator = elevator_filter or bool(
                re.search(r"\bascensor\b", card.get_text(" ", strip=True), re.IGNORECASE)
            )

            item = ScrapyrealestateItem()
            item["id"] = listing_id
            item["title"] = title
            item["price"] = price
            item["rooms"] = rooms
            item["bathrooms"] = bathrooms
            item["m2"] = m2
            item["floor"] = ""
            item["elevator"] = elevator
            item["town"] = town
            item["neighbour"] = neighbour
            item["street"] = street
            item["number"] = ""
            item["type"] = transaction
            item["href"] = ("https://www.yaencontre.com" + href) if href.startswith("/") else href
            item["site"] = "yaencontre"
            yield item

    parse_start_url = parse
