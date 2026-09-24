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
USERS_PATH = "./data/telegram_users.json"     # {autorizados, pendientes, avisados}
PETICIONES_PATH = "./data/peticiones.json"    # mensajes/peticiones a relatar
RESPUESTAS_PATH = "./data/respuestas.json"    # respuestas del equipo a usuarios
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
    cfg.setdefault("tunel_email", "")             # email push del tunel (formsubmit)


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

    m = re.search(r"\b(autoriza|autorizar|aprueba|aprobar|admite)\b\s+(?:a\s+)?(@?[\w]+)", t)
    if m:
        return "usuario_add", {"ref": m.group(2)}
    if re.search(r"^\s*(autoriza|autorizar|aprueba|aprobar|admite)\s*$", t):
        return "usuario_add", {"ref": None}   # bare: vale si hay 1 pendiente
    m = re.search(r"\b(rechaza|rechazar|deniega|denegar|bloquea)\b\s+(?:a\s+)?(@?[\w]+)", t)
    if m:
        return "usuario_rechaza", {"ref": m.group(2)}
    if re.search(r"^\s*(rechaza|rechazar|deniega|denegar|bloquea)\s*$", t):
        return "usuario_rechaza", {"ref": None}
    if re.search(r"\b(pendientes|solicitudes)\b", t):
        return "pendientes", {}
    if re.search(r"\b(usuarios|autorizados)\b", t):
        return "usuarios", {}

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
    m = re.search(r"\b(quita|quitar|elimina|saca|borra)\b\s+(?:de\s+|a\s+)?(@?\w[\w \-]*?)\s*$", t)
    if m:
        nombre = m.group(2).strip()
        if nombre.startswith("@") or nombre.isdigit():
            return "usuario_del", {"ref": nombre}
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
    u = cargar_usuarios()
    lineas.append(f"👥 {len(u['autorizados'])} autorizados · "
                  f"{len(u['pendientes'])} pendientes")
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
         "• «usuarios» / «pendientes» - quién tiene acceso\n"
         "• Solo el dueño: «autoriza 123456789», «quita a @usuario»,\n"
         "  «rechaza @usuario» - gestiona quién puede hablarme\n"
         "Todo lo que cambie te lo confirmo aquí mismo.\n"
         "Y si me escribes cualquier otra cosa, se lo paso al equipo\n"
         "y te contestan por aquí en unos minutos 🤝.")


def ejecutar(tb, chat_id, accion, params, cfg, nivel="owner"):
    """Aplica la accion sobre cfg (persistiendo) y responde en chat_id."""
    if accion in ("usuario_add", "usuario_del", "usuario_rechaza") \
            and nivel not in ("owner", "canal", "admin"):
        tb.send_message(chat_id, "Eso solo puede hacerlo el dueño 👑.")
        return
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
    elif accion == "usuario_add":
        usuarios_add(tb, chat_id, params["ref"])
    elif accion == "usuario_del":
        usuarios_quita(tb, chat_id, params["ref"])
    elif accion == "usuario_rechaza":
        usuarios_rechaza(tb, chat_id, params["ref"])
    elif accion == "pendientes":
        tb.send_message(chat_id, texto_pendientes())
    elif accion == "usuarios":
        tb.send_message(chat_id, texto_usuarios())
    else:
        tb.send_message(chat_id, "No te he entendido 🤔. Escribe «ayuda» y te "
                        "digo lo que sé hacer.")


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def cargar_usuarios():
    u = _load_json(USERS_PATH, {})
    u.setdefault("autorizados", [])
    u.setdefault("pendientes", [])
    u.setdefault("avisados", [])   # user_ids ya notificados al dueño
    return u


def guardar_usuarios(u):
    with open(USERS_PATH, "w") as f:
        json.dump(u, f, ensure_ascii=False, indent=2)


def resolver_ref(ref, lista):
    """ref puede ser id numerico, @username o nombre; busca en la lista."""
    r = str(ref).lstrip("@").strip().lower()
    for u in lista:
        if r and r == str(u.get("user_id", "")):
            return u
        if r and r == str(u.get("username", "")).lower():
            return u
        if r and norm(u.get("nombre", "")) == norm(r):
            return u
    return None


def nivel_acceso(msg, cfg):
    """Devuelve (nivel, user_id): 'canal' (post del canal configurado),
    'owner', 'user' (autorizado), 'sin_owner' (aun no hay dueño) o
    None (desconocido: pendiente de aprobacion)."""
    chat = msg.chat
    if getattr(msg, "sender_chat", None) is not None and msg.from_user is None:
        # post de canal: solo el canal configurado; quien postea ahi es admin
        if str(chat.id) == str(cfg.get("telegram_chatuserID")):
            return "canal", None
        return None, None
    uid = getattr(msg.from_user, "id", None)
    if uid is None:
        return None, None
    owner = _load_json(OWNER_PATH, {})
    if not owner.get("user_id"):
        return "sin_owner", uid
    if uid == owner.get("user_id"):
        return "owner", uid
    users = cargar_usuarios()
    encontrado = resolver_ref(uid, users["autorizados"])
    if not encontrado:
        # preautorizado por @username sin id: se vincula en su primer mensaje
        uname = getattr(msg.from_user, "username", "") or ""
        if uname:
            candidato = resolver_ref("@" + uname, users["autorizados"])
            if candidato and not candidato.get("user_id"):
                candidato["user_id"] = uid
                candidato["nombre"] = (getattr(msg.from_user, "first_name", "")
                                       or "")
                guardar_usuarios(users)
                encontrado = candidato
    if encontrado:
        return ("admin" if encontrado.get("rol") == "admin" else "user"), uid
    return None, uid


def registrar_dueno(tb, msg, cfg):
    """El primer remitente privado/grupo queda registrado como dueño."""
    uid = msg.from_user.id
    nombre = getattr(msg.from_user, "first_name", "") or ""
    with open(OWNER_PATH, "w") as f:
        json.dump({"user_id": uid, "nombre": nombre}, f)
    aviso = (f"👑 Dueño registrado: {nombre} (id {uid}). "
             "Solo respondo a ti y a quien autorices.")
    tb.send_message(msg.chat.id, aviso)
    canal = cfg.get("telegram_chatuserID")
    if canal and str(msg.chat.id) != str(canal):
        try:
            tb.send_message(canal, aviso)
        except Exception:
            pass


def gestionar_desconocido(tb, msg):
    """Alguien sin acceso escribe al bot: queda pendiente y se avisa al dueño."""
    uid = msg.from_user.id
    nombre = getattr(msg.from_user, "first_name", "") or ""
    username = getattr(msg.from_user, "username", "") or ""
    u = cargar_usuarios()
    if not resolver_ref(uid, u["pendientes"]):
        u["pendientes"].append({"user_id": uid, "nombre": nombre,
                                "username": username})
        guardar_usuarios(u)
    owner = _load_json(OWNER_PATH, {})
    if owner.get("user_id") and uid not in u["avisados"]:
        try:
            tb.send_message(owner["user_id"],
                            f"👤 {nombre} (@{username or '-'}, id {uid}) "
                            "quiere usar el bot. Responde "
                            f"«autoriza {uid}» o «rechaza {uid}».")
            u["avisados"].append(uid)
            guardar_usuarios(u)
        except Exception:
            pass
    tb.send_message(msg.chat.id,
                    "Hola 👋. Este bot es privado: he dejado tu solicitud "
                    "al dueño y te aviso aquí mismo si te autoriza.")


def _unico_pendiente(tb, chat_id, u, verbo):
    if len(u["pendientes"]) == 1:
        return u["pendientes"][0]
    if not u["pendientes"]:
        tb.send_message(chat_id, "No hay solicitudes pendientes.")
    else:
        tb.send_message(chat_id, f"Hay {len(u['pendientes'])} pendientes: dime "
                        f"cuál («{verbo} 123456789» o «{verbo} @usuario»).\n"
                        + texto_pendientes())
    return None


def usuarios_add(tb, chat_id, ref):
    u = cargar_usuarios()
    if ref is None:
        encontrado = _unico_pendiente(tb, chat_id, u, "autoriza")
        if not encontrado:
            return
    else:
        encontrado = resolver_ref(ref, u["pendientes"])
    if encontrado:
        u["pendientes"] = [x for x in u["pendientes"] if x is not encontrado]
        if not resolver_ref(encontrado["user_id"], u["autorizados"]):
            u["autorizados"].append(encontrado)
        guardar_usuarios(u)
        tb.send_message(chat_id, f"✅ {encontrado.get('nombre') or ref} "
                        "autorizado. Ya puede hablarme.")
        try:
            tb.send_message(encontrado["user_id"],
                            "✅ Acceso concedido: ya puedes hablarme. "
                            "Escribe «ayuda» para ver lo que sé hacer.")
        except Exception:
            pass
        return
    r = str(ref or "").lstrip("@").strip()
    if r.isdigit():
        if resolver_ref(r, u["autorizados"]):
            tb.send_message(chat_id, "Ese id ya estaba autorizado.")
            return
        u["autorizados"].append({"user_id": int(r), "nombre": "",
                                 "username": ""})
        guardar_usuarios(u)
        tb.send_message(chat_id, f"✅ Autorizado el id {r}.")
        try:
            tb.send_message(int(r), "✅ Acceso concedido: ya puedes hablarme. "
                            "Escribe «ayuda» para ver lo que sé hacer.")
        except Exception:
            pass
        return
    tb.send_message(chat_id, f"No tengo ninguna solicitud de {ref}. Telegram "
                    "no me deja resolver usuarios que no me han escrito: "
                    "pídele que me hable primero por privado y repite "
                    f"«autoriza {ref}», o dame su id numérico "
                    "(«autoriza 123456789»).")


def usuarios_quita(tb, chat_id, ref):
    u = cargar_usuarios()
    encontrado = resolver_ref(ref, u["autorizados"])
    if not encontrado:
        tb.send_message(chat_id, f"{ref} no estaba autorizado.")
        return
    u["autorizados"] = [x for x in u["autorizados"] if x is not encontrado]
    guardar_usuarios(u)
    tb.send_message(chat_id, f"🚫 Acceso quitado a "
                    f"{encontrado.get('nombre') or ref}.")
    try:
        tb.send_message(encontrado["user_id"],
                        "Te han quitado el acceso a este bot.")
    except Exception:
        pass


def usuarios_rechaza(tb, chat_id, ref):
    u = cargar_usuarios()
    if ref is None:
        encontrado = _unico_pendiente(tb, chat_id, u, "rechaza")
        if not encontrado:
            return
    else:
        encontrado = resolver_ref(ref, u["pendientes"])
    if not encontrado:
        tb.send_message(chat_id, f"No hay ninguna solicitud pendiente de {ref}.")
        return
    u["pendientes"] = [x for x in u["pendientes"] if x is not encontrado]
    u["avisados"] = [x for x in u["avisados"] if x != encontrado.get("user_id")]
    guardar_usuarios(u)
    tb.send_message(chat_id, f"🚫 Solicitud de "
                    f"{encontrado.get('nombre') or ref} rechazada.")


def texto_pendientes():
    u = cargar_usuarios()
    if not u["pendientes"]:
        return "Sin solicitudes pendientes."
    lineas = ["⏳ Pendientes de autorizar:"]
    for p in u["pendientes"]:
        lineas.append(f"• {p.get('nombre') or '?'} (@{p.get('username') or '-'}, "
                      f"id {p.get('user_id')}) - «autoriza {p.get('user_id')}» "
                      f"o «rechaza {p.get('user_id')}»")
    return "\n".join(lineas)


def texto_usuarios():
    owner = _load_json(OWNER_PATH, {})
    u = cargar_usuarios()
    lineas = [f"👑 Dueño: {owner.get('nombre', '?')} "
              f"(id {owner.get('user_id', '?')})"]
    if u["autorizados"]:
        lineas.append("✅ Autorizados:")
        for a in u["autorizados"]:
            rol = " (admin)" if a.get("rol") == "admin" else ""
            lineas.append(f"• {a.get('nombre') or '?'} "
                          f"(@{a.get('username') or '-'}, "
                          f"id {a.get('user_id') or 'pendiente de entrar'}){rol}")
    else:
        lineas.append("Sin usuarios autorizados.")
    if u["pendientes"]:
        lineas.append(f"⏳ Pendientes: {len(u['pendientes'])}")
    return "\n".join(lineas)


def notificar_email(msg, cfg):
    """Aviso push por email (formsubmit) para bajar la latencia del tunel.
    Fire-and-forget: si falla, la recogida periodica sigue como respaldo."""
    destino = cfg.get("tunel_email")
    if not destino:
        return
    import urllib.request
    datos = json.dumps({
        "_subject": f"BOT-PISOS mensaje de "
                    f"{getattr(msg.from_user, 'first_name', '') or '?'}",
        "de_id": msg.from_user.id,
        "de_nombre": getattr(msg.from_user, "first_name", "") or "",
        "de_username": getattr(msg.from_user, "username", "") or "",
        "texto": msg.text,
    }).encode()
    req = urllib.request.Request(
        f"https://formsubmit.co/ajax/{destino}",
        data=datos,
        headers={"Content-Type": "application/json",
                 "Accept": "application/json",
                 "X-Requested-With": "XMLHttpRequest",
                 "Origin": "https://nicogarrr.github.io",
                 "Referer": "https://nicogarrr.github.io/",
                 "User-Agent": "Mozilla/5.0"})
    try:
        urllib.request.urlopen(req, timeout=6).read()
    except Exception:
        pass


def anotar_peticion(msg):
    """Texto no-comando de alguien con acceso = peticion de funcion nueva.
    Se guarda para que el equipo la recoja y la convierta en PR."""
    try:
        peticiones = _load_json(PETICIONES_PATH, [])
    except Exception:
        peticiones = []
    peticiones.append({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "de_id": msg.from_user.id,
                       "de_nombre": getattr(msg.from_user, "first_name", "") or "",
                       "de_username": getattr(msg.from_user, "username", "") or "",
                       "texto": msg.text})
    with open(PETICIONES_PATH, "w") as f:
        json.dump(peticiones, f, ensure_ascii=False, indent=2)


def enviar_respuestas(tb):
    """Saca las respuestas del equipo (respuestas.json) a sus destinatarios.
    Solo limpia el archivo si todas salen; si no, reintenta en la próxima
    vuelta."""
    resp = _load_json(RESPUESTAS_PATH, [])
    if not resp:
        return 0
    enviadas = 0
    for r in resp:
        try:
            tb.send_message(r["para_id"], r["texto"])
            enviadas += 1
        except Exception:
            pass
    if enviadas == len(resp):
        with open(RESPUESTAS_PATH, "w") as f:
            json.dump([], f)
    return enviadas


def bucle_telegram(token, cfg):
    """Hilo de escucha: get_updates en largo; procesa comandos del dueño."""
    import telebot
    tb = telebot.TeleBot(token)
    offset = _load_json(OFFSET_PATH, {}).get("offset", 0)
    while True:
        try:
            updates = tb.get_updates(offset=offset, timeout=10,
                                     allowed_updates=["message", "channel_post"])
            for upd in updates:
                offset = upd.update_id + 1
                msg = upd.message or upd.channel_post
                if msg is None or not getattr(msg, "text", None):
                    continue
                nivel, uid = nivel_acceso(msg, cfg)
                if nivel == "sin_owner":
                    registrar_dueno(tb, msg, cfg)
                    nivel = "owner"
                elif nivel is None:
                    if msg.from_user is not None:
                        gestionar_desconocido(tb, msg)
                    continue
                accion, params = parse_comando(msg.text)
                if accion == "desconocido" and nivel in ("owner", "user",
                                                         "admin"):
                    anotar_peticion(msg)
                    notificar_email(msg, cfg)
                    tb.send_message(msg.chat.id,
                                    "Se lo paso 🤝. Te contesto por aquí en "
                                    "unos minutos.")
                    continue
                ejecutar(tb, msg.chat.id, accion, params, cfg, nivel)
            if updates:
                with open(OFFSET_PATH, "w") as f:
                    json.dump({"offset": offset}, f)
            try:
                enviar_respuestas(tb)
            except Exception:
                pass
        except Exception:
            time.sleep(10)
        time.sleep(1)
