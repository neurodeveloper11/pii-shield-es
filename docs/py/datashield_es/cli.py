"""CLI ``datashield``: procesa texto, archivos ``.txt`` y ``.csv`` (todo local)."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .anonymize import MODES, PseudonymTable, anonymize, normalize_mode, replace_entities
from .detectors import detect
from .files import (
    UnsupportedFileError,
    anonymize_bytes,
    default_output_path,
    detect_bytes,
    restore_bytes,
    scan_cell,
)
from .types import PIIType, coerce_types

_AVISO = (
    "datashield-es es una ayuda técnica: no sustituye una revisión de cumplimiento "
    "(Ley 1581 de 2012 / Habeas Data)."
)


class CLIError(Exception):
    """Error de uso: se imprime en stderr y termina con código 2."""


_TYPE_HELP: dict[PIIType, str] = {
    PIIType.CEDULA: "cédula de ciudadanía / tarjeta de identidad (con palabra clave)",
    PIIType.CEDULA_EXTRANJERIA: "cédula de extranjería (con palabra clave)",
    PIIType.NIT: "NIT con dígito de verificación DIAN, o tras «NIT»",
    PIIType.PASAPORTE: "pasaporte (tras «pasaporte»)",
    PIIType.TELEFONO: "celulares y fijos colombianos",
    PIIType.CORREO: "correos electrónicos, también ofuscados («(at)», «arroba»)",
    PIIType.DIRECCION: "direcciones urbanas, vías con nombre y manzana/casa",
    PIIType.PLACA: "placas de carro y moto",
    PIIType.CUENTA_BANCARIA: "IBAN, CLABE y cuentas con palabra clave",
    PIIType.TARJETA_CREDITO: "tarjetas de pago (prefijo de marca + Luhn)",
    PIIType.DIRECCION_IP: "direcciones IPv4 / IPv6",
    PIIType.FECHA_NACIMIENTO: "fechas de nacimiento (con contexto)",
    PIIType.NOMBRE: "nombres propios (listas + contexto)",
}


def _score(value: str) -> float:
    try:
        score = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"no es un número: {value!r}") from None
    if not 0.0 <= score <= 1.0:
        raise argparse.ArgumentTypeError("debe estar entre 0 y 1")
    return score


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datashield",
        description="Detecta y anonimiza datos personales en español (Colombia/LatAm), 100 % local",
        epilog=_AVISO,
    )
    parser.add_argument("--version", action="version", version=f"datashield-es {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMANDO")

    def add_input(p: argparse.ArgumentParser) -> None:
        p.add_argument("texto", nargs="?", help="texto a procesar (si se omite, se lee stdin)")
        p.add_argument(
            "-f",
            "--archivo",
            help="archivo de entrada: .txt, .md, .csv, .tsv, .docx (Word) o .xlsx (Excel)",
        )
        p.add_argument("-o", "--salida", help="archivo de salida (por defecto, stdout)")
        p.add_argument(
            "--tipos",
            help="tipos separados por coma (p. ej. CEDULA,NIT,CORREO). Por defecto, todos",
        )
        p.add_argument(
            "--min-score", type=_score, default=0.0, help="umbral mínimo de confianza (0 a 1)"
        )
        p.add_argument(
            "--columnas",
            help="solo CSV: columnas a procesar (nombres o índices desde 0, separados por coma)",
        )
        p.add_argument(
            "--sin-encabezado", action="store_true", help="solo CSV: sin fila de cabecera"
        )
        p.add_argument("--delimitador", help="solo CSV: delimitador (por defecto se autodetecta)")

    anon = sub.add_parser("anonimizar", aliases=["anonymize"], help="anonimiza el texto")
    add_input(anon)
    anon.add_argument(
        "-m", "--modo", default="etiqueta", choices=MODES, help="modo de anonimización"
    )
    anon.add_argument(
        "--conservar-metadatos",
        action="store_true",
        help="solo .docx/.xlsx: no borrar autor, empresa ni autores de comentarios",
    )
    anon.add_argument(
        "--tabla",
        help="archivo JSON local de seudónimos (modo seudonimo). Se crea o se amplía. "
        "CONTIENE LOS DATOS ORIGINALES: protégelo",
    )

    det = sub.add_parser("detectar", aliases=["detect"], help="lista las entidades detectadas")
    add_input(det)
    det.add_argument("--json", action="store_true", help="salida en JSON")
    det.add_argument(
        "--resumen", action="store_true", help="solo el conteo por tipo (sin mostrar los datos)"
    )

    sub.add_parser("tipos", aliases=["types"], help="lista los tipos de datos que se detectan")

    res = sub.add_parser("restaurar", aliases=["restore"], help="revierte una seudonimización")
    res.add_argument("texto", nargs="?", help="texto seudonimizado (si se omite, se lee stdin)")
    res.add_argument("-f", "--archivo", help="archivo de entrada")
    res.add_argument("-o", "--salida", help="archivo de salida (por defecto, stdout)")
    res.add_argument("--tabla", required=True, help="archivo JSON de seudónimos")
    return parser


# --------------------------------------------------------------------------- E/S


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise CLIError(f"No se pudo leer {path}: {exc.strerror or exc}") from exc
    except UnicodeDecodeError as exc:
        raise CLIError(f"{path} no es UTF-8 válido") from exc


OFFICE = (".docx", ".xlsx")


def _is_office(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "archivo", None)) and Path(args.archivo).suffix.lower() in OFFICE


def _read_bytes(path: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise CLIError(f"No se pudo leer {path}: {exc.strerror or exc}") from exc


def _write_bytes(path: Path, data: bytes) -> None:
    try:
        path.write_bytes(data)
    except OSError as exc:
        raise CLIError(f"No se pudo escribir {path}: {exc.strerror or exc}") from exc


def _load_input(args: argparse.Namespace) -> tuple[str, bool]:
    """Devuelve ``(contenido, es_csv)``."""
    if args.archivo:
        content = _read_text(args.archivo)
        return content, Path(args.archivo).suffix.lower() in (".csv", ".tsv")
    if args.texto is not None and args.texto != "-":
        return args.texto, False
    if sys.stdin.isatty():
        raise CLIError("No hay entrada: pasa un texto, --archivo o redirige stdin")
    return sys.stdin.read(), False


def _write_output(args: argparse.Namespace, content: str) -> None:
    if args.salida:
        try:
            Path(args.salida).write_text(content, encoding="utf-8", newline="")
        except OSError as exc:
            raise CLIError(f"No se pudo escribir {args.salida}: {exc.strerror or exc}") from exc
    else:
        sys.stdout.write(content)
        if content and not content.endswith("\n"):
            sys.stdout.write("\n")


# --------------------------------------------------------------------------- CSV


def _csv_dialect(sample: str, delimiter: str | None) -> type[csv.Dialect] | csv.Dialect:
    if delimiter:
        if len(delimiter) != 1:
            raise CLIError("--delimitador debe ser un solo carácter")

        class _Custom(csv.excel):
            pass

        _Custom.delimiter = delimiter
        return _Custom
    try:
        return csv.Sniffer().sniff(sample[:4096], delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def _selected_columns(spec: str | None, header: list[str] | None, width: int) -> set[int] | None:
    if not spec:
        return None
    chosen: set[int] = set()
    for item in (part.strip() for part in spec.split(",") if part.strip()):
        if header is not None and item in header:
            chosen.add(header.index(item))
        elif item.isdigit() and int(item) < width:
            chosen.add(int(item))
        else:
            raise CLIError(f"Columna no encontrada: {item!r}")
    return chosen


def _read_csv(args: argparse.Namespace, content: str) -> tuple[list[list[str]], csv.Dialect]:
    dialect = _csv_dialect(content, args.delimitador)
    rows = list(csv.reader(io.StringIO(content, newline=""), dialect))
    return rows, dialect  # type: ignore[return-value]


def _write_csv(rows: list[list[str]], dialect: csv.Dialect) -> str:
    buffer = io.StringIO(newline="")
    csv.writer(buffer, dialect).writerows(rows)
    return buffer.getvalue()


def _process_csv(  # type: ignore[no-untyped-def]
    args: argparse.Namespace, rows: list[list[str]], cell_fn
) -> list[list[str]]:
    width = max((len(r) for r in rows), default=0)
    header = None if args.sin_encabezado or not rows else rows[0]
    columns = _selected_columns(args.columnas, header, width)
    out: list[list[str]] = []
    for i, row in enumerate(rows):
        if header is not None and i == 0:
            out.append(row)
            continue
        out.append(
            [
                cell_fn(cell, i, j, header[j] if header is not None and j < len(header) else None)
                if (columns is None or j in columns)
                else cell
                for j, cell in enumerate(row)
            ]
        )
    return out


# --------------------------------------------------------------------------- comandos


def _types(args: argparse.Namespace) -> tuple[PIIType, ...] | None:
    if not args.tipos:
        return None
    try:
        return coerce_types([t for t in args.tipos.split(",") if t.strip()])
    except ValueError as exc:
        raise CLIError(str(exc)) from exc


def _load_table(path: str | None, modo: str) -> PseudonymTable | None:
    if modo != "seudonimo":
        if path:
            raise CLIError("--tabla solo aplica con --modo seudonimo")
        return None
    if not path:
        return None
    if Path(path).exists():
        try:
            return PseudonymTable.load(path)
        except (ValueError, OSError) as exc:
            raise CLIError(f"Tabla inválida {path}: {exc}") from exc
    return PseudonymTable()


def _cmd_anonymize(args: argparse.Namespace) -> int:
    modo = normalize_mode(args.modo)
    tipos = _types(args)
    table = _load_table(args.tabla, modo)
    if modo == "seudonimo" and table is None:
        table = PseudonymTable()
    if _is_office(args):
        return _anonymize_office(args, modo, tipos, table)
    content, is_csv = _load_input(args)

    def run(cell: str) -> str:
        return anonymize(cell, modo, tipos=tipos, tabla=table, min_score=args.min_score)

    def run_cell(cell: str, _i: int, _j: int, head: str | None) -> str:
        ents = scan_cell(cell, head, tipos=tipos, min_score=args.min_score)
        return replace_entities(cell, ents, modo, table) if ents else cell

    if is_csv:
        rows, dialect = _read_csv(args, content)
        result = _write_csv(_process_csv(args, rows, run_cell), dialect)
    else:
        result = run(content)
    # La tabla se guarda ANTES que la salida: si algo falla después, no queda un archivo
    # seudonimizado sin la tabla que permite revertirlo.
    if table is not None and args.tabla:
        try:
            table.save(args.tabla)
        except OSError as exc:
            raise CLIError(f"No se pudo guardar la tabla {args.tabla}: {exc}") from exc
    _write_output(args, result)
    if table is not None and args.tabla:
        print(
            f"Tabla de seudónimos guardada en {args.tabla} ({len(table)} entradas). "
            "Contiene datos originales: protégela.",
            file=sys.stderr,
        )
    return 0


def _anonymize_office(
    args: argparse.Namespace, modo: str, tipos: object, table: PseudonymTable | None
) -> int:
    source = Path(args.archivo)
    try:
        data, report = anonymize_bytes(
            _read_bytes(args.archivo),
            source.name,
            modo,
            tipos=tipos,  # type: ignore[arg-type]
            tabla=table,
            min_score=args.min_score,
            limpiar_metadatos=not args.conservar_metadatos,
        )
    except UnsupportedFileError as exc:
        raise CLIError(str(exc)) from exc
    target = Path(args.salida) if args.salida else default_output_path(source)
    if table is not None and args.tabla:
        try:
            table.save(args.tabla)
        except OSError as exc:
            raise CLIError(f"No se pudo guardar la tabla {args.tabla}: {exc}") from exc
    _write_bytes(target, data)
    resumen = ", ".join(f"{k}={v}" for k, v in report.conteo.items()) or "sin hallazgos"
    print(f"Archivo anonimizado: {target} ({resumen})", file=sys.stderr)
    if report.metadatos_limpiados:
        print(f"Metadatos limpiados: {', '.join(report.metadatos_limpiados)}", file=sys.stderr)
    for warning in report.advertencias:
        print(f"Advertencia: {warning}", file=sys.stderr)
    if table is not None and args.tabla:
        print(
            f"Tabla de seudónimos guardada en {args.tabla} ({len(table)} entradas). "
            "Contiene datos originales: protégela.",
            file=sys.stderr,
        )
    return 0


def _detect_office(args: argparse.Namespace, tipos: object) -> int:
    try:
        report = detect_bytes(
            _read_bytes(args.archivo),
            Path(args.archivo).name,
            tipos=tipos,  # type: ignore[arg-type]
            min_score=args.min_score,
        )
    except UnsupportedFileError as exc:
        raise CLIError(str(exc)) from exc
    if args.resumen:
        if args.json:
            _write_output(args, json.dumps(report.conteo, ensure_ascii=False, indent=2))
        else:
            lines = [f"{k:<20} {v:>6}" for k, v in report.conteo.items()]
            lines.append(f"{'TOTAL':<20} {report.total:>6}")
            _write_output(args, "\n".join(lines))
        return 0
    if args.json:
        _write_output(args, json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0
    lines = [f"{h['tipo']:<20} score={h['score']:.2f}  {h['ubicacion']}" for h in report.hallazgos]
    lines += [f"Advertencia: {w}" for w in report.advertencias]
    lines.append("")
    conteo = ", ".join(f"{k}={v}" for k, v in report.conteo.items())
    lines.append("Total: " + (conteo or "sin hallazgos"))
    _write_output(args, "\n".join(lines))
    return 0


def _cmd_detect(args: argparse.Namespace) -> int:
    tipos = _types(args)
    if _is_office(args):
        return _detect_office(args, tipos)
    content, is_csv = _load_input(args)
    findings: list[dict[str, object]] = []
    if is_csv:

        def collect(cell: str, i: int, j: int, head: str | None) -> str:
            for ent in scan_cell(cell, head, tipos=tipos, min_score=args.min_score):
                findings.append({"fila": i, "columna": j, **ent.to_dict()})
            return cell

        rows, _ = _read_csv(args, content)
        _process_csv(args, rows, collect)
    else:
        findings = [e.to_dict() for e in detect(content, tipos=tipos, min_score=args.min_score)]

    counts = Counter(str(f["type"]) for f in findings)
    if args.resumen:
        summary = {k: counts[k] for k in sorted(counts)}
        if args.json:
            _write_output(args, json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            lines = [f"{k:<20} {v:>6}" for k, v in summary.items()]
            lines.append(f"{'TOTAL':<20} {sum(counts.values()):>6}")
            _write_output(args, "\n".join(lines))
        return 0
    if args.json:
        _write_output(args, json.dumps(findings, ensure_ascii=False, indent=2))
        return 0
    lines = [
        f"{f['type']:<20} {f['start']:>6}-{f['end']:<6} score={f['score']:.2f}  {f['text']}"
        for f in findings
    ]
    lines.append("")
    lines.append(
        "Total: "
        + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) if counts else "sin hallazgos")
    )
    _write_output(args, "\n".join(lines))
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    try:
        table = PseudonymTable.load(args.tabla)
    except (ValueError, OSError) as exc:
        raise CLIError(f"Tabla inválida {args.tabla}: {exc}") from exc
    if args.archivo and Path(args.archivo).suffix.lower() in OFFICE:
        source = Path(args.archivo)
        target = (
            Path(args.salida)
            if args.salida
            else source.with_name(f"{source.stem}_restaurado{source.suffix}")
        )
        try:
            data = restore_bytes(_read_bytes(args.archivo), source.name, table)
        except Exception as exc:  # zip inválido u otro error de formato
            raise CLIError(f"No se pudo restaurar {source}: {exc}") from exc
        _write_bytes(target, data)
        print(f"Archivo restaurado: {target}", file=sys.stderr)
        return 0
    if args.archivo:
        content = _read_text(args.archivo)
    elif args.texto is not None and args.texto != "-":
        content = args.texto
    elif sys.stdin.isatty():
        raise CLIError("No hay entrada: pasa un texto, --archivo o redirige stdin")
    else:
        content = sys.stdin.read()
    _write_output(args, table.restore(content))
    return 0


def _cmd_types(_args: argparse.Namespace) -> int:
    lines = [f"{tipo.value:<20} {_TYPE_HELP[tipo]}" for tipo in PIIType]
    _write_output(argparse.Namespace(salida=None), "\n".join(lines))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "anonimizar": _cmd_anonymize,
        "anonymize": _cmd_anonymize,
        "detectar": _cmd_detect,
        "detect": _cmd_detect,
        "restaurar": _cmd_restore,
        "restore": _cmd_restore,
        "tipos": _cmd_types,
        "types": _cmd_types,
    }
    try:
        return handlers[args.command](args)
    except CLIError as exc:
        print(f"datashield: error: {exc}", file=sys.stderr)
        return 2


def legacy_main(argv: Sequence[str] | None = None) -> int:
    """Comando obsoleto ``pii-shield``: avisa y delega en ``datashield``."""
    print(
        "aviso: el comando «pii-shield» ahora se llama «datashield»; el alias se eliminará "
        "en una versión futura.",
        file=sys.stderr,
    )
    return main(argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
