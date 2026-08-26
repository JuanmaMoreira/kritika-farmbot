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

## Decisiones y alternativas reemplazadas

- El icono de oro de Lobby describe un shell persistente, no una pantalla base exclusiva.
- `landmark.lobby_commerce_pair` quedó alternativa offline; producción usa Trading Center.
- Battle Mode Select no se promovió por evidencia insuficiente.
- La calibración empírica expresa posición dentro del gap observado, no probabilidad.
- Las sesiones raw o diagnósticas nunca se promueven automáticamente.
- La policy temprana del vertical slice aborta errores técnicos; no representa la policy unattended final.

## Registros relacionados

- `docs/semantic_census.md`: taxonomía legacy y Quick Menu.
- `docs/legacy/`: documentación 0.1 preservada.
- `datasets/*manifest.json`: ground truth curado y provenance reproducible.
- `CHANGELOG.md`: milestones de alto nivel.
- Git `4a14eee`: documentos hot completos previos a la compactación.
