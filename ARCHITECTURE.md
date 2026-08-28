# Arquitectura — Kritika FarmBot 0.2

Este documento define componentes, contratos, data flow e invariantes vigentes. El estado implementado está en [`CONTEXT.md`](CONTEXT.md); los antecedentes están en [`docs/HISTORY.md`](docs/HISTORY.md).

## Data flow runtime

```text
Capture
  ↓
Perception
  ↓
Semantic Observations
  ↓
ContextResolver
  ↓
RuntimeSnapshot ──────────────┐
  ↓                           │
RuntimeFactReader             │
  ↓                           │
ROI / preprocessing → OCR Engine → OcrResult → Parser → RuntimeFact
                                                      └→ Flow
  ↓
Semantic Actions
  ↓
ActionExecutor
  ↓
AdbClient
```

Invariantes centrales:

```text
Rotation ≠ Flow
Flow ≠ ActionExecutor
ActionExecutor ≠ Perception
```

- Perception observa; no navega ni decide gameplay.
- El resolver interpreta evidencia; no captura ni ejecuta acciones.
- Un flow decide según estado/facts y solicita intents; no hace matching ni llama ADB.
- `ActionExecutor` conoce targets y geometría; no reconoce pantallas ni aplica policy de negocio.
- `AdbClient` conoce comandos físicos; no conoce frames ni semántica.

## Configuración y composition root

`bot/config.py` define `RuntimeConfig` inmutable. La construcción explícita no lee environment; `RuntimeConfig.from_env()` lo hace sólo cuando el caller lo solicita. Rutas locales y seriales no se hardcodean.

`bot/runtime.py` ensambla `RuntimeConfig → AdbClient → ScrcpyFrameSource` sin iniciar infraestructura durante imports o construcción. Los tools y futuros entry points poseen el lifecycle de la composición.

`bot/productive_runtime.py` es el composition root operacional compartido: adquiere configuración, ADB, captura, percepción, observer, OCR facts, executor, flows, rotation y runner con cleanup explícito. `bot/flow_registry.py` contiene la única lista productiva de flows (`black_market`, `world_boss`) con metadata, contrato y factory explícitos; no hay discovery, reflection ni plugin system.

`RuntimeEventStream` emite eventos estructurados (`timestamp`, level, component, event y fields) hacia consola, log persistente y consumidores suscriptos. Los entrypoints `tools.run_flow`, `tools.run_session` y `tools.gui` son adaptadores finos sobre esta misma composición. La GUI obtiene selección/orden de `FlowRegistry`; un único worker llama `ProductiveRuntime`, encola eventos/resultados y nunca toca Tk. El main thread drena por `after()`, deriva progreso de eventos y activa el mismo `CancellationToken`. No contiene business logic ni una segunda state machine del juego.

Toda geometría visual deriva de `frame.shape` en orden `(height, width, ...)`. Los puntos normalizados representan índices de píxel; las regiones usan límite final exclusivo. `adb wm size` puede ser diagnóstico, nunca fuente de geometría de captura.

## Capture

`bot/capture.py` implementa `ScrcpyFrameSource` como única captura activa 0.2. Recibe un `AdbClient` y el path de scrcpy-server, prepara push/forward, proceso, socket y decoder PyAV, y publica el último frame BGR.

`FrameSnapshot` contiene copia del ndarray, sequence y timestamp monotónico. La fuente posee todos los recursos adquiridos y garantiza cleanup best-effort e idempotente, incluso tras startup parcial. Los fallos del receiver permanecen observables.

Capture no importa Perception, Resolver, flows ni acciones.

## Perception

`PerceptionEngine` recibe detectores explícitos y produce un `ObservationBatch` con la identidad temporal exacta del `FrameSnapshot`. No conserva historial, contexto ni estado de gameplay.

El backend actual usa OpenCV local:

- templates precargados y matching a tamaño nativo;
- regiones normalizadas proyectadas desde el ndarray;
- raw score separado de semantic confidence;
- calibración empírica por detector;
- cero IO de assets por frame;
- múltiples variantes sólo cuando representan el mismo significado visual.

Los detectores productivos cubren Lobby, Character Select, Battle Mode Select, Black Market, World Boss, batalla World Boss, Quick Menu y los overlays Purchase Confirmation, Insufficient Gold, Inventory Full, Select Boss, Previous Rewards y Raid Complete. Inventory Full usa el botón `OK` común con gating explícito de Black Market, no el mensaje variable. Select Boss y Raid Complete usan `overlay.*` porque no son popups convencionales; pueden resolver independientemente de la base. Detectores especializados emiten GOLD y Purchased por slot. La lista y evidencia actual están en `CONTEXT.md`; paths, regiones y anchors son verdad de código/tests.

OCR usa un boundary transversal separado para facts demand-driven. Un futuro VLM seguirá provider-agnostic y ninguna capa superior dependerá de proveedor, modelo o API concretos.

### Observaciones y facts

`Observation` es evidencia semántica inmutable: nombre namespaced, confidence normalizada, `ObservationSource`, valor escalar opcional y `RelativeRegion` opcional. No transporta frames, templates ni objetos de detector.

`ObservationBatch` agrupa evidencia ordenada de un único frame y permite nombres repetidos. Sus helpers buscan; no fusionan fuentes ni aplican policy.

Hay dos consumos deliberadamente distintos:

- landmarks de pantalla alimentan `ContextResolver`;
- facts internos como `currency.black_market.gold(slot)` y `status.black_market.purchased(slot)` son consumidos por el flow correspondiente.
- facts dinámicos demand-driven usan `RuntimeFact(value, confidence, quality, source, context, evidence)` y nunca se mezclan con `CharacterContext`.
- facts temporales conservan evidencia multiframe `(sequence, timestamp, activity, region)`; `UNKNOWN` puede ser un valor tipado seguro y no se convierte en permiso para actuar.

Un fact no se convierte en contexto sólo para facilitar navegación.

## ContextResolver

`bot/resolver.py` es puro, determinista y stateless. Recibe reglas base y overlay explícitas. Cada `ContextRule` exige observations namespaced con un threshold común; selecciona la mayor confidence de cada nombre y usa el mínimo sólo como diagnóstico.

La resolución base no tiene first-match ni desempate por confidence:

- cero candidatos → `UNKNOWN`;
- uno → `RESOLVED`;
- varios → `AMBIGUOUS` con candidatos explícitos.

Los overlays se resuelven independientemente y pueden coexistir con cualquier estado base. El resolver no implementa hysteresis, voting, debounce, transiciones ni memoria. `ResolvedState` separa base, subcontexto opcional, overlays y candidatos conflictivos.

## RuntimeObserver

`RuntimeObserver` une captura, Perception y Resolver sin mezclarlos. Cada `RuntimeSnapshot` conserva el `FrameSnapshot` BGR y garantiza que observations, estado resuelto, runtime facts y geometría proceden de ese mismo frame. La imagen permite comparaciones visuales acotadas sin saltarse el observer.

Las esperas son bounded, cancelables, rechazan sequences stale posteriores a una solicitud o acción y pueden exigir estabilidad continua sobre frames distintos. La estabilidad pertenece a la espera del caso de uso, no introduce estado implícito en `ContextResolver`.

`TemporalObserver` es una primitive pequeña sobre `RuntimeObserver`: reúne un número fijo de snapshots frescos, separados por intervalo, dentro de un timeout y un único contexto, y aborta ante overlays incompatibles declarados. No clasifica ni ejecuta input. `AutoBattleDetector` es su primer extractor: recorta el control, limita la métrica al borde, agrega por mediana y emite `setting.auto_battle` como `ON/OFF/UNKNOWN` sin OCR.

Todo efecto de una acción que tenga una postcondición observable fiable se verifica antes de continuar, incluso cuando la pantalla no cambia. Una interacción observada/verificada combina `RuntimeObserver + ActionExecutor`; el Flow o Rotation declara el efecto requerido y los guards, pero no implementa retries físicos manuales. Si no existe una señal robusta, la acción permanece explícitamente no verificable y usa policy conservadora: no se inventan postcondiciones débiles.

## Rotation

`bot/rotation.py` define `RotationStrategy.advance()` como contrato transversal. `StandardRotation` decide cómo cambiar una vez de personaje mediante estado semántico y solicita intents al `ActionExecutor`; no conoce flows, identidad de personajes ni ADB.

`bot/observed_scroll.py` es una operación transversal que compone `RuntimeObserver + ActionExecutor`. Conserva un frame settled A, observa frames transitorios T mientras se ejecuta un `Swipe` y exige un settled B fresco posterior al release/bounce. Clasifica progreso, edge candidate e intento inefectivo; aplica confirmaciones, timeout y máximo de intentos bounded. La similitud A/B por sí sola nunca prueba edge: debe existir movimiento transitorio efectivo del mismo intento.

`bot/character_select_scroll.py` sólo aporta el perfil específico de Character Select: ROI, thresholds, gestos de progreso/confirmación, settle y policy bounded. `StandardRotation` navega, delega `scroll_to_edge` y sólo intenta seleccionar si el resultado confirma edge; no contiene medición A/T/B ni detección de bounce. Después verifica la selección de la tarjeta con `bot/character_selection.py`, un detector local del marco amarillo de la posición target que no identifica personajes.

`bot/verified_transition.py` verifica acciones discretas contra una postcondición, tanto transiciones de contexto como efectos intra-screen: input, espera nominal, ventana de gracia sin input y, sólo cuando el consumidor aporta un guard que acepta el estado fresco actual, retry bounded. Una policy opcional puede esperar pasivamente que un guard inicialmente inconcluso se estabilice; nunca repite input desde `UNKNOWN`. Distingue éxito inicial, retrasado o posterior a retry, rechazo del guard, agotamiento, estado inesperado, timeout y fallo. No implementa recovery ni decide qué estados son seguros; Rotation o el Flow aportan precondición, postcondición y `retryable_from`.

`bot/controlled_wait.py` cubre otra semántica temporal: una actividad larga que el juego ya ejecuta y cuya entrada fue validada. `ControlledWait` recibe duración esperada o deadline monotónico, intervalo configurable, condición de finalización opcional, condición terminal explícita opcional y cancelación; duerme entre checks y devuelve `completed`, `terminated`, `cancelled`, `timeout` o `failed`. No ejecuta input, retry ni recovery. Una condición todavía falsa —incluido `UNKNOWN` interpretado por el consumidor— sólo significa que el final no fue observado y continúa hasta el límite; una excepción real de callback conserva `failed` como outcome distinto. Esperar horas hasta una disponibilidad futura pertenece a un scheduler, no a esta primitive.

`VerifiedTransition` conserva recuperación local de acciones cortas: `input → espera normal → grace → retry seguro`. Si esa recuperación se agota, produce un failure estructurado. Un futuro `ConflictResolver` podrá consumirlo para conexión, popup inesperado, app trabada, navegación segura, restart o recovery de sesión; no absorberá los guards ni retries locales. La futura calibración podrá escalonar retry rápido y luego conservador antes de escalar, sin alterar en este checkpoint los timings ya validados de Black Market.

## Flows

Los flows contienen intención y reglas de negocio deterministas. Declaran scope, precondition exacta o capability requerida y estados semánticos permitidos al completar; reaccionan a `RuntimeSnapshot` y emiten semantic actions.

`bot/flow_contracts.py` define `FlowContract(precondition, successful_postconditions)` y separa ese contrato de `FlowResult(status, events)`. `COMPLETED` significa que el flow terminó correctamente y dejó uno de los estados permitidos por su contrato; no implica Lobby. `FAILED` indica que continuar no es seguro y `CANCELLED` conserva una cancelación solicitada sin reclasificarla como fallo. `FlowEvent(kind, detail=None)` representa resultados de negocio extensibles y no controla la sesión. `BlackMarketFlow` declara `screen.lobby → screen.lobby`; `WorldBossFlow` declara entrada Lobby y salidas Lobby o World Boss.

`BlackMarketFlow` es `PER_CHARACTER`, comienza y termina en Lobby y no cambia de personaje. Su closure semántico incluye Black Market, Purchase Confirmation, Insufficient Gold, Inventory Full, GOLD y Purchased; Quick Menu no es prerequisite. Abrir/cerrar Black Market, seleccionar GOLD y responder a los tres popups son transiciones verificadas. Cada selección admite tres outcomes válidos declarados por el flow y sólo puede repetirse desde Black Market limpio si el target sigue GOLD y no Purchased. `Yes`, `No` y `OK` sólo pueden repetirse si persiste inequívocamente su mismo popup; `Yes` exige además Purchased en el slot y nunca repite la selección completa. El retorno de cada rama entrega Black Market limpio, fresco y estable antes del siguiente slot. Low Gold e Inventory Full producen business events no fatales, pero un fallo al cerrar o verificar sus popups es técnico y aborta. El flow no identifica ni libera inventarios. La policy funcional detallada está en `CONTEXT.md`.

`WorldBossFlow` es `PER_CHARACTER` y mantiene la intención `ALWAYS_PARTICIPATE`. Lee sapphires antes de observar o actuar; `<5` termina en Lobby sin input. Las rutas de navegación y los botones Previous Rewards, Start, Inventory Full/No y Raid Complete/Continue son intents semánticos con postcondiciones verificadas. Después de Select Boss se estabiliza explícitamente la bifurcación entre World Boss limpio y Previous Rewards tardío, evitando habilitar Start durante una base transitoria. Inventory Full es un outcome de Start que termina correctamente en World Boss y no contiene policy de limpieza. La batalla confirma Auto Battle una sola vez, lee el timer, espera pasivamente `timer + margen` sin percepción y recién entonces consulta Raid Complete cada segundo durante un timeout bounded. La presencia del overlay Raid Complete es la única condición de éxito y tiene prioridad aunque la base esté `UNKNOWN`, en transición o sea distinta; su ausencia continúa sin input. El flow no implementa matching, OCR, ADB ni recovery de conexión.

Los support operations futuros seguirán `check → bounded support operation → recheck → continue/skip/fail`; no se permiten llamadas recursivas arbitrarias entre flows.

## Semantic Actions y ActionExecutor

Los intents modelan acciones del dominio y primitives físicas tipadas. El slice actual define acciones de Black Market, World Boss, las mínimas de Rotation y `ToggleAutoBattle`. `bot/quick_menu.py` selecciona transversalmente el intent `OpenCharacterSelect` con layout base para Lobby o desplazado para cualquier otro contexto permitido; los consumidores sólo aportan el contexto de origen y las coordenadas permanecen en `ActionExecutor`. `Swipe(start, end, duration)` es genérico y no contiene policy de scroll, bounce ni conocimiento de pantallas.

`ActionExecutor` es el único traductor de intent a input físico. Valida taps o swipes normalizados, deriva pixels desde la geometría del frame y delega en `AdbClient`. No consulta Perception, no interpreta movimiento/bounce, no espera postcondiciones y no decide gameplay.

El boundary de interacción queda: `Rotation / Flow / operación transversal → RuntimeObserver + ActionExecutor → AdbClient`, con la primitive observada adecuada. `AutoBattleEnsurer` sólo toca desde OFF temporal confirmado, exige ON en una ventana posterior y suprime retry desde UNKNOWN, cambio de contexto o Raid Complete. `ActionExecutor` sólo emite input físico; retry y verificación permanecen en la operación observada. Conflict/Recovery queda reservado para estados inesperados no resueltos localmente.

## Device / ADB

`bot/adb.py` define `AdbClient`, límite único para procesos y comandos ADB. Recibe ejecutable, serial y timeout explícitos; construye argumentos separados y traduce fallos a `AdbError` o `AdbTimeoutError` con contexto.

Expone estado, shell, taps/swipes pixel, push, forwards y procesos persistentes. El owner de un proceso o forward conserva su lifecycle. Tests normales inyectan un runner fake y no requieren ADB instalado.

## Perception Workbench

Workbench es una composición humana paralela, fuera del runtime de gameplay:

```text
ScrcpyFrameSource → PerceptionEngine → ContextResolver ─┐
Android touch → HumanInputObserver (read-only) ─────────┴→ Workbench UI / raw evidence
```

`HumanInputObserver` observa `getevent`, reconstruye gestos y normaliza coordenadas/rotación; nunca envía input. La UI trabaja sobre copias, conserva ground truth explícito, limita escritura y separa vocabulary de adquisición del catálogo productivo.

La evidencia de una interacción es observacional. Sólo una confirmación humana explícita puede registrar destino semántico; ni el frame posterior ni una prediction rellenan ground truth, prueban causalidad o crean targets. Raw sessions viven en `artifacts/`; sólo manifests curados bajo `datasets/` alimentan evaluación productiva.

El protocolo conversacional y las restricciones de hardware están centralizados en `AGENTS.md`.

## Orquestación de sesión

El producto objetivo es un orquestador configurable, no un agente general:

```text
User Control Panel
  → SessionPlan
    → SessionRunner
      ├── Selected PER_CHARACTER Flow(s)
      └── RotationStrategy.advance()
```

`SessionPlan` expresa intención: `character_count`, flows ordenados y strategy. `SessionRunner` consulta el contrato del próximo componente, pide a `MinimalPreconditionEnsurer` sólo ese requisito y valida después uno de sus estados finales declarados. Si el requisito ya se cumple no navega; si sólo exige `quick_menu_accessible` no fuerza Lobby. Para un requisito exacto `screen.lobby`, el helper sólo puede normalizar desde un contexto declarado Quick Menu-capable mediante un callback de navegación que el composition root deberá implementar con transiciones verificadas. No contiene coordenadas ni ADB. Repite el bloque exactamente `character_count` veces, incluido el advance final que cierra el ciclo; no trata 27 como caso especial ni reprocesa el personaje inicial después del retorno.

`quick_menu_accessible` es una capability de policy (`bot/quick_menu.py`), no `screen.quick_menu_accessible` ni un nodo de navegación. El allow-list productivo contiene `screen.lobby` y `screen.world_boss`; ambos abren el mismo `menu.quick` con el target común del header, pero sus botones internos no comparten origen: Character usa `(0.0704, 0.7835)` en Lobby y `(0.2000, 0.7835)` en el layout desplazado. Nuevos contextos se incorporan sólo después de validación live. Quick Menu actúa como hub operacional para la normalización mínima a Lobby, sin grafo ni pathfinding.

Business events se agregan y registran sin interpretación específica. Un `FlowResult.FAILED`, una postcondición contradictoria o un `RotationResult` fallido abortan la sesión sin intentar el siguiente personaje. La cancelación se observa en el runner y en waits/facts que aceptan el boundary; `Ctrl+C` y la futura GUI solicitan el mismo token. `SessionCharacterResult` y `SessionResult` preservan el progreso parcial.

El primitive de `rotation.standard` requiere la capability `quick_menu_accessible`, no Lobby por definición, y usa Quick Menu → Character Select → bottom confirmado → última posición → Lobby. Sólo acepta contextos presentes en la policy productiva: Lobby y World Boss. El comportamiento MRU permite recorrer personajes sin identidad visual y `character_count = 28` es configuración explícita compartida. La captura transitoria concurrente no cambia los límites: Rotation solicita un intent semántico y `ActionExecutor` sigue siendo quien ejecuta el input físico. El loop aislado 28/28 y el regreso final al personaje inicial están validados; MAIN/SUBS quedan para strategies futuras.

La identidad futura sigue un boundary independiente:

```text
OCR / Perception extractors
  → CharacterContextProvider
    → CharacterContext
      → SessionRunner / logging / flows
```

`SessionRunner` coordinará como máximo una adquisición opcional desde Lobby por personaje. Identidad ausente no es fatal cuando sólo alimenta logging. `StandardRotation` no identifica personajes y una strategy futura identity-aware será otra implementación de `RotationStrategy`, no una modificación de la standard.

`CharacterContext` contiene identidad y metadata relativamente estable durante el personaje (`name`, `name_confidence`). Un futuro provider podrá adquirirla una vez desde Lobby para compartirla con flows y logging; en este checkpoint permanece `name=None`.

Los datos dinámicos —sapphires, stamina, recursos, battle timer o rank— son Runtime Facts y se adquieren cuando el contexto o flow los necesita. `RuntimeFactReader` registra extractors y expone `read_fact()` más helpers tipados; exige frames posteriores a la solicitud y el contexto resuelto requerido. Cada extractor posee ROI, preprocessing, parser y policy bounded, mientras `RapidOcrEngine` sólo transforma una imagen preparada en `OcrResult(text, confidence, metadata)` mediante modelos ONNX locales. Los flows no recortan screenshots, llaman OCR ni parsean strings.

Los facts productivos iniciales son `resource.sapphires` en `screen.lobby` y `battle.timer_remaining` en `screen.world_boss_battle`. Sapphires usa consenso exacto de dos observaciones independientes dentro de tres intentos; discrepancia, unreadable, cambio de contexto, timeout, cancelación y fallo son outcomes distintos. El timer es dinámico y por eso confirma una observación sintácticamente válida, conservando el raw y convirtiendo `M:SS.t` a segundos restantes con `ceil`. Confidence combina score OCR, validez de parser, contexto correcto y soporte del consenso. La importancia decisional sigue perteneciendo al consumidor.

El slice semántico World Boss distingue `screen.battle_mode_select`, `overlay.world_boss_select_boss`, `popup.world_boss_previous_rewards`, `popup.world_boss_inventory_full`, `screen.world_boss`, `screen.world_boss_battle` y `overlay.world_boss_raid_complete`. `setting.auto_battle` usa 10 frames dentro de un budget de adquisición de `4 s`, ROI `(0.835, 0.018, 0.890, 0.078)`, mediana de actividad del borde y thresholds `OFF ≤ 2`, `ON ≥ 5`, conservando la zona intermedia como UNKNOWN. La evidencia live curada separó 8 ventanas OFF y 9 ON con 0 FP/FN; ON inicial usó 0 taps y OFF pasó a ON confirmado con un tap. `WorldBossFlow` compone `Auto Battle verificado ON → timer inicial + margen configurable de 5 s → polling cada 1 s por hasta 25 s → Raid Complete visual`. Countdown y timer sólo optimizan observación: nunca prueban success sin el overlay. Auto Repeat tiene menús y modos propios, no es una primitive transversal y queda fuera del primer flow.

El runtime unattended futuro necesita timeouts, recovery transversal, logging, aislamiento de fallos, cleanup y policy de continuación. Hasta entonces, el vertical slice aborta ante errores técnicos después de registrar y limpiar.

## AdsManager

`bot/ads_manager.py` sigue siendo un subsistema standalone basado en UIAutomator2 para aplicaciones o packages externos. No participa en Perception ni `ContextResolver`; su contrato futuro es recuperar control y devolverlo al juego.

## Legacy y migración

El tag `legacy-pre-hybrid` y `docs/legacy/` preservan la implementación anterior. `constants.py` conserva taxonomía y conocimiento de dominio, pero no es configuración objetivo. Los consumers legacy rotos no se reparan mediante shims: cada capacidad se migra incrementalmente a los límites 0.2 cuando un caso funcional la requiere.

OpenCV, scrcpy y ADB no son legacy por sí mismos; lo legacy es acoplar captura, reconocimiento, decisión y coordenadas en el mismo modelo.
