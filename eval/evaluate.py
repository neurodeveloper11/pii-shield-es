"""Mide precisión/recall/F1 por tipo sobre el conjunto sintético y actualiza el README.

Uso:
    python eval/evaluate.py                 # imprime las tablas
    python eval/evaluate.py --update-readme # reescribe el bloque de métricas del README
    python eval/evaluate.py --check         # falla si JSONL o README están desactualizados
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
from pii_shield_es import PIIType, detect

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
START, END = "<!-- METRICS:START -->", "<!-- METRICS:END -->"
SETS = ("dev", "holdout")
SET_LABEL = {
    "dev": "desarrollo / development",
    "holdout": "ciego / blind hold-out",
}


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


def update_readme(block: str) -> bool:
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise SystemExit("README.md no contiene los marcadores de métricas")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    new = head + block + tail
    changed = new != text
    if changed:
        README.write_text(new, encoding="utf-8")
    return changed


def readme_in_sync(block: str) -> bool:
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        return False
    current = START + text.split(START, 1)[1].split(END, 1)[0] + END
    return current.strip() == block.strip()


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
    if args.check:
        if not readme_in_sync(block):
            print(
                "El README no coincide con las métricas medidas. "
                "Ejecuta: python eval/evaluate.py --update-readme",
                file=sys.stderr,
            )
            return 1
        print("OK: dataset y README sincronizados con las métricas medidas.")
        return 0
    print_report(results, show_errors=args.errors)
    if args.json:
        Path(args.json).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.update_readme:
        print("\nREADME actualizado." if update_readme(block) else "\nREADME ya estaba al día.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
