# Contexto actual — Kritika FarmBot

**Estado:** rediseño híbrido 0.2 — Fase 3F completada offline; Fase 3D permanece parcial hasta revalidación live 3G
**Última actualización:** 2026-08-25

## Objetivo

Kritika FarmBot busca automatizar actividades repetitivas de **Kritika: The White Knights** sobre un dispositivo Android físico. La automatización debe reconocer el estado del juego, ejecutar flows deterministas y realizar la interacción final mediante ADB.

## Por qué se rediseña

El enfoque legacy depende de una colección grande de templates, regiones, botones y coordenadas mantenidos manualmente. Ese modelo se volvió frágil y costoso ante cambios de UI, resoluciones diferentes y contenido nuevo. La versión 0.2 adoptará una percepción híbrida que permita conservar detectores locales rápidos sin exigir que cada situación posible esté codificada como un template específico.

## Estado real legacy

El estado previo al rediseño está preservado en el tag Git `legacy-pre-hybrid`.

La implementación existente contiene:

- captura H.264 mediante el server de scrcpy y decodificación con PyAV;
- almacenamiento del último frame como array BGR compatible con OpenCV;
- template matching y crops con OpenCV;
- un catálogo de 75 contextos en `bot/constants.py`;
- modelos `Contexto` y `Boton`;
- taps y swipes mediante ADB;
- un flow de Tower of Tribulations (TOT);
- un AdsManager standalone basado en UIAutomator2;
- herramientas manuales para capturar frames y templates.

## Qué funciona o conserva valor

- El pipeline conceptual `scrcpy → frame NumPy/OpenCV` es reutilizable.
- Las primitivas ADB son válidas como mecanismo final de interacción.
- OpenCV sigue siendo útil para preprocesamiento y detectores locales conocidos.
- La taxonomía de contextos, controles y actividades conserva conocimiento de dominio.
- El flow TOT conserva intención y reglas de negocio, aunque su implementación no sea reutilizable directamente.
- `bot/ads_manager.py` está aislado del flujo visual normal y conserva una estrategia distinta para anuncios externos.
- Las herramientas de adquisición de capturas pueden evolucionar hacia herramientas de dataset.

## Qué está roto o incompleto

- `python main.py` falla durante imports: `bot/flows.py` solicita funciones eliminadas de `bot/actions.py`.
- La geometría mezcla coordenadas relativas con bloques absolutos legacy, especialmente TOT.
- Los frames históricos son landscape `2712×1224`, mientras el runtime usa `adb wm size` como `(1224, 2712)` para escalar.
- El schema de botones está migrado solo parcialmente y no todos los consumidores aceptan el formato nuevo.
- Los 75 contextos tienen la misma prioridad efectiva.
- No hay outcomes reales configurados.
- Faltan templates activos utilizados por TOT; solo existen variantes históricas `960x540`.
- No hay loop global de percepción, resolución y decisión.

No se reparará el runtime legacy como paso previo al rediseño. Sus problemas se abordarán únicamente cuando una fase futura extraiga una pieza reutilizable o migre un caso de uso.

## Decisiones cerradas para 0.2

### Plataforma y geometría

- La interfaz soportada es landscape.
- Deben admitirse resoluciones variables.
- La geometría debe derivarse de las dimensiones reales de cada frame (`frame.shape`), no de una resolución fija obtenida con `adb wm size`.
- Las coordenadas normalizadas deben permanecer en `[0,1]`.

### Captura y dispositivo

- scrcpy seguirá proporcionando los frames.
- ADB seguirá ejecutando las acciones finales sobre el dispositivo.
- Captura, percepción e interacción deberán quedar separadas y testeables de forma independiente.

### Percepción

- OpenCV no se considera legacy por sí mismo.
- Los detectores locales rápidos atenderán estados o elementos conocidos cuando aporten valor.
- OCR se utilizará para valores dinámicos requeridos por los flows, como stamina o recursos.
- El VLM será un fallback infrecuente para situaciones desconocidas.
- El fallback VLM será provider-agnostic: podrá usar un proveedor externo o un modelo local sin contaminar las demás capas.
- La percepción producirá observaciones semánticas, no decisiones de navegación.

### Estado y negocio

- Un `ContextResolver` consumirá observaciones semánticas y resolverá el estado del juego.
- Los flows conservarán lógica e intención de negocio mayormente deterministas.
- Los flows no deberán ejecutar template matching ni comandos ADB directos.
- Las interrupciones y prioridades se representarán semánticamente, no únicamente por orden de templates.

### AdsManager

- `bot/ads_manager.py` seguirá formando parte del proyecto.
- UIAutomator2 se mantiene separado de la percepción normal del juego.
- En 0.2 actuará como subsistema de interrupción externa: detecta/gestiona un anuncio y devuelve el control al juego.

## Assets y datos preservados

- Los assets runtime activos bajo `assets/ui/` están disponibles para versionado selectivo.
- Los 28 assets de `assets/ui/960x540/` se conservan localmente como referencia y material histórico, pero no son assets runtime activos ni se versionan en el repositorio normal.
- Existen 173 capturas landscape en `screencaps/`, aproximadamente 527 MiB en total.
- Las capturas son un dataset legacy potencialmente valioso. Permanecen intactas e ignoradas por Git; `datasets/semantic_slice_manifest.json` versiona labels humanos para un subconjunto de 27 imágenes sin copiar los frames.
- El catálogo monolítico de `bot/constants.py` se conserva por su conocimiento histórico, pero no será el modelo de configuración de 0.2.

## Núcleo 0.2 implementado y tests

La Fase 1A estableció los primeros fundamentos 0.2 sin migrar el runtime legacy:

- `bot/config.py` define una configuración de runtime explícita y construible sin leer `.env`; la carga desde environment o un archivo dotenv ocurre únicamente mediante `RuntimeConfig.from_env()`.
- `bot/geometry.py` deriva siempre `(width, height)` desde `frame.shape` y convierte puntos y regiones normalizados mediante helpers puros.
- `pytest` ejecuta la suite normal bajo `tests/` sin teléfono, ADB, scrcpy-server, red ni interacción humana.

La Fase 1B añadió `bot/adb.py` como límite explícito para comandos físicos Android:

- `AdbClient` recibe ejecutable, serial y timeout; puede construirse desde los campos ADB de `RuntimeConfig` sin retener el resto de la configuración.
- `get_state`, `shell`, `tap`, `swipe`, `push`, `forward` y `remove_forward` pasan por una única primitiva segura basada en `subprocess` y argumentos separados.
- `AdbError` y `AdbTimeoutError` conservan comando, salida y contexto del fallo.
- Los tests usan un runner inyectado y no requieren que ADB esté instalado ni inician procesos reales.

La Fase 1C añadió `bot/capture.py` como fuente de frames scrcpy independiente:

- `ScrcpyFrameSource` recibe explícitamente un `AdbClient` y el path local de `scrcpy-server.jar`; no lee environment ni configuración global.
- Administra push, forward, proceso persistente, socket, decoder PyAV, thread receptor, espera acotada del primer frame y cleanup idempotente.
- `FrameSnapshot` expone una copia BGR del último ndarray junto con timestamp monotónico y sequence; width/height se derivan de `image.shape`.
- Los fallos parciales de startup limpian únicamente los recursos adquiridos y los errores del receptor quedan observables mediante `failure` y `get_frame()`.
- `AdbClient.spawn_shell()` construye el proceso ADB persistente, pero el ownership de su lifecycle pertenece a `ScrcpyFrameSource`.

La Fase 1D integró el núcleo técnico y lo validó contra hardware real:

- `bot/runtime.py` ensambla transparentemente `RuntimeConfig → AdbClient → ScrcpyFrameSource` sin globals ni operaciones externas durante la construcción.
- `tools/smoke_capture.py` es un diagnóstico manual opt-in que valida ADB, múltiples frames y cleanup sin enviar input al dispositivo.
- El smoke real confirmó ADB state `device`, scrcpy-server 3.3.4 y cinco snapshots con sequence `1 → 5`.
- El primer frame llegó en aproximadamente 2.4 s; los frames fueron BGR `uint8` con shape `(1224, 2712, 3)`, es decir width `2712` y height `1224` derivados del ndarray.
- Shutdown completó y una consulta posterior de forwards confirmó que `tcp:27183` fue retirado.
- La validación real detectó y corrigió un detalle de protocolo 3.3.4: los packets H.264 de configuración SPS/PPS se guardan y anteponen al siguiente media packet antes de decodificar.

La Fase 1E cerró el núcleo reutilizable y retiró infraestructura duplicada:

- `bot/screen.py` quedó reducido a `find_image_on_screen()` y `find_all_on_screen()`, helpers OpenCV transicionales que reciben el frame explícitamente y calculan regiones desde sus dimensiones reales.
- `bot/capture.py` es la única implementación activa del protocolo scrcpy y `bot/adb.py` el único límite activo de procesos ADB.
- `tools/screencap_batch.py` y `tools/asset_capture.py` consumen `RuntimeConfig → build_frame_source()`, mantienen lifecycle explícito y son import-safe.
- `tools/debug_context.py` se retiró porque mezclaba ADB directo con matching del modelo legacy. Los tres scripts de `testing/` también se retiraron: duplicaban el smoke de captura o dependían de UIAutomator2, IDs hardcodeados e interacción manual.
- `.tools/` es una ubicación local deliberada para binarios de ADB/scrcpy; permanece ignorada y no se versiona.

La Fase 2A definió los contratos semánticos sin implementar percepción ni resolución:

- `bot/observations.py` define `Observation`, evidencia inmutable identificada mediante nombres namespaced, confianza normalizada, una categoría `ObservationSource`, un valor escalar opcional y una región relativa opcional.
- `ObservationSource` distingue `LOCAL_CV`, `OCR`, `VLM` y `SYSTEM` sin exponer proveedores, modelos ni detectores concretos.
- `ObservationBatch` agrupa una tupla inmutable de observaciones para un único `sequence` y `timestamp`; no conserva el ndarray y permite múltiples observaciones con el mismo nombre. Sus helpers `find()` y `best()` sólo buscan evidencia y no fusionan fuentes.
- `bot/state.py` define `ResolvedState` y `ResolutionStatus` (`RESOLVED`, `UNKNOWN`, `AMBIGUOUS`) como salida inmutable del futuro resolver. El estado separa contexto base, subcontexto opcional, overlays y candidatos base conflictivos.
- `UNKNOWN` es un resultado normal y puede coexistir con overlays conocidos aunque el contexto subyacente no haya podido resolverse. `AMBIGUOUS` conserva al menos dos candidatos semánticos sin seleccionar uno.
- La ubicación semántica reutiliza `RelativeRegion` de `bot/geometry.py`; `normalize_relative_region()` valida límites relativos en `[0,1]` y área positiva sin introducir geometría pixel en el contrato.
- Los contratos no importan NumPy, OpenCV, PyAV, ADB, configuración runtime ni módulos legacy.

La Fase 2B implementó resolución semántica determinista y explicable sobre un único batch:

- `bot/resolver.py` define `ContextRule`, `RuleMatch`, `match_rule()` y un `ContextResolver` inmutable construido con reglas base y overlay inyectadas explícitamente.
- Cada regla exige una colección no vacía de nombres semánticos únicos y aplica el mismo threshold inclusivo a cada requirement.
- Para cada requirement se selecciona únicamente la observación de mayor confidence. Las confidences no se suman, promedian ni ponderan por `ObservationSource`; las regiones tampoco alteran el matching.
- Una regla coincide sólo cuando todos sus requirements satisfacen el threshold. `RuleMatch.confidence` es la confidence mínima entre las evidencias seleccionadas y sirve únicamente para diagnóstico, no como probabilidad calibrada.
- Cero contextos base producen `UNKNOWN`, uno produce `RESOLVED` y dos o más producen `AMBIGUOUS`. Nunca se desempata por orden ni por mayor confidence.
- Los overlays se resuelven independientemente del contexto base, pueden coexistir y se retornan ordenados por nombre. No generan una ambigüedad separada ni expresan prioridad de atención.
- `matching_base_rules()` y `matching_overlay_rules()` permiten inspeccionar qué regla coincidió y qué observación concreta satisfizo cada requirement sin incorporar esa traza a `ResolvedState`.
- El resolver no conserva contexto anterior, no implementa temporalidad y deja `subcontext=None`.

La Fase 2C añadió el primer catálogo semántico productivo y deliberadamente mínimo. La validación posterior de 2D corrigió parte de su semántica inicial:

- `bot/catalog.py` publica tres reglas base (`screen.character_select`, `screen.battle_mode_select`, `screen.black_market`) y un overlay (`popup.purchase_confirmation`).
- El vocabulario evaluado consta de `landmark.gold_currency_icon`, `landmark.character_select_header`, `landmark.monster_wave_entry_title`, `landmark.black_market_title` y `landmark.purchase_confirmation_prompt`.
- `landmark.gold_currency_icon` conserva el fragmento histórico con un nombre correcto, pero ninguna regla lo consume: el asset no es un header y permanece visible en la misma posición cuando Black Market u otros modales conservan debajo el shell de Lobby. Por esa razón no distingue por sí solo el contexto base actual y se retiró la regla de `screen.lobby` hasta contar con otra señal.
- `BASE_CONTEXT_RULES`, `OVERLAY_RULES` y `build_default_resolver()` forman la API del catálogo. Cada llamada al builder crea un resolver nuevo; no existe singleton ni estado global.
- Todas las reglas usan provisionalmente confidence semántica `0.80`. Ese valor no copia el threshold OpenCV legacy `0.85`; 2D midió raw scores deliberadamente sin calibrar esa confidence, tarea que permanece para Fase 3.
- Los nombres y reglas no contienen assets, regiones, coordenadas, templates ni tecnología de detector. El mapping legacy se conserva únicamente en `ARCHITECTURE.md` como trazabilidad para la futura percepción.
- Tower of Tribulations quedó fuera pese a ser consumido por el flow legacy: sus templates principales referenciados no forman parte de los assets runtime activos y su entrada todavía mezcla geometría absoluta y subcontextos. `bag-full-alert` también quedó fuera porque el propio catálogo legacy duda de su semántica.

La Fase 2D validó este slice de forma offline sin crear Perception productiva:

- `bot/screen.py` expone `template_match_score()`, una primitiva pura que devuelve el máximo `TM_CCOEFF_NORMED` crudo sobre frame, template y region explícitos. Ese valor sigue siendo `raw_match_score`; no se transforma en `Observation.confidence` ni se compara con el threshold semántico `0.80`.
- `tools/semantic_slice_evaluation.py` descubre el dataset, ejecuta la matriz completa screenshot × landmark, selecciona un subconjunto determinista y resume ground truth. `tools/review_semantic_slice.py` permite revisar ese subconjunto mediante OpenCV sin introducir frameworks nuevos.
- La ejecución real descubrió 173 PNG legibles, todos `2712×1224`, y produjo 865/865 mediciones compatibles. Las cinco regions legacy ya estaban normalizadas, funcionaron sin fallback full-frame y los assets coincidieron a tamaño nativo.
- Se revisaron humanamente 27 capturas: 27 `confirmed`, cero `unsure` y cero `skipped`; incluyen 6 Black Market, 2 Character Select, 1 Battle Mode Select, 1 Lobby, 17 contextos fuera del slice y 3 prompts de compra.
- `landmark.black_market_title` quedó **VALIDATED** (6 positivos, 21 negativos; mínimo positivo `0.9976`, máximo negativo `0.2230`). `landmark.purchase_confirmation_prompt` quedó **VALIDATED** (3/24; `0.9959` frente a `0.4876`) y también apareció en Guild Shop, por lo que dejó de estar acoplado semánticamente a Black Market.
- `landmark.character_select_header` quedó **PROMISING** (2/25; `0.9929` frente a `0.4921`) y `landmark.monster_wave_entry_title` **PROMISING** (1/26; `1.0000` frente a `0.4000`) por muestra positiva pequeña.
- `landmark.gold_currency_icon` quedó **NEEDS_REWORK** como señal exclusiva de lobby: obtuvo hasta `0.9882` en negativos y scores alrededor de `0.985` en Black Market. El nombre anterior `landmark.lobby_header` describía incorrectamente el contenido visible; Fase 3B.1 revisó por separado su valor posicional.
- En las dos capturas Black Market + confirmación, ambos landmarks permanecieron detectables simultáneamente con scores crudos cercanos a `1.0`, respaldando el modelo base + overlay para ese caso histórico.

La Fase 3A implementó la primera porción productiva de Perception local:

- `bot/perception/engine.py` define un contrato pequeño de detector y un `PerceptionEngine` inmutable. El engine recibe detectores explícitos, agrega sus observations en orden determinista y devuelve un `ObservationBatch` con el `sequence` y `timestamp` exactos del `FrameSnapshot`; no conserva contexto, historial ni estado de gameplay.
- `bot/perception/local_cv.py` implementa matching OpenCV a tamaño nativo para un landmark por detector. Cada template se carga y valida una sola vez durante la construcción, queda precargado en grayscale y se reutiliza en todos los frames. La búsqueda convierte la region normalizada mediante `bot.geometry` y reutiliza `template_match_score()` sin leer el PNG por frame.
- `bot/perception/specs.py` contiene únicamente las specs productivas de `landmark.black_market_title` y `landmark.purchase_confirmation_prompt`, con los mismos assets y regions verificados en 2D. `bot/catalog.py` continúa sin conocer paths, templates ni OpenCV.
- `LinearGapCalibration` transforma el score crudo mediante interpolación lineal entre el máximo negativo confirmado y el mínimo positivo confirmado, clamped a `[0,1]`. La confidence resultante expresa posición en el gap empírico; no es una probabilidad ni una calibración estadística final.
- Los anchors reproducidos sobre 173 screencaps y el manifest de 27 labels son `0.2230203002691269 → 0.997641384601593` para Black Market y `0.48758167028427124 → 0.9959162473678589` para Purchase Confirmation. Son provisionales porque sólo existen seis y tres positivos confirmados respectivamente.
- El detector no emite una observation cuando la confidence calibrada es `0`; para valores mayores emite presencia con `ObservationSource.LOCAL_CV`, `value=None` y sin region semántica. El threshold de resolución `0.80` permanece exclusivamente en `ContextRule`.
- `build_default_perception()` crea una instancia nueva con sólo esos dos detectores y realiza IO únicamente durante esa construcción. Character Select y Battle Mode Select siguen `PROMISING`; Lobby permanece sin detector; OCR y VLM todavía no existen.
- La evaluación productiva sobre las 27 capturas confirmadas obtuvo 6/6 TP para Black Market y 3/3 TP para Purchase, sin FP ni FN. El resolver produjo 27/27 resultados esperados, incluidos dos casos Black Market + overlay y un caso base `UNKNOWN` + Purchase overlay; no hubo `AMBIGUOUS`.

La Fase 3B añadió adquisición dirigida y reevaluó las señales pendientes sin ampliar Perception productiva:

- `tools/capture_semantic_dataset.py` consume exclusivamente `RuntimeConfig → build_frame_source() → ScrcpyFrameSource`, exige selección humana por teclado antes de guardar y nunca consulta templates, Perception ni ContextResolver para etiquetar. Guarda screenshots PNG completos bajo `screencaps/semantic/`, informa similitud temporal y mantiene lifecycle mediante context manager.
- `datasets/semantic_acquisition_manifest.json` versiona 30 labels humanos nuevos: 10 `screen.lobby`, 10 `screen.character_select` y 10 `screen.battle_mode_select`, todos `confirmed` y `2712×1224`. Sus paths son relativos y la metadata sólo conserva fecha UTC, resolución, sequence y diferencia visual; no contiene seriales, device IDs ni paths absolutos.
- Lobby quedó investigado contra 11 positivos totales y 46 negativos confirmados. El candidate interpretable formado por los rótulos `Shop / Black Market / Trading Center` quedó **VALIDATED**: positivos `0.7178/0.9862/1.0000` min/median/max, máximo negativo `0.4514`, gap `0.2664` y cero errores en el operating point diagnóstico. Permanece bajo `artifacts/` y no es asset ni detector productivo.
- El asset legacy de `landmark.character_select_header` pasó a **NEEDS_REWORK** (`12/45`, mínimo positivo `0.4343`, máximo negativo `0.4921`). Un crop experimental con el rendering actual del mismo header quedó **VALIDATED** (`12/45`, mínimo positivo `0.4337`, máximo negativo `0.2444`, gap `0.1894`), por lo que la semántica sigue siendo correcta pero el asset productivo futuro deberá curarse en 3C.
- El asset legacy de `landmark.monster_wave_entry_title` pasó a **NEEDS_REWORK** (`11/46`, mínimo positivo `0.3480`, máximo negativo `0.4000`). Un crop actual quedó **PROMISING**: cero errores diagnósticos pero gap pequeño `0.0278`. “Monster Wave” estuvo visible en las 10 capturas nuevas de Battle Mode Select; nueve comparaciones consecutivas quedaron bajo el aviso de near-duplicate porque esa sesión cubrió una UI casi estática, limitación que impide promoverlo todavía.
- La regresión productiva combinada sobre 57 labels confirmó 6/6 Black Market y 3/3 Purchase, cero FP, cero FN, 57/57 resoluciones correctas y cero ambigüedades. `build_default_perception()`, las calibraciones productivas y `SEMANTIC_CONFIDENCE_THRESHOLD = 0.80` no cambiaron.
- No se añadieron OCR, VLM, ActionExecutor, acciones Android ni gameplay. Al terminar hardware no quedaron procesos de captura ni forwards ADB activos.

La Fase 3B.1 reabrió únicamente la elección del landmark de Lobby mediante análisis offline:

- `assets/ui/lobby-id.png` es un template `51×47` del icono de oro. Su región legacy normalizada `(0.2039, 0.0302, 0.2434, 0.0899)` corresponde correctamente a `(552, 36, 660, 110)` sobre un frame landscape `2712×1224`. Sin embargo, el runtime preservado en `legacy-pre-hybrid` escalaba esa región con `adb wm size` en orden portrait `(1224, 2712)`, produciendo `(249, 81, 297, 243)`; la intención geométrica era posicional, pero su aplicación histórica estaba afectada por la orientación que 0.2 ya corrige mediante `frame.shape`.
- Aplicada con la geometría landscape actual sobre los 57 labels, el ancla de oro obtuvo positivos `0.9686/0.9721/1.0000`, máximo negativo `0.9882` y gap `-0.0196`. Los positivos se localizaron en `x=565`, con `y=49` en el frame histórico y `y=61` en los diez nuevos. Un sobre ajustado objetivamente a esas posiciones, `(565, 49, 616, 108)`, conservó el mismo solapamiento y gap `-0.0196`.
- La inspección de los negativos más altos mostró Quests, Trading Center y diálogos de Item Trade sobre el shell de Lobby, además de Black Market, todos con el icono en `(565, 49)`. El resultado corrige la explicación previa: no son principalmente coincidencias del mismo icono desplazado, sino persistencia real del ancla de Lobby bajo estados que el manifest clasifica como `unknown` o `screen.black_market`. Por ello puede describir el shell subyacente, pero no resolver por sí sola `screen.lobby` con la taxonomía vigente.
- Se aislaron crops experimentales sin retratos. `Trading Center` solo quedó **VALIDATED** (`11/46`, positivos `0.7199/0.9826/1.0000`, máximo negativo `0.4657`, gap `0.2541`). El par `Black Market + Trading Center` también quedó **VALIDATED** y obtuvo el mayor gap estrecho (`0.2874`), aunque con menor mínimo positivo (`0.6503`) y mayor superficie. Los rótulos individuales `Shop` y `Black Market` se solaparon con negativos y quedaron **NEEDS_REWORK**.
- Para 3C se recomienda curar `landmark.lobby_trading_center_label` como única señal de Lobby, no el ancla de oro ni una conjunción obligatoria. A los mínimos positivos observados, `Trading Center` ya separa `11/11` positivos de `46/46` negativos; añadir oro no mejora ese resultado y agrega otra condición de fallo. `landmark.lobby_commerce_pair` queda como alternativa experimental, no como requirement simultáneo.
- La evaluación valida separación sólo en el dataset actual. Aunque los frames exhiben fondos visualmente distintos, no constituyen una campaña multi-season controlada. La menor sensibilidad estacional de un rótulo GUI aislado frente a retratos, decoración y fondo es una expectativa por diseño, no evidencia empírica multi-season.

La Fase 3C promovió exactamente Lobby y Character Select a Perception productiva, sin incorporar Battle Mode Select:

- Los PNG experimentales aprobados se copiaron byte por byte a `assets/ui/landmarks/lobby-trading-center-label.png` (`235×70`) y `assets/ui/landmarks/character-select-header.png` (`440×80`). Sus fuentes son, respectivamente, `screencaps/semantic/lobby/20260823T025455_304538Z.png` y `screencaps/semantic/character_select/20260823T025343_820522Z.png`; producción no depende de `artifacts/`.
- `build_default_perception()` construye exactamente cuatro detectores: `landmark.lobby_trading_center_label`, `landmark.character_select_header`, `landmark.black_market_title` y `landmark.purchase_confirmation_prompt`. No construye detectores para el oro, Monster Wave ni otros landmarks legacy.
- La calibración reproducida sobre los 57 frames confirmados combinados fijó Lobby en `0.4657268226146698 → 0.7198567986488342` (11 positivos, 46 negativos, gap `0.25412997603416443`) y Character Select en `0.2443815916776657 → 0.43373382091522217` (12/45, gap `0.18935222923755646`).
- La reevaluación de Black Market y Purchase Confirmation mantuvo sin cambios sus anchors de 3A: `0.2230203002691269 → 0.997641384601593` y `0.48758167028427124 → 0.9959162473678589`. Las 30 capturas dirigidas no introdujeron extremos nuevos ni falsos positivos.
- `bot/catalog.py` restauró `screen.lobby` requiriendo únicamente `landmark.lobby_trading_center_label` con confidence `0.80`. `screen.character_select` conserva como única requirement su header. El oro se retiró del vocabulary productivo; su historia permanece en tooling y documentación 2D/3B.1.
- La evaluación end-to-end `FrameSnapshot → PerceptionEngine → ObservationBatch → ContextResolver → ResolvedState` produjo 57/57 resultados esperados, cero ambigüedades y cero resoluciones incorrectas: Lobby 11/11, Character Select 12/12 y Black Market 6/6 resueltos; Battle Mode Select 11/11 y los otros 17 frames permanecieron `UNKNOWN` como corresponde. Los tres overlays Purchase se conservaron, incluidos dos sobre Black Market y uno sobre base `UNKNOWN`.
- La suite normal contiene 308 tests hardware-free y valida composición exacta, hashes/dimensiones de los assets curados, regions, calibraciones, comportamiento sintético, catálogo e import safety.
- Los negativos críticos que comparten el shell de Lobby —Trading Center abierto, Item Trade, Quests y Black Market— no emitieron el landmark de Lobby con confidence positiva. No se añadió oro, conjunción ni fallback a una franja comercial más amplia.
- Lobby está validado sólo contra el corpus actual. Su menor superficie reduce riesgo esperado por diseño, pero no demuestra robustez multi-season. Ante un cambio de season deben adquirirse nuevos positivos humanos y repetirse evaluación/calibración.
- Battle Mode Select continúa `PROMISING` y sin detector productivo; su regla semántica se conserva para una promoción futura basada en evidencia. OCR, VLM, ActionExecutor, gameplay y acciones físicas siguen deferred.

La primera corrida de Fase 3D validó parcialmente el pipeline completo en hardware real, pero no permite cerrar la fase:

- `tools/smoke_perception.py` compone explícitamente `RuntimeConfig → AdbClient → ScrcpyFrameSource → PerceptionEngine → ObservationBatch → ContextResolver → ResolvedState`. Es manual/opt-in, import-safe, procesa siempre un sequence nuevo a frecuencia acotada, muestra cambios más heartbeat, raw scores diagnósticos separados de `Observation`, latencias y rachas stateless por etapa. No contiene scheduler, estado previo, acciones ni input Android.
- La sesión live del 2026-08-23 confirmó ADB `device`, scrcpy-server 3.3.4, frames BGR `2712×1224`, 1061 análisis en 355.92 s y sequence `1 → 21015`. Lobby se resolvió con confidence `1.0` en la apariencia de la season actual y Character Select con confidence `1.0`; ambos permanecieron estables durante decenas de análisis consecutivos. La reentrada a Lobby también funcionó. Esta evidencia es únicamente **live validation on current season**, no validación multi-season.
- Las transiciones manuales exhibieron `UNKNOWN` sin excepciones, como admite el resolver stateless. La pantalla unsupported ensayada permaneció `UNKNOWN` durante los 37 análisis de su ventana marcada y no produjo un falso contexto base.
- En la pantalla marcada manualmente como Black Market, el detector productivo no resolvió la base: `landmark.black_market_title` permaneció aproximadamente en raw `0.398–0.403`, semantic confidence `0.226–0.233`, muy por debajo de `0.80`. Lobby quedó en confidence `0`, pero Character Select emitió evidence subthreshold aproximada `0.14–0.16`; no hubo resolución falsa ni `AMBIGUOUS`.
- Con Purchase Confirmation visible, el raw del prompt subió aproximadamente de `0.14` a `0.419–0.421`, pero no alcanzó su anchor negativo offline `0.48758167028427124`; semantic confidence permaneció `0` y el overlay no se emitió. La base ya era `UNKNOWN`, por lo que no pudo demostrarse `screen.black_market + popup.purchase_confirmation` live.
- La latencia de sesión fue: perception `5.954/10.621/10.769/27.397 ms` min/median/mean/max, resolver `0.041/0.058/0.069/2.079 ms` y snapshot-to-state `15/31/29.217/109 ms`. Las mediciones raw diagnósticas duplican matching después de resolver y no están incluidas en la latencia productiva reportada.
- El cierre por `q` completó context manager, receiver, socket y proceso; `source.is_running` quedó falso, `adb forward --list` confirmó que el forward fue retirado y no quedó proceso `scrcpy` local. No se guardaron screenshots ni se enviaron taps, swipes o keyevents.
- La evidencia offline de 57/57 sigue siendo reproducible, pero no cubre la apariencia live fallida. Antes de recalibrar deben adquirirse frames completos, actuales y human-confirmed de Black Market y Purchase Confirmation, inspeccionarse crops/posición/rendering y repetirse la matriz contra todos los negativos. No se ajustaron thresholds ni se añadió temporalidad durante 3D.
- La suite normal contiene ahora 313 tests hardware-free. Fase 3D y Fase 3 permanecen abiertas hasta explicar y corregir con evidencia los dos fallos live y repetir exitosamente el smoke completo.

La Fase 3E completó el Perception Workbench v1 y su validación interactiva en hardware real:

- `bot/human_input.py` añadió `HumanInputObserver` como fuente separada y read-only de interacción física. Usa el único límite `AdbClient`: `getevent -pl` descubre dinámicamente dispositivos con `ABS_MT_POSITION_X/Y` y sus min/max, `dumpsys input` informa rotation y `spawn_shell(capture_output=True)` posee el stream `getevent -lt`. No envía taps/swipes ni conoce gameplay.
- `GestureReconstructor` cubre single-touch protocol B y fallback mediante `BTN_TOUCH`: reconstruye un único `HumanTap` o `HumanSwipe` con timestamps monotónicos host, raw diagnostics y puntos display-relative. `getevent` informa monotónico del teléfono, por lo que el observer reestampa al recibir y nunca compara ambos orígenes. Una tolerancia relativa de `0.025` distingue tap/swipe; multitouch e incompletos quedan como `UnknownGesture`.
- La transformación sensor→display sigue AOSP: rotation 0 `(x,y)`, 1 `(y,1-x)`, 2 `(1-x,1-y)`, 3 `(1-y,x)`. Los rangos reales normalizan el sensor y la proyección final usa exclusivamente `frame.shape`; `wm size` no decide geometría.
- `tools/perception_workbench.py` es import-safe y compone `RuntimeConfig → AdbClient → ScrcpyFrameSource + HumanInputObserver → PerceptionEngine → ContextResolver → OpenCV UI`. Deriva dinámicamente bases/overlays de las reglas, soporta ground truth persistente, `UNKNOWN`, overlay toggles, MATCH/MISMATCH/AMBIGUOUS, raw detector diagnostics, marcador temporal de touch, manual save y representative mode.
- La captura activa guarda mismatch/ambiguous y examples representative mediante fingerprint `32×32`, cooldown 2 s, diferencia media mínima 3, refresh máximo 8 s y máximo 12 automáticos por key. No guarda el stream completo. El ring de 24 frames usa nearest-before y first-after-delay (`0.5 s`) para taps/swipes; las imágenes se guardan sin overlays diagnósticos.
- Las sesiones raw quedan en `artifacts/workbench/<session-id>/events.jsonl`, `frames/` y `summary.json`, cubiertas por el ignore existente de `artifacts/`. El envelope v1 es append-friendly/extensible y separa `human_confirmed` de `predicted`; no conserva serial, paths absolutos ni identificadores de usuario/dispositivo. Los datasets/manifests curated no se modifican.
- Black Market, Purchase Confirmation, las calibrations, los assets productivos, `SEMANTIC_CONFIDENCE_THRESHOLD` y `ContextResolver` permanecen sin cambios. 3D continúa PARCIAL por domain drift; 3F no comenzó.
- El primer smoke 3E fue abortado y su sesión `20260823T054558_979538Z-46e40344` queda explícitamente diagnóstica/no curada: 103 evidence events, 89 PNG únicos, aproximadamente 452 MB y 75 mismatch. No puede promoverse a datasets semantic.
- Un frame raw de esa sesión ya exhibía macroblocking/corrupción. Ejecutar el mismo ndarray BGR `2712×1224` mediante el evaluator de 3D y el de Workbench produjo raw scores idénticos y hash sin cambios; resize/overlay/UI no alteraban Perception. El problema estaba antes de presentación.
- El loop anterior redibujaba/redimensionaba continuamente el mismo frame y escribía PNG full-resolution síncronamente; la medición local dio aproximadamente `155 ms` por PNG. Además, el stream usaba sólo `2 Mbps` sin límite de FPS y los timestamps device/host impedían finalizar gestures hasta shutdown.
- Workbench usa ahora `8 Mbps`, `max_fps=30`, preview exacta `1356×612`, render sólo al cambiar, y un único writer acotado que saca PNG/JSONL del loop. Consume siempre `source.get_frame()` más reciente y descarta gaps de sequence. Muestra `source sequence`, `frame age ms`, `perception ms`, `UI/display ms` y `evidence-save ms`; `--compare-once` valida un frame live sin UI/input.
- La suite hardware-free contiene 348 tests y cubre además clock-domain host, stream quality options, igualdad 3D/Workbench, hash/inmutabilidad, aspect ratio exacto, evidence writer no bloqueante y separación inequívoca entre `0 = UNKNOWN` y `P = toggle overlay`.
- El `--compare-once` live posterior recibió BGR `uint8` `(1224, 2712, 3)` con `frame_age_ms=120.9`: los cuatro raw scores fueron idénticos entre 3D y Workbench (`0.985677`, `0.064931`, `0.004422`, `0.073296`), `input_unchanged=True` y `raw_scores_equal=True`.
- El segundo smoke `20260823T061544_647270Z-11461340` es válido como evidencia raw/no revisada: durante 122 s la preview permaneció limpia y prácticamente live, Lobby y Character Select resolvieron correctamente y no reapareció el atraso de ~20 s. Sus 60 PNG originales conservan forma `2712×1224`; inspección de frames de Black Market y Battle Mode Select confirmó imagen limpia.
- La sesión registró 9 taps y 16 swipes; las 25 asociaciones tuvieron frame anterior, frame posterior y secuencias crecientes. El nearest-before quedó entre `1–223 ms` (mediana `107 ms`) y el after entre `511–797 ms` (mediana `655 ms`). El writer guardó 64 evidence events con queue máxima 2, cero drops y cero failure; el cleanup confirmó observer, scrcpy y ADB forward detenidos/removidos.
- Black Market produjo falsos negativos reproducibles sobre frames visualmente confirmados (raw aproximadamente `0.400`, confidence aproximadamente `0.228`); Battle Mode Select permaneció `UNKNOWN`/mismatch como corresponde al carecer de detector productivo. Varios mismatch adicionales corresponden a frames de navegación mientras el ground truth persistente todavía conservaba la pantalla anterior y no deben interpretarse automáticamente como errores del detector.
- El segundo smoke nunca activó `popup.purchase_confirmation`. Una primera sesión suplementaria sí guardó manualmente el popup visible con raw aproximadamente `0.420`, pero usó `0 = UNKNOWN` y dejó `overlays=[]`; no constituye validación del toggle ni ground truth correcto. Para eliminar la confusión visual entre letra `O` y dígito `0`, `P` es ahora la tecla primaria de toggle y la UI la muestra explícitamente; `O` permanece sólo como compatibilidad.
- La sesión suplementaria corregida `20260823T064721_367331Z-addb7117` validó Purchase Confirmation: conservó simultáneamente human base `screen.black_market` y human overlay `popup.purchase_confirmation`, y guardó dos mismatch automáticos más uno manual. En los tres frames la prediction fue `UNKNOWN` sin overlay; Black Market quedó en raw aproximadamente `0.3997–0.3998`, confidence aproximadamente `0.2281–0.2282`, y Purchase en raw aproximadamente `0.4205–0.4206`, confidence `0`. El PNG manual full-frame `2712×1224` fue inspeccionado y muestra el popup limpio.
- Esa sesión produjo 11 evidence events/PNG, queue máxima 2, cero drops/failure y cleanup completo. Sus dos taps tuvieron before/after crecientes, con nearest-before de `114/235 ms` y after de `588/750 ms`. La sesión continúa `raw_unreviewed`, `artifacts/` la ignora y no se promovió nada a datasets semantic.
- Los eventos de las sesiones válidas prueban asociación geométrica/temporal, taps en sectores diversos y clasificación de swipe. El usuario confirmó que los marcadores de taps y swipes se alinearon visualmente con sus acciones físicas, sin rotación, inversión ni multiplicación incorrecta. Con preview live, ground truth dinámico, mismatches automáticos, evidencia acotada, before/after, cleanup y 348 tests verdes, 3E queda completada. Las sesiones permanecen raw/no revisadas; detector repair y promoción curated pertenecen exclusivamente a 3F.

La Fase 3F reparó offline Black Market y Purchase Confirmation a partir de evidencia Workbench curada, sin hardware ni cambios al threshold semántico `0.80`:

- Se inspeccionaron visualmente los sequences `1706` y `1946` de `20260823T061544_647270Z-11461340`: ambos muestran limpiamente `screen.black_market`. También se confirmaron `905`, `1145` y `1214` de `20260823T064721_367331Z-addb7117`: conservan `screen.black_market` y muestran `popup.purchase_confirmation`. Eventos adicionales con ground truth persistente atrasado o sin overlay correctamente activado no se promovieron.
- `datasets/workbench_evidence_manifest.json` versiona únicamente esos cinco examples, con paths POSIX relativos, `source=workbench`, session id, sequence, timestamp, reason y frame shape. Sus PNG full-frame se materializan localmente bajo `screencaps/semantic/workbench/`, permanecen ignorados y son copias byte-for-byte de los raw frames; `artifacts/workbench/` continúa siendo raw input, no dataset.
- `tools/production_perception_evaluation.py` valida la promoción contra `summary.json` y el único evento `evidence.frame`: exige sesión explícitamente `raw_unreviewed`, ground truth `human_confirmed`, labels/metadata concordantes, paths confinados, PNG legible y shape exacto. La sesión degradada `20260823T054558_979538Z-46e40344` está marcada localmente `curation_status=diagnostic`, `curated=false`; además, la policy general rechaza tanto `diagnostic` como status ausente, sin depender de hardcodear ese ID.
- El root cause de Black Market es rendering drift horizontal/antialiasing: el texto live es más ancho, pero el asset histórico y su región siguen siendo semánticamente correctos y conservan separación positiva. No se reemplazó el asset ni se amplió el crop; la calibración pasó de `0.2230203002691269 → 0.997641384601593` a `0.2230203002691269 → 0.3996976613998413` sobre `11/51`, gap `0.17667736113071442`.
- Para Purchase, el asset único histórico ya no tenía gap al incluir live (`0.42050543427467346` mínimo positivo frente a `0.48758167028427124` máximo negativo). Se añadió `assets/ui/landmarks/purchase-confirmation-prompt-current.png`, crop exacto `212×35` del mismo literal “Purchase?” en sequence `1214`. `LocalCvDetector` admite ahora variantes nativas precargadas del mismo landmark y usa su máximo raw sin scaling ni weighting.
- La región Purchase quedó acotada a `(1235/2712, 590/1224, 1460/2712, 647/1224)`: admite los renderings histórico y actual, pero no se extiende hacia el match fuerte del diálogo genérico “Still proceed?” situado más a la derecha. La calibración combinada es `0.4875827729701996 → 0.9959162473678589` sobre `6/56`, gap `0.5083334743976593`.
- La reevaluación de los nuevos Black Market como negativos de Character Select elevó su anchor de `0.2443815916776657` a `0.2749116122722626`; el mínimo positivo permanece `0.43373382091522217` y el gap sigue positivo en `0.1588222086429596`. Lobby no cambió. Los cuatro detectores terminaron sin FP/FN emitidos sobre el corpus confirmado.
- El pipeline completo `FrameSnapshot → PerceptionEngine → ObservationBatch → ContextResolver → ResolvedState` produjo `62/62` resultados esperados, `28 UNKNOWN`, cero `AMBIGUOUS` y cero wrong. Lobby resolvió `11/11`, Character Select `12/12`, Black Market `11/11`; Purchase produjo `6/6` overlays, incluidos cinco `screen.black_market + popup.purchase_confirmation` y un `UNKNOWN + popup.purchase_confirmation` de Guild Shop.
- La suite normal contiene 357 tests hardware-free. No cambiaron `SEMANTIC_CONFIDENCE_THRESHOLD`, reglas de contexto, source weighting, hysteresis ni temporalidad. Battle Mode Select, taps/element learning, OCR, VLM, ActionExecutor, SessionRunner y gameplay permanecen deferred. Fase 3D no se cierra hasta repetir live el smoke completo en 3G.

La dirección de producto quedó cerrada documentalmente: el runtime final será un Session Orchestrator configurable (`User Control Panel → SessionPlan → SessionRunner → Characters → Selected Flows`), no un agente general. Los flows serán predominantemente `PER_CHARACTER` pero con scope explícito. Sus prerequisites solicitarán support operations acotadas y revalidarán condiciones en lugar de formar llamadas recursivas arbitrarias. El producto unattended deberá aislar fallos, recuperar, registrar outcomes, limpiar y continuar cuando corresponda. Runtime facts inmediatos y informational snapshots consultados explícitamente serán conceptos distintos; ninguno se implementó en 3E ni 3F.

El inventario confirmó que `main.py`, `bot/context.py`, `bot/actions.py` y `bot/flows.py` todavía importan símbolos de captura/input eliminados de `bot.screen`. Se mantienen rotos deliberadamente: no son runtime activo y adaptarlos exigiría introducir ActionExecutor, ContextResolver y migración de flows fuera de esta fase. `bot/constants.py` continúa como conocimiento legacy preservado y `bot/ads_manager.py` sigue separado mediante UIAutomator2.

La suite normal permanece hardware-free. La arquitectura híbrida completa todavía no está implementada. La siguiente validación de hardware deberá limitarse a conectar `ScrcpyFrameSource → PerceptionEngine → ContextResolver`, observar resultados y cleanup, sin gameplay ni acciones. `landmark.lobby_commerce_pair` permanece como alternativa offline y Battle Mode Select necesita evidencia más diversa o una señal con separación más amplia antes de entrar a Perception productiva.
