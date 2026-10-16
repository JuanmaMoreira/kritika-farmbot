# Pets early exits — implementación y comparación offline, 2026-10-16

Rama `rebuild/stable-baseline`, HEAD `8ab0ff6ce78d2bf0e5a6d30641a60f11e5bc05ad`.
Modalidad `kritika-dev-workflow / fix-and-validate`. Cambios sin commit/push.
El [profiling original](PERCEPTION_ENGINE_FOCAL_PROFILE.md) y el
[resultado negativo de reacreditación MW](MW_BOARD_REACCREDITATION_PERFORMANCE.md)
se conservan intactos como procedencia anterior a este cambio.

## Cambio exacto

Sólo dos detectores productivos:

- `PetLowTierCandidateDetector.detect`: mide Combine una vez. Con confianza
  **<0,8**, ninguna confianza de candidato puede alcanzar 0,8 por la fórmula
  `min(combine, prompt)` seguida de `min(gate, normal/rare)`. Sobre geometría
  compatible devuelve `()` antes de Prompt, seis blockers, HSV completo y slots.
- `PetEpicAvailabilityDetector.detect`: mide Summon una vez. Con confianza
  **<confidence_threshold** (0,8 vigente), ninguna de las dos disponibilidades
  puede alcanzar el umbral por `min(gate, calibration)`. Sobre geometría
  compatible devuelve `()` antes de seis blockers y procesamiento de tarjeta.

No se declara ausencia física de Pets ni se añade una observación negativa.
Con gate exactamente 0,8 o superior se ejecuta el cálculo completo, en su orden
anterior, conservando blockers, tier, colores, márgenes y disponibilidad.

El sufijo del cálculo original vive en dos métodos privados locales,
`_measure_slots(frame, combine)` y `_measure_card(frame, summon)`. Tanto
`measure` como `detect` reutilizan ese sufijo. El resultado del primer gate se
pasa como argumento: no se vuelve a medir en el camino positivo. La API
diagnóstica `measure` sigue ejecutando todo incluso cuando el gate es bajo;
sus tipos, campos y valores no cambian.

Un gate bajo no debe ocultar un error posterior. Antes del early exit se
comprueba, usando `frame.shape` y `relative_region_to_pixels`, si al menos una
variante de cada template pendiente cabe en su ROI y si los crops de color no
están vacíos. Si no se puede aplicar el atajo, se conserva el recorrido original
restante y su excepción. La comprobación geométrica no se ejecuta en el camino
admitido y no hace matching ni convierte colores.

Engine, otros detectores, scopes, resolver, guards, owners y política de input
permanecen sin cambios. Low Tier no está en A1; sólo Epic puede beneficiarlo.

## Equivalencia y validación

**117 tests afectados pasan:** 59 nuevos + 58 regresiones existentes. Los nuevos
protegen los umbrales inmediatos inferior/superior y exactamente 0,8, candidatos
Normal/Rare con colores adversariales, ambos estados Epic, los seis blockers
de cada detector, Prompt, lectura diagnóstica y errores de geometría. Incluyen
el caso crítico donde el primer template sí cabe, el gate es bajo y uno posterior
no cabe; también variantes compatibles junto a una demasiado grande y ninguna
variante compatible. En ramas admitidas, spies verifican una sola medición de
cada gate y el cálculo de todos los blockers.

Los tests existentes cubren Pets Summon, Pets Relief, el flow de relief,
el scope de adquisición de board y LocalCv. Incluyen los candidatos reales
Normal/Rare, color ambiguo, mass evolve, resultados, disponibilidad y modales.
[JUnit de regresiones](../artifacts/pet_early_exits_20261016/tests_affected.xml).
La primera ejecución unitaria sólo emitió un warning por `.pytest_cache` sin
permiso; no afectó sus 59 resultados. Las regresiones usaron un cache local
en artifacts.

Replay independiente contra **fuentes originales obtenidas de Git 8ab0ff6**,
no un oracle reescrito con el algoritmo optimizado:

- **85 frames únicos:** 22 del profiling + 64 de los manifiestos Pets, con un
  frame común. Observaciones completas y ordenadas, confianza, valores/regiones,
  procedencia y resultado completo del resolver son exactamente iguales.
- Los **64 frames Pets** también cumplen su GT curado de BASE, overlays y
  observaciones requeridas, con todos los detectores globales presentes.
- **170 comparaciones diagnósticas** (85 × 2) conservan todos los campos exactos
  de `measure`, incluidos los gates cerrados y los positivos reales.
- **64 comparaciones adicionales** sobre entradas malformadas y tamaños:
  coinciden 52 `ValueError`, cuatro errores OpenCV y ocho retornos normales,
  incluyendo argumentos/mensaje de excepción. Ocho comparaciones de vistas
  no contiguas/reducidas también coinciden.
- **10 comparaciones de construcción** conservan los errores de assets ausentes,
  imágenes indecodificables, vacías, con canales o dtype incompatibles.

[Replay detallado](../artifacts/pet_early_exits_20261016/replay.json).
Los inputs conservan sus hashes; no se reetiquetaron capturas por un miss.

### Evaluator incremental limitado a Pets

Se evaluaron sólo los dos detectores afectados sobre los 64 frames Pets:
**128 pares originales y 128 optimizados, equivalencia exacta**; la repetición
optimizada reutilizó **128 hits / cero pares nuevos**. Se usa la API existente
`evaluate_detector_frame_pairs`, con cache independiente en artifacts.
[Resultado incremental](../artifacts/pet_early_exits_20261016/incremental.json).

El CLI legacy `tools.production_perception_evaluation` falló en el intento
original limitado a esos mismos manifiestos con
`ValueError: Unsupported production detector: landmark.trading_center_title`.
Es una limitación ajena a estos dos detectores; no se corrigió el evaluator ni
se amplió el corpus. La API incremental da la comparación por pares, y el replay
anterior comprueba separadamente el resolver global contra el GT Pets.

## Metodología del benchmark

Comparación en el mismo proceso entre las clases originales preservadas desde
Git y las clases del working tree. Se inyectan en la misma posición de los
engines actuales, sin cambiar ningún otro detector. Para A1 se selecciona el
scope productivo antes de sustituir las clases y se usa su memo existente.

Entradas: los 22 frames originales (16 focales y seis extranjeros), más cuatro
positivos reales: Low Tier Normal/Rare y Epic available/unavailable. Decode y
copias quedan fuera del timer. Cada análisis recibe nuevo snapshot con sequence,
timestamp y source explícitos. Se exige firma exacta de observaciones en todas
las repeticiones y versiones.

Seis rondas por frame, con orden pseudoaleatorio reproducible y versiones
intercaladas original→optimizado / optimizado→original. Se miden global, A1
alternado y A1 con la memo caliente sobre píxeles repetidos. Ambas versiones
se precalientan de igual forma. También se mide cada detector por separado;
sus dos positivos propios se separan de los negativos focales. En un frame
positivo de un detector el otro puede seguir ahorrando: por eso el tiempo global
de “positivos” no acredita una mejora de la rama positiva individual.

Latencia sin instrumentar `cv2` ni `LocalCv.measure`. El conteo de operaciones
se ejecuta aparte sobre las mismas entradas, con estado de memo controlado.
Control A/A: 16 parejas original-original con el mismo harness, etiquetas de
versión y orden intercalado. Un detector vacío permite medir el piso del timer
y dispatch del harness; copia/hash/serialización no forman parte del intervalo.

Las diferencias se calculan por pareja, no restando p95. Se conserva la
variabilidad por frame y se calcula un intervalo exploratorio por bootstrap
sobre las medias de frame (5.000 remuestreos, seed fija). No se consideran las
repeticiones como nuevas capturas físicas independientes. CPU/scheduling y
las cachés internas de OpenCV no están aislados.

## Ahorro neto medido

Sobre los **22 frames originales**, 132 parejas por motor (seis por frame).
Ms de pared; todos los timers incluyen el nuevo control geométrico y el resto
del engine. El ahorro medio es la diferencia **pareada** original−optimizado.

| Motor / estado | p50 original → optimizado | Media original → optimizado | p95 original → optimizado | Ahorro medio | Reducción media |
| --- | --- | --- | --- | ---: | ---: |
| Global | 567,29 → 461,36 | 571,49 → 463,71 | 609,77 → 506,50 | **107,77 ms** | **18,86%** |
| A1 alternado | 413,16 → 375,76 | 418,61 → 381,61 | 449,30 → 433,00 | **37,00 ms** | **8,84%** |
| A1 caliente, mismos píxeles | 158,63 → 122,18 | 158,19 → 121,48 | 172,39 → 133,95 | **36,70 ms** | **23,20%** |

En los **16 frames focales** aislados, global baja de 569,79 a 458,78 ms medios:
**111,01 ms netos / 19,48%**; medianas 565,41 → 457,54 y p95 609,04 → 492,26.
En los seis controles extranjeros, el ahorro medio es 99,13 ms; se conserva
el resultado original de todos sus detectores y el resolver.

Variabilidad y control:

- Global: **132/132 parejas** mejoran; ahorro mediano 112,35 ms,
  desviación 18,83 ms, rango 29,73..133,80 ms. IC exploratorio de la media
  agrupado por frame: **99,63..112,65 ms**. Las seis rondas dan ahorros medios
  105,31 / 111,69 / 113,77 / 105,56 / 105,73 / 104,56 ms.
- A1 alternado: **127/132** mejoran; ahorro mediano 37,49 ms, desviación
  17,02 ms, IC 34,42..39,56 ms. Hay cinco parejas donde la versión optimizada
  tarda más; no se promete una mejora de cada llamada bajo scheduling arbitrario.
- A1 caliente: **132/132** mejoran; ahorro mediano 36,27 ms, desviación 3,82 ms,
  IC 36,04..37,31 ms. Ambas versiones tienen **81 hits** en todos los frames
  originales; el beneficio es Epic, no una modificación de la memo LocalCv.
- A/A global, 16 parejas: ahorro aparente medio 12,28 ms, mediano 0,63 ms,
  desviación 27,95 ms y rango −14,56..101,10 ms. Un outlier puede fabricar una
  diferencia grande aislada. La ganancia global A/B supera ese control y es
  consistente en todas las rondas; la cola de A1 alternado conserva ruido.
- Piso del harness, 1.000 parejas vacías: aproximadamente **0,002 ms** por
  llamada, p95 0,003 ms. Copia, firma y JSON quedan fuera del timer. No se resta
  A/A como si fuera un overhead fijo, ni se mezclan sus outliers con coste de código.

Se guardaron **3.592 intervalos** en la serie principal: 968 análisis de engine
(incluidos 32 del A/A), 624 llamadas individuales y 2.000 llamadas vacías.
Los warmups y conteos separados son adicionales y no integran esos timers.

[Tabla completa y variación por frame](../artifacts/pet_early_exits_20261016/MEASUREMENTS.md),
[muestras crudas](../artifacts/pet_early_exits_20261016/benchmark_samples.jsonl),
[resumen numérico](../artifacts/pet_early_exits_20261016/benchmark_summary.json),
[entorno y diff medido](../artifacts/pet_early_exits_20261016/benchmark_metadata.json).
Entorno: Python 3.12.14, OpenCV 5.0.0, NumPy 2.5.2, Windows 11, seis threads
OpenCV; no se cambia configuración de threads/optimización entre versiones.

### Tiempo individual y ramas admitidas

Primera serie individual: negativos focales, **96 parejas por detector**;
positivos propios, **12 parejas por detector**. Valores media / p50 / p95, ms.

| Detector / gate | Original | Optimizado | Ahorro medio pareado |
| --- | --- | --- | ---: |
| Low Tier cerrado | 78,19 / 73,53 / 97,42 | 1,15 / 1,10 / 1,37 | **77,04 ms** |
| Epic cerrado | 37,53 / 36,38 / 43,28 | 1,08 / 1,02 / 1,29 | **36,45 ms** |
| Low Tier abierto, Normal/Rare | 76,10 / 74,49 / 84,76 | 76,74 / 74,28 / 85,59 | −0,63 ms |
| Epic abierto, available/unavailable | 37,71 / 37,02 / 41,34 | 37,88 / 37,16 / 41,78 | −0,18 ms |

La diferencia submilisegundo de los positivos justificó repetir **sólo esos
cuatro frames**, sin repetir el resto del benchmark ni cambiar código:
32 parejas por frame con orden exactamente equilibrado, **64 A/B por detector**;
control **32 A/A por detector**. Son 384 llamadas individuales suplementarias.

| Positivo, repetición equilibrada | Media original → optimizado | p50 original → optimizado | p95 original → optimizado | Ahorro medio / mediano |
| --- | --- | --- | --- | --- |
| Low Tier | 63,27 → 64,14 | 62,70 → 63,08 | 67,98 → 67,95 | −0,87 / −0,44 ms |
| Epic | 31,82 → 32,16 | 31,10 → 31,42 | 36,98 → 37,55 | −0,34 / −0,41 ms |

En Low Tier, un outlier optimizado aporta 43,34 ms de penalización pareada;
la desviación A/B es 5,73 ms y la A/A 1,39 ms. Epic tiene desviación A/B
1,61 ms y A/A 1,16 ms. Los controles A/A producen diferencias medias aparentes
de +0,34 y +0,16 ms respectivamente, sin cambio de código. Los tiempos absolutos
también varían entre fases: sólo comparar versiones dentro de su serie pareada.

**No se demuestra una mejora del camino abierto ni una regresión separable del
ruido en estos datos.** Se reportan las diferencias observadas sin ocultarlas.
Sí se demuestra que el camino abierto no añade mediciones: primer gate una vez,
mismos 8/7 matches y cálculo completo. La muestra física de positivos sigue
siendo dos frames por detector; 64 repeticiones no la convierten en 64 escenas.
[Suplemento positivo reproducible](../artifacts/pet_early_exits_20261016/positive_followup.json).

### Matches efectivamente evitados

Conteo ejecutado aparte, no inferido a partir de timers:

| Caso | Original → optimizado | Evitados |
| --- | --- | ---: |
| Low Tier, gate cerrado compatible | 8 → 1 | **7** |
| Epic, gate cerrado compatible | 7 → 1 | **6** |
| Global, cada uno de los 16 focales | Dependientes del resto del frame | **13/análisis** |
| Global, 22 frames completos | 21 frames evitan 13; Pet mass-selection evita 6 | **12,68/análisis de media** |
| A1 alternado o caliente, los 22 frames | Low Tier ausente; sólo cambia Epic | **6/análisis** |
| Low Tier abierto, Normal y Rare | 8 → 8 | **0; primer gate una vez** |
| Epic abierto, ambos estados | 7 → 7 | **0; primer gate una vez** |

Mass-selection mantiene Combine admitido y consulta sus blockers completos;
el early exit no se fuerza por el nombre del contexto ni por emitir vacío.
Los demás detectores permanecen inyectados y ejecutándose en su orden original.
[Conteos de matches y medidas](../artifacts/pet_early_exits_20261016/match_counts.json).

## Potencial anterior, efecto físico y límites

El profiling original identificó **135,7 ms** de trabajo potencial global en otra
corrida y mezcla; su escenario aritmético sobre 368 reacreditaciones de board
era **50,93 s**, sujeto a sus costes offline. El ahorro **neto implementado y
medido ahora** es **107,77 ms** en los 22 frames, o 111,01 ms en los 16 focales.
No es correcto exigir igualdad entre ambas cifras ni convertir la diferencia
de corridas en overhead: cambian la instrumentación, los tiempos base y la mezcla.
El control geométrico y todo el engine ya están incluidos en el neto actual.

No se multiplica este ahorro por las 20.044 llamadas históricas: mezclan scopes,
positivos, negativos, píxeles y estados de caché sin frecuencia por detector.
**Ahorro físico nuevo: pendiente, no medido.** No se ejecutó gameplay, ADB,
captura, Session ni una nueva reacreditación económica. No se deduce throughput,
freshness al input o pared de campaña a partir de este microbenchmark.

No se encontraron discrepancias semánticas en el alcance validado. Las ramas
de geometría incompatible conservan su error y deliberadamente no toman el
atajo. Los positivos no ahorran trabajo de estos detectores. La ampliación
positiva conserva variabilidad submilisegundo que no permite una garantía
temporal estricta. El CLI legacy mantiene la limitación documentada de Trading;
la API incremental afectada y el replay global sí completan la validación.

No se incorporan memo compartida, scopes, cambios de Arena ni otras optimizaciones.

## Reproducción y artifacts

Desde la raíz, con el Python de `AGENT_LOCAL.md`:

```powershell
.\.venv\Scripts\python.exe -m artifacts.pet_early_exits_20261016.compare replay
.\.venv\Scripts\python.exe -m artifacts.pet_early_exits_20261016.compare incremental
.\.venv\Scripts\python.exe -m artifacts.pet_early_exits_20261016.compare benchmark --rounds 6
.\.venv\Scripts\python.exe -m artifacts.pet_early_exits_20261016.render_results
.\.venv\Scripts\python.exe -m artifacts.pet_early_exits_20261016.positive_followup
.\.venv\Scripts\python.exe -m pytest tests/test_pet_early_exits.py -q -o cache_dir=artifacts/pet_early_exits_20261016/pytest_cache
.\.venv\Scripts\python.exe -m pytest tests/test_pet_summon_perception.py tests/test_pet_summon_space_relief_perception.py tests/test_pet_summon_space_relief.py tests/test_monster_wave_board_acquisition_scope.py tests/test_local_cv_perception.py -q -o cache_dir=artifacts/pet_early_exits_20261016/pytest_cache
```

El cache incremental es derivado; una reproducción con cache ya existente puede
cambiar sus contadores de hits/invalidaciones iniciales, conservando las
comparaciones de salidas. Las fuentes originales y sus hashes quedan en
[preservation.json](../artifacts/pet_early_exits_20261016/preservation.json).
No se reemplazan los artifacts del profiling anterior.

## Archivos y Git

- Modificados: `bot/perception/pet_combine.py`, `bot/perception/pet_summon.py`.
- Nuevos: `tests/test_pet_early_exits.py` y este informe.
- Derivados reproducibles: `artifacts/pet_early_exits_20261016/`, ignorados por Git.
- Untracked previos conservados: `docs/PERCEPTION_ENGINE_FOCAL_PROFILE.md`,
  `docs/MW_BOARD_REACCREDITATION_PERFORMANCE.md`, `tools/loading_central_acquisition.py`.

HEAD y rama no cambian; staged vacío, sin commit/push. Se verifican los hashes
de los 45 archivos protegidos: ambos informes anteriores, capturador HIL,
artifacts del profiling, 22 PNG y cuatro logs. Se conserva toda la evidencia.
