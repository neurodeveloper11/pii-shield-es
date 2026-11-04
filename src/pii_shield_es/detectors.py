"""Detectores basados en reglas (regex + contexto + checksum). Sin red, sin modelos."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import NamedTuple

from . import _names
from .types import PRIORITY, Entity, PIIType, coerce_types
from .validators import is_valid_clabe, is_valid_iban, is_valid_nit

Detector = Callable[[str], list[Entity]]

# --------------------------------------------------------------------------- utilidades


def _entity(tipo: PIIType, text: str, start: int, end: int, score: float, detector: str) -> Entity:
    return Entity(tipo, start, end, text[start:end], score, detector)


def _line_before(text: str, pos: int, size: int = 60) -> str:
    """Hasta ``size`` caracteres anteriores a ``pos``, sin cruzar saltos de línea."""
    chunk = text[max(0, pos - size) : pos]
    cut = chunk.rfind("\n")
    return chunk[cut + 1 :] if cut >= 0 else chunk


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


# Prefijo opcional entre una palabra clave y el número: «No.», «número», «:», «#»...
_IS = r"(?:(?i:(?:es|era|fue)(?:\s+(?:el|la))?)[\s:.#-]{1,3})?"  # «mi cédula es 123...»
_NUM_PREFIX = r"[\s:.#-]{0,3}" + _IS + r"(?:(?i:n[uú]mero|n[oº°]|nro|num)\.?[\s:.#-]{0,3})?"
# Fin de número: no seguido de otro dígito ni de «.dígito».
_NUM_END = r"(?!\d|[.,]\d)"
# Inicio de número: no precedido de dígito ni de «dígito + separador».
_NUM_START = r"(?<!\d)(?<!\d[.,-])"

# --------------------------------------------------------------------------- cédulas

_ID_NUMBER = r"(?P<num>\d{1,3}(?:\.\d{3}){1,3}|\d{6,10})" + _NUM_END
_CC_KEYWORD = (
    r"(?:c[eé]dula(?:\s+de\s+ciudadan[ií]a)?(?!\s+de\s+extranjer[ií]a)"
    r"|\bc\.\s?c\b\.?|\bcc\b"
    r"|documento\s+de\s+identidad|doc\.?\s+de\s+identidad|identificaci[oó]n"
    r"|tarjeta\s+de\s+identidad|\bt\.\s?i\b\.?|\bnuip\b)"
)
_CC_RE = re.compile(_CC_KEYWORD + _NUM_PREFIX + _ID_NUMBER, re.IGNORECASE)

_CE_KEYWORD = r"(?:(?i:c[eé]dula\s+de\s+extranjer[ií]a)|\bC\.\s?E\b\.?|\bCE\b)"
_CE_RE = re.compile(
    _CE_KEYWORD + _NUM_PREFIX + r"(?P<num>\d{1,3}(?:\.\d{3}){1,2}|\d{6,7})" + _NUM_END
)


def detect_cedula(text: str) -> list[Entity]:
    """Cédula de ciudadanía: solo con palabra clave de contexto (evita confundir con montos)."""
    found = []
    for m in _CC_RE.finditer(text):
        if 6 <= len(_digits(m["num"])) <= 10:
            found.append(
                _entity(PIIType.CEDULA, text, m.start("num"), m.end("num"), 0.92, "cc_ctx")
            )
    return found


def detect_cedula_extranjeria(text: str) -> list[Entity]:
    """Cédula de extranjería (6-7 dígitos) con contexto «C.E.» / «cédula de extranjería»."""
    found = []
    for m in _CE_RE.finditer(text):
        if 6 <= len(_digits(m["num"])) <= 7:
            found.append(
                _entity(
                    PIIType.CEDULA_EXTRANJERIA, text, m.start("num"), m.end("num"), 0.92, "ce_ctx"
                )
            )
    return found


# --------------------------------------------------------------------------- NIT

_NIT_KW = r"(?i:\bn\.?\s?i\.?\s?t\b\.?)"
_NIT_BASE = r"(?:\d{1,3}(?:\.\d{3}){2,3}|\d{6,10})"
_NIT_DV_RE = re.compile(
    rf"(?<![\d.,-])(?P<kw>{_NIT_KW}{_NUM_PREFIX})?(?P<base>{_NIT_BASE})\s?[-–]\s?(?P<dv>\d)(?!\d)"
)
_NIT_KW_RE = re.compile(rf"{_NIT_KW}{_NUM_PREFIX}(?P<base>{_NIT_BASE})(?!\d|[.-]\d)")


def detect_nit(text: str) -> list[Entity]:
    """NIT. Con DV se valida el checksum de la DIAN; sin DV exige la palabra «NIT»."""
    found: list[Entity] = []
    for m in _NIT_DV_RE.finditer(text):
        base_digits = _digits(m["base"])
        if not 6 <= len(base_digits) <= 10:
            continue
        valid = is_valid_nit(base_digits, m["dv"])
        has_kw = m["kw"] is not None
        if valid:
            score = 0.97 if has_kw else 0.9
        elif has_kw:
            score = 0.55  # NIT declarado pero con DV incorrecto: probable error de digitación
        else:
            continue
        found.append(_entity(PIIType.NIT, text, m.start("base"), m.end("dv"), score, "nit_dv"))
    for m in _NIT_KW_RE.finditer(text):
        if 6 <= len(_digits(m["base"])) <= 10:
            found.append(
                _entity(PIIType.NIT, text, m.start("base"), m.end("base"), 0.75, "nit_ctx")
            )
    return found


# --------------------------------------------------------------------------- pasaporte

_PASSPORT_RE = re.compile(
    r"(?i:pasaporte|passport)"
    r"(?i:(?:\s+(?:colombiano|colombiana|vigente|extranjero|extranjera))?"
    r"(?:\s+(?:n[uú]mero|n[oº°]|nro|num))?\.?)"
    r"[\s:#.-]{0,3}" + _IS + r"(?P<num>(?=[A-Z0-9]*\d{5})[A-Z0-9]{6,9})(?![A-Za-z0-9])"
)


def detect_pasaporte(text: str) -> list[Entity]:
    """Pasaporte: letras/dígitos mayúsculos (6-9) tras la palabra «pasaporte»."""
    return [
        _entity(PIIType.PASAPORTE, text, m.start("num"), m.end("num"), 0.9, "pasaporte_ctx")
        for m in _PASSPORT_RE.finditer(text)
    ]


# --------------------------------------------------------------------------- teléfonos

_SEP = r"[\s.-]?"
_CC57 = r"(?:(?:\+|00)?57[\s.-]?|\(\+?57\)[\s.-]?)"
_PHONE_END = r"(?!\d|[.,]\d)"
_MOBILE_RE = re.compile(
    _NUM_START
    + rf"(?:{_CC57})?"
    + rf"\(?3[0-35]\d\)?{_SEP}(?:\d{{3}}{_SEP}\d{{4}}|\d{{3}}{_SEP}\d{{2}}[\s.-]\d{{2}})"
    + _PHONE_END
)
_LANDLINE_PAREN_RE = re.compile(
    _NUM_START
    + rf"(?:{_CC57})?"
    + rf"\(\s?(?:60)?[1-8]\s?\){_SEP}\d{{3}}{_SEP}\d{{4}}"
    + _PHONE_END
)
_LANDLINE_60_RE = re.compile(
    _NUM_START + rf"(?:{_CC57})?60[1-8]{_SEP}\d{{3}}{_SEP}\d{{4}}" + _PHONE_END
)
_LANDLINE_INTL_RE = re.compile(
    _NUM_START + rf"(?:\+|00)57[\s.-]?(?:60)?[1-8]{_SEP}\d{{3}}{_SEP}\d{{4}}" + _PHONE_END
)
_PHONE_KW_RE = re.compile(
    r"(?<![A-Za-z])(?i:tel(?:[eé]fono)?s?\.?|tlf\.?|fijo|pbx|conmutador)"
    r"[\s:.#-]{0,4}"
    + _IS
    + rf"(?P<num>(?:{_CC57})?(?:\d{{7,10}}|\d{{3}}[\s.-]\d{{4}}|\d{{3}}[\s.-]\d{{2}}[\s.-]\d{{2}}))"
    + _PHONE_END
)


def detect_telefono(text: str) -> list[Entity]:
    """Teléfonos colombianos: móviles (3xx), fijos con indicativo y números con contexto."""
    found: list[Entity] = []
    for regex, score, name in (
        (_MOBILE_RE, 0.9, "movil"),
        (_LANDLINE_PAREN_RE, 0.88, "fijo_paren"),
        (_LANDLINE_60_RE, 0.85, "fijo_60"),
        (_LANDLINE_INTL_RE, 0.88, "fijo_57"),
    ):
        for m in regex.finditer(text):
            found.append(_entity(PIIType.TELEFONO, text, m.start(), m.end(), score, name))
    for m in _PHONE_KW_RE.finditer(text):
        found.append(_entity(PIIType.TELEFONO, text, m.start("num"), m.end("num"), 0.86, "tel_ctx"))
    return found


# --------------------------------------------------------------------------- correo

_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9][A-Za-z0-9._%+-]*@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}"
)


def detect_correo(text: str) -> list[Entity]:
    """Correos electrónicos."""
    return [
        _entity(PIIType.CORREO, text, m.start(), m.end(), 0.98, "email")
        for m in _EMAIL_RE.finditer(text)
        if not m.group().split("@")[0].endswith(".")
    ]


# --------------------------------------------------------------------------- direcciones

_VIA = (
    r"(?:avenida|av\.?|autopista|calle|cll?\.?|carrera|cra\.?|crr\.?|kr\.?|cr\.?"
    r"|diagonal|diag\.?|dg\.?|transversal|trans\.?|tv\.?|circular)"
)
_CARD = r"(?:sur|norte|este|oeste)"
_ADDR_NUM = rf"\d{{1,3}}[A-Za-z]?(?:\s?bis)?(?:\s?{_CARD})?"
_ADDR_MARK = r"(?:\s*(?:#|n[oº°]\.?|nro\.?|n[uú]mero)\s*|\s+)"
_ADDR_UNIT = (
    r"(?:apartamento|apto|apt|ap|oficina|ofc|of|casa|torre|interior|int|piso|local|bloque"
    r"|bodega|manzana|mz|lote|etapa)"
)
_PROPER = r"(?-i:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)"
_ADDRESS_RE = re.compile(
    rf"(?<![A-Za-z]){_VIA}\.?\s*(?:{_VIA}\.?\s*)?{_ADDR_NUM}{_ADDR_MARK}{_ADDR_NUM}"
    r"\s*[-–]\s*\d{1,3}(?!\d)"
    rf"(?:,?\s*{_ADDR_UNIT}\.?\s*(?:\d{{1,4}}[A-Za-z]?|(?-i:[A-Z]))\b){{0,3}}"
    rf"(?:,?\s+barrio\s+{_PROPER}(?:\s+(?:de\s+|del\s+)?{_PROPER}){{0,2}})?",
    re.IGNORECASE,
)


def detect_direccion(text: str) -> list[Entity]:
    """Direcciones urbanas colombianas (Calle/Carrera/Diagonal/Transversal/Avenida...)."""
    return [
        _entity(PIIType.DIRECCION, text, m.start(), m.end(), 0.9, "direccion")
        for m in _ADDRESS_RE.finditer(text)
    ]


# --------------------------------------------------------------------------- placas

_PLATE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<plate>[A-Za-z]{3}[\s-]?(?:\d{3}|\d{2}[A-Za-z]))(?![A-Za-z0-9])"
)
_PLATE_CTX = re.compile(
    r"(?i:placas?|matr[ií]cula|veh[ií]culo|carro|moto(?:cicleta)?|camioneta|autom[oó]vil"
    r"|taxi|bus|cami[oó]n|tractomula|volqueta|vehicular)\W{0,25}$"
)
_PLATE_STOP = frozenset(
    [
        "USB",
        "PDF",
        "ISO",
        "SQL",
        "CSS",
        "RFC",
        "DNS",
        "API",
        "SKU",
        "COP",
        "USD",
        "EUR",
        "BTC",
        "ETH",
        "VPN",
        "CPU",
        "GPU",
        "RAM",
        "SSD",
        "HDD",
        "LTE",
        "AWS",
        "TCP",
        "UDP",
        "FAQ",
        "CAD",
        "REF",
        "NIT",
        "DIAN",
        "IVA",
        "PIB",
        "RUT",
        "UVT",
        "SMS",
        "GPS",
        "DVD",
        "HTM",
    ]
)


def detect_placa(text: str) -> list[Entity]:
    """Placas colombianas: carro (ABC123) y moto (ABC12D). Sin contexto solo en formato compacto."""
    found = []
    for m in _PLATE_RE.finditer(text):
        plate = m["plate"]
        letters = plate[:3]
        context = bool(_PLATE_CTX.search(_line_before(text, m.start("plate"), 40)))
        compact = plate[3] not in " -"
        if context:
            score = 0.9
        elif compact and letters.isupper() and letters not in _PLATE_STOP:
            score = 0.5
        else:
            continue
        found.append(_entity(PIIType.PLACA, text, m.start("plate"), m.end("plate"), score, "placa"))
    return found


# --------------------------------------------------------------------------- cuentas

_ACCOUNT_KW_RE = re.compile(
    r"(?i:cuenta(?:\s+(?:de\s+ahorros?|corriente|bancaria|ahorros|n[uú]mero|no\.?|nro\.?))?"
    r"|cta\.?(?:\s*(?:de\s+)?(?:ahorros?|cte\.?|corriente))?|ahorros|corriente)"
    r"[\s:#.-]{0,4}" + _IS + r"(?:(?i:n[uú]mero|no\.?|nro\.?|n[°º])[\s:#.-]{0,3})?"
    r"(?P<num>\d[\d \t-]{6,24}\d)(?!\d)"
)
_IBAN_RE = re.compile(
    r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?:[ -]?[A-Z0-9]{4}){2,8}(?:[ -]?[A-Z0-9]{1,3})?(?![A-Za-z0-9])"
)
_CLABE_RE = re.compile(r"(?<!\d)\d{18}(?!\d)")


def _iban_prefix(candidate: str) -> str | None:
    """Devuelve el prefijo de ``candidate`` que sea un IBAN válido (prueba recortes en espacios)."""
    cuts = [len(candidate)] + [i for i in range(len(candidate) - 1, 14, -1) if candidate[i] in " -"]
    for cut in cuts:
        if is_valid_iban(candidate[:cut]):
            return candidate[:cut]
    return None


def detect_cuenta_bancaria(text: str) -> list[Entity]:
    """IBAN (checksum mod 97), CLABE (checksum) y cuentas colombianas con palabra clave."""
    found: list[Entity] = []
    for m in _IBAN_RE.finditer(text):
        valid = _iban_prefix(m.group())
        if valid is not None:
            found.append(
                _entity(
                    PIIType.CUENTA_BANCARIA, text, m.start(), m.start() + len(valid), 0.97, "iban"
                )
            )
    for m in _CLABE_RE.finditer(text):
        if is_valid_clabe(m.group()):
            found.append(_entity(PIIType.CUENTA_BANCARIA, text, m.start(), m.end(), 0.8, "clabe"))
    for m in _ACCOUNT_KW_RE.finditer(text):
        num = m["num"].rstrip(" \t-")
        if 8 <= len(_digits(num)) <= 20:
            found.append(
                _entity(
                    PIIType.CUENTA_BANCARIA,
                    text,
                    m.start("num"),
                    m.start("num") + len(num),
                    0.88,
                    "cuenta_ctx",
                )
            )
    return found


# --------------------------------------------------------------------------- nombres

_UPPER = "A-ZÁÉÍÓÚÜÑ"
_LOWER = "a-záéíóúüñ"
_NAME_WORD = rf"(?:[{_UPPER}][{_LOWER}]+(?:[-'’][{_UPPER}][{_LOWER}]+)?|[{_UPPER}]{{2,}})"
_CONNECTOR = r"(?:(?i:de[ ]+la|de[ ]+los|de[ ]+las|del|de))"
_RUN_RE = re.compile(rf"{_NAME_WORD}(?:[ \t\u00a0]+(?:{_CONNECTOR}[ \t\u00a0]+)?{_NAME_WORD})*")
_WORD_RE = re.compile(_NAME_WORD)

_STRICT_CTX = re.compile(
    r"(?i:nombres?(?:\s+completo)?|apellidos?|me\s+llamo|mi\s+nombre\s+es|se\s+llama|llamad[oa]"
    r"|firmad[oa]\s+por|firma|titular|paciente|beneficiari[oa]|solicitante|remitente"
    r"|destinatari[oa]|propietari[oa]|asegurad[oa]|deudor(?:a)?|acreedor(?:a)?"
    r"|representante(?:\s+legal)?|cliente|usuari[oa]|contacto|conductor(?:a)?"
    r"|a\s+nombre\s+de)\s*[:,\-–]?\s*$"
)
_WEAK_CTX = re.compile(
    r"(?i:se[ñn]or(?:a|es|as)?|sr\.?|sra\.?|don|do[ñn]a|doctor(?:a)?|dr\.?|dra\.?|ing\.?"
    r"|ingeniero|ingeniera|abogad[oa]|licenciad[oa]|lic\.?|profesor(?:a)?|prof\.?"
    r"|estimad[oa]s?|querid[oa]s?|hola|gracias|saludos|buenos\s+d[ií]as|buenas\s+(?:tardes|noches)"
    r"|atentamente|cordialmente)\s*[:,\-–]?\s*$"
)
_SENTENCE_END = frozenset('.!?¡¿\n:;"“(-•*')
_LISTED = _names.FIRST_NAMES | _names.SURNAMES
_MAX_NAME_WORDS = 5


class _Word(NamedTuple):
    start: int
    end: int
    norm: str


def _is_sentence_start(text: str, pos: int) -> bool:
    prev = text[:pos].rstrip(" \t\u00a0")
    return not prev or prev[-1] in _SENTENCE_END


def _evaluate_run(text: str, run_start: int, run_end: int) -> Entity | None:
    words = [
        _Word(run_start + w.start(), run_start + w.end(), _names.normalize(w.group()))
        for w in _WORD_RE.finditer(text[run_start:run_end])
    ]
    before = _line_before(text, run_start, 40)
    strict = bool(_STRICT_CTX.search(before))
    trigger = strict or bool(_WEAK_CTX.search(before))
    sentence_start = _is_sentence_start(text, run_start)

    while words and words[0].norm in _names.TITLES:
        words.pop(0)
        trigger = True
        sentence_start = False

    while words and words[0].norm not in _LISTED:
        if trigger and words[0].norm not in _names.STOPWORDS:
            break
        nxt = words[1].norm if len(words) > 1 else None
        if (
            not trigger
            and not (sentence_start or words[0].norm in _names.STOPWORDS)
            and (nxt in _LISTED)
        ):
            break
        words.pop(0)
        sentence_start = False

    while words and words[-1].norm not in _LISTED:
        prev = words[-2].norm if len(words) > 1 else None
        if words[-1].norm in _names.STOPWORDS or (not trigger and prev not in _LISTED):
            words.pop()
        else:
            break

    words = words[:_MAX_NAME_WORDS]
    if not words:
        return None

    listed = [w for w in words if w.norm in _LISTED]
    firsts = [w for w in words if w.norm in _names.FIRST_NAMES]
    strong = [w for w in listed if w.norm not in _names.AMBIGUOUS]

    if trigger:
        accepted = len(words) >= 2 or bool(listed) or strict
        score = 0.85 if listed else 0.7
    else:
        accepted = bool(firsts) and len(listed) >= 2 and bool(strong)
        score = 0.8 if len(strong) >= 2 else 0.7
    if not accepted:
        return None
    return _entity(PIIType.NOMBRE, text, words[0].start, words[-1].end, score, "nombre")


def detect_nombre(text: str) -> list[Entity]:
    """Nombres propios por listas (nombres/apellidos frecuentes) y contexto («señor», «nombre:»)."""
    found = []
    for m in _RUN_RE.finditer(text):
        entity = _evaluate_run(text, m.start(), m.end())
        if entity is not None:
            found.append(entity)
    return found


# --------------------------------------------------------------------------- orquestación

DETECTORS: dict[PIIType, tuple[Detector, ...]] = {
    PIIType.CEDULA: (detect_cedula,),
    PIIType.CEDULA_EXTRANJERIA: (detect_cedula_extranjeria,),
    PIIType.NIT: (detect_nit,),
    PIIType.PASAPORTE: (detect_pasaporte,),
    PIIType.TELEFONO: (detect_telefono,),
    PIIType.CORREO: (detect_correo,),
    PIIType.DIRECCION: (detect_direccion,),
    PIIType.PLACA: (detect_placa,),
    PIIType.CUENTA_BANCARIA: (detect_cuenta_bancaria,),
    PIIType.NOMBRE: (detect_nombre,),
}

_PRIORITY_INDEX = {t: i for i, t in enumerate(PRIORITY)}


def resolve_overlaps(entities: Iterable[Entity]) -> list[Entity]:
    """Conserva, entre detecciones solapadas, la de mayor puntaje (luego prioridad y longitud)."""
    ordered = sorted(
        entities,
        key=lambda e: (-e.score, _PRIORITY_INDEX[e.type], -(e.end - e.start), e.start),
    )
    chosen: list[Entity] = []
    for ent in ordered:
        if all(ent.end <= c.start or ent.start >= c.end for c in chosen):
            chosen.append(ent)
    return sorted(chosen, key=lambda e: (e.start, e.end))


def detect(
    texto: str,
    *,
    tipos: Iterable[PIIType | str] | PIIType | str | None = None,
    min_score: float = 0.0,
) -> list[Entity]:
    """Detecta datos personales en ``texto``.

    Args:
        texto: texto en español.
        tipos: restringe la búsqueda a estos tipos (``PIIType`` o cadenas como ``"NIT"``).
        min_score: descarta detecciones con confianza menor a este umbral (0 a 1).

    Returns:
        Lista de :class:`Entity` ordenada por posición y sin solapamientos.
    """
    if not isinstance(texto, str):
        raise TypeError(f"texto debe ser str, no {type(texto).__name__}")
    found: list[Entity] = []
    for tipo in coerce_types(tipos):
        for detector in DETECTORS[tipo]:
            found.extend(detector(texto))
    return resolve_overlaps(e for e in found if e.score >= min_score)
