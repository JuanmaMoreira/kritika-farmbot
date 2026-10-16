# Preparación del hub MW — validación offline, 2026-10-16

Baseline comparado: `5aaf8fdeb10c7e3866401d4d5bf3b5336e03cf81`, rama
`rebuild/stable-baseline`. Modalidad `fix-and-validate`, sin hardware, ADB,
gameplay ni Session real. No se acredita una reducción física nueva.

## Causa y contrato reconstruido

`BattleModeZone.enter()` espera Lobby limpio y ejecuta
`battle_mode.open_battle_mode_select`, con precondition/retry desde Lobby,
dos intentos como máximo y destino `is_battle_mode_select`, estable .25s.
`VerifiedTransition` conserva source efectivo, snapshot final, receipts y
resultado de nominal/gracia/retry. También estabiliza un efecto detectado
después de la gracia; un único frame tardío no sustituye esa estabilidad.

Antes del cambio, `MonsterWaveFlow.run()` y
`ProductiveMonsterWaveFlow.run()` descartaban esa evidencia al preparar:

| Observaciones antes de `monster_wave.open` | Función | Decisión |
| --- | --- | --- |
| observe inicial, habitualmente 1 análisis | Crear cursor de preparación | Redundante con handoff válido |
| primer wait del hub, habitualmente 2 análisis | Acreditar Select Battle Mode estable .25s | Redundante: lo acaba de acreditar la transición |
| consenso de Sapphires, habitualmente 2 análisis más OCR | Leer valor económico nuevo, posterior a la barrera | Se conserva completo |
| wait final del hub, habitualmente 2 análisis | Contexto compatible posterior a toda la lectura económica | Se conserva completo |

`monster_wave.open` conserva su fuente en ese **último** wait, precondition
positiva, un intento y normalización existente de modales. El snapshot transferido
no autoriza ese tap ni compra/activación/MAX/Start. La preparación económica,
pressure, board, reliefs y consumo posterior a CLEAR conservan sus owners.

## Cambio y guards

`BattleModeZoneResult.hub_entry` entrega el resultado exacto de la transición;
los dos wrappers lo pasan como argumento a la preparación inmediata. No hay
cache de visita, nueva abstracción de navegación ni cambios en RuntimeObserver,
VerifiedTransition, OCR o detectores.

`MonsterWaveActivity._reuse_hub_entry` acepta exclusivamente:

- Transición de entrada conocida, exitosa, efecto acreditado y ready; sin recovery
  posterior al input, con source efectivo y último receipt disponibles.
- Source efectivo Lobby limpio y snapshot final Select Battle Mode positivo,
  resuelto y con sólo los indicadores Daily permitidos por el predicado existente.
- Secuencia final mayor que la del source; captura final estrictamente posterior
  al retorno del último despacho, incluido retry.
- Último receipt de la misma operación e intento que el resultado; timestamp
  finito no negativo. Metadata ausente o mezclada conserva el fallback.
- Cobertura declarada del source conservada en el destino; pérdida o falta de
  esa declaración tras una declaración previa rechaza reutilización.
- `source_id` no vacío e idéntico en source, destino y frame actual del observer.
- Edad del destino 0..2s antes y después de consultar el frame actual;
  secuencia y timestamp actuales sin retroceso.
- Cancelación y presupuesto heredado vigentes, incluidos los controles al volver
  de la consulta de captura. El caller entrega el argumento inmediatamente,
  sin inputs ni trabajo de otro owner entre transición y preparación.

La consulta adicional usa `get_frame()`: copia del frame stream actual en el
source productivo, sin análisis, refresh nativo, input ni espera nueva.
Si falta información o el handoff caduca/incompatibiliza, se ejecutan el observe
y wait originales. Las lecturas económicas nuevas deben superar la barrera
aceptada; la acreditación final supera todas las secuencias del resultado y fact.

La procedencia de operación también depende del wiring explícito: los dos callers
entregan el objeto exacto recién devuelto por su propio `zone.enter()`, sin cache,
inputs intermedios ni consulta a otra operación. El registry conecta entrada y
Activity al mismo observer/percepción global/resolver. No se transfiere evidencia
del scope de readiness ni de otro observer. `PerceptionEngine` global publica
actualmente `coverage=None`: no se inventa cobertura a partir de observaciones
ausentes; se conserva el contrato de percepción conocido del productor inmediato.
Si existe cobertura explícita, el guard nuevo exige conservarla.

No se reutilizan las observaciones económicas para omitir el wait final:
`FactReadResult`/`FactEvidence` no conservan los snapshots completos, el source
de cada muestra ni prueba de estabilidad continua .25s. Hacerlo con esos datos
no demostraría equivalencia. Tampoco se propaga evidencia mediante Session o
`prepared(zone)`: su entrada compartida puede incluir otras comprobaciones;
su camino actual queda vigente. `reenter()` sigue intacto.

## Comparación determinística contra el baseline

[Harness versionable](../tests/test_monster_wave_hub_preparation.py): carga los
bytes de Activity mediante `git show 5aaf8fd:bot/monster_wave_activity.py` sin
checkout ni cambios de Git. Corre ambas versiones con RuntimeObserver,
resolver, VerifiedTransition, ActionExecutor y RuntimeFactReader reales.
Los dobles representan reloj, observaciones de píxeles, texto OCR y transporte.
El algoritmo de Zone y los predicados compartidos permanecen iguales al baseline;
Zone sólo agrega el resultado transportado.

Modelo explícito: .4s por análisis, .05s por despacho, polling existente .02s,
consulta/copia de captura y OCR de coste cero salvo el caso indicado. No son
mediciones del teléfono ni una predicción de latencia física.

| Escenario | Análisis antes de Open, antes→después | Tiempo simulado antes de Open | Inputs/permisos |
| --- | --- | --- | --- |
| Entrada normal | 7→4 | 2.84→1.62s | Una entrada al hub y un Open MW |
| Entrada con retry acreditado | 7→4 | 2.84→1.62s | Dos entradas al hub y un Open MW; mismo retry positivo |
| Efecto tardío en gracia | 7→4 | 2.84→1.62s | Una entrada al hub y un Open MW; sin repetir por efecto tardío |
| Sin seed, vencido, anterior al despacho o source cambiado | 7→7 | 2.84→2.84s | Readquisición original antes de Open |
| Contexto contradictorio/modal persistente tras consenso | No se abre | 8.30→7.08s hasta fallo | Cero Open en ambas versiones |
| Sapphires ilegibles/inconsistentes | 6→3 hasta fallo | 2.42→1.20s hasta fallo | Tres muestras nuevas; cero Open |
| Cancelación previa | 0→0 | 0→0s | Cero inputs nuevos |
| Deadline heredado +.6s | 2→2 hasta fallo | .8→.8s cooperativos | Cero inputs nuevos; no se renueva deadline |

Se eliminan tres análisis y 1.20s de procesamiento simulado más .02s de polling
en las entradas equivalentes: **1.22s simulados por preparación compatible**.
Incluyendo la acreditación de MW posterior al tap, la preparación completa pasa
de 9 análisis/3.71s a 6/2.49s. Los inputs físicos simulados y límites de intentos
son iguales; los dos consensos usan muestras posteriores al hub acreditado.

Fallback: cero análisis extra. Un rechazo anterior a consultar el source no
añade capturas; un rechazo por source/continuidad/edad durante esa consulta añade
una captura a las nueve del ciclo completo (9→10). Con copia de coste cero, el
tiempo completo permanece 3.71s. En un segundo modelo explícito de 5ms por
`get_frame()`, el fallback completo es 3.755→3.760s y antes de Open
2.875→2.880s: exactamente una copia adicional. Su coste real depende del source
y no se ha medido físicamente en esta tarea.

También se prueban snapshot futuro, secuencia regresiva, metadata/receipt ausentes,
no-ready/no-effect, recovery posterior, caducidad durante captura, AMBIGUOUS,
UNKNOWN, cero económico, muestra ilegible intermedia, cancelación durante captura,
consenso y wait final, y deadline agotado durante la consulta de metadata.

Resultados reproducibles:
[script](../artifacts/mw_hub_preparation_20261016/compare.py),
[comparación JSON](../artifacts/mw_hub_preparation_20261016/simulated_comparison.json).
Ejecutar desde raíz con el Python de AGENT_LOCAL:
`python -m artifacts.mw_hub_preparation_20261016.compare`.

## Aplicabilidad histórica: campaña 28/28

Se reconstruyeron las ventanas entre el éxito de
`battle_mode.open_battle_mode_select` y el inicio de `monster_wave.open` en los
cuatro JSONL referenciados por `analysis_checkpoint.json`. Reproduce el informe:
59 ventanas, 288.718003s acumulados, mediana 4.874603s y 278.083681s de análisis.

**57 ventanas** son preparación con consenso de Sapphires: su prefijo redundante
suma **171 análisis / 116.130160s de procesamiento histórico candidato**.
Las otras dos son `reenter`, sin consenso: S4 #10951→#10955 y #22217→#22221;
se conservan sus seis análisis / 4.200121s de prefijo. Así se explica la diferencia
entre las 59 ventanas temporizadas y las 57 oportunidades de esta optimización.

Las 57 tienen entrada ready y ningún input intermedio. Su **aplicabilidad
estructural** está acreditada; cuántas cumplirían todos los guards en ejecución
es UNKNOWN: los logs no contienen `source_id` ni timestamp de captura final.
No se transforma tiempo de evento, número de secuencia ni coste de análisis en
metadatos de captura inventados. Cero ocurrencias tienen elegibilidad completa
demostrable retrospectivamente; eso no significa que cero serían elegibles live.
Los 116.130s no son ahorro garantizado ni observado tras el cambio.

[Detalle por ocurrencia](../artifacts/mw_hub_preparation_20261016/historical_opportunities.json),
[informe de campaña](../artifacts/supervision_gold28_20261015/INFORME_BASIC_GOLD_28_28.md).

## Validación y archivos

Primera validación: 41 tests nuevos directos aprobados. Regresiones dirigidas en 24 archivos:
Zone/WB, Activity/entry/clear/reentry/MAX, productivo/reliefs/board, prepared binding,
facts/readiness/OCR, Gold Farming, Yes/loading y replays existentes.
Unión de nodos ejecutados: 612 aprobados y un skip por frames de failure evidence
post-CLEAR ausentes; las corridas se hicieron por invalidación, no como suite global.
Se corrigió el pin del mock standalone al nuevo argumento explícito; prepared
mantiene su binding anterior. Listado:
[regression_files.json](../artifacts/mw_hub_preparation_20261016/regression_files.json).

Revisión de publicación: se cerraron los guards locales de identidad del receipt,
cobertura declarada y timestamp de despacho no finito/negativo. Se reutilizan los
612 resultados y cuatro replays anteriores, salvo la validación directa del handoff
invalidada por ese ajuste. Corrida focal: **67 passed**, con 50 casos de handoff,
Zone y binding. Nueve casos nuevos elevan la unión a **621 aprobados y un skip**.
El skip es `test_failure_frames_are_transient_negatives_never_zero_or_confirmed`:
sus tres PNG privados no están presentes, el test y OCR post-CLEAR no cambian
contra el baseline, y los tests sintéticos de recovery sí pasan. No acredita una
regresión ni se sustituye su evidencia física ausente.

Los 50 tests del handoff usan código versionado, datos sintéticos en memoria y el
objeto Git del baseline; no leen datasets, logs ni artifacts ignorados. Requieren
que `5aaf8fd` esté disponible en la historia Git. Pueden ejecutarse directamente
con `python -m pytest tests/test_monster_wave_hub_preparation.py -p no:cacheprovider`.
Los scripts y resultados enlazados bajo `artifacts/` son evidencia local auxiliar;
no son dependencias de los tests versionados ni estarán en un checkout nuevo.

Replay adicional de cuatro PNG nativos 2712×1220 de la campaña, inspeccionados
visualmente: dos hubs compatibles con Daily WB, Lobby y MW como negativos.
Los cuatro pasan con percepción y resolver productivos, sin reescalar ni
reconstruir source/edad. [Script](../artifacts/mw_hub_preparation_20261016/replay_context.py)
y [resultado](../artifacts/mw_hub_preparation_20261016/context_replay.json).
El replay OCR existente también conserva los siete saldos curados del hub.
Sin cambio perceptivo, no se ejecutó evaluator global.

Archivos de implementación: `bot/battle_mode_zone.py`,
`bot/monster_wave_activity.py`, `bot/monster_wave_flow.py`,
`bot/monster_wave_productive.py`. Tests: nuevo
`tests/test_monster_wave_hub_preparation.py` y ajuste de
`tests/test_productive_monster_wave_session_binding.py`. Documentación dueña:
`docs/MONSTER_WAVE_SKIP.md` y este informe. Scripts/resultados locales nuevos
quedan en `artifacts/mw_hub_preparation_20261016/`, ignorados por Git.

La publicación autorizada se limita a los ocho archivos de esta fase en
`rebuild/stable-baseline`, en un único commit y push normal. El capturador untracked
`tools/loading_central_acquisition.py`, evidencia, logs y artifacts quedan fuera
del staging y se preservan. No hay aceptación física nueva ni promesa de ahorro con evidencia
incompatible; ese caso mantiene la adquisición conservadora del baseline.
