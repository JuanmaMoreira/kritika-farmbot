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

`bot/flow_registry.py` es la única lista productiva de flows. Cada `FlowDefinition` declara id, display name, scope, contrato y factory; `FlowRegistry` valida y conserva orden explícito. No hay discovery, reflection ni plugin system. El registry actual contiene `black_market`, `world_boss`, `send_stamina`, `summon_pet_daily`, `daily_quests`, `mailbox` y `guild_check_in`, en ese orden default.

## Capture y Perception

`ScrcpyFrameSource` publica `FrameSnapshot` BGR con sequence y timestamp monotónico. Posee server, forward, proceso, socket, decoder y receiver; cleanup es best-effort e idempotente. Capture no importa Perception, Resolver, flows ni actions.

`PerceptionEngine` ejecuta detectores explícitos y precargados sobre un frame y produce un `ObservationBatch` con la misma identidad temporal. El backend productivo es OpenCV local; assets, ROIs y calibraciones concretas pertenecen al código, tests y manifests, no a este contrato.

`Observation` es evidencia inmutable namespaced con confidence, source, value/región opcionales. `ObservationBatch` agrupa evidencia de un único frame y permite nombres repetidos; sus helpers buscan, no resuelven policy.

Hay tres usos separados:

- landmarks de base/overlay alimentan `ContextResolver`;
- facts intra-screen como GOLD/Purchased permanecen en el snapshot para el flow dueño;
- Runtime Facts demand-driven/temporales usan extractors tipados y evidencia propia.

Las observaciones intra-Socket de velo rojo y fase oscura de Enhance son operation-scoped: Perception sólo reporta evidencia. No seleccionan estrategia, no autorizan KARATS ni convierten una coincidencia aislada en permiso de venta.

Daily Quests y Character Mail usan semántica y actions productivas separadas. `screen.quests`/`mode.daily_quests` gatean tanto el `Claim` de filas como el indicador cyan independiente del reward de progreso; el resolver los expone como statuses distintos. `screen.mailbox`/`mode.mailbox_character_mail` gatean `Claim` y `Delete` para no confundir Account Mail. El spinner cyan se expone como `activity.mailbox_claim_processing`, una observación operation-scoped que puede faltar durante fases oscuras de rotación. Perception no interpreta bubbles, no declara Inbox vacío y no decide qué reward reclamar.

La señal Daily verde compartida usa un único asset visual y cuatro detectores posicionales: Friends All, Guild Attendance, la tarjeta World Boss y el tab Pet Summon. El resolver la combina con landmarks estructurales para derivar statuses independientes; encontrar otro badge igual en la pantalla no habilita la actividad equivocada. Friends añade `screen.friends` mediante título + All. Pets usa un shell superior y el tab activo, evitando el título centrado que puede ocultar el chat. Perception sólo expone presencia/ausencia observable: no decide si enviar stamina, hacer Attendance, ejecutar World Boss o invocar un pet, y el bubble transitorio no es señal.

Pet Summon separa observación de policy. `PetEpicAvailabilityDetector` clasifica el render brillante/apagado de la tarjeta Epic y emite disponibilidad mutuamente excluyente sin leer contador ni asumir costo: también cubre eventos temporales de 7 runas. Los detectores Premium sólo distinguen ticket/GOLD y sus menús porque cambian la interacción, pero no eligen recurso. El resultado de summon exige banner dorado + pergamino; los popups de fragmentos, GOLD insuficiente y Pet Full permanecen outcomes observables.

Pet Combine conserva semántica adquirida para rutinas específicas futuras de Pets. `PetLowTierCandidateDetector` recorre la grilla visible fija, emite `candidate.pet_low_tier` con región y valor `normal`/`rare` únicamente ante frames verdes/azules inequívocos, y se calla en modo de selección o bajo modal; identidad, Epic+ y ambigüedad no son candidatos. `popup.pet_mass_evolve_confirmation` es un estado único cuyo landmark lleva el tier explícito. `popup.pet_epic_runes_full` se reutiliza tanto desde Combine All como desde Mass Evolve. Combine All y Mass Evolve comparten `screen.pet_combine_result` y la actividad existente `activity.combine_animation_tappable`; el base dedicado evita autorizar taps desde `UNKNOWN`. El relief incidental actual sólo consume la rama Combine All; Perception no decide candidato, páginas, estrategia ni outcome.

Guild usa `landmark.guild_message_tab` para resolver `screen.guild` desde una zona estable fuera del bubble superior. `GuildAttendanceDetector` mide una franja interior del fill del botón y emite exactamente uno de `indicator.guild_attendance_active/completed`; el resolver deriva los statuses correspondientes. El detector se calla bajo `menu.quick`, porque el overlay cubre parte del control y navegación no debe heredar un status de negocio. El bubble no se modela.

Equipment Inventory Full usa `popup.equipment_inventory_full` como overlay global, separado del caller. `screen.combine` deriva de un landmark compuesto que acepta el tab Fuse persistente o la actividad inequívoca de animación, evitando un estado `UNKNOWN` en la fase que consumirá `TapThroughAnimation`. Los modos activos y tres observaciones posicionales de `N` se combinan en el resolver para producir disponibilidad Transmute, Ethereal y Fuse. Los títulos de panel/modal aportan estados intermedios con consumidores futuros concretos. Las tres operaciones comparten `activity.combine_animation_tappable`; Perception no decide el orden ni si debe combinar.

Los landmarks base evitan regiones con oclusión dinámica conocida. En Socket, el tab izquierdo persistente sustituye al encabezado superior derecho; en Battle Mode, el título de la tarjeta World Boss sustituye al encabezado superior. Popups, overlays y el panel Black Market se renderizan por encima del chat, por lo que su layering también forma parte de la auditoría; una ROI base situada en una zona dinámica requiere positivos reales con el overlay antes de considerarse robusta.

Un fact no se convierte en contexto para facilitar navegación.

La evaluación offline productiva conserva los manifests curados como fuente de verdad y cachea sólo resultados derivados por par detector/frame. Un hit exige identidad de contenido del frame, configuración y código del detector, contenido de assets, helpers CV compartidos, runtime OpenCV/NumPy y versión/lógica del evaluator; labels y `ContextResolver` se recalculan siempre. La cache bajo `artifacts/` es regenerable y una entrada corrupta o no fingerprintable se invalida conservadoramente; `--full-rebuild` fuerza auditoría global desde cero.

## ContextResolver y RuntimeObserver

`ContextResolver` es puro, determinista y stateless. Con reglas explícitas, cero/uno/varios candidatos base producen `UNKNOWN`/`RESOLVED`/`AMBIGUOUS`; no hay first-match, voting, hysteresis ni desempate por confidence. Overlays se resuelven independientemente y pueden coexistir con base desconocida.

`RuntimeObserver` une frame, observations, estado, facts intra-screen y geometría en un `RuntimeSnapshot` coherente. `observe()` y `wait_until()` son el boundary de consumidores; las esperas exigen sequences frescas, tienen timeout, pueden exigir estabilidad y aceptan cancelación/abort conditions. La estabilidad pertenece al consumidor, no al resolver.

Los consumidores de Claim All reutilizan esa estabilidad: Daily Quests confirma primero la desaparición estable de `status.daily_quests_claimable` bajo su base/modo y reevalúa el snapshot resultante. Si contiene `status.daily_quests_progress_reward_claimable`, una acción separada exige después la desaparición estable de ese status. Mailbox termina sólo tras ausencia estable de `activity.mailbox_claim_processing` y retorno estable del modo Character Mail. En Mailbox no basta un único frame sin spinner y la persistencia de `status.mailbox_claimable` después de la quiescencia representa leftovers, no procesamiento activo.

La completion de Attendance exige `screen.guild + status.guild_attendance_completed` estable durante `0.75 s` sobre frames frescos, con budget de `10 s`. El status independiente `status.guild_attendance_daily_active` es compatible con la navegación y los estados active/completed, pero no autoriza el check-in por sí solo. No usa `ControlledWait`, bubble ni timing fijo como postcondición.

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

Distingue éxito inicial, durante grace, tras retry, recuperación de obstrucción, guard rechazado, agotamiento, estado inesperado, timeout y fallo. Un match tardío aislado —post-grace, retry guard o recovery— debe satisfacer también `stable_for` mediante una espera pasiva bounded antes de declarar éxito; si pierde estabilidad no repite la acción. El guard post-grace debe superar la secuencia más reciente de las esperas. Acepta un hook genérico opcional de obstruction recovery (protocolo `attempt`, sin vocabulario de overlays): ante una observación fresca que no satisface la condición esperada —en precondición o tras la grace—, el hook puede hacer taps de limpieza con la capa normal de acciones, reobservar bounded y devolver un snapshot fresco para reevaluar la condición original, sin repetir la acción productiva. Tras cada tap de limpieza hay una ventana pasiva bounded de settle (5 s con margen sobre el fade >2 s medido live, sin input) con reprobe on-demand: `ABSENT` termina temprano, `INCONCLUSIVE` o fuente trabada no autorizan otro tap y sólo un `CONFIRMED` fresco al cierre de la ventana permite el segundo y último tap. `UNKNOWN` jamás satisface por defecto un retry guard y no autoriza input; sólo una detección positiva específica del hook autoriza sus taps. Una captura repetida o fallida durante settle invalida el permiso de segundo dismiss. Fallos del hook después de intentar input no se convierten en ausencia de obstrucción ni habilitan retry con evidencia anterior; el caller conserva el fallo técnico. Un retry productivo posterior a recovery exige otra observación fresca. La cancelación corta el recovery en sus boundaries y se propaga a los consumidores.

`ObservedScroll` es una operación continua transversal. Conserva frame settled A, observa movimiento transitorio T durante `Swipe` y exige frame settled B posterior; clasifica progreso, edge candidate o gesto inefectivo con intentos bounded. Similitud A/B sin movimiento T no prueba borde. El perfil Character Select aporta ROI/thresholds/gestos. `StandardRotation` ya no la consume como autoridad terminal: sigue disponible como primitive general para futuros menús scrolleables (p. ej. Trading Center).

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

`WorldBossFlow` es `PER_CHARACTER`, declara Lobby → Lobby/World Boss y posee policy de sapphires, navegación, Previous Rewards, guards de inventario, Auto Battle, timer, Raid Complete y Continue. Battle Mode Select admite cero overlays o únicamente el status auxiliar `status.world_boss_daily_active`; esa señal no decide elegibilidad dentro del flow. Raid Complete depende del overlay, no de que una base concreta resuelva simultáneamente. El check de Auto Battle es single-pass por batalla: un tap como máximo y sólo ante OFF confirmado con la misma ventana de 9-10 frames y mediana bajo el umbral OFF. La adquisición es un harvest crudo desde la fuente (sin semántica por frame) con secuencias estrictamente crecientes; la misma regla temporal, thresholds y gate de visibilidad clasifican la ventana. Un OFF temporal exige además el gate de visibilidad del pill verde (las fases cinemáticas ocultan los controles y su quietud no es evidencia OFF): sin control visible la lectura se abstiene como UNKNOWN y nunca autoriza tap. Una observación semántica fresca confirma el contexto tras el harvest (Raid Complete, base incompatible o no confirmada) y el guard pre-tap debe ser más nuevo que el harvest y volver a confirmar que el control está visible; la re-verificación post-tap es otro harvest rápido y best-effort. ON confirma sin input y cualquier caso inconcluso (harvest timeout, UNKNOWN, contexto no confirmado, verificación post-tap sin confirmar) continúa al timer sin input a ciegas ni fallo. El budget cubre con margen las adquisiciones sanas observadas (`1.188-1.875 s` en 17 ventanas curadas); abandonarlo sólo resigna un tap, nunca autoriza uno. Sólo un `CONTEXT_MISMATCH` resuelto fuera de la batalla sigue abortando. Si Raid Complete interrumpe esa ventana, el flow lo reacquire pasivamente y salta timer/espera larga sólo al verificar el overlay. El timer sólo dimensiona la espera: una lectura no concluyente (ilegible, incierta, timeout o fallo OCR) usa el máximo validado de `90 s` en vez de abortar; sólo `CONTEXT_MISMATCH` del timer conserva el fallo. El flow no implementa OCR, matching, ADB ni recovery de conexión; consume esos boundaries.

`DailyQuestsFlow` y `MailboxFlow` son `PER_CHARACTER`, declaran Lobby → Lobby y contienen únicamente su policy de negocio. `OpenQuests` valida primero el shell que restaura el último tab del personaje; `SelectDailyQuests` se ejecuta sólo cuando falta `mode.daily_quests` en Quests resuelto y limpio. El loop reobserva cada ~1 s y permite repetir únicamente desde una secuencia estrictamente nueva del mismo estado, dentro de `navigation_timeout` (6 s por defecto). UNKNOWN/AMBIGUOUS y frames repetidos no autorizan input; otro contexto resuelto aborta. Daily activo termina la selección. Claim All es single-attempt en ambos. Daily confirma la desaparición estable de los claims de fila, reevalúa el reward de progreso en ese estado fresco y lo reclama una vez si está disponible; la acción independiente también requiere desaparición estable y nunca se reintenta. Ausencia inicial de ambos statuses es no-op. Mailbox separa onset bounded, actividad observada y quiescencia estable; si el onset no llega a observarse, usa el mismo budget de procesamiento de `30 s`, exige Character Mail sin actividad estable y distingue completion por desaparición de claims de `no_effect` con claims persistentes. El budget contempla la secuencia variable de bubbles por mail y termina anticipadamente al confirmar la postcondición. Delete Read ocurre después de esa rama y únicamente con read mail observable; una oclusión transitoria del tab bajo `screen.mailbox` prolonga pasivamente la espera, mientras el éxito sigue exigiendo retorno estable a Character Mail sin Read. Leftovers son `FlowEvent` no fatal.

`SendStaminaFlow` es `PER_CHARACTER`, declara Lobby → Lobby y verifica Friends como estado intermedio. La ausencia inicial de su status Daily es no-op y nunca autoriza All. La presencia autoriza un único `SendStaminaToAllFriends`; completion requiere ausencia fresca estable durante `0.75 s` con timeout de `3 s`. Si vence ese budget, Friends + Daily debe confirmarse estable durante `0.75 s` sobre frames frescos para producir el resultado no fatal `all_no_effect + daily_pending`; sólo esa rama tolera Daily mientras cierra Friends. El flow verifica Lobby en todas las ramas exitosas. No usa bubble, oscurecimiento de botones individuales, retry ni `ControlledWait`.

`SummonPetDailyFlow` es `PER_CHARACTER`, usa el id `summon_pet_daily` y declara Manage → Manage/Summon. La entrada a Pets pertenece a la normalización de precondiciones: el estado natural verificado es `screen.pets_manage`. Ausencia del badge es no-op y conserva Manage; presencia entra a Summon, autoriza Epic cuando su status está disponible y Premium sólo cuando Epic está unavailable, y termina estable en Summon. El flow siempre solicita `1 (Open)` y no decide ticket contra GOLD. La decisión Daily se toma en Manage y no se exige que el badge persista en Summon. El par selector → settle de 0.25 s → `1 (Open)` directo es diseño HIL intencional: no se observa el dropdown entre taps. Después se esperan outcomes reales; un selector todavía visible sólo consume espera, sin más taps. Resultado estable + cierre + Summon limpio estable es completion. Las navegaciones y cierres verifican predicados completos, incluidos overlays compatibles; una base coincidente bajo popup no basta. Insufficient GOLD es un business event con Daily pendiente. Pet Full delega una vez a `PetSummonSpaceRelief`; relief positivo habilita un solo retry, mientras unavailable o un segundo Pet Full terminan en resolución manual no fatal. Toda rama que pasó por Combine vuelve a Summon antes de completar. Failure y cancelación de la operación se propagan.

`GuildCheckInFlow` es `PER_CHARACTER`, declara Guild → Guild y no contiene navegación. Completed inicial es no-op; Active autoriza un único tap y una espera fresca bounded por Completed estable. No existe retry del tap. Timeout, estados contradictorios/incompatibles y completion no verificable producen fallo conservador; cancelación se propaga.

Los statuses `status.guild_attendance_daily_active` y `status.world_boss_daily_active` aún no tienen consumidores funcionales. En particular, `WorldBossFlow` sigue siendo general-purpose: tolera su Daily como overlay de Battle Mode Select, pero no lo exige; cualquier elegibilidad futura pertenece fuera del flow. `GuildCheckInFlow` permanece sin el guard Daily hasta adquirir el negativo discriminante pendiente.

`PetSummonSpaceRelief` es estrictamente incidental y consume sólo la rama Combine All de la semántica Pet Combine. Exige Combine limpio, ejecuta como máximo un `Combine All`, confirma su popup y sólo declara `RELIEVED` tras observar el resultado tappable y un retorno estable a Combine mediante `TapThroughAnimation`. No material, capacidad de runas Epic llena u otro cierre seguro sin progreso terminan en `NO_RELIEF_AVAILABLE`; estados contradictorios o técnicamente inválidos producen `FAILED`, y la cancelación produce `CANCELLED`. No busca candidatos, no ejecuta Mass Evolve, no navega a Summon, no abre pets Epic y no repite Combine All. La semántica y assets de esas rutas permanecen disponibles para futuras rutinas específicas de Pets.

Las support operations siguen `check → operación bounded → recheck → continue/skip/fail`; no son flows, no entran en GUI/`FlowRegistry` y no permiten llamadas recursivas arbitrarias entre flows. El caller conserva la policy de cuándo invocarlas y entrega un return plan con acción y estado exacto esperado; la operación sólo reporta éxito después de verificar ese retorno.

`SocketInventoryRelief` requiere `screen.socket` limpio, intenta Enhance All sólo con GOLD y, ante No Material, puede buscar de forma bounded un ópalo incompatible visible. GOLD nunca se reintenta: si el costo de percepción pierde todas las fases tappable y la espera termina ya en Socket limpio, exige una segunda confirmación fresca de ese terminal antes de declarar efecto con cero taps de animación. Un terminal incompatible o inestable sigue fallando. Sell in Bulk se autoriza únicamente con velo rojo y un fact de nivel confirmado en `0`; lectura no confirmada o nivel distinto cancela la venta. Sus outcomes explícitos son `RELIEVED`, `NO_RELIEF_AVAILABLE`, `FAILED` y `CANCELLED`. `WorldBossFlow` posee tanto el `Yes` inicial como el permiso local de un único intento positivo por ejecución; una segunda aparición usa `No`. El único return plan compuesto productivamente es `ExitSocket → screen.world_boss`.

`EquipmentCombineRelief` es otra support operation, no una extensión de Socket ni un flow. Recibe un return plan exacto del caller y recorre siempre Transmute → Ethereal condicional → Fuse, acumulando efectos sin short-circuit. Cada paso interpreta su status únicamente bajo el tab activo, usa transiciones verificadas hacia modal/panel, reutiliza `TapThroughAnimation` con la actividad común y exige desaparición fresca del status. Ethereal también admite que una combinación corta regrese directamente a Random Part antes de observar una fase tappable, pero sólo declara efecto después de volver a Transmute y comprobar que su guard desapareció; cerrar el popup sin efecto sigue fallando. Un guard presente sin animación/postcondición o el defensivo Ethereal de material insuficiente produce `FAILED`; no se degrada a no-op. Sus outcomes son `RELIEVED`, `NO_RELIEF_AVAILABLE`, `FAILED` y `CANCELLED`.

`WorldBossFlow` posee la entrada `Combine`, el único permiso positivo de Equipment Full por `run()` y el return plan productivo `ExitCombine → screen.world_boss`. El permiso se consume sólo después de observar Combine. Una segunda aparición usa el cierre negativo, emite el business event y termina el flow de forma no fatal. La operación no está registrada en `FlowRegistry` ni expuesta en GUI.

`popup.meteor_inventory_full` es un overlay global de capacidad de Meteoritos, separado del caller como los otros guards de Start. `WorldBossFlow` no posee permiso positivo para este popup por policy provisional (sin venta/combinación/expansión/descarte ni support operation): ante `screen.world_boss + popup.meteor_inventory_full` ejecuta una única vez `RejectMeteorInventoryFull` (geometría `No` verificada compartida con Socket), exige `screen.world_boss` limpio y completa el personaje con el business event no fatal `world_boss.meteor_full`, sin reintentar Start. `UNKNOWN`/`AMBIGUOUS` nunca autorizan el tap y todo retry queda bounded y state-guarded por `VerifiedTransition`.

Después de Bulk, un frame Socket limpio puede preceder al landmark estable de Equipment Home. Esa fase sólo prolonga pasivamente la espera bounded: no satisface la postcondición, no autoriza retry destructivo y el éxito sigue exigiendo popup ausente, Equipment Home estable y desaparición del candidato previo.

## Rotation y Quick Menu

`RotationStrategy.advance()` es un contrato transversal. `StandardRotation` requiere la capability `quick_menu_accessible` y deja Lobby como única postcondición exitosa. Abre Quick Menu, Character Select y localiza la tarjeta `Create Character (+)` como sentinel explícito con `CreateCharacterSentinelDetector` (template pequeño de la cruz, threshold calibrado 0.78 sobre corpus curado): visible → deriva el predecessor desde `bot/character_select_layout.py` (grilla fija 3xN row-major; col 2/3 → izquierda misma fila, col 1 → col 3 fila anterior) y lo selecciona con `SelectCharacterCard`; ausente bajo Character Select limpio → búsqueda coarse-to-fine (2 swipes fuertes del perfil existente, luego swipes cortos controlados `fine_swipe`) con reobservación bounded (máximo 6 swipes totales, `sentinel_not_found_after_max_swipes`). `UNKNOWN`/`AMBIGUOUS` nunca autorizan input; un swipe inefectivo no es evidencia de final. La selección se verifica con `CharacterSelectionDetector` sobre la ROI de la tarjeta target, luego confirma y exige Lobby fresco. No conoce flows, nombres de personaje ni ADB.

`quick_menu_accessible` es una capability de policy, no una pantalla ni un nodo de navegación. Su allow-list productivo contiene Lobby, World Boss, Guild, Pet Manage y Pet Summon. `menu.quick` sigue siendo un overlay observable; `bot/quick_menu.py` elige el layout del intent interno según el contexto de origen. Todo origen no-Lobby usa el layout desplazado adquirido. Guild acepta exactamente un status Attendance al abrir el menú; Manage y Summon aceptan únicamente sus statuses estables compatibles.

La normalización a Guild tiene dos transiciones explícitas: desde Lobby usa el acceso directo `OpenGuild`; desde otros contextos permitidos —incluidos Manage y Summon— usa `Quick Menu → Guild` con el layout adquirido. Ambas exigen `screen.guild` con un estado Attendance coherente como postcondición. La evidencia live también confirma `Lobby → menu.quick → screen.guild`, que `screen.guild` abre `menu.quick` con el layout desplazado y que ambos estados Pet de salida acceden físicamente a Quick Menu.

`MinimalPreconditionEnsurer` conserva callbacks separados para normalizar a Lobby, Pet Manage o Guild. Manage se obtiene mediante `OpenPets` desde Lobby; si el origen es otro contexto Quick Menu-capable, la composición normaliza primero a Lobby. Manage/Summon vuelven a Lobby mediante el `ClosePets` directo ya verificado; otros orígenes usan Quick Menu. Para Guild, un origen Lobby elige siempre la transición directa y los demás orígenes con `quick_menu_accessible` usan Quick Menu sin retorno preventivo a Lobby. Un requisito ya satisfecho no invoca navegación y un fallo directo no encadena otra estrategia. No existe navigation graph ni lógica de destino dentro de los flows. `SessionRunner` continúa sin actions ni business logic.

## SessionRunner

`SessionPlan` expresa `character_count`, flows `PER_CHARACTER` ordenados y una `RotationStrategy`. Para cada personaje, `SessionRunner`:

1. asegura sólo el requisito del siguiente componente;
2. ejecuta cada flow en orden;
3. verifica una postcondición permitida y registra sus business events;
4. ejecuta y verifica exactamente un advance;
5. conserva resultado/progreso parcial.

Si un requisito ya se cumple, no navega. `MinimalPreconditionEnsurer` sólo normaliza cuando existe una operación explícita/verificada; no contiene un grafo general. El advance final cierra el ciclo y no reprocesa el personaje inicial. Fallos técnicos, postcondiciones contradictorias o Rotation fallida abortan conservadoramente. Cancelación se propaga como `CANCELLED`, no como fallo.

SessionReport v1 se construye fuera del runtime mediante `build_session_report(SessionResult)`, seguido opcionalmente de `render_session_report`. SessionRunner conserva aditivamente en su resultado el total esperado, orden de IDs, duración monotónica de la sesión y posición del flow terminal (para repeticiones). El report proyecta resultados/business events existentes y flags de dominio, conserva FailureCause/evidence_ref y separa completion técnica de incompletitud de negocio. No agrega eventos, persistencia, IO, captura, input ni policy. Resultados legacy incompletos exponen datos faltantes sin fabricar éxito o fallo. Contratos, conteos y límites en [`docs/SESSION_REPORT_V1.md`](docs/SESSION_REPORT_V1.md).

## Semantic Actions, ActionExecutor y ADB

Los intents tipados modelan acciones del dominio; `Swipe` es una primitive física sin policy. `ActionExecutor` valida coordenadas normalizadas, proyecta pixels desde la geometría del frame y delega taps/swipes a `AdbClient`. No observa postcondiciones, espera, hace retry ni decide gameplay.

`AdbClient` recibe executable, serial y timeout explícitos; expone state, shell, input, push, forwards y procesos persistentes. Traduce errores y no conoce frames ni semántica. Tests normales inyectan fakes y no requieren dispositivo.

## Frontends, logging y cancelación

CLI (`tools.run_flow`, `tools.run_session`) y GUI (`tools.gui`) seleccionan definitions del mismo `FlowRegistry` y llaman `ProductiveRuntime`. No duplican flows ni policy.

La GUI contiene modelos de selección/progreso, un timer monotónico de presentación para `Run Session` y un `GuiRuntimeController` con un único worker no-daemon. El worker ejecuta runtime y encola eventos/resultados; Tk sólo drena/renderiza y actualiza el timer en el main thread. `Run Selected Flows`, `Run Session`, orden, character count, debug y stop son control de ejecución, no business logic.

`ProductiveRuntime.run_flows_once` compone `run_flow` en el orden recibido sobre el personaje actual, sin construir Rotation ni SessionPlan. `FlowsOnceResult` inmutable conserva status, resultados parciales, causa y conteos derivados. Se detiene ante un retorno no COMPLETED, excepción o cancelación entre componentes; no agrega navegación, retries ni publicación duplicada. El controller sólo adapta ese agregado; el modo standalone anterior sigue disponible para consumidores legacy. No se fabrica un SessionResult con advances ficticios.

`GuiExecutionResult.report` expone SessionReport opcional después del cleanup de una sesión con resultado; campos/status legacy permanecen. `_finish` presenta `render_session_report` en una pestaña dedicada seleccionada automáticamente, sin clasificar outcomes ni recomponer etiquetas. Operaciones standalone/seleccionada y errores exteriores sin SessionResult conservan `report=None`. `bot/gui_evidence.py` proyecta las referencias técnicas del report y resuelve/abre carpetas locales sólo bajo acción humana, comprobando existencia y aislando errores. No consulta disponibilidad desde worker, builder, renderer o polling. JSONL continúa como fuente machine canónica, sin persistencia adicional. CLI de sesión usa el renderer humano y conserva exit codes; `runtime_cli.session_summary` sigue disponible con su salida legacy. Mapa detallado en [`docs/GUI_FUNCTIONAL_MINIMUM.md`](docs/GUI_FUNCTIONAL_MINIMUM.md).

`RuntimeEventStream → RuntimeEvent → JsonLineEventConsumer → JSONL` es la única fuente machine persistente. Structured Observability v1 añade schema_version, event_sequence y contexto run/session/character/flow/operation mediante scopes ContextVar; no se pasan IDs por las firmas de gameplay. Los nombres de lifecycle que consume GUI permanecen. Los nuevos paths por defecto usan `.jsonl`; paths `.log` explícitos siguen siendo JSONL y `JsonLineEventLog` legacy delega al mismo pipeline. Fallos de consumers y escrituras se aíslan; debug cambia visibilidad, no policy.

Los runners publican una vez los business outcomes de `FlowResult.events`; `FlowEvent.fields` conserva metadata de dominio y `event_role` distingue business, lifecycle y diagnóstico. `transition.completed` pertenece a VerifiedTransition; se elimina el resumen duplicado `world_boss.transition`. FailureCause se añade como `failure` keyword-only a resultados de flow/sesión/Rotation/transición/ControlledWait, conservando strings existentes. Su `evidence_ref` nullable es completado por Failure Evidence únicamente cuando persiste un bundle terminal.

`FailureEvidence` pertenece a la composition root: recibe snapshots ya resueltos mediante un callback aislado de `RuntimeObserver`, proyecta metadata explícita y posee un ring de 3 imágenes reducidas independientes. El stream enriquece exclusivamente `flow.failed`, `rotation.failed`, `session.failed` y `runtime.failed` antes del fan-out; los runners recuperan el evento retornado aditivamente por `record` y propagan la referencia mediante reemplazo de la causa inmutable. Cancelaciones y operaciones internas manejadas no generan bundles. El writer síncrono es best-effort y no reporta sus propios errores como failures. Storage local gestionado: 20 bundles/128 MiB/7 días; cleanup seguro al abrir/escribir y liberación del ring al cerrar. Formato, cuotas, compatibilidad y límites en [`docs/FAILURE_EVIDENCE_V1.md`](docs/FAILURE_EVIDENCE_V1.md).

VerifiedTransition mide elapsed e identifica cada ejecución; RuntimeObserver emite un terminal por wait con elapsed, poll_count, fresh_count y secuencias, sin cambiar el retorno RuntimeSnapshot ni la policy de frescura. `perception.analyze_summary` acumula count/elapsed/max/errores en lotes de hasta 64 llamadas, vaciados por contexto, al terminar waits y al cerrar runtime. Los clocks de métricas son inyectables y separados de deadlines; esos agregados no emiten eventos por frame ni guardan imágenes. El ring diagnóstico pertenece exclusivamente a FailureEvidence. Contratos de métricas en [`docs/STRUCTURED_OBSERVABILITY_V1.md`](docs/STRUCTURED_OBSERVABILITY_V1.md).

`CancellationToken` es thread-safe. CLI signals y `Stop Safely` solicitan el mismo token; runner, waits, facts y operaciones que lo aceptan terminan en boundaries seguros. Cerrar GUI no mata el worker activo.

## Adquisición humana, ConflictResolver y legacy

Perception Workbench es tooling read-only paralelo al runtime. Sólo ground truth humano explícito puede registrar significado/destino; taps, predictions o frames posteriores no prueban causalidad. Evidencia raw queda ignorada y sólo manifests curados alimentan producción.

Un futuro `ConflictResolver` vivirá por encima de failures estructurados de flows/operaciones para tratar conexión, popup inesperado, app trabada, restart o policy de sesión. No absorberá matching, guards locales ni retries de `VerifiedTransition`, y no se implementará sin casos/outcomes acordados.

`AdsManager` continúa standalone. El tag `legacy-pre-hybrid` y `docs/legacy/` preservan la implementación previa; tecnologías útiles como OpenCV, scrcpy o ADB no son legacy por sí mismas. No se reparan consumers antiguos mediante shims ni se vuelve a acoplar captura, reconocimiento, decisión y coordenadas.
