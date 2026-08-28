# Arquitectura — Kritika FarmBot 0.2

Este documento define límites, contratos y data flow vigentes. El estado productivo está en [`CONTEXT.md`](CONTEXT.md), el trabajo próximo en [`ROADMAP.md`](ROADMAP.md) y la evolución en [`docs/HISTORY.md`](docs/HISTORY.md).

## Data flow productivo

```text
Capture
  → Perception
  → Semantic Observations / Runtime Facts
  → ContextResolver
  → Flow / SessionRunner / Rotation
  → semantic/verified runtime operations
  → ActionExecutor
  → AdbClient
```

Los Runtime Facts no necesariamente pasan por `ContextResolver`: extractors demand-driven consumen snapshots context-correct y entregan values tipados al flow. Las operaciones verificadas componen observación y ejecución física, pero preservan ambos límites.

Invariantes:

```text
Rotation != Flow
Flow != ActionExecutor
ActionExecutor != Perception
GUI contains no business logic
```

- Capture obtiene frames y posee recursos; no reconoce pantallas.
- Perception observa y emite evidencia semántica; no navega ni decide gameplay.
- `ContextResolver` interpreta observaciones; no captura, ejecuta acciones ni conserva policy de flows.
- Flows deciden negocio y solicitan operaciones/intents semánticos; no hacen matching ni llaman ADB.
- Rotation cambia de personaje como estrategia transversal; no ejecuta flows.
- `ActionExecutor` traduce intents a input físico; no observa efectos ni decide policy.
- `AdbClient` es el único límite activo de comandos ADB.

## Configuración, lifecycle y composition root

`RuntimeConfig` es explícito e import-safe; `from_env()` carga configuración sólo a pedido. Rutas locales, seriales y geometría no se hardcodean. Toda geometría visual deriva de `frame.shape`; puntos normalizados se proyectan recién en el executor.

`bot/runtime.py` construye ADB, captura y facts. `bot/productive_runtime.py` es el composition root compartido: adquiere configuración, `AdbClient`, `ScrcpyFrameSource`, percepción, resolver, observer, OCR facts, Auto Battle, `ActionExecutor`, flows, Rotation y runner. El owner mantiene cleanup explícito de source, proceso, socket y forward, incluso ante fallo.

`bot/flow_registry.py` es la única lista productiva de flows. Cada `FlowDefinition` declara id, display name, scope, contrato y factory; `FlowRegistry` valida y conserva orden explícito. No hay discovery, reflection ni plugin system. El registry actual contiene `black_market` y `world_boss`.

## Capture y Perception

`ScrcpyFrameSource` publica `FrameSnapshot` BGR con sequence y timestamp monotónico. Posee server, forward, proceso, socket, decoder y receiver; cleanup es best-effort e idempotente. Capture no importa Perception, Resolver, flows ni actions.

`PerceptionEngine` ejecuta detectores explícitos y precargados sobre un frame y produce un `ObservationBatch` con la misma identidad temporal. El backend productivo es OpenCV local; assets, ROIs y calibraciones concretas pertenecen al código, tests y manifests, no a este contrato.

`Observation` es evidencia inmutable namespaced con confidence, source, value/región opcionales. `ObservationBatch` agrupa evidencia de un único frame y permite nombres repetidos; sus helpers buscan, no resuelven policy.

Hay tres usos separados:

- landmarks de base/overlay alimentan `ContextResolver`;
- facts intra-screen como GOLD/Purchased permanecen en el snapshot para el flow dueño;
- Runtime Facts demand-driven/temporales usan extractors tipados y evidencia propia.

Un fact no se convierte en contexto para facilitar navegación.

## ContextResolver y RuntimeObserver

`ContextResolver` es puro, determinista y stateless. Con reglas explícitas, cero/uno/varios candidatos base producen `UNKNOWN`/`RESOLVED`/`AMBIGUOUS`; no hay first-match, voting, hysteresis ni desempate por confidence. Overlays se resuelven independientemente y pueden coexistir con base desconocida.

`RuntimeObserver` une frame, observations, estado, facts intra-screen y geometría en un `RuntimeSnapshot` coherente. `observe()` y `wait_until()` son el boundary de consumidores; las esperas exigen sequences frescas, tienen timeout, pueden exigir estabilidad y aceptan cancelación/abort conditions. La estabilidad pertenece al consumidor, no al resolver.

`TemporalObserver` reúne un número bounded de snapshots frescos, separados en el tiempo y context-correct. No clasifica ni ejecuta input. `AutoBattleDetector` es un extractor temporal que produce `setting.auto_battle = ON/OFF/UNKNOWN`.

## Runtime Facts y CharacterContext

`RuntimeFact(value, confidence, quality, source, context, evidence)` representa un valor dinámico adquirido cuando un flow lo necesita. `RuntimeFactReader` registra extractors, exige frames frescos/resueltos del contexto requerido y devuelve outcomes explícitos para confirmed, unreadable/uncertain, context mismatch, timeout, cancelación o fallo. Frames transitorios sin resolución pueden consumirse dentro del mismo budget sin autorizar OCR ni input.

El boundary OCR es:

```text
RuntimeSnapshot
  → extractor (context + ROI + preprocessing)
  → OcrEngine / OcrResult
  → parser
  → RuntimeFactReader
  → consumidor
```

Los flows no recortan píxeles, invocan el engine ni parsean strings. Los facts productivos iniciales son sapphires y battle timer; Auto Battle es temporal, no OCR.

`CharacterContext` contiene metadata relativamente estable de un personaje, hoy `name=None` y `name_confidence=None`. El índice `1..N` es posición de sesión, no identidad. Recursos, stamina, timers y rank son Runtime Facts. Un futuro `CharacterContextProvider` podrá adquirir identidad una vez por personaje y enriquecer logging/flows sin modificar `StandardRotation`; ausencia de nombre no debe ser fatal para consumidores observacionales.

## Operaciones verificadas

Una acción con postcondición observable fiable debe verificarse antes de continuar. El consumidor declara precondition, expected outcome, abort condition y estado desde el cual sería seguro repetir; la operación observada compone `RuntimeObserver + ActionExecutor`.

`VerifiedTransition` implementa una interacción discreta:

```text
precondition fresca
  → input
  → espera nominal
  → grace pasiva
  → guard fresco de retry
  → retry bounded (si el guard lo autoriza)
```

Distingue éxito inicial, durante grace, tras retry, guard rechazado, agotamiento, estado inesperado, timeout y fallo. No decide qué estado es seguro ni implementa recovery transversal. `UNKNOWN` jamás satisface por defecto un retry guard y no autoriza input.

`ObservedScroll` es una operación continua transversal. Conserva frame settled A, observa movimiento transitorio T durante `Swipe` y exige frame settled B posterior; clasifica progreso, edge candidate o gesto inefectivo con intentos bounded. Similitud A/B sin movimiento T no prueba borde. El perfil Character Select aporta ROI/thresholds/gestos; `StandardRotation` sólo consume el resultado.

`ControlledWait` modela actividad larga ya iniciada. Recibe exactamente una duración esperada o deadline monotónico, intervalo, completion condition opcional, terminal condition opcional y cancelación. Duerme entre checks y devuelve `completed`, `terminated`, `cancelled`, `timeout` o `failed`:

- sin conditions, alcanzar el bound significa que la espera pasiva se completó;
- con alguna condition, alcanzar el bound sin observarla es `timeout`;
- una condition falsa sólo significa “todavía no observado” y continúa;
- una terminal explícita produce `terminated`; una excepción de callback produce `failed`.

No ejecuta input, retry, navegación ni recovery. Esperar disponibilidad futura durante horas pertenece a un scheduler.

## Flows y contratos

`FlowContract` declara una precondición (`EXACT_STATE` o capability) y uno o más estados exactos permitidos al completar. `FlowResult` separa `COMPLETED`, `FAILED` y `CANCELLED`; completion sólo es válido si la postcondición actual está declarada. `FlowEvent` representa un resultado de negocio no fatal y no controla la sesión.

`BlackMarketFlow` es `PER_CHARACTER`, declara Lobby → Lobby y posee la policy de GOLD/Purchased, Purchase Confirmation, Insufficient Gold e Inventory Full. Todas las interacciones observables son verificadas. No identifica items/personajes ni libera inventario.

`WorldBossFlow` es `PER_CHARACTER`, declara Lobby → Lobby/World Boss y posee policy de sapphires, navegación, Previous Rewards, guards de inventario, Auto Battle, timer, Raid Complete y Continue. Raid Complete depende del overlay, no de que una base concreta resuelva simultáneamente. El flow no implementa OCR, matching, ADB ni recovery de conexión; consume esos boundaries.

Support operations futuros seguirán `check → operación bounded → recheck → continue/skip/fail`; no se permiten llamadas recursivas arbitrarias entre flows.

## Rotation y Quick Menu

`RotationStrategy.advance()` es un contrato transversal. `StandardRotation` requiere la capability `quick_menu_accessible` y deja Lobby como única postcondición exitosa. Abre Quick Menu, Character Select, usa `ObservedScroll` hasta borde confirmado, verifica la selección visual de la tarjeta target, confirma y exige Lobby fresco. No conoce flows, nombres de personaje ni ADB.

`quick_menu_accessible` es una capability de policy, no una pantalla ni un nodo de navegación. Su allow-list productivo contiene Lobby y World Boss. `menu.quick` sigue siendo un overlay observable; `bot/quick_menu.py` elige el layout del intent interno según el contexto de origen. Incorporar otro contexto requiere evidencia live, no inferencia desde metadata legacy.

## SessionRunner

`SessionPlan` expresa `character_count`, flows `PER_CHARACTER` ordenados y una `RotationStrategy`. Para cada personaje, `SessionRunner`:

1. asegura sólo el requisito del siguiente componente;
2. ejecuta cada flow en orden;
3. verifica una postcondición permitida y registra sus business events;
4. ejecuta y verifica exactamente un advance;
5. conserva resultado/progreso parcial.

Si un requisito ya se cumple, no navega. `MinimalPreconditionEnsurer` sólo normaliza cuando existe una operación explícita/verificada; no contiene un grafo general. El advance final cierra el ciclo y no reprocesa el personaje inicial. Fallos técnicos, postcondiciones contradictorias o Rotation fallida abortan conservadoramente. Cancelación se propaga como `CANCELLED`, no como fallo.

## Semantic Actions, ActionExecutor y ADB

Los intents tipados modelan acciones del dominio; `Swipe` es una primitive física sin policy. `ActionExecutor` valida coordenadas normalizadas, proyecta pixels desde la geometría del frame y delega taps/swipes a `AdbClient`. No observa postcondiciones, espera, hace retry ni decide gameplay.

`AdbClient` recibe executable, serial y timeout explícitos; expone state, shell, input, push, forwards y procesos persistentes. Traduce errores y no conoce frames ni semántica. Tests normales inyectan fakes y no requieren dispositivo.

## Frontends, logging y cancelación

CLI (`tools.run_flow`, `tools.run_session`) y GUI (`tools.gui`) seleccionan definitions del mismo `FlowRegistry` y llaman `ProductiveRuntime`. No duplican flows ni policy.

La GUI contiene modelos de selección/progreso y un `GuiRuntimeController` con un único worker no-daemon. El worker ejecuta runtime y encola eventos/resultados; Tk sólo drena/renderiza en el main thread. `Run Flow Once`, `Run Session`, orden, character count, debug y stop son control de ejecución, no business logic.

`RuntimeEventStream` crea eventos estructurados con timestamp, level, component, name y fields; distribuye a JSONL persistente, consola y suscriptores. Fallos de un consumer de observabilidad no pueden alterar gameplay ni provocar input. Debug cambia visibilidad, no policy.

`CancellationToken` es thread-safe. CLI signals y `Stop Safely` solicitan el mismo token; runner, waits, facts y operaciones que lo aceptan terminan en boundaries seguros. Cerrar GUI no mata el worker activo.

## Adquisición humana, ConflictResolver y legacy

Perception Workbench es tooling read-only paralelo al runtime. Sólo ground truth humano explícito puede registrar significado/destino; taps, predictions o frames posteriores no prueban causalidad. Evidencia raw queda ignorada y sólo manifests curados alimentan producción.

Un futuro `ConflictResolver` vivirá por encima de failures estructurados de flows/operaciones para tratar conexión, popup inesperado, app trabada, restart o policy de sesión. No absorberá matching, guards locales ni retries de `VerifiedTransition`, y no se implementará sin casos/outcomes acordados.

`AdsManager` continúa standalone. El tag `legacy-pre-hybrid` y `docs/legacy/` preservan la implementación previa; tecnologías útiles como OpenCV, scrcpy o ADB no son legacy por sí mismas. No se reparan consumers antiguos mediante shims ni se vuelve a acoplar captura, reconocimiento, decisión y coordenadas.
