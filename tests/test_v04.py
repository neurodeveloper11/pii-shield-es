"""Pruebas de la v0.4: nombres (apellidos poco comunes, minúsculas, «Apellido, Nombre», una
palabra con contexto), cuentas con nombre de banco y cédulas con la palabra clave lejos."""

from __future__ import annotations

import pytest

from conftest import found
from datashield_es import PIIType, anonymize

N = PIIType.NOMBRE


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # nombre de pila conocido + apellidos fuera de las listas
        ("Ayer llamó Kevin Arley Mosquera para confirmar.", ["Kevin Arley Mosquera"]),
        ("Le entregué los documentos a Edwin Ararat en la portería.", ["Edwin Ararat"]),
        ("El reporte lo firmó Yamile Pertuz desde Barranquilla.", ["Yamile Pertuz"]),
        # una palabra con preposición o tratamiento
        ("Saludos a Hernán y a toda la familia.", ["Hernán"]),
        ("Pregúntale a Esteban por las llaves.", ["Esteban"]),
        ("Visité a doña Ofelia en el hospital.", ["Ofelia"]),
        # minúsculas
        ("hola, me llamo carlos andrés gómez y necesito ayuda", ["carlos andrés gómez"]),
        ("soy andrés felipe rojas del área de compras", ["andrés felipe rojas"]),
        ("ok gracias camila, quedo pendiente", ["camila"]),
        ("le pregunté a sandra milena y no sabía", ["sandra milena"]),
        # Apellido, Nombre
        ("Restrepo Gómez, Juliana — aprobada.", ["Restrepo Gómez", "Juliana"]),
        ("Cárdenas Vargas, Andrés Felipe: pendiente.", ["Cárdenas Vargas", "Andrés Felipe"]),
        ("GÓMEZ PÉREZ, LAURA figura en la lista.", ["GÓMEZ PÉREZ", "LAURA"]),
        ("Duarte Ramírez, Mariela aparece en el listado.", ["Duarte Ramírez", "Mariela"]),
    ],
)
def test_nombres_v04(text, expected):
    assert found(text, N) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Compré café Juan Valdez para la oficina.",
        "Vivo cerca de la estación San Diego del metro.",
        "El Santo Tomás de Aquino es patrono de los estudiantes.",
        "El Hospital Pablo Tobón Uribe recibió una donación.",
        "Fuimos al parque Jaime Duque el fin de semana.",
        "La avenida Jiménez estaba congestionada.",
        "tomas el bus en la esquina y te bajas en la plaza",
        "la rosa del jardín se marchitó con el verano",
        "el pastor cuida a las ovejas en el páramo",
        "mercedes y dolores son nombres antiguos, dijo la profesora",
        "Marcos y ventanas de aluminio a domicilio.",
        "Fuimos con Medellín y Cali a la final.",
        "Bogotá, Colombia es la capital.",
        "Gómez, Pérez y López firmaron como testigos.",
        "Juan",
    ],
)
def test_sin_falsos_positivos_de_nombre(text):
    assert found(text, N) == []


@pytest.mark.parametrize(
    ("text", "tipo", "expected"),
    [
        ("Consignar en Bancolombia 24567891234 a nombre de la empresa.", "CUENTA_BANCARIA",
         ["24567891234"]),
        ("Davivienda: 0550-1234-5678 para pagos", "CUENTA_BANCARIA", ["0550-1234-5678"]),
        ("El número de identificación del estudiante es 1.098.234.567.", "CEDULA",
         ["1.098.234.567"]),
        ("La tarjeta de identidad del niño que vino ayer es la 1.234.567.890.", "CEDULA",
         ["1.234.567.890"]),
    ],
)  # fmt: skip
def test_cuentas_y_cedulas_v04(text, tipo, expected):
    assert found(text, tipo) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Bancolombia cumple 150 años de historia.",
        "Pagos a Bancolombia por $1.500.000 se reflejan en 24 horas.",
        "Banco de Bogotá informa que la tasa subió a 12,5 %.",
        "La cédula de ciudadanía es el documento de identidad de los mayores de edad.",
        "La cédula del país es un documento que cuesta 52.000 pesos.",
    ],
)
def test_sin_falsos_positivos_de_cuentas_ni_cedulas(text):
    assert [e for e in found(text, "CUENTA_BANCARIA") + found(text, "CEDULA")] == []


def test_apellido_nombre_en_seudonimo_es_reversible():
    from datashield_es import PseudonymTable

    texto = "Inscritos: Martínez López, Sofía; Ortiz Ramírez, Mateo."
    tabla = PseudonymTable()
    anon = anonymize(texto, "seudonimo", tabla=tabla)
    assert anon == "Inscritos: [NOMBRE_1], [NOMBRE_2]; [NOMBRE_3], [NOMBRE_4]."
    assert tabla.restore(anon) == texto


def test_nombre_en_minuscula_se_enmascara():
    assert anonymize("hola soy valentina", "mascara") == "hola soy v********"
