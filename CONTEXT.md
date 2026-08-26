# Contexto actual — Kritika FarmBot

**Estado:** rediseño híbrido 0.2; Fase 4 single-character Black Market cerrada y validada live.
**Último checkpoint funcional:** `4a14eee` — `feat: implement single-character Black Market flow`.
**Baseline conocido:** 460/460 tests hardware-free verdes en ese checkpoint.
**Siguiente trabajo funcional:** `RotationStrategy` / `rotation.standard`.

La cronología, calibraciones reemplazadas y evidencia detallada están en [`docs/HISTORY.md`](docs/HISTORY.md). El código y los tests siguen siendo la verdad de implementación.

## Arquitectura runtime implementada

- `RuntimeConfig` carga configuración sólo cuando el composition root lo solicita.
- `AdbClient` concentra comandos Android y es sustituible por fakes en tests.
- `ScrcpyFrameSource` captura y decodifica H.264 mediante scrcpy/PyAV, publica `FrameSnapshot` BGR y posee el cleanup de proceso, socket y forward.
- `PerceptionEngine` ejecuta detectores locales precargados y produce `ObservationBatch` del mismo frame.
- `ContextResolver` transforma observaciones en `ResolvedState` determinista (`RESOLVED`, `UNKNOWN` o `AMBIGUOUS`) y resuelve overlays independientemente.
- `RuntimeObserver` produce `RuntimeSnapshot` coherentes con observations, estado, facts y geometría del mismo frame; sus esperas exigen frames frescos y tienen timeout.
- Los intents semánticos tipados separan negocio de coordenadas.
- `ActionExecutor` traduce esos intents a taps ADB normalizados contra `frame.shape`; no decide gameplay.
- `BlackMarketFlow` es un flow 0.2 `PER_CHARACTER` implementado y separado del runtime legacy.

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

- `RotationStrategy`, `rotation.standard`, `SessionPlan` y `SessionRunner` no están implementados.
- Recovery transversal, conflict resolver, aislamiento de fallos y policy unattended de continuación siguen deferred.
- OCR y VLM no están implementados; VLM seguirá provider-agnostic si un caso funcional lo requiere.
- Battle Mode Select requiere evidencia más diversa o una señal con mejor separación.
- `landmark.lobby_commerce_pair` permanece como alternativa offline, no detector productivo.
- `main.py`, `bot/context.py`, `bot/actions.py` y `bot/flows.py` legacy conservan imports retirados y no son runtime activo.
- `bot/constants.py` es conocimiento legacy; `bot/ads_manager.py` permanece standalone mediante UIAutomator2.

## Próximo trabajo

Implementar `RotationStrategy` y `rotation.standard` sin acoplarlas a `BlackMarketFlow`: Quick Menu → Character Select → scroll al final → última posición → Lobby, con 28 personajes configurables y pruebas hardware-free primero. Después corresponde la composición mínima `SessionPlan / SessionRunner → RotationStrategy + Selected PER_CHARACTER Flow(s)`.
