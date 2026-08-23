# Contexto actual — Kritika FarmBot

**Estado:** rediseño híbrido 0.2 — Fase 3B completada
**Última actualización:** 2026-08-23

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
- `landmark.gold_currency_icon` conserva el fragmento histórico con un nombre correcto, pero ninguna regla lo consume: el asset no es un header ni distingue lobby. Por la misma razón se retiró la regla base de `screen.lobby` hasta contar con otra señal.
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
- `landmark.gold_currency_icon` quedó **NEEDS_REWORK** como señal de lobby: obtuvo hasta `0.9882` en negativos y scores alrededor de `0.985` en Black Market. El nombre anterior `landmark.lobby_header` describía incorrectamente un icono global.
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

El inventario confirmó que `main.py`, `bot/context.py`, `bot/actions.py` y `bot/flows.py` todavía importan símbolos de captura/input eliminados de `bot.screen`. Se mantienen rotos deliberadamente: no son runtime activo y adaptarlos exigiría introducir ActionExecutor, ContextResolver y migración de flows fuera de esta fase. `bot/constants.py` continúa como conocimiento legacy preservado y `bot/ads_manager.py` sigue separado mediante UIAutomator2.

La suite normal contiene 300 tests hardware-free. La arquitectura híbrida completa todavía no está implementada. Fase 3C podrá curar y promover los candidates validados de Lobby y Character Select; Battle Mode Select necesita evidencia más diversa o una señal con separación más amplia antes de entrar a Perception productiva.
