"""La página de docs/ no debe desincronizarse del código ni cargar recursos externos."""

import html
import re
import sys
from pathlib import Path

import pytest

from datashield_es import PIIType, PseudonymTable, anonymize

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "eval"))

import build_docs  # noqa: E402

import evaluate  # noqa: E402

DOCS = Path(__file__).resolve().parent.parent / "docs"
INDEX = (DOCS / "index.html").read_text(encoding="utf-8")
REPO_URL = "https://github.com/neurodeveloper11/pii-shield-es"


def _text_by_id(elem_id: str) -> str:
    match = re.search(rf'<(pre|td)[^>]*id="{elem_id}"[^>]*>(.*?)</\1>', INDEX, re.S)
    assert match, elem_id
    return html.unescape(re.sub(r"<[^>]+>", "", match.group(2)))


def test_bloques_generados_estan_sincronizados():
    assert build_docs.build() == INDEX, "Ejecuta: python scripts/build_docs.py"
    assert build_docs.main(["--check"]) == 0


@pytest.mark.parametrize("scenario", build_docs.SCENARIOS, ids=lambda s: s[0])
def test_cada_escenario_coincide_con_la_libreria(scenario):
    sid, _es, _en, text = scenario
    assert _text_by_id(f"in-{sid}") == text
    assert _text_by_id(f"out-{sid}-etiqueta") == anonymize(text, "etiqueta")
    assert _text_by_id(f"out-{sid}-mascara") == anonymize(text, "mascara")
    tabla = PseudonymTable()
    seud = _text_by_id(f"out-{sid}-seudonimo")
    assert seud == anonymize(text, "seudonimo", tabla=tabla)
    assert tabla.restore(seud) == text
    assert "[" in seud  # el escenario realmente contiene datos detectados


def test_hoja_csv_coincide_con_la_libreria():
    block = INDEX.split(build_docs.CSV_START, 1)[1].split(build_docs.CSV_END, 1)[0]
    after = block.split('class="csv csv-after"', 1)[1]
    cells = [html.unescape(re.sub(r"<[^>]+>", "", c)) for c in re.findall(r"<td>(.*?)</td>", after)]
    tabla = PseudonymTable()
    expected = [
        anonymize(c, "seudonimo", tabla=tabla) if j in build_docs.CSV_COLUMNS else c
        for row in build_docs.CSV_ROWS
        for j, c in enumerate(row)
    ]
    assert cells == expected


def test_grafica_de_metricas_sincronizada():
    results = evaluate.run()
    assert evaluate.docs_in_sync(evaluate.render_chart(results))


def test_cifra_de_tipos_coincide():
    assert f"<strong>{len(PIIType)}</strong>" in INDEX
    for tipo in PIIType:
        assert f"e-{tipo.value}" in INDEX, tipo


def test_ejemplo_codigo_de_instalacion_es_correcto():
    texto = "Mi cédula es 1.023.456.789 y mi correo es a@example.com"
    assert anonymize(texto) == "Mi cédula es [CEDULA] y mi correo es [CORREO]"
    assert '# "Mi cédula es [CEDULA] y mi correo es [CORREO]"' in INDEX


def test_boton_visible_hacia_el_repositorio():
    links = re.findall(r'<a class="btn btn-primary" href="([^"]+)"', INDEX)
    assert links and set(links) == {REPO_URL}


def test_sin_recursos_externos_ni_estilos_o_scripts_en_linea():
    assert "style=" not in INDEX
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", INDEX), "script en línea"
    sources = re.findall(r'(?:src|href)="([^"]+)"', INDEX)
    for url in sources:
        if url.startswith("http"):
            assert url.startswith(REPO_URL), url
    for name in ("style.css", "app.js"):
        text = (DOCS / name).read_text(encoding="utf-8")
        assert "http://" not in text and "https://" not in text.replace(REPO_URL, "")
        assert "@import" not in text


def test_bilingue_y_con_modo_oscuro():
    assert INDEX.count('data-l="es"') > 20 and INDEX.count('data-l="en"') > 20
    css = (DOCS / "style.css").read_text(encoding="utf-8")
    assert "prefers-color-scheme: dark" in css and '[data-theme="dark"]' in css
    assert (DOCS / ".nojekyll").exists() and (DOCS / "favicon.svg").exists()


def test_todos_los_ids_referenciados_existen():
    ids = set(re.findall(r'\bid="([^"]+)"', INDEX))
    for ref in re.findall(r'(?:href="#|data-target="|data-copy=")([^"]+)"', INDEX):
        assert ref in ids, ref
