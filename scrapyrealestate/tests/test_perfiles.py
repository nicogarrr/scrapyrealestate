"""Tests de los perfiles de busqueda (piso / terrenos / casas)."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main
from scrapyrealestate import comandos


class FakeLogger:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def debug(self, *a, **k): pass
    def error(self, *a, **k): pass


class FakeBot:
    def __init__(self, token):
        self.sent = []

    def send_message(self, chat_id, text, parse_mode=None, **kw):
        self.sent.append((chat_id, text))
        return SimpleNamespace(chat=SimpleNamespace(title="test"), message_id=1)


def _flat(price, m2, town, site="pisoscom", lid=None, title="Casa en Llanes",
          href=None, rooms="3 hab."):
    return {
        "site": site,
        "id": lid or f"{site}-{price}-{m2}-{town}",
        "price": f"{price:,}".replace(",", ".") + " €",
        "m2": str(m2),
        "rooms": rooms,
        "town": town,
        "title": title,
        "href": href or f"https://www.{site}.example/anuncio-{price}-{m2}-{town}",
        "type": "buy",
    }


def _run_check(tmp_path, monkeypatch, flats, perfil, pmax, bot):
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "get_bot_token", lambda: "t")
    monkeypatch.setattr(main.telebot, "TeleBot", lambda token: bot)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    feed = data_dir / f"feed_{perfil}.json"
    feed.write_text(json.dumps(flats), encoding="utf-8")
    return main.check_new_flats(str(feed), "asturias", "0", str(pmax),
                                "canal", True, FakeLogger(), perfil=perfil)


def test_perfil_de_clave():
    assert main.perfil_de_clave("url_fotocasa") == "piso"
    assert main.perfil_de_clave("url_pisoscom") == "piso"
    assert main.perfil_de_clave("url_fotocasa_terrenos") == "terrenos"
    assert main.perfil_de_clave("url_pisoscom_terrenos") == "terrenos"
    assert main.perfil_de_clave("url_fotocasa_casas") == "casas"
    assert main.perfil_de_clave("url_habitaclia_casas") == "casas"
    assert main.perfil_de_clave("telegram_bot_token") == "piso"


def test_limites_perfil(monkeypatch):
    monkeypatch.setattr(main, "data",
                        {"min_price": "0", "max_price": "110000",
                         "perfil_max_precio": {"terrenos": 100000,
                                               "casas": 100000}},
                        raising=False)
    assert main.limites_perfil("piso") == ("0", "110000")
    assert main.limites_perfil("terrenos") == ("0", "100000")
    assert main.limites_perfil("casas") == ("0", "100000")
    # sin config de perfil: sin limite
    monkeypatch.setattr(main, "data", {"min_price": "0", "max_price": "110000"},
                        raising=False)
    assert main.limites_perfil("casas") == ("0", "0")


def test_terreno_etiqueta_y_tope(tmp_path, monkeypatch):
    bot = FakeBot("t")
    flats = [_flat(90000, 500, "Llanes", title="Terreno en Llanes"),
             _flat(120000, 900, "Llanes", title="Terreno caro en Llanes")]
    nuevas, _ = _run_check(tmp_path, monkeypatch, flats, "terrenos", 100000, bot)
    assert nuevas == 1
    assert len(bot.sent) == 1
    cuerpo = bot.sent[0][1]
    assert "TERRENO" in cuerpo
    assert "90.000" in cuerpo
    # sin tags residenciales para suelo
    assert "parques" not in cuerpo and "renta" not in cuerpo
    assert "media de" not in cuerpo


def test_terreno_no_contamina_zonas_pisos(tmp_path, monkeypatch):
    bot = FakeBot("t")
    flats = [_flat(40000, 800, "Mieres", title="Solar en Mieres")]
    _run_check(tmp_path, monkeypatch, flats, "terrenos", 100000, bot)
    zonas = json.loads((tmp_path / "data" / "zonas.json").read_text())
    assert "mieres" not in zonas
    assert zonas["terrenos:mieres"]["samples"] == [50]


def test_casa_namespaces_zonas(tmp_path, monkeypatch):
    bot = FakeBot("t")
    pisos = [_flat(100000, 80, "Mieres", title="Piso en Mieres")]
    _run_check(tmp_path, monkeypatch, pisos, "piso", 110000, bot)
    casas = [_flat(60000, 150, "Mieres", title="Casa en Mieres")]
    _run_check(tmp_path, monkeypatch, casas, "casas", 100000, bot)
    zonas = json.loads((tmp_path / "data" / "zonas.json").read_text())
    # piso mantiene la clave legacy y no se mezcla con la casa
    assert zonas["mieres"]["samples"] == [1250]
    assert zonas["casas:mieres"]["samples"] == [400]


def test_casa_mensaje_completo(tmp_path, monkeypatch):
    bot = FakeBot("t")
    casas = [_flat(85000, 120, "Gijón", title="Casa en Gijón")]
    nuevas, _ = _run_check(tmp_path, monkeypatch, casas, "casas", 100000, bot)
    assert nuevas == 1
    cuerpo = bot.sent[0][1]
    assert "CASA" in cuerpo and "85.000" in cuerpo and "Gijón" in cuerpo


def test_avisos_privados_perfiles_default_piso(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    monkeypatch.chdir(tmp_path)
    (data_dir / "alertas_privadas.json").write_text(json.dumps([
        {"user_id": 111, "town": "Mieres"},
        {"user_id": 222, "town": "Mieres", "perfiles": ["piso", "casas"]},
    ]))
    bot = FakeBot("t")
    main.avisos_privados(bot, "aviso", "Mieres", "", "casas")
    assert [c for c, _ in bot.sent] == [222]
    bot.sent.clear()
    main.avisos_privados(bot, "aviso", "Mieres", "", "piso")
    assert sorted(c for c, _ in bot.sent) == [111, 222]


def test_update_pisos_guarda_perfil():
    pisos = {}
    e = main.update_pisos(pisos, _flat(50000, 100, "Siero"), 50000, 100,
                          "Siero", "casas")
    assert e["perfil"] == "casas"


def test_comandos_perfiles():
    assert comandos.parse_comando("apaga terrenos") == (
        "perfil_apagar", {"perfil": "terrenos"})
    assert comandos.parse_comando("activa casas") == (
        "perfil_activar", {"perfil": "casas"})
    assert comandos.parse_comando("quita terrenos")[0] == "perfil_apagar"
    assert comandos.parse_comando("añade casas")[0] == "perfil_activar"
    # portales y municipios siguen igual
    assert comandos.parse_comando("apaga idealista") == (
        "apagar", {"portal": "idealista"})
    assert comandos.parse_comando("añade Avilés") == (
        "municipio_add", {"nombre": "aviles"})


def test_ejecutar_perfil_apagar_activar(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    bot = FakeBot("t")
    cfg = {"perfiles_off": []}
    comandos.ejecutar(bot, "chat", "perfil_apagar", {"perfil": "terrenos"}, cfg)
    assert cfg["perfiles_off"] == ["terrenos"]
    comandos.ejecutar(bot, "chat", "perfil_activar", {"perfil": "terrenos"}, cfg)
    assert cfg["perfiles_off"] == []


def test_regenerar_urls_conserva_perfiles():
    cfg = {"municipios": ["Gijón"], "max_price": "110000",
           "url_fotocasa_terrenos": ["https://x"], "url_pisoscom_casas": ["https://y"]}
    comandos.regenerar_urls(cfg)
    assert cfg["url_fotocasa_terrenos"] == ["https://x"]
    assert cfg["url_pisoscom_casas"] == ["https://y"]
    assert len(cfg["url_fotocasa"]) == 1


def test_sembrar_config_perfiles():
    cfg = {}
    comandos.sembrar_config(cfg)
    assert cfg["perfiles_off"] == []
    assert cfg["perfil_max_precio"] == {"terrenos": 100000, "casas": 100000}
    for k in ("url_fotocasa_terrenos", "url_pisoscom_terrenos",
              "url_fotocasa_casas", "url_pisoscom_casas", "url_habitaclia_casas"):
        assert cfg[k] == []


def test_habitaclia_slug_casas():
    import re
    m = re.search(r'(?:viviendas|casas)-([a-z_]+)\.htm',
                  "https://www.habitaclia.com/casas-gijon.htm")
    assert m and m.group(1) == "gijon"
    m2 = re.search(r'(?:viviendas|casas)-([a-z_]+)\.htm',
                   "https://www.habitaclia.com/viviendas-mieres.htm")
    assert m2 and m2.group(1) == "mieres"


def test_finca_colada_en_url_pisos_se_clasifica_como_terreno():
    flat = _flat(100000, 2638, "Siero", title="Finca rústica en Granda-Tiñana-Hevia",
                 href="https://www.pisos.com/comprar/finca_rustica-granda_123/")
    assert main.perfil_de_anuncio(flat, "piso") == "terrenos"
    assert main.perfil_de_anuncio(flat, "casas") == "terrenos"
    assert main.perfil_de_anuncio(_flat(70000, 100, "Siero", title="Casa con parcela"),
                                 "terrenos") == "casas"
    assert main.perfil_de_anuncio(_flat(90000, 80, "Siero", title="Piso céntrico"),
                                 "piso") == "piso"


def test_mediana_terrenos_sin_cruce_y_sin_etiquetas_residenciales(tmp_path, monkeypatch):
    bot = FakeBot("t")
    # Repro de la alerta: una mediana residencial existente de 1.301€/m²
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "zonas.json").write_text(json.dumps({
        "siero": {"samples": [1301] * 20},
        "terrenos:siero": {"samples": [38] * 20},
        "casas:siero": {"samples": [800] * 20},
    }))
    finca = _flat(100000, 2638, "Siero", title="Finca rústica en Granda-Tiñana-Hevia",
                  href="https://www.pisos.com/comprar/finca_rustica-granda_123/")
    assert main.perfil_de_anuncio(finca, "piso") == "terrenos"
    _run_check(tmp_path, monkeypatch, [finca], "terrenos", 100000, bot)
    cuerpo = bot.sent[0][1]
    assert "TERRENO" in cuerpo
    assert "terrenos en Siero (38€/m²)" in cuerpo
    for incompatible in ("1301", "1.301", "parques", "bares", "bus", "coles", "renta", "infracciones"):
        assert incompatible not in cuerpo
    zonas = json.loads((data_dir / "zonas.json").read_text())
    assert zonas["siero"]["samples"] == [1301] * 20
    assert zonas["casas:siero"]["samples"] == [800] * 20
    assert 38 in zonas["terrenos:siero"]["samples"]


def test_no_hay_mediana_terrenos_sin_muestra_propia():
    zonas = {"siero": {"samples": [1301] * 20}}
    assert main.zona_tag(zonas, 100000, 2638, "Siero", "terrenos") == ""
    assert main.es_chollo(zonas, 100000, 2638, "Siero", "terrenos") == (False, None)


def test_reagrupacion_real_por_anuncio_no_por_url():
    finca = _flat(100000, 2638, "Siero", title="Finca rústica en Granda",
                  href="https://www.pisos.com/comprar/finca_rustica-granda/")
    piso = _flat(90000, 80, "Siero", title="Piso con ascensor")
    casa = _flat(80000, 110, "Siero", title="Casa en Siero")
    clasificados = main.clasificar_anuncios({"piso": [finca, piso],
                                            "terrenos": [casa]})
    assert clasificados == {"piso": [piso], "terrenos": [finca],
                            "casas": [casa]}
    solo_slug = dict(finca, title="Oportunidad en Siero")
    assert main.perfil_de_anuncio(solo_slug, "piso") == "terrenos"
