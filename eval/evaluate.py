"""Mide precisión/recall/F1 por tipo sobre el conjunto sintético y actualiza el README.

Uso:
    python eval/evaluate.py                 # imprime las tablas
    python eval/evaluate.py --update-readme # reescribe las métricas del README y la gráfica web
    python eval/evaluate.py --check         # falla si JSONL, README o web están desactualizados
    python eval/evaluate.py --json out.json # guarda los resultados

Coincidencia estricta: una predicción es TP solo si tipo, inicio y fin coinciden EXACTAMENTE.
Se reporta también una coincidencia laxa (mismo tipo y solapamiento) a modo de diagnóstico.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import dataset
from datashield_es import PIIType, detect

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
DOCS_INDEX = ROOT / "docs" / "index.html"
START, END = "<!-- METRICS:START -->", "<!-- METRICS:END -->"
CHART_START, CHART_END = "<!-- CHART:START -->", "<!-- CHART:END -->"
SETS = ("dev", "holdout", "holdout2")
SET_LABEL = {
    "dev": "desarrollo / development",
    "holdout": "hold-out v1 (ciego en v0.1; usado para diagnóstico en v0.2 / blind in v0.1, "
    "used for diagnosis in v0.2)",
    "holdout2": "ciego v2 / blind hold-out v2",
}
CHART_SET = "holdout2"


def _counts() -> dict[str, int]:
    return {"tp": 0, "fp": 0, "fn": 0}


def evaluate_samples(samples: list[dict[str, object]], *, lenient: bool = False):
    """Devuelve ``{tipo: {tp, fp, fn}}`` y la lista de errores (para diagnóstico)."""
    per_type: dict[str, dict[str, int]] = defaultdict(_counts)
    errors: list[dict[str, object]] = []
    for sample in samples:
        text = sample["text"]
        gold = [(e["type"], e["start"], e["end"]) for e in sample["entities"]]
        pred = [(e.type.value, e.start, e.end) for e in detect(text)]
        unmatched_gold = list(gold)
        for p in pred:
            hit = None
            for g in unmatched_gold:
                overlaps = g[0] == p[0] and g[1] < p[2] and p[1] < g[2]
                if overlaps if lenient else g == p:
                    hit = g
                    break
            if hit is not None:
                unmatched_gold.remove(hit)
                per_type[p[0]]["tp"] += 1
            else:
                per_type[p[0]]["fp"] += 1
                errors.append(
                    {"id": sample["id"], "kind": "FP", "type": p[0], "text": text[p[1] : p[2]]}
                )
        for g in unmatched_gold:
            per_type[g[0]]["fn"] += 1
            errors.append(
                {"id": sample["id"], "kind": "FN", "type": g[0], "text": text[g[1] : g[2]]}
            )
    return per_type, errors


def _prf(c: dict[str, int]) -> tuple[float | None, float | None, float | None]:
    """Precisión, recall y F1 (``None`` cuando el denominador es 0: «n/a»)."""
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return precision, recall, f1


def summarize(per_type: dict[str, dict[str, int]]) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    total = _counts()
    for tipo in PIIType:
        c = per_type.get(tipo.value, _counts())
        p, r, f = _prf(c)
        rows[tipo.value] = {**c, "precision": p, "recall": r, "f1": f, "support": c["tp"] + c["fn"]}
        for k in total:
            total[k] += c[k]
    p, r, f = _prf(total)
    rows["TOTAL (micro)"] = {
        **total,
        "precision": p,
        "recall": r,
        "f1": f,
        "support": total["tp"] + total["fn"],
    }
    return rows


def _fmt(value: object) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def markdown_table(rows: dict[str, dict[str, object]]) -> str:
    lines = [
        "| Tipo / Type | Soporte / Support | TP | FP | FN | Precisión / Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, r in rows.items():
        bold = "**" if name.startswith("TOTAL") else ""
        lines.append(
            f"| {bold}{name}{bold} | {r['support']} | {r['tp']} | {r['fp']} | {r['fn']} | "
            f"{_fmt(r['precision'])} | {_fmt(r['recall'])} | {_fmt(r['f1'])} |"
        )
    return "\n".join(lines)


def run() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name in SETS:
        if not dataset.jsonl_path(name).exists():
            continue
        samples = dataset.load(name)
        strict, errors = evaluate_samples(samples)
        lenient, _ = evaluate_samples(samples, lenient=True)
        n_entities = sum(len(s["entities"]) for s in samples)
        results[name] = {
            "samples": len(samples),
            "entities": n_entities,
            "strict": summarize(strict),
            "lenient": summarize(lenient),
            "errors": errors,
        }
    return results


def render_block(results: dict[str, Any]) -> str:
    out = [
        START,
        "<!-- Generado por `python eval/evaluate.py --update-readme`. No editar a mano. -->",
        "",
    ]
    for name in SETS:
        if name not in results:
            continue
        data = results[name]
        out.append(
            f"**{SET_LABEL[name]}** — {data['samples']} muestras / samples, "
            f"{data['entities']} entidades / entities "
            "(coincidencia exacta de tipo y rango / exact type+span match)"
        )
        out.append("")
        out.append(markdown_table(data["strict"]))
        out.append("")
    out.append(END)
    return "\n".join(out)


def render_chart(results: dict[str, Any]) -> str:
    """Gráfica SVG (barras horizontales de F1 por tipo) para la web, sin JS ni estilos en línea.

    Los colores salen de clases CSS (``.ch-*``) para respetar el tema claro/oscuro.
    """
    data = results.get(CHART_SET)
    if data is None:
        return f"{CHART_START}\n{CHART_END}"
    rows = [(k, v) for k, v in data["strict"].items() if v["support"]]
    row_h, top, left, width = 30, 34, 170, 330
    height = top + row_h * len(rows) + 8
    out = [
        CHART_START,
        f'<svg class="chart" viewBox="0 0 610 {height}" role="img" '
        f'aria-labelledby="chart-title chart-desc">',
        f'<title id="chart-title">F1 por tipo — {SET_LABEL[CHART_SET]}</title>',
        f'<desc id="chart-desc">{data["samples"]} muestras, {data["entities"]} entidades; '
        "coincidencia exacta de tipo y rango.</desc>",
    ]
    for tick in (0, 0.25, 0.5, 0.75, 1):
        x = left + width * tick
        out.append(
            f'<line class="ch-grid" x1="{x:.0f}" y1="{top - 8}" x2="{x:.0f}" y2="{height - 8}"/>'
            f'<text class="ch-tick" x="{x:.0f}" y="{top - 14}">{tick:.2f}</text>'
        )
    for i, (name, r) in enumerate(rows):
        y = top + i * row_h
        f1 = r["f1"] or 0.0
        total = name.startswith("TOTAL")
        cls = "ch-bar ch-total" if total else "ch-bar"
        label = "TOTAL" if total else name
        out.append(
            f'<text class="ch-label{" ch-strong" if total else ""}" x="{left - 10}" '
            f'y="{y + 15}">{label}</text>'
            f'<rect class="ch-track" x="{left}" y="{y + 3}" width="{width}" height="16" rx="3"/>'
            f'<rect class="{cls}" x="{left}" y="{y + 3}" width="{width * f1:.1f}" height="16" '
            f'rx="3"><title>{label}: F1 {f1:.2f} · P {_fmt(r["precision"])} · '
            f"R {_fmt(r['recall'])} · n={r['support']}</title></rect>"
            f'<text class="ch-value" x="{left + width + 10}" y="{y + 15}">{f1:.2f}</text>'
            f'<text class="ch-n" x="{left + width + 50}" y="{y + 15}">n={r["support"]}</text>'
        )
    out.append("</svg>")
    out.append(CHART_END)
    return "\n".join(out)


def _replace_block(path: Path, start: str, end: str, block: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if start not in text or end not in text:
        raise SystemExit(f"{path.name} no contiene los marcadores {start}")
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    new = head + block + tail
    changed = new != text
    if changed:
        path.write_text(new, encoding="utf-8")
    return changed


def _block_in_sync(path: Path, start: str, end: str, block: str) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if start not in text or end not in text:
        return False
    current = start + text.split(start, 1)[1].split(end, 1)[0] + end
    return current.strip() == block.strip()


def update_readme(block: str) -> bool:
    return _replace_block(README, START, END, block)


def readme_in_sync(block: str) -> bool:
    return _block_in_sync(README, START, END, block)


def update_docs(chart: str) -> bool:
    return _replace_block(DOCS_INDEX, CHART_START, CHART_END, chart)


def docs_in_sync(chart: str) -> bool:
    return _block_in_sync(DOCS_INDEX, CHART_START, CHART_END, chart)


def print_report(results: dict[str, Any], *, show_errors: bool) -> None:
    for name, data in results.items():
        print(
            f"\n== {SET_LABEL[name]}: {data['samples']} muestras, {data['entities']} entidades =="
        )
        print("-- coincidencia estricta --")
        print(markdown_table(data["strict"]))
        print("-- coincidencia laxa (mismo tipo, solapamiento) --")
        print(markdown_table(data["lenient"]))
        if show_errors:
            print("-- errores (estricto) --")
            for err in data["errors"]:
                print(f"  {err['id']} {err['kind']} {err['type']}: {err['text']!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--update-readme", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--errors", action="store_true", help="lista FP/FN")
    parser.add_argument("--json", metavar="ARCHIVO")
    args = parser.parse_args(argv)

    if args.check:
        stale = [
            n
            for n in SETS
            if (dataset.HERE / f"{n}.txt").exists()
            and (
                not dataset.jsonl_path(n).exists()
                or dataset.jsonl_path(n).read_text(encoding="utf-8") != dataset.render_jsonl(n)
            )
        ]
        if stale:
            print(
                f"JSONL desactualizado: {', '.join(stale)}. Ejecuta: python eval/dataset.py",
                file=sys.stderr,
            )
            return 1
    else:
        dataset.build()

    results = run()
    block = render_block(results)
    chart = render_chart(results)
    if args.check:
        if not readme_in_sync(block) or not docs_in_sync(chart):
            print(
                "El README o la gráfica de docs/index.html no coinciden con las métricas "
                "medidas. Ejecuta: python eval/evaluate.py --update-readme",
                file=sys.stderr,
            )
            return 1
        print("OK: dataset, README y web sincronizados con las métricas medidas.")
        return 0
    print_report(results, show_errors=args.errors)
    if args.json:
        Path(args.json).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.update_readme:
        print("\nREADME actualizado." if update_readme(block) else "\nREADME ya estaba al día.")
        print("Web actualizada." if update_docs(chart) else "Web ya estaba al día.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
