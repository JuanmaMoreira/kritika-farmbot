# LocalCv: reutilización dentro de un análisis — 2026-10-16

Baseline `eacc47b58acfaadd28a718f14711b5b581b3063c`, rama
`rebuild/stable-baseline`. Trabajo offline `kritika-dev-workflow / fix-and-validate`.

## Diagnóstico actualizado

Se usaron los 22 frames originales (16 focales y seis extranjeros), con dos
pasadas por condición. Los artifacts anteriores y sus informes se preservan.
La instrumentación nueva distingue equivalencia de datos y coincidencia de
`repr(spec)`: identidad completa de spec, assets resueltos, variantes cargadas
ordenadas (shape, dtype y bytes), geometría y píxeles BGR del ROI.

| Baseline / condición | Repeticiones medias | Trabajo repetido medio |
| --- | ---: | ---: |
| Global frío | 13,318 | 54,170 ms |
| Global repetido | 13,318 | 51,533 ms |
| A1 frío | 5 | 13,044 ms |
| A1 caliente | 0 | 0 ms |

Los 16 focales tienen exactamente 13 repeticiones; cinco controles extranjeros
también. Pet Combine extranjero tiene 20. Global no tiene memo entre frames:
“frío/caliente” sólo designa el recorrido; sus variaciones temporales son ruido
real, no hits persistentes. A1 frío se obtiene vaciando sólo su memo existente
fuera del timer; A1 caliente se precalienta con los mismos píxeles.

En 44 llamadas por condición se acumularon 2,383 s repetidos Global frío,
2,267 s Global repetido y 0,574 s A1 frío. A1 caliente no repitió trabajo.
El coste de atribución está instrumentado: no equivale al ahorro del producto.
[Filas](../artifacts/local_cv_reuse_20261016/baseline_rows.json),
[resumen por owner/spec y frame](../artifacts/local_cv_reuse_20261016/baseline_summary.json).

## Identidad y pureza

`LocalCvDetector.measure` valida H×W×3 BGR uint8, recorta según la geometría
actual, convierte a gris, ejecuta `TM_CCOEFF_NORMED` por variante compatible,
toma el máximo y aplica `LinearGapCalibration`. No escribe frame, templates ni
estado propio; el loader sólo interviene durante construcción y cada template
se copia. `LocalCvDetection` es frozen. `detect` crea después las observaciones.

La clave incluye nombre, calibración y ROI del spec completo; no basta igual
nombre, archivo o confidence. Incluye los bytes realmente precargados: dos
loaders distintos para el mismo path no son equivalentes. Se conservan las
variantes y su orden. Las rutas distintas se tratan conservadoramente como
no equivalentes aunque los assets coincidan; BGR distinto también falla la
identidad aunque su gris coincida. Las regiones próximas que redondean al mismo
crop no se unifican. Son misses conservadores, no falsos hits.

La clave no cambia el algoritmo de matching ni sus parámetros. Clases derivadas
de detector/spec/calibración y arrays NumPy derivados no se presuponen puros. Templates privados
malformados pasan por el recorrido original. Los errores nunca se almacenan.
Cada llamada valida su frame antes de consultar la memo; los píxeles del ROI y
los templates se comprueban de nuevo, incluso si un consumidor los mutó durante
la invocación. No se sustituye este chequeo por identidad del objeto ndarray.

## Alcance del mecanismo

La reutilización pertenece a `PerceptionEngine.analyze`. Cada llamada abre su
propio contexto temporal y lo descarta mediante `finally`; la reentrada tiene
otra memo y restaura la exterior. La salida invalida también referencias de
contexto escapadas. No hay memo persistente nueva ni caché de observaciones,
facts, contexto, resolver, snapshot, permisos o datos económicos. Cada `detect`
se ejecuta y conserva orden, confidence, regiones, valores y procedencia.

Los metadatos de `ObservationBatch` se siguen construyendo con el contrato
original. Source, sequence, timestamp, cobertura y freshness no se sintetizan
ni modifican. Los early exits Pets permanecen en su recorrido vigente.

## Reconciliación con los early exits

En los 16 focales, las 26 repeticiones históricas pasan a 13: Low Tier deja de
medir Prompt y sus seis blockers (siete); Epic deja de medir seis blockers.
El control Pet Combine mantiene abierto Low Tier: desaparecen sólo las seis de
Epic y quedan 20. En A1, Low Tier no está inyectado: las seis de Epic explican
el paso de 11 a cinco en frío; en caliente ya no había repeticiones.

Las 13 vigentes Global son Combine tab/animación (dos), title/tab Quests en
Progress/Rows/Loading (seis), Mailbox title (una), Guild tab/Quick Menu (dos),
Summon gate de Epic y Combine gate de Low Tier (dos). En Pets positivos se
agregan los blockers que realmente ejecuta el gate abierto. Full, selectores,
confirmaciones y calibraciones de distinta familia no se agrupan por nombre.
La comparación sintáctica y la identidad conservadora coinciden en los 22
frames vigentes; no se acreditó ahorro por un spec simplemente parecido.
[Desglose por frame y medidas desaparecidas](../artifacts/local_cv_reuse_20261016/early_exit_reconciliation.json).

Los **183,4 ms históricos no son un ahorro incremental vigente** ni se restan a
estos tiempos: proceden de otro código, antes de los gates, y de otra tanda.

## Validación del código final

- **277 tests pasan:** 59 directos (35 nuevos), 100 regresiones de percepción
  Quests/Guild/Pets/early exits/A1 y 118 de scopes/resolver.
- Hay **un fallo heredado**, confirmado usando el engine de Git `eacc47b`:
  `test_pets_manage_navigate_scope_fails_fast` exige un conteo decorativo de 97,
  pero el builder del baseline ya inyecta 101. No se modificó ese test.
  [Comprobación](../artifacts/local_cv_reuse_20261016/baseline_stale_test.json).
- Replay Global: **270 frames únicos**, de los 22 originales y manifiestos
  semantic slice, Pets Summon/Relief, Quests/Mailbox/readiness, Guild y Equipment
  Full. Observaciones completas, ordenadas y resolver completo exactamente
  iguales al oracle de Git. Incluye contextos extranjeros, blockers,
  Combine estable/animación, Full y Pets positivos. Las regresiones del resolver
  cubren bases contradictorias/AMBIGUOUS y overlays con base ambigua; los tests
  del scope Summon conservan el rechazo de contextos extranjeros y ambiguos.
- Replay A1: **66 comparaciones**, incluyendo frío, repetición con array nuevo
  y píxeles XOR modificados. Se conserva también `last_cached_count` exacto.
- **52 comparaciones Global adicionales** contra Git: píxeles XOR, imagen
  invertida y cambios de píxeles entre productores LocalCv y sus consumidores.
  Los resultados completos y el resolver siguen siendo exactamente iguales.
- **11 casos de entrada/geometría** comparados contra Git: ocho ValueError,
  dos errores OpenCV y un retorno normal coinciden, con tipo y argumentos.
- Los tests determinísticos cubren variantes/orden/shape, calibraciones,
  loaders distintos, specs similares, mutación de pixels/templates/spec,
  frames no contiguos, engines paralelos, scopes anidados, reentrada, excepción
  parcial en una variante, cancelación BaseException, emisión inválida,
  calibración derivada con estado y contextos escapados después del cleanup.

[Replay principal](../artifacts/local_cv_reuse_20261016/replay.json),
[replay de píxeles modificados](../artifacts/local_cv_reuse_20261016/modified_replay.json),
[JUnit directos](../artifacts/local_cv_reuse_20261016/tests_direct.xml),
[regresiones](../artifacts/local_cv_reuse_20261016/tests_affected.xml),
[scopes](../artifacts/local_cv_reuse_20261016/tests_scopes.xml).

El primer intento de pytest no pudo crear sus temporales en el sandbox de
Windows (14 errores de setup, sin ejecutar esos casos). Se repitió con
`--basetemp` y cache dentro de artifacts; los 59 directos pasaron.

### Evaluator incremental afectado

Se limitaron las entradas a los mismos 270 frames y los **94 consumidores**
LocalCv: 84 directos y diez especializados que lo contienen. No se evaluaron
Stages, Meteorites, Arena, slots Black Market ni Socket, cuyos algoritmos no
cambiaron, ni se recorrieron todos los manifiestos del corpus.

**25.380 pares por versión, equivalencia exacta**, incluidos scores crudos y
observaciones; una tercera pasada optimizada obtiene 25.380 hits, cero pares
nuevos. El harness incorpora el hash del código compartido de LocalCv/engine/A1
al fingerprint, porque el evaluator estándar no incluye todos los hijos
privados de los especializados. Sus caches original/optimizado son separados.
No se modificó el evaluator productivo.

El evaluator invoca detectores individualmente: valida su contrato sin compartir
entre pares. La ruta de reutilización activa y la agregación/resolución se
comprueban con los replays del engine y los tests anteriores.
[Resultado incremental](../artifacts/local_cv_reuse_20261016/incremental.json).

## A1: ensayo descartado e aislamiento

La primera variante activaba la memo nueva también dentro del wrapper A1.
Se midió en seis vueltas alternadas sobre 22 frames más cuatro positivos:
Global ahorró 33,645 ms medios; **A1 frío perdió 5,640 ms y caliente 5,796 ms**.
El control A/A dio −0,770 ms medios. Se descartó esa activación.
[Datos del ensayo](../artifacts/local_cv_reuse_20261016/candidate_a1_benchmark_summary.json).

A1 conserva su memo especializada sin sembrar ni consultar la nueva. Sólo abre
un contexto suspendido al entrar y restaura el exterior al salir: es necesario
para que un A1 anidado no tome medidas de otra invocación de engine. Su bucle,
comparación gris, cache de observaciones preexistente y `last_cached_count`
permanecen intactos. El test de A1 anidado verifica esta frontera.

La revisión final detectó y corrigió un caso contractual: arrays derivados con
`tobytes` sobrescrito retornaban normalmente en el baseline, pero la primera
clave podía lanzar su excepción. Se comprobó contra Git tanto para frame como
para template de loader custom. Ambos siguen ahora el cálculo original, sin
construir claves; dos regresiones nuevas verifican el retorno y sus matches.
Los replays previos sobre arrays nativos siguen válidos: esa condición no cambia
su recorrido. Se repitieron benchmark y evaluator con los hashes finales.
[Comparación específica contra Git](../artifacts/local_cv_reuse_20261016/array_subclasses.json).

## Benchmark final pareado e intercalado

4 vueltas, 22 frames originales y cuatro positivos Pets. El orden baseline/nuevo se alterna por posición y vuelta (13 parejas por orden en cada vuelta de 26 frames; el balance no se impone por frame); el orden de frames se baraja con seed 20261016 + vuelta. Construcción, lectura, copia del frame y precalentamiento A1 quedan fuera del timer. Cada pareja conserva snapshots y píxeles idénticos. Se ejecutó sin otras validaciones CV en paralelo.

Python 3.12.14, OpenCV 5.0.0, 6 threads OpenCV, optimized=True, OpenCL=True. No se fijaron afinidad, frecuencia CPU ni scheduler de Windows. Metadatos y hashes del código medido se conservan.

Tabla principal: sólo los **22 frames originales × 4 = 88 pares** por condición. Tiempos de pared de `analyze`, en ms; Δ es baseline − nuevo medido por pareja.

| Condición | Baseline mediana / media / p95 | Nuevo mediana / media / p95 | Δ medio pareado |
| --- | ---: | ---: | ---: |
| Global | 472.979 / 467.360 / 537.023 | 446.420 / 443.016 / 489.435 | 24.344 |
| A1 frío | 396.722 / 400.249 / 463.424 | 394.958 / 399.613 / 458.894 | 0.635 |
| A1 caliente | 131.577 / 129.978 / 142.624 | 131.828 / 129.906 / 142.101 | 0.072 |
| Scope slot, sin repeticiones | 18.906 / 19.037 / 20.613 | 19.174 / 19.429 / 20.720 | -0.392 |

Global mejora **24.344 ms/análisis (5.21 % incremental sobre eacc47b)**. Intervalo bootstrap descriptivo 95 % por bloques de frame: 16.800..33.326 ms. No es un intervalo de ahorro físico en gameplay.

| Subconjunto Global | Pares | Δ medio | Δ mediano | p95 del Δ | Parejas con pérdida |
| --- | ---: | ---: | ---: | ---: | ---: |
| 16 focales | 64 | 22.758 | 23.101 | 52.567 | 7 |
| 6 extranjeros | 24 | 28.575 | 29.968 | 100.558 | 2 |
| 4 positivos Pets | 16 | 71.493 | 65.389 | 105.858 | 0 |
| 4 boards | 16 | 27.738 | 24.390 | 58.489 | 1 |

Control **A/A: 36 pares**, dos engines baseline, nueve frames muestreados y cuatro vueltas con orden equilibrado. Δ medio -0.472 ms, mediano 0.168 ms, p95 11.870 ms; 18 pares negativos. Los outliers y deltas por frame permanecen en las muestras crudas. Los cambios temporales A1 no se acreditan como ahorro algorítmico: evitan cero mediciones nuevas.

### Trabajo evitado y coste de la memo

Conteo instrumentado separado del benchmark limpio, una pasada por cada frame/condición. `matchTemplate` incluye todos los consumidores del engine; la diferencia identifica las llamadas realmente eliminadas.

| Condición / grupo | Medidas evitadas por análisis | matchTemplate evitados | Clave nueva, ms medios | Resto de measure fuera de matching, ms medios |
| --- | ---: | ---: | ---: | ---: |
| Global focal | 13.000 | 19.000 | 11.975 | 12.768 |
| Global extranjero | 14.167 | 20.167 | 13.382 | 15.276 |
| Global positivo | 19.500 | 25.500 | 15.801 | 19.038 |
| A1 frío focal | 0.000 | 0.000 | 0.000 | 0.687 |
| A1 caliente focal | 0.000 | 0.000 | 0.000 | 0.093 |
| Slot sin repeticiones | 0.000 | 0.000 | 0.430 | 0.358 |
| 84 LocalCv únicos, control sintético | 0.000 | 0.000 | 10.345 | 11.638 |

La construcción de clave copia bytes de templates/crop; el resto incluye hash, lookup, validación y coste de los spies. Esta atribución no incluye entrada/salida del contexto ni es una resta exacta de overhead original. El ahorro neto fiable es el benchmark pareado completo; la columna de clave explica por qué el trabajo redundante bruto no se convierte íntegramente en ahorro.

Sin reutilización, el scope slot evita cero matches y su Δ pareado es -0.392 ms (mediana -0.435 ms). El control sintético de 84 LocalCv únicos muestra también el coste de preparar claves para medidas sin segundo consumidor; su tiempo instrumentado no sustituye un benchmark productivo. Los scopes pequeños pueden pagar overhead sin ganar trabajo. No se añadieron reglas de exclusión por contexto ni se cambió la selección de detectores.

### Cuatro cantidades distintas

1. **Trabajo redundante previo vigente:** 13 medidas / 50,332 ms medios Global focal frío; A1 frío cinco / 12,787 ms, caliente cero. Son tiempos instrumentados del baseline, antes de activar la reutilización.
2. **Ahorro neto nuevo:** 24.344 ms medios Global sobre los 22 originales; incluye overhead, preserva los early exits y no se suma al 18,9 % histórico de Pets.
3. **Potencial de campaña:** los 368 análisis globales de reacreditación en 184 boards documentados anteriormente darían **10.208 s hipotéticos** usando 27.738 ms medios incrementales del subconjunto board actual. Exige igual frecuencia y distribución; no se aplica el delta Global a los 20.044 análisis mezclados de aquella campaña, cuyo total Global es desconocido.
4. **Ahorro físico incremental:** todavía **no acreditado**. No hubo teléfono, gameplay, Session productiva ni nueva campaña. Captura, OCR del reader, resolver, espera y transporte están fuera del timer; este resultado no acredita reducir en igual proporción el tiempo total de campaña.

[Muestras pareadas](../artifacts/local_cv_reuse_20261016/benchmark_rows.jsonl), [resumen](../artifacts/local_cv_reuse_20261016/benchmark_summary.json), [entorno y fuentes](../artifacts/local_cv_reuse_20261016/benchmark_metadata.json), [conteos y overhead](../artifacts/local_cv_reuse_20261016/counts.json).

## Reproducción, archivos y cierre

Desde la raíz, con el Python indicado en AGENT_LOCAL:

```powershell
.\.venv\Scripts\python.exe -m artifacts.local_cv_reuse_20261016.prepare
.\.venv\Scripts\python.exe -m artifacts.local_cv_reuse_20261016.profile
.\.venv\Scripts\python.exe -m artifacts.local_cv_reuse_20261016.compare replay
.\.venv\Scripts\python.exe -m artifacts.local_cv_reuse_20261016.modified_replay
.\.venv\Scripts\python.exe -m artifacts.local_cv_reuse_20261016.compare incremental
.\.venv\Scripts\python.exe -m artifacts.local_cv_reuse_20261016.compare benchmark --rounds 4
.\.venv\Scripts\python.exe -m artifacts.local_cv_reuse_20261016.counts
.\.venv\Scripts\python.exe -m artifacts.local_cv_reuse_20261016.render
.\.venv\Scripts\python.exe -m pytest tests/test_local_cv_measurement_reuse.py tests/test_perception_engine.py tests/test_local_cv_perception.py -q --basetemp artifacts/local_cv_reuse_20261016/pytest_tmp_reproduce -o cache_dir=artifacts/local_cv_reuse_20261016/pytest_cache
```

Cambios runtime: `bot/perception/local_cv.py` (medidas temporales), `bot/perception/engine.py` (lifetime por invocación) y `bot/monster_wave_board_perception.py` (aislamiento sin activación). Nuevos: `tests/test_local_cv_measurement_reuse.py` y este informe. Scripts, oracles y salidas viven en `artifacts/local_cv_reuse_20261016/`, ignorado por Git.

Estado al medir: rama `rebuild/stable-baseline`, HEAD `eacc47b58acfaadd28a718f14711b5b581b3063c`, antes de staging, commit y push. Se preservan los informes de profiling/Pets/board, artifacts anteriores y `tools/loading_central_acquisition.py` untracked; la comprobación de hashes de esa etapa está en [preservation_after.json](../artifacts/local_cv_reuse_20261016/preservation_after.json). No se modificaron OCR, navegación, economía, Session, resolver, políticas ni la selección de detectores/scopes.

Decisión: conservar la optimización acotada a PerceptionEngine por su beneficio Global medido; descartar su activación A1. El coste de preparar claves sin reutilización y la falta de una campaña física son los límites de esta aceptación offline.

### Revisión final para publicación — 2026-10-16

Se revisaron los tres archivos runtime, los tests y este informe. Los hashes de
runtime y tests coinciden exactamente con los del benchmark aprobado; se
reutilizan los 277 tests, replays, 25.380 pares por versión del evaluator y
benchmark pareado, sin repetir trabajo que siga válido. Los oracles guardados
coinciden con Git `eacc47b`; el builder, el test heredado 97/101 y los early exits
Pets permanecen idénticos al baseline. El fallo heredado está reproducido en el
JUnit original y no lo introduce esta optimización.

El cierre autorizado comprende staging selectivo de estos cinco archivos,
`git diff --cached --check`, un único commit y push normal a
`origin/rebuild/stable-baseline`, con comprobación posterior de HEAD remoto,
upstream, ahead/behind 0/0 e INDEX limpio. Los artifacts, profiling histórico,
logs y capturador HIL quedan fuera del commit. Esta publicación mantiene la
aceptación exclusivamente offline: 24,3 ms / 5,21 % incrementales, sin
extrapolación automática a las 20.044 percepciones históricas ni ahorro físico
acreditado. La campaña 28/28 con `full-live-ownership` queda para el próximo
trabajo; no se inicia hardware ni Session durante este cierre.
