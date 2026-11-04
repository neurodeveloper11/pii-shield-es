"""Anonimización de archivos completos: .txt, .md, .csv, .tsv, Word (.docx) y Excel (.xlsx).

Sin dependencias: un .docx y un .xlsx son archivos ZIP con XML por dentro. Se edita solo el
texto, de modo que el formato (negritas, tablas, estilos, anchos de columna, fórmulas) se
conserva.

Qué se procesa:

* **Word:** cuerpo, tablas, encabezados, pies de página, notas al pie y al final, comentarios,
  texto eliminado con control de cambios, campos (``mailto:``) y vínculos de correo.
* **Excel:** celdas de texto y numéricas de todas las hojas, usando el **encabezado de la
  columna como contexto** («Cédula», «Celular», «Nombre»…), y los comentarios. Las celdas con
  fórmula no se tocan.
* **Metadatos** (``limpiar_metadatos=True``): autor, «modificado por», empresa y autores de
  comentarios y revisiones.

Límites: no se analizan imágenes, objetos incrustados, gráficos ni cachés de tablas dinámicas;
si existen, el reporte lo advierte.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape, unescape

from .anonymize import PseudonymTable, normalize_mode, replace_entities
from .detectors import detect
from .types import Entity, PIIType, coerce_types

TEXT_SUFFIXES = (".txt", ".md", ".log")
TABLE_SUFFIXES = (".csv", ".tsv")
SUPPORTED = TEXT_SUFFIXES + TABLE_SUFFIXES + (".docx", ".xlsx")

_XML_ENTITIES = {"&quot;": '"', "&apos;": "'"}


class UnsupportedFileError(ValueError):
    """El tipo de archivo no está soportado."""


@dataclass
class FileReport:
    """Qué se encontró y dónde. ``hallazgos`` no incluye el texto original a propósito."""

    hallazgos: list[dict[str, object]] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    metadatos_limpiados: list[str] = field(default_factory=list)

    @property
    def conteo(self) -> dict[str, int]:
        counts = Counter(str(h["tipo"]) for h in self.hallazgos)
        return dict(sorted(counts.items()))

    @property
    def total(self) -> int:
        return len(self.hallazgos)

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "conteo": self.conteo,
            "hallazgos": self.hallazgos,
            "advertencias": self.advertencias,
            "metadatos_limpiados": self.metadatos_limpiados,
        }


# --------------------------------------------------------------------------- columnas tipadas


def _norm_header(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


# Encabezados que, por sí solos, dicen qué contiene la columna. Se comparan normalizados
# (minúsculas, sin tildes ni puntuación) y deben coincidir completos.
_TYPED_HEADERS: dict[str, PIIType] = {}
for _tipo, _names in {
    PIIType.CEDULA: "cedula|cedula de ciudadania|cc|c c|documento|documento de identidad|"
    "numero de documento|no documento|nro documento|num documento|identificacion|"
    "numero de identificacion|tarjeta de identidad|nuip",
    PIIType.CEDULA_EXTRANJERIA: "cedula de extranjeria|ce|c e",
    PIIType.NIT: "nit|numero nit|nit empresa",
    PIIType.PASAPORTE: "pasaporte|numero de pasaporte|passport",
    PIIType.TELEFONO: "telefono|telefonos|tel|celular|cel|movil|whatsapp|numero de celular|"
    "numero de telefono|telefono fijo|telefono de contacto|contacto telefonico|phone",
    PIIType.CORREO: "correo|correo electronico|email|e mail|mail",
    PIIType.DIRECCION: "direccion|direccion de residencia|domicilio|direccion residencia|address",
    PIIType.PLACA: "placa|placa vehiculo|placa del vehiculo",
    PIIType.CUENTA_BANCARIA: "cuenta|cuenta bancaria|numero de cuenta|no cuenta|cuenta de ahorros|"
    "iban|clabe",
    PIIType.TARJETA_CREDITO: "tarjeta|tarjeta de credito|numero de tarjeta",
    PIIType.DIRECCION_IP: "ip|direccion ip",
    PIIType.FECHA_NACIMIENTO: "fecha de nacimiento|fecha nacimiento|f nacimiento|nacimiento|"
    "f nac|cumpleanos|birth date|date of birth|dob",
    PIIType.NOMBRE: "nombre|nombres|nombre completo|nombres y apellidos|apellido|apellidos|"
    "primer nombre|segundo nombre|primer apellido|segundo apellido|paciente|titular|"
    "beneficiario|acudiente|contacto de emergencia|name|full name",
}.items():
    for _name in _names.split("|"):
        _TYPED_HEADERS[_name] = _tipo


_MIN_DIGITS = {
    PIIType.CEDULA: 5,
    PIIType.CEDULA_EXTRANJERIA: 5,
    PIIType.NIT: 6,
    PIIType.PASAPORTE: 4,
    PIIType.TELEFONO: 7,
    PIIType.CUENTA_BANCARIA: 6,
    PIIType.TARJETA_CREDITO: 12,
    PIIType.DIRECCION: 1,
    PIIType.PLACA: 2,
    PIIType.DIRECCION_IP: 2,
    PIIType.FECHA_NACIMIENTO: 2,
}


def _plausible(tipo: PIIType, value: str) -> bool:
    """Forma mínima para tratar una celda completa como del tipo de su columna."""
    digits = sum(c.isdigit() for c in value)
    if tipo is PIIType.CORREO:
        return "@" in value or "(at)" in value.lower() or " arroba " in value.lower()
    if tipo is PIIType.NOMBRE:
        return any(c.isalpha() for c in value) and digits == 0
    return digits >= _MIN_DIGITS.get(tipo, 1)


def header_type(header: str | None) -> PIIType | None:
    """Tipo de PII que anuncia un encabezado de columna, o ``None``."""
    if not header:
        return None
    return _TYPED_HEADERS.get(_norm_header(header))


# --------------------------------------------------------------------------- escaneo de texto


@dataclass
class _Options:
    mode: str | None  # None = solo detectar
    tipos: tuple[PIIType, ...]
    table: PseudonymTable | None
    min_score: float
    report: FileReport


def _scan(text: str, opts: _Options, header: str | None = None) -> list[Entity]:
    """Entidades en ``text``. Con ``header`` se usa el encabezado como contexto y, si la
    columna es tipada y no se detecta nada, la celda completa se trata como de ese tipo."""
    if not text.strip():
        return []
    if header:
        if _norm_header(text) == _norm_header(header):
            return []  # celda que repite el encabezado (p. ej., tablas apiladas)
        prefix = f"{header.strip()}: "
        shift = len(prefix)
        found = [
            Entity(e.type, e.start - shift, e.end - shift, e.text, e.score, e.detector)
            for e in detect(prefix + text, tipos=opts.tipos, min_score=opts.min_score)
            if e.start >= shift
        ]
        typed = header_type(header)
        if not found and typed is not None and typed in opts.tipos:
            start = len(text) - len(text.lstrip())
            end = len(text.rstrip())
            if _plausible(typed, text[start:end]):
                found = [Entity(typed, start, end, text[start:end], 0.75, "columna")]
        return found
    return detect(text, tipos=opts.tipos, min_score=opts.min_score)


def _transform(text: str, opts: _Options, location: str, header: str | None = None) -> str:
    entities = _scan(text, opts, header)
    for ent in entities:
        opts.report.hallazgos.append(
            {"tipo": ent.type.value, "ubicacion": location, "score": round(ent.score, 2)}
        )
    if opts.mode is None or not entities:
        return text
    return replace_entities(text, entities, opts.mode, opts.table)


# --------------------------------------------------------------------------- texto y CSV


def _decode(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1"), "latin-1"  # pragma: no cover - latin-1 nunca falla


def _encode(text: str, encoding: str, had_bom: bool) -> bytes:
    if encoding == "utf-8-sig" and not had_bom:
        encoding = "utf-8"
    return text.encode(encoding, errors="replace")


def _process_text(data: bytes, opts: _Options) -> bytes:
    text, encoding = _decode(data)
    lines = text.split("\n")
    out = [_transform(line, opts, f"línea {i}") for i, line in enumerate(lines, start=1)]
    return _encode("\n".join(out), encoding, data.startswith(b"\xef\xbb\xbf"))


def process_rows(
    rows: list[list[str]],
    opts_or_fn: Callable[[str, int, int, str | None], str],
    *,
    header: bool = True,
    columns: set[int] | None = None,
) -> list[list[str]]:
    """Aplica ``fn(celda, fila, columna, encabezado)`` a cada celda de datos."""
    head = rows[0] if header and rows else None
    out: list[list[str]] = []
    for i, row in enumerate(rows):
        if head is not None and i == 0:
            out.append(list(row))
            continue
        out.append(
            [
                opts_or_fn(cell, i, j, head[j] if head is not None and j < len(head) else None)
                if columns is None or j in columns
                else cell
                for j, cell in enumerate(row)
            ]
        )
    return out


def _process_table(data: bytes, opts: _Options, suffix: str) -> bytes:
    text, encoding = _decode(data)
    if suffix == ".tsv":
        dialect: type[csv.Dialect] | csv.Dialect = csv.excel_tab
    else:
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text, newline=""), dialect))
    processed = process_rows(
        rows,
        lambda cell, i, j, head: _transform(cell, opts, f"fila {i + 1}, columna {j + 1}", head),
    )
    buffer = io.StringIO(newline="")
    csv.writer(buffer, dialect).writerows(processed)
    return _encode(buffer.getvalue(), encoding, data.startswith(b"\xef\xbb\xbf"))


# --------------------------------------------------------------------------- XML de Office


def _xml_unescape(value: str) -> str:
    value = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), value)
    value = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), value)
    return unescape(value, _XML_ENTITIES)


def _xml_escape(value: str) -> str:
    return escape(value)


def _apply_edits(xml: str, edits: list[tuple[int, int, str]]) -> str:
    for start, end, new in sorted(edits, reverse=True):
        xml = xml[:start] + new + xml[end:]
    return xml


def _rewrite_group(
    pieces: list[tuple[int, int, str] | str], opts: _Options, location: str
) -> list[tuple[int, int, str]]:
    """``pieces``: fragmentos de texto ``(inicio_xml, fin_xml, texto)`` o separadores virtuales
    (``str``). Devuelve las ediciones de XML para reflejar la anonimización del grupo."""
    text = "".join(p if isinstance(p, str) else p[2] for p in pieces)
    entities = _scan(text, opts)
    for ent in entities:
        opts.report.hallazgos.append(
            {"tipo": ent.type.value, "ubicacion": location, "score": round(ent.score, 2)}
        )
    if opts.mode is None or not entities:
        return []
    replacement = {
        id(ent): replace_entities(ent.text, [Entity(ent.type, 0, len(ent.text), ent.text,
                                                    ent.score)], opts.mode, opts.table)
        for ent in entities
    }  # fmt: skip
    edits: list[tuple[int, int, str]] = []
    offset = 0
    for piece in pieces:
        if isinstance(piece, str):
            offset += len(piece)
            continue
        xml_start, xml_end, ptext = piece
        p_start, p_end = offset, offset + len(ptext)
        new = []
        cursor = p_start
        for ent in entities:
            if ent.end <= p_start or ent.start >= p_end:
                continue
            seg_start, seg_end = max(ent.start, p_start), min(ent.end, p_end)
            new.append(text[cursor:seg_start])
            if seg_start == ent.start:  # el reemplazo va en el fragmento donde empieza
                new.append(replacement[id(ent)])
            cursor = seg_end
        if cursor != p_start or new:
            new.append(text[cursor:p_end])
            edits.append((xml_start, xml_end, _xml_escape("".join(new))))
        offset = p_end
    return edits


_W_TOKEN_RE = re.compile(
    r"<w:p\b[^>]*?/>|<w:p\b[^>]*>|</w:p>"
    r"|<w:(t|delText|instrText)\b[^>]*?/>"
    r"|<w:(t|delText|instrText)\b([^>]*)>(.*?)</w:\2>"
    r"|<w:(?:tab|br|cr)\b[^>]*/>",
    re.S,
)


def _process_word_part(xml: str, opts: _Options, part: str) -> str:
    edits: list[tuple[int, int, str]] = []
    pieces: list[tuple[int, int, str] | str] = []
    needs_preserve: dict[int, int] = {}  # inicio del texto -> posición donde va el atributo
    paragraph = 0

    def flush() -> None:
        nonlocal pieces
        if any(not isinstance(p, str) for p in pieces):
            group = _rewrite_group(pieces, opts, f"{part}, párrafo {paragraph}")
            edits.extend(group)
            for start, _end, _new in group:
                if start in needs_preserve:
                    pos = needs_preserve[start]
                    edits.append((pos, pos, ' xml:space="preserve"'))
        pieces = []

    for m in _W_TOKEN_RE.finditer(xml):
        token = m.group(0)
        if token.startswith(("<w:p ", "<w:p>", "<w:p/")) or token == "</w:p>":
            flush()
            if not token.startswith("</"):
                paragraph += 1
            continue
        if m.group(2):  # <w:t ...>texto</w:t>
            attrs = m.group(3)
            pieces.append((m.start(4), m.end(4), _xml_unescape(m.group(4))))
            if "xml:space" not in attrs:
                needs_preserve[m.start(4)] = m.start(4) - 1  # antes del «>» de apertura
        elif m.group(1):
            continue  # <w:t/> vacío
        else:
            pieces.append("\t" if "tab" in token[:8] else "\n")
    flush()
    return _apply_edits(xml, edits)


def _scrub_attr(xml: str, names: Iterable[str], report: FileReport, label: str) -> str:
    changed = False
    for name in names:
        pattern = re.compile(rf'(\s{re.escape(name)}=")([^"]*)(")')

        def sub(m: re.Match[str]) -> str:
            nonlocal changed
            if m.group(2) and m.group(2) != "DataShield":
                changed = True
                return m.group(1) + "DataShield" + m.group(3)
            return m.group(0)

        xml = pattern.sub(sub, xml)
    if changed and label not in report.metadatos_limpiados:
        report.metadatos_limpiados.append(label)
    return xml


def _scrub_elements(xml: str, tags: Iterable[str], report: FileReport, label: str) -> str:
    for tag in tags:
        pattern = re.compile(rf"(<{re.escape(tag)}\b[^>]*>)([^<]+)(</{re.escape(tag)}>)")
        if pattern.search(xml):
            xml = pattern.sub(r"\1\3", xml)
            if label not in report.metadatos_limpiados:
                report.metadatos_limpiados.append(label)
    return xml


def _scrub_core_props(files: dict[str, bytes], report: FileReport) -> None:
    if "docProps/core.xml" in files:
        xml = files["docProps/core.xml"].decode("utf-8")
        xml = _scrub_elements(xml, ("dc:creator",), report, "autor")
        xml = _scrub_elements(xml, ("cp:lastModifiedBy",), report, "modificado por")
        files["docProps/core.xml"] = xml.encode("utf-8")
    if "docProps/app.xml" in files:
        xml = files["docProps/app.xml"].decode("utf-8")
        xml = _scrub_elements(xml, ("Company", "Manager"), report, "empresa / responsable")
        files["docProps/app.xml"] = xml.encode("utf-8")


_MAILTO_RE = re.compile(r'(Target="mailto:)([^"?]*)')


def _process_docx(files: dict[str, bytes], opts: _Options, scrub: bool) -> None:
    word_parts = [
        name
        for name in files
        if re.fullmatch(
            r"word/(document|header\d*|footer\d*|footnotes|endnotes|comments\w*)\.xml", name
        )
    ]
    for name in word_parts:
        xml = files[name].decode("utf-8")
        part = name.split("/")[-1].removesuffix(".xml")
        xml = _process_word_part(xml, opts, part)
        if scrub:
            xml = _scrub_attr(
                xml, ("w:author", "w:initials"), opts.report, "autores de comentarios y cambios"
            )
        files[name] = xml.encode("utf-8")
    for name in [n for n in files if re.fullmatch(r"word/_rels/[^/]+\.rels", n)]:
        xml = files[name].decode("utf-8")

        def mailto(m: re.Match[str]) -> str:
            return m.group(1) + _xml_escape(
                _transform(_xml_unescape(m.group(2)), opts, "vínculo de correo")
            )

        files[name] = _MAILTO_RE.sub(mailto, xml).encode("utf-8")
    if scrub and "word/people.xml" in files:
        xml = files["word/people.xml"].decode("utf-8")
        files["word/people.xml"] = _scrub_attr(
            xml, ("w15:author", "w15:userId"), opts.report, "autores de comentarios y cambios"
        ).encode("utf-8")
    if any(n.startswith("word/media/") for n in files):
        opts.report.advertencias.append(
            "El documento tiene imágenes: su contenido no se analiza (revísalas a mano)."
        )
    if any(n.startswith("word/embeddings/") for n in files):
        opts.report.advertencias.append(
            "El documento tiene objetos incrustados que no se analizan."
        )


# --------------------------------------------------------------------------- Excel

_SI_RE = re.compile(r"<si>(.*?)</si>|<si/>", re.S)
_T_RE = re.compile(r"<t\b([^>]*)>(.*?)</t>", re.S)
_RPH_RE = re.compile(r"<rPh\b.*?</rPh>", re.S)
_ROW_RE = re.compile(r'<row\b[^>]*\br="(\d+)"', re.S)
_CELL_RE = re.compile(r"<c\b([^>]*?)(?:/>|>(.*?)</c>)", re.S)
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_V_RE = re.compile(r"<v>(.*?)</v>", re.S)


def _cell_text_from_runs(inner: str) -> str:
    inner = _RPH_RE.sub("", inner)
    return "".join(_xml_unescape(m.group(2)) for m in _T_RE.finditer(inner))


def _col_row(ref: str) -> tuple[str, int]:
    m = re.fullmatch(r"([A-Z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else ("", 0)


def _process_xlsx(files: dict[str, bytes], opts: _Options, scrub: bool) -> None:
    sst_xml = files.get("xl/sharedStrings.xml", b"").decode("utf-8")
    sst = [_cell_text_from_runs(m.group(1) or "") for m in _SI_RE.finditer(sst_xml)]
    sheet_names = _sheet_names(files)
    replaced_sst: set[int] = set()
    kept_sst: set[int] = set()

    for name in sorted(n for n in files if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)):
        xml = files[name].decode("utf-8")
        label = sheet_names.get(name, name.split("/")[-1].removesuffix(".xml"))
        rows = [int(r) for r in _ROW_RE.findall(xml)]
        header_row = min(rows) if rows else 1
        headers: dict[str, str] = {}
        cells = list(_CELL_RE.finditer(xml))

        def value_of(attrs: dict[str, str], inner: str) -> str | None:
            kind = attrs.get("t", "n")
            if "<f>" in inner or "<f " in inner:
                return None  # fórmula: no se toca
            if kind == "s":
                v = _V_RE.search(inner)
                return (
                    sst[int(v.group(1))]
                    if v and v.group(1).isdigit() and int(v.group(1)) < len(sst)
                    else None
                )
            if kind == "inlineStr":
                return _cell_text_from_runs(inner)
            if kind == "n":
                v = _V_RE.search(inner)
                return v.group(1) if v else None
            return None

        for m in cells:
            attrs = dict(_ATTR_RE.findall(m.group(1)))
            col, row = _col_row(attrs.get("r", ""))
            if row == header_row:
                text = value_of(attrs, m.group(2) or "")
                if text:
                    headers[col] = text
        edits: list[tuple[int, int, str]] = []
        for m in cells:
            attrs = dict(_ATTR_RE.findall(m.group(1)))
            col, row = _col_row(attrs.get("r", ""))
            inner = m.group(2) or ""
            sst_index = None
            if attrs.get("t") == "s":
                v = _V_RE.search(inner)
                if v and v.group(1).isdigit():
                    sst_index = int(v.group(1))
            if row == header_row or not col:
                if sst_index is not None:
                    kept_sst.add(sst_index)
                continue
            text = value_of(attrs, inner)
            if text is None:
                if sst_index is not None:
                    kept_sst.add(sst_index)
                continue
            new = _transform(text, opts, f"{label}!{col}{row}", headers.get(col))
            if (
                opts.table is not None
                and attrs.get("t", "n") == "n"
                and _TOKEN_IN_XML_RE.fullmatch(new)
            ):
                opts.table.numeric_tokens.add(new)
            if new == text:
                if sst_index is not None:
                    kept_sst.add(sst_index)
                continue
            if sst_index is not None:
                replaced_sst.add(sst_index)
            keep = " ".join(f'{k}="{v}"' for k, v in _ATTR_RE.findall(m.group(1)) if k != "t")
            edits.append(
                (
                    m.start(),
                    m.end(),
                    f'<c {keep} t="inlineStr"><is><t xml:space="preserve">'
                    f"{_xml_escape(new)}</t></is></c>",
                )
            )
        files[name] = _apply_edits(xml, edits).encode("utf-8")

    # Las cadenas compartidas que ya no usa ninguna celda se vacían: si no, el dato original
    # seguiría dentro del archivo aunque no se vea en la hoja.
    orphan = replaced_sst - kept_sst
    if orphan and sst_xml:
        index = -1

        def blank(m: re.Match[str]) -> str:
            nonlocal index
            index += 1
            return "<si><t></t></si>" if index in orphan else m.group(0)

        files["xl/sharedStrings.xml"] = _SI_RE.sub(blank, sst_xml).encode("utf-8")

    comment_parts = [
        n
        for n in files
        if re.fullmatch(r"xl/(?:comments/)?comments?\d*\.xml", n)
        or re.fullmatch(r"xl/threadedComments/threadedComment\d*\.xml", n)
    ]
    for name in comment_parts:
        xml = files[name].decode("utf-8")
        edits = []
        for i, m in enumerate(re.finditer(r"<text>(.*?)</text>", xml, re.S), start=1):
            inner_start = m.start(1)
            runs = list(_T_RE.finditer(m.group(1)))
            pieces: list[tuple[int, int, str] | str] = (
                [
                    (inner_start + r.start(2), inner_start + r.end(2), _xml_unescape(r.group(2)))
                    for r in runs
                ]
                if runs
                else [(m.start(1), m.end(1), _xml_unescape(m.group(1)))]
            )
            edits.extend(_rewrite_group(pieces, opts, f"comentario {i}"))
        xml = _apply_edits(xml, edits)
        if scrub:
            xml = _scrub_elements(xml, ("author",), opts.report, "autores de comentarios")
        files[name] = xml.encode("utf-8")
    if scrub:
        for name in [n for n in files if re.fullmatch(r"xl/persons/person\d*\.xml", n)]:
            xml = files[name].decode("utf-8")
            files[name] = _scrub_attr(
                xml, ("displayName", "userId"), opts.report, "autores de comentarios"
            ).encode("utf-8")
    if any(n.startswith("xl/pivotCache/") for n in files):
        opts.report.advertencias.append(
            "El libro tiene tablas dinámicas: su caché puede conservar los datos originales. "
            "Actualízalas o elimínalas antes de compartir."
        )
    if any(n.startswith(("xl/media/", "xl/embeddings/")) for n in files):
        opts.report.advertencias.append(
            "El libro tiene imágenes u objetos incrustados que no se analizan."
        )


def _sheet_names(files: dict[str, bytes]) -> dict[str, str]:
    """``{ruta de la hoja: nombre visible}`` a partir de workbook.xml y sus relaciones."""
    try:
        wb = files["xl/workbook.xml"].decode("utf-8")
        rels = files["xl/_rels/workbook.xml.rels"].decode("utf-8")
    except KeyError:
        return {}
    targets = {
        m.group(1): m.group(2)
        for m in re.finditer(r'<Relationship\b[^>]*?Id="([^"]+)"[^>]*?Target="([^"]+)"', rels)
    }
    names = {}
    for m in re.finditer(r'<sheet\b[^>]*?name="([^"]+)"[^>]*?r:id="([^"]+)"', wb):
        target = targets.get(m.group(2), "")
        path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        names[path] = _xml_unescape(m.group(1))
    return names


# --------------------------------------------------------------------------- ZIP


def _process_zip(data: bytes, opts: _Options, kind: str, scrub: bool) -> bytes:
    try:
        source = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsupportedFileError(f"El archivo no es un {kind} válido") from exc
    with source:
        infos = source.infolist()
        files = {info.filename: source.read(info.filename) for info in infos}
    marker = "word/document.xml" if kind == ".docx" else "xl/workbook.xml"
    if marker not in files:
        raise UnsupportedFileError(f"El archivo no es un {kind} válido")
    if kind == ".docx":
        _process_docx(files, opts, scrub)
    else:
        _process_xlsx(files, opts, scrub)
    if scrub:
        _scrub_core_props(files, opts.report)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in infos:
            target.writestr(info, files[info.filename], compress_type=zipfile.ZIP_DEFLATED)
    return out.getvalue()


# --------------------------------------------------------------------------- API


def _suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise UnsupportedFileError(
            f"Formato no soportado: {suffix or filename!r}. Soportados: {', '.join(SUPPORTED)}"
        )
    return suffix


def _run(
    data: bytes,
    filename: str,
    mode: str | None,
    tipos: object,
    tabla: PseudonymTable | None,
    min_score: float,
    scrub: bool,
) -> tuple[bytes, FileReport]:
    suffix = _suffix(filename)
    if mode == "seudonimo" and tabla is None:
        tabla = PseudonymTable()
    opts = _Options(mode, coerce_types(tipos), tabla, min_score, FileReport())
    if suffix in TEXT_SUFFIXES:
        out = _process_text(data, opts)
    elif suffix in TABLE_SUFFIXES:
        out = _process_table(data, opts, suffix)
    else:
        out = _process_zip(data, opts, suffix, scrub)
    return out, opts.report


def anonymize_bytes(
    data: bytes,
    filename: str,
    modo: str = "etiqueta",
    *,
    tipos: Iterable[PIIType | str] | PIIType | str | None = None,
    tabla: PseudonymTable | None = None,
    min_score: float = 0.0,
    limpiar_metadatos: bool = True,
) -> tuple[bytes, FileReport]:
    """Anonimiza el contenido de un archivo (``filename`` solo se usa por su extensión).

    Devuelve los bytes del archivo anonimizado, en el mismo formato, y un :class:`FileReport`.
    """
    return _run(data, filename, normalize_mode(modo), tipos, tabla, min_score, limpiar_metadatos)


def detect_bytes(
    data: bytes,
    filename: str,
    *,
    tipos: Iterable[PIIType | str] | PIIType | str | None = None,
    min_score: float = 0.0,
) -> FileReport:
    """Solo detecta: devuelve dónde hay datos personales, sin modificar nada."""
    return _run(data, filename, None, tipos, None, min_score, False)[1]


def default_output_path(path: str | Path) -> Path:
    """``informe.docx`` → ``informe_anonimizado.docx`` (en la misma carpeta)."""
    path = Path(path)
    return path.with_name(f"{path.stem}_anonimizado{path.suffix}")


def anonymize_file(
    path: str | Path,
    salida: str | Path | None = None,
    modo: str = "etiqueta",
    *,
    tipos: Iterable[PIIType | str] | PIIType | str | None = None,
    tabla: PseudonymTable | None = None,
    min_score: float = 0.0,
    limpiar_metadatos: bool = True,
) -> tuple[Path, FileReport]:
    """Anonimiza un archivo en disco y escribe el resultado (por defecto ``*_anonimizado.*``)."""
    source = Path(path)
    target = Path(salida) if salida else default_output_path(source)
    data, report = anonymize_bytes(
        source.read_bytes(),
        source.name,
        modo,
        tipos=tipos,
        tabla=tabla,
        min_score=min_score,
        limpiar_metadatos=limpiar_metadatos,
    )
    target.write_bytes(data)
    return target, report


def scan_cell(
    text: str,
    header: str | None = None,
    *,
    tipos: Iterable[PIIType | str] | PIIType | str | None = None,
    min_score: float = 0.0,
) -> list[Entity]:
    """Entidades de una celda usando su encabezado como contexto (CSV, hojas de cálculo)."""
    opts = _Options(None, coerce_types(tipos), None, min_score, FileReport())
    return _scan(text, opts, header)


_TOKEN_IN_XML_RE = re.compile(r"\[([A-Z_]+)_(\d+)\]")
_NUMERIC_TOKEN_CELL_RE = re.compile(
    r'<c ([^>]*?) t="inlineStr"><is><t xml:space="preserve">(\[[A-Z_]+_\d+\])</t></is></c>'
)


def restore_bytes(data: bytes, filename: str, tabla: PseudonymTable) -> bytes:
    """Revierte la seudonimización de un archivo con la tabla local."""
    suffix = _suffix(filename)
    if suffix in TEXT_SUFFIXES + TABLE_SUFFIXES:
        text, encoding = _decode(data)
        return _encode(tabla.restore(text), encoding, data.startswith(b"\xef\xbb\xbf"))
    mapping = tabla.mapping

    def numeric_cell(m: re.Match[str]) -> str:
        token = m.group(2)
        if token in tabla.numeric_tokens and token in mapping:
            return f"<c {m.group(1)}><v>{_xml_escape(mapping[token])}</v></c>"
        return m.group(0)

    with zipfile.ZipFile(io.BytesIO(data)) as source:
        infos = source.infolist()
        files = {info.filename: source.read(info.filename) for info in infos}
    for name, content in files.items():
        if not name.endswith((".xml", ".rels")):
            continue
        xml = content.decode("utf-8")
        if name.startswith("xl/worksheets/"):
            xml = _NUMERIC_TOKEN_CELL_RE.sub(numeric_cell, xml)
        new = _TOKEN_IN_XML_RE.sub(lambda m: _xml_escape(mapping.get(m.group(0), m.group(0))), xml)
        if new != xml:
            files[name] = new.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in infos:
            target.writestr(info, files[info.filename], compress_type=zipfile.ZIP_DEFLATED)
    return out.getvalue()
