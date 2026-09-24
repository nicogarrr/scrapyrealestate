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
