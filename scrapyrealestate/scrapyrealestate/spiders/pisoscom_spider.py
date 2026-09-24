import scrapy
from bs4 import BeautifulSoup
from scrapy.spiders import CrawlSpider

from scrapyrealestate.items import ScrapyrealestateItem
from scrapyrealestate.parsing import extract_listing_id, has_elevator_filter


class PisoscomSpider(CrawlSpider):
    name = "pisoscom"
    allowed_domains = ["pisos.com"]

    def start_requests(self):
        yield scrapy.Request(f"{self.start_urls}")

    custom_settings = {
        "DEFAULT_REQUEST_HEADERS": {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "es-ES,es;q=0.9,ca;q=0.8,en;q=0.7",
            "cache-control": "max-age=0",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "sec-gpc": "1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
        }
    }

    def parse(self, response):
        transaction = self._transaction(self.start_urls)
        elevator_filter = has_elevator_filter(self.start_urls)
        soup = BeautifulSoup(response.text, "lxml")
        cards = soup.find_all("div", {"class": "ad-preview__info"})
        seen_ids = set()

        for card in cards:
            title_el = card.find(class_="ad-preview__title")
            if title_el is None or not title_el.get("href"):
                continue

            href = title_el["href"]
            listing_id = extract_listing_id("pisoscom", href)
            if listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)

            title = title_el.get_text(" ", strip=True)
            town = ""
            neighbour = ""
            street = ""
            number = ""
            street_name = ""
            if len(title.split(",")) == 2:
                street_name = title.split(",")[0]
                number = title.split(",")[-1]
            elif len(title.split(",") ) == 1:
                street_name = title.split(" en ")[-1]

            street_keywords = (
                "calle", "carrer", "c.", "avenida", "avinguda", "av.", "plaza",
                "plaça", "via", "travessera", "camino", "cami", "paseo", "passeig",
                "passaje", "passatge", "carretera", "ctra.",
            )
            if any(keyword in street_name.lower() for keyword in street_keywords):
                street = street_name

            subtitle_el = card.find(class_="ad-preview__subtitle")
            subtitle = subtitle_el.get_text(" ", strip=True) if subtitle_el else ""
            if "(" in subtitle:
                neighbour = subtitle.split("(", 1)[0].rstrip()
                town = subtitle.split("(", 1)[1].split(")", 1)[0].strip()
                if "Distrito" in town:
                    town = town.rsplit(".", 1)[-1].split(" ", 1)[-1]
                town = town.replace("Capital", "").strip()
            else:
                town = subtitle

            price_el = card.find("span", {"class": "ad-preview__price"})
            price = price_el.get_text(" ", strip=True) if price_el else ""
            rooms = m2 = floor = bathrooms = ""
            for characteristic in card.find_all("p", {"class": "ad-preview__char p-sm"}):
                text = characteristic.get_text(" ", strip=True)
                lower = text.lower()
                if "hab" in lower:
                    rooms = text
                elif "baño" in lower or "bano" in lower or "ba\u00f1" in lower:
                    bathrooms = text
                elif "m²" in lower or "m2" in lower:
                    m2 = text
                elif "planta" in lower or "bajo" in lower or "sótano" in lower:
                    floor = text

            item = ScrapyrealestateItem()
            item["id"] = listing_id
            item["price"] = price
            item["m2"] = m2
            item["rooms"] = rooms
            item["bathrooms"] = bathrooms
            item["floor"] = floor
            item["elevator"] = True if elevator_filter else None
            item["town"] = town
            item["neighbour"] = neighbour
            item["street"] = street
            item["number"] = number
            item["type"] = transaction
            item["title"] = title
            item["href"] = "https://www.pisos.com" + href
            item["site"] = "pisoscom"
            yield item

    @staticmethod
    def _transaction(url: str) -> str:
        parts = (url or "").lower().split("/")
        if "alquiler" in parts:
            return "rent"
        if "venta" in parts or "comprar" in parts:
            return "buy"
        return ""

    # Procesamos también la primera página (no solo las paginadas).
    parse_start_url = parse
