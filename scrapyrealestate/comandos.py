# Interfaz de comandos en lenguaje natural por Telegram.
# Nico habla con el bot (privado, grupo o el propio canal) y cambia la
# config en caliente: precios, municipios, portales, ciclos y consultas.
# Parser determinista en español; si en config hay llm_key se puede
# enchufar un LLM OpenAI-compatible como paso previo (vacío por defecto).
import json
import os
import re
import time
import unicodedata

CONFIG_PATH = "./data/config.json"
OWNER_PATH = "./data/telegram_owner.json"     # {user_id, nombre}
OFFSET_PATH = "./data/telegram_offset.json"   # offset de get_updates
FORCE_PATH = "./data/.force_cycle"            # flag para ciclo inmediato

# nombre corto -> dominio del portal
PORTALES = {"idealista": "idealista.com", "pisos": "pisos.com",
            "pisoscom": "pisos.com", "fotocasa": "fotocasa.es",
            "yaencontre": "yaencontre.com", "habitaclia": "habitaclia.com"}

# slugs que no siguen la regla general
SLUG_PC = {"gijon": "pisos-gijon_concejo_xixon_conceyu_gijon"}
SLUG_FC = {"mieres": "mieres-asturias"}
SLUG_ID = {"gijon": "gijon-gijon", "oviedo": "oviedo-oviedo"}


def norm(s):
    s = unicodedata.normalize("NFD", str(s).lower().strip())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def slug(nombre, sep="-"):
    return re.sub(r"\s+", sep, norm(nombre))


def regenerar_urls(cfg):
    """Reconstruye las url_* a partir de municipios + max_price."""
    maxp = str(cfg.get("max_price", "110000"))
    pc, fc, ye, idl, hab = [], [], [], [], []
    for t in cfg.get("municipios", []):
        nb = slug(t, "-")
        pc_s = SLUG_PC.get(nb, "pisos-" + slug(t, "_"))
        fc_s = SLUG_FC.get(nb, nb)
        id_s = SLUG_ID.get(nb, nb)
        pc.append(f"https://www.pisos.com/venta/{pc_s}/ascensor/hasta-{maxp}")
        fc.append("https://www.fotocasa.es/es/comprar/viviendas/"
                  f"{fc_s}/todas-las-zonas/ascensor/l"
                  "?sortType=publicationDate&sortOrderDesc=true")
        ye.append(f"https://www.yaencontre.com/venta/pisos/{nb}/f-ascensor")
        idl.append("https://www.idealista.com/venta-viviendas/"
                   f"{id_s}/con-precio-hasta_{maxp},ascensor/")
        hab.append(f"https://www.habitaclia.com/viviendas-{nb}.htm")
    cfg["url_pisoscom"] = pc
    cfg["url_fotocasa"] = fc
    cfg["url_yaencontre"] = ye
    cfg["url_idealista"] = idl
    cfg["url_habitaclia"] = hab


def sembrar_config(cfg):
    """Claves nuevas con valores por defecto (no pisa nada existente)."""
    cfg.setdefault("municipios", ["Gijón", "Oviedo", "Mieres", "Siero"])
    cfg.setdefault("portales_off", [])          # no se scrapean
    cfg.setdefault("portales_silenciados", [])  # se scrapean sin avisos de salud
    cfg.setdefault("llm_key", "")               # opcional: OpenAI-compatible
    cfg.setdefault("llm_base_url", "")
    cfg.setdefault("llm_model", "")


def guardar_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def parse_numero(txt, sufijo):
    n = txt.replace(".", "").replace(",", "").strip()
    try:
        v = int(float(n))
    except ValueError:
        return None
    if sufijo and sufijo.lower() in ("k", "mil"):
        v *= 1000
    return v if v >= 1000 else None


NUM = r"(\d[\d\.,]*)\s*(mil|k|€|eur|euros|pavos)?"


def parse_comando(texto):
    """Español libre -> (accion, params). Devuelve ('desconocido', {}) si no lo ve."""
    t = norm(texto)
    # portales mencionados por nombre corto
    def portal_en(t):
        for nombre in PORTALES:
            if re.search(rf"\b{nombre}\b", t):
                return nombre
        return None

    if re.search(r"\b(ayuda|help|comandos|que puedes)\b", t):
        return "ayuda", {}
    if re.search(r"\b(chollos?|gangas?|mejores|top)\b", t):
        return "chollos", {}
    if re.search(r"\b(estado|como vas|status|resumen)\b", t):
        return "estado", {}
    if re.search(r"\b(ciclo|busca ahora|buscar ahora|actualiza|refresca)\b", t):
        return "ciclo", {}

    m = re.search(r"\b(silencia|silenciar)\b\s*(\w+)?", t)
    if m:
        p = portal_en(t)
        if p:
            return "silenciar", {"portal": p}
    m = re.search(r"\b(quita los avisos|sin avisos)\b", t)
    if m:
        p = portal_en(t)
        if p:
            return "silenciar", {"portal": p}
    if re.search(r"\b(activa|enciende|reactiva)\b", t):
        p = portal_en(t)
        if p:
            return "activar", {"portal": p}
    if re.search(r"\b(apaga|desactiva)\b", t):
        p = portal_en(t)
        if p:
            return "apagar", {"portal": p}

    m = re.search(r"\b(?:minimo|min|desde)\b\D{0,15}" + NUM, t)
    if m:
        v = parse_numero(m.group(1), m.group(2))
        if v is not None:
            return "precio_min", {"valor": v}
    m = re.search(r"\b(?:maximo|max|tope|hasta|precio|presupuesto)\b\D{0,15}" + NUM, t)
    if m:
        v = parse_numero(m.group(1), m.group(2))
        if v is not None:
            return "precio_max", {"valor": v}

    m = re.search(r"\b(anade|anadir|agrega|mete|incluye|suma)\b\s+(?:a\s+)?([a-zñ][a-zñ \-]*?)\s*$", t)
    if m:
        p = PORTALES.get(m.group(2).strip())
        if p:
            return "activar", {"portal": m.group(2).strip()}
        return "municipio_add", {"nombre": m.group(2).strip()}
    m = re.search(r"\b(quita|quitar|elimina|saca|borra)\b\s+(?:de\s+|a\s+)?([a-zñ][a-zñ \-]*?)\s*$", t)
    if m:
        nombre = m.group(2).strip()
        if nombre in PORTALES:
            return "apagar", {"portal": nombre}
        return "municipio_del", {"nombre": nombre}
    return "desconocido", {}


def fmt_eur(v):
    return f"{int(v):,}€".replace(",", ".")


def mediana(lst):
    lst = sorted(lst)
    return lst[len(lst) // 2] if lst else None


def chollos_actuales(top=5, umbral=25.0):
    """Top chollos del inventario: % bajo la mediana €/m² de su ciudad."""
    try:
        pisos = json.load(open("./data/pisos.json"))
        zonas = json.load(open("./data/zonas.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    meds = {}
    for t, e in zonas.items():
        if len(e.get("samples", [])) >= 20:
            meds[t] = mediana(e["samples"])
    out = []
    for href, e in pisos.items():
        price, m2 = e.get("price"), e.get("m2")
        if not (isinstance(price, int) and isinstance(m2, int) and m2 >= 30):
            continue
        med = meds.get(norm(e.get("town", "")))
        if not med or med <= 0:
            continue
        diff = (med - price / m2) / med * 100
        if diff >= umbral:
            out.append((round(diff), e, href))
    out.sort(key=lambda x: -x[0])
    return out[:top]


def texto_chollos():
    top = chollos_actuales()
    if not top:
        return ("No tengo chollos claros ahora mismo (nada ≥25% bajo la "
                "mediana de su ciudad). Te aviso en cuanto salga uno 🏆")
    lineas = ["🏆 <b>CHOLLOS AHORA</b> (vs mediana de su ciudad):"]
    for diff, e, href in top:
        zona = e.get("town", "").strip()
        m2 = e.get("m2")
        lineas.append(
            f"• <b>{fmt_eur(e['price'])}</b> · {m2}m² · {zona} · -{diff}%\n{href}")
    return "\n".join(lineas)


def texto_estado(cfg):
    try:
        st = json.load(open("./data/status.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        st = {}
    counts = st.get("portal_counts", {})
    salud = st.get("health", {})
    lineas = [f"📊 <b>Estado</b> · hasta {fmt_eur(cfg.get('max_price', 0))}"
              f" · min {fmt_eur(cfg.get('min_price', 0))}",
              "🏘️ " + ", ".join(cfg.get("municipios", []))]
    for portal, n in counts.items():
        corto = portal.split(".")[0]
        if corto in cfg.get("portales_off", []):
            lineas.append(f"🔇 {portal}: apagado")
        elif n == 0:
            lineas.append(f"⚠️ {portal}: 0 items (bloqueado o sin resultados)")
        else:
            lineas.append(f"✅ {portal}: {n} items/ciclo")
    lineas.append(f"Último ciclo: {st.get('last_cycle', '?')}"
                  f" · nuevos enviados: {st.get('sent_new', 0)}")
    return "\n".join(lineas)


AYUDA = ("Puedes hablarme normal. Entiendo cosas como:\n"
         "• «máximo 90.000» / «mínimo 50k» — cambia el presupuesto\n"
         "• «añade Avilés» / «quita Mieres» — cambia los municipios\n"
         "• «apaga idealista» / «activa yaencontre» — portales on/off\n"
         "• «silencia idealista» — sin avisos de salud de ese portal\n"
         "• «busca ahora» — fuerza un ciclo al momento\n"
         "• «estado» — cómo va todo\n"
         "• «chollos» — los mejores pisos vistos\n"
         "Todo lo que cambie te lo confirmo aquí mismo.")


def ejecutar(tb, chat_id, accion, params, cfg):
    """Aplica la accion sobre cfg (persistiendo) y responde en chat_id."""
    if accion == "ayuda":
        tb.send_message(chat_id, AYUDA, disable_web_page_preview=True)
    elif accion == "estado":
        tb.send_message(chat_id, texto_estado(cfg), parse_mode="HTML",
                        disable_web_page_preview=True)
    elif accion == "chollos":
        tb.send_message(chat_id, texto_chollos(), parse_mode="HTML",
                        disable_web_page_preview=True)
    elif accion == "ciclo":
        open(FORCE_PATH, "w").write("1")
        tb.send_message(chat_id, "🔄 Vale, ciclo forzado: en cuanto termine el "
                        "actual (o en segundos si está durmiendo) busco.")
    elif accion == "precio_max":
        cfg["max_price"] = str(params["valor"])
        regenerar_urls(cfg)
        guardar_config(cfg)
        tb.send_message(chat_id, f"✅ Presupuesto máximo: {fmt_eur(params['valor'])}. "
                        "URLs de los portales actualizadas.")
    elif accion == "precio_min":
        cfg["min_price"] = str(params["valor"])
        guardar_config(cfg)
        tb.send_message(chat_id, f"✅ Precio mínimo: {fmt_eur(params['valor'])}.")
    elif accion == "municipio_add":
        nombre = params["nombre"].strip().title()
        towns = cfg.setdefault("municipios", [])
        if any(norm(t) == norm(nombre) for t in towns):
            tb.send_message(chat_id, f"{nombre} ya está en la lista.")
        else:
            towns.append(nombre)
            regenerar_urls(cfg)
            guardar_config(cfg)
            tb.send_message(chat_id, f"✅ Añadido {nombre}. Ahora busco en: "
                            + ", ".join(towns))
    elif accion == "municipio_del":
        nombre = params["nombre"]
        towns = cfg.get("municipios", [])
        nueva = [t for t in towns if norm(t) != norm(nombre)]
        if len(nueva) == len(towns):
            tb.send_message(chat_id, f"{nombre.title()} no estaba en la lista.")
        elif not nueva:
            tb.send_message(chat_id, "No puedo quedarme sin municipios: "
                            "añade otro antes de quitar este.")
        else:
            cfg["municipios"] = nueva
            regenerar_urls(cfg)
            guardar_config(cfg)
            tb.send_message(chat_id, f"✅ Quitado {nombre.title()}. Ahora busco en: "
                            + ", ".join(nueva))
    elif accion == "apagar":
        p = params["portal"]
        off = cfg.setdefault("portales_off", [])
        if p not in off:
            off.append(p)
            guardar_config(cfg)
        tb.send_message(chat_id, f"🔇 {p} apagado: no lo scrapeo más. "
                        "«Activa " + p + "» para volver.")
    elif accion == "activar":
        p = params["portal"]
        cfg["portales_off"] = [x for x in cfg.get("portales_off", []) if x != p]
        cfg["portales_silenciados"] = [x for x in cfg.get("portales_silenciados", [])
                                       if x != p]
        guardar_config(cfg)
        tb.send_message(chat_id, f"✅ {p} activo otra vez (y con avisos).")
    elif accion == "silenciar":
        p = params["portal"]
        sil = cfg.setdefault("portales_silenciados", [])
        if p not in sil:
            sil.append(p)
            guardar_config(cfg)
        tb.send_message(chat_id, f"🤫 {p} silenciado: sigo intentándolo pero "
                        "sin avisos de salud en el canal.")
    else:
        tb.send_message(chat_id, "No te he entendido 🤔. Escribe «ayuda» y te "
                        "digo lo que sé hacer.")


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def es_duenio(msg, cfg):
    """Control de acceso: solo el dueño (su user_id de Telegram).
    Primer mensaje privado/grupo lo registra como dueño. Los mensajes del
    canal (channel_post) los acepta solo si vienen del canal configurado."""
    chat = msg.chat
    if getattr(msg, "sender_chat", None) is not None and msg.from_user is None:
        # post de canal: solo el canal configurado; quien postea ahí es admin
        return str(chat.id) == str(cfg.get("telegram_chatuserID"))
    uid = getattr(msg.from_user, "id", None)
    if uid is None:
        return False
    owner = _load_json(OWNER_PATH, {})
    if not owner.get("user_id"):
        nombre = getattr(msg.from_user, "first_name", "") or ""
        with open(OWNER_PATH, "w") as f:
            json.dump({"user_id": uid, "nombre": nombre}, f)
        return True
    return uid == owner.get("user_id")


def bucle_telegram(token, cfg):
    """Hilo de escucha: get_updates en largo; procesa comandos del dueño."""
    import telebot
    tb = telebot.TeleBot(token)
    offset = _load_json(OFFSET_PATH, {}).get("offset", 0)
    while True:
        try:
            updates = tb.get_updates(offset=offset, timeout=25,
                                     allowed_updates=["message", "channel_post"])
            for upd in updates:
                offset = upd.update_id + 1
                msg = upd.message or upd.channel_post
                if msg is None or not getattr(msg, "text", None):
                    continue
                if not es_duenio(msg, cfg):
                    continue
                accion, params = parse_comando(msg.text)
                ejecutar(tb, msg.chat.id, accion, params, cfg)
            if updates:
                with open(OFFSET_PATH, "w") as f:
                    json.dump({"offset": offset}, f)
        except Exception:
            time.sleep(10)
        time.sleep(1)
