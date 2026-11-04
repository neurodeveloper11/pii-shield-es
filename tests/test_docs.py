"""La página de docs/ no debe desincronizarse del código ni cargar recursos externos."""

import html
import re
from pathlib import Path

import pytest

from pii_shield_es import PseudonymTable, anonymize

DOCS = Path(__file__).resolve().parent.parent / "docs"
INDEX = (DOCS / "index.html").read_text(encoding="utf-8")
REPO_URL = "https://github.com/neurodeveloper11/pii-shield-es"


def _pre_text(pre_id: str) -> str:
    match = re.search(rf'<pre[^>]*id="{pre_id}"[^>]*>(.*?)</pre>', INDEX, re.S)
    assert match, pre_id
    return html.unescape(re.sub(r"<[^>]+>", "", match.group(1)))


@pytest.fixture(scope="module")
def entrada() -> str:
    return _pre_text("ex-input")


def test_ejemplo_etiqueta_coincide_con_la_libreria(entrada):
    assert _pre_text("ex-etiqueta") == anonymize(entrada, "etiqueta")


def test_ejemplo_mascara_coincide_con_la_libreria(entrada):
    assert _pre_text("ex-mascara") == anonymize(entrada, "mascara")


def test_ejemplo_seudonimo_coincide_con_la_libreria(entrada):
    tabla = PseudonymTable()
    assert _pre_text("ex-seudonimo") == anonymize(entrada, "seudonimo", tabla=tabla)
    assert tabla.restore(_pre_text("ex-seudonimo")) == entrada


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
