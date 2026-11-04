import pytest

from pii_shield_es.validators import (
    clabe_check_digit,
    iban_check_digits,
    is_valid_clabe,
    is_valid_iban,
    is_valid_nit,
    nit_check_digit,
)


def test_nit_dv_ancla_publica():
    # NIT de una entidad pública (DIAN), no de una persona: ancla del algoritmo.
    assert nit_check_digit("800197268") == 4
    assert nit_check_digit("800.197.268") == 4  # ignora separadores


@pytest.mark.parametrize("base", ["900123456", "811000222", "79123456", "1"])
def test_nit_dv_roundtrip(base):
    dv = nit_check_digit(base)
    assert 0 <= dv <= 9
    assert is_valid_nit(base, dv)
    assert is_valid_nit(base, str(dv))
    assert not is_valid_nit(base, (dv + 1) % 10)


@pytest.mark.parametrize("bad", ["", "abc", "1" * 16])
def test_nit_base_invalida(bad):
    with pytest.raises(ValueError):
        nit_check_digit(bad)
    assert is_valid_nit(bad, 0) is False


def test_iban_valido_e_invalido():
    assert is_valid_iban("GB82 WEST 1234 5698 7654 32")  # ejemplo de documentación pública
    assert is_valid_iban("gb82west12345698765432")
    assert not is_valid_iban("GB82 WEST 1234 5698 7654 33")  # control incorrecto
    assert not is_valid_iban("XX82 WEST 1234 5698 7654 32")  # país desconocido
    assert not is_valid_iban("GB82 WEST 1234 5698 7654")  # longitud incorrecta
    assert not is_valid_iban("no es un iban")


def test_iban_check_digits_roundtrip():
    check = iban_check_digits("ES", "12345678901234567890")
    assert is_valid_iban(f"ES{check}12345678901234567890")


def test_clabe():
    first17 = "01218000123456789"
    d = clabe_check_digit(first17)
    assert is_valid_clabe(first17 + str(d))
    assert not is_valid_clabe(first17 + str((d + 1) % 10))
    assert not is_valid_clabe("123")
    with pytest.raises(ValueError):
        clabe_check_digit("123")
