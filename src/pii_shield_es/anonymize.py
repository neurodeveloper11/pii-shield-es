"""Modos de anonimización: etiqueta, enmascarado parcial y seudonimización reversible."""

from __future__ import annotations

import contextlib
import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .detectors import detect
from .types import Entity, PIIType

_MODE_ALIASES = {
    "etiqueta": "etiqueta",
    "label": "etiqueta",
    "tag": "etiqueta",
    "mascara": "mascara",
    "máscara": "mascara",
    "mask": "mascara",
    "masked": "mascara",
    "seudonimo": "seudonimo",
    "seudónimo": "seudonimo",
    "seudonimizar": "seudonimo",
    "pseudonym": "seudonimo",
    "pseudonymize": "seudonimo",
}
MODES = ("etiqueta", "mascara", "seudonimo")

# Cuántos caracteres alfanuméricos finales se conservan al enmascarar cada tipo.
_MASK_KEEP_LAST: dict[PIIType, int] = {
    PIIType.CEDULA: 3,
    PIIType.CEDULA_EXTRANJERIA: 3,
    PIIType.NIT: 1,
    PIIType.PASAPORTE: 2,
    PIIType.TELEFONO: 3,
    PIIType.PLACA: 0,
    PIIType.CUENTA_BANCARIA: 4,
}

_TOKEN_RE = re.compile(r"\[([A-Z_]+)_(\d+)\]")


def normalize_mode(modo: str) -> str:
    """Devuelve el nombre canónico del modo o lanza ``ValueError``."""
    try:
        return _MODE_ALIASES[str(modo).strip().lower()]
    except KeyError:
        raise ValueError(
            f"Modo desconocido: {modo!r}. Válidos: etiqueta, mascara, seudonimo"
        ) from None


# --------------------------------------------------------------------------- etiqueta


def label_for(tipo: PIIType) -> str:
    return f"[{tipo.value}]"


# --------------------------------------------------------------------------- máscara


def _mask_alnum(value: str, keep_last: int, keep_first: int = 0, mask: str = "*") -> str:
    """Enmascara los alfanuméricos conservando separadores, el inicio y el final indicados."""
    positions = [i for i, c in enumerate(value) if c.isalnum()]
    protected = set(positions[:keep_first])
    if keep_last > 0:
        protected.update(positions[-keep_last:])
    out = list(value)
    for i in positions:
        if i not in protected:
            out[i] = mask
    return "".join(out)


def _mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    host, dot, tld = domain.rpartition(".")
    if not dot:  # dominio sin punto: no se conserva nada de él
        return f"{local[:1]}***@***"
    return f"{local[:1]}***@{host[:1]}***.{tld}"


def _mask_name(value: str) -> str:
    return " ".join(
        word[:1] + "*" * max(len(word) - 1, 2) if word.isalpha() else word
        for word in value.split(" ")
    )


def _mask_address(value: str) -> str:
    first, sep, rest = value.partition(" ")
    if not sep:
        return _mask_alnum(value, 0)
    return f"{first} {_mask_alnum(rest, 0)}"


def mask_value(tipo: PIIType, value: str) -> str:
    """Enmascarado parcial específico por tipo (conserva formato y pocos caracteres útiles)."""
    if tipo is PIIType.CORREO:
        return _mask_email(value)
    if tipo is PIIType.NOMBRE:
        return _mask_name(value)
    if tipo is PIIType.DIRECCION:
        return _mask_address(value)
    return _mask_alnum(value, _MASK_KEEP_LAST.get(tipo, 0))


# --------------------------------------------------------------------------- seudónimos


class PseudonymTable:
    """Tabla local ``seudónimo -> valor original`` que permite revertir la anonimización.

    ATENCIÓN: la tabla contiene los datos personales originales. Trátala como un dato
    sensible: guárdala cifrada o con permisos restrictivos, separada del texto
    anonimizado, y nunca la subas a un repositorio.

    El mismo texto original (idéntico carácter a carácter y del mismo tipo) recibe siempre
    el mismo seudónimo dentro de una tabla, lo que conserva la correlación entre apariciones.
    """

    VERSION = 1

    def __init__(self) -> None:
        self._token_to_value: dict[str, str] = {}
        self._value_to_token: dict[tuple[str, str], str] = {}
        self._counters: dict[str, int] = {}

    def __len__(self) -> int:
        return len(self._token_to_value)

    @property
    def mapping(self) -> dict[str, str]:
        """Copia de ``{seudónimo: original}``."""
        return dict(self._token_to_value)

    def token_for(self, tipo: PIIType, original: str) -> str:
        key = (tipo.value, original)
        token = self._value_to_token.get(key)
        if token is None:
            n = self._counters.get(tipo.value, 0) + 1
            self._counters[tipo.value] = n
            token = f"[{tipo.value}_{n}]"
            self._value_to_token[key] = token
            self._token_to_value[token] = original
        return token

    def restore(self, text: str) -> str:
        """Reemplaza cada seudónimo conocido por su valor original (los desconocidos se dejan)."""
        return _TOKEN_RE.sub(lambda m: self._token_to_value.get(m.group(0), m.group(0)), text)

    # -- persistencia ------------------------------------------------------------------

    def to_json(self) -> str:
        return json.dumps(
            {"version": self.VERSION, "mapping": self._token_to_value},
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def from_json(cls, data: str) -> PseudonymTable:
        payload = json.loads(data)
        if not isinstance(payload, dict) or payload.get("version") != cls.VERSION:
            raise ValueError("Formato de tabla no soportado")
        table = cls()
        for token, original in payload.get("mapping", {}).items():
            match = _TOKEN_RE.fullmatch(token)
            if match is None or not isinstance(original, str):
                raise ValueError(f"Entrada inválida en la tabla: {token!r}")
            tipo, n = match.group(1), int(match.group(2))
            table._token_to_value[token] = original
            table._value_to_token[(tipo, original)] = token
            table._counters[tipo] = max(table._counters.get(tipo, 0), n)
        return table

    def save(self, path: str | os.PathLike[str]) -> None:
        """Guarda la tabla en JSON con permisos ``0600`` (solo el propietario)."""
        target = Path(path)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(self.to_json())
        with contextlib.suppress(OSError):  # sistemas de archivos sin permisos POSIX
            target.chmod(0o600)

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> PseudonymTable:
        return cls.from_json(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- API


@dataclass
class AnonymizationResult:
    """Resultado detallado de :func:`anonymize_detailed`."""

    text: str
    entities: list[Entity] = field(default_factory=list)
    table: PseudonymTable | None = None


def _replacement(ent: Entity, modo: str, table: PseudonymTable | None) -> str:
    if modo == "etiqueta":
        return label_for(ent.type)
    if modo == "mascara":
        return mask_value(ent.type, ent.text)
    assert table is not None
    return table.token_for(ent.type, ent.text)


def anonymize_detailed(
    texto: str,
    modo: str = "etiqueta",
    *,
    tipos: Iterable[PIIType | str] | PIIType | str | None = None,
    tabla: PseudonymTable | None = None,
    min_score: float = 0.0,
) -> AnonymizationResult:
    """Como :func:`anonymize`, pero devuelve también las entidades y la tabla usada."""
    mode = normalize_mode(modo)
    entities = detect(texto, tipos=tipos, min_score=min_score)
    table = tabla
    if mode == "seudonimo" and table is None:
        table = PseudonymTable()  # consistente dentro de la llamada, pero no recuperable
    pieces: list[str] = []
    cursor = 0
    for ent in entities:
        pieces.append(texto[cursor : ent.start])
        pieces.append(_replacement(ent, mode, table))
        cursor = ent.end
    pieces.append(texto[cursor:])
    return AnonymizationResult("".join(pieces), entities, table if mode == "seudonimo" else None)


def anonymize(
    texto: str,
    modo: str = "etiqueta",
    *,
    tipos: Iterable[PIIType | str] | PIIType | str | None = None,
    tabla: PseudonymTable | None = None,
    min_score: float = 0.0,
) -> str:
    """Anonimiza ``texto``.

    Args:
        texto: texto de entrada.
        modo: ``"etiqueta"`` (``[CEDULA]``), ``"mascara"`` (enmascarado parcial) o
            ``"seudonimo"`` (``[CEDULA_1]``; reversible si se pasa ``tabla``).
        tipos: restringe los tipos a anonimizar.
        tabla: :class:`PseudonymTable` que acumula el mapeo en modo ``seudonimo``.
        min_score: umbral mínimo de confianza.
    """
    return anonymize_detailed(texto, modo, tipos=tipos, tabla=tabla, min_score=min_score).text


def deanonymize(texto: str, tabla: PseudonymTable) -> str:
    """Revierte una seudonimización usando la tabla local."""
    return tabla.restore(texto)
