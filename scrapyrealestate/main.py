#!/usr/bin/python3
import re, html
import sys, subprocess, telebot, time, os.path, os, logging, urllib.request, urllib.error, json, random
from datetime import datetime
from os import path
from art import *
from fake_useragent import UserAgent

from scrapyrealestate.ingest import listing_key, numeric_price
from scrapyrealestate.parsing import append_url_fragment


__license__ = "GPL"
__version__ = "3.0.0"

# No hay bot por defecto: el token lo pone el usuario en la web de
# configuración o con la variable de entorno TELEGRAM_BOT_TOKEN (recomendado
# en despliegue: así nunca se guarda en disco dentro de config.json).


def get_bot_token():
    # Prioridad: token de la web (config.json) > variable de entorno.
    try:
        token = data.get('telegram_bot_token', '')
    except NameError:
        token = ''
    token = token or os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        raise SystemExit('FALTA EL TOKEN DE TELEGRAM: config.json o TELEGRAM_BOT_TOKEN')
    return token

# Por si fake-useragent falla.
FALLBACK_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)


def init_logs():
    global logger
    try:
        log_level = data['log_level'].upper()
    except (KeyError, NameError, AttributeError):
        log_level = 'INFO'

    levels = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
    }
    log_level = levels.get(log_level, logging.INFO)

    logger = logging.getLogger()
    logger.setLevel(log_level)

    ch = logging.StreamHandler()
    ch.setLevel(log_level)
    ch.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                                      "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(ch)

    return logger


def mix_list(original_list):
    # baraja para no empezar siempre por el mismo portal
    shuffled = original_list[:]
    random.shuffle(shuffled)
    return shuffled


def get_config():
    # Sin config.json arrancamos la web para que el usuario lo cree.
    if not os.path.isfile('./data/config.json'):
        if not os.path.exists('data'):
            os.makedirs('data')
        process = init_app_flask()
        get_config_flask(process)
    else:
        with open('./data/config.json') as json_file:
            global data
            data = json.load(json_file)
        # Overrides de entorno para despliegue (docker): TELEGRAM_CHAT_ID
        # permite fijar el canal sin rehacer config.json.
        if os.environ.get('TELEGRAM_CHAT_ID'):
            data['telegram_chatuserID'] = os.environ['TELEGRAM_CHAT_ID']


def check_config():
    tb = telebot.TeleBot(get_bot_token())

    if not path.exists("scrapy.cfg"):
        logger.error("NO SE ENCUENTRA EL FICHERO scrapy.cfg")
        sys.exit()

    # URLs para el mensaje de inicio.
    urls = get_urls(data)
    urls_ok = ''
    urls_ok_count = 0
    for portal in urls:
        for url in urls[portal]:
            if len(url.split('/')) > 2:
                portal_url = url.split('/')[2]
                portal_name = portal_url.split('.')[1]
                urls_ok_count += 1
                urls_ok += f'{portal_name} '

    if data['telegram_chatuserID'] is None:
        logger.error('EL CHAT ID DE TELEGRAM ESTÁ VACÍO')
        sys.exit()

    try:
        if data['start_msg'] == 'True':
            max_txt = 'sin límite' if data['max_price'] == '0' else f"{int(data['max_price']):,}€".replace(',', '.')
            info_message = tb.send_message(
                data['telegram_chatuserID'],
                f"✅ <b>Bot de pisos activo</b>\n"
                f"🔄 cada {int(data['time_update'])//60} min · 💰 hasta {max_txt}\n"
                f"🌐 {urls_ok.strip()}",
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        else:
            info_message = tb.send_message(
                data['telegram_chatuserID'],
                f"LOADING... scrapyrealestate v{__version__}\n")
    except telebot.apihelper.ApiTelegramException:
        logger.error('EL CHAT ID DE TELEGRAM NO ES CORRECTO O EL BOT '
                     '@scrapyrealestatebot NO SE HA AÑADIDO BIEN AL CANAL')
        sys.exit()

    logger.info(f"CANAL DE TELEGRAM {info_message.chat.title} VERIFICADO")
    return info_message


def checks():
    if int(data['time_update']) < 300:
        logger.error("TIME UPDATE < 300 (el mínimo es 300 segundos)")
        sys.exit()
    check_config()   # valida la configuración y verifica el canal de Telegram


def check_url(url):
    try:
        url_code = urllib.request.urlopen(url).getcode()
    except (urllib.error.URLError, OSError):
        url_code = 404
    return url_code


def init_app_flask():
    # Devuelve el proceso (o None si el servidor ya estaba arriba) para poder pararlo.
    localhost_code = check_url("http://localhost:8080")
    if localhost_code == 200:
        return None

    python_bin = sys.executable or "python3"
    process = subprocess.Popen([python_bin, "./scrapyrealestate/flask_server.py"])
    return process


def get_config_flask(process):
    # Espera a que la web escriba config.json y para el servidor.
    global data
    while True:
        if os.path.isfile('./data/config.json'):
            try:
                with open('./data/config.json') as json_file:
                    data = json.load(json_file)
                break
            except json.JSONDecodeError:
                # todavía se está escribiendo
                pass
        time.sleep(1)
    if process is not None:
        process.terminate()


def get_urls(data):
    urls = {}

    if data.get('url_idealista', '') == '' and data.get('url_pisoscom', '') == '' \
            and data.get('url_fotocasa', '') == '' and data.get('url_habitaclia', '') == '' \
            and data.get('url_yaencontre', '') == '':
        logger.warning("NO URLS ENTERED (MINIMUM 1 URL)")
        sys.exit()

    start_urls_idealista = data.get('url_idealista', [])
    start_urls_idealista = [append_url_fragment(url, '?ordenado-por=fecha-publicacion-desc') for url in start_urls_idealista]

    start_urls_pisoscom = data.get('url_pisoscom', [])
    start_urls_pisoscom = [append_url_fragment(url, 'fecharecientedesde-desc/') for url in start_urls_pisoscom]

    start_urls_fotocasa = data.get('url_fotocasa', [])

    start_urls_habitaclia = data.get('url_habitaclia', [])
    start_urls_habitaclia = [append_url_fragment(url, '?ordenar=mas_recientes') for url in start_urls_habitaclia]

    start_urls_yaencontre = data.get('url_yaencontre', [])
    start_urls_yaencontre = [append_url_fragment(url, '/o-recientes') for url in start_urls_yaencontre]

    urls['start_urls_idealista'] = start_urls_idealista
    urls['start_urls_pisoscom'] = start_urls_pisoscom
    urls['start_urls_fotocasa'] = start_urls_fotocasa
    urls['start_urls_habitaclia'] = start_urls_habitaclia
    urls['start_urls_yaencontre'] = start_urls_yaencontre

    return urls



# --- Mejoras fork Nico: ids con metadatos, salud de portales, status ---

IDS_PATH = "./data/ids.json"
HEALTH_PATH = "./data/health.json"
STATUS_PATH = "./data/status.json"
MAX_IDS = 100000          # cap de ids.json (se purgan los más antiguos)
HEALTH_FAIL_THRESHOLD = 6  # ciclos seguidos sin resultados antes de avisar (~1,5h a 15 min)

SIG_STOPWORDS = {"piso", "en", "venta", "de", "la", "el", "calle", "avenida",
                 "av", "avda", "atico", "ático", "duplex", "dúplex", "estudio",
                 "apartamento", "planta", "bajo", "urb", "urbanizacion"}


def load_ids():
    # Formato nuevo: {id: {price, ts, portal, sig}}. Migra la lista antigua.
    try:
        with open(IDS_PATH) as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if isinstance(raw, list):
        return {str(i): {"price": None, "ts": 0, "portal": "", "sig": None}
                for i in raw}
    return raw


def save_ids(ids):
    if len(ids) > MAX_IDS:
        ids = dict(sorted(ids.items(),
                          key=lambda kv: kv[1].get("ts", 0),
                          reverse=True)[:MAX_IDS])
    with open(IDS_PATH, "w") as f:
        json.dump(ids, f)


def load_health():
    try:
        with open(HEALTH_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def update_health(portal, ok, tb, tg_chatID):
    # Avisa por el canal (una vez) si un portal encadena fallos; se resetea al recuperarse.
    h = load_health()
    e = h.get(portal, {"fail": 0, "alerted": False})
    if ok:
        e = {"fail": 0, "alerted": False}
    else:
        e["fail"] += 1
        if e["fail"] >= HEALTH_FAIL_THRESHOLD and not e["alerted"]:
            try:
                tb.send_message(
                    tg_chatID,
                    f"⚠️ <b>{portal}</b> lleva {e['fail']} ciclos sin dar "
                    f"resultados (posible bloqueo anti-bot o cambio de la web). "
                    f"Revisar: docker logs flats-bot-asturias",
                    parse_mode='HTML')
            except Exception as ex:
                logger.error(f'ERROR ENVIANDO AVISO DE SALUD: {ex}')
            e["alerted"] = True
    h[portal] = e
    with open(HEALTH_PATH, "w") as f:
        json.dump(h, f)
    return h


def write_status(portal_counts, sent_new, sent_drops):
    # Estado del último ciclo para inspección por SSH (no hay web expuesta).
    try:
        st = {"last_cycle": datetime.now().isoformat(timespec="seconds"),
              "portal_counts": portal_counts,
              "health": load_health(),
              "sent_new": sent_new, "sent_drops": sent_drops}
        with open(STATUS_PATH, "w") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
    except OSError as e:
        logger.warning(f'NO SE PUDO ESCRIBIR status.json: {e}')



ZONAS_PATH = "./data/zonas.json"
ZONAS_MIN_MUESTRAS = 15   # por debajo no anotamos: poca fiabilidad
ZONAS_MAX_MUESTRAS = 300  # muestras €/m² guardadas por ciudad (rotación)


def load_zonas():
    try:
        with open(ZONAS_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_zonas(z):
    with open(ZONAS_PATH, "w") as f:
        json.dump(z, f)


def norm_town(town):
    return re.sub(r'[^a-z0-9áéíóúñ]', '', str(town).lower())


def update_zonas(zonas, price, m2, town):
    """Acumula €/m² por ciudad (solo datos sanos)."""
    if not (isinstance(price, int) and isinstance(m2, int) and m2 >= 20 and price >= 5000):
        return
    t = norm_town(town)
    if not t:
        return
    eurm2 = round(price / m2)
    if not (100 <= eurm2 <= 10000):
        return
    e = zonas.setdefault(t, {"samples": []})
    e["samples"].append(eurm2)
    if len(e["samples"]) > ZONAS_MAX_MUESTRAS:
        e["samples"] = e["samples"][-ZONAS_MAX_MUESTRAS:]


def zona_tag(zonas, price, m2, town):
    """Etiqueta de zona por €/m² vs mediana de la ciudad. Anota, nunca excluye."""
    if not (isinstance(price, int) and isinstance(m2, int) and m2 > 0):
        return ''
    t = norm_town(town)
    e = zonas.get(t)
    if not e or len(e["samples"]) < ZONAS_MIN_MUESTRAS:
        return ''
    samples = sorted(e["samples"])
    med = samples[len(samples) // 2]
    if med <= 0:
        return ''
    eurm2 = price / m2
    diff = round((eurm2 - med) / med * 100)
    town_c = str(town).strip()
    if diff <= -20:
        return f"🔥 {abs(diff)}% bajo la media de {town_c} ({med}€/m²) - posible chollo"
    if diff >= 20:
        return f"💎 {diff}% sobre la media de {town_c} ({med}€/m²) - zona cotizada"
    return f"≈ media de {town_c} ({med}€/m²)"



GEO_PATH = "./data/geo.json"
GEO_MAX = 2000            # direcciones cacheadas como máximo
GEO_UA = "flats-bot-asturias/1.0 (bot personal de alertas de pisos)"


def load_geo():
    try:
        with open(GEO_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_geo(g):
    if len(g) > GEO_MAX:
        g = dict(sorted(g.items(), key=lambda kv: kv[1].get("ts", 0),
                        reverse=True)[:GEO_MAX])
    with open(GEO_PATH, "w") as f:
        json.dump(g, f)


def geo_tag(geo, title, town):
    """Cuenta parques y bares/fiesta en 400m (OpenStreetMap). Anota, nunca excluye.
    Devuelve '' si no se puede geocodificar o falla la red."""
    import urllib.parse
    import urllib.request
    key = norm_town(town) + '|' + re.sub(r'\s+', ' ', str(title).lower().strip())[:80]
    e = geo.get(key)
    if e is not None and not e.get("fail") and "bus" not in e:
        e = None  # caché antigua sin bus/coles: recalcular
    if e is None:
        # limpia el título ("Piso en Calle X, Centro" -> "Calle X, Centro")
        clean = re.sub(r'^(piso|casa|ático|atico|dúplex|duplex|estudio|apartamento|chalet|adosado|vivienda|local|oficina|planta baja|bajo)\s+(en\s+)?',
                       '', str(title).strip(), flags=re.I)
        lat = lon = None
        for q in (f"{clean}, {town}, Asturias, España",
                  f"{town}, Asturias, España"):  # fallback: centro del concejo
            try:
                url = ("https://nominatim.openstreetmap.org/search?format=json&limit=1&q="
                       + urllib.parse.quote(q))
                req = urllib.request.Request(url, headers={"User-Agent": GEO_UA})
                with urllib.request.urlopen(req, timeout=15) as r:
                    res = json.loads(r.read().decode())
                if res:
                    lat, lon = float(res[0]["lat"]), float(res[0]["lon"])
                    break
            except Exception:
                return ''
            time.sleep(1.1)  # política Nominatim: máx 1 req/s
        if lat is None:
            geo[key] = {"ts": int(time.time()), "fail": True}
            return ''  
        try:
            q2 = ('[out:json][timeout:15];('
                  f'nwr["leisure"="park"](around:400,{lat},{lon});'
                  f'nwr["amenity"~"^(bar|pub|nightclub)$"](around:400,{lat},{lon});'
                  f'nwr["amenity"="school"](around:400,{lat},{lon});'
                  f'nwr["highway"="bus_stop"](around:400,{lat},{lon});'
                  f'nwr["public_transport"="platform"](around:400,{lat},{lon});'
                  ');out tags;')
            els = None
            for endpoint in ("https://overpass-api.de/api/interpreter",
                             "https://overpass.kumi.systems/api/interpreter"):
                try:
                    req2 = urllib.request.Request(
                        endpoint,
                        data=urllib.parse.urlencode({"data": q2}).encode(),
                        headers={"User-Agent": GEO_UA})
                    with urllib.request.urlopen(req2, timeout=25) as r:
                        els = json.loads(r.read().decode()).get("elements", [])
                    break
                except Exception:
                    continue
            if els is None:
                return ''
            
            parks = sum(1 for x in els if x.get("tags", {}).get("leisure") == "park")
            night = sum(1 for x in els
                        if x.get("tags", {}).get("amenity") in ("bar", "pub", "nightclub"))
            coles = sum(1 for x in els if x.get("tags", {}).get("amenity") == "school")
            bus = sum(1 for x in els if x.get("tags", {}).get("highway") == "bus_stop"
                      or x.get("tags", {}).get("public_transport") == "platform")
            e = {"ts": int(time.time()), "parks": parks, "night": night,
                 "coles": coles, "bus": bus}
            geo[key] = e
        except Exception:
            return ''
    if e.get("fail"):
        return ''
    return (f"🌳 {e['parks']} parques · 🍺 {e['night']} bares/fiesta · "
            f"🚌 {e['bus']} bus · 🏫 {e['coles']} coles (400m)")



# Criminalidad municipal 2024 (ene-sep), Balance de Criminalidad del Ministerio
# del Interior (hechos conocidos, criminalidad convencional + robos con fuerza
# en domicilios, variación % interanual). Fuente:
# https://estadisticasdecriminalidad.ses.mir.es/publico/portalestadistico/
# Solo existe a nivel municipio (>20.000 hab.); por barrio no hay dato en España.
SEGURIDAD_2024 = {
    "gijón":    {"total": "5.443", "var": "+1%",  "dom": "93",  "domvar": "-49%"},
    "oviedo":   {"total": "4.164", "var": "+4%",  "dom": "108", "domvar": "-30%"},
    "avilés":   {"total": "1.496", "var": "+3%",  "dom": "57",  "domvar": "+11%"},
    "langreo":  {"total": "848",   "var": "-8%",  "dom": "43",  "domvar": "-8%"},
    "mieres":   {"total": "647",   "var": "-10%", "dom": "15",  "domvar": "-53%"},
    "castrillón": {"total": "319", "var": "+15%", "dom": "8",   "domvar": "-27%"},
}


def seguridad_tag(town):
    e = SEGURIDAD_2024.get(norm_town(town))
    if not e:
        return ''
    return (f"🛡️ {town.strip()}: {e['total']} infracciones ({e['var']}) · "
            f"robos en vivienda {e['dom']} ({e['domvar']}) - Min. Interior 2024")



PISOS_PATH = "./data/pisos.json"
PISOS_MAX = 2000        # inventario durable de pisos vistos
CHOLLO_UMBRAL = 25.0    # % bajo la mediana de la ciudad para marcar CHOLLO


def load_pisos():
    try:
        with open(PISOS_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_pisos(ps):
    if len(ps) > PISOS_MAX:
        ps = dict(sorted(ps.items(), key=lambda kv: kv[1].get("ts", 0),
                         reverse=True)[:PISOS_MAX])
    with open(PISOS_PATH, "w") as f:
        json.dump(ps, f)


def es_chollo(zonas, price, m2, town):
    """True si el piso está >=CHOLLO_UMBRAL% bajo la mediana €/m² de su ciudad."""
    if not (isinstance(price, int) and isinstance(m2, int) and m2 >= 30
            and 5000 <= price):
        return False, None
    t = norm_town(town)
    e = zonas.get(t)
    if not e or len(e["samples"]) < ZONAS_MIN_MUESTRAS:
        return False, None
    samples = sorted(e["samples"])
    med = samples[len(samples) // 2]
    if med <= 0:
        return False, None
    diff = (med - price / m2) / med * 100
    return diff >= CHOLLO_UMBRAL, round(diff)


def update_pisos(pisos, flat, price, m2, town):
    href = str(flat.get('href', '') or '')
    if not href:
        return None
    e = pisos.get(href, {})
    e.update({"title": str(flat.get('title', '') or '')[:120],
              "price": price if isinstance(price, int) else e.get("price"),
              "m2": m2 or e.get("m2"),
              "town": town, "rooms": str(flat.get('rooms', '') or ''),
              "portal": flat.get('site', ''), "ts": int(time.time())})
    pisos[href] = e
    return e


def make_sig(price, m2, town, rooms, title):
    # Firma para dedup entre portales. Conservadora: exige precio+m2+ciudad+hab
    # iguales y buen solape de tokens del título.
    if not isinstance(price, int) or not m2:
        return None
    town_n = re.sub(r'[^a-z0-9áéíóúñ]', '', str(town).lower())
    rooms_n = ''.join(c for c in str(rooms) if c.isdecimal())
    tokens = sorted(set(re.sub(r'[^a-z0-9áéíóúñ ]', '', str(title).lower()).split())
                    - SIG_STOPWORDS)
    if not tokens:
        return None
    return {"k": [price, m2, town_n, rooms_n], "tt": tokens}


def sigs_match(a, b):
    if not a or not b or a["k"] != b["k"]:
        return False
    ta, tb_ = set(a["tt"]), set(b["tt"])
    if not ta or not tb_:
        return False
    return len(ta & tb_) / min(len(ta), len(tb_)) >= 0.6


def check_new_flats(json_file_name, scrapy_rs_name, min_price, max_price,
                    tg_chatID, telegram_msg, logger):
    """Detecta viviendas no vistas (contra data/ids.json) y bajadas de precio,
    y envía por Telegram las que entran en el rango de precio.
    Dedup 100% local, sin BD. Devuelve (nuevas enviadas, bajadas enviadas)."""
    tb = telebot.TeleBot(get_bot_token())
    ids = load_ids()
    zonas = load_zonas()
    geo = load_geo()
    pisos = load_pisos()
    sent_chollos = 0
    new_urls = []
    sent_drops = 0
    historic_sigs = [v.get("sig") for v in ids.values() if v.get("sig")]
    accepted_sigs = []

    try:
        with open(json_file_name) as json_file:
            data_json = json.load(json_file)
    except (FileNotFoundError, json.JSONDecodeError):
        data_json = []

    if len(data_json) == 0:
        logger.warning(f'SIN DATOS EN EL JSON {scrapy_rs_name.upper()}')

    for flat in data_json:
        try:
            flat_key = listing_key(flat)
        except (KeyError, TypeError, ValueError):
            continue

        # Historically ids.json used raw numeric IDs. Keep that key format
        # compatible, while the normalized key is used for new persistence.
        flat_id = str(flat.get("id") or flat_key)
        price_str = str(flat.get('price', ''))
        href = flat.get('href', '')
        title = str(flat.get('title', '') or '')
        town = str(flat.get('town', '') or '')
        rooms = str(flat.get('rooms', '') or '')

        price = numeric_price(price_str)
        m2 = numeric_price(flat.get('m2', ''))
        m2_tg = f'{m2}m²' if m2 else ''
        update_zonas(zonas, price, m2, town)
        inv = update_pisos(pisos, flat, price, m2, town)

        if price is None:
            continue

        try:
            within_range = (int(max_price) >= price >= int(min_price)
                            or (int(max_price) == 0 and price >= int(min_price)))
        except (ValueError, TypeError):
            within_range = False

        # Prefer the normalized key, but look up the legacy raw ID during
        # migration so existing users do not receive duplicate alerts.
        entry = ids.get(flat_key)
        if entry is None:
            entry = ids.get(flat_id)
        if entry is not None:
            # conocido: detectamos bajada de precio (p.ej. entra en presupuesto)
            old_price = entry.get("price")
            entry["ts"] = int(time.time())
            if isinstance(old_price, int) and isinstance(price, int) and price != old_price:
                entry["price"] = price
                if price < old_price and within_range and telegram_msg:
                    try:
                        tb.send_message(
                            tg_chatID,
                            f"🔻 <b>BAJADA: {old_price}€ → {price}€</b> [{m2_tg}]\n"
                            f"{html.escape(title)[:90]}\n"
                            f"{zona_tag(zonas, price, m2, town)}\n"
                    f"{geo_tag(geo, title, town)}\n"
                    f"{seguridad_tag(town)}\n"
                            f"{geo_tag(geo, title, town)}\n"
                            f"{seguridad_tag(town)}\n"
                            f"{html.escape(href)}",
                            parse_mode='HTML')
                        sent_drops += 1
                        if inv is not None:
                            ch, diffc = es_chollo(zonas, price, m2, town)
                            if ch and not inv.get("chollo"):
                                inv["chollo"] = True
                                try:
                                    tb.send_message(
                                        tg_chatID,
                                        f"🏆 <b>CHOLLO POR BAJADA: {diffc}% bajo la media de {town.strip()}</b>\n"
                                        f"{html.escape(title)[:90]}\n"
                                        f"{html.escape(href)}",
                                        parse_mode='HTML',
                                        disable_web_page_preview=True)
                                    sent_chollos += 1
                                except telebot.apihelper.ApiTelegramException:
                                    pass
                    except telebot.apihelper.ApiTelegramException as e:
                        logger.error(f'ERROR ENVIANDO A TELEGRAM: {e}')
                    time.sleep(3.05)
            elif isinstance(price, int) and not isinstance(old_price, int):
                entry["price"] = price
            continue

        # nuevo: dedup inter-portal por firma (precio+m2+ciudad+hab+título)
        sig = make_sig(price, m2, town, rooms, title)
        ids[flat_key] = {"price": price,
                        "ts": int(time.time()),
                        "portal": flat.get('site', ''),
                        "sig": sig}

        # "A consultar": lo damos por visto pero no lo enviamos
        if price in ('Aconsultar', 'A consultar'):
            continue

        if sig and any(sigs_match(sig, s2) for s2 in accepted_sigs + historic_sigs):
            logger.info(f'DUP INTER-PORTAL (mismo inmueble en otro portal): {href}')
            continue

        if within_range and telegram_msg:
            new_urls.append(href)
            accepted_sigs.append(sig)
            try:
                avg_price_m2 = '%.2f' % (price / float(m2)) if m2 else ''
            except (ValueError, ZeroDivisionError, TypeError):
                avg_price_m2 = ''
            zone = ' · '.join(x for x in (town.strip(), rooms.strip()) if x)
            try:
                tb.send_message(
                    tg_chatID,
                    f"<b>{price_str}</b> [{m2_tg}] → {avg_price_m2}€/m²\n"
                    f"{html.escape(title)[:90]}\n"
                    f"{html.escape(zone)}\n"
                    f"{zona_tag(zonas, price, m2, town)}\n"
                    f"{html.escape(href)}",
                    parse_mode='HTML')
            except telebot.apihelper.ApiTelegramException as e:
                logger.error(f'ERROR ENVIANDO A TELEGRAM: {e}')
            time.sleep(3.05)
            if inv is not None:
                ch, diffc = es_chollo(zonas, price, m2, town)
                if ch and not inv.get("chollo"):
                    inv["chollo"] = True
                    try:
                        tb.send_message(
                            tg_chatID,
                            f"🏆 <b>CHOLLO: {diffc}% bajo la media de {town.strip()}</b>\n"
                            f"{html.escape(title)[:90]}\n"
                            f"{html.escape(href)}",
                            parse_mode='HTML',
                            disable_web_page_preview=True)
                        sent_chollos += 1
                    except telebot.apihelper.ApiTelegramException:
                        pass
                    time.sleep(3.05)

    save_ids(ids)
    save_zonas(zonas)
    save_geo(geo)
    save_pisos(pisos)

    # solo a INFO si hay nuevas; si no, a DEBUG
    if new_urls or sent_drops:
        logger.info(f"NUEVAS: {len(new_urls)} | BAJADAS: {sent_drops} | "
                    f"TOTAL: {len(data_json)} -> {new_urls}")
    else:
        logger.debug(f"NUEVAS: 0 | TOTAL: {len(data_json)}")

    logger.info(f"CHOLLOS ENVIADOS: {sent_chollos}") if sent_chollos else None
    return len(new_urls), sent_drops


def run_spider(spider_name, scrapy_log, out_file, start_url):
    # Lista de args (sin shell): las URLs con '?'/'&' no rompen la línea de comandos.
    cmd = ["scrapy", "crawl", "-L", scrapy_log, spider_name,
           "-o", out_file, "-a", f"start_urls={start_url}"]
    result = subprocess.run(cmd, check=False)
    return result.returncode


def page2_url(portal_name_url, url):
    # Página 2 por portal (mejor esfuerzo: un fallo aquí NO cuenta para la salud).
    if portal_name_url == 'idealista.com':
        return url + 'pagina-2.htm?ordenado-por=fecha-publicacion-desc'
    if portal_name_url == 'pisos.com':
        return url + '/fecharecientedesde-desc/pagina-2/'
    if portal_name_url == 'fotocasa.es':
        if '?' in url:
            base, q = url.split('?', 1)
            return base + '/2?' + q
        return url + '/2'
    if portal_name_url == 'yaencontre.com':
        return url + '/o-recientes/pagina-2'
    if portal_name_url == 'habitaclia.com':
        return url + '?ordenar=mas_recientes&pagina=2'
    return None


def scrap_realestate(telegram_msg):
    scrapy_rs_name = data['scrapy_rs_name'].replace("-", "_")
    scrapy_log = data['log_level_scrapy'].upper()
    proxy_idealista = data['proxy_idealista']
    out_file = f"./data/{scrapy_rs_name}.json"
    tb = telebot.TeleBot(get_bot_token())

    # todas las claves 'url_*' de la config
    urls = []
    for key in data:
        if "url" in key and isinstance(data[key], list):
            urls += data[key]
        elif "url" in key:
            urls.append(data[key])

    urls_mixed = mix_list(urls)

    process = subprocess.run(["scrapy", "list"], capture_output=True)
    if process.returncode != 0:
        logger.error("SPIDERS NOT DETECTED")
        sys.exit()

    portal_counts = {}

    for url in urls_mixed:
        if url == '':
            continue

        portal_url = url.split('/')[2]
        portal_name = portal_url.split('.')[1]
        try:
            portal_name_url = portal_url.split('.')[1] + '.' + portal_url.split('.')[2]
        except IndexError:
            portal_name = portal_url
            portal_name_url = ''

        if portal_name_url == 'idealista.com':
            spider = 'idealista_proxy' if proxy_idealista == 'on' else 'idealista'
            page1 = url + '?ordenado-por=fecha-publicacion-desc'
        elif portal_name_url == 'pisos.com':
            spider, page1 = 'pisoscom', url + '/fecharecientedesde-desc/'
        elif portal_name_url == 'fotocasa.es':
            spider, page1 = 'fotocasa', url
        elif portal_name_url == 'habitaclia.com':
            spider, page1 = 'habitaclia', url + '?ordenar=mas_recientes'
        elif portal_name_url == 'yaencontre.com':
            spider, page1 = 'yaencontre', url + '/o-recientes'
        else:
            continue

        if proxy_idealista == 'on' and portal_name_url == 'idealista.com':
            logger.debug('IDEALISTA PROXY ACTIVATED')

        logger.debug(f"SCRAPING PORTAL {portal_name_url} FROM {scrapy_rs_name}...")

        # cada portal/página va a su propio tmp: permite salud por portal y merge limpio
        portal_items = 0
        tmp1 = f"./data/.tmp_{portal_name}_p1.json"
        os.path.exists(tmp1) and os.remove(tmp1)
        run_spider(spider, scrapy_log, tmp1, page1)
        portal_items += count_items(tmp1)

        p2 = page2_url(portal_name_url, url)
        if p2:
            tmp2 = f"./data/.tmp_{portal_name}_p2.json"
            os.path.exists(tmp2) and os.remove(tmp2)
            run_spider(spider, scrapy_log, tmp2, p2)
            portal_items += count_items(tmp2)

        portal_counts[portal_name_url] = portal_items
        update_health(portal_name_url, portal_items > 0, tb, data['telegram_chatuserID'])
        logger.debug(f"CRAWLED {portal_name.upper()} ({portal_items} items)")

    # merge de todos los tmp en el fichero del ciclo
    merged = []
    for f in os.listdir('./data'):
        if f.startswith('.tmp_') and f.endswith('.json'):
            merged += load_items(f'./data/{f}')
            os.remove(f'./data/{f}')
    with open(out_file, 'w') as file:
        json.dump(merged, file)

    if not merged:
        logger.warning(f"NO SE GENERARON RESULTADOS EN ESTE CICLO")
        return

    sent_new, sent_drops = check_new_flats(out_file,
                                           scrapy_rs_name,
                                           data['min_price'],
                                           data['max_price'],
                                           data['telegram_chatuserID'],
                                           telegram_msg,
                                           logger)
    write_status(portal_counts, sent_new, sent_drops)


def count_items(path):
    return len(load_items(path))


def load_items(path):
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def update_useragent():
    try:
        os.remove('./data/useragent.txt')
    except FileNotFoundError:
        pass
    try:
        ua = UserAgent(platforms='pc', os=['windows', 'macos'])
        useragent = ua.chrome
    except Exception as e:
        logger.warning(f'fake-useragent falló ({e}); usando User-Agent de reserva')
        useragent = FALLBACK_USER_AGENT
    with open('./data/useragent.txt', 'w') as f:
        f.write(useragent)


def init():
    tprint("scrapyrealestate")
    print(f'scrapyrealestate v{__version__}')

    get_config()
    init_logs()
    checks()

    count = 0
    telegram_msg = False
    scrapy_rs_name = data['scrapy_rs_name'].replace("-", "_")
    send_first = data['send_first']

    while True:
        try:
            os.remove(f"./data/{scrapy_rs_name}.json")
        except FileNotFoundError:
            pass

        # renovamos el User-Agent cada 10 ciclos
        if count % 10 == 0:
            logger.debug('Renovando User-Agent')
            update_useragent()

        # send_first envía ya en el primer ciclo; si no, solo a partir del segundo
        if send_first == 'True' or count > 0:
            telegram_msg = True

        scrap_realestate(telegram_msg)

        count += 1
        rndtime = random.randint(3, 40) + int(data['time_update'])
        logger.info(f"SLEEPING {rndtime} SECONDS")
        time.sleep(rndtime)


if __name__ == "__main__":
    init()
