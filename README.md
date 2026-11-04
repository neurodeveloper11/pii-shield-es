# pii-shield-es

[![CI](https://github.com/neurodeveloper11/pii-shield-es/actions/workflows/ci.yml/badge.svg)](https://github.com/neurodeveloper11/pii-shield-es/actions/workflows/ci.yml)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)

**ES** — Detecta y anonimiza datos personales en textos en español de Colombia/LatAm. 100 % local: sin llamadas de red, sin APIs externas, sin modelos pesados. · [Ir a Español](#español)

**EN** — Detects and anonymizes personal data (PII) in Colombian/LatAm Spanish text. 100 % local: no network calls, no external APIs, no heavy models. · [Jump to English](#english)

> **Aviso / Notice.** 
> **ES:** esta herramienta es una ayuda técnica heurística. **No sustituye una revisión de cumplimiento** de la Ley 1581 de 2012 (régimen de protección de datos personales / *Habeas Data*) ni asesoría jurídica, y **no garantiza** que todo dato personal sea detectado. Revisa siempre el resultado antes de publicarlo o compartirlo.
> **EN:** this is a heuristic technical aid. It **does not replace a compliance review** under Colombian Law 1581 of 2012 (data protection / *Habeas Data*) nor legal advice, and it **does not guarantee** that all personal data is detected. Always review the output before publishing or sharing it.

---

## Español

### Qué hace

- Detecta: **cédula de ciudadanía**, **cédula de extranjería**, **NIT** (valida el dígito de verificación), **pasaporte**, **teléfonos** colombianos (móvil y fijo, con o sin +57), **correos**, **direcciones** (Calle/Carrera/Diagonal/Transversal/Avenida…), **placas** de vehículo, **cuentas bancarias** (IBAN y CLABE con checksum; cuentas colombianas con contexto) y **nombres propios** (reglas y listas).
- Tres modos de anonimización: **etiqueta** (`[CEDULA]`), **enmascarado parcial** (`*.***.***.890`) y **seudonimización reversible** con una tabla local opcional.
- API de Python (`detect`, `anonymize`) y CLI `pii-shield` para texto, `.txt` y `.csv`.
- Sin dependencias en tiempo de ejecución. Nada sale de tu máquina.

### Instalación

Requiere Python 3.10 o superior. Aún no está publicado en PyPI; instálalo desde GitHub:

```bash
pip install "git+https://github.com/neurodeveloper11/pii-shield-es.git"
```

Para desarrollo:

```bash
git clone https://github.com/neurodeveloper11/pii-shield-es.git
cd pii-shield-es
pip install -e ".[dev]"
```

### Uso en Python

```python
from pii_shield_es import detect, anonymize, PseudonymTable

texto = (
    "Hola, soy Juan Camilo Pérez Gómez, C.C. 1.023.456.789. "
    "Vivo en la Carrera 15 # 93-60, Apto 502, Bogotá. "
    "Mi celular es +57 300 123 4567 y mi correo es juan.perez@example.com."
)

for e in detect(texto):
    print(e.type.value, e.start, e.end, round(e.score, 2), e.text)
# NOMBRE 10 33 0.8 Juan Camilo Pérez Gómez
# CEDULA 40 53 0.92 1.023.456.789
# DIRECCION 66 94 0.9 Carrera 15 # 93-60, Apto 502
# TELEFONO 118 134 0.9 +57 300 123 4567
# CORREO 150 172 0.98 juan.perez@example.com

print(anonymize(texto))  # modo="etiqueta" (por defecto)
# Hola, soy [NOMBRE], C.C. [CEDULA]. Vivo en la [DIRECCION], Bogotá. Mi celular es [TELEFONO] y mi correo es [CORREO].

print(anonymize(texto, modo="mascara"))
# Hola, soy J*** C***** P**** G****, C.C. *.***.***.789. Vivo en la Carrera ** # **-**, **** ***, Bogotá. Mi celular es +** *** *** *567 y mi correo es j***@e***.com.

tabla = PseudonymTable()
anon = anonymize(texto, modo="seudonimo", tabla=tabla)
# Hola, soy [NOMBRE_1], C.C. [CEDULA_1]. Vivo en la [DIRECCION_1], Bogotá. Mi celular es [TELEFONO_1] y mi correo es [CORREO_1].
assert tabla.restore(anon) == texto  # reversible con la tabla
tabla.save("tabla.json")  # ¡contiene los datos originales! (permisos 0600)
```

Opciones útiles: `detect(texto, tipos=["CEDULA", "NIT"], min_score=0.8)`; `anonymize_detailed(...)` devuelve además las entidades; `deanonymize(texto, tabla)` revierte.

`score` es una confianza **heurística** (0–1), no una probabilidad calibrada. Las detecciones por contexto explícito («cédula 123…», «NIT 900…») puntúan alto; las que dependen solo del formato (por ejemplo, una placa sin la palabra «placa») puntúan bajo, y puedes filtrarlas con `min_score`.

### Modos de anonimización

| Modo | Resultado | Reversible |
|---|---|---|
| `etiqueta` | `[CEDULA]`, `[CORREO]`… | No |
| `mascara` | conserva formato y pocos caracteres (`*.***.***.789`, `j***@e***.com`, `J*** P****`) | No |
| `seudonimo` | `[CEDULA_1]`, `[NOMBRE_2]`… (mismo valor exacto → mismo seudónimo) | Sí, **solo con la tabla local** |

**Importante sobre la seudonimización:** quien tenga la tabla puede reidentificar a las personas. Los datos seudonimizados siguen siendo, en general, datos personales. Guarda la tabla separada del texto, con acceso restringido y nunca en un repositorio (el `.gitignore` de este proyecto ya excluye `*.tabla.json` y `tabla*.json`). Sin tabla, el modo `seudonimo` mantiene la consistencia dentro de la llamada pero no es recuperable.

### CLI

```bash
# Texto directo
pii-shield anonimizar "Mi cédula es 1.023.456.789 y mi correo a@example.com"

# Archivos .txt y .csv (por defecto, a stdout; usa -o para escribir un archivo)
pii-shield anonimizar -f entrevistas.txt -o entrevistas_anon.txt
pii-shield anonimizar -f clientes.csv --columnas nota,observaciones -m mascara -o clientes_anon.csv

# Desde stdin
cat correo.txt | pii-shield anonimizar -m etiqueta

# Seudonimización reversible con tabla local
pii-shield anonimizar -f datos.csv -m seudonimo --tabla tabla.json -o datos_anon.csv
pii-shield restaurar -f datos_anon.csv --tabla tabla.json -o datos_originales.csv

# Solo detectar (tabla legible o JSON; en CSV incluye fila y columna)
pii-shield detectar -f clientes.csv --json
```

Opciones comunes: `--tipos CEDULA,NIT,CORREO`, `--min-score 0.8`, `--columnas` (nombres o índices; CSV), `--sin-encabezado`, `--delimitador ";"`. Los comandos también existen en inglés (`anonymize`, `detect`, `restore`). Los archivos se leen como UTF-8. En CSV se procesa cada celda por separado.

### Qué se detecta y cómo se valida

| Tipo | Cómo se detecta | Reduce falsos positivos con |
|---|---|---|
| `CEDULA` | número de 6–10 dígitos (con o sin puntos) tras «cédula», «C.C.», «documento de identidad», «tarjeta de identidad», «NUIP»… | exige palabra clave; así no confunde montos como `$1.234.567` |
| `CEDULA_EXTRANJERIA` | 6–7 dígitos tras «cédula de extranjería» / «C.E.» | palabra clave |
| `NIT` | `900.123.456-8` o `900123456-8`; sin DV solo tras «NIT» | **dígito de verificación (DIAN)**; con DV inválido y sin «NIT» se descarta |
| `PASAPORTE` | alfanumérico de 6–9 caracteres tras «pasaporte» | palabra clave |
| `TELEFONO` | móviles `3xx`, fijos con indicativo `(60x)`/`+57 x`, y 7–10 dígitos tras «tel», «PBX»… | límites de dígitos; contexto para números sin indicativo |
| `CORREO` | patrón de correo | — |
| `DIRECCION` | `Calle/Carrera/Diagonal/Transversal/Avenida… N # N-N` + apto/torre/barrio | exige la estructura `N # N-N` |
| `PLACA` | carro `ABC123`, moto `ABC12D` | contexto («placa», «moto»…); sin contexto solo formato compacto en mayúsculas y lista de siglas |
| `CUENTA_BANCARIA` | IBAN, CLABE y números tras «cuenta de ahorros», «cta»… | **módulo 97 (IBAN)**, **checksum CLABE**, palabra clave |
| `NOMBRE` | secuencias de palabras con mayúscula inicial apoyadas en listas de nombres/apellidos frecuentes y en contexto («señor», «nombre:», «me llamo»…) | exige coincidencias en lista o contexto; descarta lugares e instituciones comunes |

### Limitaciones

Léelas antes de confiar en la herramienta; son importantes.

- **Es una heurística, no un modelo de lenguaje.** Habrá falsos negativos (datos que no detecta) y falsos positivos. Las métricas de abajo vienen de un conjunto sintético pequeño; **no** se pueden extrapolar a tus datos reales.
- **Nombres:** las listas son cortas. Un nombre fuera de ellas **solo se detecta si hay contexto** («señor X», «nombre: X», «me llamo X»). No detecta nombres en minúscula, nombres de una sola palabra sin contexto (`Gladys`), ni el formato «Apellido Apellido, Nombre». Puede marcar como nombre una institución que contenga nombres (`Universidad Francisco José de Caldas`) o un nombre de empresa tras «a nombre de».
- **Números de identificación sin contexto no se detectan** (por diseño, para no marcar montos o códigos). Una cédula suelta como `1.234.567.890` sin la palabra «cédula» cerca pasa de largo. Tampoco si entre la palabra clave y el número hay mucho texto («la tarjeta de identidad del menor es la 1.100…»).
- **Teléfonos:** solo formatos colombianos. Los números internacionales no se detectan. Nequi y Daviplata son números de celular (se detectan como `TELEFONO`).
- **Direcciones:** solo el patrón urbano `Vía N # N-N`. No cubre abreviaturas poco comunes (`Kra`), nombres de vía sin número (`Autopista Norte # 152-30`), direcciones rurales ni de manzana/casa (`Manzana 5 Casa 12`), ni intersecciones («calle 80 con carrera 30»).
- **Placas:** un código con forma de placa sin contexto (`PED123`) puede marcarse por error; filtra con `min_score=0.8` si prefieres precisión.
- **Cuentas:** las cuentas colombianas no tienen checksum público: se detectan solo con palabra clave. El IBAN se valida solo para un subconjunto de países. No hay detector de tarjetas de crédito.
- **Correos ofuscados** (`info(at)example.com`) no se detectan.
- **No cubre otros datos personales:** fechas de nacimiento, ciudades, nombres de empresas, datos de salud, direcciones IP, usuarios de redes sociales, documentos de otros países (CURP, RFC, DNI, RUT…). Un texto «anonimizado» puede seguir permitiendo reidentificar a alguien por el contexto.
- **Acentos:** normaliza el texto a NFC (`unicodedata.normalize("NFC", texto)`) si puede venir con tildes descompuestas. Los índices de `Entity` son posiciones de carácter del texto de entrada.
- **Seudonimización:** el mismo valor escrito de dos formas distintas (`1.234.567` vs `1234567`) recibe seudónimos distintos.

### Cumplimiento legal (Ley 1581 de 2012 / Habeas Data)

Anonimizar o seudonimizar texto es una medida técnica útil, pero **cumplir la ley es más que eso**: base legal y autorización del titular, finalidad, información al titular, medidas de seguridad, políticas de tratamiento, atención de consultas y reclamos, registro cuando aplique, transferencias, etc. Esta librería **no ofrece asesoría jurídica ni certifica cumplimiento**. Si tratas datos personales de personas en Colombia, consulta con un profesional del derecho o con tu oficial de protección de datos.

---

## English

### What it does

- Detects: Colombian **ID card (cédula de ciudadanía)**, **foreigner ID (cédula de extranjería)**, **tax ID (NIT, with check-digit validation)**, **passport**, Colombian **phone numbers** (mobile and landline, with or without +57), **emails**, **street addresses** (Calle/Carrera/Diagonal/Transversal/Avenida…), **vehicle plates**, **bank accounts** (IBAN and CLABE with checksum; Colombian accounts with context) and **proper names** (rules and word lists).
- Three anonymization modes: **label** (`[CEDULA]`), **partial masking** (`*.***.***.890`) and **reversible pseudonymization** with an optional local table.
- Python API (`detect`, `anonymize`) and a `pii-shield` CLI for text, `.txt` and `.csv`.
- Zero runtime dependencies. Nothing leaves your machine.

### Installation

Requires Python 3.10+. Not on PyPI yet; install from GitHub:

```bash
pip install "git+https://github.com/neurodeveloper11/pii-shield-es.git"
```

For development:

```bash
git clone https://github.com/neurodeveloper11/pii-shield-es.git
cd pii-shield-es
pip install -e ".[dev]"
```

### Python usage

```python
from pii_shield_es import detect, anonymize, PseudonymTable

text = "Hola, soy Juan Camilo Pérez Gómez, C.C. 1.023.456.789. Mi correo es juan.perez@example.com."

for e in detect(text):  # Entity(type, start, end, text, score)
    print(e.type.value, e.start, e.end, e.text)

anonymize(text)  # mode="etiqueta" (label, default) -> "[NOMBRE]", "[CEDULA]"...
anonymize(text, modo="mascara")  # partial masking
table = PseudonymTable()
anon = anonymize(text, modo="seudonimo", tabla=table)  # "[NOMBRE_1]", "[CEDULA_1]"...
assert table.restore(anon) == text  # reversible only with the local table
table.save("tabla.json")  # contains the ORIGINAL data (file mode 0600)
```

Mode names accept English aliases: `label`, `mask`, `pseudonym`. `detect(text, tipos=["CEDULA", "NIT"], min_score=0.8)` restricts types and filters by confidence. `score` is a **heuristic** confidence (0–1), not a calibrated probability.

**About pseudonymization:** whoever holds the table can re-identify people, and pseudonymized data generally remains personal data. Keep the table separate from the text, access-restricted, and never in a repository (`.gitignore` already excludes `*.tabla.json` and `tabla*.json`).

### CLI

```bash
pii-shield anonymize "Mi cédula es 1.023.456.789 y mi correo a@example.com"
pii-shield anonymize -f clients.csv --columnas notes -m mascara -o clients_anon.csv
cat mail.txt | pii-shield anonymize
pii-shield anonymize -f data.csv -m seudonimo --tabla tabla.json -o data_anon.csv
pii-shield restore -f data_anon.csv --tabla tabla.json -o data_original.csv
pii-shield detect -f clients.csv --json     # in CSV, includes row and column
```

Subcommands also exist in Spanish (`anonimizar`, `detectar`, `restaurar`). Options: `--tipos`, `--min-score`, `--columnas` (names or 0-based indexes; CSV), `--sin-encabezado` (no header row), `--delimitador`. Files are read as UTF-8; each CSV cell is processed independently. The CLI messages are in Spanish.

### Limitations (please read)

- **Heuristics, not a language model.** Expect false negatives and false positives. The metrics below come from a small synthetic set and **cannot** be extrapolated to your real data.
- **Names:** the word lists are short. A name that is not in them is **only detected with context** ("señor X", "nombre: X", "me llamo X"). Lowercase names, single-word names without context, and the "Surname Surname, Given name" format are missed. Institutions containing person names can be flagged by mistake.
- **ID numbers without context are not detected** (by design, to avoid flagging amounts and codes). A bare `1.234.567.890` with no nearby keyword is missed.
- **Phones:** Colombian formats only; international numbers are not detected.
- **Addresses:** only the urban `Street N # N-N` pattern; no rural/block-style addresses, unusual abbreviations (`Kra`), street names without a number, or intersections.
- **Plates:** plate-shaped codes with no context (`PED123`) can be flagged by mistake; use `min_score=0.8` to favor precision.
- **Accounts:** Colombian bank accounts have no public checksum, so they are detected only with a keyword; IBAN is validated only for a subset of countries; no credit-card detector.
- **Obfuscated emails** (`info(at)example.com`) are not detected.
- **Not covered:** dates of birth, cities, company names, health data, IP addresses, social handles, documents from other countries (CURP, RFC, DNI, RUT…). "Anonymized" text may still allow re-identification from context.
- Normalize input to NFC if it may contain decomposed accents. `Entity` offsets are character indexes into the input.

### Legal notice (Law 1581 of 2012 / Habeas Data)

Anonymizing or pseudonymizing text is a useful technical measure, but **legal compliance is much more than that** (lawful basis and data-subject authorization, purpose limitation, privacy notices, security measures, handling policies, queries and complaints, registration where applicable, transfers, etc.). This library provides **no legal advice and certifies no compliance**. If you process personal data of people in Colombia, consult a lawyer or your data protection officer.

---

## Métricas medidas / Measured metrics

Generadas por `python eval/evaluate.py` sobre conjuntos **sintéticos** (todos los datos son inventados; ver `eval/`). / Produced by `python eval/evaluate.py` on **synthetic** sets (all data is fabricated; see `eval/`).

<!-- METRICS:START -->
<!-- Generado por `python eval/evaluate.py --update-readme`. No editar a mano. -->

**desarrollo / development** — 149 muestras / samples, 127 entidades / entities (coincidencia exacta de tipo y rango / exact type+span match)

| Tipo / Type | Soporte / Support | TP | FP | FN | Precisión / Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| CEDULA | 16 | 16 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| CEDULA_EXTRANJERIA | 6 | 6 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| NIT | 10 | 10 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| PASAPORTE | 6 | 6 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| TELEFONO | 20 | 20 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| CORREO | 9 | 9 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| DIRECCION | 13 | 13 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| PLACA | 9 | 9 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| CUENTA_BANCARIA | 10 | 10 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| NOMBRE | 28 | 25 | 0 | 3 | 1.00 | 0.89 | 0.94 |
| **TOTAL (micro)** | 127 | 124 | 0 | 3 | 1.00 | 0.98 | 0.99 |

**ciego / blind hold-out** — 124 muestras / samples, 90 entidades / entities (coincidencia exacta de tipo y rango / exact type+span match)

| Tipo / Type | Soporte / Support | TP | FP | FN | Precisión / Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| CEDULA | 11 | 8 | 0 | 3 | 1.00 | 0.73 | 0.84 |
| CEDULA_EXTRANJERIA | 5 | 5 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| NIT | 7 | 7 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| PASAPORTE | 5 | 4 | 0 | 1 | 1.00 | 0.80 | 0.89 |
| TELEFONO | 11 | 11 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| CORREO | 7 | 6 | 0 | 1 | 1.00 | 0.86 | 0.92 |
| DIRECCION | 10 | 7 | 0 | 3 | 1.00 | 0.70 | 0.82 |
| PLACA | 7 | 7 | 1 | 0 | 0.88 | 1.00 | 0.93 |
| CUENTA_BANCARIA | 6 | 5 | 0 | 1 | 1.00 | 0.83 | 0.91 |
| NOMBRE | 21 | 17 | 2 | 4 | 0.89 | 0.81 | 0.85 |
| **TOTAL (micro)** | 90 | 77 | 3 | 13 | 0.96 | 0.86 | 0.91 |

<!-- METRICS:END -->

**Cómo leerlas / How to read them**

- **ES:** *desarrollo* se usó mientras se escribían y ajustaban los detectores, por lo que **sobreestima** el rendimiento. *Ciego* (hold-out) se redactó **después** de congelar los detectores (commit `e6c853d`) y no se usó para ajustarlos; es la cifra más honesta, pero sigue siendo pequeña, sintética y escrita por la misma persona que escribió los detectores. Incluye a propósito casos difíciles y falsos positivos. Coincidencia estricta: tipo y rango exactos. Los conteos son pequeños: una diferencia de una o dos muestras mueve mucho los porcentajes.
- **EN:** *development* was used while the detectors were written and tuned, so it **overestimates** performance. *Blind hold-out* was written **after** freezing the detectors (commit `e6c853d`) and never used to tune them; it is the more honest figure, but it is still small, synthetic and authored by the same person who wrote the detectors. It deliberately includes hard cases and false-positive bait. Strict match: exact type and span. Counts are small: one or two samples move the percentages a lot.
- `n/a` = no hay casos (denominador cero) / no cases (zero denominator).
- Reproducir / Reproduce: `python eval/evaluate.py --errors` lista cada falso positivo/negativo / lists every false positive/negative. `python eval/evaluate.py --update-readme` regenera esta tabla; el CI falla si el README no coincide con lo medido / regenerates this table; CI fails if the README does not match what was measured.

## Desarrollo / Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest --cov=pii_shield_es
python eval/evaluate.py --check
```

- `src/pii_shield_es/` — librería / library. `tests/` — pruebas (incluye falsos positivos) / tests (including false positives). `eval/` — conjuntos sintéticos y script de métricas / synthetic sets and metrics script. `docs/` — página web estática (GitHub Pages) / static site.
- Los datos de `eval/` son inventados: nombres sobre listas de nombres comunes, números ficticios y dominios reservados (`example.com/.org/.net`). Cualquier coincidencia con personas reales es involuntaria. / `eval/` data is fabricated: common-name combinations, fictitious numbers and reserved domains. Any resemblance to real people is unintentional.

## Licencia / License

MIT — ver [LICENSE](LICENSE).
