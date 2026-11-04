"""Utilidades compartidas por las pruebas. Todos los datos son inventados."""

from __future__ import annotations

import pytest

from pii_shield_es import PIIType, detect
from pii_shield_es.validators import nit_check_digit


def nit(base: str, dotted: bool = False) -> str:
    """NIT sintético con DV válido."""
    shown = f"{int(base):,}".replace(",", ".") if dotted else base
    return f"{shown}-{nit_check_digit(base)}"


def found(text: str, tipo: PIIType | str, **kwargs) -> list[str]:
    """Textos detectados del tipo indicado."""
    tipo = PIIType(tipo) if isinstance(tipo, str) else tipo
    return [e.text for e in detect(text, **kwargs) if e.type is tipo]


@pytest.fixture
def types():
    return PIIType
