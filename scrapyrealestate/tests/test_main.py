import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main


class FakeLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class FakeBot:
    def __init__(self, token):
        self.sent = []

    def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text, parse_mode))
        return SimpleNamespace(chat=SimpleNamespace(title="test"))


def test_get_urls_preserves_existing_query_strings(monkeypatch):
    monkeypatch.setattr(main, "logger", FakeLogger(), raising=False)
    config = {
        "url_idealista": ["https://www.idealista.com/venta-viviendas/asturias/?ordenado-por=fecha"],
        "url_pisoscom": ["https://www.pisos.com/venta/pisos-asturias/hasta-100000"],
        "url_fotocasa": ["https://www.fotocasa.es/es/comprar/viviendas/asturias/l?sortType=price"],
        "url_habitaclia": ["https://www.habitaclia.com/comprar/viviendas/asturias-provincia/s"],
        "url_yaencontre": ["https://www.yaencontre.com/venta/pisos/asturias/f-ascensor"],
    }
    monkeypatch.setattr(main, "logger", FakeLogger())
    urls = main.get_urls(config)
    assert urls["start_urls_idealista"][0].endswith("?ordenado-por=fecha&ordenado-por=fecha-publicacion-desc")
    assert urls["start_urls_pisoscom"][0].endswith("/hasta-100000/fecharecientedesde-desc/")
    assert urls["start_urls_habitaclia"][0].endswith("?ordenar=mas_recientes")
    assert urls["start_urls_yaencontre"][0].endswith("/f-ascensor/o-recientes")


def test_check_new_flats_supports_string_ids_and_numeric_prices(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "ids.json").write_text(json.dumps([42]), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "get_bot_token", lambda: "test-token")
    bot = FakeBot("test-token")
    monkeypatch.setattr(main.telebot, "TeleBot", lambda token: bot)
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)
    current = data_dir / "current.json"
    current.write_text(
        json.dumps(
            [
                {
                    "site": "pisoscom",
                    "id": "50016420678_500957",
                    "price": "80.000 €",
                    "m2": "100 m²",
                    "href": "https://www.pisos.com/comprar/piso-50016420678_500957/",
                    "type": "buy",
                }
            ]
        ),
        encoding="utf-8",
    )

    main.check_new_flats(str(current), "asturias", "0", "100000", "chat", True, FakeLogger())

    saved = json.loads((data_dir / "ids.json").read_text(encoding="utf-8"))
    assert "pisoscom:50016420678_500957" in saved
    assert len(bot.sent) == 1
    assert "80.000 €" in bot.sent[0][1]


def test_run_spider_returns_process_exit_code(monkeypatch, tmp_path):
    seen = {}

    def fake_run(command, check=False):
        seen["command"] = command
        seen["check"] = check
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(main.subprocess, "run", fake_run)
    code = main.run_spider("pisoscom", "INFO", str(tmp_path / "out.json"), "https://example.test")
    assert code == 7
    assert seen["check"] is False
    assert "pisoscom" in seen["command"]


def test_update_pisos_guarda_url_y_zona():
    pisos = {}
    flat = {"href": "https://www.pisos.com/piso-123", "title": "Piso en Santa Marina-Uxo",
            "rooms": "2 habs.", "site": "pisoscom", "neighbour": ""}
    e = main.update_pisos(pisos, flat, 44000, 70, "Mieres")
    assert e["url"] == "https://www.pisos.com/piso-123"
    assert e["zona"] == "Santa Marina-Uxo"  # derivada del titulo
    flat2 = {"href": "https://x/1", "title": "Piso", "neighbour": "La Villa",
             "rooms": "", "site": "fotocasa"}
    e2 = main.update_pisos(pisos, flat2, 90000, 80, "Mieres")
    assert e2["zona"] == "La Villa"  # neighbour del portal manda


def test_coincide_alerta():
    priv = {"user_id": 1, "town": "Mieres", "excluir_zonas": ["uxo"]}
    assert main.coincide_alerta(priv, "Mieres", "Santa Marina-Uxo") is False
    assert main.coincide_alerta(priv, "Mieres", "La Villa") is True
    assert main.coincide_alerta(priv, "Gijón", "Centro") is False
    priv_inc = {"user_id": 1, "town": "Mieres", "incluir_zonas": ["villa", "centro"]}
    assert main.coincide_alerta(priv_inc, "Mieres", "La Villa") is True
    assert main.coincide_alerta(priv_inc, "Mieres", "Santa Marina-Uxo") is False
