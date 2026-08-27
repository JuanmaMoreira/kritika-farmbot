# Contexto actual — Kritika FarmBot

**Estado:** rediseño híbrido 0.2; Fase 4 cerrada y primer primitive aislado de Rotation validado live.
**Unidad funcional vigente:** `StandardRotation.advance()` realiza un único cambio `Lobby → Quick Menu → Character Select → final de lista → última tarjeta → Lobby`.
**Baseline conocido:** 486/486 tests hardware-free verdes; regresión productiva 96/96 sin estados ambiguos ni errores.
**Siguiente trabajo funcional:** completar la semántica de `rotation.standard` para una rotación entera, sin integrar todavía `SessionRunner`.

La cronología, calibraciones reemplazadas y evidencia detallada están en [`docs/HISTORY.md`](docs/HISTORY.md). El código y los tests siguen siendo la verdad de implementación.

## Arquitectura runtime implementada

- `RuntimeConfig` carga configuración sólo cuando el composition root lo solicita.
- `AdbClient` concentra comandos Android y es sustituible por fakes en tests.
- `ScrcpyFrameSource` captura y decodifica H.264 mediante scrcpy/PyAV, publica `FrameSnapshot` BGR y posee el cleanup de proceso, socket y forward.
- `PerceptionEngine` ejecuta detectores locales precargados y produce `ObservationBatch` del mismo frame.
- `ContextResolver` transforma observaciones en `ResolvedState` determinista (`RESOLVED`, `UNKNOWN` o `AMBIGUOUS`) y resuelve overlays independientemente.
- `RuntimeObserver` produce `RuntimeSnapshot` coherentes con frame BGR, observations, estado, facts y geometría del mismo frame; sus esperas exigen frames frescos y tienen timeout.
- Los intents semánticos tipados separan negocio de coordenadas.
- `ActionExecutor` traduce esos intents a taps ADB normalizados contra `frame.shape`; no decide gameplay.
- `BlackMarketFlow` es un flow 0.2 `PER_CHARACTER` implementado y separado del runtime legacy.
- `StandardRotation` es transversal, implementa un solo `advance()` y no conoce flows ni ADB.

El data flow y los límites vigentes se describen en [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Perception productiva

Contextos base y overlays disponibles:

- `screen.lobby`
- `screen.character_select`
- `screen.black_market`
- `menu.quick` como overlay global
- `popup.purchase_confirmation`
- `popup.insufficient_gold`

Facts internos de Black Market:

- `currency.black_market.gold(value=slot_index)` sobre el grid 5×2;
- `status.black_market.purchased(value=slot_index)` como postcondición de compra.

Estado de evidencia vigente:

- Quick Menu: 18/18 TP, 0 FP/FN frente a 77 negativos.
- GOLD: 25/25 TP, 0 FP/FN y 0 FP sobre 61 KARATS; hay positivos reales en ocho posiciones y cobertura geométrica sintética de las diez.
- Purchased: 11/11 TP, 0 FP/FN frente a 929 regiones negativas.
- Insufficient Gold: 1/1 TP, 0 FP/FN frente a 95 negativos; su muestra positiva todavía es pequeña.
- La regresión productiva previa al flow produjo estados esperados sin `AMBIGUOUS`; la validación live de Fase 4 confirmó compras, `Purchased` y retorno final a Lobby.

Las calibraciones exactas, manifests y antecedentes de repair están en código/tests, datasets versionados y [`docs/HISTORY.md`](docs/HISTORY.md). Battle Mode Select no tiene detector productivo.

## Perception Workbench

`tools/perception_workbench.py` es tooling humano de adquisición, no runtime de gameplay. Combina captura, Perception, Resolver y observación read-only del touchscreen. Conserva ground truth explícito, candidates separados del catálogo productivo, evidencia acotada y transiciones sólo cuando el humano las confirma. No envía input Android ni promueve automáticamente evidencia raw.

El protocolo human-in-the-loop canónico está en [`AGENTS.md`](AGENTS.md).

## Runtime y flow Black Market

`BlackMarketFlow`:

- comienza únicamente en `screen.lobby`;
- navega directamente `Lobby → Black Market → Lobby`;
- hace una sola lectura inicial de diez slots y recorre los GOLD en orden row-major;
- compra si y sólo si la moneda es GOLD: **NEVER BUY KARATS**;
- no identifica item, precio, balance ni personaje y no usa OCR;
- acepta `popup.purchase_confirmation`, espera el retorno a Black Market y exige `Purchased` en el mismo slot;
- ante `popup.insufficient_gold`, registra `timestamp + low_gold`, elige No y continúa con el siguiente GOLD;
- trata cero GOLD como success/no-op normal y vuelve a Lobby;
- ante `purchase_unverified` u otro error técnico aplica la policy temprana `log → cleanup seguro → abortar proceso completo`.

La entrada espera estabilidad visual de Black Market durante 0,75 s porque el título puede aparecer antes que la grilla. No se añadió memoria ni voting a `ContextResolver`.

La validación live incremental confirmó un one-slot smoke, un full smoke con dos compras verificadas y el cierre final a un frame fresco `screen.lobby`. Todos los sources hicieron cleanup.

## Primitive Rotation standard

`bot/rotation.py` define el contrato mínimo `RotationStrategy` y `StandardRotation(character_count=28)`. El primitive abre Quick Menu, acepta `UNKNOWN + menu.quick`, entra a Character Select, hace swipes bounded, verifica visualmente la selección de la última tarjeta del layout final, confirma y exige un Lobby fresco. La precondición tolera sólo un `UNKNOWN` transitorio de startup esperando pasivamente Lobby fresco; una pantalla resuelta incompatible, overlay o ambigüedad abortan sin input. No identifica personajes, no usa OCR, no ejecuta flows y no llama ADB directamente.

El algoritmo reusable vive en `bot/observed_scroll.py`: compone `RuntimeObserver + ActionExecutor`, separa A/T/B frescos, clasifica `progress / edge_candidate / ineffective` y devuelve edge, gesto inefectivo, límite, timeout o fallo explícitos. `StandardRotation` delega esta operación y no selecciona sin `edge_reached`. `bot/character_select_scroll.py` conserva únicamente el perfil del menú: ROI `(0.49, 0.19, 0.85, 0.805)`, thresholds de movimiento/settled `0,05`, settle `1,0 s` y policy de hasta tres intentos. Un gesto inefectivo aborta; el tercero sólo se usa si el segundo todavía demuestra progreso real.

Las interacciones discretas retry-safe de Rotation delegan en `bot/verified_transition.py`: espera nominal, gracia sin repetir input y hasta dos intentos. El segundo input sólo se permite si una observación fresca sigue inequívocamente en la precondición declarada; las acciones verify-only pueden omitir el guard y nunca se repiten. Abrir Quick Menu, abrir Character Select y confirmar Select usan `6 s + 2 s`; la selección de tarjeta usa `1 s + 0,75 s`, estabilidad `0,25 s` y el mismo máximo de dos intentos. `ActionExecutor` continúa limitado a input físico.

`bot/character_selection.py` responde únicamente si la tarjeta target quedó seleccionada. Mide píxeles amarillos HSV en el borde de la ROI normalizada `(0.48, 0.64, 0.63, 0.84)`, excluyendo la mayor parte del retrato. Cinco pares live selected/unselected dieron negativos `0,00000–0,00087` y positivos `0,09864–0,11216`; `≤ 0,01` autoriza el estado unselected, `≥ 0,05` confirma selected y la banda intermedia es incierta, por lo que no confirma ni habilita retry. El frame previo debe ser unselected y sólo sequences frescas posteriores al tap pueden confirmar el efecto. `Select` no se ejecuta sin esta postcondición.

La verificación visual de tarjeta quedó validada live en 5/5 entradas aisladas y 3/3 `advance()` supervisados. Las aisladas produjeron scores selected `0,10417–0,11258`; los advances, `0,10709–0,10819`. Todos usaron scroll `progress → edge_candidate`, selección correcta confirmada humanamente y primer intento sin grace ni retry real. Los 3 advances regresaron a Lobby fresco. Las rutas delayed/retry permanecen cubiertas hardware-free; el smoke 28/28 continúa pausado hasta publicar este checkpoint.

La última posición es la primera columna de la última fila visible, regla confirmada en el layout de tres columnas con el slot `+` inmediatamente después. El target es normalizado y no depende de `character_count`.

La demostración humana observada fue `(0.67054, 0.81337) → (0.69375, 0.02433)` en `188 ms`. El perfil ADB derivado usa progreso `(0.80, 0.80) → (0.80, 0.025)` en `190 ms` y confirmación controlada `(0.68, 0.76) → (0.68, 0.24)` en `200 ms`. En 5/5 entradas independientes produjo `progress → edge_candidate`; ROI y thresholds permanecieron sin cambios. Un smoke completo posterior llegó a 14/28 y se detuvo correctamente en la iteración 15: el scroll y la selección de tarjeta fueron correctos, pero el único tap de Select no produjo transición. El ciclo 28/28 permanece pausado hasta publicar los checkpoints locales ya validados.

## Decisiones funcionales cerradas

- Black Market se abre sólo desde Lobby; Quick Menu no participa en `BlackMarketFlow`.
- Quick Menu pertenece a Rotation.
- Rotation es transversal: un flow opera sobre el personaje activo y nunca selecciona el siguiente.
- La primera estrategia será `rotation.standard`, con `character_count = 28` explícito.
- Character Select funciona como lista MRU: scroll al final + última posición permite recorrer personajes sin identificarlos.
- `MAIN`, `SUB1`, `SUB2` y `SUB3` se preservan para estrategias futuras, sin trato especial inicial.
- Perception no navega, los flows no llaman ADB y `ActionExecutor` no decide gameplay.
- La geometría se deriva del frame landscape real, nunca de `adb wm size`.
- Runtime facts inmediatos e informational snapshots consultados explícitamente son conceptos distintos.
- El producto objetivo es un Session Orchestrator configurable, no un agente general.

## Limitaciones y deferred

- El primitive `StandardRotation.advance()` está endurecido; el smoke 28/28 está temporalmente pausado tras un tap Select no registrado en la iteración 15. La rotación completa, el retorno final al inicial, `SessionPlan` y `SessionRunner` siguen pendientes.
- Recovery transversal, conflict resolver, aislamiento de fallos y policy unattended de continuación siguen deferred.
- OCR y VLM no están implementados; VLM seguirá provider-agnostic si un caso funcional lo requiere.
- Battle Mode Select requiere evidencia más diversa o una señal con mejor separación.
- `landmark.lobby_commerce_pair` permanece como alternativa offline, no detector productivo.
- `main.py`, `bot/context.py`, `bot/actions.py` y `bot/flows.py` legacy conservan imports retirados y no son runtime activo.
- `bot/constants.py` es conocimiento legacy; `bot/ads_manager.py` permanece standalone mediante UIAutomator2.

## Próximo trabajo

Revisar y publicar conjuntamente los checkpoints locales de transición y selección verificada. Sólo después retomar el smoke aislado de 28 cambios y validar humanamente el retorno al personaje inicial. Esto no implica que el runtime productivo hará 28 cambios seguidos; un futuro `SessionRunner` intercalará flows con `RotationStrategy.advance()`.
