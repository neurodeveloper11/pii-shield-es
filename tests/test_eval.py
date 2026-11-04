"""Pruebas del conjunto de evaluación sintético y del script de métricas."""

import sys
from pathlib import Path

import pytest

EVAL = Path(__file__).resolve().parent.parent / "eval"
sys.path.insert(0, str(EVAL))

import dataset  # noqa: E402
import evaluate  # noqa: E402
from datashield_es.validators import is_valid_clabe, is_valid_iban, is_valid_nit  # noqa: E402


def test_parse_line_calcula_offsets():
    sample = dataset.parse_line("Hola [[NOMBRE|Juan Pérez]], cédula [[CEDULA|1.234.567]].")
    assert sample["text"] == "Hola Juan Pérez, cédula 1.234.567."
    ents = sample["entities"]
    assert [(e["type"], sample["text"][e["start"] : e["end"]]) for e in ents] == [
        ("NOMBRE", "Juan Pérez"),
        ("CEDULA", "1.234.567"),
    ]


def test_macros_generan_digitos_de_control_validos_e_invalidos():
    nit = dataset.parse_line("[[NIT|{NITDV.:900123456}]]")["text"]
    base, dv = nit.split("-")
    assert nit.startswith("900.123.456-") and is_valid_nit(base, dv)
    bad = dataset.parse_line("{NITBAD:900123456}")["text"]
    assert not is_valid_nit(*bad.split("-"))
    iban = dataset.parse_line("{IBAN:ES:12345678901234567890}")["text"]
    assert is_valid_iban(iban)
    assert not is_valid_iban(dataset.parse_line("{IBANBAD:ES:12345678901234567890}")["text"])
    assert is_valid_clabe(dataset.parse_line("{CLABE:01218000123456789}")["text"])
    with pytest.raises(ValueError):
        dataset.parse_line("{NOPE:1}")


@pytest.mark.parametrize("name", ["dev", "holdout", "holdout2"])
def test_jsonl_esta_sincronizado_con_la_fuente(name):
    if not (EVAL / f"{name}.txt").exists():
        pytest.skip("conjunto no presente")
    assert dataset.jsonl_path(name).read_text(encoding="utf-8") == dataset.render_jsonl(name)


@pytest.mark.parametrize("name", ["dev", "holdout", "holdout2"])
def test_dataset_bien_formado_y_con_negativos(name):
    if not dataset.jsonl_path(name).exists():
        pytest.skip("conjunto no presente")
    samples = dataset.load(name)
    assert len({s["id"] for s in samples}) == len(samples)
    assert any(not s["entities"] for s in samples), "debe haber muestras negativas"
    tipos = {e["type"] for s in samples for e in s["entities"]}
    assert tipos <= {t.value for t in evaluate.PIIType}
    for s in samples:
        for e in s["entities"]:
            assert s["text"][e["start"] : e["end"]] == e["text"]


def test_dataset_no_contiene_correos_reales():
    # Solo dominios reservados para ejemplos (RFC 2606) o claramente ficticios.
    import re

    for name in ("dev", "holdout", "holdout2"):
        if not dataset.jsonl_path(name).exists():
            continue
        for s in dataset.load(name):
            for m in re.finditer(r"@([A-Za-z0-9._-]+)", s["text"]):
                host = m.group(1).rstrip(".").lower()
                reserved = host.endswith(("example.com", "example.org", "example.net"))
                version_like = re.fullmatch(r"[\d.]+", host) is not None  # p. ej. left-pad@1.3.0
                assert reserved or version_like or host in {"usuario", "usuario_ejemplo"}, host


def test_metricas_sobre_muestras_controladas():
    samples = [
        {
            "id": "a",
            "text": "Cédula 1.234.567 y correo a@example.com",
            "entities": [
                {"type": "CEDULA", "start": 7, "end": 16, "text": "1.234.567"},
                {"type": "CORREO", "start": 26, "end": 39, "text": "a@example.com"},
            ],
        },
        {"id": "b", "text": "Pagó 1 cuenta", "entities": []},
        {  # FN: nombre que no se detecta
            "id": "c",
            "text": "escribió juan perez",
            "entities": [{"type": "NOMBRE", "start": 9, "end": 19, "text": "juan perez"}],
        },
        {  # FP: correo no esperado
            "id": "d",
            "text": "x z@example.com",
            "entities": [],
        },
    ]
    per_type, errors = evaluate.evaluate_samples(samples)
    assert per_type["CEDULA"] == {"tp": 1, "fp": 0, "fn": 0}
    assert per_type["CORREO"]["tp"] == 1 and per_type["CORREO"]["fp"] == 1
    assert per_type["NOMBRE"] == {"tp": 0, "fp": 0, "fn": 1}
    assert {(e["kind"], e["type"]) for e in errors} == {("FP", "CORREO"), ("FN", "NOMBRE")}
    rows = evaluate.summarize(per_type)
    assert rows["CEDULA"]["precision"] == 1.0 and rows["CEDULA"]["recall"] == 1.0
    assert rows["CORREO"]["precision"] == 0.5
    assert rows["NOMBRE"]["recall"] == 0.0 and rows["NOMBRE"]["f1"] == 0.0
    assert rows["NIT"]["precision"] is None and rows["NIT"]["f1"] is None
    total = rows["TOTAL (micro)"]
    assert (total["tp"], total["fp"], total["fn"]) == (2, 1, 1)


def test_coincidencia_laxa_acepta_solapamiento():
    samples = [
        {
            "id": "a",
            "text": "Cédula 1.234.567 fin",
            "entities": [{"type": "CEDULA", "start": 7, "end": 18, "text": "1.234.567 f"}],
        }
    ]
    strict, _ = evaluate.evaluate_samples(samples)
    lenient, _ = evaluate.evaluate_samples(samples, lenient=True)
    assert strict["CEDULA"]["tp"] == 0 and lenient["CEDULA"]["tp"] == 1


def test_markdown_y_readme_roundtrip(tmp_path, monkeypatch):
    readme = tmp_path / "README.md"
    readme.write_text(
        f"antes\n{evaluate.START}\nviejo\n{evaluate.END}\ndespués\n", encoding="utf-8"
    )
    monkeypatch.setattr(evaluate, "README", readme)
    results = evaluate.run()
    block = evaluate.render_block(results)
    assert evaluate.update_readme(block) is True
    assert evaluate.update_readme(block) is False  # idempotente
    assert evaluate.readme_in_sync(block)
    text = readme.read_text(encoding="utf-8")
    assert text.startswith("antes\n") and text.rstrip().endswith("después")
    assert "| Tipo / Type |" in text
    readme.write_text("sin marcadores", encoding="utf-8")
    assert not evaluate.readme_in_sync(block)
    with pytest.raises(SystemExit):
        evaluate.update_readme(block)


def test_main_check_detecta_readme_desactualizado(tmp_path, monkeypatch, capsys):
    readme = tmp_path / "README.md"
    readme.write_text(f"{evaluate.START}\nviejo\n{evaluate.END}\n", encoding="utf-8")
    monkeypatch.setattr(evaluate, "README", readme)
    assert evaluate.main(["--check"]) == 1
    assert "no coincide" in capsys.readouterr().err
    assert evaluate.main(["--update-readme"]) == 0
    capsys.readouterr()
    assert evaluate.main(["--check"]) == 0


def test_main_json_y_errores(tmp_path, capsys):
    out = tmp_path / "r.json"
    assert evaluate.main(["--errors", "--json", str(out)]) == 0
    assert "coincidencia estricta" in capsys.readouterr().out
    assert out.exists() and out.stat().st_size > 0
