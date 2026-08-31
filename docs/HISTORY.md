# Historia técnica — Kritika FarmBot 0.2

Este documento es cold context. Conserva cronología, experimentos y evidencia que pueden servir para debugging o trazabilidad, pero no debe leerse por defecto. Para decisiones vigentes usar `CONTEXT.md` y `ARCHITECTURE.md`; para la implementación real, código y tests.

El estado documental completo anterior a esta compactación permanece además en Git, commit `4a14eee`.

## Legacy y rediseño híbrido

El estado anterior se preservó en el tag `legacy-pre-hybrid`. El runtime mezclaba captura scrcpy, templates, globals, coordenadas y policy dentro de `screen.py`, `context.py`, `actions.py`, `flows.py` y el catálogo de 75 entradas de `constants.py`. TOT conservaba conocimiento de negocio, pero el entry point ya no era importable tras retirar APIs acopladas.

Se decidió conservar scrcpy, OpenCV y ADB como tecnologías útiles, separando responsabilidades. Las 173 capturas landscape históricas (aprox. 527 MiB) permanecieron ignoradas; los manifests versionados conservaron labels sin copiar el dataset. Los 28 assets `960x540` quedaron como referencia local, no runtime activo. `AdsManager` se mantuvo standalone mediante UIAutomator2.

## Fase 0 — auditoría y preservación

La auditoría confirmó geometría inconsistente, prioridades/outcomes incompletos, templates faltantes y ausencia de loop global. Se preservó el conocimiento legacy sin intentar reparar primero su runtime. La reorganización estableció código/tests como fuente de implementación y documentación separada para contexto, arquitectura y futuro.

## Fase 1 — núcleo reutilizable

### Configuración y geometría

`RuntimeConfig` pasó a ser explícito e import-safe. `bot/geometry.py` estableció coordenadas normalizadas y dimensiones derivadas de `frame.shape`, corrigiendo la mezcla histórica entre frames landscape `2712×1224` y `adb wm size` reportado en orden portrait.

### ADB y captura

`AdbClient` concentró state, shell, input, push y forwards detrás de un runner inyectable. `ScrcpyFrameSource` tomó ownership de server, forward, proceso persistente, socket, decoder, thread y cleanup.

El smoke físico con scrcpy-server 3.3.4 produjo cinco frames BGR `(1224, 2712, 3)`, sequences `1→5`, primer frame en ~2,4 s y cleanup completo del forward. La prueba detectó que los packets H.264 SPS/PPS debían conservarse y anteponerse al siguiente media packet para PyAV.

Fase 1E retiró captura/input duplicados de `screen.py`; quedaron sólo helpers OpenCV puros sobre frames explícitos. Tools de captura migraron al composition root y se eliminaron diagnósticos duplicados o con IDs hardcodeados.

## Fase 2 — modelo semántico

Se definieron `Observation`, `ObservationBatch`, `ResolvedState` y `ResolutionStatus`. `UNKNOWN` quedó como resultado normal y overlays pueden coexistir con base desconocida. El resolver se hizo determinista: cero/uno/varios matches producen `UNKNOWN`/`RESOLVED`/`AMBIGUOUS`, sin first-match ni desempate por confidence.

El catálogo inicial separó semántica de assets. La evaluación offline de 27 capturas confirmó Black Market 6/6 y Purchase Confirmation 3/3 sin FP/FN. Character Select y Battle Mode Select quedaron prometedores; el icono de oro resultó inadecuado como señal exclusiva de Lobby porque persiste bajo otras pantallas.

## Fase 3 — Perception local

### 3A–3C: pipeline y señales base

`PerceptionEngine` y detectores OpenCV precargados introdujeron raw scores separados de confidence semántica mediante `LinearGapCalibration`. La evaluación inicial produjo 27/27 estados esperados.

La adquisición dirigida añadió 30 capturas human-confirmed: diez Lobby, diez Character Select y diez Battle Mode Select. La reevaluación mostró que los assets legacy de Character Select y Monster Wave no separaban adecuadamente la apariencia actual. Un crop de `Trading Center` fue elegido como landmark mínimo de Lobby; el icono de oro se descartó como base porque aparece en Black Market, Quests, Trading Center e Item Trade.

Se promovieron assets actuales de Lobby y Character Select. Sobre 57 labels, el pipeline produjo 57/57 estados esperados, cero errores y cero ambigüedades. Battle Mode Select permaneció sin detector productivo por gap pequeño y poca diversidad visual.

### 3D–3G: drift live, Workbench y repair

El primer smoke live resolvió Lobby y Character Select, pero falló en Black Market y Purchase Confirmation por rendering drift de la season actual. No se bajaron thresholds sin evidencia.

Perception Workbench v1 añadió observación read-only del touchscreen, ground truth humano y evidencia before/after. La primera sesión `20260823T054558_979538Z-46e40344` sufrió macroblocking/lag y quedó marcada diagnóstica/no curable. El root cause fue presión combinada de stream `2 Mbps`, render repetido y PNG full-resolution síncrono; no una diferencia entre Perception y UI.

Workbench pasó a `8 Mbps / 30 fps`, preview `1356×612`, último frame, render por cambios y writer acotado. `--compare-once` confirmó raw scores idénticos e input inmutable. La sesión válida `20260823T061544_647270Z-11461340` guardó 60 PNG limpios, 25 gestos con asociaciones crecientes, queue máxima 2, cero drops/failure y cleanup completo. La sesión `20260823T064721_367331Z-addb7117` confirmó ground truth correcto de Purchase sobre Black Market.

Cinco frames revisados se promovieron a `datasets/workbench_evidence_manifest.json`. Black Market conservó el asset histórico y recalibró su mínimo positivo live. Purchase añadió una variante nativa current-season y acotó su región para excluir el diálogo genérico “Still proceed?”. La evaluación reparada produjo 62/62 estados esperados, 28 `UNKNOWN`, cero wrong y cero `AMBIGUOUS`.

El smoke 3G revalidó live Lobby, Character Select, Black Market y Purchase sobre Black Market y Guild Shop. Procesó 1478 snapshots en 494,75 s; no hubo `AMBIGUOUS`. Latencias min/mediana/media/máxima: Perception `7.296/12.195/12.388/53.201 ms`, Resolver `0.039/0.060/0.067/0.953 ms` y snapshot-to-state `0/32/32.769/157 ms`. Cleanup dejó cero forwards y ningún proceso de captura persistente.

### 3H.1: acquisition vocabulary y transiciones

Workbench separó catálogo productivo de vocabulary humano candidate. El envelope v2 incorporó `interaction_id`; el primer frame posterior quedó explícitamente como observación temporal. Sólo la tecla semántica de confirmación humana podía registrar `after_ground_truth`; una prediction o un gesto nunca inferían destino ni causalidad.

La sesión `20260825T185040_032589Z-95f6cd26` validó Lobby, Guild Shop candidate, períodos `UNSET`, taps y swipe con confirmación explícita. Registró 35 events/31 PNG, queue máxima 3, cero drops/failure y cleanup completo; permaneció raw sin promoción.

### 3H.2: semantic census y Quick Menu

`docs/semantic_census.md` preservó las 75 entradas legacy. Quick Menu no era una entrada adicional: era detección global con offsets dependientes de contexto. La sesión `20260825T193046_517947Z-76b5e238` adquirió estados abierto/cerrado sobre Lobby e Inventory sin input ADB y produjo 70 events/69 PNG con cleanup completo.

El manifest curado conservó 18 positivos y 15 negativos locales. `menu.quick` se promovió como overlay global usando un tile “Lobby” y una región que cubre ambas posiciones observadas. La evaluación combinada dio 18/18 TP, 0 FP/FN frente a 77 negativos y gap raw `0.684476` (`0.298147→0.982623`). Cuando el panel oculta el landmark base, `UNKNOWN + menu.quick` es correcto.

### 3H.3: GOLD e Insufficient Gold

La evidencia corrigió el supuesto grid 4×2: Black Market tiene 5 filas × 2 columnas. `BlackMarketGoldDetector` reutilizó el icono GOLD legacy sobre diez regiones estrechas, con índice row-major como value. El primer corpus dio 24 TP, 0 FP/FN sobre 840 regiones negativas y 0 FP sobre KARATS; las posiciones sin positivo real quedaron cubiertas sólo geométricamente por tests sintéticos.

La exploración humana confirmó que falta de fondos abre directamente `popup.insufficient_gold`; elegir No retorna a Black Market. La rama Yes no se probó por riesgo de iniciar compra de oro. El detector obtuvo 1 TP y 0 FP/FN frente a 95 negativos. La regresión completa produjo 96/96 estados esperados, 60 `UNKNOWN`, cero wrong y cero `AMBIGUOUS`.

Un probe live posterior resolvió Black Market y tres GOLD con confidence 1.0. El protocolo human-in-the-loop quedó centralizado en `AGENTS.md` antes de esta prueba.

## Fase 4 — Black Market single-character

Se implementaron `RuntimeSnapshot`, esperas frescas bounded, semantic intents, `ActionExecutor` y `BlackMarketFlow`. La navegación quedó `Lobby → Black Market → Lobby`, sin Quick Menu. El flow lee una vez los slots GOLD, compra en orden row-major, maneja Purchase/Insufficient Gold y exige `Purchased` del mismo slot.

`BlackMarketPurchasedDetector` usa dos crops nativos de `Purchase Complete!`. Tras tres compras live confirmadas obtuvo 11/11 TP, 0 FP/FN frente a 929 negativos; raw positivo min/mediana/máximo `0.881583/0.942529/0.999968`, máximo negativo `0.557578` y gap `0.324005`. GOLD cerró con 25/25 TP, 0 FP/FN y cero FP sobre 61 KARATS, incluyendo positivo empírico en slot 8.

La validación física fue incremental: probe pasivo con GOLD `[6,8]`; one-slot smoke que compró y verificó slot 6; full smoke con GOLD `[7,8]` que verificó ambos; captura pasiva posterior; cierre final de Black Market a un frame fresco Lobby. Un intento falló en `adb get-state` antes de cualquier tap por aislamiento del daemon; el reintento autorizado funcionó. Todos los sources hicieron cleanup.

El checkpoint `4a14eee` cerró la fase con 460 tests hardware-free. Rotation, SessionRunner, OCR, VLM y recovery transversal quedaron sin implementar.

### Extensión Inventory Full

Una adquisición live read-only preservó seis frames frescos del popup real de límite de Emerald. La señal elegida fue el botón `OK` común, excluyendo el mensaje variable. Los positivos dieron `0,983645–0,999941`; el máximo negativo revisado entre otros diálogos con `OK` fue `0,894897`, con threshold raw efectivo `0,965896` y gap `0,088749`. El gating adicional exige `landmark.black_market_title`: sobre 252 capturas locales la conjunción produjo sólo los seis positivos y ningún conflicto.

`popup.inventory_full` reemplazó el candidate semántico `popup.bag_full_alert`. `BlackMarketFlow` lo registra como `black_market.inventory_full`, ejecuta un intent `AcknowledgeInventoryFull` mediante `VerifiedTransition`, exige un Black Market fresco y continúa con el siguiente GOLD sin reintentar el slot. No se añadió OCR, `inventory_kind`, limpieza de inventario ni composición de sesión. La prueba live sobre el popup adquirido cerró al primer tap, sin grace ni retry, y el usuario confirmó visualmente el Black Market normal. El cierre quedó en 574/574 tests hardware-free.

## World Boss — adquisición y percepción semántica

La auditoría legacy localizó `select-boss-id.png`, `world-boss-id.png`, `world-boss-auto-repeat-id.png`, `battle-id.png` y targets históricos, pero no los promovió por sí sola. El primer probe live entró al selector PvP mediante Battle; la corrección humana identificó que World Boss está bajo Survival. Esa pantalla negativa no se convirtió en un contexto del slice.

La navegación supervisada adquirió y el usuario confirmó por chat seis estados: `screen.battle_mode_select`, `overlay.world_boss_select_boss`, `popup.world_boss_previous_rewards`, `screen.world_boss`, `screen.world_boss_battle` y `overlay.world_boss_raid_complete`. Select Boss preserva la base atenuada y Close la restaura, por lo que es overlay. Previous Rewards corresponde al boss anterior y no demuestra participación actual. Raid Complete conserva visible el HUD productivo de batalla y resuelve base + overlay.

Se curaron 44 frames: 6 Battle Mode, 4 Select Boss, 5 Previous Rewards, 8 World Boss, 13 batalla y 8 Raid Complete. Se promovieron seis crops current-season que excluyen números, boss, rewards y otros datos variables. La evaluación productiva conjunta recorrió 146 labels con 146 correctos, cero wrong/ambiguous y 0 FP/FN para los 13 detectores. Los nuevos gaps raw fueron `0,272674`, `0,709750`, `0,628603`, `0,388257`, `0,357196` y `0,564908`; Lobby y Black Market se recalibraron contra el corpus global ampliado sin cambiar su semántica.

Quick Menu abrió y cerró desde World Boss con el target común `(0.1940, 0.0564)`, restaurando la base; el mismo target fue revalidado sobre Lobby antes de ampliar `quick_menu_accessible`. El manifest específico conserva `UNKNOWN + menu.quick` mientras el panel tapa la base, sin inventarla.

La batalla se observó con varios valores del timer y se capturaron secuencias explícitas Auto OFF/ON. En la ROI del control, OFF obtuvo diferencia absoluta consecutiva media `1,672837` y desviación estándar media `6,429503`; ON obtuvo `11,612882` y `38,287155`. Auto quedó restaurado ON. Esto es evidencia candidate, no detector productivo. Los manifests también preservaron ROIs normalizados para sapphires, costo, rank/participation, Start, Auto Repeat, Auto Battle, timer y taps seguros. En ese checkpoint todavía no se implementaron OCR, parsers, acciones World Boss, Auto Repeat, `WorldBossFlow`, integración de sesión ni ConflictResolver.

## OCR transversal y primeros Runtime Facts

Se eligió RapidOCR 3.9.2 con ONNX Runtime 1.29.0: inferencia CPU completamente local, modelos incluidos en el wheel, soporte Python 3.12 y ninguna instalación binaria externa como Tesseract. El import y la inicialización son lazy. `OcrResult` conserva texto, confidence y metadata; los extractors poseen crop/preprocessing/parser y `RuntimeFactReader` exige frames posteriores a la solicitud, contexto correcto, separación temporal y operación bounded/cancelable.

La primera validación de sapphires expuso un error semántico útil: la ROI candidate `[0.845, 0.59, 0.945, 0.68]` leía `32/32`, pero el usuario identificó ese sprite violeta como melee tickets de Battle. La evidencia fue rechazada para sapphires. El contador azul correcto de Survival quedó en `[0.77, 0.43, 0.855, 0.505]`; tres lecturas live independientes produjeron consensos `247/66 → 247` con confidence `0,999435–0,999545`. Tres frames previos human-confirmed aportaron naturalmente `257/66 → 257`; no se gastaron recursos para fabricar variación.

El timer real usa `M:SS.t`, no sólo `MM:SS`. Cinco lecturas de una misma batalla, confirmadas visualmente por el usuario, dieron raw `0:55.4`, `0:52.0`, `0:50.4`, `0.48.8` y `0:47.3`; el parser toleró la confusión OCR colon/punto y emitió por `ceil` `56, 52, 51, 49, 48` segundos, una secuencia plausible y estrictamente decreciente. Formas ambiguas sin separador se rechazan como unreadable. `datasets/ocr_runtime_facts_evidence_manifest.json` preserva provenance, corrección HIL y limitaciones.

No se implementaron reglas de participación, OCR de costo/rank/nombre, CharacterContextProvider, Auto Battle, `WorldBossFlow`, Auto Repeat, acciones ni integración con `ControlledWait`/`SessionRunner`.

## Auto Battle temporal

La recalibración live human-confirmed estrechó la ROI candidate para excluir Pause y fondo móvil: `(0.835, 0.018, 0.890, 0.078)`. Diez frames frescos por ventana, separados nominalmente `0,1 s`, se agregan por mediana de nueve diferencias absolutas consecutivas sobre el borde. Ocho ventanas OFF alcanzaron como máximo `1,253144`; nueve ON como mínimo `7,385336`. Los thresholds productivos `OFF ≤ 2` y `ON ≥ 5` dejan gap UNKNOWN `2–5`, con 0 FP/FN en el corpus curado.

`setting.auto_battle` quedó como Runtime Fact tipado con evidencia temporal y `ensure_auto_battle_on()` como operación transversal sobre `RuntimeObserver + ActionExecutor`. Live, ON inicial terminó sin input; OFF `0,226251` produjo un tap normalizado `(0.8625, 0.0480)` y la ventana fresca posterior confirmó ON `9,265052`. No hubo retries y el usuario confirmó visualmente ON final. Una consulta durante Raid Complete abortó sin clasificar ni tocar. No se implementaron `WorldBossFlow`, `ControlledWait` integrado, Auto Repeat, SessionRunner World Boss ni ConflictResolver.

## WorldBossFlow productivo

Se implementó el flow single-character con policy `ALWAYS_PARTICIPATE`, OCR inicial de sapphires, navegación semántica verificada, Previous Rewards opcional, Start, Auto Battle, timer, espera controlada en dos fases, Raid Complete y salida World Boss. La primera ejecución expuso que Previous Rewards puede aparecer después de que `screen.world_boss` resuelva transitoriamente; la rama quedó ligada a `SelectAvailableWorldBoss` con un settle explícito antes de habilitar Start.

Start expuso además un popup Yes/No de inventario Socket lleno, inicialmente namespaced como si fuera específico de World Boss y luego promovido a `popup.socket_inventory_full`. Dos frames live sostuvieron la primera rama conservadora: el flow registra el evento, verifica `No → World Boss` y termina ese personaje, sin reintentar Start ni intentar liberar inventario. El layout interno de Quick Menu fuera de Lobby mostró un offset lateral: Character se validó en `(0.2000, 0.7835)`. Con esa corrección, un `StandardRotation.advance()` real desde World Boss hizo dos swipes efectivos y llegó al Lobby del personaje siguiente.

Los smokes finales sobre el mismo personaje cerraron tres ramas: inventario lleno con todas las transiciones al primer intento; batalla completa con Auto Battle ON, timer inicial 60 s, 29 checks, Raid Complete y Continue exitoso tras un retry seguro; y sapphires `0`, que emitió `world_boss.insufficient_sapphires` sin ninguna transición ni input. Previous Rewards se reconoció y cerró manualmente sobre la evidencia que motivó la corrección; su secuencia tardía quedó cubierta por regresión determinista.

## Rotation, sesiones y frontends productivos

`StandardRotation` quedó validada primero de forma aislada: 28/28 advances, 56 swipes, 28 selecciones visuales y 112 interacciones discretas al primer intento, con retorno humano-confirmado al personaje inicial. La composición Black Market posterior completó 28/28 flows y 28/28 advances; acumuló 14 `inventory_full` no fatales, diez retries seguros y cero fallos técnicos.

`SessionRunner` evolucionó de una secuencia ligada a Lobby a contratos explícitos por componente. `WorldBossFlow` pudo terminar en World Boss, `StandardRotation` consumir la capability Quick Menu desde ese contexto y el runner verificar la salida real antes de continuar. Los smokes N=2 cerraron tanto `World Boss → Rotation` como `Black Market → World Boss → Rotation`, sin normalizaciones redundantes.

Los commits `fac9f6a` y `df4a0ad` añadieron el runtime manual y la GUI Tkinter sobre el mismo `FlowRegistry`, composition root, cancellation token y event stream. `a7e34f0` añadió el launcher Windows de doble clic. Run Flow Once y Run Session quedaron como adaptadores: la GUI mantiene selección/progreso y un worker encolado, pero ninguna business logic.

## Raid Complete, ControlledWait y hardening previo al 28/28

El primer smoke de la espera final agotó el timeout aunque Raid Complete estaba visible: el consumer exigía simultáneamente la base de batalla y el overlay, pero el resolver preservaba correctamente overlays con base no resuelta. Los fixes posteriores a la GUI cerraron los gaps encontrados en sesiones reales:

- `4ad891f`: espera inicial pasiva sin capturar; después polling bounded, donde un check falso sólo continúa.
- `d5346f1`: Raid Complete se detecta por el overlay independientemente de la base resuelta.
- `9aa578c`: timeout final ampliado a 25 s por latencia post-timer observada.
- `f4443d2`: budget de adquisición temporal de Auto Battle ampliado sin cambiar thresholds.
- `6554369`: Runtime Facts toleran frames transitorios no resueltos dentro del mismo timeout.
- `e3aa5c5`: nuevo guard `popup.world_boss_bag_full`, con `X → World Boss` verificado y fin conservador del flow.
- `1814ddc`: la sonda de postcondición de sesión tolera frames transitorios, exige contexto limpio estable y sigue rechazando estados contradictorios.

Los cambios conservaron el principio común: espera/grace puede ser pasiva, pero ningún `UNKNOWN` habilita input o retry. Todo segundo input de las transiciones discretas permaneció protegido por una precondición fresca específica.

## Primer 28/28 combinado desde GUI

La sesión GUI con debug quedó en `logs/20260828T230015.529054Z_session_53bc461e.log` (archivo local gitignored). Se inició el 28 de agosto de 2026 a las 20:00:15 -03:00 y terminó a las 20:28:25 con `session.completed`, `runtime.completed` y cleanup `runtime.closed`.

Hechos derivados del log estructurado:

- 28/28 personajes iniciados y completados; 28/28 advances.
- 28 ejecuciones completas de Black Market y 28 de World Boss; cero `flow.failed`, `session.failed`, `runtime.failed` o eventos level `ERROR`.
- 38 business events agregados por los resultados: 23 `black_market.inventory_full`; World Boss produjo 10 `inventory_full`, 3 `bag_full` y 2 `insufficient_sapphires`.
- Black Market informó además 12 `black_market.no_gold` informativos. Trece personajes ejecutaron batalla World Boss completa con Auto Battle confirmado, espera completada, Raid Complete y Continue; los otros quince cerraron por un resultado de negocio conservador.
- Las 410 transiciones verificadas terminaron exitosas: 394 al primer intento y 16 después de un retry state-guarded. Los retries fueron Black Market `accept_purchase` ×6, `select_slot` ×3, `open` ×1 y `close` ×1; World Boss `open_selector` ×1, `open_battle_mode_select` ×1 y `continue_after_raid` ×2; Rotation `open_character_select` ×1.
- Las trece esperas finales de batalla terminaron `completed`; no hubo timeout, cancelación ni recovery no estructurado.
- Resultado final: `SessionStatus.COMPLETED`, `characters_processed=28`, `advances_completed=28`, technical failures = 0.

Este checkpoint quedó sobre `1814ddc`. El cierre documental reportó 921/921 tests, pero la auditoría posterior de colección demostró que `1814ddc`/`cf0aa4c` contienen 866 casos: no existieron 921 casos coleccionables en ese árbol. No hubo borrado posterior de 25 tests; el diff hasta `6a086e1` contiene 33 IDs añadidos y tres retirados por renombre, un neto de +30 hasta 896.

## Socket Inventory Relief — adquisición semántica

La campaña HIL del 29 de agosto de 2026 promovió el guard a semántica global `popup.socket_inventory_full` y verificó `World Boss → Yes → screen.socket → Back → World Boss`. El primer target inferido para Yes falló; Workbench registró el tap humano real `(0.433974, 0.640779)`, que luego reprodujo la transición. No se generalizó el retorno a otros callers.

Dentro de Socket se verificó que la ruta de ópalos es **Equipment Home**, no el filtro `[Legendary] Gem`. `Enhance All` distingue GOLD a la izquierda de KARATS a la derecha; sólo GOLD fue usado. Un merge positivo descontó `8.670.754` GOLD, produjo una secuencia oscura/flash/`SUCCESS!!` y regresó a Socket tras un tap en la región lateral segura alrededor de `(0.08, 0.50)`. La señal promovida exige fracción negra periférica alta y media central `≤26`; así separa las fases oscuras revisadas de Select Boss, Previous Rewards y cinco pantallas legacy oscuras. El flash brillante queda deliberadamente sin observación autorizante. Otro intento GOLD produjo `There is no material.`, confirmado como `NO_EFFECT`; OK volvió al modal Enhance All y X volvió a Socket. No se implementó aún ninguna primitive de taps.

Equipment Home mostró doce slots con velo rojo en la grilla 4×4. El asset histórico `opal-blocked.png` resultó robusto sobre el marcado completo pese al glow del sprite: positivos limpios `0,950..0,970`, negativo máximo revisado `0,526`. Seleccionar el primer slot rojo abrió Sell para `Opal (Skill)+0`; la ROI normalizada `(0.47, 0.39, 0.58, 0.45)` con escala 4 produjo lecturas consistentes y permitió verificar una única venta destructiva por `Sell (Bulk)`. El popup desapareció, Socket/Equipment Home permanecieron estables y el mismo slot dejó de contener el candidato rojo. El bubble transitorio de ~1 s y frame equality quedaron descartados como postcondición. Un ópalo `+10` se leyó inequívocamente y se canceló; luego se capturó ausencia de candidatos rojos. El indicador `1/30 → 1/27` se observó, pero no se promovió como conteo de items porque su semántica no quedó confirmada.

Producción incorporó assets current-season para título Socket normal/dimmed, Equipment Home, Enhance All, no-material y Sell Bulk; un detector row-major del velo rojo; una señal conservadora para fases oscuras tappable; y el Runtime Fact `item.socket.sell_level`, que exige `screen.socket + popup.socket_sell`, confidence OCR mínima `0,90` y consenso 2/3. La evaluación global descubrió que `SUCCESS!!` podía confundir el crop de texto histórico de Black Market; se reemplazó por el marco completo con espadas, cerrando el corpus ampliado en 168/168 resoluciones, cero wrong/ambiguous y overlays 168/168. Perception no elige estrategia ni autoriza venta: la futura support operation deberá exigir el slot rojo fresco, popup Sell, nivel confirmado exactamente `0` y postcondición estable del slot.

## Evaluación offline incremental

El evaluator productivo pasó a cachear observaciones/raw score por par detector×frame con fingerprints conservadores de frame, configuración, assets, código y runtime CV. Los labels y el resolver siguen evaluándose en cada corrida. Sobre 168 frames y 24 detectores, el full audit ejecutó 4.032 pares en 41,284 s; la repetición idéntica reutilizó 4.032/4.032, ejecutó cero matches y tardó 1,056 s. Ambos reportes fueron semánticamente idénticos: 168/168 resoluciones y overlays, cero wrong/ambiguous.

## Socket Inventory Relief — implementación y primer smoke

El checkpoint `6dafb22` añadió `TapThroughAnimation`, `SocketInventoryRelief` fuera del registry y la policy local de una única rama positiva por `WorldBossFlow.run()`. Enhance usa sólo GOLD; No Material habilita Equipment Home; Bulk sólo existe para un slot con velo rojo y `item.socket.sell_level == 0` confirmado; todo retorno exige un estado exacto. El checkpoint cerró 961/961 tests hardware-free y evaluator incremental 4.032/4.032 cache hits, cero wrong/ambiguous.

El primer smoke HIL leyó 24 sapphires, llegó a Socket Full y ejecutó Yes. El tap sí abrió Socket, pero el verifier abortó sobre un frame transitorio World Boss ya sin popup antes de que cargara el landmark Socket. El soporte continuó desde el Socket confirmado: Enhance GOLD produjo efecto, la animación necesitó 6 taps autorizados únicamente por fases oscuras, volvió a Socket, no ejecutó Sell y verificó Back a World Boss. La corrección posterior tolera ese frame World Boss sólo durante la espera de entrada; no lo convierte en retry guard ni permite otro Yes.

El usuario señaló que el chat dinámico puede cubrir el encabezado superior derecho usado como base Socket. Se lo reemplazó por el tab izquierdo persistente, con cuatro variantes selected/unselected y normal/dimmed sobre ROI `(0.16, 0.11, 0.26, 0.24)`. Diez positivos curados dieron raw `0.977370–1.0`; el máximo inicial de 158 negativos fue `0.713128`. Cinco capturas Socket legacy confirmaron persistencia espacial. Un frame live actual resolvió `screen.socket` con confidence `1.0`. Como `specs.py` participa del fingerprint compartido, la auditoría recalculó conservadoramente los 4.032 pares y cerró otra vez sin wrong/ambiguous.

Una captura legacy posterior aportada por el usuario delimitó el chat visible en la banda normalizada conservadora `(0.44, 0.12, 0.85, 0.21)`: interseca directamente la ROI anterior `(0.67, 0.08, 0.82, 0.18)` y queda completamente separada en X de la nueva. El frame pertenece a Meteorites y se incorporó como negativo curado; `landmark.socket_tab` obtuvo raw `0.469354`, confidence cero y ninguna emisión. El corpus pasó así a 169 frames y 159 negativos para ese detector. La evaluación incremental reutilizó 4.032 pares, calculó sólo los 24 del frame nuevo y cerró 4.056/4.056 sin wrong/ambiguous.

El smoke HIL No Material comenzó desde Socket abierto manualmente. Enhance GOLD produjo el popup esperado y el fallback llegó a Equipment Home. La selección amarilla alteró el template del velo rojo, por lo que se promovió una segunda apariencia del mismo `item.socket.incompatible_opal(slot)`; esto preserva el guard antes de Sell y evita un falso éxito posterior basado en la desaparición visual causada sólo por selección. Un sombreado más intenso de Enhance All requirió también una quinta apariencia del tab izquierdo. El corpus final de esta campaña quedó en 171 frames × 24 detectores, 4.104/4.104 pares, 171/171 resoluciones y overlays, cero wrong/ambiguous.

En el popup Sell, OCR confirmó dos veces `Opal (Skill)+0` con confidence `0,958`. Tras la confirmación humana específica se envió un único Bulk. La UI tardó brevemente: un frame Socket limpio apareció antes que Equipment Home estable y produjo un failure conservador inicial, aunque el usuario confirmó la venta y la evidencia pasiva mostró popup ausente, candidato previo ausente e inventario `1/29 → 1/28`. El verifier ahora tolera ese tránsito sólo como espera pasiva, jamás como éxito ni retry. No se ejecutó Back porque la entrada había sido manual y no existía un return plan World Boss válido para ese smoke.

No se fabricó live la segunda aparición de Socket Full: el usuario indicó que preparar ese caso extremo no era razonable. La regresión determinista conserva la policy de un solo permiso positivo por `WorldBossFlow.run()`, segundo popup por `No`, evento no fatal y cero segunda entrada a Socket; los logs productivos preservarán la primera ocurrencia natural.

## Daily Quests y Mailbox productivos

La adquisición HIL confirmó Daily Claim All positivo, no-op y reward independiente; Character Mail confirmó spinner con fases oscuras, transición Claim → Delete, Delete Read y leftovers por límites de recompensa. Se promovieron siete landmarks, una actividad derivada y 30 labels curados.

`DailyQuestsFlow` y `MailboxFlow` se integraron como `PER_CHARACTER` Lobby → Lobby al final del registry. Ambos usan intents tipados y waits frescos bounded con estabilidad, sin sleep como postcondición ni retries de Claim All. Mailbox registra el intento sin efecto y leftovers sin liberar recursos. Para preservar el contrato Lobby de Daily después de World Boss, el composition root conectó el normalizador ya previsto por `MinimalPreconditionEnsurer` a la ruta adquirida World Boss → Quick Menu → Lobby; `WorldBossFlow` y `SessionRunner` no cambiaron policy.

El cierre hardware-free pasó 1090 tests y el evaluator incremental reutilizó 13500/13500 pares sin invalidaciones, con 300/300 resoluciones correctas. No se hizo smoke adicional porque la adquisición live previa ya cubría targets/transiciones y las validaciones no dejaron dudas de hardware.

## Guild Check-In productivo

La adquisición HIL confirmó `screen.guild`, Attendance activo/completado, la transición a botón oscuro, `Lobby → Quick Menu → Guild` y Quick Menu abierto desde Guild con layout desplazado. El cambio visual completó en menos de 0,749 s dentro de la evidencia curada; el bubble quedó explícitamente excluido de la señal.

La implementación promovió targets normalizados para Guild en ambos layouts y para Attendance, añadió Guild a `quick_menu_accessible` y conectó una normalización exacta/verificada hacia `screen.guild`. `GuildCheckInFlow` permanece Guild → Guild: completed inicial es no-op, active habilita un solo tap y la completion exige estado completed fresco durante 0,75 s dentro de 10 s. No se añadieron retries de negocio, categories, routines ni un navigation graph.

## Decisiones y alternativas reemplazadas

- El icono de oro de Lobby describe un shell persistente, no una pantalla base exclusiva.
- `landmark.lobby_commerce_pair` quedó alternativa offline; producción usa Trading Center.
- El candidate anterior de Monster Wave no bastaba para Battle Mode Select; el slice World Boss lo reemplazó por un header current-season con corpus ampliado.
- La calibración empírica expresa posición dentro del gap observado, no probabilidad.
- Las sesiones raw o diagnósticas nunca se promueven automáticamente.
- La policy temprana del vertical slice aborta errores técnicos; no representa la policy unattended final.

## Registros relacionados

- `docs/semantic_census.md`: taxonomía legacy y Quick Menu.
- `docs/legacy/`: documentación 0.1 preservada.
- `datasets/*manifest.json`: ground truth curado y provenance reproducible.
- `CHANGELOG.md`: milestones de alto nivel.
- Git `4a14eee`: documentos hot completos previos a la compactación.
