# Reacreditación del board MW — estudio offline, 2026-10-16

Baseline `8ab0ff6ce78d2bf0e5a6d30641a60f11e5bc05ad`, rama
`rebuild/stable-baseline`, skill `kritika-dev-workflow`, modalidad
`fix-and-validate`. Sin hardware, ADB, gameplay, commit ni push.

## Decisión

**Se conserva íntegramente la reacreditación anterior. No se implementó un
handoff de autorización.** La pareja económica actual no permite acreditar
todas las condiciones exigidas para omitir las observaciones posteriores.
El beneficio computacional potencial merece consideración, pero no demuestra
equivalencia de seguridad. No se creó un fast path siempre rechazado ni un
framework de handoffs.

Los owners productivos, scopes, detectores, OCR, consenso y tests siguen iguales
al baseline. El estudio compara ambos owners cargando los bytes de `8ab0ff6`
con `git show`, sin checkout ni modificación de Git. La
[identidad de los 13 archivos relevantes](../artifacts/mw_board_reaccreditation_20261016/runtime_identity.json)
también se verificó contra el baseline, normalizando sólo CRLF/LF.

## Recorrido y semántica disponible

1. `MonsterWaveActivity.run_pass(yield_resource_board=True)` ejecuta un único
   Start desde ACTIVE/MAX/controles MW expuestos y espera una boundary estable
   .25s. El board abierto entrega `RESOURCE_BOARD_PENDING` y `board_sequence`.
   Su resultado retiene nombres/outcomes/conteos de las transiciones; no entrega
   el objeto de transición Start, su receipt ni el snapshot completo del pending.
2. `ProductiveMonsterWaveFlow._consume_pending` adquiere A1 con esa barrera.
   `MonsterWaveBoardAcquisitionRuntime` obtiene un `RuntimeSnapshot` y espera
   otro posterior. Cada snapshot contiene imagen, identidad de captura,
   observaciones, estado resuelto y geometría del mismo frame. Ambos deben
   satisfacer `_board_open`: RESOLVED, BASE MW y board como único MODAL.
3. La pareja exige secuencias y timestamps crecientes, gap máximo 1s y edad
   final máxima 2s, comprobada antes y después del reader. No exige gap mínimo
   .25s ni `stable_for=.25` en esa espera. Los retries A1 sólo descartan parejas
   por timing, hasta tres intentos pasivos; no repiten Start.
4. El reader interpreta las cinco filas con el OCR/presión roja existentes.
   El consenso exige filas concordantes, muestras distintas y posteriores a la
   barrera. Rojo fuerte puede acreditar presión sin números; ilegibilidad o
   discrepancia no autorizan planificación ni respuesta económica.
5. `FreshMonsterWaveBoard` entrega el segundo contexto, el snapshot económico
   y `after_sequence=first.sequence-1`. Los row sequences de ambas muestras
   sobreviven; el primer contexto completo se descarta. La relación con la
   barrera pending queda establecida por el recorrido local, sin conservar su
   identidad como un permiso transferible.
6. El planner recibe exactamente ese snapshot, hechos no-board explícitos,
   reloj y barrera. NO_PREREQUISITES conduce a Yes; READY/presión conduce a No
   antes de los reliefs. Insuficiencia/contradicción termina sin Yes/No. Dentro
   del mismo request bloqueado no se repiten board/planner/J después del relief.
7. `accept_board` / `close_board` esperan otros frames globales del board,
   posteriores al segundo frame A1, con estabilidad .25s, timeout nominal 3s
   y aborto por contexto incompatible. Después despachan como máximo un Yes/No.

El spacing habitual de ~.5s no sustituye la comprobación semántica de ambas
muestras ni acredita capacidades que no se ejecutaron. Dos estados positivos,
con cobertura adecuada y gap suficiente, podrían satisfacer el contrato de
estabilidad muestreada del observer; el gap por sí solo no lo hace.

## Por qué la pareja no autoriza el handoff

| Condición | Evidencia actual | Falta para reutilizar |
| --- | --- | --- |
| Contexto positivo en ambas muestras | `_board_open` en los dos snapshots locales | Transportar ambas pruebas, no sólo el snapshot económico |
| Blockers y contradicciones | A1 ejecuta su scope y resolver en cada frame | Su cobertura no equivale a la global vigente; falta `StagesDetector` |
| Cobertura | `MonsterWaveBoardPerception` emite un batch nuevo por frame | Publica `coverage=None`; no hay prueba explícita de capacidades ejecutadas |
| Estabilidad temporal | Distintos frames, tiempo creciente, gap ≤1s | No hay mínimo .25s; una pareja de .01s puede adquirir economía |
| Source/continuidad | `FrameSnapshot.source_id` opcional en cada contexto local | A1 no compara los sources y sólo conserva el segundo contexto |
| Captura posterior al input | Barrera de secuencia pending en el caller | Receipt/timestamp del último despacho relevante no viaja con la pareja |
| Freshness en autorización | Edad del segundo frame al terminar A1 y al planificar | Edad de toda evidencia necesaria al autorizar, después del planner y en dispatch |
| Yes/No expuestos | Board resuelto como único MODAL; targets físicos conocidos | No existe señal positiva de exposición de estos botones en las observaciones actuales |
| Misma intención | Wiring síncrono local: board → planning input → plan → navegación | No se conserva una asociación transferible con pending/receipt, ni una prueba de ausencia de input intermedio |

`RuntimeEvidenceRequirements` y `VerifiedTransition` ya tienen source,
captured_after, max_age y required_coverage; no falta una infraestructura
genérica. Para un handoff nuevo habría que conservar la procedencia y ambos
contextos en los owners existentes y aportar la percepción que hoy falta.
Copiar filas o añadir un booleano de estabilidad no cubriría esos requisitos.

**Diferencia real entre contrato y wiring:** RESOURCE_ROUTING describe A1 como
resolver-complete. El test de scope comprueba las reglas estáticas
`BASE_CONTEXT_RULES`/`OVERLAY_RULES`, pero `build_default_resolver()` agrega
reglas dinámicas de Stages y batalla manual. El scope A1 no incluye su detector;
el observer global posterior sí. No se corrigió ese gap como cambio vecino.

También existe una asimetría previa: S1 protege Yes con source/edad/cobertura y
revalidación de dispatch; `close_board` no declara los mismos requisitos antes
de No. Sí conserva el anchor posterior a No con source y barrera temporal.
Este estudio no atribuye guards nuevos al camino legacy ni amplía su alcance.

## Replays y contraejemplos

Se ejecutó percepción existente sobre
`artifacts/supervision_gold28_20261015/decline_before.png`,
shape **1220×2712×3** y hash registrado en el
[replay](../artifacts/mw_board_reaccreditation_20261016/replay.json).
Global y A1 reconocen MW con resource board como único MODAL.

El landmark del board observa y=.493..573; los targets Yes/No tienen y=.626.
En una copia en memoria se enmascaró la banda de ambos botones
x=.37..63, y=.59..67, calculada desde `frame.shape`. **Ambos engines conservan
el mismo board positivo.** `MW_CONTROLS_CLEAR` identifica controles de uso de
la BASE; no es una acreditación de los botones Yes/No de este MODAL.
Así, ni siquiera volver a correr la percepción global existente sobre esa
pareja demuestra la condición de exposición requerida.

Un segundo contraejemplo inyecta outputs conocidos de MW+board+`stages.base`
en los detectores existentes: el resolver global devuelve AMBIGUOUS
(MW/Stages), mientras A1 devuelve RESOLVED MW. Demuestra una dependencia
omitida, sin afirmar que esas señales coexistieran en una captura física.

El enmascarado y la inyección son **contraejemplos sintéticos offline**, no
LIVE_EVIDENCE, ni nuevos hechos de gameplay, ni una calibración de detector.
No se pide HIL para reconfirmar la existencia o función ya conocida de Yes/No.

## Costes separados

La reconstrucción de los cuatro logs referidos en `analysis_checkpoint.json`
reproduce la auditoría y su informe de campaña:

| Magnitud histórica | Valor |
| --- | ---: |
| Adquisiciones seguidas de renovación Yes/No | 184 |
| Destino Yes / No | 163 / 21 |
| Análisis globales de renovación | 368 |
| Procesamiento de esos análisis | 256.448015s |
| Espera de renovación acumulada | 264.630994s |
| Mediana de espera por board | 1.391010s |
| Reader acumulado, sin modificación | 55.426000s |
| Ventana de evento fin-reader → transición | 265.195289s |

La cifra 264.631s es tiempo de espera, no exclusivamente tiempo de análisis.
Incluye S1 #361→#365: dos análisis/2.941284s de espera que acabaron en rechazo
anterior al despacho, sin `transition.started` ni Yes. Omitir ese caso daría
183 boards/366 análisis y subestimaría precisamente el fallback relevante.

**182 parejas son candidatas sólo por timing al finalizar el reader**, usando
gap .25..1s y edad 0..2s de ambas capturas. Las otras dos tienen edad de primera
muestra 2.282s y 2.095561s. Este filtro no incluye coste posterior del planner
ni autorización. Las 184 ventanas no contienen inputs intermedios registrados.
**Cero tienen elegibilidad completa demostrable retrospectivamente**: faltan
source/cobertura de la pareja y prueba de exposición. La elegibilidad real es
UNKNOWN; no se deduce de las secuencias ni de timestamps de eventos.
[Detalle por ocurrencia](../artifacts/mw_board_reaccreditation_20261016/historical.json).

Microbenchmark local sobre el frame preservado, siete repeticiones tras warm-up,
mismos píxeles, sin OCR, source ni esperas:

| Operación | Mediana local |
| --- | ---: |
| Percepción global | .632344s |
| A1 con memo exacto caliente | .181859s |
| Stages existente aislado | .019726s |

Añadir Stages a dos muestras costaría aproximadamente .039451s frente a
1.264689s de dos análisis globales: **el coste de Stages no es el motivo para
detenerse**. Es una diferencia aritmética orientativa, medida con otra corrida
offline concurrente; no estima el coste de una nueva acreditación de botones,
la latencia completa, ni ahorro físico. Sin esa garantía falta evaluar un
candidato completo. Reanalizar globalmente las dos imágenes sólo trasladaría
dos análisis y seguiría sin demostrar exposición.

## Comparación determinística con 8ab0ff6

La comparación ejecuta RuntimeObserver, resolver, VerifiedTransition y
ActionExecutor reales con transporte simulado, outputs de detectores inyectados
y reloj explícito. Parte del fin de adquisición; no mide OCR ni ejecuta el flow
completo. Planner/productivo/relief se validan por sus regresiones existentes.
Modelo: .4s por análisis global, polling .5s, tap .1s y agenda fija de capturas.
La pareja económica y el planner no autorizan el input del harness: siempre
se ejecuta la renovación global del owner.

| Escenario | Análisis previos al input, baseline→actual | Fin-adquisición→input | Resultado en ambas versiones |
| --- | --- | --- | --- |
| Board normal → Yes | 2→2 | 1.8→1.8s | Un Yes, COMPLETED |
| Board con decisión No | 2→2 | 1.8→1.8s | Un No, anchor fresco, COMPLETED |
| Sólo evidencia económica compatible | 2→2 | 1.8→1.8s | Renovación completa antes de un Yes |
| Snapshot original vencido | 2→2 | 1.8→1.8s desde entrada al owner | Sólo frames nuevos autorizan un Yes |
| S1: percepción lenta seguida de pareja fresca | 4→4 | 4.9→4.9s | Readquisición pasiva única; un Yes |
| Source cambiado, blocker, foreign, AMBIGUOUS, CLEAR anterior al input | Sin despacho | — | RuntimeWaitAborted, cero taps |
| Cancelación previa / deadline heredado | Sin despacho | — | CANCELLED / OperationBudgetExpired, cero taps |
| Transporte incierto de Yes | 2→2 | 1.8→1.8s | FAILED, un intento de tap, ningún retry |

Yes completa en 2.8s simulados; No, incluido el anchor posterior, en 4.5s en
ambas versiones. El fallback añadido cuesta **0 análisis, 0 capturas y 0s**:
no hay un nuevo probe ni un camino rápido incorporado. Su coste total permanece
el de la reacreditación original. **Análisis eliminados: 0. Ahorro simulado: 0.
Ahorro físico nuevo observado: ninguno.** El coste histórico candidato anterior
no se convierte en ahorro implementado.

Diez comparaciones adicionales de adquisición muestran equivalencia en pareja
normal, source ausente/cambiado, gap .01s, duplicado, stale, pareja anterior al
receipt sintético, ilegibilidad, discrepancia y presión roja. Adquirir economía
con source cambiado o antes del receipt es posible en la API descriptiva actual;
no constituye autorización de Yes/No y explica por qué no se promovió esa pareja.
Las comparaciones suman 23 escenarios pareados, 46 ejecuciones; no son 46 tests
nuevos ni una aceptación física.

Resultados y reproducción con el Python de AGENT_LOCAL, desde raíz:

```powershell
.\.venv\Scripts\python.exe -m artifacts.mw_board_reaccreditation_20261016.study
```

[Script local](../artifacts/mw_board_reaccreditation_20261016/study.py),
[navegación y tiempos](../artifacts/mw_board_reaccreditation_20261016/comparison.json),
[adquisición](../artifacts/mw_board_reaccreditation_20261016/acquisition_comparison.json).

## Validación y garantías conservadas

**313 passed, 1 skipped**, en 92.67s. La selección cubre adquisición/scope,
cinco filas/consenso/presión roja, planner, navegación, productivo, ruta de
recursos, integración, loading/efecto tardío, expiry tras relief, CLEAR y los
replays existentes. El skip corresponde al replay post-CLEAR cuyo bundle de
failure evidence ya no contiene frames locales. No se ejecutó evaluator:
ningún detector, ROI, reader, parser ni infraestructura perceptiva cambió.
[Resultado JUnit](../artifacts/mw_board_reaccreditation_20261016/regressions.xml).

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_monster_wave_standalone.py tests/test_monster_wave_productive.py tests/test_monster_wave_board.py tests/test_monster_wave_board_acquisition_scope.py tests/test_monster_wave_resource_route.py tests/test_monster_wave_yes_loading.py tests/test_monster_wave_integration.py tests/test_monster_wave_skip_expiry.py tests/test_monster_wave_post_clear_recovery.py tests/test_monster_wave_clear_retry.py tests/test_mw_failed_session_replay.py tests/test_resource_route_planner.py
```

Se conservan A1 y S1 sin modificación, no-repeat SKIP por adquisición fallida,
Yes/No single-attempt ante efecto incierto, cancelación/deadlines, edad máxima
vigente, loading sólo como progreso, CLEAR como señal de efecto productivo,
anchor posterior a No y ejecución/resume de relief del mismo request.
Los snapshots/planes no se reutilizan entre pasadas. Los tests de productivo
siguen verificando preparación/J una sola vez y continuaciones posteriores a
relief; no se modificó Session ni la navegación Battle Mode/hub.

Entrega versionable: este informe. Scripts, JSON y JUnit nuevos se conservan
localmente bajo `artifacts/mw_board_reaccreditation_20261016/`, ignorado por Git;
no son dependencias runtime. Los artifacts existentes y
`tools/loading_central_acquisition.py` untracked se preservan. No hay cambios
staged ni modificaciones productivas, y HEAD/rama permanecen en el baseline.
