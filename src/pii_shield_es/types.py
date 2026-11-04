"""Tipos públicos: categorías de PII y entidades detectadas."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class PIIType(str, Enum):
    """Categorías de datos personales que reconoce la librería."""

    CEDULA = "CEDULA"
    CEDULA_EXTRANJERIA = "CEDULA_EXTRANJERIA"
    NIT = "NIT"
    PASAPORTE = "PASAPORTE"
    TELEFONO = "TELEFONO"
    CORREO = "CORREO"
    DIRECCION = "DIRECCION"
    PLACA = "PLACA"
    CUENTA_BANCARIA = "CUENTA_BANCARIA"
    NOMBRE = "NOMBRE"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# Orden de desempate cuando dos detecciones solapan con el mismo puntaje.
PRIORITY: tuple[PIIType, ...] = (
    PIIType.CORREO,
    PIIType.CUENTA_BANCARIA,
    PIIType.NIT,
    PIIType.CEDULA_EXTRANJERIA,
    PIIType.CEDULA,
    PIIType.PASAPORTE,
    PIIType.TELEFONO,
    PIIType.PLACA,
    PIIType.DIRECCION,
    PIIType.NOMBRE,
)


@dataclass(frozen=True)
class Entity:
    """Un fragmento de texto identificado como dato personal.

    ``start`` y ``end`` son índices de carácter sobre el texto original
    (``texto[start:end] == text``). ``score`` va de 0 a 1 y refleja la confianza
    heurística (no es una probabilidad calibrada).
    """

    type: PIIType
    start: int
    end: int
    text: str
    score: float
    detector: str = ""

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["type"] = self.type.value
        return data


def coerce_types(tipos: object) -> tuple[PIIType, ...]:
    """Normaliza una lista de tipos (``PIIType`` o cadenas) a ``PIIType``."""
    if tipos is None:
        return tuple(PIIType)
    if isinstance(tipos, (str, PIIType)):
        tipos = [tipos]
    result: list[PIIType] = []
    for item in tipos:  # type: ignore[attr-defined]
        if isinstance(item, PIIType):
            result.append(item)
            continue
        key = str(item).strip().upper().replace(" ", "_")
        try:
            result.append(PIIType(key))
        except ValueError as exc:
            valid = ", ".join(t.value for t in PIIType)
            raise ValueError(f"Tipo de PII desconocido: {item!r}. Válidos: {valid}") from exc
    return tuple(dict.fromkeys(result))
