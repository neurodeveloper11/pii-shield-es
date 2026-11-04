import pytest

from conftest import found
from datashield_es import PIIType
from datashield_es.validators import iban_check_digits


class TestTelefono:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Llámame al 3001234567 hoy", "3001234567"),
            ("Cel 300 123 4567", "300 123 4567"),
            ("WhatsApp +57 311 555 0199", "+57 311 555 0199"),
            ("Mi número (+57) 320-555-0123", "(+57) 320-555-0123"),
            ("celular 573105550123", "573105550123"),
            ("Su celular es 310.555.0123 según", "310.555.0123"),
            ("al 350 555 01 99 por favor", "350 555 01 99"),
            ("Contactar +573155550177 mañana", "+573155550177"),
            ("Oficina: (601) 555 0123 ext. 4", "(601) 555 0123"),
            ("PBX 601 5550123", "601 5550123"),
            ("Fijo (2) 555 0123 Cali", "(2) 555 0123"),
            ("(604) 555-0142", "(604) 555-0142"),
            ("Tel. 555 0123", "555 0123"),
            ("Teléfono: 5550123.", "5550123"),
            ("tel 555-0123", "555-0123"),
            ("Mi teléfono es 5550123", "5550123"),
            ("+57 1 555 0123", "+57 1 555 0123"),
            ("+57 601 5550123", "+57 601 5550123"),
            ("00573105550123", "00573105550123"),
        ],
    )
    def test_detecta(self, text, expected):
        assert found(text, PIIType.TELEFONO) == [expected]

    def test_dos_numeros(self):
        assert found("3205550188 o 3115550102", PIIType.TELEFONO) == ["3205550188", "3115550102"]

    @pytest.mark.parametrize(
        "text",
        [
            "Pedido 3001234567890 enviado",  # más de 10 dígitos pegados
            "Total $3.001.234",
            "Código 123456",
            "Llame al 123",
            "Año 2024 y 2025",
            "Radicado 2024-0034567",
            "Hotel 5550123",  # «tel» dentro de otra palabra
            "Ver páginas 305-4567",  # 7 dígitos sin contexto telefónico
            "Referencia 4001234567",  # no empieza por 3x ni 60x
            "Tel 123",
        ],
    )
    def test_no_detecta(self, text):
        assert found(text, PIIType.TELEFONO) == []

    def test_prefijo_sin_mas_se_conserva_completo(self):
        (ent,) = [e for e in __import__("datashield_es").detect("+57 3001234567")]
        assert ent.text == "+57 3001234567"


class TestCorreo:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Escríbeme a juan.perez@example.com y listo", "juan.perez@example.com"),
            ("Correo: maria_g88@example.org, gracias", "maria_g88@example.org"),
            ("Use contacto@example.com.co.", "contacto@example.com.co"),
            ("(jorge+facturas@example.net)", "jorge+facturas@example.net"),
            ("soporte@sub.example.com.", "soporte@sub.example.com"),
            ("a.rios_77@example.org", "a.rios_77@example.org"),
        ],
    )
    def test_detecta(self, text, expected):
        assert found(text, PIIType.CORREO) == [expected]

    @pytest.mark.parametrize(
        "text",
        ["Sígueme en @usuario", "El símbolo @ se usa", "a@b", "correo@", "usuario@localhost"],
    )
    def test_no_detecta(self, text):
        assert found(text, PIIType.CORREO) == []


class TestDireccion:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Vivo en la Calle 45 # 12-34 de Bogotá", "Calle 45 # 12-34"),
            ("Carrera 15 No. 93-60, Apto 502", "Carrera 15 No. 93-60, Apto 502"),
            ("Cra 7 # 71-21 Torre B antes", "Cra 7 # 71-21 Torre B"),
            ("Diagonal 40A Sur # 15-22 por", "Diagonal 40A Sur # 15-22"),
            ("Transversal 25 No 10-05 Interior 3", "Transversal 25 No 10-05 Interior 3"),
            ("Av. Calle 26 # 59-51", "Av. Calle 26 # 59-51"),
            ("Cl 80 # 11-42 Oficina 301", "Cl 80 # 11-42 Oficina 301"),
            ("Carrera 13 # 85-32, Barrio Chicó Norte", "Carrera 13 # 85-32, Barrio Chicó Norte"),
            ("en Cll 100 19-61 frente", "Cll 100 19-61"),
            ("Calle 72 Bis # 10-34", "Calle 72 Bis # 10-34"),
            ("Kr 15A # 100 - 20", "Kr 15A # 100 - 20"),
            ("Calle 9 # 5-17 Casa 2 y", "Calle 9 # 5-17 Casa 2"),
            ("CALLE 10 # 5-20", "CALLE 10 # 5-20"),
        ],
    )
    def test_detecta(self, text, expected):
        assert found(text, PIIType.DIRECCION) == [expected]

    @pytest.mark.parametrize(
        "text",
        [
            "La Calle 100 es muy transitada",
            "En la Carrera 7 con calle 72 hay trancón",
            "Está en la avenida principal",
            "Calle 13",
            "Carrera 7 2024-2025",  # cuatro dígitos: no es numeración vial
            "Calle 10 de mayo",
        ],
    )
    def test_no_detecta(self, text):
        assert found(text, PIIType.DIRECCION) == []

    def test_unidad_con_letra_suelta_no_arrastra_palabras(self):
        assert found("Calle 9 # 5-17, casa de Juan", PIIType.DIRECCION) == ["Calle 9 # 5-17"]


class TestPlaca:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("El vehículo de placa ABC123 fue", "ABC123"),
            ("Moto XYZ12D estacionada", "XYZ12D"),
            ("Placa: QWE-456 registrada", "QWE-456"),
            ("La placa abc 123 aparece", "abc 123"),
            ("Camioneta JKL789 de servicio", "JKL789"),
            ("Salió el RTY987 por la puerta", "RTY987"),  # sin contexto, compacta
            ("Motocicleta de placa FGH45K con SOAT", "FGH45K"),
        ],
    )
    def test_detecta(self, text, expected):
        assert found(text, PIIType.PLACA) == [expected]

    @pytest.mark.parametrize(
        "text",
        [
            "Modelo USB 300 de alta velocidad",
            "Norma ISO 900 vigente",
            "Código REF123 agotado",
            "El archivo PDF 123 pesa",
            "Habitación ABC 123 reservada",  # con espacio y sin contexto
            "Matrícula 123456",
            "placa metálica de 3 mm",
        ],
    )
    def test_no_detecta(self, text):
        assert found(text, PIIType.PLACA) == []

    def test_confianza_menor_sin_contexto(self):
        from datashield_es import detect

        con = detect("placa ABC123")[0].score
        sin = detect("salió ABC123")[0].score
        assert con > sin


class TestCuenta:
    def test_cuentas_con_contexto(self):
        assert found(
            "Consigne a la cuenta de ahorros 123-456789-01 hoy", PIIType.CUENTA_BANCARIA
        ) == ["123-456789-01"]
        assert found("Cta corriente No. 0123456789", PIIType.CUENTA_BANCARIA) == ["0123456789"]
        assert found("Número de cuenta: 4567 8901 2345", PIIType.CUENTA_BANCARIA) == [
            "4567 8901 2345"
        ]
        assert found("Mi cuenta es 987654321098.", PIIType.CUENTA_BANCARIA) == ["987654321098"]

    def test_iban_valido(self):
        bban = "12345678901234567890"
        iban = f"ES{iban_check_digits('ES', bban)}{bban}"
        spaced = " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))
        assert found(f"IBAN {spaced} gracias", PIIType.CUENTA_BANCARIA) == [spaced]
        assert found(f"IBAN {iban}.", PIIType.CUENTA_BANCARIA) == [iban]

    def test_iban_con_texto_pegado_se_recorta(self):
        bban = "12345678901234567890"
        iban = f"ES{iban_check_digits('ES', bban)}{bban}"
        spaced = " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))
        assert found(f"IBAN {spaced} AB", PIIType.CUENTA_BANCARIA) == [spaced]

    def test_iban_checksum_invalido_se_descarta(self):
        assert found("IBAN ES00 1234 5678 9012 3456 7890", PIIType.CUENTA_BANCARIA) == []

    def test_clabe(self):
        from datashield_es.validators import clabe_check_digit

        first17 = "01218000123456789"
        clabe = first17 + str(clabe_check_digit(first17))
        assert found(f"CLABE {clabe}", PIIType.CUENTA_BANCARIA) == [clabe]
        bad = first17 + str((clabe_check_digit(first17) + 1) % 10)
        assert found(f"CLABE {bad}", PIIType.CUENTA_BANCARIA) == []

    @pytest.mark.parametrize(
        "text",
        [
            "La cuenta de cobro fue enviada",
            "Tenga en cuenta 12 de los 15 puntos",
            "cuenta 123",
            "Código 987654321098 sin contexto",
        ],
    )
    def test_no_detecta(self, text):
        assert found(text, PIIType.CUENTA_BANCARIA) == []
