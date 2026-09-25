import scrapy, re
from scrapy.spiders import CrawlSpider
from bs4 import BeautifulSoup
from scrapyrealestate.items import ScrapyrealestateItem


class HabitacliaSpider(CrawlSpider):
    name = "habitaclia"
    allowed_domains = ["habitaclia.com"]

    def start_requests(self):
        # callback explícito: con callback=None el engine no llegaba a
        # llamar a parse en este proyecto (scrapy 2.11 + handler playwright).
        yield scrapy.Request(f'{self.start_urls}', callback=self.parse,
                             dont_filter=True)

    custom_settings = {
        'DEFAULT_REQUEST_HEADERS': {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'accept-encoding': 'gzip, deflate, br',
            'accept-language': 'es-ES,es;q=0.9,ca;q=0.8,en;q=0.7',
            'cache-control': 'max-age=0',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'sec-gpc': '1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'
        }
    }

    def parse(self, response):
        # habitaclia (grupo Adevinta) usa desde 2025 el motor de fotocasa:
        # listado renderizado en servidor como <article data-panot-component=
        # "link-box">. El markup viejo (div.list-item) ya no existe.
        soup = BeautifulSoup(response.text, 'lxml')
        mslug = re.search(r'(?:viviendas|casas)-([a-z_]+)\.htm', str(self.start_urls))
        slug_town = {'gijon': 'Gijón', 'oviedo': 'Oviedo',
                     'mieres': 'Mieres', 'siero': 'Siero'}.get(
                         mslug.group(1) if mslug else '', '')
        for card in soup.find_all('article'):
            items = ScrapyrealestateItem()  # un item por tarjeta
            try:
                title = card.get('aria-label', '').strip()
                if not title or ' en ' not in title:
                    continue
                a = card.find('a', href=re.compile(r'^/i\d+'))
                href = ('https://www.habitaclia.com' + a['href'].split('?')[0]
                        ) if a else ''
                blob = re.sub(r'\s+', ' ', card.get_text(' ')).strip()

                mprice = re.search(r'([\d.]+)\s*€', blob)
                price = mprice.group(1) + ' €' if mprice else ''
                mm2 = re.search(r'(\d+)\s*m²', blob)
                m2 = mm2.group(1) if mm2 else ''
                mrooms = re.search(r'(\d+)\s*hab', blob)
                rooms = mrooms.group(1) + ' hab.' if mrooms else ''
                mfloor = re.search(r'(\d+)º', blob)
                floor = mfloor.group(0) if mfloor else ''

                # localidad: tras el título y antes de los m² -> "Este, Gijón"
                town = slug_town
                neighbour = ''
                street = ''
                number = ''
                try:
                    loc = blob.split(title)[1].split('m²')[0]
                    loc = re.sub(r'\d+\s*$', '', loc).strip()
                    parts = [x.strip() for x in loc.split(',') if x.strip()]
                    # "Gijón, Asturias" cuando el anuncio no da barrio
                    if parts and parts[-1].lower() == 'asturias':
                        parts = parts[:-1]
                    if parts:
                        town = parts[-1] or slug_town
                        neighbour = parts[0] if len(parts) > 1 else ''
                    elif loc:
                        town = loc
                except Exception:
                    pass

                lid = re.search(r'/i(\d+)', href)
                id = lid.group(1) if lid else (
                    ''.join(c for c in rooms if c.isdigit())
                    + ''.join(c for c in price if c.isdigit()) + m2)

                items['id'] = id
                items['price'] = price
                items['m2'] = m2
                items['rooms'] = rooms
                items['floor'] = floor
                items['town'] = town
                items['neighbour'] = neighbour
                items['street'] = street
                items['number'] = number
                items['type'] = 'buy'
                items['title'] = title
                items['href'] = href
                items['site'] = 'habitaclia'
                yield items
            except Exception:
                continue
