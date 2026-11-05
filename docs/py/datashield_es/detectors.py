"""Detectores basados en reglas (regex + contexto + checksum). Sin red, sin modelos."""

from __future__ import annotations

import bisect
import re
import unicodedata
from collections.abc import Callable, Iterable
from datetime import date
from typing import NamedTuple

from . import _names
from .types import PRIORITY, Entity, PIIType, coerce_types
from .validators import is_valid_card, is_valid_clabe, is_valid_iban, is_valid_ip, is_valid_nit

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

_ID_NUMBER = r"(?P<num>\d{1,3}(?:\.\d{3}){1,3}|\d{1,4}(?: \d{3}){2}|\d{6,10})" + _NUM_END
_CC_KEYWORD = (
    r"(?:c[eé]dula(?:\s+de\s+ciudadan[ií]a)?(?!\s+de\s+extranjer[ií]a)"
    r"|\bc\.\s?c\b\.?|\bcc\b"
    r"|documento\s+de\s+identidad|doc\.?\s+de\s+identidad|identificaci[oó]n"
    r"|tarjeta\s+de\s+identidad|\bt\.\s?i\b\.?|\bnuip\b"
    r"|\bdoc(?:umento)?\b\.?(?=\s*(?:[:#]|n[uú]mero|n[oº°]|nro|\d)))"
)
_CC_RE = re.compile(_CC_KEYWORD + _NUM_PREFIX + _ID_NUMBER, re.IGNORECASE)
# Palabra clave separada del número por una frase corta que termina en «es (el|la)»:
# «la tarjeta de identidad del niño que vino ayer es la 1.234.567.890».
_CC_FAR_RE = re.compile(
    r"(?:c[eé]dula(?:\s+de\s+ciudadan[ií]a)?(?!\s+de\s+extranjer[ií]a)|documento\s+de\s+identidad"
    r"|tarjeta\s+de\s+identidad|(?:n[uú]mero\s+de\s+)?identificaci[oó]n)"
    r"(?:\s+[a-záéíóúñ]+){1,6}?\s+(?:es|era|fue)(?:\s+(?:el|la))?\s*:?\s*" + _ID_NUMBER,
    re.IGNORECASE,
)

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
    for m in _CC_FAR_RE.finditer(text):
        if 6 <= len(_digits(m["num"])) <= 10:
            found.append(
                _entity(PIIType.CEDULA, text, m.start("num"), m.end("num"), 0.85, "cc_lejos")
            )
    return found


_PIDE_DOCUMENTO = re.compile(
    r"(?i:c[eé]dula|documento|identificaci[oó]n|\bc\.?\s?c\b|tarjeta\s+de\s+identidad|\bnuip\b)"
)
_ID_SUELTO_RE = re.compile(r"(?<![\d$.,])(?<!\$ )" + _ID_NUMBER)


def detect_cedula_dialogo(text: str, contexto: str) -> list[Entity]:
    """Cédula dictada como respuesta: la palabra clave está en el contexto, no en el texto.

    En una conversación el asesor pide el documento y el cliente responde, a veces varios
    turnos después, solo con el número. Los montos («$1.200.000») se excluyen.
    """
    if not _PIDE_DOCUMENTO.search(contexto):
        return []
    found = []
    for m in _ID_SUELTO_RE.finditer(text):
        if 6 <= len(_digits(m["num"])) <= 10:
            found.append(
                _entity(PIIType.CEDULA, text, m.start("num"), m.end("num"), 0.75, "cc_dialogo")
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
    + rf"(?:\(3[0-35]\d\)|3[0-35]\d){_SEP}"
    + rf"(?:\d{{3}}{_SEP}\d{{4}}|\d{{3}}{_SEP}\d{{2}}[\s.-]\d{{2}})"
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


_OBFUSCATED_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9][A-Za-z0-9._%+-]*"
    r"(?:\s*[\(\[\{<]\s*(?i:at|arroba)\s*[\)\]\}>]\s*|\s+(?i:arroba)\s+)"
    r"(?:[A-Za-z0-9-]+(?:\.|\s*[\(\[](?i:dot|punto)[\)\]]\s*))+[A-Za-z]{2,}\b"
)


def detect_correo(text: str) -> list[Entity]:
    """Correos electrónicos, incluidos los ofuscados («ana(at)example.com», «ana arroba ...»)."""
    found = [
        _entity(PIIType.CORREO, text, m.start(), m.end(), 0.98, "email")
        for m in _EMAIL_RE.finditer(text)
        if not m.group().split("@")[0].endswith(".")
    ]
    found += [
        _entity(PIIType.CORREO, text, m.start(), m.end(), 0.85, "email_ofuscado")
        for m in _OBFUSCATED_EMAIL_RE.finditer(text)
    ]
    return found


# --------------------------------------------------------------------------- direcciones

_VIA = (
    r"(?:avenida|av\.?|autopista|calle|cll?\.?|carrera|kra\.?|cra\.?|crr\.?|kr\.?|cr\.?"
    r"|ak\.?|ac\.?|diagonal|diag\.?|dg\.?|transversal|trans\.?|tv\.?|tr\.?|circular|cq\.?)"
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
_BARRIO = rf"(?:,?\s+barrio\s+{_PROPER}(?:\s+(?:de\s+|del\s+|el\s+|la\s+)?{_PROPER}){{0,2}})?"
# Vías con nombre: «Autopista Norte # 152-30», «Avenida Boyacá No. 64-20». Exige «#» o «No.».
_NAMED_ROAD_RE = re.compile(
    rf"(?<![A-Za-z])(?i:autopista|avenida|av\.?)\s+{_PROPER}(?:\s+(?:de\s+)?{_PROPER}){{0,2}}"
    rf"\s*(?i:#|n[oº°]\.?|nro\.?)\s*{_ADDR_NUM}\s*[-–]\s*\d{{1,3}}(?!\d)" + _BARRIO
)
# Manzana/casa: «Manzana 5 Casa 12 barrio El Prado», «Mz B Lote 7».
_BLOCK_RE = re.compile(
    r"(?<![A-Za-z])(?i:manzana|mz\.?)\s*(?:\d{1,3}|[A-Z])\b\s*,?\s*(?i:casa|lote|cs\.?)\s*\d{1,4}\b"
    + rf"(?:\s+(?i:barrio)\s+{_PROPER}(?:\s+(?:(?i:de|del|el|la)\s+)?{_PROPER}){{0,2}})?"
)


def detect_direccion(text: str) -> list[Entity]:
    """Direcciones urbanas colombianas (Calle/Carrera/Diagonal/Transversal/Avenida...)."""
    found = [
        _entity(PIIType.DIRECCION, text, m.start(), m.end(), 0.9, "direccion")
        for m in _ADDRESS_RE.finditer(text)
    ]
    found += [
        _entity(PIIType.DIRECCION, text, m.start(), m.end(), 0.86, "via_nombre")
        for m in _NAMED_ROAD_RE.finditer(text)
    ]
    found += [
        _entity(PIIType.DIRECCION, text, m.start(), m.end(), 0.85, "manzana")
        for m in _BLOCK_RE.finditer(text)
    ]
    return found


# --------------------------------------------------------------------------- placas

_PLATE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<plate>[A-Za-z]{3}[\s-]?(?:\d{3}|\d{2}[A-Za-z]))(?![A-Za-z0-9])"
)
_PLATE_CTX = re.compile(
    r"(?i:placas?|matr[ií]cula|veh[ií]culo|carro|moto(?:cicleta)?|camioneta|autom[oó]vil"
    r"|taxi|bus|cami[oó]n|tractomula|volqueta|vehicular)"
    r"(?:\W{1,3}(?i:es|era|de|del|la|el|su|mi|n[uú]mero|no|n[oº°]|tiene|con|moto)){0,3}\W{0,25}$"
)
# Códigos que se parecen a una placa pero no lo son («clave ABC123», «ref. PED123»).
_PLATE_ANTI_CTX = re.compile(
    r"(?i:clave|contrase[ñn]a|c[oó]digo|cod\.?|ref(?:erencia)?\.?|pedido|orden|usuario|modelo"
    r"|serial|lote|sku|cup[oó]n|pin|token|vuelo|sala|habitaci[oó]n)\W*(?:\w+\W+){0,2}$"
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
        elif (
            compact
            and letters.isupper()
            and letters not in _PLATE_STOP
            and not _PLATE_ANTI_CTX.search(_line_before(text, m.start("plate"), 40))
        ):
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
# Nombre del banco seguido del número: «Consignar en Bancolombia 24567891234».
_BANK_RE = re.compile(
    r"(?i:bancolombia|davivienda|bbva|colpatria|scotiabank|ita[uú]|banco\s+(?:de\s+bogot[aá]"
    r"|popular|de\s+occidente|agrario|caja\s+social|av\s+villas|falabella|pichincha|w)"
    r"|av\s+villas)"
    r"[\s:#.,-]{1,4}(?P<num>\d[\d \t-]{6,24}\d)(?!\d|[.,]\d)"
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
    for m in _BANK_RE.finditer(text):
        num = m["num"].rstrip(" \t-")
        if 8 <= len(_digits(num)) <= 20:
            found.append(
                _entity(
                    PIIType.CUENTA_BANCARIA,
                    text,
                    m.start("num"),
                    m.start("num") + len(num),
                    0.8,
                    "banco_ctx",
                )
            )
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


# --------------------------------------------------------------------------- tarjetas

_CARD_RE = re.compile(
    r"(?<![\d.,-])"
    r"(?:\d{4}(?:([ -])\d{4}){2}\1\d{4}(?:\1\d{1,3})?"  # 4-4-4-4(-1..3) con separador uniforme
    r"|\d{4}([ -])\d{6}\2\d{4,5}"  # Amex 4-6-5 / Diners 4-6-4
    r"|\d{13,19})"
    r"(?!\d|[.,-]\d)"
)
_CARD_CTX = re.compile(
    r"(?i:tarjeta|t\.?\s?c\b|tdc|cr[eé]dito|d[eé]bito|visa|master\s?card|amex|american\s+express"
    r"|diners|dat[aá]fono|card|pag[oóa]|cobro|n[uú]mero)"
)


def detect_tarjeta(text: str) -> list[Entity]:
    """Tarjetas de pago: prefijo IIN de una marca conocida, longitud válida y Luhn."""
    found = []
    for m in _CARD_RE.finditer(text):
        if not is_valid_card(m.group()):
            continue
        context = bool(_CARD_CTX.search(_line_before(text, m.start(), 40)))
        score = 0.97 if context else 0.85
        found.append(_entity(PIIType.TARJETA_CREDITO, text, m.start(), m.end(), score, "luhn"))
    return found


# --------------------------------------------------------------------------- direcciones IP

_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
_IPV4_RE = re.compile(rf"(?<![\w.])(?:{_OCTET}\.){{3}}{_OCTET}(?![\w]|\.\d)")
_IPV6_RE = re.compile(
    r"(?<![\w:.])(?=[0-9A-Fa-f:]*\d)[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7}(?![\w:])"
)
_IP_CTX = re.compile(r"(?i:\bip(?:v[46])?\b|host|servidor|equipo|conexi[oó]n|acceso|desde|origen)")
_VERSION_CTX = re.compile(r"(?i:versi[oó]n|\bv(?:er)?\.?|release|build|parche|actualiz)\W{0,3}$")


def detect_ip(text: str) -> list[Entity]:
    """Direcciones IPv4/IPv6 válidas. Omite versiones de software y direcciones no personales."""
    found = []
    for m in _IPV4_RE.finditer(text):
        value = m.group()
        before = _line_before(text, m.start(), 40)
        if _VERSION_CTX.search(before) or value.startswith(("0.", "127.", "255.")):
            continue
        score = 0.95 if _IP_CTX.search(before) else 0.8
        found.append(_entity(PIIType.DIRECCION_IP, text, m.start(), m.end(), score, "ipv4"))
    for m in _IPV6_RE.finditer(text):
        value = m.group()
        too_short = value.count(":") < 7 and "::" not in value
        if too_short or value == "::1" or not is_valid_ip(value):
            continue
        score = 0.95 if _IP_CTX.search(_line_before(text, m.start(), 40)) else 0.85
        found.append(_entity(PIIType.DIRECCION_IP, text, m.start(), m.end(), score, "ipv6"))
    return found


# --------------------------------------------------------------------------- fecha de nacimiento

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}  # fmt: skip
_BIRTH_KW = (
    r"(?i:fecha\s+de\s+nacimiento|f(?:echa)?\.?\s?(?:de\s+)?nac(?:imiento)?\.?|nacimiento"
    r"|naci[oó]|nac[ií]|nacid[oa]s?|cumplea[ñn]os|d\.?o\.?b\.?|born)"
)
# Entre la palabra clave y la fecha: «:», «el», «en Tunja el»...
_BIRTH_GAP = (
    r"(?:[\s:.,\-–]{0,3}(?i:(?:el|en|del|de|:)\s+){0,2}"
    r"(?:(?-i:[A-ZÁÉÍÓÚ][a-záéíóúñ]+)\s+(?i:el)\s+)?)"
)
_DATE_ALT = (
    r"(?P<dmy>(?P<d1>\d{1,2})[/.\-](?P<m1>\d{1,2})[/.\-](?P<y1>\d{4}))"
    r"|(?P<ymd>(?P<y2>\d{4})[/.\-](?P<m2>\d{1,2})[/.\-](?P<d2>\d{1,2}))"
    r"|(?P<txt>(?P<d3>\d{1,2})\s+de\s+(?P<m3>(?i:" + "|".join(_MONTHS) + r"))\s+(?i:del?)\s+"
    r"(?P<y3>\d{4}))"
)
_BIRTH_RE = re.compile(_BIRTH_KW + _BIRTH_GAP + r"(?P<date>" + _DATE_ALT + r")(?!\d)")


def _valid_date(day: str, month: str | int, year: str) -> bool:
    try:
        value = date(int(year), int(month), int(day))
    except ValueError:
        return False
    return 1900 <= value.year <= date.today().year


def detect_fecha_nacimiento(text: str) -> list[Entity]:
    """Fechas de nacimiento: solo con contexto («fecha de nacimiento», «nació el»...)."""
    found = []
    for m in _BIRTH_RE.finditer(text):
        if m["dmy"]:
            ok = _valid_date(m["d1"], m["m1"], m["y1"])
        elif m["ymd"]:
            ok = _valid_date(m["d2"], m["m2"], m["y2"])
        else:
            ok = _valid_date(m["d3"], _MONTHS[m["m3"].lower()], m["y3"])
        if ok:
            found.append(
                _entity(
                    PIIType.FECHA_NACIMIENTO, text, m.start("date"), m.end("date"), 0.9, "nac_ctx"
                )
            )
    return found


# --------------------------------------------------------------------------- nombres

_UPPER = "A-ZÁÉÍÓÚÜÑ"
_LOWER = "a-záéíóúüñ"
# Límites de palabra a ambos lados: «ConectaYa» no contiene el nombre «Conecta».
_NAME_WORD = (
    rf"(?<![\w])(?:[{_UPPER}][{_LOWER}]+(?:[-'’][{_UPPER}][{_LOWER}]+)?|[{_UPPER}]{{2,}})(?![\w])"
)
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
# Instituciones y lugares que suelen llevar nombre de persona («Universidad Francisco José de
# Caldas», «Colegio San José», «Parque Simón Bolívar»): si preceden a la secuencia, no es nombre.
_INSTITUTION = frozenset(
    [
        "universidad",
        "colegio",
        "escuela",
        "instituto",
        "fundacion",
        "hospital",
        "clinica",
        "parque",
        "plaza",
        "teatro",
        "hotel",
        "edificio",
        "conjunto",
        "urbanizacion",
        "centro",
        "estadio",
        "aeropuerto",
        "biblioteca",
        "museo",
        "corporacion",
        "liceo",
        "seminario",
        "iglesia",
        "parroquia",
        "capilla",
        "avenida",
        "calle",
        "carrera",
        "barrio",
        "vereda",
        "municipio",
        "club",
        "coliseo",
    ]
)
_INSTITUTION_BEFORE = re.compile(
    r"(?i:universidad|colegio|escuela|instituto|fundaci[oó]n|hospital|cl[ií]nica|parque|plaza"
    r"|teatro|hotel|edificio|conjunto|estadio|aeropuerto|biblioteca|museo|corporaci[oó]n|liceo"
    r"|iglesia|parroquia|estaci[oó]n|terminal|avenida|calle|carrera|barrio|almac[eé]n"
    r"|restaurante|caf[eé]|marca|empresa|compa[ñn][ií]a)\s+$"
)
# Prefijos de lugares y santos: «San Diego», «Santo Tomás», «Nuestra Señora».
_SAINT = frozenset(["san", "santo", "santa", "santisima", "santisimo", "nuestra", "virgen"])
# Marcas y lugares muy conocidos con forma de nombre de persona.
_NON_PERSON = frozenset(["juan valdez"])
# Una preposición justo antes de un nombre de pila conocido es contexto débil («Saludos a
# Hernán», «Habló con Mónica»).
_TITLE_BEFORE = re.compile(
    r"(?<![\w])(?i:se[ñn]or(?:a)?|sr\.?|sra\.?|don|do[ñn]a|doctor(?:a)?|dr\.?|dra\.?)\s+$"
)
_PREP_CTX = re.compile(r"(?<![\w])(?i:a|con|para|de\s+parte\s+de)\s+$")
# Presentación del asesor: «le habla Sebastián de ConectaYa», «soy Laura del Banco». Solo
# se toman nombres y apellidos conocidos: lo que sigue suele ser la empresa.
_INTRO_CTX = re.compile(r"(?<![\w])(?i:(?:le|te|les)\s+habla|soy)\s+$")
_VOCATIVE_BEFORE = re.compile(r"\w[ \t]*,[ \t]*$")
_VOCATIVE_AFTER = re.compile(r"[ \t]*[,.;!?]")
_SENTENCE_END = frozenset('.!?¡¿\n:;"“(-•*')
_LISTED = _names.FIRST_NAMES | _names.SURNAMES
_STRONG_FIRST = _names.FIRST_NAMES - _names.AMBIGUOUS - _names.STOPWORDS
_MAX_NAME_WORDS = 5


class _Word(NamedTuple):
    start: int
    end: int
    norm: str


def _is_sentence_start(text: str, pos: int) -> bool:
    i = pos - 1
    while i >= 0 and text[i] in " \t\u00a0":
        i -= 1
    return i < 0 or text[i] in _SENTENCE_END


def _word_key(token: str) -> str:
    """Clave de búsqueda en listas. Un compuesto («Ana-María») cuenta como su primera parte
    si todas sus partes están en las listas."""
    norm = _names.normalize(token)
    parts = re.split(r"[-'’]", norm)
    if len(parts) > 1 and all(part in _LISTED for part in parts):
        return parts[0]
    return norm


def _evaluate_run(text: str, run_start: int, run_end: int) -> Entity | None:
    words = [
        _Word(run_start + w.start(), run_start + w.end(), _word_key(w.group()))
        for w in _WORD_RE.finditer(text[run_start:run_end])
    ]
    before = _line_before(text, run_start, 40)
    if _INSTITUTION_BEFORE.search(before):
        return None
    leading = [
        w.norm
        for w in words[: next((i for i, w in enumerate(words) if w.norm in _LISTED), len(words))]
    ]
    if any(n in _INSTITUTION or n in _SAINT for n in leading):
        return None
    strict = bool(_STRICT_CTX.search(before))
    trigger = strict or bool(_WEAK_CTX.search(before))
    sentence_start = _is_sentence_start(text, run_start)
    titled = bool(_TITLE_BEFORE.search(before))
    if not trigger and words and words[0].norm in _STRONG_FIRST and _PREP_CTX.search(before):
        trigger = True
    # Tras «con», «a», «para»: un nombre de pila aunque sea ambiguo, si lo sigue otra palabra
    # con mayúscula («¿Hablo con Luz Dary?»).
    if (
        not trigger
        and len(words) >= 2
        and words[0].norm in _names.FIRST_NAMES
        and _PREP_CTX.search(before)
    ):
        trigger = True
    if not trigger and words and words[0].norm in _names.FIRST_NAMES and _INTRO_CTX.search(before):
        n = 1
        while n < len(words) and words[n].norm in _LISTED:
            n += 1
        words = words[:n]
        trigger = True
    # Vocativo entre comas: «Entiendo su preocupación, Jorge, ya lo reviso».
    if (
        not trigger
        and len(words) == 1
        and words[0].norm in _STRONG_FIRST
        and _VOCATIVE_BEFORE.search(before)
        and _VOCATIVE_AFTER.match(text, run_end)
    ):
        trigger = True

    while words and words[0].norm in _names.TITLES:
        words.pop(0)
        trigger = True
        titled = True
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

    # Sin contexto, un nombre de pila conocido (no ambiguo) al inicio arrastra hasta dos
    # apellidos desconocidos: «Kevin Arley Mosquera», «Edwin Ararat».
    head_first = bool(words) and words[0].norm in _STRONG_FIRST
    while words and words[-1].norm not in _LISTED:
        prev = words[-2].norm if len(words) > 1 else None
        unknown_tail = sum(1 for w in words[1:] if w.norm not in _LISTED)
        keep_tail = head_first and len(words) > 1 and unknown_tail <= 2
        if words[-1].norm in _names.STOPWORDS or (
            not trigger and prev not in _LISTED and not keep_tail
        ):
            words.pop()
        else:
            break

    words = words[:_MAX_NAME_WORDS]
    if not words:
        return None
    if " ".join(w.norm for w in words) in _NON_PERSON:
        return None

    listed = [w for w in words if w.norm in _LISTED]
    firsts = [w for w in words if w.norm in _names.FIRST_NAMES]
    strong = [w for w in listed if w.norm not in _names.AMBIGUOUS]

    if trigger:
        accepted = len(words) >= 2 or bool(listed) or strict or titled
        score = 0.85 if listed else 0.7
    else:
        accepted = (
            bool(firsts)
            and bool(strong)
            and (len(listed) >= 2 or (len(words) >= 2 and words[0].norm in _STRONG_FIRST))
        )
        score = 0.8 if len(strong) >= 2 else 0.7
    if not accepted:
        return None
    return _entity(PIIType.NOMBRE, text, words[0].start, words[-1].end, score, "nombre")


# --------------------------------------------------------------------------- nombres: formatos

# «Apellido Apellido, Nombre Nombre» (listados, actas, planillas): dos entidades.
_SURNAME_FIRST_RE = re.compile(
    rf"(?<![\w])(?P<sur>{_NAME_WORD}(?:[ \t]+{_NAME_WORD})?)[ \t]*,[ \t]*"
    rf"(?P<first>{_NAME_WORD}(?:[ \t]+{_NAME_WORD}){{0,2}})"
)


def _surname_first(text: str) -> list[Entity]:
    found = []
    for m in _SURNAME_FIRST_RE.finditer(text):
        sur = [_names.normalize(w) for w in m["sur"].split()]
        if not any(s in _names.SURNAMES for s in sur) or any(
            s in _names.STOPWORDS or s in _names.FIRST_NAMES for s in sur
        ):
            continue
        firsts = list(_WORD_RE.finditer(m["first"]))
        n = 0
        while n < len(firsts) and _names.normalize(firsts[n].group()) in _names.FIRST_NAMES:
            n += 1
        if n == 0 or _names.normalize(firsts[0].group()) in _names.AMBIGUOUS:
            continue
        base = m.start("first")
        found.append(
            _entity(PIIType.NOMBRE, text, m.start("sur"), m.end("sur"), 0.82, "apellido_nombre")
        )
        found.append(
            _entity(
                PIIType.NOMBRE,
                text,
                base + firsts[0].start(),
                base + firsts[n - 1].end(),
                0.82,
                "apellido_nombre",
            )
        )
    return found


# Nombres en minúscula (chats, formularios informales). Muy conservador: el primer nombre debe
# estar en la lista, no ser una palabra común, y hace falta contexto o dos nombres listados.
_LOWER_WORD_RE = re.compile(r"(?<![\w])[a-záéíóúüñ]+(?![\w])")
_LOWER_CTX = re.compile(
    r"(?i:me\s+llamo|mi\s+nombre\s+es|nombres?\s*:|soy|habla|le\s+habla|gracias|hola"
    r"|se[ñn]or(?:a)?|sr\.?|sra\.?|don|do[ñn]a|estimad[oa]|querid[oa])\s*[:,]?\s*$"
)
_LOWER_UNSAFE = _names.AMBIGUOUS | frozenset(
    [
        "tomas",
        "salvador",
        "rosario",
        "rocio",
        "armando",
        "marco",
        "marcos",
        "francia",
        "margarita",
        "lucero",
        "piedad",
        "estela",
        "clemente",
        "florencia",
        "leon",
        "angel",
        "pastor",
        "nieves",
        "milagros",
        "remedios",
        "socorro",
        "reyes",
        "ramos",
        "gracia",
        "santiago",
        "victoria",
    ]
)


def _lowercase_names(text: str) -> list[Entity]:
    found = []
    words = list(_LOWER_WORD_RE.finditer(text))
    i = 0
    while i < len(words):
        head = words[i]
        norm = _names.normalize(head.group())
        if norm not in _names.FIRST_NAMES or norm in _LOWER_UNSAFE or norm in _names.STOPWORDS:
            i += 1
            continue
        j = i
        while (
            j + 1 < len(words)
            and j - i < 3
            and text[words[j].end() : words[j + 1].start()] == " "
            and _names.normalize(words[j + 1].group()) in _LISTED
            and _names.normalize(words[j + 1].group()) not in _names.STOPWORDS
        ):
            j += 1
        context = bool(_LOWER_CTX.search(_line_before(text, head.start(), 40)))
        strong = [
            w
            for w in words[i : j + 1]
            if _names.normalize(w.group()) in _LISTED
            and _names.normalize(w.group()) not in _LOWER_UNSAFE
        ]
        if context or (j > i and len(strong) >= 2):
            score = 0.8 if context else 0.6
            found.append(
                _entity(PIIType.NOMBRE, text, head.start(), words[j].end(), score, "minuscula")
            )
        i = j + 1
    return found


def detect_nombre(text: str) -> list[Entity]:
    """Nombres propios: listas de nombres/apellidos, contexto («señor», «me llamo», «a»...),
    formato «Apellido, Nombre» y nombres en minúscula con contexto."""
    found = []
    for m in _RUN_RE.finditer(text):
        entity = _evaluate_run(text, m.start(), m.end())
        if entity is not None:
            found.append(entity)
    found += _surname_first(text)
    found += _lowercase_names(text)
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
    PIIType.TARJETA_CREDITO: (detect_tarjeta,),
    PIIType.DIRECCION_IP: (detect_ip,),
    PIIType.FECHA_NACIMIENTO: (detect_fecha_nacimiento,),
    PIIType.NOMBRE: (detect_nombre,),
}

_PRIORITY_INDEX = {t: i for i, t in enumerate(PRIORITY)}


def resolve_overlaps(entities: Iterable[Entity]) -> list[Entity]:
    """Conserva, entre detecciones solapadas, la de mayor puntaje (luego prioridad y longitud).

    Las entidades elegidas se guardan ordenadas por inicio; como no se solapan entre sí, basta
    comparar con las vecinas (búsqueda binaria): O(n log n) en lugar de O(n²).
    """
    ordered = sorted(
        entities,
        key=lambda e: (-e.score, _PRIORITY_INDEX[e.type], -(e.end - e.start), e.start),
    )
    starts: list[int] = []
    chosen: list[Entity] = []
    for ent in ordered:
        i = bisect.bisect_right(starts, ent.start)
        if i > 0 and chosen[i - 1].end > ent.start:
            continue
        if i < len(chosen) and chosen[i].start < ent.end:
            continue
        starts.insert(i, ent.start)
        chosen.insert(i, ent)
    return chosen


def _nfc_with_offsets(text: str) -> tuple[str, list[int] | None, list[int] | None]:
    """Normaliza a NFC y devuelve, por cada carácter normalizado, su inicio y fin originales.

    Se normaliza por segmentos (un carácter base + sus marcas combinantes), de modo que cada
    carácter normalizado proviene de un segmento conocido del texto original. Si el texto ya
    está en NFC no se construye ningún mapa.
    """
    if unicodedata.is_normalized("NFC", text):
        return text, None, None
    pieces: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    seg = 0
    for i in range(1, len(text) + 1):
        if i == len(text) or unicodedata.combining(text[i]) == 0:
            norm = unicodedata.normalize("NFC", text[seg:i])
            pieces.append(norm)
            starts.extend([seg] * len(norm))
            ends.extend([i] * len(norm))
            seg = i
    return "".join(pieces), starts, ends


def detect(
    texto: str,
    *,
    tipos: Iterable[PIIType | str] | PIIType | str | None = None,
    min_score: float = 0.0,
    contexto: str | None = None,
) -> list[Entity]:
    """Detecta datos personales en ``texto``.

    Args:
        texto: texto en español.
        tipos: restringe la búsqueda a estos tipos (``PIIType`` o cadenas como ``"NIT"``).
        min_score: descarta detecciones con confianza menor a este umbral (0 a 1).
        contexto: texto anterior (por ejemplo, los turnos previos de una conversación). Si
            pide un documento («¿me confirma su número de cédula?»), un número con forma de
            documento dictado solo en ``texto`` («12.635.880») se marca como ``CEDULA``.
            El contexto no se analiza ni se devuelve: solo da la pista.

    Returns:
        Lista de :class:`Entity` ordenada por posición y sin solapamientos. Los índices se
        refieren a ``texto`` tal como se recibió, aunque venga con tildes descompuestas (NFD):
        la normalización a NFC es interna.
    """
    if not isinstance(texto, str):
        raise TypeError(f"texto debe ser str, no {type(texto).__name__}")
    if not 0.0 <= min_score <= 1.0:
        raise ValueError("min_score debe estar entre 0 y 1")
    norm, starts, ends = _nfc_with_offsets(texto)
    found: list[Entity] = []
    for tipo in coerce_types(tipos):
        for detector in DETECTORS[tipo]:
            found.extend(detector(norm))
    if contexto and PIIType.CEDULA in coerce_types(tipos):
        found.extend(detect_cedula_dialogo(norm, contexto))
    result = resolve_overlaps(e for e in found if e.score >= min_score)
    if starts is None or ends is None:
        return result
    return [
        Entity(
            e.type,
            starts[e.start],
            ends[e.end - 1],
            texto[starts[e.start] : ends[e.end - 1]],
            e.score,
            e.detector,
        )
        for e in result
    ]
