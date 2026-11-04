import json
import os
import stat

import pytest

from datashield_es import (
    PIIType,
    PseudonymTable,
    anonymize,
    anonymize_detailed,
    deanonymize,
)
from datashield_es.anonymize import mask_value, normalize_mode

TEXTO = (
    "Soy Juan Camilo Pérez Gómez, C.C. 1.023.456.789, vivo en Cra 15 # 93-60 apto 502. "
    "Celular +57 300 123 4567, correo juan.perez@example.com, placa del carro ABC123."
)


class TestEtiqueta:
    def test_reemplaza_por_etiqueta(self):
        out = anonymize(TEXTO)
        assert out == (
            "Soy [NOMBRE], C.C. [CEDULA], vivo en [DIRECCION]. "
            "Celular [TELEFONO], correo [CORREO], placa del carro [PLACA]."
        )

    def test_es_el_modo_por_defecto_y_acepta_alias(self):
        assert anonymize(TEXTO) == anonymize(TEXTO, "etiqueta") == anonymize(TEXTO, "label")

    def test_no_altera_texto_sin_pii(self):
        assert anonymize("Hola mundo") == "Hola mundo"

    def test_tipos_selectivos(self):
        out = anonymize(TEXTO, tipos=["CORREO"])
        assert "[CORREO]" in out and "1.023.456.789" in out


class TestMascara:
    def test_mascara_por_tipo(self):
        assert mask_value(PIIType.CEDULA, "1.023.456.789") == "*.***.***.789"
        assert mask_value(PIIType.TELEFONO, "300 123 4567") == "*** *** *567"
        assert mask_value(PIIType.CORREO, "juan.perez@example.com") == "j***@e***.com"
        assert mask_value(PIIType.NOMBRE, "Juan Pérez") == "J*** P****"
        assert mask_value(PIIType.DIRECCION, "Cra 15 # 93-60") == "Cra ** # **-**"
        assert mask_value(PIIType.PLACA, "ABC123") == "******"
        assert mask_value(PIIType.NIT, "900.123.456-7") == "***.***.***-7"

    def test_cuenta_conserva_ultimos_cuatro(self):
        masked = mask_value(PIIType.CUENTA_BANCARIA, "123-456789-01")
        assert masked.endswith("9-01") and masked.count("*") == 7

    def test_mascara_en_texto(self):
        out = anonymize(TEXTO, "mascara")
        assert "1.023.456.789" not in out and "*.***.***.789" in out
        assert "juan.perez@example.com" not in out and "j***@e***.com" in out
        assert "Juan" not in out

    def test_direccion_sin_espacios_y_correo_degenerado(self):
        assert mask_value(PIIType.DIRECCION, "Calle") == "*****"
        assert mask_value(PIIType.CORREO, "a@b") == "a***@***"


class TestSeudonimo:
    def test_sin_tabla_es_consistente_pero_no_recuperable(self):
        texto = "Cédula 1.234.567.890 y otra vez cédula 1.234.567.890; correo a@example.com"
        out = anonymize(texto, "seudonimo")
        assert out == "Cédula [CEDULA_1] y otra vez cédula [CEDULA_1]; correo [CORREO_1]"
        assert anonymize_detailed(texto, "seudonimo").table is not None

    def test_roundtrip_con_tabla(self):
        tabla = PseudonymTable()
        out = anonymize(TEXTO, "seudonimo", tabla=tabla)
        assert "1.023.456.789" not in out
        assert len(tabla) == 6
        assert deanonymize(out, tabla) == TEXTO
        assert tabla.restore(out) == TEXTO

    def test_tabla_acumula_entre_llamadas(self):
        tabla = PseudonymTable()
        a = anonymize("cédula 1.111.111", "seudonimo", tabla=tabla)
        b = anonymize("cédula 2.222.222 y cédula 1.111.111", "seudonimo", tabla=tabla)
        assert a == "cédula [CEDULA_1]"
        assert b == "cédula [CEDULA_2] y cédula [CEDULA_1]"

    def test_token_desconocido_se_deja(self):
        assert PseudonymTable().restore("[CEDULA_9] queda") == "[CEDULA_9] queda"

    def test_persistencia_json(self, tmp_path):
        tabla = PseudonymTable()
        out = anonymize(TEXTO, "seudonimo", tabla=tabla)
        path = tmp_path / "t.json"
        tabla.save(path)
        if os.name == "posix":
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == 1 and len(data["mapping"]) == 6
        loaded = PseudonymTable.load(path)
        assert loaded.restore(out) == TEXTO
        # los contadores se retoman: el siguiente seudónimo no colisiona
        assert loaded.token_for(PIIType.CEDULA, "9.999.999") == "[CEDULA_2]"
        assert loaded.mapping == {**tabla.mapping, "[CEDULA_2]": "9.999.999"}

    @pytest.mark.parametrize(
        "payload",
        [
            "[]",
            '{"version": 2, "mapping": {}}',
            '{"version": 1, "mapping": {"malo": "x"}}',
            '{"version": 1, "mapping": {"[CEDULA_1]": 5}}',
        ],
    )
    def test_tabla_invalida(self, payload):
        with pytest.raises(ValueError):
            PseudonymTable.from_json(payload)


def test_modo_invalido():
    with pytest.raises(ValueError, match="Modo desconocido"):
        anonymize("x", "otro")
    assert normalize_mode("Máscara") == "mascara"
    assert normalize_mode("PSEUDONYM") == "seudonimo"


def test_detailed_incluye_entidades():
    res = anonymize_detailed(TEXTO)
    assert len(res.entities) == 6 and res.table is None
