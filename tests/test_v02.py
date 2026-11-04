"""Pruebas de la v0.2: tipos nuevos, correcciones de fugas, NFD, rendimiento y CLI."""

from __future__ import annotations

import json
import os
import random
import unicodedata

import pytest

from conftest import found
from pii_shield_es import PIIType, PseudonymTable, anonymize, detect
from pii_shield_es.anonymize import mask_value
from pii_shield_es.cli import main
from pii_shield_es.detectors import _is_sentence_start, resolve_overlaps
from pii_shield_es.types import Entity
from pii_shield_es.validators import card_brand, is_valid_card, is_valid_ip, luhn_ok

# --------------------------------------------------------------------------- validadores


@pytest.mark.parametrize(
    ("number", "brand"),
    [
        ("4111 1111 1111 1111", "visa"),
        ("5555555555554444", "mastercard"),
        ("2221000000000009", "mastercard"),
        ("3782 822463 10005", "amex"),
        ("30569309025904", "diners"),
        ("6011111111111117", "discover"),
        ("3530111333300000", "jcb"),
    ],
)
def test_tarjetas_de_prueba_validas(number, brand):
    assert card_brand(number) == brand
    assert is_valid_card(number)


@pytest.mark.parametrize(
    "number", ["4111 1111 1111 1112", "1234567812345678", "9111111111111111", "41111111111"]
)
def test_tarjetas_invalidas(number):
    assert not is_valid_card(number)


def test_luhn_y_ip():
    assert luhn_ok("79927398713") and not luhn_ok("79927398710") and not luhn_ok("12a")
    assert card_brand("4111-x") is None
    assert is_valid_ip("203.0.113.4") and is_valid_ip("2001:db8::1")
    assert not is_valid_ip("999.1.1.1") and not is_valid_ip("01.2.3.4")


# --------------------------------------------------------------------------- tipos nuevos


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Pagó con la tarjeta 4111 1111 1111 1111 y salió doble.", "4111 1111 1111 1111"),
        ("Número de tarjeta: 5555555555554444 (Mastercard).", "5555555555554444"),
        ("American Express 3782 822463 10005 bloqueada.", "3782 822463 10005"),
        ("TC 4012-8888-8888-1881 vence pronto", "4012-8888-8888-1881"),
    ],
)
def test_detecta_tarjetas(text, expected):
    assert found(text, "TARJETA_CREDITO") == [expected]


@pytest.mark.parametrize(
    "text",
    [
        "El número 4111 1111 1111 1112 no pasó la validación.",
        "Pedido 3001234567890 enviado por transportadora.",
        "Tarjeta terminada en 1111.",
        "Separadores mezclados 4111 1111-1111 1111 no cuentan como un solo número.",
    ],
)
def test_no_detecta_tarjetas_falsas(text):
    assert found(text, "TARJETA_CREDITO") == []


def test_tarjeta_sin_contexto_puntua_menos():
    (ent,) = detect("ref 4111111111111111", tipos="TARJETA_CREDITO")
    assert ent.score < 0.9


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Acceso desde la IP 203.0.113.45 a las 02:13.", ["203.0.113.45"]),
        (
            "Bloqueada 2001:db8:85a3::8a2e:370:7334 por fuerza bruta.",
            ["2001:db8:85a3::8a2e:370:7334"],
        ),
        (
            "host 2001:0db8:0000:0000:0000:ff00:0042:8329 ok",
            ["2001:0db8:0000:0000:0000:ff00:0042:8329"],
        ),
        ("Dirección IP 192.168.100.200 del servidor interno.", ["192.168.100.200"]),
    ],
)
def test_detecta_ip(text, expected):
    assert found(text, "DIRECCION_IP") == expected


@pytest.mark.parametrize(
    "text",
    [
        "Actualice a la versión 2.10.4.1 antes del viernes.",
        "La dirección 999.10.10.10 no es válida.",
        "Escuche en 127.0.0.1 y máscara 255.255.255.0 o 0.0.0.0.",
        "std::cout << 10:30:45 y el loopback ::1",
        "Coordenadas 4.7110, -74.0721 en el mapa.",
        "Hora 12:30:45:10 del registro.",
    ],
)
def test_no_detecta_ip_falsas(text):
    assert found(text, "DIRECCION_IP") == []


def test_ip_sin_contexto_puntua_menos():
    (ent,) = detect("dato 203.0.113.9", tipos="DIRECCION_IP")
    assert ent.score == 0.8
    (ent6,) = detect("dato 2001:db8::7", tipos="DIRECCION_IP")
    assert ent6.score == 0.85


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Fecha de nacimiento: 14/03/1957.", "14/03/1957"),
        ("F. nac.: 1985-07-22 · Documento pendiente", "1985-07-22"),
        ("Nació el 3 de mayo de 1990 en Tunja.", "3 de mayo de 1990"),
        ("Nació en Tunja el 12 de octubre del 1978.", "12 de octubre del 1978"),
        ("nacida el 02-11-1993, soltera", "02-11-1993"),
    ],
)
def test_detecta_fecha_nacimiento(text, expected):
    assert found(text, "FECHA_NACIMIENTO") == [expected]


@pytest.mark.parametrize(
    "text",
    [
        "Reunión el 14/03/2025 a las 3:00 p. m.",
        "Fecha de vencimiento: 30/06/2026.",
        "Fecha de nacimiento: 31/02/1990 (inválida).",
        "Fecha de nacimiento: 01/01/1850.",
        "Nació el 1 de enero de 2999.",
    ],
)
def test_no_detecta_fechas_que_no_son_de_nacimiento(text):
    assert found(text, "FECHA_NACIMIENTO") == []


# --------------------------------------------------------------------------- mejoras de detección


@pytest.mark.parametrize(
    ("text", "tipo", "expected"),
    [
        ("Contacto: Martha (320 555 0111).", "TELEFONO", ["320 555 0111"]),
        ("Llame al (320) 555 0111", "TELEFONO", ["(320) 555 0111"]),
        ("Doc: 1020304050 en la planilla", "CEDULA", ["1020304050"]),
        ("Cédula 1020 304 050 copiada", "CEDULA", ["1020 304 050"]),
        ("Documento: 1.098.765.432", "CEDULA", ["1.098.765.432"]),
        ("Enviar a Kra 10 # 20-30 hoy", "DIRECCION", ["Kra 10 # 20-30"]),
        ("Sede en la Ak 7 # 32-16 de Bogotá", "DIRECCION", ["Ak 7 # 32-16"]),
        ("Queda en la Autopista Norte # 152-30", "DIRECCION", ["Autopista Norte # 152-30"]),
        (
            "Vive en Manzana 5 Casa 12 barrio El Prado.",
            "DIRECCION",
            ["Manzana 5 Casa 12 barrio El Prado"],
        ),
        ("Escriba a info(at)example.com", "CORREO", ["info(at)example.com"]),
        ("o a laura.vega[at]example.com", "CORREO", ["laura.vega[at]example.com"]),
        ("o ana arroba example.com hoy", "CORREO", ["ana arroba example.com"]),
        ("Mi placa es HTR 593 y el parqueadero el 12", "PLACA", ["HTR 593"]),
        ("Placa de la moto: XYZ45F", "PLACA", ["XYZ45F"]),
        ("Ana-María Restrepo envió la cotización.", "NOMBRE", ["Ana-María Restrepo"]),
        ("Gracias Natalia, quedo atento.", "NOMBRE", ["Natalia"]),
    ],
)
def test_mejoras_de_deteccion(text, tipo, expected):
    assert found(text, tipo) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Clave temporal ABC123 enviada al usuario.",
        "Referencia del pedido PED123 entregada ayer.",
        "El documento adjunto 1234567 no aplica.",
        "La Avenida Boyacá estará cerrada el domingo.",
        "Estudia en la Universidad Francisco José de Caldas.",
        "La Fundación Pablo Neruda organizó la feria.",
        "Visité el parque Simón Bolívar.",
    ],
)
def test_nuevos_controles_de_falsos_positivos(text):
    assert detect(text) == []


# --------------------------------------------------------------------------- fugas en máscara


@pytest.mark.parametrize(
    ("value", "masked"),
    [
        ("Ana-María Pérez", "A**-M**** P****"),
        ("Juan Pérez", "J*** P****"),
        ("Juan\tPérez", "J***\tP****"),
        ("Patrick O'Neil", "P****** O**'N***"),
        ("Ana", "A**"),
    ],
)
def test_mascara_de_nombres_no_deja_partes_visibles(value, masked):
    assert mask_value(PIIType.NOMBRE, value) == masked


def test_mascara_tipos_nuevos():
    assert mask_value(PIIType.TARJETA_CREDITO, "4111 1111 1111 1111") == "**** **** **** 1111"
    assert mask_value(PIIType.DIRECCION_IP, "203.0.113.45") == "***.*.***.**"
    assert mask_value(PIIType.FECHA_NACIMIENTO, "14/03/1957") == "**/**/****"
    assert mask_value(PIIType.CORREO, "info(at)example.com") == "i***@e***.com"
    assert mask_value(PIIType.CORREO, "ana arroba ejemplo") == "a***@***"
    assert mask_value(PIIType.DIRECCION, "Kra. 10 # 20-30") == "Kra. ** # **-**"


def test_anonimizar_nombre_con_espacio_duro_no_filtra_datos():
    out = anonymize("Hola, soy Juan Camilo Pérez Gómez.", "mascara")
    assert "Camilo" not in out and "Juan" not in out


# --------------------------------------------------------------------------- NFD


def test_texto_nfd_se_detecta_y_conserva_offsets_originales():
    nfc = "Hola, soy Juan Camilo Pérez Gómez, C.C. 1.023.456.789."
    nfd = unicodedata.normalize("NFD", nfc)
    assert len(nfd) > len(nfc)
    ents = detect(nfd)
    assert [e.type for e in ents] == [PIIType.NOMBRE, PIIType.CEDULA]
    for e in ents:
        assert nfd[e.start : e.end] == e.text
    assert unicodedata.normalize("NFC", ents[0].text) == "Juan Camilo Pérez Gómez"
    out = anonymize(nfd)
    assert out == "Hola, soy [NOMBRE], C.C. [CEDULA]."


def test_texto_nfd_en_seudonimo_es_reversible():
    nfd = unicodedata.normalize("NFD", "Señora Ana María Pérez, cédula 52.345.678.")
    tabla = PseudonymTable()
    anon = anonymize(nfd, "seudonimo", tabla=tabla)
    assert "[NOMBRE_1]" in anon and tabla.restore(anon) == nfd


def test_min_score_fuera_de_rango():
    with pytest.raises(ValueError):
        detect("x", min_score=1.5)


# --------------------------------------------------------------------------- rendimiento


def test_inicio_de_oracion_lineal():
    assert _is_sentence_start("Hola", 0)
    assert _is_sentence_start("Fin. \t Ana", 7)
    assert not _is_sentence_start("dijo Ana", 5)


def test_resolve_overlaps_equivale_a_la_version_cuadratica():
    rng = random.Random(7)
    tipos = list(PIIType)
    for _ in range(200):
        ents = []
        for _ in range(rng.randint(0, 25)):
            start = rng.randint(0, 80)
            ents.append(
                Entity(rng.choice(tipos), start, start + rng.randint(1, 15), "x", rng.random())
            )
        from pii_shield_es.detectors import _PRIORITY_INDEX

        ordered = sorted(
            ents, key=lambda e: (-e.score, _PRIORITY_INDEX[e.type], -(e.end - e.start), e.start)
        )
        expected: list[Entity] = []
        for e in ordered:
            if all(e.end <= c.start or e.start >= c.end for c in expected):
                expected.append(e)
        assert resolve_overlaps(ents) == sorted(expected, key=lambda e: (e.start, e.end))


# --------------------------------------------------------------------------- tabla y CLI


def test_guardado_atomico_no_deja_temporales(tmp_path):
    tabla = PseudonymTable()
    tabla.token_for(PIIType.CEDULA, "123")
    destino = tmp_path / "tabla.json"
    destino.write_text("viejo", encoding="utf-8")
    tabla.save(destino)
    assert json.loads(destino.read_text(encoding="utf-8"))["mapping"] == {"[CEDULA_1]": "123"}
    assert [p.name for p in tmp_path.iterdir()] == ["tabla.json"]


def test_guardado_fallido_conserva_tabla_anterior(tmp_path, monkeypatch):
    destino = tmp_path / "tabla.json"
    destino.write_text("original", encoding="utf-8")
    tabla = PseudonymTable()

    def boom(*_a, **_k):
        raise OSError("disco lleno")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        tabla.save(destino)
    assert destino.read_text(encoding="utf-8") == "original"
    assert [p.name for p in tmp_path.iterdir()] == ["tabla.json"]


def test_cli_no_escribe_salida_si_no_puede_guardar_la_tabla(tmp_path, capsys):
    salida = tmp_path / "anon.txt"
    tabla = tmp_path / "no-existe" / "tabla.json"
    code = main(
        ["anonimizar", "cédula 1.023.456.789", "-m", "seudonimo", "--tabla", str(tabla),
         "-o", str(salida)]
    )  # fmt: skip
    assert code == 2
    assert not salida.exists()
    assert "No se pudo guardar la tabla" in capsys.readouterr().err


def test_cli_min_score_invalido(capsys):
    for valor in ("2", "abc"):
        with pytest.raises(SystemExit) as exc:
            main(["detectar", "x", "--min-score", valor])
        assert exc.value.code == 2
    assert "min-score" in capsys.readouterr().err


def test_cli_resumen_texto_y_json(capsys):
    texto = "Doc: 1020304050, tarjeta 4111 1111 1111 1111, ana(at)example.com"
    assert main(["detectar", texto, "--resumen"]) == 0
    out = capsys.readouterr().out
    assert "TARJETA_CREDITO" in out and "TOTAL" in out and "4111" not in out
    assert main(["detect", texto, "--resumen", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "CEDULA": 1,
        "CORREO": 1,
        "TARJETA_CREDITO": 1,
    }


def test_cli_tipos(capsys):
    assert main(["tipos"]) == 0
    out = capsys.readouterr().out
    assert all(t.value in out for t in PIIType)


def test_cli_min_score_valido(capsys):
    assert main(["detectar", "cédula 1.023.456.789", "--min-score", "0.5", "--resumen"]) == 0
    assert "CEDULA" in capsys.readouterr().out
