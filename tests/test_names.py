import pytest

from conftest import found
from datashield_es import PIIType


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Habla Carlos Andrés Gómez desde la oficina", "Carlos Andrés Gómez"),
        ("Me llamo Yeimy Fonseca y quiero reclamar", "Yeimy Fonseca"),  # nombre fuera de lista
        ("Estimado Julián Restrepo: adjunto", "Julián Restrepo"),
        ("Hola Sofía, gracias por escribir", "Sofía"),
        ("El paciente Luis Fernando Rojas Pineda ingresó", "Luis Fernando Rojas Pineda"),
        ("NOMBRE: MARÍA FERNANDA LÓPEZ MARÍN", "MARÍA FERNANDA LÓPEZ MARÍN"),
        ("La reunión es con Andrés Felipe Cardona mañana", "Andrés Felipe Cardona"),
        ("Dra. Paola Quintero atiende", "Paola Quintero"),
        ("Señora Luz Marina Salazar pase a caja", "Luz Marina Salazar"),
        ("Atendió María de los Ángeles Gómez en recepción", "María de los Ángeles Gómez"),
        ("Entregó Juan de Dios Pérez sin demora", "Juan de Dios Pérez"),
        ("Gracias, Valentina Cruz, por todo", "Valentina Cruz"),
        ("Contacto: Camila Vélez, correo", "Camila Vélez"),
        ("Señor Pérez llamó", "Pérez"),
        ("Hablé con Juan Perez ayer", "Juan Perez"),  # sin tilde
        ("JUAN CAMILO PEREZ GOMEZ", "JUAN CAMILO PEREZ GOMEZ"),
        ("Don Álvaro Uribe Vélez", "Álvaro Uribe Vélez"),
        ("Apellidos: Torres Zapata", "Torres Zapata"),
        ("Cliente: Marta Rodríguez, CC", "Marta Rodríguez"),
    ],
)
def test_detecta(text, expected):
    assert found(text, PIIType.NOMBRE) == [expected]


def test_dos_nombres_separados_por_y():
    assert found("Entregó Pablo Orjuela y Natalia Ballesteros los documentos", PIIType.NOMBRE) == [
        "Pablo Orjuela",
        "Natalia Ballesteros",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Viajé de Santiago de Cali a Santa Marta",
        "Visité el Hospital San Juan de Dios",
        "Estudió en la Universidad Nacional de Colombia",
        "Pagó en el Banco de Bogotá",
        "Rosa es una flor muy común",
        "La luz verde del semáforo",
        "El Ministerio de Hacienda y Crédito Público",
        "Santa Marta y San Andrés son destinos",
        "Gracias por su atención",
        "Buenos días a todos",
        "Señor Presidente",
        "Rosa Blanco",  # dos palabras ambiguas sin contexto: no se declara nombre
        "Luna Torres",
        "Juan",  # un solo nombre sin contexto
        "Colegio Santa María",
        "Bogotá Medellín Cali",
        "El Juan",
    ],
)
def test_no_detecta(text):
    assert found(text, PIIType.NOMBRE) == []


def test_limites_conocidos_documentados():
    # Nombres fuera de las listas y sin contexto: NO se detectan (límite de las reglas).
    assert found("Ayer hablé con Yeimy Orjuelita sobre el tema", PIIType.NOMBRE) == []
    # Nombres en minúsculas: tampoco.
    assert found("me escribió juan perez ayer", PIIType.NOMBRE) == []


def test_nombre_no_invade_otros_tipos():
    from datashield_es import detect

    ents = detect("Contacto: Camila Vélez, correo camila.velez@example.com")
    assert [e.type for e in ents] == [PIIType.NOMBRE, PIIType.CORREO]


def test_no_cruza_saltos_de_linea():
    assert found("Juan\nPérez", PIIType.NOMBRE) == []


def test_normalize_tolera_tildes_y_enie():
    from datashield_es._names import normalize

    assert normalize("PÉREZ") == "perez"
    assert normalize("Ñoño") == "nono"


def test_nombre_desconocido_a_mitad_de_frase_junto_a_apellido_conocido():
    assert found("Contactar a Yeimy Pérez hoy", PIIType.NOMBRE) == ["Yeimy Pérez"]


def test_apellido_desconocido_final_se_conserva_pero_no_ciudades():
    assert found("Hablé con Juan Pérez Mondragón hoy", PIIType.NOMBRE) == ["Juan Pérez Mondragón"]
    assert found("Hablé con Juan Pérez Bogotá hoy", PIIType.NOMBRE) == ["Juan Pérez"]
