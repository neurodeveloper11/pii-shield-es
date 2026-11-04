import io
import json
import sys

import pytest

from datashield_es import PseudonymTable, cli

TEXTO = "Cédula 1.234.567.890, correo a.b@example.com."


def run(args, capsys, stdin: str | None = None, monkeypatch=None):
    if stdin is not None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    code = cli.main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_texto_posicional(capsys):
    code, out, _ = run(["anonimizar", TEXTO], capsys)
    assert code == 0 and out == "Cédula [CEDULA], correo [CORREO].\n"


def test_alias_en_ingles_y_modo(capsys):
    code, out, _ = run(["anonymize", "-m", "mascara", TEXTO], capsys)
    assert code == 0 and "*.***.***.890" in out


def test_stdin(capsys, monkeypatch):
    class FakeStdin(io.StringIO):
        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stdin", FakeStdin(TEXTO))
    assert cli.main(["anonimizar"]) == 0
    assert capsys.readouterr().out == "Cédula [CEDULA], correo [CORREO].\n"


def test_sin_entrada_con_tty(capsys, monkeypatch):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Tty())
    code, _, err = run(["anonimizar"], capsys)
    assert code == 2 and "No hay entrada" in err


def test_archivo_txt_a_archivo(tmp_path, capsys):
    src, dst = tmp_path / "in.txt", tmp_path / "out.txt"
    src.write_text(TEXTO + "\nOtra línea sin datos.\n", encoding="utf-8")
    code, out, _ = run(["anonimizar", "-f", str(src), "-o", str(dst)], capsys)
    assert code == 0 and out == ""
    assert (
        dst.read_text(encoding="utf-8")
        == "Cédula [CEDULA], correo [CORREO].\nOtra línea sin datos.\n"
    )


def test_archivo_inexistente(capsys):
    code, _, err = run(["anonimizar", "-f", "/no/existe.txt"], capsys)
    assert code == 2 and "No se pudo leer" in err


def test_archivo_no_utf8(tmp_path, capsys):
    f = tmp_path / "latin.txt"
    f.write_bytes("cédula".encode("latin-1"))
    code, _, err = run(["anonimizar", "-f", str(f)], capsys)
    assert code == 2 and "UTF-8" in err


def test_salida_no_escribible(tmp_path, capsys):
    code, _, err = run(["anonimizar", TEXTO, "-o", str(tmp_path / "no" / "out.txt")], capsys)
    assert code == 2 and "No se pudo escribir" in err


CSV = 'id,nombre,nota\n1,Pedro Ramírez,"Cédula 79.123.456, tel 3101234567"\n2,Ana,sin datos\n'


def test_csv_todas_las_columnas(tmp_path, capsys):
    f = tmp_path / "d.csv"
    f.write_text(CSV, encoding="utf-8")
    code, out, _ = run(["anonimizar", "-f", str(f)], capsys)
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "id,nombre,nota"
    assert lines[1] == '1,[NOMBRE],"Cédula [CEDULA], tel [TELEFONO]"'
    assert lines[2] == "2,[NOMBRE],sin datos"  # el encabezado «nombre» da contexto


def test_csv_columnas_por_nombre_e_indice(tmp_path, capsys):
    f = tmp_path / "d.csv"
    f.write_text(CSV, encoding="utf-8")
    _, out, _ = run(["anonimizar", "-f", str(f), "--columnas", "nota"], capsys)
    assert "Pedro Ramírez" in out and "[CEDULA]" in out
    _, out, _ = run(["anonimizar", "-f", str(f), "--columnas", "1"], capsys)
    assert "[NOMBRE]" in out and "79.123.456" in out


def test_csv_columna_inexistente(tmp_path, capsys):
    f = tmp_path / "d.csv"
    f.write_text(CSV, encoding="utf-8")
    code, _, err = run(["anonimizar", "-f", str(f), "--columnas", "zzz"], capsys)
    assert code == 2 and "Columna no encontrada" in err


def test_csv_punto_y_coma_y_delimitador_explicito(tmp_path, capsys):
    f = tmp_path / "d.csv"
    f.write_text("a;b\nx;correo z@example.com\n", encoding="utf-8")
    _, out, _ = run(["anonimizar", "-f", str(f)], capsys)
    assert out.splitlines()[1] == "x;correo [CORREO]"
    _, out, _ = run(["anonimizar", "-f", str(f), "--delimitador", ";"], capsys)
    assert out.splitlines()[1] == "x;correo [CORREO]"
    code, _, err = run(["anonimizar", "-f", str(f), "--delimitador", ";;"], capsys)
    assert code == 2 and "un solo carácter" in err


def test_csv_sin_encabezado(tmp_path, capsys):
    f = tmp_path / "d.csv"
    f.write_text("a@example.com,x\nb@example.com,y\n", encoding="utf-8")
    _, out, _ = run(["anonimizar", "-f", str(f), "--sin-encabezado"], capsys)
    assert out.splitlines() == ["[CORREO],x", "[CORREO],y"]


def test_seudonimo_con_tabla_y_restaurar(tmp_path, capsys):
    table = tmp_path / "t.json"
    code, out, err = run(["anonimizar", "-m", "seudonimo", "--tabla", str(table), TEXTO], capsys)
    assert code == 0 and out == "Cédula [CEDULA_1], correo [CORREO_1].\n"
    assert "protégela" in err
    assert json.loads(table.read_text(encoding="utf-8"))["mapping"]["[CEDULA_1]"] == "1.234.567.890"
    code, out, _ = run(["restaurar", "--tabla", str(table), "Cédula [CEDULA_1]."], capsys)
    assert code == 0 and out == "Cédula 1.234.567.890.\n"
    # segunda ejecución: la tabla se amplía y respeta lo existente
    _, out, _ = run(
        [
            "anonimizar",
            "-m",
            "seudonimo",
            "--tabla",
            str(table),
            "cédula 9.999.999 y 1.234.567.890",
        ],
        capsys,
    )
    # el segundo valor no lleva palabra clave y no se detecta; el nuevo continúa la numeración
    assert out == "cédula [CEDULA_2] y 1.234.567.890\n"
    assert PseudonymTable.load(table).restore("[CEDULA_1] [CEDULA_2]") == "1.234.567.890 9.999.999"


def test_restaurar_desde_archivo(tmp_path, capsys):
    table = tmp_path / "t.json"
    run(["anonimizar", "-m", "seudonimo", "--tabla", str(table), TEXTO], capsys)
    f = tmp_path / "anon.txt"
    f.write_text("[CORREO_1]", encoding="utf-8")
    _, out, _ = run(["restore", "--tabla", str(table), "-f", str(f)], capsys)
    assert out == "a.b@example.com\n"


def test_restaurar_tabla_invalida(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    code, _, err = run(["restaurar", "--tabla", str(bad), "x"], capsys)
    assert code == 2 and "Tabla inválida" in err
    code, _, err = run(["restaurar", "--tabla", str(tmp_path / "nada.json"), "x"], capsys)
    assert code == 2


def test_tabla_solo_con_seudonimo(tmp_path, capsys):
    code, _, err = run(["anonimizar", "--tabla", str(tmp_path / "t.json"), TEXTO], capsys)
    assert code == 2 and "solo aplica" in err


def test_tabla_existente_corrupta(tmp_path, capsys):
    bad = tmp_path / "t.json"
    bad.write_text("no es json", encoding="utf-8")
    code, _, err = run(["anonimizar", "-m", "seudonimo", "--tabla", str(bad), TEXTO], capsys)
    assert code == 2 and "Tabla inválida" in err


def test_tipos_invalidos_y_validos(capsys):
    code, _, err = run(["anonimizar", "--tipos", "NOPE", TEXTO], capsys)
    assert code == 2 and "Tipo de PII desconocido" in err
    _, out, _ = run(["anonimizar", "--tipos", "CORREO", TEXTO], capsys)
    assert out == "Cédula 1.234.567.890, correo [CORREO].\n"


def test_detectar_texto_y_json(capsys):
    code, out, _ = run(["detectar", TEXTO], capsys)
    assert code == 0 and "CEDULA" in out and "Total: CEDULA=1, CORREO=1" in out
    _, out, _ = run(["detect", "--json", TEXTO], capsys)
    data = json.loads(out)
    assert [d["type"] for d in data] == ["CEDULA", "CORREO"]


def test_detectar_sin_hallazgos(capsys):
    _, out, _ = run(["detectar", "nada que ver"], capsys)
    assert "sin hallazgos" in out


def test_detectar_csv_con_fila_y_columna(tmp_path, capsys):
    f = tmp_path / "d.csv"
    f.write_text(CSV, encoding="utf-8")
    _, out, _ = run(["detectar", "-f", str(f), "--json"], capsys)
    data = json.loads(out)
    assert {(d["fila"], d["columna"]) for d in data} == {(1, 1), (1, 2), (2, 1)}


def test_version_y_ayuda(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0 and "datashield-es" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main([])


def test_csv_no_detectable_usa_dialecto_por_defecto(tmp_path, capsys):
    f = tmp_path / "raro.csv"
    f.write_text("una sola columna sin separadores a@example.com\n", encoding="utf-8")
    _, out, _ = run(["anonimizar", "-f", str(f), "--sin-encabezado"], capsys)
    assert out.strip() == "una sola columna sin separadores [CORREO]"


def test_columnas_sin_encabezado_por_indice(tmp_path, capsys):
    f = tmp_path / "d.csv"
    f.write_text("x,a@example.com\n", encoding="utf-8")
    _, out, _ = run(["anonimizar", "-f", str(f), "--sin-encabezado", "--columnas", "1"], capsys)
    assert out.strip() == "x,[CORREO]"


def test_seudonimo_sin_archivo_de_tabla(capsys):
    code, out, err = run(["anonimizar", "-m", "seudonimo", TEXTO], capsys)
    assert code == 0 and "[CEDULA_1]" in out and err == ""


def test_restaurar_por_stdin_y_sin_entrada(tmp_path, capsys, monkeypatch):
    table = tmp_path / "t.json"
    run(["anonimizar", "-m", "seudonimo", "--tabla", str(table), TEXTO], capsys)

    class Pipe(io.StringIO):
        def isatty(self):
            return False

    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Pipe("[CORREO_1]"))
    assert cli.main(["restaurar", "--tabla", str(table)]) == 0
    assert capsys.readouterr().out == "a.b@example.com\n"
    monkeypatch.setattr(sys, "stdin", Tty())
    assert cli.main(["restaurar", "--tabla", str(table)]) == 2
    assert "No hay entrada" in capsys.readouterr().err


def _docx_bytes() -> bytes:
    import io
    import zipfile

    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(
            "word/document.xml",
            f"<w:document {w}><w:body><w:p><w:r><w:t>Paciente: Rosa Elena Quintero, "
            "C.C. 41.888.222</w:t></w:r></w:p></w:body></w:document>",
        )
        z.writestr("word/media/image1.png", "png")
        z.writestr(
            "docProps/core.xml",
            '<cp:coreProperties xmlns:cp="x" xmlns:dc="y"><dc:creator>Fabio</dc:creator>'
            "</cp:coreProperties>",
        )
    return buffer.getvalue()


def test_word_anonimizar_detectar_y_restaurar(tmp_path, capsys):
    import zipfile

    src = tmp_path / "historia.docx"
    src.write_bytes(_docx_bytes())
    tabla = tmp_path / "tabla.json"
    code, _, err = run(
        ["anonimizar", "-f", str(src), "-m", "seudonimo", "--tabla", str(tabla)], capsys
    )
    out = tmp_path / "historia_anonimizado.docx"
    assert code == 0 and out.exists() and tabla.exists()
    assert "CEDULA=1" in err and "Metadatos limpiados: autor" in err and "Advertencia" in err
    doc = zipfile.ZipFile(out).read("word/document.xml").decode()
    assert "[NOMBRE_1]" in doc and "Rosa" not in doc

    code, out_text, _ = run(["detectar", "-f", str(src)], capsys)
    assert "word/document" not in out_text and "document, párrafo 1" in out_text
    assert "Total: CEDULA=1, NOMBRE=1" in out_text
    _, js, _ = run(["detectar", "-f", str(src), "--json"], capsys)
    assert json.loads(js)["total"] == 2
    _, res, _ = run(["detectar", "-f", str(src), "--resumen"], capsys)
    assert "TOTAL" in res and "2" in res
    _, res_js, _ = run(["detectar", "-f", str(src), "--resumen", "--json"], capsys)
    assert json.loads(res_js) == {"CEDULA": 1, "NOMBRE": 1}

    code, _, err = run(["restaurar", "-f", str(out), "--tabla", str(tabla)], capsys)
    restored = tmp_path / "historia_anonimizado_restaurado.docx"
    assert code == 0 and "restaurado" in err
    assert "Rosa Elena Quintero" in zipfile.ZipFile(restored).read("word/document.xml").decode()


def test_office_con_salida_explicita_conservar_metadatos_y_errores(tmp_path, capsys):
    import zipfile

    src = tmp_path / "h.docx"
    src.write_bytes(_docx_bytes())
    dest = tmp_path / "limpio.docx"
    code, _, _ = run(
        ["anonimizar", "-f", str(src), "-o", str(dest), "--conservar-metadatos"], capsys
    )
    assert code == 0
    assert b"Fabio" in zipfile.ZipFile(dest).read("docProps/core.xml")
    bad = tmp_path / "roto.xlsx"
    bad.write_bytes(b"no es zip")
    for cmd in (["anonimizar", "-f", str(bad)], ["detectar", "-f", str(bad)]):
        code, _, err = run(cmd, capsys)
        assert code == 2 and "no es un .xlsx válido" in err
    tabla = tmp_path / "t.json"
    tabla.write_text('{"version": 1, "mapping": {}}', encoding="utf-8")
    code, _, err = run(["restaurar", "-f", str(bad), "--tabla", str(tabla)], capsys)
    assert code == 2 and "No se pudo restaurar" in err
    code, _, err = run(["anonimizar", "-f", str(tmp_path / "no.docx")], capsys)
    assert code == 2 and "No se pudo leer" in err
