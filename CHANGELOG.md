# Cambios / Changelog

## 0.4.0

### Nombres (el punto más débil)

- Un nombre de pila conocido arrastra hasta dos apellidos fuera de las listas
  («Kevin Arley Mosquera», «Edwin Ararat»).
- Formato de listados `Apellido Apellido, Nombre` → dos entidades («Restrepo Gómez, Juliana»).
- Nombres en minúscula con contexto («me llamo carlos andrés gómez», «gracias camila») o dos
  nombres listados seguidos; se excluyen palabras comunes («tomas el bus», «la rosa»).
- Un solo nombre tras preposición («Saludos a Hernán») o tratamiento («doña Ofelia»).
- Menos falsos positivos: santos y lugares («San Diego», «Santo Tomás»), instituciones en
  cualquier posición («El Hospital Pablo Tobón Uribe», «parque Jaime Duque»), marcas («Juan Valdez»).
- Normalización de palabras en caché: el rendimiento se mantiene pese a la pasada extra.

### Otros

- Cuentas tras el nombre del banco («Bancolombia 24567891234»).
- Cédulas con la palabra clave lejos («la tarjeta de identidad del niño … es la 1.234.567.890»).
- Conjunto **ciego v3** centrado en nombres, escrito antes de los cambios (commit 6c4b5b1):
  F1 0,49 → 0,96 (nombres: recall 0,26 → 0,95). Ciego v2: 0,97 → 0,99.
- Web: escenario de demo «Chat informal», gráfica de evolución por versión y límites actualizados.

## 0.3.0

- **Nuevo nombre: DataShield.** Paquete `datashield-es`, módulo `datashield_es`, comando
  `datashield`. Se usa el sufijo `-es` para no confundirse con DataSHIELD (datashield.org).
- Compatibilidad: `import pii_shield_es` y el comando `pii-shield` siguen funcionando y emiten un
  aviso de obsolescencia; se eliminarán en una versión futura.
- Sin cambios en la detección ni en la API (`detect`, `anonymize`, `PseudonymTable`…).

## 0.2.0

### Seguridad y correcciones

- **Fugas en el modo `mascara`:** los nombres compuestos (`Ana-María`, `O'Neil`) y los nombres
  separados por tabulador o espacio duro (NBSP) quedaban **sin enmascarar**. Ahora se enmascara
  cada parte del nombre respetando cualquier separador.
- **Texto NFD** (tildes descompuestas, típico al copiar de PDF o macOS): rompía la detección de
  nombres (`Juan Camilo Pe`). Ahora se normaliza a NFC internamente y los índices de `Entity`
  siguen apuntando al texto original.
- **Tabla de seudónimos:** escritura atómica (archivo temporal + `os.replace` + `fsync`). Una
  interrupción ya no puede dejar la tabla vacía o corrupta.
- **CLI:** la tabla se guarda **antes** de escribir la salida; si no se puede guardar, no se
  escribe un archivo seudonimizado irreversible. `--min-score` se valida en [0, 1].
- **Teléfonos:** `(320 555 0111` (paréntesis sin cerrar) incluía el paréntesis en la entidad.

### Rendimiento

- Detección lineal en el tamaño del texto: `_is_sentence_start` era O(n) por candidato y
  `resolve_overlaps` era O(n²). Un texto de 624 KB pasa de 6,06 s a 0,88 s (≈7×).
- El CSV ya no se analiza dos veces en `anonimizar`.

### Detección

- Tipos nuevos: `TARJETA_CREDITO` (prefijo de marca + longitud + Luhn), `DIRECCION_IP`
  (IPv4/IPv6 validadas, omite versiones de software y direcciones no personales) y
  `FECHA_NACIMIENTO` (solo con contexto y con fecha real).
- Direcciones: `Kra`, `Ak`, `Ac`, `Tr`, `Cq`; vías con nombre (`Autopista Norte # 152-30`);
  manzana/casa (`Manzana 5 Casa 12 barrio El Prado`).
- Correos ofuscados: `(at)`, `[at]`, `{at}`, ` arroba `.
- Cédula: palabra clave `Doc:`/`Documento` y números agrupados con espacios (`1020 304 050`).
- Placas: contexto con verbo («mi placa es HTR 593») y anti-contexto («clave ABC123»,
  «pedido PED123»).
- Nombres: compuestos con guion, saludos como contexto («Gracias Natalia»), listas ampliadas y
  rechazo de instituciones («Universidad Francisco José de Caldas», «Parque Simón Bolívar»).

### CLI

- `datashield tipos` lista los tipos detectables.
- `datashield detectar --resumen` cuenta por tipo sin mostrar los datos (también con `--json`).

### Evaluación y web

- Conjunto **ciego v2** (`eval/holdout2.txt`), escrito antes de los cambios. v0.1 → v0.2:
  P 0,95 → 1,00 · R 0,67 → 0,95 · F1 0,79 → 0,97. El hold-out v1 se declara «ya no ciego».
- Página `docs/` rediseñada: ilustración, casos de uso, demo con cuatro escenarios reales,
  hoja CSV antes/después, diagrama del proceso, gráficas de métricas y de rendimiento y
  comparativa. Los ejemplos los genera `scripts/build_docs.py` y la gráfica de métricas
  `eval/evaluate.py`; el CI verifica que la web coincida con la librería.

## 0.1.0

- Primera versión: 10 tipos, tres modos de anonimización, CLI, evaluación dev + hold-out.
