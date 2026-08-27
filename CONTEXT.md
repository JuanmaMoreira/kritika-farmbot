# Contexto actual — Kritika FarmBot

**Estado:** rediseño híbrido 0.2; composición `BlackMarketFlow + rotation.standard` validada live en una sesión productiva completa 28/28.
**Unidad funcional vigente:** `SessionRunner` ejecuta flows `PER_CHARACTER` en orden y hace exactamente un `RotationStrategy.advance()` después de completarlos.
**Baseline conocido:** 613/613 tests hardware-free verdes; hardening completo de interacciones Black Market validado en smoke single-character y sesión 28/28.
**Checkpoint operativo:** `SessionResult.COMPLETED`, 28/28 flows, 28/28 advances, Lobby final y retorno al personaje inicial confirmados humanamente.

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
- `SessionPlan` expresa `character_count + flows PER_CHARACTER + RotationStrategy`; `SessionRunner` los compone sin conocer navegación ni negocio interno.

El data flow y los límites vigentes se describen en [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Perception productiva

Contextos base y overlays disponibles:

- `screen.lobby`
- `screen.character_select`
- `screen.black_market`
- `menu.quick` como overlay global
- `popup.purchase_confirmation`
- `popup.insufficient_gold`
- `popup.inventory_full`, acotado a Black Market mediante el landmark común del botón `OK` + `landmark.black_market_title`

Facts internos de Black Market:

- `currency.black_market.gold(value=slot_index)` sobre el grid 5×2;
- `status.black_market.purchased(value=slot_index)` como postcondición de compra.

Estado de evidencia vigente:

- Quick Menu: 18/18 TP, 0 FP/FN frente a 77 negativos.
- GOLD: 25/25 TP, 0 FP/FN y 0 FP sobre 61 KARATS; hay positivos reales en ocho posiciones y cobertura geométrica sintética de las diez.
- Purchased: 11/11 TP, 0 FP/FN frente a 929 regiones negativas.
- Insufficient Gold: 1/1 TP, 0 FP/FN frente a 95 negativos; su muestra positiva todavía es pequeña.
- Inventory Full: 6/6 TP, 0 FP/FN frente a 96 negativos confirmados. El botón común dio positivos `0,983645–0,999941`; el máximo negativo revisado con otro `OK` fue `0,894897`, threshold raw efectivo `0,965896` y gap `0,088749`. La conjunción productiva tuvo 6 matches positivos y cero conflictos al recorrer 252 capturas locales.
- La regresión productiva produjo 102/102 estados esperados sin `AMBIGUOUS`; la validación live confirmó compras, `Purchased`, Inventory Full y retornos frescos.

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
- acepta `popup.purchase_confirmation` mediante `VerifiedTransition`, espera el retorno a Black Market y exige `Purchased` en el mismo slot; sólo reintenta `Yes` si el popup de confirmación persiste inequívocamente y nunca vuelve a seleccionar el slot;
- selecciona cada slot mediante `VerifiedTransition`: espera inicial corta de 1 s + grace pasiva de 2 s y sólo reintenta si un snapshot fresco confirma Black Market limpio, el target aún GOLD y no Purchased;
- ante `popup.insufficient_gold`, registra `timestamp + low_gold`, verifica `No → Black Market` mediante `VerifiedTransition` y sólo reintenta si el mismo popup persiste;
- ante `popup.inventory_full`, registra `black_market.inventory_full`, ejecuta `OK` mediante `VerifiedTransition`, exige volver a Black Market y continúa con el siguiente GOLD sin reintentar el slot;
- trata cero GOLD como success/no-op normal y vuelve a Lobby;
- verifica tanto `Lobby → Black Market` como `Black Market → Lobby` con grace y retry bounded sólo desde la precondición limpia correspondiente;
- ante `purchase_unverified` u otro error técnico aplica la policy temprana `log → cleanup seguro → abortar proceso completo`.

La entrada espera estabilidad visual de Black Market durante 0,75 s porque el título puede aparecer antes que la grilla. Después de Purchase, Low Gold o Inventory Full exige Black Market limpio estable durante 0,5 s; el snapshot resultante, con facts frescos, es la precondición del siguiente slot. `UNKNOWN`, un target ya no accionable o cualquier estado ambiguo prohíben retry. No se añadió memoria ni voting a `ContextResolver`.

La validación live incremental confirmó un one-slot smoke, un full smoke con dos compras verificadas, el cierre final a Lobby y `popup.inventory_full → OK → screen.black_market` al primer intento, sin grace ni retry. Todos los sources hicieron cleanup.

## Composición mínima de sesión

`bot/flow_contracts.py` separa `FlowStatus.COMPLETED/FAILED` de `FlowEvent(kind, detail=None)`. `low_gold` e `inventory_full` son eventos de negocio acumulables y no fatales; un resultado técnico `FAILED` aborta la sesión sin hacer advance. Los counts útiles se derivan de eventos, no son campos estructurales del runner.

`bot/session.py` ejecuta todos los flows seleccionados en orden para el personaje activo, exige su postcondición semántica Lobby, hace un advance y repite exactamente `character_count` veces. Por eso el plan productivo de 28 realiza 28 ejecuciones por flow y 28 advances: el último retorno al personaje inicial no vuelve a procesarlo. Fallos de flow, contradicciones de postcondición o fallos de Rotation preservan progreso parcial y abortan conservadoramente; la cancelación se consulta sólo entre componentes seguros y produce `CANCELLED`.

Cada `SessionCharacterResult` usa un índice de sesión `1..N`, conserva `CharacterContext(name=None, name_confidence=None)`, resultados de flows y resultado de advance. El índice no es identidad. No existe OCR ni provider productivo: un futuro provider opcional podrá enriquecer una vez por personaje el contexto desde Lobby sin hacer fatal la identidad usada sólo para observabilidad.

`CharacterContext` contiene identidad o metadata estable. Stamina, recursos y otros datos cambiantes son runtime facts que un flow solicitará cuando los necesite; no pertenecen al contexto estable y los flows no implementarán OCR directamente.

Los smokes incrementales expusieron latencia de carga entre Lobby y Black Market. Un tap de apertura no registrado abortó correctamente sin advance; `black_market.open` pasó a `VerifiedTransition` con grace sin input y retry sólo desde Lobby fresco. La precondición del flow y la sonda Lobby del composition root también esperan estabilidad pasivamente y rechazan estados incompatibles.

La revisión humana detectó además un falso `no GOLD`: el personaje tenía GOLD que el primer snapshot de facts no había mostrado. El probe sin compras confirmó slots `[2,3,5,8]`; el flow ahora espera una ventana fresca adicional antes de aceptar ausencia, y una validación posterior detectó y compró los cuatro. El smoke final, después de 597 tests verdes, completó 2/2 flows y 2/2 advances: el primer personaje mostró como Purchased los slots `[1,9]` comprados en un intento incremental, y el segundo detectó y compró GOLD `[1,5]`. No hubo business events en la corrida final; un smoke incremental anterior acumuló tres `inventory_full` no fatales. Todos los resultados conservaron `CharacterContext.name=None` y Lobby entre componentes.

El primer smoke productivo 28-character abortó correctamente en el índice 3 tras `2/28` flows y `2/28` advances: no apareció una rama de compra dentro del timeout y el estado final permaneció en Black Market limpio, por lo que no se hizo el advance 3. La observación humana confirmó que el tap del siguiente GOLD ocurrió mientras la compra anterior todavía terminaba de procesarse. Ese caso cerró el gap restante: estabilidad post-rama de 0,5 s y `black_market.select_slot` verificado con grace + retry state-guarded. El intento abortado no se reanudó ni cuenta como válido.

La policy inicial de selección usa una ventana corta de `1 s`; sólo si no aparece una rama espera `2 s` adicionales de grace sin input y después permite retry desde Black Market limpio con el mismo target todavía accionable. Un smoke single-character posterior detectó GOLD `[7,8]`, verificó ambas compras al primer intento, no usó grace/retry y volvió a Lobby. El settle post-rama de `0,5 s` queda abierto a calibración futura si la evidencia live muestra que puede reducirse sin reintroducir taps durante carga.

El segundo intento 28-character también abortó correctamente en el índice 3 tras `2/28` flows y `2/28` advances: el tap de `Yes` no produjo una transición observable y el popup permaneció abierto. El audit posterior migró `Yes`, `insufficient_gold → No` y el cierre final a `VerifiedTransition`, y endureció el guard de GOLD con facts del target. Un smoke live acotado posterior procesó cuatro GOLD consecutivos `[2,4,6,8]`, verificó las cuatro compras y regresó a Lobby sin business popups ni fallo técnico.

La siguiente ejecución productiva cerró el checkpoint completo: `28/28` flows y `28/28` advances, sin technical failures, `SessionStatus.COMPLETED`, Lobby final estable y retorno al personaje inicial confirmado visualmente por el usuario. Acumuló `14 inventory_full` no fatales en los índices `5(1), 7(3), 8(4), 11(2), 12(3), 23(1)`; no hubo `low_gold` ni otros `FlowEvent`. Tres personajes tuvieron no-GOLD normal (`1, 26, 28`). Diez interacciones usaron grace + un retry seguro: selección GOLD en `8, 16, 23`; `Yes` en `10, 14, 17, 24, 25`; cierre Black Market en `18`; apertura en `21`. Las diez terminaron `success_after_retry`; Rotation no tuvo retries. Duración total: `549,625 s`.

## Primitive Rotation standard

`bot/rotation.py` define el contrato mínimo `RotationStrategy` y `StandardRotation(character_count=28)`. El primitive abre Quick Menu, acepta `UNKNOWN + menu.quick`, entra a Character Select, hace swipes bounded, verifica visualmente la selección de la última tarjeta del layout final, confirma y exige un Lobby fresco. La precondición tolera sólo un `UNKNOWN` transitorio de startup esperando pasivamente Lobby fresco; una pantalla resuelta incompatible, overlay o ambigüedad abortan sin input. No identifica personajes, no usa OCR, no ejecuta flows y no llama ADB directamente.

El algoritmo reusable vive en `bot/observed_scroll.py`: compone `RuntimeObserver + ActionExecutor`, separa A/T/B frescos, clasifica `progress / edge_candidate / ineffective` y devuelve edge, gesto inefectivo, límite, timeout o fallo explícitos. `StandardRotation` delega esta operación y no selecciona sin `edge_reached`. `bot/character_select_scroll.py` conserva únicamente el perfil del menú: ROI `(0.49, 0.19, 0.85, 0.805)`, thresholds de movimiento/settled `0,05`, settle `1,0 s` y policy de hasta tres intentos. Un gesto inefectivo aborta; el tercero sólo se usa si el segundo todavía demuestra progreso real.

Las interacciones discretas retry-safe de Rotation delegan en `bot/verified_transition.py`: espera nominal, gracia sin repetir input y hasta dos intentos. El segundo input sólo se permite si una observación fresca sigue inequívocamente en la precondición declarada; las acciones verify-only pueden omitir el guard y nunca se repiten. Abrir Quick Menu, abrir Character Select y confirmar Select usan `6 s + 2 s`; la selección de tarjeta usa `1 s + 0,75 s`, estabilidad `0,25 s` y el mismo máximo de dos intentos. `ActionExecutor` continúa limitado a input físico.

`bot/character_selection.py` responde únicamente si la tarjeta target quedó seleccionada. Mide píxeles amarillos HSV en el borde de la ROI normalizada `(0.48, 0.64, 0.63, 0.84)`, excluyendo la mayor parte del retrato. Cinco pares live selected/unselected dieron negativos `0,00000–0,00087` y positivos `0,09864–0,11216`; `≤ 0,01` autoriza el estado unselected, `≥ 0,05` confirma selected y la banda intermedia es incierta, por lo que no confirma ni habilita retry. El frame previo debe ser unselected y sólo sequences frescas posteriores al tap pueden confirmar el efecto. `Select` no se ejecuta sin esta postcondición.

La verificación visual de tarjeta quedó validada live en 5/5 entradas aisladas y 3/3 `advance()` supervisados. El ciclo completo posterior cerró `rotation.standard`: 28/28 advances, 56 swipes totales, todos `progress → edge_candidate`, 28/28 tarjetas selected al primer tap, 112/112 interacciones verificadas al primer intento y 28/28 retornos a Lobby. No hubo grace, retries, gestos inefectivos ni anomalías; el usuario confirmó visualmente el regreso exacto al personaje inicial A después del advance 28. Duración del loop: `292,7 s`.

La última posición es la primera columna de la última fila visible, regla confirmada en el layout de tres columnas con el slot `+` inmediatamente después. El target es normalizado y no depende de `character_count`.

La demostración humana observada fue `(0.67054, 0.81337) → (0.69375, 0.02433)` en `188 ms`. El perfil ADB derivado usa progreso `(0.80, 0.80) → (0.80, 0.025)` en `190 ms` y confirmación controlada `(0.68, 0.76) → (0.68, 0.24)` en `200 ms`. En 5/5 entradas independientes produjo `progress → edge_candidate`; ROI y thresholds permanecieron sin cambios. Un smoke anterior llegó a 14/28 y se detuvo en la iteración 15 por un tap Select no registrado; `VerifiedTransition` y la selección visual verificada cerraron esa brecha antes del PASS definitivo posterior.

## Decisiones funcionales cerradas

- Black Market se abre sólo desde Lobby; Quick Menu no participa en `BlackMarketFlow`.
- Todos los límites de inventario observados durante una compra se normalizan inicialmente a `popup.inventory_full`; Black Market no distingue el tipo ni gestiona inventarios.
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

- `StandardRotation` aislado está cerrado con ciclo live 28/28 y retorno al inicial confirmado; la composición pasó smoke live pequeño, pero la sesión productiva completa sigue sin ejecutarse.
- Recovery transversal, conflict resolver, aislamiento de fallos y policy unattended de continuación siguen deferred.
- OCR y VLM no están implementados; VLM seguirá provider-agnostic si un caso funcional lo requiere.
- `inventory_kind` e identidad de personaje permanecen desconocidos; liberar, vender o mover inventario pertenece a futuros flows especializados.
- Battle Mode Select requiere evidencia más diversa o una señal con mejor separación.
- `landmark.lobby_commerce_pair` permanece como alternativa offline, no detector productivo.
- `main.py`, `bot/context.py`, `bot/actions.py` y `bot/flows.py` legacy conservan imports retirados y no son runtime activo.
- `bot/constants.py` es conocimiento legacy; `bot/ads_manager.py` permanece standalone mediante UIAutomator2.

## Próximo trabajo

Ejecutar, cuando se autorice explícitamente, la validación completa `BlackMarketFlow + StandardRotation` de 28 personajes. El smoke truncado no intentó ni necesitó regresar al personaje inicial.
