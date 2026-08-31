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

`bot/flow_registry.py` es la única lista productiva de flows. Cada `FlowDefinition` declara id, display name, scope, contrato y factory; `FlowRegistry` valida y conserva orden explícito. No hay discovery, reflection ni plugin system. El registry actual contiene `black_market`, `world_boss`, `daily_quests`, `mailbox` y `guild_check_in`, en ese orden default.

## Capture y Perception

`ScrcpyFrameSource` publica `FrameSnapshot` BGR con sequence y timestamp monotónico. Posee server, forward, proceso, socket, decoder y receiver; cleanup es best-effort e idempotente. Capture no importa Perception, Resolver, flows ni actions.

`PerceptionEngine` ejecuta detectores explícitos y precargados sobre un frame y produce un `ObservationBatch` con la misma identidad temporal. El backend productivo es OpenCV local; assets, ROIs y calibraciones concretas pertenecen al código, tests y manifests, no a este contrato.

`Observation` es evidencia inmutable namespaced con confidence, source, value/región opcionales. `ObservationBatch` agrupa evidencia de un único frame y permite nombres repetidos; sus helpers buscan, no resuelven policy.

Hay tres usos separados:

- landmarks de base/overlay alimentan `ContextResolver`;
- facts intra-screen como GOLD/Purchased permanecen en el snapshot para el flow dueño;
- Runtime Facts demand-driven/temporales usan extractors tipados y evidencia propia.

Las observaciones intra-Socket de velo rojo y fase oscura de Enhance son operation-scoped: Perception sólo reporta evidencia. No seleccionan estrategia, no autorizan KARATS ni convierten una coincidencia aislada en permiso de venta.

Daily Quests y Character Mail usan semántica y actions productivas separadas. `screen.quests`/`mode.daily_quests` separan el `Claim` de filas del reward de progreso; `screen.mailbox`/`mode.mailbox_character_mail` gatean `Claim` y `Delete` para no confundir Account Mail. El spinner cyan se expone como `activity.mailbox_claim_processing`, una observación operation-scoped que puede faltar durante fases oscuras de rotación. Perception no interpreta bubbles, no declara Inbox vacío y no decide si quedaron rewards reclamables.

Guild usa `landmark.guild_message_tab` para resolver `screen.guild` desde una zona estable fuera del bubble superior. `GuildAttendanceDetector` mide una franja interior del fill del botón y emite exactamente uno de `indicator.guild_attendance_active/completed`; el resolver deriva los statuses correspondientes. El detector se calla bajo `menu.quick`, porque el overlay cubre parte del control y navegación no debe heredar un status de negocio. El bubble no se modela.

Equipment Inventory Full usa `popup.equipment_inventory_full` como overlay global, separado del caller. `screen.combine` deriva de un landmark compuesto que acepta el tab Fuse persistente o la actividad inequívoca de animación, evitando un estado `UNKNOWN` en la fase que consumirá `TapThroughAnimation`. Los modos activos y tres observaciones posicionales de `N` se combinan en el resolver para producir disponibilidad Transmute, Ethereal y Fuse. Los títulos de panel/modal aportan estados intermedios con consumidores futuros concretos. Las tres operaciones comparten `activity.combine_animation_tappable`; Perception no decide el orden ni si debe combinar.

Los landmarks base evitan regiones con oclusión dinámica conocida. En Socket, el tab izquierdo persistente sustituye al encabezado superior derecho; en Battle Mode, el título de la tarjeta World Boss sustituye al encabezado superior. Popups, overlays y el panel Black Market se renderizan por encima del chat, por lo que su layering también forma parte de la auditoría; una ROI base situada en una zona dinámica requiere positivos reales con el overlay antes de considerarse robusta.

Un fact no se convierte en contexto para facilitar navegación.

La evaluación offline productiva conserva los manifests curados como fuente de verdad y cachea sólo resultados derivados por par detector/frame. Un hit exige identidad de contenido del frame, configuración y código del detector, contenido de assets, helpers CV compartidos, runtime OpenCV/NumPy y versión/lógica del evaluator; labels y `ContextResolver` se recalculan siempre. La cache bajo `artifacts/` es regenerable y una entrada corrupta o no fingerprintable se invalida conservadoramente; `--full-rebuild` fuerza auditoría global desde cero.

## ContextResolver y RuntimeObserver

`ContextResolver` es puro, determinista y stateless. Con reglas explícitas, cero/uno/varios candidatos base producen `UNKNOWN`/`RESOLVED`/`AMBIGUOUS`; no hay first-match, voting, hysteresis ni desempate por confidence. Overlays se resuelven independientemente y pueden coexistir con base desconocida.

`RuntimeObserver` une frame, observations, estado, facts intra-screen y geometría en un `RuntimeSnapshot` coherente. `observe()` y `wait_until()` son el boundary de consumidores; las esperas exigen sequences frescas, tienen timeout, pueden exigir estabilidad y aceptan cancelación/abort conditions. La estabilidad pertenece al consumidor, no al resolver.

Los consumidores de Claim All reutilizan esa estabilidad: Daily Quests termina al desaparecer establemente `status.daily_quests_claimable` bajo su base/modo; Mailbox termina sólo tras ausencia estable de `activity.mailbox_claim_processing` y retorno estable del modo Character Mail. En Mailbox no basta un único frame sin spinner y la persistencia de `status.mailbox_claimable` después de la quiescencia representa leftovers, no procesamiento activo.

La completion de Attendance exige `screen.guild + status.guild_attendance_completed` estable durante `0.75 s` sobre frames frescos, con budget de `10 s`. No usa `ControlledWait`, bubble ni timing fijo como postcondición.

`TemporalObserver` reúne un número bounded de snapshots frescos, separados en el tiempo y context-correct. Un frame `UNKNOWN`/`AMBIGUOUS` transitorio consume budget pero no entra en la ventana ni autoriza input; un contexto incompatible ya resuelto aborta inmediatamente. Los overlays de interrupción declarados tienen prioridad sobre una base momentáneamente no resuelta. La primitive no clasifica ni ejecuta input. `AutoBattleDetector` es un extractor temporal que produce `setting.auto_battle = ON/OFF/UNKNOWN`.

## Runtime Facts y CharacterContext

`RuntimeFact(value, confidence, quality, source, context, evidence)` representa un valor dinámico adquirido cuando un consumidor lo necesita. `RuntimeFactReader` registra extractors, exige frames frescos/resueltos del contexto base y de todos los overlays requeridos por el extractor, y devuelve outcomes explícitos para confirmed, unreadable/uncertain, context mismatch, timeout, cancelación o fallo. Frames transitorios sin resolución y lecturas OCR temporalmente ilegibles pueden consumirse dentro del budget bounded del extractor sin autorizar input; el timer usa hasta 10 frames frescos separados 0,5 s porque el chat puede cubrir su única ubicación visual. Su parser específico acepta sólo `0..90` segundos; un valor fuera del límite de negocio es ilegible y nunca llega a `ControlledWait`.

El boundary OCR es:

```text
RuntimeSnapshot
  → extractor (context + ROI + preprocessing)
  → OcrEngine / OcrResult
  → parser
  → RuntimeFactReader
  → consumidor
```

Flows y support operations no recortan píxeles, invocan el engine ni parsean strings. Los facts OCR productivos son sapphires, battle timer y el nivel mostrado en el popup Sell de Socket; Auto Battle es temporal, no OCR.

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

`TapThroughAnimation` modela una animación salteable ya iniciada. Alterna snapshots frescos con un tap semántico sólo cuando el caller confirma una fase tappable; impone intervalo, timeout y máximo de taps, y termina inmediatamente ante la postcondición. Estados flash/transitorios pueden observarse sin input; `UNKNOWN` o un estado incompatible nunca autorizan tap. La primitive compone `RuntimeObserver + ActionExecutor`, pero no reconoce pantallas ni elige estrategia.

## Flows y contratos

`FlowContract` declara una precondición (`EXACT_STATE` o capability) y uno o más estados exactos permitidos al completar. `FlowResult` separa `COMPLETED`, `FAILED` y `CANCELLED`; completion sólo es válido si la postcondición actual está declarada. `FlowEvent` representa un resultado de negocio no fatal y no controla la sesión.

`BlackMarketFlow` es `PER_CHARACTER`, declara Lobby → Lobby y posee la policy de GOLD/Purchased, Purchase Confirmation, Insufficient Gold e Inventory Full. Todas las interacciones observables son verificadas. No identifica items/personajes ni libera inventario.

`WorldBossFlow` es `PER_CHARACTER`, declara Lobby → Lobby/World Boss y posee policy de sapphires, navegación, Previous Rewards, guards de inventario, Auto Battle, timer, Raid Complete y Continue. Raid Complete depende del overlay, no de que una base concreta resuelva simultáneamente. Si ese overlay interrumpe la adquisición temporal de Auto Battle, el flow lo reacquire pasivamente y salta timer/espera larga antes de Continue. El flow no implementa OCR, matching, ADB ni recovery de conexión; consume esos boundaries.

`DailyQuestsFlow` y `MailboxFlow` son `PER_CHARACTER`, declaran Lobby → Lobby y contienen únicamente su policy de negocio. `OpenQuests` valida primero el shell que restaura el último tab del personaje; `SelectDailyQuests` se ejecuta una vez sólo cuando falta `mode.daily_quests` y exige ese modo como postcondición. Claim All es single-attempt en ambos. Daily acepta no-op inicial y completa por desaparición estable del status. Mailbox separa onset bounded, actividad observada y quiescencia estable; ausencia de onset sólo es no-effect cuando los claims persisten de forma estable. Delete Read ocurre después de esa rama y únicamente con read mail observable; una oclusión transitoria del tab bajo `screen.mailbox` prolonga pasivamente la espera, mientras el éxito sigue exigiendo retorno estable a Character Mail sin Read. Leftovers son `FlowEvent` no fatal.

`GuildCheckInFlow` es `PER_CHARACTER`, declara Guild → Guild y no contiene navegación. Completed inicial es no-op; Active autoriza un único tap y una espera fresca bounded por Completed estable. No existe retry del tap. Timeout, estados contradictorios/incompatibles y completion no verificable producen fallo conservador; cancelación se propaga.

Las support operations siguen `check → operación bounded → recheck → continue/skip/fail`; no son flows, no entran en GUI/`FlowRegistry` y no permiten llamadas recursivas arbitrarias entre flows. El caller conserva la policy de cuándo invocarlas y entrega un return plan con acción y estado exacto esperado; la operación sólo reporta éxito después de verificar ese retorno.

`SocketInventoryRelief` requiere `screen.socket` limpio, intenta Enhance All sólo con GOLD y, ante No Material, puede buscar de forma bounded un ópalo incompatible visible. Sell in Bulk se autoriza únicamente con velo rojo y un fact de nivel confirmado en `0`; lectura no confirmada o nivel distinto cancela la venta. Sus outcomes explícitos son `RELIEVED`, `NO_RELIEF_AVAILABLE`, `FAILED` y `CANCELLED`. `WorldBossFlow` posee tanto el `Yes` inicial como el permiso local de un único intento positivo por ejecución; una segunda aparición usa `No`. El único return plan compuesto productivamente es `ExitSocket → screen.world_boss`.

`EquipmentCombineRelief` es otra support operation, no una extensión de Socket ni un flow. Recibe un return plan exacto del caller y recorre siempre Transmute → Ethereal condicional → Fuse, acumulando efectos sin short-circuit. Cada paso interpreta su status únicamente bajo el tab activo, usa transiciones verificadas hacia modal/panel, reutiliza `TapThroughAnimation` con la actividad común y exige desaparición fresca del status. Ethereal también admite que una combinación corta regrese directamente a Random Part antes de observar una fase tappable, pero sólo declara efecto después de volver a Transmute y comprobar que su guard desapareció; cerrar el popup sin efecto sigue fallando. Un guard presente sin animación/postcondición o el defensivo Ethereal de material insuficiente produce `FAILED`; no se degrada a no-op. Sus outcomes son `RELIEVED`, `NO_RELIEF_AVAILABLE`, `FAILED` y `CANCELLED`.

`WorldBossFlow` posee la entrada `Combine`, el único permiso positivo de Equipment Full por `run()` y el return plan productivo `ExitCombine → screen.world_boss`. El permiso se consume sólo después de observar Combine. Una segunda aparición usa el cierre negativo, emite el business event y termina el flow de forma no fatal. La operación no está registrada en `FlowRegistry` ni expuesta en GUI.

Después de Bulk, un frame Socket limpio puede preceder al landmark estable de Equipment Home. Esa fase sólo prolonga pasivamente la espera bounded: no satisface la postcondición, no autoriza retry destructivo y el éxito sigue exigiendo popup ausente, Equipment Home estable y desaparición del candidato previo.

## Rotation y Quick Menu

`RotationStrategy.advance()` es un contrato transversal. `StandardRotation` requiere la capability `quick_menu_accessible` y deja Lobby como única postcondición exitosa. Abre Quick Menu, Character Select, usa `ObservedScroll` hasta borde confirmado, verifica la selección visual de la tarjeta target, confirma y exige Lobby fresco. No conoce flows, nombres de personaje ni ADB.

`quick_menu_accessible` es una capability de policy, no una pantalla ni un nodo de navegación. Su allow-list productivo contiene Lobby, World Boss y Guild. `menu.quick` sigue siendo un overlay observable; `bot/quick_menu.py` elige el layout del intent interno según el contexto de origen. Guild acepta exactamente un status Attendance al abrir el menú y usa el layout desplazado adquirido.

La operación productiva `Quick Menu → Guild` selecciona el target base o desplazado y exige `screen.guild` con un estado Attendance coherente como postcondición. La evidencia live confirma `Lobby → menu.quick → screen.guild` y que `screen.guild` abre `menu.quick` con el layout desplazado.

`MinimalPreconditionEnsurer` conserva callbacks separados para normalizar únicamente a Lobby o Guild. El composition root implementa ambas rutas con transiciones verificadas; un requisito Guild ya satisfecho no invoca navegación. No existe navigation graph ni generalización a otros destinos. `SessionRunner` continúa sin actions ni business logic.

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

La GUI contiene modelos de selección/progreso, un timer monotónico de presentación para `Run Session` y un `GuiRuntimeController` con un único worker no-daemon. El worker ejecuta runtime y encola eventos/resultados; Tk sólo drena/renderiza y actualiza el timer en el main thread. `Run Flow Once`, `Run Session`, orden, character count, debug y stop son control de ejecución, no business logic.

`RuntimeEventStream` crea eventos estructurados con timestamp, level, component, name y fields; distribuye a JSONL persistente, consola y suscriptores. Fallos de un consumer de observabilidad no pueden alterar gameplay ni provocar input. Debug cambia visibilidad, no policy.

`CancellationToken` es thread-safe. CLI signals y `Stop Safely` solicitan el mismo token; runner, waits, facts y operaciones que lo aceptan terminan en boundaries seguros. Cerrar GUI no mata el worker activo.

## Adquisición humana, ConflictResolver y legacy

Perception Workbench es tooling read-only paralelo al runtime. Sólo ground truth humano explícito puede registrar significado/destino; taps, predictions o frames posteriores no prueban causalidad. Evidencia raw queda ignorada y sólo manifests curados alimentan producción.

Un futuro `ConflictResolver` vivirá por encima de failures estructurados de flows/operaciones para tratar conexión, popup inesperado, app trabada, restart o policy de sesión. No absorberá matching, guards locales ni retries de `VerifiedTransition`, y no se implementará sin casos/outcomes acordados.

`AdsManager` continúa standalone. El tag `legacy-pre-hybrid` y `docs/legacy/` preservan la implementación previa; tecnologías útiles como OpenCV, scrcpy o ADB no son legacy por sí mismas. No se reparan consumers antiguos mediante shims ni se vuelve a acoplar captura, reconocimiento, decisión y coordenadas.
