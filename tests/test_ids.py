import pytest

from conftest import found, nit
from datashield_es import PIIType, detect


class TestCedula:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Mi cédula es 1.234.567.890.", "1.234.567.890"),
            ("C.C. 52123456", "52123456"),
            ("cc: 79.456.123", "79.456.123"),
            ("CC No. 1020304050", "1020304050"),
            ("cedula de ciudadania numero 80123987", "80123987"),
            ("Cédula de Ciudadanía N° 43.111.222 expedida", "43.111.222"),
            ("documento de identidad 1013222111", "1013222111"),
            ("Tarjeta de identidad 1.000.123.456", "1.000.123.456"),
            ("identificación 94.321.654", "94.321.654"),
            ("NUIP 1002003004", "1002003004"),
            ("T.I. 1099887766", "1099887766"),
        ],
    )
    def test_con_contexto(self, text, expected):
        assert found(text, PIIType.CEDULA) == [expected]

    @pytest.mark.parametrize(
        "text",
        [
            "Pagó $1.234.567 en la cuota.",  # monto con formato de cédula
            "Total 1.234.567.890 pesos",
            "El número 1020304050 aparece sin contexto.",
            "Cédula 12345",  # demasiado corto
            "cédula 123456789012",  # demasiado largo
            "cédula de extranjería 1234567",  # es otro tipo
        ],
    )
    def test_sin_deteccion(self, text):
        assert found(text, PIIType.CEDULA) == []

    def test_cc_en_campo_copia_no_es_cedula(self):
        assert found("CC: juan@example.com", PIIType.CEDULA) == []


class TestCedulaExtranjeria:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("cédula de extranjería 456789", "456789"),
            ("Cédula de extranjería No. 987654", "987654"),
            ("C.E. 1234567", "1234567"),
            ("CE 345.678", "345.678"),
            ("CE: 7654321", "7654321"),
        ],
    )
    def test_detecta(self, text, expected):
        assert found(text, PIIType.CEDULA_EXTRANJERIA) == [expected]
        assert found(text, PIIType.CEDULA) == []

    def test_ce_minuscula_no_es_palabra_clave(self):
        assert found("el ce 456789 es otra cosa", PIIType.CEDULA_EXTRANJERIA) == []

    def test_demasiado_corto(self):
        assert found("CE 12345", PIIType.CEDULA_EXTRANJERIA) == []


class TestNit:
    def test_con_dv_valido_sin_contexto(self):
        value = nit("900123456", dotted=True)
        assert found(f"Empresa {value} Bogotá", PIIType.NIT) == [value]

    def test_formatos(self):
        for value in (nit("900123456"), nit("811000222", dotted=True), nit("79123456")):
            assert found(f"NIT {value}", PIIType.NIT) == [value]
            assert found(f"nit: {value}.", PIIType.NIT) == [value]

    def test_dv_con_espacios(self):
        base, dv = "900123456", nit("900123456").split("-")[1]
        assert found(f"NIT {base} - {dv}", PIIType.NIT) == [f"{base} - {dv}"]

    def test_dv_invalido_sin_contexto_se_descarta(self):
        base = "900123456"
        wrong = (int(nit(base).split("-")[1]) + 3) % 10
        assert found(f"Referencia {base}-{wrong}", PIIType.NIT) == []

    def test_dv_invalido_con_contexto_baja_confianza(self):
        base = "900123456"
        wrong = (int(nit(base).split("-")[1]) + 3) % 10
        ents = [e for e in detect(f"NIT {base}-{wrong}") if e.type is PIIType.NIT]
        assert len(ents) == 1 and ents[0].score < 0.6

    def test_sin_dv_exige_palabra_nit(self):
        assert found("NIT 901234567", PIIType.NIT) == ["901234567"]
        assert found("N.I.T. 901234567", PIIType.NIT) == ["901234567"]
        assert found("Código 901234567", PIIType.NIT) == []

    def test_score_con_contexto_mayor(self):
        value = nit("900123456")
        with_kw = detect(f"NIT {value}")[0].score
        without = detect(f"ref {value}")[0].score
        assert with_kw > without


class TestPasaporte:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Pasaporte AP123456 vence", "AP123456"),
            ("pasaporte No. AT987654", "AT987654"),
            ("Passport: XK3456789", "XK3456789"),
            ("pasaporte colombiano número AQ555123", "AQ555123"),
            ("Pasaporte: 12345678", "12345678"),
        ],
    )
    def test_detecta(self, text, expected):
        assert found(text, PIIType.PASAPORTE) == [expected]

    @pytest.mark.parametrize(
        "text",
        ["AP123456 sin contexto", "pasaporte vencido", "pasaporte ab12", "pasaporte sanitario"],
    )
    def test_no_detecta(self, text):
        assert found(text, PIIType.PASAPORTE) == []


def test_nit_con_base_demasiado_larga_se_ignora():
    assert found("NIT 123.456.789.012-3", PIIType.NIT) == []
