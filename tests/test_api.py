import pytest

from datashield_es import Entity, PIIType, detect
from datashield_es.detectors import resolve_overlaps
from datashield_es.types import coerce_types

TEXTO = (
    "Soy Juan Camilo Pérez Gómez, C.C. 1.023.456.789, vivo en Cra 15 # 93-60 apto 502. "
    "Celular +57 300 123 4567, correo juan.perez@example.com, placa del carro ABC123."
)


def test_detect_devuelve_todos_los_tipos_ordenados():
    ents = detect(TEXTO)
    assert [e.type for e in ents] == [
        PIIType.NOMBRE,
        PIIType.CEDULA,
        PIIType.DIRECCION,
        PIIType.TELEFONO,
        PIIType.CORREO,
        PIIType.PLACA,
    ]
    assert [e.start for e in ents] == sorted(e.start for e in ents)
    for e in ents:
        assert TEXTO[e.start : e.end] == e.text
        assert 0 < e.score <= 1


def test_filtrar_por_tipos_acepta_cadenas_y_enums():
    assert {e.type for e in detect(TEXTO, tipos=["correo", PIIType.PLACA])} == {
        PIIType.CORREO,
        PIIType.PLACA,
    }
    assert [e.type for e in detect(TEXTO, tipos="CORREO")] == [PIIType.CORREO]
    assert [e.type for e in detect(TEXTO, tipos=PIIType.CEDULA)] == [PIIType.CEDULA]


def test_tipo_desconocido():
    with pytest.raises(ValueError, match="Tipo de PII desconocido"):
        detect(TEXTO, tipos=["INEXISTENTE"])


def test_min_score_filtra():
    todas = detect("salió ABC123 y placa XYZ987")
    assert len(todas) == 2
    assert [e.text for e in detect("salió ABC123 y placa XYZ987", min_score=0.8)] == ["XYZ987"]


def test_entrada_no_str():
    with pytest.raises(TypeError):
        detect(123)  # type: ignore[arg-type]


def test_vacio_y_sin_pii():
    assert detect("") == []
    assert detect("Texto cualquiera sin datos personales.") == []


def test_cedula_gana_a_telefono_cuando_hay_contexto():
    ents = detect("cédula 3012345678")
    assert [e.type for e in ents] == [PIIType.CEDULA]


def test_resolve_overlaps_prefiere_mayor_score_y_luego_prioridad():
    a = Entity(PIIType.NOMBRE, 0, 10, "x" * 10, 0.7)
    b = Entity(PIIType.CORREO, 5, 15, "y" * 10, 0.9)
    c = Entity(PIIType.TELEFONO, 20, 25, "z" * 5, 0.9)
    assert resolve_overlaps([a, b, c]) == [b, c]
    d = Entity(PIIType.CEDULA, 0, 5, "x" * 5, 0.9)
    e = Entity(PIIType.TELEFONO, 0, 5, "x" * 5, 0.9)
    assert resolve_overlaps([e, d]) == [d]  # misma confianza: gana el de mayor prioridad


def test_entity_to_dict():
    ent = detect("correo a@example.com")[0]
    data = ent.to_dict()
    assert data["type"] == "CORREO" and data["text"] == "a@example.com"


def test_coerce_types():
    assert coerce_types(None) == tuple(PIIType)
    assert coerce_types(["nit", "NIT", "cuenta bancaria"]) == (PIIType.NIT, PIIType.CUENTA_BANCARIA)


def test_texto_largo_es_rapido():
    import time

    texto = (TEXTO + "\n") * 500
    t0 = time.perf_counter()
    ents = detect(texto)
    assert time.perf_counter() - t0 < 10
    assert len(ents) == 6 * 500
