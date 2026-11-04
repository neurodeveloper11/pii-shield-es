"""Archivos completos: .txt, .csv, Word (.docx) y Excel (.xlsx), construidos a mano como los
guarda Microsoft Office (cadenas compartidas, revisiones, comentarios, vínculos)."""

from __future__ import annotations

import io
import zipfile

import pytest

from datashield_es import PseudonymTable
from datashield_es.files import (
    UnsupportedFileError,
    anonymize_bytes,
    anonymize_file,
    default_output_path,
    detect_bytes,
    header_type,
)
from datashield_es.types import PIIType

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _zip(parts: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, content in parts.items():
            z.writestr(name, content)
    return buffer.getvalue()


def _unzip(data: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n).decode("utf-8") for n in z.namelist()}


CORE = (
    '<cp:coreProperties xmlns:cp="x" xmlns:dc="y"><dc:creator>Fabio Torres</dc:creator>'
    "<cp:lastModifiedBy>Fabio Torres</cp:lastModifiedBy></cp:coreProperties>"
)


def _docx(body: str, **extra: str) -> bytes:
    parts = {
        "[Content_Types].xml": "<Types/>",
        "word/document.xml": f"<w:document {W}><w:body>{body}</w:body></w:document>",
        "docProps/core.xml": CORE,
        "docProps/app.xml": "<Properties><Company>Clínica Ejemplo</Company></Properties>",
    }
    parts.update(extra)
    return _zip(parts)


# --------------------------------------------------------------------------- Word


def test_word_nombre_partido_en_varios_fragmentos_conserva_formato():
    body = (
        '<w:p><w:r><w:t xml:space="preserve">Paciente: </w:t></w:r>'
        "<w:r><w:rPr><w:b/></w:rPr><w:t>Rosa Elena</w:t></w:r>"
        '<w:r><w:t xml:space="preserve"> Quintero, C.C. 41.888.222.</w:t></w:r></w:p>'
    )
    out, report = anonymize_bytes(_docx(body), "h.docx")
    xml = _unzip(out)["word/document.xml"]
    assert "Rosa" not in xml and "Quintero" not in xml and "41.888.222" not in xml
    assert '<w:b/></w:rPr><w:t xml:space="preserve">[NOMBRE]</w:t>' in xml  # hereda la negrita
    assert "[CEDULA]" in xml
    assert report.conteo == {"CEDULA": 1, "NOMBRE": 1}


def test_word_revisiones_comentarios_vinculos_y_metadatos():
    body = (
        '<w:p><w:ins w:id="1" w:author="Fabio Torres" w:date="2026-01-01T00:00:00Z">'
        "<w:r><w:t>Llamar a Marcela Pineda</w:t></w:r></w:ins>"
        '<w:del w:id="2" w:author="Fabio Torres"><w:r><w:delText>cédula 52.345.678'
        "</w:delText></w:r></w:del></w:p>"
        '<w:p><w:r><w:instrText xml:space="preserve"> HYPERLINK "mailto:ana@example.com" '
        "</w:instrText></w:r><w:r><w:t>escríbele</w:t></w:r></w:p>"
    )
    comments = (
        f'<w:comments {W}><w:comment w:id="0" w:author="Fabio Torres" w:initials="FT">'
        "<w:p><w:r><w:t>Su celular es 300 555 0175</w:t></w:r></w:p></w:comment></w:comments>"
    )
    rels = (
        '<Relationships><Relationship Id="rId9" Type="hyperlink" '
        'Target="mailto:ana@example.com" TargetMode="External"/></Relationships>'
    )
    data = _docx(body, **{"word/comments.xml": comments, "word/_rels/document.xml.rels": rels})
    out, report = anonymize_bytes(data, "c.docx")
    blob = "".join(_unzip(out).values())
    for leak in ("Marcela", "52.345.678", "ana@example.com", "300 555 0175", "Fabio", "Clínica"):
        assert leak not in blob, leak
    assert "autor" in report.metadatos_limpiados
    assert "autores de comentarios y cambios" in report.metadatos_limpiados
    assert "empresa / responsable" in report.metadatos_limpiados


def test_word_sin_metadatos_si_se_pide_y_texto_sin_datos_intacto():
    body = "<w:p><w:r><w:t>Versión 2.10.4, TA 140/90.</w:t></w:r></w:p>"
    data = _docx(body)
    out, report = anonymize_bytes(data, "x.docx", limpiar_metadatos=False)
    parts = _unzip(out)
    assert parts["word/document.xml"] == _unzip(data)["word/document.xml"]
    assert "Fabio Torres" in parts["docProps/core.xml"]
    assert report.total == 0 and report.metadatos_limpiados == []


def test_word_advierte_imagenes_y_objetos():
    data = _docx(
        "<w:p/>",
        **{"word/media/image1.png": "png", "word/embeddings/ole1.bin": "bin"},
    )
    _, report = anonymize_bytes(data, "x.docx")
    assert len(report.advertencias) == 2


def test_word_seudonimo_reversible_con_tabla():
    body = "<w:p><w:r><w:t>Hola, soy Juan Camilo Pérez, cédula 1.023.456.789.</w:t></w:r></w:p>"
    tabla = PseudonymTable()
    out, _ = anonymize_bytes(_docx(body), "x.docx", "seudonimo", tabla=tabla)
    xml = _unzip(out)["word/document.xml"]
    assert "[NOMBRE_1]" in xml and "[CEDULA_1]" in xml
    assert tabla.restore("[NOMBRE_1]") == "Juan Camilo Pérez"


# --------------------------------------------------------------------------- Excel


def _xlsx(sheet: str, sst: list[str], **extra: str) -> bytes:
    si = "".join(f"<si><t>{s}</t></si>" for s in sst)
    parts = {
        "[Content_Types].xml": "<Types/>",
        "xl/workbook.xml": (
            '<workbook xmlns:r="r"><sheets><sheet name="Clientes" sheetId="1" r:id="rId1"/>'
            "</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        ),
        "xl/sharedStrings.xml": f'<sst count="{len(sst)}">{si}</sst>',
        "xl/worksheets/sheet1.xml": f"<worksheet><sheetData>{sheet}</sheetData></worksheet>",
        "docProps/core.xml": CORE,
    }
    parts.update(extra)
    return _zip(parts)


SST = ["Nombre", "Cédula", "Nota", "Gladys", "Llamar a Marcela Pineda", "ID", "Gladys"]
SHEET = (
    '<row r="1"><c r="A1" t="s"><v>5</v></c><c r="B1" t="s"><v>0</v></c>'
    '<c r="C1" t="s"><v>1</v></c><c r="D1" t="s"><v>2</v></c></row>'
    '<row r="2"><c r="A2"><v>1</v></c><c r="B2" t="s"><v>3</v></c><c r="C2"><v>1032456789</v></c>'
    '<c r="D2" t="s"><v>4</v></c></row>'
    '<row r="3"><c r="A3"><v>2</v></c><c r="B3" s="2" t="s"><v>6</v></c>'
    '<c r="C3"><f>C2+1</f><v>1032456790</v></c><c r="D3"/></row>'
)


def test_excel_usa_encabezado_y_vacia_cadenas_compartidas_huerfanas():
    out, report = anonymize_bytes(_xlsx(SHEET, SST), "c.xlsx")
    parts = _unzip(out)
    sheet, sst = parts["xl/worksheets/sheet1.xml"], parts["xl/sharedStrings.xml"]
    blob = sheet + sst
    for leak in ("Gladys", "1032456789", "Marcela"):
        assert leak not in blob, leak
    assert '<c r="B2" t="inlineStr"><is><t xml:space="preserve">[NOMBRE]</t></is></c>' in sheet
    assert '<c r="B3" s="2" t="inlineStr">' in sheet  # conserva el estilo
    assert "<f>C2+1</f>" in sheet  # las fórmulas no se tocan
    assert '<c r="A2"><v>1</v></c>' in sheet  # la columna «ID» (consecutivo) no se toca
    assert "<si><t>Nombre</t></si>" in sst  # los encabezados se conservan
    assert report.conteo == {"CEDULA": 1, "NOMBRE": 3}
    assert {h["ubicacion"] for h in report.hallazgos} >= {"Clientes!B2", "Clientes!C2"}


def test_excel_cadena_compartida_usada_tambien_en_encabezado_no_se_vacia():
    sst = ["Nombre", "Nombre"]
    sheet = (
        '<row r="1"><c r="A1" t="s"><v>0</v></c></row><row r="2"><c r="A2" t="s"><v>1</v></c></row>'
    )
    out, report = anonymize_bytes(_xlsx(sheet, sst), "c.xlsx")
    assert report.total == 0
    assert _unzip(out)["xl/sharedStrings.xml"].count("<si><t>Nombre</t></si>") == 2


def test_excel_comentarios_autores_y_advertencias():
    comments = (
        "<comments><authors><author>Fabio Torres</author></authors><commentList>"
        '<comment ref="A1" authorId="0"><text><r><t>Llamar al 320 555 0111</t></r></text>'
        "</comment></commentList></comments>"
    )
    threaded = (
        '<ThreadedComments><threadedComment ref="A1"><text>Habló Ana María López</text>'
        "</threadedComment></ThreadedComments>"
    )
    person = '<personList><person displayName="Fabio Torres" userId="fabio@x.com"/></personList>'
    data = _xlsx(
        SHEET,
        SST,
        **{
            "xl/comments1.xml": comments,
            "xl/threadedComments/threadedComment1.xml": threaded,
            "xl/persons/person.xml": person,
            "xl/pivotCache/pivotCacheRecords1.xml": "<x/>",
            "xl/media/image1.png": "png",
        },
    )
    out, report = anonymize_bytes(data, "c.xlsx")
    blob = "".join(_unzip(out).values())
    for leak in ("Fabio", "320 555 0111", "Ana María López", "fabio@x.com"):
        assert leak not in blob, leak
    assert len(report.advertencias) == 2


def test_excel_sin_cadenas_compartidas_ni_nombres_de_hoja():
    sheet = (
        '<row r="1"><c r="A1" t="inlineStr"><is><t>Celular</t></is></c></row>'
        '<row r="2"><c r="A2"><v>3005550190</v></c><c r="B2" t="b"><v>1</v></c></row>'
    )
    data = _zip(
        {
            "xl/workbook.xml": "<workbook/>",
            "xl/worksheets/sheet1.xml": f"<worksheet><sheetData>{sheet}</sheetData></worksheet>",
        }
    )
    out, report = anonymize_bytes(data, "c.xlsx", "mascara")
    assert "*******190" in _unzip(out)["xl/worksheets/sheet1.xml"]
    assert report.hallazgos[0]["ubicacion"] == "sheet1!A2"


# --------------------------------------------------------------------------- texto y CSV


def test_csv_usa_encabezado_como_contexto_y_respeta_cp1252():
    data = "Nombre;Cédula;Nota\nGladys;1032456789;Pagó $120.000\n".encode("cp1252")
    out, report = anonymize_bytes(data, "c.csv")
    text = out.decode("cp1252")
    assert text.splitlines() == ["Nombre;Cédula;Nota", "[NOMBRE];[CEDULA];Pagó $120.000"]
    assert report.conteo == {"CEDULA": 1, "NOMBRE": 1}


def test_tsv_y_txt_con_bom():
    out, _ = anonymize_bytes(b"Correo\tNota\nana@example.com\tok\n", "c.tsv")
    assert out.decode().splitlines()[1] == "[CORREO]\tok"
    data = "﻿Hola, mi cédula es 1.023.456.789\nsin datos".encode()
    out, report = anonymize_bytes(data, "n.txt")
    assert out.startswith(b"\xef\xbb\xbf")
    assert out.decode("utf-8-sig") == "Hola, mi cédula es [CEDULA]\nsin datos"
    assert report.hallazgos == [{"tipo": "CEDULA", "ubicacion": "línea 1", "score": 0.92}]


def test_detect_bytes_no_modifica_y_reporta_ubicaciones():
    report = detect_bytes(_xlsx(SHEET, SST), "c.xlsx", tipos=["CEDULA"])
    assert report.conteo == {"CEDULA": 1}
    assert report.to_dict()["total"] == 1


# --------------------------------------------------------------------------- API de archivo


def test_anonymize_file_nombre_por_defecto(tmp_path):
    source = tmp_path / "notas.txt"
    source.write_text("Tel. 604 555 0123", encoding="utf-8")
    target, report = anonymize_file(source)
    assert target == default_output_path(source) == tmp_path / "notas_anonimizado.txt"
    assert target.read_text(encoding="utf-8") == "Tel. [TELEFONO]"
    assert report.total == 1


def test_formato_no_soportado_y_zip_invalido():
    with pytest.raises(UnsupportedFileError):
        anonymize_bytes(b"x", "foto.png")
    with pytest.raises(UnsupportedFileError):
        anonymize_bytes(b"no es zip", "x.docx")
    with pytest.raises(UnsupportedFileError):
        anonymize_bytes(_zip({"otra/cosa.xml": "<x/>"}), "x.xlsx")


@pytest.mark.parametrize(
    ("header", "tipo"),
    [
        ("Cédula", PIIType.CEDULA),
        ("No. Documento", PIIType.CEDULA),
        ("E-mail", PIIType.CORREO),
        ("Celular", PIIType.TELEFONO),
        ("Fecha de nacimiento", PIIType.FECHA_NACIMIENTO),
        ("Nombres y apellidos", PIIType.NOMBRE),
        ("ID", None),
        ("Total", None),
        (None, None),
    ],
)
def test_encabezados_tipados(header, tipo):
    assert header_type(header) is tipo


def test_columna_tipada_exige_forma_plausible():
    data = "Cédula,Celular,Correo,Nombre\nN/A,123,sin correo,Cliente 1\n".encode()
    out, report = anonymize_bytes(data, "c.csv")
    assert report.total == 0
    assert out.decode().splitlines()[1] == "N/A,123,sin correo,Cliente 1"


def test_excel_seudonimo_restaura_numeros_como_numeros():
    from datashield_es.files import restore_bytes

    tabla = PseudonymTable()
    out, _ = anonymize_bytes(_xlsx(SHEET, SST), "c.xlsx", "seudonimo", tabla=tabla)
    assert tabla.numeric_tokens == {"[CEDULA_1]"}
    copia = PseudonymTable.from_json(tabla.to_json())
    sheet = _unzip(restore_bytes(out, "c.xlsx", copia))["xl/worksheets/sheet1.xml"]
    assert '<c r="C2"><v>1032456789</v></c>' in sheet  # vuelve a ser número
    assert '<t xml:space="preserve">Gladys</t>' in sheet


def test_restaurar_texto_y_tabla_con_numericos_invalidos():
    from datashield_es.files import restore_bytes

    tabla = PseudonymTable()
    anon, _ = anonymize_bytes("Cédula 52.345.678".encode(), "n.txt", "seudonimo", tabla=tabla)
    assert restore_bytes(anon, "n.txt", tabla).decode() == "Cédula 52.345.678"
    with pytest.raises(ValueError, match="numericos"):
        PseudonymTable.from_json('{"version": 1, "mapping": {}, "numericos": ["[X_1]"]}')
