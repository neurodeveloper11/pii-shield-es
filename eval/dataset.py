"""Carga y construcción del conjunto de evaluación SINTÉTICO.

Todos los datos son inventados: nombres combinando nombres comunes, documentos y teléfonos
fabricados (patrones tipo 555), dominios reservados (example.com/.org/.net) y números con
dígitos de control calculados por macros. Ninguna muestra proviene de personas reales.

Formato de las fuentes (``dev.txt`` / ``holdout.txt``), una muestra por línea:

* ``[[TIPO|texto]]`` marca una entidad esperada del tipo ``TIPO``.
* Líneas sin marcas son negativos (no debe detectarse nada).
* Líneas vacías o que empiezan con ``#`` se ignoran.
* Macros que calculan dígitos de control válidos (o inválidos a propósito):
  ``{NITDV:900123456}`` -> ``900123456-<dv>``; ``{NITDV.:900123456}`` -> ``900.123.456-<dv>``;
  ``{NITBAD:900123456}`` -> DV incorrecto; ``{IBAN:ES:21000418450200051332}`` -> IBAN
  agrupado de a 4; ``{IBANBAD:ES:...}`` -> IBAN con control incorrecto;
  ``{CLABE:00201007777777777}`` -> 18 dígitos con control válido.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pii_shield_es.validators import clabe_check_digit, iban_check_digits, nit_check_digit

HERE = Path(__file__).parent

_ENTITY_RE = re.compile(r"\[\[([A-Z_]+)\|(.*?)\]\]")
_MACRO_RE = re.compile(r"\{([A-Z.]+):([^}]*)\}")


def _group4(value: str) -> str:
    return " ".join(value[i : i + 4] for i in range(0, len(value), 4))


def _expand_macro(kind: str, arg: str) -> str:
    if kind in {"NITDV", "NITDV."}:
        dv = nit_check_digit(arg)
        base = f"{int(arg):,}".replace(",", ".") if kind == "NITDV." else arg
        return f"{base}-{dv}"
    if kind == "NITBAD":
        return f"{arg}-{(nit_check_digit(arg) + 3) % 10}"
    if kind in {"IBAN", "IBANBAD"}:
        country, bban = arg.split(":")
        check = iban_check_digits(country, bban)
        if kind == "IBANBAD":
            check = f"{(int(check) % 90) + 3:02d}"
        return _group4(f"{country}{check}{bban}")
    if kind == "CLABE":
        return arg + str(clabe_check_digit(arg))
    raise ValueError(f"Macro desconocida: {kind}")


def parse_line(line: str) -> dict[str, object]:
    """Convierte una línea marcada en ``{"text": ..., "entities": [...]}``."""
    expanded = _MACRO_RE.sub(lambda m: _expand_macro(m.group(1), m.group(2)), line)
    entities: list[dict[str, object]] = []
    parts: list[str] = []
    cursor_out = 0
    cursor_in = 0
    for m in _ENTITY_RE.finditer(expanded):
        before = expanded[cursor_in : m.start()]
        parts.append(before)
        cursor_out += len(before)
        value = m.group(2)
        entities.append(
            {"type": m.group(1), "start": cursor_out, "end": cursor_out + len(value), "text": value}
        )
        parts.append(value)
        cursor_out += len(value)
        cursor_in = m.end()
    parts.append(expanded[cursor_in:])
    text = "".join(parts)
    for ent in entities:
        assert text[ent["start"] : ent["end"]] == ent["text"]  # type: ignore[index]
    return {"text": text, "entities": entities}


def load_source(name: str) -> list[dict[str, object]]:
    """Lee ``eval/<name>.txt`` y devuelve las muestras con offsets calculados."""
    samples = []
    for raw in (HERE / f"{name}.txt").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        sample = parse_line(line)
        sample["id"] = f"{name}-{len(samples) + 1:03d}"
        samples.append(sample)
    return samples


def jsonl_path(name: str) -> Path:
    return HERE / f"dataset_{name}.jsonl"


def render_jsonl(name: str) -> str:
    return "".join(json.dumps(sample, ensure_ascii=False) + "\n" for sample in load_source(name))


def load(name: str) -> list[dict[str, object]]:
    """Lee el JSONL generado (el que se evalúa)."""
    return [
        json.loads(line)
        for line in jsonl_path(name).read_text(encoding="utf-8").splitlines()
        if line
    ]


def build(names: tuple[str, ...] = ("dev", "holdout")) -> None:
    for name in names:
        if (HERE / f"{name}.txt").exists():
            jsonl_path(name).write_text(render_jsonl(name), encoding="utf-8")


if __name__ == "__main__":
    build()
