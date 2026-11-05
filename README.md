# DataShield

[![CI](https://github.com/neurodeveloper11/pii-shield-es/actions/workflows/ci.yml/badge.svg)](https://github.com/neurodeveloper11/pii-shield-es/actions/workflows/ci.yml)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)

**ES** — Detecta y anonimiza datos personales en textos en español de Colombia/LatAm. 100 % local: sin llamadas de red, sin APIs externas, sin modelos pesados. · [Ir a Español](#español)

**EN** — Detects and anonymizes personal data (PII) in Colombian/LatAm Spanish text. 100 % local: no network calls, no external APIs, no heavy models. · [Jump to English](#english)

> **Nombre / Name.** Antes se llamaba **pii-shield-es**. Paquete `datashield-es`, módulo `datashield_es`, comando `datashield`. `import pii_shield_es` y el comando `pii-shield` siguen funcionando con un aviso de obsolescencia. No tiene relación con [DataSHIELD](https://www.datashield.org/) (plataforma de análisis federado), de ahí el sufijo `-es`. / Formerly **pii-shield-es**. Package `datashield-es`, module `datashield_es`, command `datashield`; the old import and command still work with a deprecation warning. Unrelated to the DataSHIELD federated-analysis platform, hence the `-es` suffix.

> **Aviso / Notice.** 
> **ES:** esta herramienta es una ayuda técnica heurística. **No sustituye una revisión de cumplimiento** de la Ley 1581 de 2012 (régimen de protección de datos personales / *Habeas Data*) ni asesoría jurídica, y **no garantiza** que todo dato personal sea detectado. Revisa siempre el resultado antes de publicarlo o compartirlo.
> **EN:** this is a heuristic technical aid. It **does not replace a compliance review** under Colombian Law 1581 of 2012 (data protection / *Habeas Data*) nor legal advice, and it **does not guarantee** that all personal data is detected. Always review the output before publishing or sharing it.

---

## Español

### Qué hace

- Detecta: **cédula de ciudadanía**, **cédula de extranjería**, **NIT** (valida el dígito de verificación), **pasaporte**, **teléfonos** colombianos (móvil y fijo, con o sin +57), **correos**, **direcciones** (Calle/Carrera/Diagonal/Transversal/Avenida…), **placas** de vehículo, **cuentas bancarias** (IBAN y CLABE con checksum; cuentas colombianas con contexto), **tarjetas de pago** (marca + Luhn), **direcciones IP** (IPv4/IPv6), **fechas de nacimiento** (con contexto) y **nombres propios** (reglas y listas).
- Tres modos de anonimización: **etiqueta** (`[CEDULA]`), **enmascarado parcial** (`*.***.***.890`) y **seudonimización reversible** con una tabla local opcional.
- **Archivos completos: Word (`.docx`), Excel (`.xlsx`), `.csv`, `.txt` y `.md`**, conservando el formato. En Excel y CSV usa el **encabezado de la columna como contexto** («Cédula», «Celular», «Nombre»…). En Word limpia también encabezados, pies, comentarios, control de cambios y vínculos de correo. Borra los metadatos (autor, empresa, autores de comentarios).
- **Sin instalar nada:** en la [página del proyecto](https://neurodeveloper11.github.io/pii-shield-es/#probar) arrastras el archivo y descargas la versión anonimizada. Se procesa **dentro de tu navegador** (Python en WebAssembly con Pyodide, alojado en el mismo sitio): el archivo no se sube a ningún servidor.
- API de Python (`detect`, `anonymize`, `anonymize_file`) y CLI `datashield`.
- Acepta texto con tildes descompuestas (NFD, típico al copiar de PDF o macOS): se normaliza internamente y los índices siguen apuntando al texto original.
- Escala de forma lineal con el tamaño del texto (≈0,7 MB/s en un núcleo).
- Sin dependencias en tiempo de ejecución. Nada sale de tu máquina.
- Página de presentación con demo y métricas: [`docs/`](docs/index.html) (GitHub Pages).

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
from datashield_es import detect, anonymize, PseudonymTable

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

Archivos completos:

```python
from datashield_es.files import anonymize_file

salida, reporte = anonymize_file("clientes.xlsx")  # escribe clientes_anonimizado.xlsx
print(reporte.conteo)  # {'CEDULA': 4, 'NOMBRE': 5, ...}
print(reporte.metadatos_limpiados)  # ['autor', 'autores de comentarios']
print(reporte.advertencias)  # p. ej., imágenes que no se analizan
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
datashield anonimizar "Mi cédula es 1.023.456.789 y mi correo a@example.com"

# Word y Excel: escribe informe_anonimizado.docx / clientes_anonimizado.xlsx
datashield anonimizar -f informe.docx
datashield anonimizar -f clientes.xlsx -m seudonimo --tabla tabla.json
datashield restaurar -f clientes_anonimizado.xlsx --tabla tabla.json   # -> *_restaurado.xlsx
datashield detectar -f clientes.xlsx            # tipo, hoja!celda o párrafo de cada hallazgo

# Archivos .txt y .csv (por defecto, a stdout; usa -o para escribir un archivo)
datashield anonimizar -f entrevistas.txt -o entrevistas_anon.txt
datashield anonimizar -f clientes.csv --columnas nota,observaciones -m mascara -o clientes_anon.csv

# Desde stdin
cat correo.txt | datashield anonimizar -m etiqueta

# Seudonimización reversible con tabla local
datashield anonimizar -f datos.csv -m seudonimo --tabla tabla.json -o datos_anon.csv
datashield restaurar -f datos_anon.csv --tabla tabla.json -o datos_originales.csv

# Solo detectar (tabla legible o JSON; en CSV incluye fila y columna)
datashield detectar -f clientes.csv --json

# Solo contar por tipo, sin mostrar los datos (útil para auditar un archivo)
datashield detectar -f clientes.csv --resumen

# Listar los tipos que se detectan
datashield tipos
```

Con `--tabla`, la tabla se guarda **antes** de escribir la salida y de forma atómica: si algo falla, no queda un archivo seudonimizado sin su tabla.

En Word y Excel, `--conservar-metadatos` deja el autor y la empresa. Los formatos antiguos `.doc` y `.xls` no se soportan: ábrelos y guárdalos como `.docx`/`.xlsx`.

Opciones comunes: `--tipos CEDULA,NIT,CORREO`, `--min-score 0.8` (entre 0 y 1), `--columnas` (nombres o índices; CSV), `--sin-encabezado`, `--delimitador ";"`. Los comandos también existen en inglés (`anonymize`, `detect`, `restore`). Los archivos se leen como UTF-8. En CSV se procesa cada celda por separado.

### Qué se detecta y cómo se valida

| Tipo | Cómo se detecta | Reduce falsos positivos con |
|---|---|---|
| `CEDULA` | número de 6–10 dígitos (con puntos, espacios o seguidos) tras «cédula», «C.C.», «documento», «Doc:», «tarjeta de identidad», «NUIP»… | exige palabra clave; así no confunde montos como `$1.234.567` |
| `CEDULA_EXTRANJERIA` | 6–7 dígitos tras «cédula de extranjería» / «C.E.» | palabra clave |
| `NIT` | `900.123.456-8` o `900123456-8`; sin DV solo tras «NIT» | **dígito de verificación (DIAN)**; con DV inválido y sin «NIT» se descarta |
| `PASAPORTE` | alfanumérico de 6–9 caracteres tras «pasaporte» | palabra clave |
| `TELEFONO` | móviles `3xx`, fijos con indicativo `(60x)`/`+57 x`, y 7–10 dígitos tras «tel», «PBX»… | límites de dígitos; contexto para números sin indicativo |
| `CORREO` | patrón de correo; también ofuscados (`ana(at)example.com`, `ana arroba example.com`) | — |
| `DIRECCION` | `Calle/Carrera/Kra/Ak/Ac/Diagonal/Transversal… N # N-N` + apto/torre/barrio; vías con nombre (`Autopista Norte # 152-30`); `Manzana 5 Casa 12` | exige la estructura `N # N-N` (o manzana + casa/lote) |
| `PLACA` | carro `ABC123`, moto `ABC12D` | contexto («placa», «mi placa es»…); sin contexto solo formato compacto en mayúsculas, lista de siglas y sin anti-contexto («clave», «código», «pedido»…) |
| `CUENTA_BANCARIA` | IBAN, CLABE y números tras «cuenta de ahorros», «cta»… | **módulo 97 (IBAN)**, **checksum CLABE**, palabra clave |
| `TARJETA_CREDITO` | 13–19 dígitos (agrupados 4-4-4-4, 4-6-5 o seguidos) | **prefijo de marca (IIN) + longitud + Luhn**; puntaje mayor con contexto («tarjeta», «Visa»…) |
| `DIRECCION_IP` | IPv4 e IPv6 | **validación de octetos/grupos**; omite versiones de software («versión 2.10.4.1»), `127.*`, `0.*`, `255.*` y `::1` |
| `FECHA_NACIMIENTO` | `14/03/1957`, `1985-07-22`, «3 de mayo de 1990» tras «fecha de nacimiento», «F. nac.», «nació el»… | exige contexto y una **fecha real** entre 1900 y hoy |
| `NOMBRE` | palabras con mayúscula inicial apoyadas en listas de nombres/apellidos frecuentes y en contexto («señor», «me llamo», «gracias», «a Hernán»…); un nombre de pila conocido arrastra hasta dos apellidos poco comunes (`Kevin Arley Mosquera`); formato `Apellido Apellido, Nombre`; minúsculas con contexto o dos nombres listados (`me llamo carlos andrés gómez`); compuestos (`Ana-María`) | exige lista o contexto; descarta instituciones, santos y lugares («Hospital…», «San Diego», «Santo Tomás»), marcas conocidas y palabras comunes en minúscula («tomas el bus», «la rosa») |

### Limitaciones

Léelas antes de confiar en la herramienta; son importantes.

- **Es una heurística, no un modelo de lenguaje.** Habrá falsos negativos (datos que no detecta) y falsos positivos. Las métricas de abajo vienen de un conjunto sintético pequeño; **no** se pueden extrapolar a tus datos reales.
- **Nombres:** siguen siendo lo más difícil (recall 0,95 en el ciego v3). No se detectan: un nombre de pila ambiguo («Luz», «Rosa») seguido de apellidos fuera de las listas (`Luz Dary Guarín`); un nombre suelto en minúscula sin contexto (`me escribió juan`); y en minúscula solo se incluyen palabras de las listas (`jorge eliécer` queda en `jorge`). Los nombres de figuras públicas (`Carlos Vives`) también se marcan, y una empresa tras «a nombre de» puede marcarse como nombre.
- **Números de identificación sin contexto no se detectan** (por diseño, para no marcar montos o códigos). Una cédula suelta como `1.234.567.890` sin la palabra «cédula» cerca pasa de largo. Si la palabra clave está lejos, solo se cubre la forma «… es (el/la) número» con hasta seis palabras en medio.
- **Teléfonos:** solo formatos colombianos. Los números internacionales no se detectan. Nequi y Daviplata son números de celular (se detectan como `TELEFONO`).
- **Direcciones:** patrón urbano `Vía N # N-N`, vías con nombre seguidas de `#`/`No.` y manzana/casa. No cubre direcciones rurales («vereda…, finca…»), nombres de vía sin `#` ni intersecciones («calle 80 con carrera 30»).
- **Placas:** un código con forma de placa sin contexto (`PED123`) puede marcarse por error; filtra con `min_score=0.8` si prefieres precisión.
- **Cuentas:** las cuentas colombianas no tienen checksum público: se detectan con palabra clave («cuenta», «ahorros»…) o tras el nombre del banco («Bancolombia 24567891234»). El IBAN se valida solo para un subconjunto de países.
- **Tarjetas:** solo marcas con prefijos públicos (Visa, Mastercard, Amex, Diners, Discover, JCB, UnionPay). Una tarjeta escrita con separadores mezclados (`4111 1111-1111 1111`) no se detecta.
- **Fechas de nacimiento:** solo con contexto explícito; una fecha suelta nunca se marca. **IP:** una IPv4 tras «versión»/«v.» se omite a propósito.
- **Correos ofuscados:** se cubren `(at)`, `[at]`, `{at}` y « arroba »; no variantes más creativas («ana punto ruiz en example»).
- **Archivos:** no se analizan imágenes, fotos escaneadas, gráficos ni objetos incrustados (el reporte lo advierte), ni la caché de tablas dinámicas de Excel (actualízalas o elimínalas). Una celda de Excel o CSV se considera del tipo de su columna solo si tiene la forma mínima (dígitos suficientes, una @…); una columna «ID» no se toca. Las celdas con fórmula no se modifican. La herramienta web acepta archivos de hasta 50 MB; para más, usa la CLI.
- **No cubre otros datos personales:** ciudades, nombres de empresas, datos de salud, usuarios de redes sociales, documentos de otros países (CURP, RFC, DNI, RUT…). Un texto «anonimizado» puede seguir permitiendo reidentificar a alguien por el contexto.
- **Acentos:** el texto con tildes descompuestas (NFD) se normaliza internamente; los índices de `Entity` son siempre posiciones de carácter del texto de entrada.
- **Seudonimización:** el mismo valor escrito de dos formas distintas (`1.234.567` vs `1234567`) recibe seudónimos distintos.

### Cumplimiento legal (Ley 1581 de 2012 / Habeas Data)

Anonimizar o seudonimizar texto es una medida técnica útil, pero **cumplir la ley es más que eso**: base legal y autorización del titular, finalidad, información al titular, medidas de seguridad, políticas de tratamiento, atención de consultas y reclamos, registro cuando aplique, transferencias, etc. Esta librería **no ofrece asesoría jurídica ni certifica cumplimiento**. Si tratas datos personales de personas en Colombia, consulta con un profesional del derecho o con tu oficial de protección de datos.

---

## English

### What it does

- Detects: Colombian **ID card (cédula de ciudadanía)**, **foreigner ID (cédula de extranjería)**, **tax ID (NIT, with check-digit validation)**, **passport**, Colombian **phone numbers** (mobile and landline, with or without +57), **emails**, **street addresses** (Calle/Carrera/Diagonal/Transversal/Avenida…), **vehicle plates**, **bank accounts** (IBAN and CLABE with checksum; Colombian accounts with context), **payment cards** (brand + Luhn), **IP addresses** (IPv4/IPv6), **birth dates** (with context) and **proper names** (rules and word lists).
- Three anonymization modes: **label** (`[CEDULA]`), **partial masking** (`*.***.***.890`) and **reversible pseudonymization** with an optional local table.
- **Whole files: Word (`.docx`), Excel (`.xlsx`), `.csv`, `.txt`, `.md`**, keeping the formatting. Spreadsheets use the **column header as context**; Word headers, footers, comments, tracked changes and mail links are cleaned too, plus document metadata (author, company, comment authors).
- **No install needed:** on the [project page](https://neurodeveloper11.github.io/pii-shield-es/#probar) drop a file and download the anonymized version. It runs **inside your browser** (Python on WebAssembly via self-hosted Pyodide); the file is never uploaded.
- Python API (`detect`, `anonymize`, `anonymize_file`) and a `datashield` CLI.
- Handles text with decomposed accents (NFD); offsets always refer to the original input.
- Scales linearly with input size (≈0.7 MB/s on one core).
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
from datashield_es import detect, anonymize, PseudonymTable

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
datashield anonymize "Mi cédula es 1.023.456.789 y mi correo a@example.com"
datashield anonymize -f clients.csv --columnas notes -m mascara -o clients_anon.csv
cat mail.txt | datashield anonymize
datashield anonymize -f data.csv -m seudonimo --tabla tabla.json -o data_anon.csv
datashield restore -f data_anon.csv --tabla tabla.json -o data_original.csv
datashield detect -f clients.csv --json     # in CSV, includes row and column
datashield detect -f clients.csv --resumen  # counts per type only, no data shown
datashield types                            # list the supported types
```

Subcommands also exist in Spanish (`anonimizar`, `detectar`, `restaurar`). Options: `--tipos`, `--min-score`, `--columnas` (names or 0-based indexes; CSV), `--sin-encabezado` (no header row), `--delimitador`. Files are read as UTF-8; each CSV cell is processed independently. The CLI messages are in Spanish.

### Limitations (please read)

- **Heuristics, not a language model.** Expect false negatives and false positives. The metrics below come from a small synthetic set and **cannot** be extrapolated to your real data.
- **Names:** still the hardest part (recall 0.95 on blind v3). Missed: an ambiguous given name ("Luz", "Rosa") followed by unlisted surnames; a lone lowercase name without context; lowercase spans include only listed words. Public figures' names are flagged too.
- **ID numbers without context are not detected** (by design, to avoid flagging amounts and codes). A bare `1.234.567.890` with no nearby keyword is missed.
- **Phones:** Colombian formats only; international numbers are not detected.
- **Addresses:** urban `Street N # N-N`, named roads followed by `#`/`No.`, and block/house; no rural addresses or intersections.
- **Plates:** plate-shaped codes with no context (`PED123`) can be flagged by mistake; use `min_score=0.8` to favor precision.
- **Accounts:** Colombian bank accounts have no public checksum, so they are detected only with a keyword; IBAN is validated only for a subset of countries.
- **Cards:** only brands with public prefixes; mixed separators are not matched. **Birth dates** need explicit context. An IPv4 after "versión"/"v." is skipped on purpose.
- **Files:** images, scanned pages, charts, embedded objects and Excel pivot caches are not analyzed (the report warns). Formula cells are left untouched. The web tool accepts files up to 50 MB.
- **Not covered:** cities, company names, health data, social handles, documents from other countries (CURP, RFC, DNI, RUT…). "Anonymized" text may still allow re-identification from context.
- `Entity` offsets are character indexes into the input, even for NFD text.

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
| TARJETA_CREDITO | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| DIRECCION_IP | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| FECHA_NACIMIENTO | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| NOMBRE | 28 | 28 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| **TOTAL (micro)** | 127 | 127 | 0 | 0 | 1.00 | 1.00 | 1.00 |

**hold-out v1 (ciego en v0.1; usado para diagnóstico en v0.2 / blind in v0.1, used for diagnosis in v0.2)** — 124 muestras / samples, 90 entidades / entities (coincidencia exacta de tipo y rango / exact type+span match)

| Tipo / Type | Soporte / Support | TP | FP | FN | Precisión / Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| CEDULA | 11 | 11 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| CEDULA_EXTRANJERIA | 5 | 5 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| NIT | 7 | 7 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| PASAPORTE | 5 | 4 | 0 | 1 | 1.00 | 0.80 | 0.89 |
| TELEFONO | 11 | 11 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| CORREO | 7 | 7 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| DIRECCION | 10 | 10 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| PLACA | 7 | 7 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| CUENTA_BANCARIA | 6 | 6 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| TARJETA_CREDITO | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| DIRECCION_IP | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| FECHA_NACIMIENTO | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| NOMBRE | 21 | 20 | 1 | 1 | 0.95 | 0.95 | 0.95 |
| **TOTAL (micro)** | 90 | 88 | 1 | 2 | 0.99 | 0.98 | 0.98 |

**ciego v2 / blind hold-out v2** — 89 muestras / samples, 79 entidades / entities (coincidencia exacta de tipo y rango / exact type+span match)

| Tipo / Type | Soporte / Support | TP | FP | FN | Precisión / Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| CEDULA | 6 | 6 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| CEDULA_EXTRANJERIA | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| NIT | 2 | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| PASAPORTE | 1 | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| TELEFONO | 9 | 9 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| CORREO | 7 | 7 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| DIRECCION | 6 | 6 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| PLACA | 4 | 4 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| CUENTA_BANCARIA | 3 | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| TARJETA_CREDITO | 4 | 4 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| DIRECCION_IP | 5 | 5 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| FECHA_NACIMIENTO | 5 | 5 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| NOMBRE | 27 | 26 | 0 | 1 | 1.00 | 0.96 | 0.98 |
| **TOTAL (micro)** | 79 | 78 | 0 | 1 | 1.00 | 0.99 | 0.99 |

**ciego v3, centrado en nombres / blind hold-out v3, name-focused** — 64 muestras / samples, 51 entidades / entities (coincidencia exacta de tipo y rango / exact type+span match)

| Tipo / Type | Soporte / Support | TP | FP | FN | Precisión / Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| CEDULA | 3 | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| CEDULA_EXTRANJERIA | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| NIT | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| PASAPORTE | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| TELEFONO | 3 | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| CORREO | 1 | 1 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| DIRECCION | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| PLACA | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| CUENTA_BANCARIA | 2 | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| TARJETA_CREDITO | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| DIRECCION_IP | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| FECHA_NACIMIENTO | 0 | 0 | 0 | 0 | n/a | n/a | n/a |
| NOMBRE | 42 | 40 | 2 | 2 | 0.95 | 0.95 | 0.95 |
| **TOTAL (micro)** | 51 | 49 | 2 | 2 | 0.96 | 0.96 | 0.96 |

<!-- METRICS:END -->

**Cómo leerlas / How to read them**

- **ES:** *desarrollo* se usó mientras se escribían y ajustaban los detectores, por lo que **sobreestima** el rendimiento. El *hold-out v1* fue ciego para la v0.1, pero sus errores se usaron para diagnosticar la v0.2: **ya no es ciego**. La cifra honesta de la v0.2 es la del *ciego v2*, redactado **antes** de cambiar los detectores (commit `5117975`) e imitando documentos reales (historias clínicas, call center, RR. HH., registros). Con la v0.1 ese mismo conjunto da P 0,96 · R 0,68 · F1 0,80 (sin tarjetas, IP ni fechas de nacimiento). El *ciego v3* se escribió antes de los cambios de la v0.4 (commit `6c4b5b1`) y se centra en nombres (apellidos poco comunes, minúsculas, «Apellido, Nombre») con muchas trampas de falsos positivos; con la v0.3 daba F1 0,49 (nombres: recall 0,26). Sigue siendo pequeño, sintético y escrito por quien escribió los detectores, y los errores de la línea base se vieron antes de implementar. Coincidencia estricta: tipo y rango exactos. Los conteos son pequeños: una o dos muestras mueven mucho los porcentajes.
- **EN:** *development* was used while the detectors were written and tuned, so it **overestimates** performance. *Hold-out v1* was blind for v0.1, but its errors were used to diagnose v0.2: it is **no longer blind**. The honest v0.2 figure is *blind v2*, written **before** changing the detectors (commit `5117975`) and modeled on real documents (medical records, call center, HR, logs). With v0.1 the same set scores P 0.96 · R 0.68 · F1 0.80 (no cards, IPs or birth dates). *Blind v3* was written before the v0.4 changes (commit `6c4b5b1`) and focuses on names, with many false-positive traps; v0.3 scored F1 0.49 on it (names recall 0.26). It is still small, synthetic and authored by the detectors' author, and the baseline errors were seen before implementing. Strict match: exact type and span. Counts are small: one or two samples move the percentages a lot.
- `n/a` = no hay casos (denominador cero) / no cases (zero denominator).
- Reproducir / Reproduce: `python eval/evaluate.py --errors` lista cada falso positivo/negativo / lists every false positive/negative. `python eval/evaluate.py --update-readme` regenera esta tabla; el CI falla si el README no coincide con lo medido / regenerates this table; CI fails if the README does not match what was measured.

## Desarrollo / Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest --cov=datashield_es
python eval/evaluate.py --check      # métricas, README y gráfica de la web
python scripts/build_docs.py --check # ejemplos de la web = salida real de la librería
```

- `src/datashield_es/` — librería / library. `tests/` — pruebas (incluye falsos positivos) / tests (including false positives). `eval/` — conjuntos sintéticos y script de métricas / synthetic sets and metrics script. `docs/` — página web estática (GitHub Pages) / static site; `scripts/build_docs.py` genera sus ejemplos / generates its examples. Historial / history: [CHANGELOG.md](CHANGELOG.md).
- Los datos de `eval/` son inventados: nombres sobre listas de nombres comunes, números ficticios y dominios reservados (`example.com/.org/.net`). Cualquier coincidencia con personas reales es involuntaria. / `eval/` data is fabricated: common-name combinations, fictitious numbers and reserved domains. Any resemblance to real people is unintentional.

## Licencia / License

MIT — ver [LICENSE](LICENSE).
