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
