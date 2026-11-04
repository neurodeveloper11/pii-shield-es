"""Validadores: NIT (DIAN), IBAN (ISO 13616), CLABE (México), tarjetas (Luhn) e IP."""

from __future__ import annotations

import ipaddress
import re

# Pesos oficiales de la DIAN para el dígito de verificación (de derecha a izquierda).
_NIT_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)

# Longitud total del IBAN por país (subconjunto; países no listados se rechazan
# a propósito para evitar falsos positivos).
IBAN_LENGTHS: dict[str, int] = {
    "AD": 24, "AT": 20, "BE": 16, "BR": 29, "CH": 21, "CR": 22, "CY": 28, "CZ": 24,
    "DE": 22, "DK": 18, "DO": 28, "EE": 20, "ES": 24, "FI": 18, "FR": 27, "GB": 22,
    "GR": 27, "GT": 28, "HR": 21, "HU": 28, "IE": 22, "IT": 27, "LU": 20, "LV": 21,
    "MC": 27, "MT": 31, "NL": 18, "NO": 15, "PL": 28, "PT": 25, "SE": 24, "SI": 19,
    "SK": 24, "SV": 28, "TR": 26, "VG": 24,
}  # fmt: skip


def nit_check_digit(base: str) -> int:
    """Calcula el dígito de verificación (DV) de un NIT colombiano.

    ``base`` es el NIT sin DV; se ignoran puntos, espacios y guiones.
    """
    digits = [int(c) for c in base if c.isdigit()]
    if not 1 <= len(digits) <= len(_NIT_WEIGHTS):
        raise ValueError("La base del NIT debe tener entre 1 y 15 dígitos")
    total = sum(d * w for d, w in zip(reversed(digits), _NIT_WEIGHTS, strict=False))
    remainder = total % 11
    return remainder if remainder in (0, 1) else 11 - remainder


def is_valid_nit(base: str, dv: str | int) -> bool:
    """``True`` si ``dv`` es el dígito de verificación correcto para ``base``."""
    try:
        return nit_check_digit(base) == int(dv)
    except ValueError:
        return False


def _iban_numeric(iban: str) -> int:
    rearranged = iban[4:] + iban[:4]
    return int("".join(str(int(c, 36)) for c in rearranged))


def is_valid_iban(value: str) -> bool:
    """Valida un IBAN: país conocido, longitud correcta y módulo 97 == 1."""
    iban = re.sub(r"[\s-]", "", value).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", iban):
        return False
    expected = IBAN_LENGTHS.get(iban[:2])
    if expected is None or len(iban) != expected:
        return False
    return _iban_numeric(iban) % 97 == 1


def iban_check_digits(country: str, bban: str) -> str:
    """Calcula los dos dígitos de control de un IBAN (útil para datos sintéticos)."""
    country = country.upper()
    bban = re.sub(r"[\s-]", "", bban).upper()
    value = _iban_numeric(country + "00" + bban)
    return f"{98 - value % 97:02d}"


_CLABE_WEIGHTS = ((3, 7, 1) * 6)[:17]


def clabe_check_digit(first17: str) -> int:
    """Dígito de control de una CLABE interbancaria mexicana (17 dígitos)."""
    if not re.fullmatch(r"\d{17}", first17):
        raise ValueError("Se requieren 17 dígitos")
    total = sum((int(d) * w) % 10 for d, w in zip(first17, _CLABE_WEIGHTS, strict=True))
    return (10 - total % 10) % 10


def is_valid_clabe(value: str) -> bool:
    """Valida una CLABE de 18 dígitos."""
    digits = re.sub(r"[\s-]", "", value)
    if not re.fullmatch(r"\d{18}", digits):
        return False
    return clabe_check_digit(digits[:17]) == int(digits[17])


def luhn_ok(digits: str) -> bool:
    """Algoritmo de Luhn (ISO/IEC 7812) sobre una cadena de dígitos."""
    if not digits.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


# (prefijos, longitudes válidas) por marca. Solo marcas con rangos IIN públicos y estables.
_CARD_BRANDS: tuple[tuple[str, tuple[tuple[int, int], ...], frozenset[int]], ...] = (
    ("visa", ((4, 4),), frozenset({13, 16, 19})),
    ("mastercard", ((51, 55), (2221, 2720)), frozenset({16})),
    ("amex", ((34, 34), (37, 37)), frozenset({15})),
    ("diners", ((300, 305), (36, 36), (38, 39)), frozenset({14, 16})),
    ("discover", ((6011, 6011), (644, 649), (65, 65)), frozenset({16, 19})),
    ("jcb", ((3528, 3589),), frozenset({16, 17, 18, 19})),
    ("unionpay", ((62, 62),), frozenset({16, 17, 18, 19})),
)


def card_brand(number: str) -> str | None:
    """Marca de una tarjeta por su prefijo IIN y longitud, o ``None`` si no encaja."""
    digits = re.sub(r"[\s-]", "", number)
    if not digits.isdigit():
        return None
    for brand, ranges, lengths in _CARD_BRANDS:
        if len(digits) not in lengths:
            continue
        for low, high in ranges:
            width = len(str(low))
            if low <= int(digits[:width]) <= high:
                return brand
    return None


def is_valid_card(number: str) -> bool:
    """``True`` si el número tiene prefijo/longitud de una marca conocida y pasa Luhn."""
    digits = re.sub(r"[\s-]", "", number)
    return card_brand(digits) is not None and luhn_ok(digits)


def is_valid_ip(value: str) -> bool:
    """IPv4/IPv6 sintácticamente válida (sin ceros a la izquierda en IPv4)."""
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True
