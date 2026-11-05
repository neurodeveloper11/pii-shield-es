"""Casos de atención al cliente: presentaciones, vocativos y documentos dictados en otro turno."""

import pytest

from conftest import found
from datashield_es import anonymize, detect


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Entiendo su preocupación, Jorge, ya lo reviso", ["Jorge"]),
        ("Llegó tarde, Diana.", ["Diana"]),
        ("¿Hablo con Luz Dary?", ["Luz Dary"]),
        ("Buenos días, le habla Sebastián de ConectaYa.", ["Sebastián"]),
        ("Hola, soy Laura de Banco Cordillera", ["Laura"]),
        ("te habla María José Pérez de Movistar", ["María José Pérez"]),
    ],
)
def test_nombres_en_atencion(text, expected):
    assert found(text, "NOMBRE") == expected


@pytest.mark.parametrize(
    "text",
    [
        "Vivo en Cali, Colombia, desde 2010",
        "Compré en Falabella, Éxito y Olímpica.",
        "Fui con Luz a la tienda",
        "Visité Medellín, Bogotá, Cali.",
        "Soy Bogotano de nacimiento",
        "Le habla el sistema automático",
    ],
)
def test_no_son_nombres(text):
    assert found(text, "NOMBRE") == []


def test_entidad_nunca_corta_una_palabra():
    texto = "Buenos días, le habla Sebastián de ConectaYa. Atendió Ana de SuperMercado."
    for e in detect(texto):
        assert e.start == 0 or not texto[e.start - 1].isalnum()
        assert e.end == len(texto) or not texto[e.end].isalnum()


PIDE = "Por favor me regala su número de cédula.\nYa se la di al bot.\nEs necesario para validar."


@pytest.mark.parametrize("respuesta", ["12.635.880", "Claro, 421.216.262.", "1023456789"])
def test_cedula_dictada_en_otro_turno(respuesta):
    assert "[CEDULA]" in anonymize(respuesta, contexto=PIDE)
    assert "[CEDULA]" not in anonymize(respuesta)  # sin contexto no hay pista


def test_contexto_no_convierte_montos_ni_numeros_cortos():
    assert anonymize("Debo $1.200.000 y $ 480.000", contexto=PIDE) == "Debo $1.200.000 y $ 480.000"
    assert anonymize("Llevo 15 días", contexto=PIDE) == "Llevo 15 días"


def test_contexto_sin_pedir_documento_no_cambia_nada():
    assert anonymize("12.635.880", contexto="¿Cuánto debe?") == "12.635.880"


def test_contexto_respeta_tipos():
    assert detect("12.635.880", contexto=PIDE, tipos=["TELEFONO"]) == []
    [e] = detect("12.635.880", contexto=PIDE)
    assert e.detector == "cc_dialogo" and e.text == "12.635.880"
