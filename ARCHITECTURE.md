# Arquitectura — Kritika FarmBot

Este documento distingue el sistema legacy que existe en el repositorio de la arquitectura objetivo 0.2. La segunda sección expresa responsabilidades y límites acordados; no implica que esas capas ya estén implementadas.

## Arquitectura legacy

La implementación preservada sigue aproximadamente este flujo:

```text
main.py
  → flow TOT
    → actions y matching directo
      → estado global de context.py
        → catálogo de constants.py
          → templates y coordenadas
      → antigua API de screen.py (retirada)
```

Responsabilidades reales:

- `bot/constants.py` mezcla configuración de host, resolución, taxonomía, templates, regiones, botones, offsets y políticas aún incompletas.
- `bot/screen.py` implementaba a la vez captura scrcpy, almacenamiento del frame, percepción por templates y comandos ADB. Desde Fase 1E conserva solamente matching OpenCV puro y transicional sobre un frame explícito.
- `bot/context.py` captura un frame y recorre templates hasta encontrar el primer contexto coincidente.
- `bot/actions.py` resuelve botones mediante estado global y coordenadas del catálogo.
- `bot/flows.py` contiene lógica TOT, percepción específica, regiones, thresholds y acciones físicas.
- `bot/ads_manager.py` es un programa standalone basado en UIAutomator2.
- `main.py` no contiene un loop general: conecta el dispositivo e intenta ejecutar exclusivamente TOT.

Problemas estructurales confirmados:

- captura, percepción e input están acoplados;
- el contexto depende directamente de templates;
- actions depende de globals y coordenadas;
- flows contiene percepción y dependencias directas de la API de input retirada;
- la geometría no usa de forma confiable las dimensiones landscape del frame;
- prioridad y outcomes están modelados pero no configurados efectivamente;
- el runtime legacy no es importable en su estado preservado;
- el entry point y sus módulos legacy ya no importan porque siguen solicitando esa API retirada.

El uso de scrcpy, OpenCV o ADB no es por sí mismo legacy. Lo legacy es el acoplamiento que obliga a representar cada estado y transición mediante templates y coordenadas mantenidos manualmente.

## Arquitectura objetivo 0.2

```text
Capture
  ↓
Perception
  ↓
Semantic Observations
  ↓
ContextResolver
  ↓
Flows / Decision
  ↓
ActionExecutor
  ↓
Device / ADB
```

## Fundamentos implementados en Fase 1A

La primera porción implementada de 0.2 permanece desacoplada del runtime legacy:

- `bot/config.py` contiene `RuntimeConfig`, un objeto inmutable para configuración de host y runtime. Puede construirse explícitamente y solo consulta environment o dotenv cuando se invoca `from_env()`; no inicia infraestructura al importarse.
- `bot/geometry.py` contiene conversiones puras de puntos y regiones normalizados. Las dimensiones visuales proceden de `frame.shape`, cuyo orden es `(height, width, ...)`.
- Los puntos representan índices de píxel: usan floor y el extremo normalizado `1` se satura al último índice válido. Las regiones representan límites de slicing con extremo final exclusivo, por lo que la región completa termina en `(width, height)`.
- `adb shell wm size` puede conservarse como metadata, diagnóstico o validación auxiliar, pero no puede decidir la geometría de un frame capturado.

Estos módulos son consumidos por el núcleo 0.2, las herramientas de captura y los helpers visuales transicionales. `constants.py`, `ads_manager.py` y los flows todavía no migraron. La suite automatizada vive exclusivamente en `tests/`; el antiguo directorio `testing/` fue retirado en Fase 1E.

## Composition root y validación real

La Fase 1D añadió `bot/runtime.py` como composition root mínimo. `build_adb_client(config)` y `build_frame_source(config, adb_client=...)` ensamblan el núcleo 0.2 de forma explícita y no ejecutan operaciones externas. La carga de environment/dotenv continúa siendo responsabilidad del caller.

`tools/smoke_capture.py` es una entrada diagnóstica separada de pytest y del runtime legacy. Carga configuración solo dentro de `main()`, comprueba ADB, recibe cinco snapshots distintos y valida ndarray BGR `uint8`, shape, landscape, sequence y timestamps. Usa el context manager de captura y verifica después que el forward utilizado fue retirado.

La validación física con scrcpy-server 3.3.4 confirmó el stack completo con frames `(1224, 2712, 3)`. También cerró una diferencia respecto de la extracción legacy: en H.264, los packets de configuración SPS/PPS se retienen y se anteponen al siguiente media packet antes de enviarlo a PyAV.

### Capture

Obtiene frames landscape desde scrcpy y expone sus dimensiones reales. No reconoce contextos ni toma decisiones.

La Fase 1C implementó esta responsabilidad en `bot/capture.py`. `ScrcpyFrameSource` recibe un `AdbClient` y el path de `scrcpy-server.jar`, prepara el server y el port forwarding, mantiene el proceso ADB y socket, decodifica H.264 con PyAV y publica el frame BGR más reciente. Su API pública es `start()`, `get_frame()`, `stop()`, `is_running`, `failure` y context manager.

Cada `FrameSnapshot` contiene una copia del ndarray, timestamp monotónico y sequence number. Sus dimensiones se consultan desde el shape de esa imagen; la metadata de scrcpy y `adb wm size` no sustituyen esa fuente de verdad. Un `Event` permite cancelar el receptor y los timeouts de socket evitan bloquear el shutdown indefinidamente. Los fallos del thread se conservan y quedan visibles al owner.

La fuente es dueña del lifecycle de socket, decoder, proceso y forward, incluido cleanup best-effort ante startup parcial. `AdbClient` solo construye el proceso persistente mediante `spawn_shell()` y devuelve su handle. Desde Fase 1E es la única implementación activa del protocolo scrcpy: `tools/asset_capture.py` y `tools/screencap_batch.py` la construyen mediante el composition root y no abren sockets, procesos ADB ni decoders propios.

### Perception

La Fase 3A implementó la primera porción productiva de esta capa bajo `bot/perception/`. `PerceptionEngine` recibe una tupla explícita de detectores que cumplen `detect(frame)`, los ejecuta en orden y agrega cero, una o varias observations por detector. Su salida termina en `ObservationBatch`: preserva la identidad del `FrameSnapshot` y no invoca al resolver ni conserva contexto, historial o estado temporal.

El backend actual es `LocalCvDetector`. Cada instancia representa un único landmark, carga y valida su PNG durante construcción y conserva una copia grayscale preparada para todos los frames posteriores. Importar el package no abre assets y `build_default_perception()` crea una composición nueva, no un singleton. El matching a tamaño nativo reutiliza `bot.screen.template_match_score()` con el template precargado; la region normalizada se convierte desde las dimensiones reales del ndarray mediante `bot.geometry`. Un template incompatible con el crop del frame produce un error explícito y no dispara scaling implícito.

`LocalCvDetection` mantiene separados `raw_match_score` y `semantic_confidence`. `LinearGapCalibration` mapea linealmente el máximo negativo confirmado a `0` y el mínimo positivo confirmado a `1`, con clamp fuera del intervalo. Esa confidence sólo expresa posición en el gap empírico de la muestra 2D y no es una probabilidad. El detector omite evidence con confidence `0`; no aplica el threshold semántico `0.80`, que sigue siendo policy exclusiva del `ContextResolver`.

Desde Fase 3C, las specs productivas contienen exclusivamente:

| Observation | Asset | Region validada | Gap empírico provisional |
|---|---|---|---|
| `landmark.lobby_trading_center_label` | `assets/ui/landmarks/lobby-trading-center-label.png` | `(0.19095870206489673, 0.905032679738562, 0.29761061946902656, 0.9822222222222222)` | `0.4657268226146698 → 0.7198567986488342` |
| `landmark.character_select_header` | `assets/ui/landmarks/character-select-header.png` | `(0.40297935103244836, 0.02676470588235294, 0.5852212389380531, 0.11212418300653594)` | `0.2443815916776657 → 0.43373382091522217` |
| `landmark.black_market_title` | `assets/ui/black-market-id.png` | `(0.4395, 0.0997, 0.5579, 0.1495)` | `0.2230203002691269 → 0.997641384601593` |
| `landmark.purchase_confirmation_prompt` | `assets/ui/black-market-purchase-confirmation-id.png` | `(0.4624, 0.4828, 0.5376, 0.5294)` | `0.48758167028427124 → 0.9959162473678589` |

Los dos assets promovidos son copias exactas de los candidates evaluados bajo `artifacts/`; esos artifacts no son dependencias runtime. El detector de Lobby consume únicamente el rótulo `Trading Center`: no usa oro, una conjunción ni fallback a la franja amplia. Su separación está validada contra el corpus actual, no contra un conjunto controlado multi-season; un cambio de season exige nuevos positives humanos y recalibración. Character Select usa el rendering actual validado y no el asset legacy con overlap.

No existe todavía detector productivo para Battle Mode Select ni otros estados. Su `ContextRule` permanece disponible, de modo que sin otra señal productiva esos frames resuelven `UNKNOWN`. OCR y el fallback VLM tampoco están implementados. Cuando se incorporen, deberán respetar el mismo límite de detector; VLM permanecerá provider-agnostic y ninguna capa superior dependerá de un proveedor, API o modelo específico.

### Semantic Observations

La Fase 2A implementó esta frontera mediante contratos inmutables y puramente estructurales:

- `Observation` representa un hecho semántico con nombre namespaced, confianza normalizada, categoría de origen, valor escalar opcional y una `RelativeRegion` opcional.
- `ObservationSource` expresa categorías extensibles (`LOCAL_CV`, `OCR`, `VLM`, `SYSTEM`), no proveedores, modelos, templates ni motores concretos.
- `ObservationValue` se limita a `bool`, `int`, `float`, `str` o `None`; frames, crops y objetos de detector no atraviesan esta frontera.
- `ObservationBatch` asocia una colección ordenada de evidencia con el `sequence` y `timestamp` de un único frame lógico, pero no retiene el ndarray.
- Un batch preserva observaciones repetidas e independientes. `find(name)` devuelve todas y `best(name)` ofrece sólo una conveniencia por confianza reportada; no constituye una política de fusión.

Las ubicaciones permanecen normalizadas en `[0,1]` y con área positiva. `bot/geometry.py` expone `normalize_relative_region()` para compartir esa validación sin convertirlas todavía en targets de acción ni coordenadas pixel.

### ContextResolver

La Fase 2B implementó `bot/resolver.py` como motor puro para transformar un `ObservationBatch` en `ResolvedState`. Se construye con tuplas explícitas de `ContextRule` para contextos base y overlays; no contiene catálogo de Kritika, imports legacy, percepción, IO ni estado temporal.

Una `ContextRule` declara un nombre de resultado, requirements semánticos únicos y un threshold común. Para cada requirement, `match_rule()` consulta la observación de mayor confidence de ese nombre. La fuente y región permanecen disponibles en la evidencia, pero no alteran el resultado. Las confidences no se suman, promedian, votan ni ponderan entre fuentes no calibradas.

Una regla sólo coincide si todos sus requirements alcanzan el threshold inclusivo. El `RuleMatch` diagnóstico conserva la regla y exactamente una observación seleccionada por requirement; su confidence es el mínimo conservador de esas evidencias y no una probabilidad estadística.

La resolución base aplica estas reglas sin first-match ni prioridades:

- cero candidatos producen `UNKNOWN`;
- un candidato produce `RESOLVED`;
- varios candidatos distintos producen `AMBIGUOUS`, aun si sus confidences difieren.

Reglas, candidatos y overlays se normalizan por nombre para que el orden de inyección no decida semántica. Los overlays se evalúan independientemente y todos los que coinciden se conservan, incluso con base `UNKNOWN` o `AMBIGUOUS`; no existe ambigüedad ni prioridad propia de overlays en esta fase.

La Fase 2A sí definió su contrato de salida en `bot/state.py`. `ResolvedState` conserva la identidad `sequence`/`timestamp` del batch y separa:

- `base_context`, que sólo está seleccionado para un resultado `RESOLVED`;
- un `subcontext` opcional y explícito, sin jerarquías arbitrariamente profundas;
- cero o más `overlays`, independientes del contexto base;
- `base_candidates` conflictivos para un resultado `AMBIGUOUS`.

`ResolutionStatus.UNKNOWN` es first-class: la imposibilidad de resolver el contexto base no es una excepción y aun puede coexistir con overlays conocidos. La policy de subcontexto permanece pendiente y el resolver de 2B produce siempre `subcontext=None`. Tampoco implementa hysteresis, debounce, historial, transiciones ni voting entre frames.

### Catálogo semántico mínimo

La Fase 2C añadió `bot/catalog.py` como configuración semántica productiva separada del motor genérico. Su API pública es `BASE_CONTEXT_RULES`, `OVERLAY_RULES`, `SEMANTIC_OBSERVATION_NAMES` y `build_default_resolver()`. No importa `constants.py`, assets ni capas de percepción.

Después de la promoción 3C, el catálogo productivo contiene cuatro reglas base y un overlay. El oro dejó de formar parte del vocabulary productivo; su referencia se conserva sólo como trazabilidad histórica en tooling y documentación:

| Resultado semántico | Tipo | Requirement | Referencia legacy | Región legacy | Threshold legacy |
|---|---|---|---|---|---|
| `screen.lobby` | base | `landmark.lobby_trading_center_label` | candidate 3B.1 curado | `(0.19095870206489673, 0.905032679738562, 0.29761061946902656, 0.9822222222222222)` | — |
| `screen.character_select` | base | `landmark.character_select_header` | candidate 3B curado | `(0.40297935103244836, 0.02676470588235294, 0.5852212389380531, 0.11212418300653594)` | — |
| `screen.battle_mode_select` | base | `landmark.monster_wave_entry_title` | `survival` / `assets/ui/survival-id.png` | `(0.1707, 0.2337, 0.2994, 0.2974)` | `0.85` |
| `screen.black_market` | base | `landmark.black_market_title` | `black-market` / `assets/ui/black-market-id.png` | `(0.4395, 0.0997, 0.5579, 0.1495)` | `0.85` |
| `popup.purchase_confirmation` | overlay | `landmark.purchase_confirmation_prompt` | `black-market-purchase-confirmation` / `assets/ui/black-market-purchase-confirmation-id.png` | `(0.4624, 0.4828, 0.5376, 0.5294)` | `0.85` |

Esta tabla es trazabilidad histórica, no configuración runtime. Los landmarks describen señales visibles; no prescriben template matching y podrían provenir de cualquier backend futuro.

Todas las `ContextRule` usan `SEMANTIC_CONFIDENCE_THRESHOLD = 0.80`. Es una policy uniforme y provisional sobre confidence reportada, distinta del threshold de matching legacy de la tabla. La evaluación 2D no definió ninguna conversión desde score OpenCV a esa confidence.

Las cinco rules tienen conjuntos mínimos de evidence distintos y por ello no generan solapamiento estructural. Proporcionar simultáneamente landmarks de dos bases sigue produciendo `AMBIGUOUS`, como exige el resolver. El overlay de confirmación coexiste con `screen.black_market` y no reemplaza la base.

La regla de `screen.lobby` introducida inicialmente en 2C fue retirada hasta 3C: inspección visual confirmó que `lobby-id.png` contiene un icono de moneda, no un header, y la muestra humana encontró scores cercanos a `1.0` en Black Market y otros contextos. Fase 3B.1 aclaró que se trata de una señal posicional real del shell de Lobby, pero ese shell permanece visible bajo modales y Black Market; por tanto no puede resolver por sí solo el contexto base definido por la taxonomía actual. Fase 3C restauró la regla con el rótulo `Trading Center`, que sí separa el corpus confirmado. `survival-id.png` contiene “Monster Wave” dentro de “Select Battle Mode”, por lo que tanto el landmark como su resultado se corrigieron. El prompt “Purchase?” también aparece en Guild Shop; su semántica de overlay ahora es independiente de Black Market.

TOT no se incorporó: aunque `flow_tot()` consume `lobby → survival → tot`, los assets `tot-id.png` y sus subcontextos físicos/mágicos no están entre los assets runtime activos y la entrada conserva coordenadas pixel legacy. `bag-full-alert` tampoco se incorporó porque su comentario legacy cuestiona si representa siempre el mismo tipo de inventario lleno. No se inventaron señales para cubrir esos huecos.

### Validación offline del slice

La Fase 2D añadió tooling de evaluación, no una capa Perception. `template_match_score()` en `bot/screen.py` recibe un frame explícito, un template y una region opcional, y devuelve el máximo crudo de `TM_CCOEFF_NORMED`. `tools/semantic_slice_evaluation.py` usa esa primitiva para inventario, matriz completa, selección determinista y estadísticas; `tools/review_semantic_slice.py` solamente facilita labels humanos. Los resultados completos viven bajo `artifacts/`, ignorado por Git, y el manifest pequeño conserva paths relativos sin imágenes.

La corrida histórica cubrió 173 PNG `2712×1224`, 865 mediciones compatibles y 27 frames confirmados manualmente. Todas las regions eran relativas y se convirtieron mediante `bot.geometry`; no hubo fallback full-frame ni scaling. Los assets a tamaño nativo produjeron separación fuerte para Black Market y confirmación de compra, evidencia prometedora pero escasa para Character Select y Monster Wave, y solapamiento semántico para el icono de moneda bajo estados superpuestos al shell de Lobby. Estas mediciones caracterizan únicamente el dataset histórico y no establecen thresholds productivos ni semantic confidence.

Fase 3A reprodujo los scores de los dos landmarks validados sobre las 173 capturas para fijar sus anchors provisionales y añadió `tools/production_perception_evaluation.py`. Esta segunda evaluación ejecuta el pipeline productivo sobre las 27 entradas confirmadas y luego pasa cada batch por `build_default_resolver()`. Obtuvo 6 TP de Black Market y 3 TP de Purchase Confirmation, cero FP, cero FN, 27/27 resoluciones esperadas y cero estados ambiguos. Incluyó dos casos `screen.black_market` + overlay y un caso `UNKNOWN` + overlay, confirmando que el prompt de compra permanece genérico.

### Adquisición dirigida y candidates de Fase 3B

`tools/capture_semantic_dataset.py` extiende adquisición sin crear otra implementación de scrcpy o ADB. El composition root permanece `RuntimeConfig → build_frame_source() → ScrcpyFrameSource`; el usuario selecciona explícitamente una de las tres labels y `SPACE` guarda el `FrameSnapshot.image` completo como PNG. La similitud entre capturas consecutivas de la misma label es únicamente diagnóstica y nunca decide el ground truth.

Las 30 capturas nuevas viven bajo `screencaps/semantic/` e ignoradas por Git. `datasets/semantic_acquisition_manifest.json` usa el mismo núcleo versionado del manifest 2D (`path`, `base_context`, `overlays`, `review_status`) y agrega metadata de adquisición no sensible. `tools/semantic_candidate_evaluation.py` fusiona manifests humanos, rechaza conflictos, permite crops experimentales interpretables y evalúa únicamente `raw_match_score`; sus thresholds de clasificación son policy offline explícita, no calibration productiva.

La evaluación combinada cubrió 57 frames confirmados: 27 históricos y 30 nuevos. Los artefactos de candidate permanecen bajo `artifacts/` y no se incorporaron a `assets/ui/`, `bot/perception/specs.py` ni `build_default_perception()`.

| Señal evaluada | Positivos / negativos | Positivo min/median/max | Máximo negativo | Gap | Estado 3B |
|---|---:|---:|---:|---:|---|
| Asset legacy Character Select | 12 / 45 | `0.4343 / 0.4413 / 1.0000` | `0.4921` | `-0.0578` | NEEDS_REWORK |
| Candidate actual Character Select | 12 / 45 | `0.4337 / 0.9899 / 1.0000` | `0.2444` | `0.1894` | VALIDATED |
| Asset legacy Monster Wave | 11 / 46 | `0.3480 / 0.3486 / 1.0000` | `0.4000` | `-0.0520` | NEEDS_REWORK |
| Candidate actual Monster Wave | 11 / 46 | `0.3817 / 0.9997 / 1.0000` | `0.3538` | `0.0278` | PROMISING |
| Candidate Lobby: `Shop / Black Market / Trading Center` | 11 / 46 | `0.7178 / 0.9862 / 1.0000` | `0.4514` | `0.2664` | VALIDATED |

El candidate elegido inicialmente para Lobby usa los tres rótulos comerciales de la esquina inferior izquierda. Se prefirió al crop más amplio de la misma franja —que obtuvo un gap mayor pero incorporaba más personajes y animación— por ser visualmente más acotado e interpretable. La columna `Stage / Survival / Battle` también separó la muestra, mientras `Time Rewards` quedó `NEEDS_REWORK` por solapamiento. Fase 3B.1 volvió a reducir la señal para limitar su exposición a retratos y fondo.

Los diez nuevos frames Battle Mode Select conservaron visible `Monster Wave`, pero nueve diferencias consecutivas cayeron bajo el aviso de near-duplicate; esto demuestra estabilidad en una UI estática, no diversidad suficiente de variantes. Por eso el candidate actualizado no se promueve pese a no producir errores en el operating point diagnóstico.

La regresión de los dos detectores productivos existentes sobre los 57 labels mantuvo 6/6 Black Market y 3/3 Purchase, cero FP/FN y 57/57 resoluciones correctas. Fase 3B no definió confidence, anchors ni thresholds de ContextRule para los candidates.

### Reevaluación de Lobby de Fase 3B.1

La reevaluación fue exclusivamente offline y reutilizó los mismos 57 labels confirmados. `lobby-id.png` mide `51×47`. La región normalizada legacy equivale a `(552, 36, 660, 110)` sobre los frames landscape; el código de `legacy-pre-hybrid`, en cambio, la escalaba con el orden portrait reportado por `adb wm size`, de modo que su crop efectivo era `(249, 81, 297, 243)`. La arquitectura 0.2 conserva la intención correcta al derivar dimensiones de `frame.shape`.

Los matches positivos del oro ocuparon `x=565` y `y=49` o `61`. El sobre mínimo que incluye esos matches, `(565, 49, 616, 108)`, es el único ajuste de región ensayado porque deriva directamente de las posiciones confirmadas; no produjo separación. Los negativos más altos conservaron el icono exactamente en `(565, 49)` dentro de Quests, Trading Center, Item Trade y Black Market superpuestos al Lobby.

| Señal Lobby reevaluada | Positivos / negativos | Positivo min/median/max | Máximo negativo | Gap | Riesgo estacional esperado |
|---|---:|---:|---:|---:|---|
| Franja comercial amplia 3B | 11 / 46 | `0.7124 / 0.9787 / 1.0000` | `0.2274` | `0.4851` | Alto: incluye retratos, animación y fondo |
| Tres rótulos comerciales 3B | 11 / 46 | `0.7178 / 0.9862 / 1.0000` | `0.4514` | `0.2664` | Medio: todavía conserva partes de retratos y fondo |
| `Trading Center` aislado | 11 / 46 | `0.7199 / 0.9826 / 1.0000` | `0.4657` | `0.2541` | Bajo-medio por diseño: rótulo y backing GUI |
| `Black Market + Trading Center` aislados | 11 / 46 | `0.6503 / 0.9833 / 1.0000` | `0.3629` | `0.2874` | Bajo-medio, pero abarca dos rótulos y más superficie |
| Oro en región legacy landscape | 11 / 46 | `0.9686 / 0.9721 / 1.0000` | `0.9882` | `-0.0196` | Bajo visualmente, pero no es exclusivo del contexto base |
| Oro en sobre posicional ajustado | 11 / 46 | `0.9686 / 0.9721 / 1.0000` | `0.9882` | `-0.0196` | Igual que el anterior; el ajuste no elimina el solapamiento |

Para 3C, la señal primaria recomendada es `landmark.lobby_trading_center_label`: es el crop validado de menor superficie que excluye retratos y conserva un gap fuerte. `landmark.lobby_commerce_pair` queda como alternativa experimental por su gap algo mayor, no como segundo requirement. Exigir simultáneamente `landmark.lobby_currency_anchor` no reduce errores en el dataset frente al rótulo comercial solo y agrega un punto de fallo; el oro puede conservarse como evidencia diagnóstica del shell subyacente, no como regla de `screen.lobby`.

Estos estados VALIDATED describen únicamente la separación en el corpus actual. Sus fondos visualmente diferentes no forman una campaña multi-season controlada. La robustez estacional asignada en la tabla es una expectativa de diseño basada en qué píxeles consume cada crop, no una validación empírica entre temporadas.

Fase 3C amplió el evaluator productivo existente, sin duplicarlo, para fusionar y deduplicar los dos manifests humanos. La corrida sobre 57 frames confirmó los cuatro gaps productivos y produjo 57/57 estados esperados, cero ambigüedades y cero resoluciones incorrectas. Lobby obtuvo 11/11 y Character Select 12/12; Black Market conservó 6/6 y los tres Purchase overlays conservaron 3/3. Battle Mode Select quedó 11/11 `UNKNOWN` deliberadamente y los otros 17 contextos también permanecieron `UNKNOWN`. Los anchors 3A no cambiaron porque las capturas nuevas no añadieron extremos.

### Diagnóstico live de Fase 3D

`tools/smoke_perception.py` es un composition root diagnóstico manual, no un runtime general. Construye explícitamente configuración, ADB, captura, los cuatro detectores productivos y el resolver; el loop consume únicamente snapshots con sequence nuevo, a aproximadamente 3 análisis por segundo, y conserva siempre el frame más reciente sin backlog. Su lifecycle pertenece al context manager de `ScrcpyFrameSource` también ante `Ctrl+C`, error o cierre normal.

La herramienta mantiene fuera de los contratos productivos dos responsabilidades puramente diagnósticas: consulta `LocalCvDetector.measure()` después de ejecutar el pipeline real para mostrar raw OpenCV score, y acumula latencia/confidence/rachas por una etapa marcada manualmente. No modifica `Observation`, no etiqueta ground truth, no retiene contexto previo y no aplica hysteresis, debounce, voting ni scheduler. El usuario sigue siendo responsable de la navegación y la herramienta no contiene comandos Android de input.

La primera corrida real cubrió el pipeline completo con frames `2712×1224`. Lobby, Character Select, reentrada a Lobby y un contexto unsupported se comportaron conforme al diseño stateless. Black Market y Purchase Confirmation no alcanzaron sus calibraciones offline en la apariencia live, aunque el crop del prompt sí mostró un aumento raw al abrir el popup. Esto es una discrepancia de evidencia entre dataset y hardware, no una razón arquitectónica para introducir temporalidad o bajar thresholds: se requieren capturas current-season human-confirmed y reevaluación offline antes de modificar specs productivas.

## Perception Workbench — tooling humano de desarrollo

Fase 3E añade una composición paralela de enseñanza y mantenimiento, deliberadamente fuera del runtime de gameplay:

```text
ScrcpyFrameSource → PerceptionEngine → ContextResolver
          │                    │               │
          └────────────────────┴───────────────┴→ Perception Workbench UI

Android touchscreen → HumanInputObserver ─────────→ Perception Workbench UI
```

`bot/human_input.py` implementa exclusivamente la dirección `HUMAN → system observation`. Descubre mediante `adb shell getevent -pl` un dispositivo que exponga `ABS_MT_POSITION_X` y `ABS_MT_POSITION_Y`, conserva sus rangos inclusivos reales y posee un proceso persistente `getevent -lt` creado por `AdbClient.spawn_shell(capture_output=True)`. No conoce gameplay, no ejecuta input y no constituye un `ActionExecutor` alternativo. La selección es determinista por capacidades táctiles, área del sensor y path; el path concreto nunca se hardcodea ni se persiste como identidad.

Los timestamps impresos por `getevent` pertenecen al `CLOCK_MONOTONIC` del teléfono, mientras `FrameSnapshot` usa el monotónico del host; no son comparables aunque ambos sean monotónicos. `HumanInputObserver` reestampa cada evento al recibirlo con el reloj host y sólo ese valor se usa para asociación con frames, duración y UI. El parser v1 reconstruye contacto down, movimiento y up; una tolerancia relativa configura la frontera tap/swipe. Multitouch e interacciones incompletas se preservan como `UnknownGesture`, sin inventar semántica de elemento.

Las coordenadas humanas persistidas son relativas a display y pertenecen a `[0,1]`. Primero se normalizan desde `axis min/max`; luego se aplica la rotación Android encontrada en `dumpsys input`: `0 → (x,y)`, `90° → (y,1-x)`, `180° → (1-x,1-y)`, `270° → (1-y,x)`. Esta política sigue la transformación documentada por [AOSP para touch devices](https://source.android.com/docs/core/interaction/input/touch-devices) y el formato/timestamp de [AOSP getevent](https://source.android.com/docs/core/interaction/input/getevent). Sólo después se proyecta el punto relativo al frame usando `frame.shape`; `adb wm size` no participa. El overlay temporal de tap/swipe se dibuja sobre una copia de UI y nunca sobre la imagen guardada.

`tools/perception_workbench.py` compone explícitamente `RuntimeConfig`, `AdbClient`, `ScrcpyFrameSource`, `build_default_perception()`, `build_default_resolver()` y `HumanInputObserver`. La UI OpenCV deriva dinámicamente base contexts y overlays de las reglas del resolver. El ground truth humano permanece activo hasta ser cambiado, está marcado `human_confirmed` y nunca se completa a partir de una prediction.

La evidencia se selecciona por mismatch, `AMBIGUOUS`, input humano, guardado manual o modo representative. Un fingerprint grayscale `32×32`, cooldown de 2 s, diferencia media mínima de 3 niveles, refresh máximo de 8 s y límite de 12 ejemplos automáticos por key reducen near-duplicates sin clustering. Un ring buffer de 24 frames analizados asocia el frame más cercano anterior al inicio del gesto y un frame posterior al fin con delay nominal de 0,5 s; al cerrar, una interacción pendiente usa el último frame disponible y conserva las secuencias, sin inferir una transición semántica.

La primera sesión humana de 3E se abortó por preview degradada y lag extremo. La auditoría demostró que los PNG originales ya contenían macroblocking antes de render: un mismo ndarray BGR `2712×1224` evaluado por `tools.smoke_perception.analyze_snapshot()` y el path Workbench produjo raw scores exactamente iguales y conservó su hash. El defecto no provenía de resize, overlay ni composición. La combinación de stream `2 Mbps` sin límite de FPS, render/copia repetidos aunque no hubiera frame nuevo y PNG full-frame síncrono añadía presión suficiente para degradar/atrasar el stream y bloquear UI. Esa sesión `20260823T054558_979538Z-46e40344` es diagnóstica y no curable/promovible.

Workbench usa ahora scrcpy a `8 Mbps / 30 fps`, analiza sólo el snapshot más reciente y acepta gaps de sequence como descarte intencional de frames intermedios. Perception recibe siempre `FrameSnapshot.image` original; la UI copia primero y sólo la copia se dibuja/redimensiona a `1356×612`, exactamente la mitad de `2712×1224` y con el mismo aspect ratio. El canvas se reconstruye únicamente ante un análisis/evento/cambio visible. Un único evidence writer con queue acotada de 16 realiza PNG/JSONL fuera del loop; si se satura, registra `evidence.skipped` en vez de formar backlog ilimitado. La UI muestra source sequence, frame age, perception, UI/display, evidence-save y profundidad de queue. `--compare-once` captura un frame y prueba igualdad de raw scores/hash entre los paths 3D y Workbench antes de un smoke.

Cada sesión raw vive bajo `artifacts/workbench/<session-id>/` —ya ignorado por Git— con `events.jsonl`, `frames/` y `summary.json`. Los eventos comparten `schema_version`, `session_id`, `event_type`, timestamp UTC y payload extensible; los eventos humanos agregan timestamp monotónico, coordenadas normalizadas y raw diagnostics. No se persisten serial ADB, paths absolutos ni identidad de usuario/dispositivo. Los manifests versionados de `datasets/` siguen siendo la única fuente curated; promover evidencia raw será trabajo posterior.

El smoke final de 3E confirmó preview prácticamente live, igualdad de raw scores con el path 3D, ground truth base/overlay editable, deduplicación acotada, writer sin backlog y cleanup completo. Los marcadores de taps en sectores diversos y de un swipe coincidieron visualmente con las acciones físicas según validación humana; todas las interacciones conservaron frames before/after. Black Market y Purchase Confirmation quedaron capturados como falsos negativos actuales sin recalibrar detectores. La primera sesión degradada permanece exclusivamente diagnóstica y ninguna sesión raw se promovió automáticamente.

El Workbench es una herramienta humana de desarrollo y enseñanza. El producto final continúa siendo un runtime automatizado unattended; ninguno de los estados persistentes, hotkeys o decisiones del Workbench pertenece por defecto a ese producto.

## Dirección del producto final — Session Orchestrator

El objetivo no es un agente general que elija libremente qué jugar. La dirección acordada es un orquestador configurable:

```text
User Control Panel
  → SessionPlan
    → SessionRunner
      → Characters
        → Selected Flows
```

El usuario seleccionará previamente flows como `query_resources_type_1`, `clean_friends`, `farm_tot`, `farm_elite` o `farm_arena`. En Kritika la mayoría son `PER_CHARACTER`, pero el modelo futuro deberá exigir scopes explícitos y no suponer que todo flow comparte ese alcance.

Un top-level flow declarará prerequisites en lugar de invocar recursivamente otros flows de forma arbitraria. El patrón previsto es `check → bounded support operation → recheck → continue/skip/fail`. Operaciones como `acquire_sapphires`, `buy_stamina` o `empty_inventory` podrán ser mini-flows internos, pero no se confundirán con los flows principales seleccionables. `RequirementRunner`, `SessionPlan` y `SessionRunner` todavía no están implementados.

Las sesiones de producto deberán correr unattended durante horas. El diseño posterior necesita timeouts, recovery, logging, resultados explícitos, aislamiento de fallos, cleanup y política para continuar con el siguiente flow o personaje.

También se preserva una distinción futura: los runtime facts (`stamina`, inventario, attempts) sirven para decisiones inmediatas y no exigen persistencia; los informational snapshots de currencies/resources se actualizan mediante flows explícitos de consulta y no constituyen una réplica autoritativa, porque el usuario también juega manualmente. Fase 3E no implementa OCR ni almacenamiento de esos valores.

### Flows / Decision

Contienen intención y reglas de negocio deterministas. Solicitan acciones semánticas y reaccionan a estados resueltos; no hacen template matching ni llaman a ADB.

### ActionExecutor

Traduce una intención de acción validada a interacción con el dispositivo. La resolución geométrica debe usar el frame landscape real y coordenadas normalizadas en `[0,1]` cuando corresponda.

### Device / ADB

Es el límite de infraestructura para taps, swipes y demás comandos del dispositivo. Debe poder sustituirse por un fake en tests normales.

La Fase 1B implementó este límite en `bot/adb.py`. `AdbClient` recibe explícitamente el ejecutable ADB y el serial, y concentra la ejecución en primitivas `subprocess` con argumentos separados, timeout y traducción a `AdbError`/`AdbTimeoutError`. Expone `get_state`, `shell`, input en coordenadas pixel, push y administración de port forwarding. La extensión `spawn_shell()` de Fase 1C crea un proceso persistente sin apropiarse de su lifecycle.

`AdbClient` no conoce frames, resolución, coordenadas relativas, percepción ni acciones semánticas. Puede construirse desde los campos ADB de `RuntimeConfig`, pero no retiene configuración de scrcpy o del juego. Desde Fase 1E es el único límite activo de procesos ADB; `bot/screen.py` ya no captura, conecta ni ejecuta taps o swipes.

## Cierre del núcleo reutilizable — Fase 1E

`bot/screen.py` permanece con nombre legacy solo como módulo transicional de visión. Expone `template_match_score()`, `find_image_on_screen()` y `find_all_on_screen()`, recibe el ndarray explícitamente, calcula regiones normalizadas desde `frame.shape` y no consulta globals, dispositivo ni configuración. `template_match_score()` acepta además un template grayscale precargado para que Perception reutilice la misma primitiva sin IO por frame. Fase 3A conserva deliberadamente el tamaño nativo validado; scaling seguirá requiriendo evidencia runtime antes de diseñarse.

Los consumers legacy `main.py`, `bot/context.py`, `bot/actions.py` y `bot/flows.py` conservan imports de captura/input ya retirados. No se añadieron shims: no forman parte del runtime activo y repararlos implicaría migrar resolución semántica, ejecución de acciones y flows fuera del alcance de Fase 1. El tag `legacy-pre-hybrid` conserva su implementación anterior.

Las herramientas activas quedan delimitadas así:

- `tools/smoke_capture.py`: diagnóstico opt-in sin escritura de frames ni input físico;
- `tools/smoke_perception.py`: diagnóstico end-to-end manual de captura, observations y resolución, con métricas stateless y sin acciones;
- `tools/screencap_batch.py`: adquisición interactiva de capturas mediante `ScrcpyFrameSource`;
- `tools/asset_capture.py`: curación de templates/regiones desde carpeta o desde la misma fuente 0.2;
- `tools/semantic_slice_evaluation.py`: evaluación reproducible y offline de raw template scores;
- `tools/review_semantic_slice.py`: revisión humana local del subconjunto seleccionado.
- `tools/production_perception_evaluation.py`: evaluación offline de observations calibradas y estados resueltos sobre el manifest confirmado.
- `tools/capture_semantic_dataset.py`: adquisición dirigida de screenshots completos con labels humanas explícitas.
- `tools/semantic_candidate_evaluation.py`: selección y evaluación offline de candidates experimentales mediante raw scores.

`tools/debug_context.py` y `testing/` fueron retirados porque duplicaban captura, dependían del modelo de contexto legacy o contenían IDs/acciones manuales cubiertas por herramientas vigentes. No se migró percepción ni gameplay.

## AdsManager

Los anuncios pertenecen a aplicaciones o packages externos y se inspeccionan mediante UIAutomator2:

```text
external ad detected
  ↓
AdsManager / UIAutomator2
  ↓
return to game
```

AdsManager es una interrupción externa separada de Perception y ContextResolver. Su resultado relevante para el bot principal es recuperar el control y volver al juego.

## Estrategia de migración

La migración será incremental. Se extraerán primero captura, dispositivo y contratos testeables; después se incorporarán el modelo semántico y casos de percepción concretos. Los templates y flows legacy se reutilizarán únicamente cuando aporten evidencia o conocimiento de negocio verificable.
