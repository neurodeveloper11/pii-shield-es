"""Frases comunes que NO deben producir ninguna detección (control de falsos positivos)."""

import pytest

from pii_shield_es import detect

NEGATIVOS = [
    # montos, fechas, cantidades
    "El 15 de marzo de 2024 se pagaron $1.500.000 en 3 cuotas de $500.000.",
    "Total de la factura: $3.001.234 con IVA del 19 %.",
    "La reunión será el 12/05/2025 a las 10:30 en la sala principal.",
    "Tasa del 12,5 % EA con plazo de 36 meses.",
    "El salario mínimo de 2024 fue de $1.300.000 más auxilio de transporte.",
    "Se vendieron 1.234.567 unidades en el año.",
    "Hubo 3.500 asistentes y 120.000 visualizaciones.",
    "El precio subió de 1.250,50 a 1.310,75 dólares.",
    "El PIB creció 2,3 % en el tercer trimestre de 2023.",
    # códigos y referencias
    "Versión 3.10.4 de Python lanzada en 2023.",
    "Código postal 110111 y barrio sin número.",
    "Radicado 11001-31-03-005-2020-00123-00 del juzgado.",
    "Pedido 3001234567890 enviado por transportadora.",
    "Resolución 000123 del 5 de enero de 2020.",
    "Cumple la norma ISO 9001 y la ISO 27001.",
    "Modelo USB 300 de alta velocidad.",
    "Factura electrónica FE-2024-000123 emitida.",
    "El tracking es 1Z999AA10123456784 según la guía.",
    "Commit 3f2a9c1 y rama feature/login.",
    "Dirección IP 192.168.100.200 del servidor interno.",
    "Coordenadas 4.7110, -74.0721 en el mapa.",
    # normativa y conceptos
    "Según la Ley 1581 de 2012, el titular puede solicitar la supresión de sus datos.",
    "El decreto 1377 de 2013 reglamenta parcialmente la norma.",
    "Habeas Data es un derecho fundamental en Colombia.",
    "La Superintendencia de Industria y Comercio vigila el tratamiento de datos.",
    "Artículo 15 de la Constitución Política de Colombia.",
    # lugares e instituciones
    "Viajé de Santiago de Cali a Santa Marta en avión.",
    "Visité el Hospital San Juan de Dios por urgencias.",
    "Estudió en la Universidad Nacional de Colombia.",
    "Pagó en el Banco de Bogotá y en Bancolombia.",
    "El Ministerio de Hacienda y Crédito Público publicó la circular.",
    "Santa Marta y San Andrés son destinos turísticos.",
    "La Calle 100 es muy transitada en la mañana.",
    "En la Carrera 7 con calle 72 hay trancón siempre.",
    # palabras que también son nombres
    "Rosa es una flor muy común en los jardines.",
    "La luz verde del semáforo cambió rápido.",
    "Es un pilar fundamental de la economía.",
    "La paz es el valor más importante.",
    "Hubo mucha esperanza tras el anuncio.",
    # texto técnico y cotidiano
    "Sígueme en @usuario_ejemplo para más novedades.",
    "Tenga en cuenta 12 de los 15 puntos del acta.",
    "La cuenta de cobro fue enviada ayer.",
    "Llamen al 123 en caso de emergencia.",
    "Gracias por su atención, quedamos atentos.",
    "Buenos días, ¿cómo está usted?",
    "Hola a todos, bienvenidos a la sesión.",
    "def f(x):\n    return x * 3.14159\n",
    "SELECT * FROM clientes WHERE id = 1234567;",
]


@pytest.mark.parametrize("texto", NEGATIVOS)
def test_sin_detecciones(texto):
    assert detect(texto) == [], texto
