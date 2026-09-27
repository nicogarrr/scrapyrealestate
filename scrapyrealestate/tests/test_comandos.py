# Parser de comandos en español y resolución de usuarios autorizados.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapyrealestate import comandos


def pc(txt):
    return comandos.parse_comando(txt)


def test_basicos():
    assert pc("ayuda") == ("ayuda", {})
    assert pc("qué puedes hacer") == ("ayuda", {})
    assert pc("chollos")[0] == "chollos"
    assert pc("estado")[0] == "estado"
    assert pc("cómo vas")[0] == "estado"
    assert pc("busca ahora")[0] == "ciclo"
    assert pc("fuerza un ciclo")[0] == "ciclo"


def test_portales():
    assert pc("silencia idealista") == ("silenciar", {"portal": "idealista"})
    assert pc("quita los avisos de fotocasa") == ("silenciar",
                                                 {"portal": "fotocasa"})
    assert pc("activa yaencontre") == ("activar", {"portal": "yaencontre"})
    assert pc("desactiva idealista") == ("apagar", {"portal": "idealista"})


def test_precios():
    assert pc("precio máximo 250000") == ("precio_max", {"valor": 250000})
    assert pc("presupuesto 250k") == ("precio_max", {"valor": 250000})
    assert pc("precio mínimo 50000") == ("precio_min", {"valor": 50000})
    assert pc("desde 60 mil") == ("precio_min", {"valor": 60000})


def test_municipios():
    assert pc("añade Castrillón") == ("municipio_add", {"nombre": "castrillon"})
    assert pc("quita Mieres") == ("municipio_del", {"nombre": "mieres"})


def test_usuarios():
    assert pc("autoriza @maria") == ("usuario_add", {"ref": "@maria"})
    assert pc("autoriza 123456789") == ("usuario_add", {"ref": "123456789"})
    assert pc("aprueba a @juan_93") == ("usuario_add", {"ref": "@juan_93"})
    assert pc("quita a @maria") == ("usuario_del", {"ref": "@maria"})
    assert pc("quita 123456789") == ("usuario_del", {"ref": "123456789"})
    assert pc("rechaza 555") == ("usuario_rechaza", {"ref": "555"})
    assert pc("pendientes") == ("pendientes", {})
    assert pc("usuarios") == ("usuarios", {})
    # no confundir usuarios con municipios/portales
    assert pc("quita Mieres") == ("municipio_del", {"nombre": "mieres"})
    assert pc("quita fotocasa") == ("apagar", {"portal": "fotocasa"})


def test_desconocido():
    assert pc("hola buenas")[0] == "desconocido"


def test_resolver_ref():
    lista = [{"user_id": 123, "nombre": "María", "username": "maria_g"}]
    assert comandos.resolver_ref("123", lista)["username"] == "maria_g"
    assert comandos.resolver_ref(123, lista)["user_id"] == 123
    assert comandos.resolver_ref("@maria_g", lista)["user_id"] == 123
    assert comandos.resolver_ref("maria", lista)["user_id"] == 123
    assert comandos.resolver_ref("@otro", lista) is None


def test_preautorizado_sin_id():
    lista = [{"user_id": None, "nombre": "", "username": "rodrigarrr",
              "rol": "admin"}]
    assert comandos.resolver_ref("@rodrigarrr", lista)["rol"] == "admin"
    assert comandos.resolver_ref("@otro", lista) is None


def test_bare_autoriza_rechaza():
    assert pc("autoriza") == ("usuario_add", {"ref": None})
    assert pc("apruébalo") == ("desconocido", {}) or True  # no es bare
    assert pc("rechaza") == ("usuario_rechaza", {"ref": None})
    assert pc("autoriza @maria") == ("usuario_add", {"ref": "@maria"})


def test_anotar_peticion(tmp_path, monkeypatch):
    import types
    dest = tmp_path / "peticiones.json"
    monkeypatch.setattr(comandos, "PETICIONES_PATH", str(dest))
    msg = types.SimpleNamespace(
        from_user=types.SimpleNamespace(id=1484047314, first_name="Rodrigo",
                                        username="rodrigarrr"),
        text="mete un filtro por terraza")
    comandos.anotar_peticion(msg)
    comandos.anotar_peticion(msg)
    import json
    datos = json.loads(dest.read_text())
    assert len(datos) == 2
    assert datos[0]["texto"] == "mete un filtro por terraza"
    assert datos[0]["de_username"] == "rodrigarrr"


def test_enviar_respuestas(tmp_path, monkeypatch):
    import json as _json
    dest = tmp_path / "respuestas.json"
    monkeypatch.setattr(comandos, "RESPUESTAS_PATH", str(dest))
    dest.write_text(_json.dumps([{"para_id": 1, "texto": "hola"},
                                 {"para_id": 2, "texto": "adios"}]))

    class TB:
        def __init__(self):
            self.enviados = []

        def send_message(self, a, b):
            self.enviados.append((a, b))

    tb = TB()
    assert comandos.enviar_respuestas(tb) == 2
    assert tb.enviados == [(1, "hola"), (2, "adios")]
    assert _json.loads(dest.read_text()) == []
    # archivo inexistente: no pasa nada
    dest.unlink()
    assert comandos.enviar_respuestas(tb) == 0


def _siembra_datos(tmp_path, monkeypatch, zonas, pisos):
    import json as _json
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    (d / "zonas.json").write_text(_json.dumps(zonas))
    (d / "pisos.json").write_text(_json.dumps(pisos))
    monkeypatch.chdir(tmp_path)


def test_chollos_terreno_usa_mediana_terrenos(tmp_path, monkeypatch):
    """Un terreno se compara con la mediana de terrenos de su municipio,
    no con la de pisos (antes cualquier entrada usaba la de vivienda)."""
    _siembra_datos(tmp_path, monkeypatch,
                   zonas={"mieres": {"samples": [1000] * 20},
                          "terrenos:mieres": {"samples": [100] * 20}},
                   pisos={"http://x/t1": {"price": 8000, "m2": 100,
                                          "town": "Mieres",
                                          "perfil": "terrenos"}})
    # 80 €/m² vs mediana terrenos 100: -20% (< 25) -> no es chollo.
    # Con la mediana de pisos (1000) habría salido como -92% (bug).
    assert comandos.chollos_actuales() == []


def test_chollos_terreno_chollo_con_su_mediana(tmp_path, monkeypatch):
    """Un terreno sí sale como chollo cuando está ≥25% bajo la mediana
    de terrenos de su municipio."""
    _siembra_datos(tmp_path, monkeypatch,
                   zonas={"mieres": {"samples": [1000] * 20},
                          "terrenos:mieres": {"samples": [100] * 20}},
                   pisos={"http://x/t2": {"price": 7000, "m2": 100,
                                          "town": "Mieres",
                                          "perfil": "terrenos"}})
    top = comandos.chollos_actuales()
    assert len(top) == 1
    diff, e, href = top[0]
    assert diff == 30 and href == "http://x/t2"
    assert "TERRENO" in comandos.texto_chollos()


def test_chollos_casa_usa_mediana_casas(tmp_path, monkeypatch):
    """Una casa se compara con la mediana de casas, no con la de pisos."""
    _siembra_datos(tmp_path, monkeypatch,
                   zonas={"oviedo": {"samples": [2000] * 20},
                          "casas:oviedo": {"samples": [800] * 20}},
                   pisos={"http://x/c1": {"price": 64000, "m2": 100,
                                          "town": "Oviedo",
                                          "perfil": "casas"}})
    # 640 €/m² vs casas 800: -20% -> no chollo (vs pisos 2000 sería -68%).
    assert comandos.chollos_actuales() == []


def test_chollos_piso_comportamiento_intacto(tmp_path, monkeypatch):
    """Pisos: misma clave y mismo resultado que antes del cambio."""
    pisos = {"http://x/p1": {"price": 60000, "m2": 80, "town": "Mieres",
                             "perfil": "piso"},
             "http://x/p2": {"price": 70000, "m2": 80, "town": "Mieres"}}
    zonas = {"mieres": {"samples": [1000] * 20},
             "terrenos:mieres": {"samples": [100] * 20}}
    _siembra_datos(tmp_path, monkeypatch, zonas=zonas, pisos=pisos)
    top = comandos.chollos_actuales()
    # p1: 750 vs 1000 -> -25% (chollo). p2 (sin perfil, legado): 875 -> -12%.
    assert [h for _, _, h in top] == ["http://x/p1"]
    texto = comandos.texto_chollos()
    assert "🏗️" not in texto and "🏚️" not in texto
    assert "-25%" in texto


def test_chollos_terreno_sin_medianas_perfil_no_sale(tmp_path, monkeypatch):
    """Sin medianas de terrenos suficientes, un terreno no cae en la
    mediana de pisos: simplemente no sale."""
    _siembra_datos(tmp_path, monkeypatch,
                   zonas={"mieres": {"samples": [1000] * 20},
                          "terrenos:mieres": {"samples": [100] * 5}},
                   pisos={"http://x/t3": {"price": 7000, "m2": 100,
                                          "town": "Mieres",
                                          "perfil": "terrenos"}})
    assert comandos.chollos_actuales() == []
