import scrapy, logging, json
from bs4 import BeautifulSoup
from scrapyrealestate.items import ScrapyrealestateItem
from scrapyrealestate.parsing import extract_fotocasa_items, extract_listing_id, has_elevator_filter
from scrapy_playwright.page import PageMethod


class FotocasaSpider(scrapy.Spider):
    name = "fotocasa"
    allowed_domains = ["fotocasa.es"]

    def start_requests(self):
        # Los datos están en el script __initial_props__, que aparece en el DOM
        # pase lo que pase con el banner de cookies. Esperamos solo a ese script.
        yield scrapy.Request(
            self.start_urls,
            meta={
                'playwright': True,
                'playwright_page_methods': [
                    # state="attached": un <script> nunca es "visible"
                    PageMethod("wait_for_selector", "script#__initial_props__",
                               state="attached", timeout=45000),
                ],
            },
            errback=self.on_error,
        )

    def on_error(self, failure):
        logging.error(f'Error al obtener datos de fotocasa.es: {failure.value}')

    def parse(self, response):
        default_url = 'https://www.fotocasa.es'
        soup = BeautifulSoup(response.text, 'lxml')

        # alquiler/venta según la url
        if 'alquiler' in self.start_urls:
            tipo = 'rent'
        elif 'comprar' in self.start_urls or 'venta' in self.start_urls:
            tipo = 'buy'
        else:
            tipo = ''

        # Fotocasa usa resultsV2.items en la versión actual y realEstates
        # como fallback para respuestas antiguas/fixtures.
        script = soup.find('script', {'id': '__initial_props__'})
        if script is None:
            logging.warning('FOTOCASA: no se encontró el JSON __initial_props__ '
                            '(posible bloqueo o cambio de página)')
            return

        try:
            payload = json.loads(script.string or script.get_text())
            real_estates = extract_fotocasa_items(payload)
        except (ValueError, KeyError, TypeError) as e:
            logging.warning(f'FOTOCASA: no se pudo parsear el JSON ({e})')
            return

        logging.debug(f'FOTOCASA: {len(real_estates)} inmuebles en el JSON')

        for flat in real_estates:
            items = ScrapyrealestateItem()

            # features es una lista de {key, value} (rooms, surface, floor...)
            feats = {}
            for f in (flat.get('features') or []):
                if isinstance(f, dict) and 'key' in f:
                    feats[f['key']] = f.get('value')

            address = flat.get('address') or {}
            detail = flat.get('detail') or {}
            href = detail.get('es-ES', '') if isinstance(detail, dict) else ''

            items['id'] = str(flat.get('propertyId') or flat.get('id') or extract_listing_id('fotocasa', href))
            items['title'] = flat.get('description', '') or flat.get('promotionTitle', '')
            items['price'] = flat.get('price', '')
            items['rooms'] = feats.get('rooms', '')
            items['m2'] = feats.get('surface', '')
            items['floor'] = feats.get('floor', '')
            items['elevator'] = True if has_elevator_filter(self.start_urls) or 'elevator' in feats else None
            items['town'] = address.get('municipality', '')
            items['neighbour'] = address.get('neighborhood', '')
            items['street'] = ''
            items['number'] = ''
            items['type'] = tipo
            items['href'] = (default_url + href) if href else ''
            if 'type' in items:
                items['type'] = items['type']
            items['site'] = 'fotocasa'

            yield items
