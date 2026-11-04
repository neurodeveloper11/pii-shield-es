"""Genera los bloques de ejemplos de ``docs/index.html`` con la salida REAL de la librería.

Uso:
    python scripts/build_docs.py          # reescribe los bloques entre marcadores
    python scripts/build_docs.py --check  # falla si la web no coincide con la librería

Los escenarios usan datos inventados: nombres comunes combinados, números ficticios,
tarjetas de prueba públicas, IP de documentación (RFC 5737/3849) y dominios example.*.
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

from pii_shield_es import PIIType, PseudonymTable, detect
from pii_shield_es.anonymize import label_for, mask_value

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "docs" / "index.html"
DEMO_START, DEMO_END = "<!-- DEMO:START -->", "<!-- DEMO:END -->"
CSV_START, CSV_END = "<!-- CSV:START -->", "<!-- CSV:END -->"

MODES = ("etiqueta", "mascara", "seudonimo")
MODE_LABEL = {
    "etiqueta": ("Etiqueta", "Label"),
    "mascara": ("Máscara", "Mask"),
    "seudonimo": ("Seudónimo", "Pseudonym"),
}

# (id, título ES, título EN, texto)
SCENARIOS: tuple[tuple[str, str, str, str], ...] = (
    (
        "salud",
        "Historia clínica",
        "Medical record",
        "Paciente: Rosa Elena Quintero, C.C. 41.888.222, fecha de nacimiento: 14/03/1957.\n"
        "Acompañante: Héctor Julio Quintero, celular 311 555 0142.\n"
        "Residencia: Calle 45 # 12-30 Apto 301, barrio Galerías.\n"
        "Motivo de consulta: dolor torácico de tres días de evolución. TA 140/90, FC 88.",
    ),
    (
        "soporte",
        "Chat de soporte",
        "Support chat",
        "Cliente: Hola, soy Fabián Andrés Cárdenas. Me cobraron dos veces con la tarjeta "
        "4111 1111 1111 1111.\n"
        "Mi correo es fabian.cardenas@example.com y mi WhatsApp +57 300 555 0175.\n"
        "Agente: Ya escalamos el caso #45821; le responderemos en 24 horas.",
    ),
    (
        "proveedores",
        "Proveedores y pagos",
        "Vendors and payments",
        "Proveedor: Insumos del Sur S.A.S., NIT 900.123.456-8.\n"
        "Representante legal: Juan Sebastián Arango, C.C. 80.123.456.\n"
        "Pagar a la cuenta de ahorros No. 0123456789012 antes del viernes.\n"
        "Notificaciones: Avenida Calle 26 # 69-76 Torre 3 Oficina 602.",
    ),
    (
        "seguridad",
        "Registro de seguridad",
        "Security log",
        "02:13 login fallido usuario ana.ruiz@example.com desde la IP 203.0.113.45\n"
        "02:14 bloqueo preventivo; origen IPv6 2001:db8:85a3::8a2e:370:7334\n"
        "02:20 versión 2.10.4 del agente reinició el servicio sin errores.",
    ),
)

CSV_HEADER = ("id", "cliente", "documento", "contacto", "nota")
CSV_ROWS: tuple[tuple[str, ...], ...] = (
    (
        "1",
        "Andrea Carolina Ruiz",
        "C.C. 1.032.456.789",
        "andrea.ruiz@example.com",
        "Pide factura a nombre de su empresa.",
    ),
    ("2", "Luis Carlos Mora", "C.C. 79.111.222", "315 555 0144", "Placa de su moto: KLM27B."),
    (
        "3",
        "Marcela Pineda Ríos",
        "C.C. 52.345.678",
        "marcela.p@example.org",
        "Pagó con tarjeta 5555 5555 5555 4444.",
    ),
)
CSV_COLUMNS = (1, 2, 3, 4)


def _mark(tipo: PIIType, inner: str) -> str:
    return f'<mark class="e e-{tipo.value}" title="{tipo.value}">{html.escape(inner)}</mark>'


def render_text(text: str, modo: str | None, table: PseudonymTable | None = None) -> str:
    """HTML con las entidades marcadas; ``modo=None`` muestra el texto original."""
    pieces: list[str] = []
    cursor = 0
    for ent in detect(text):
        pieces.append(html.escape(text[cursor : ent.start]))
        if modo is None:
            shown = ent.text
        elif modo == "etiqueta":
            shown = label_for(ent.type)
        elif modo == "mascara":
            shown = mask_value(ent.type, ent.text)
        else:
            assert table is not None
            shown = table.token_for(ent.type, ent.text)
        pieces.append(_mark(ent.type, shown))
        cursor = ent.end
    pieces.append(html.escape(text[cursor:]))
    return "".join(pieces)


def _tab_button(group: str, key: str, es: str, en: str, selected: bool, kind: str) -> str:
    return (
        f'<button type="button" role="tab" id="tab-{group}-{key}" '
        f'aria-selected="{"true" if selected else "false"}"'
        f"{'' if selected else ' tabindex=' + chr(34) + '-1' + chr(34)} "
        f'data-target="{group}-{key}" data-group="{kind}">'
        f'<span data-l="es">{es}</span><span data-l="en">{en}</span></button>'
    )


def render_demo() -> str:
    out = [DEMO_START]
    out.append('<div class="tabs tabs-scenario" role="tablist" aria-label="Escenario / Scenario">')
    for i, (sid, es, en, _text) in enumerate(SCENARIOS):
        out.append(_tab_button("sc", sid, es, en, i == 0, "scenario"))
    out.append("</div>")
    for i, (sid, _es, _en, text) in enumerate(SCENARIOS):
        hidden = "" if i == 0 else " hidden"
        out.append(
            f'<div class="demo-scenario" id="sc-{sid}" role="tabpanel" '
            f'aria-labelledby="tab-sc-{sid}"{hidden}>'
        )
        out.append('<div class="example-grid">')
        out.append('<div class="pane">')
        out.append(
            '<div class="pane-title"><span data-l="es">Entrada · datos detectados</span>'
            '<span data-l="en">Input · detected data</span></div>'
        )
        out.append(f'<pre class="sample" id="in-{sid}">{render_text(text, None)}</pre>')
        out.append("</div>")
        out.append('<div class="pane">')
        out.append('<div class="pane-title"><span data-l="es">Salida</span>')
        out.append('<span data-l="en">Output</span>')
        out.append(f'<div class="tabs" role="tablist" aria-label="Modo / Mode ({sid})">')
        for j, modo in enumerate(MODES):
            es, en = MODE_LABEL[modo]
            out.append(_tab_button(f"out-{sid}", modo, es, en, j == 0, "mode"))
        out.append("</div></div>")
        table = PseudonymTable()
        for j, modo in enumerate(MODES):
            hidden_mode = "" if j == 0 else " hidden"
            body = render_text(text, modo, table if modo == "seudonimo" else None)
            out.append(
                f'<pre class="sample" id="out-{sid}-{modo}" role="tabpanel" '
                f'aria-labelledby="tab-out-{sid}-{modo}"{hidden_mode}>{body}</pre>'
            )
        out.append("</div></div></div>")
    out.append(DEMO_END)
    return "\n".join(out)


def _csv_table(rows: list[tuple[str, ...]], caption_es: str, caption_en: str, cls: str) -> str:
    head = "".join(f'<th scope="col">{html.escape(h)}</th>' for h in CSV_HEADER)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return (
        f'<div class="table-wrap"><table class="csv {cls}">'
        f'<caption><span data-l="es">{caption_es}</span><span data-l="en">{caption_en}</span>'
        f"</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def render_csv() -> str:
    """La misma hoja antes y después de ``pii-shield anonimizar -m seudonimo --tabla``."""
    table = PseudonymTable()
    before = [
        tuple(render_text(c, None) if j in CSV_COLUMNS else html.escape(c) for j, c in enumerate(r))
        for r in CSV_ROWS
    ]
    after = [
        tuple(
            render_text(c, "seudonimo", table) if j in CSV_COLUMNS else html.escape(c)
            for j, c in enumerate(r)
        )
        for r in CSV_ROWS
    ]
    return "\n".join(
        [
            CSV_START,
            '<div class="csv-compare">',
            _csv_table(before, "clientes.csv (original)", "clientes.csv (original)", "csv-before"),
            '<div class="csv-arrow" aria-hidden="true">→</div>',
            _csv_table(
                after,
                "clientes_anon.csv (seudonimizado, reversible con la tabla)",
                "clientes_anon.csv (pseudonymized, reversible with the table)",
                "csv-after",
            ),
            "</div>",
            CSV_END,
        ]
    )


def _replace(text: str, start: str, end: str, block: str) -> str:
    if start not in text or end not in text:
        raise SystemExit(f"docs/index.html no contiene {start}")
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    return head + block + tail


def build(index: Path = INDEX) -> str:
    text = index.read_text(encoding="utf-8")
    text = _replace(text, DEMO_START, DEMO_END, render_demo())
    return _replace(text, CSV_START, CSV_END, render_csv())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    new = build()
    if args.check:
        if new != INDEX.read_text(encoding="utf-8"):
            print(
                "docs/index.html está desactualizado: python scripts/build_docs.py", file=sys.stderr
            )
            return 1
        print("OK: ejemplos de la web sincronizados con la librería.")
        return 0
    INDEX.write_text(new, encoding="utf-8")
    print("docs/index.html actualizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
