"""Modos de anonimización: etiqueta, enmascarado parcial y seudonimización reversible."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
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
    PIIType.TARJETA_CREDITO: 4,  # los últimos 4 dígitos, como permite PCI DSS
    PIIType.DIRECCION_IP: 0,
    PIIType.FECHA_NACIMIENTO: 0,
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


_AT_RE = re.compile(r"@|\s*[\(\[\{<]\s*(?i:at|arroba)\s*[\)\]\}>]\s*|\s+(?i:arroba)\s+")
_LETTERS_RE = re.compile(r"[^\W\d_]+")


def _mask_email(value: str) -> str:
    parts = _AT_RE.split(value, maxsplit=1)
    local, domain = (parts[0], parts[1]) if len(parts) == 2 else (value, "")
    host, dot, tld = domain.rpartition(".")
    if not dot or not tld.isalpha():  # sin TLD reconocible: no se conserva nada del dominio
        return f"{local[:1]}***@***"
    return f"{local[:1]}***@{host[:1]}***.{tld}"


def _mask_name(value: str) -> str:
    """Conserva la inicial de cada parte del nombre y oculta el resto (y su longitud).

    Cualquier separador (espacio, tabulador, espacio duro, guion, apóstrofo) se respeta, de modo
    que «Ana-María» o «Juan\u00a0Pérez» quedan enmascarados igual que «Ana María».
    """
    return _LETTERS_RE.sub(lambda m: m.group()[0] + "*" * max(len(m.group()) - 1, 2), value)


def _mask_address(value: str) -> str:
    via = re.match(r"[^\W\d_]+\.?", value)
    if via is None or via.end() == len(value.rstrip()):
        return _mask_alnum(value, 0)
    return value[: via.end()] + _mask_alnum(value[via.end() :], 0)


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
        # Seudónimos que reemplazaron una celda NUMÉRICA de Excel (números, fechas): al
        # restaurar se devuelven como número para conservar el tipo y el formato de la celda.
        self.numeric_tokens: set[str] = set()

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
        payload: dict[str, object] = {"version": self.VERSION, "mapping": self._token_to_value}
        if self.numeric_tokens:
            payload["numericos"] = sorted(self.numeric_tokens)
        return json.dumps(payload, ensure_ascii=False, indent=2)

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
        numeric = payload.get("numericos", [])
        if not isinstance(numeric, list) or not all(
            tok in table._token_to_value for tok in numeric
        ):
            raise ValueError("Entrada inválida en la tabla: numericos")
        table.numeric_tokens = set(numeric)
        return table

    def save(self, path: str | os.PathLike[str]) -> None:
        """Guarda la tabla en JSON con permisos ``0600`` (solo el propietario).

        La escritura es atómica: se escribe un archivo temporal en la misma carpeta y luego se
        reemplaza el destino. Si el proceso se interrumpe, la tabla anterior sigue intacta (sin
        ella, la seudonimización sería irreversible).
        """
        target = Path(path)
        fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(self.to_json())
                handle.flush()
                os.fsync(handle.fileno())
            with contextlib.suppress(OSError):  # sistemas de archivos sin permisos POSIX
                os.chmod(tmp, 0o600)
            os.replace(tmp, target)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

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
    new_text = replace_entities(texto, entities, mode, table)
    return AnonymizationResult(new_text, entities, table if mode == "seudonimo" else None)


def replace_entities(
    texto: str, entities: Iterable[Entity], modo: str, tabla: PseudonymTable | None = None
) -> str:
    """Reemplaza ``entities`` (ordenadas y sin solapes) en ``texto`` según ``modo``."""
    mode = normalize_mode(modo)
    if mode == "seudonimo" and tabla is None:
        tabla = PseudonymTable()
    pieces: list[str] = []
    cursor = 0
    for ent in entities:
        pieces.append(texto[cursor : ent.start])
        pieces.append(_replacement(ent, mode, tabla))
        cursor = ent.end
    pieces.append(texto[cursor:])
    return "".join(pieces)


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
