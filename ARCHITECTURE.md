# Arquitectura — Kritika FarmBot 0.2

Este documento define contratos vigentes y dirección aceptada. El estado observable está en [`CONTEXT.md`](CONTEXT.md), la secuencia de trabajo en [`ROADMAP.md`](ROADMAP.md) y las alternativas históricas en [`docs/HISTORY.md`](docs/HISTORY.md).

## Arquitectura implementada

```text
Capture
  → Perception ───────────────┐
  → Runtime Facts ────────────┤
                              ▼
                       ContextResolver
                              ▼
 Flow / Support Operation / SessionRunner / Rotation
                              ▼
                  verified semantic operation
                              ▼
                       ActionExecutor
                              ▼
                         AdbClient
```

Los facts demand-driven pueden llegar directamente al consumidor cuando parten de un snapshot context-correct. Las operaciones verificadas coordinan observación y ejecución sin fusionar sus responsabilidades.

### Capture

`ScrcpyFrameSource` obtiene frames BGR con sequence y timestamp. Posee proceso, socket, decoder y cleanup. No reconoce pantallas ni contiene policy.

### Perception y facts

`PerceptionEngine` aplica detectores semánticos a un frame y emite observaciones, no decisiones. Los módulos específicos encapsulan templates, OCR y reglas de evidencia.

`RuntimeFactReader` calcula OCR tipado sólo cuando un consumidor lo solicita. `TemporalObserver` agrega evidencia multiframe para estados que no son seguros en una captura, como Auto Battle.

El board de Monster Wave conserva su detector de popup existente. `MonsterWaveBoardReader` se invoca sólo sobre `RESOLVED screen.monster_wave + popup.monster_wave_inventory_board` y lee cinco filas fijas mediante ROIs acotadas; identidad, `balance/límite mostrado` y orden deben coincidir en dos frames posteriores a una barrera del caller. `build_monster_wave_board_snapshot` es puro: exige el mismo contexto, último frame del fact igual al snapshot y edad temporal acotada; si el popup está presente sin consenso, el contenido queda `PRESENT_CONTENT_UNKNOWN`. `UNKNOWN`, `AMBIGUOUS`, evidencia contradictoria o previa a la barrera no producen un snapshot válido. Los pares mostrados no son cantidades requeridas ni recetas; `gold_key_capacity` es `NOT_OBSERVABLE`. No hay navegación, input ni policy de ruta en este contrato.

`plan_resource_route` es la frontera pura posterior al snapshot: `MonsterWaveBoardSnapshot + NonBoardResourceFacts → ResourceRoutePlan`. Los facts externos aportan explícitamente rewards entrantes, conversiones y precondiciones Craft que el board no observa. Una fila sólo prueba presión cuando existe reward exacto y `balance + incoming > displayed_limit`; unknown, stale, foreign o contradicción producen cero steps. El plan contiene capacidades simbólicas: Craft opcional seguido por una única sesión Trading que agrupa Keys y Materials. Keys precede Materials por el entry cerrado de Trading en Avatar & Keys; C6a/C6b conservan el orden interno y recovery Gold-full. Equipment Relief sigue siendo recovery reactivo del caller y Treasure interno a C6b: ninguno aparece como step proactivo. J consume ese plan una sola vez mediante `MonsterWaveResourceRouteRuntime`, sin llamar otra vez al planner desde el snapshot final.

`MonsterWaveStandaloneRunner` (K) sólo parte de un popup board ya abierto y confirmado en dos frames. Acquire/plan no envían input; prerequisites/full cierran el popup con `DeclineMonsterWaveInventory` y readquieren MW limpio antes de J. Un plan unresolved no cierra el popup ni ejecuta J. J SUCCESS con todos los steps supplied y MW limpio fresco es la postcondición; no se intenta reabrir el board tras J. Full sale de MW mediante `ExitMonsterWave` verificado hacia Battle Mode Select y llama `MonsterWaveActivity.run()` una vez. Planner, J y actividad se invocan como máximo una vez cada uno; no hay loop, Equipment Relief ni integración stage/session. El caller aporta `NonBoardResourceFacts` explícitos y construye los runtimes inyectados.

### Resolución y observación runtime

`ContextResolver` es puro y determinista: combina contexto base y overlays y devuelve `RESOLVED`, `UNKNOWN` o `AMBIGUOUS`. No captura, no acciona y no conserva policy de flows.

`RuntimeObserver` crea snapshots coherentes de frame, observaciones, estado, facts y geometría. Las esperas exigen secuencias frescas, timeout, estabilidad cuando corresponde y cancelación explícita.

`clean Lobby` significa `RESOLVED screen.lobby + overlays vacíos`. Discovery,
recovery y postcondiciones de sesión observan globalmente. Una transición
conocida a Lobby puede usar un observer resolver-complete: incluye todas las
dependencias de bases y overlays del catálogo, por lo que conserva blockers,
bases foreign y `AMBIGUOUS`, aunque omite readers que no alimentan resolución.
Source, acción, freshness, retry y recovery siguen perteneciendo al caller. Ver
[`docs/CLEAN_LOBBY_B2_DECISION.md`](docs/CLEAN_LOBBY_B2_DECISION.md).

### Intención y policy

- **Flows:** contienen intención de negocio, gates, outcomes y orden de operaciones.
- **Support operations:** resuelven una obstrucción concreta y vuelven al caller conocido; no son flows ni recovery general.
- **`BattleModeZone`:** comparte entrada/normalización del hub entre actividades sin absorber su gameplay.
- **`SessionRunner`:** compone flows habilitados, proyecta resultados y aplica policy de sesión.
- **Rotation:** cambia de personaje de forma transversal; no ejecuta flows.
- **Eligibility e Identity:** aportan contexto y skips, pero no seleccionan estrategia.

La lista productiva sigue siendo explícita y ordenada. La GUI configura esa lista; no contiene lógica de negocio.

`MonsterWaveActivity.run(yield_resource_board=True)` entrega el popup de recursos que aparece naturalmente después de `StartMonsterWaveSkip` como `FlowStatus.RESOURCE_BOARD_PENDING`, con `board_sequence` del postestado fresco. No emite Yes/No ni Back después de reconocerlo; el caller recibe el popup abierto y debe adquirir G desde esa barrera. El default `False` conserva la respuesta configurada Yes/No. `MonsterWaveFlow` sólo propaga el handoff; todavía no ejecuta K/J. Si un caller opt-in lo entrega a `SessionRunner` sin consumirlo, la sesión falla cerrada con `resource_board_pending`, sin cerrar la zona, ejecutar otro flow ni rotar.

El planner I exige `IncomingRewardFact` exacto para las cinco filas. El GT de producto indica que cada recurso cae probabilísticamente por sapphire, por lo que no existe una recompensa entrante fija para MAX SKIP. No hay `NonBoardResourceFacts` productivos ni configuración estática de cantidades: L debe permanecer deshabilitado hasta acordar una fuente/contrato de planificación que represente esta mecánica sin fingir exactitud. Conversiones, coste Craft y slots libres no resuelven esa primera ausencia.

### Operaciones verificadas

`VerifiedTransition` modela precondición, una acción y postcondición observable. Una falla no se convierte en éxito por demora ni por desaparición ambigua.

Todo retry es:

1. bounded;
2. autorizado por un estado fresco;
3. específico de la acción que se repite;
4. cancelable.

`UNKNOWN` y contradicciones fallan cerrados. Cuando no existe una señal robusta, la policy debe ser conservadora y quedar documentada.

Equipment Sell es una capacidad standalone bulk-only, no un flow ni un relief composer. Perception produce `EquipmentInventoryFact`, `EquipmentItemFact` y `EquipmentSellConfirmationFact`; el caller aporta `EquipmentSellAuthorization` explícita. La operación selecciona un candidato ya indicado, confirma detalle fresco dos veces, verifica identidad y grupo del popup, emite como máximo un `Sell (Bulk)` y sólo retorna éxito con Item Count fresco menor. Poor–Legendary agrupa por grado y separa Equipment de Enhance; Ethereal agrupa por tipo exacto no accesorio; Ethereal+ y candidatos accessory/unknown se deniegan. No hay scan, navegación, Karat expansion, presión de inventario, retry destructivo ni composición con Combine.

`EquipmentReliefComposer` compone esos owners sin absorber su policy ni el significado de negocio del caller. Conserva un request opaco por identidad y sólo clasifica, mediante un predicate del caller, si su resultado es Equipment Full. El orden cerrado es `caller → Equipment Full → Combine x1 → caller fresco x1 → Equipment Full → Sell x1 → caller fresco x1`; cualquier resultado caller no-full se devuelve intacto y un tercer Full falla cerrado. `RELIEVED` y `NO_RELIEF_AVAILABLE` de Combine habilitan el primer retry, pero nunca equivalen a éxito del caller; `FAILED`/`CANCELLED` cortan. Sell sólo existe en el ciclo si hay `EquipmentSellRequest` explícito con autorización+candidato y sólo habilita retry cuando su owner demuestra Item Count decreciente con un confirm. Las rutas concretas siguen siendo adapters caller-specific invocados por el compositor: Combine retorna mediante `EquipmentCombineReturnPlan`; Sell parte de Inventory abierto y publica un retorno causal fresco. Cada readquisición exige secuencia posterior a la barrera de ruta, de modo que snapshot, popup, slot, Item Count o readiness previos no sobreviven al relief.

Craft es una capacidad standalone, no un planner ni un caller adapter. `CraftRuntime.enter()` sólo parte de Equipment Inventory positivamente leído y exige `capacity - item_count >= 1` antes de cualquier navegación; después verifica `Quick Menu shifted → Craft` con facts posteriores. Para J, `enter_from_verified_quick_menu()` consume el handoff MW sólo cuando el plan ya probó esa precondición de capacidad. `CraftRuntime.execute()` acepta un `CraftRequest` Hero, confirma familia/tier, coste material y cantidad frescos, emite como máximo un confirm, nunca scrollea ni autoriza Karats, reconoce resultado estable y sólo retorna éxito tras cerrar por el lateral no interactivo adquirido y observar el decremento exacto del material. `request_back_to_origin()` emite el Back tipado una vez; J debe demostrar el MW inmediato fresco después. `open_quick_menu_or_handoff()` abre Quick Menu directamente desde Craft fresco, sin Lobby. Equipment Relief y todo retry causal siguen perteneciendo al caller.

`VerifiedTransitionResult.action_source_snapshot` publica el snapshot que autorizó el último input cuyo executor terminó normalmente, incluyendo el source actualizado tras retry o recovery de precondition. Sin input, o si el executor falla de forma incierta, no publica anchor. `recovery_after_action` distingue cleanup ocurrido después del input y prohíbe convertir su éxito posterior en nuevo handoff. Un callback local `on_recovery` se ejecuta cuando recovery devuelve un snapshot fresco, antes de evaluar un retry; permite invalidar provenance de una operación sin estado global.

Quick Menu separa visibilidad de autorización. Un tile sólo usa el handoff local `QuickMenuHandoff` creado con source del input `RESOLVED`, limpio y permitido para esa operación, menú posterior fresco y base no contradictorio. `UNKNOWN + menu.quick` puede observarse después de abrirlo: el input del tile se autoriza por ese lineage explícito y el overlay fresco, nunca por UNKNOWN aislado. `AMBIGUOUS`, base foreign, pérdida observada del menú o recovery invalidan el handoff y prohíben retry; una espera pasiva por el destino puede continuar. Layout proviene del source verificado y geometría del frame fresco. Discovery/recovery sin handoff permanece fail-closed; `ContextResolver` no conserva origen temporal.

Quick Menu conserva únicamente el origen inmediato: navegar desde un contexto por Quick Menu reemplaza cualquier provenance anterior de ese contexto. No existe tile Monster Wave. Por eso J usa MW como anchor físico, no como hub genérico: cada bloque top-level sale de MW y debe retornar a MW antes del siguiente. Craft retorna por Back antes de abrir Trading; dentro del recovery C6b MW, Trading cierra por X a MW, Treasure retorna por Back a MW y sólo entonces se reabre Trading. La cadena `MW→Craft→Quick Menu→Trading→X→Craft→Back` está prohibida porque terminaría en Lobby. Ningún segundo nivel de origen autoriza input.

`TradingMaterialsRuntime` compone los owners cerrados sin añadir policy: `ensure_general` verifica General/material rows frescos, C2 localiza sólo el row id del plan, C3 aporta un fact posterior y C4 ejecuta una cantidad `EXACT`. No diagnostica otras filas, no navega fuera de Trading y no recupera Equipment Full. `GoldCapacityRecoveryNavigation` permite que C6b conserve su decisión/drain/retry causal mientras el caller aporta tres handoffs físicos source-aware; la ruta standalone Lobby no cambia.

El resultado J distingue plan no ejecutable, fallo de capacidad, cancelación, retorno a MW fallido y postcondición final fallida. `SUCCESS` exige un `FreshMonsterWaveSnapshot` posterior al último X/Back. Ese snapshot se devuelve al caller; no dispara otro plan, SKIP, battle ni reward.

Lobby no es un hub obligatorio. Trading no expone Quick Menu mientras está abierto y siempre debe cerrarse por su X roja antes de otra ruta. En el camino Lobby→Trading de `TradingRuntime`, la X vuelve a Lobby; HIL C6b mostró que Trading abierto desde Quick Menu conserva Treasure debajo y su X vuelve a Treasure. Treasure expone Quick Menu y `QuickMenuTradingRuntime` posee Treasure→Quick Menu→Trading. Craft standalone también verifica Quick Menu directo desde Craft antes y después de una acción productiva; no normaliza a Lobby. Monster Wave conserva acceso físico para integración futura. El principio es usar Quick Menu directo cuando origen y destino están verificados, y sólo usar close/return propio cuando el contexto lo exige.

World Boss también separa visibilidad de autorización mediante dos handoffs locales, sin estado global ni base sintética. `_WorldBossSelectorHandoff` nace sólo cuando un input efectivo parte de Battle Mode Select resuelto y produce un Select Boss fresco compatible; así `UNKNOWN + overlay.world_boss_select_boss` permite seleccionar únicamente por ese lineage, nunca por discovery. `_WorldBossEntryHandoff` nace del `action_source_snapshot` efectivo de esa selección y de una rama fresca hacia World Boss limpio o Previous Rewards visible; sólo ese lineage permite Ack, que es single-attempt y exige luego `RESOLVED screen.world_boss` limpio. `AMBIGUOUS`, base foreign, overlay contradictorio o recovery invalidan el permiso; perder el selector durante loading impide retry, pero no borra retroactivamente el source de un input ya ejecutado cuya postcondición aparezca después. El overlay de Raid Complete puede interrumpir pasivamente Auto Battle aun con base no resuelta, pero no habilita `Continue`. El poll final se ancla después del último cursor de batalla/Auto Battle y de toda evidencia del timer: `UNKNOWN` y `AMBIGUOUS` esperan bounded, batalla limpia espera el overlay y cualquier otro `RESOLVED` es terminal. `Continue` admite un solo input y exige `RESOLVED screen.world_boss_battle + overlay.world_boss_raid_complete`.

### Ejecución física

`ActionExecutor` traduce intents validados a taps, swipes o texto usando geometría derivada de `frame.shape`. No reconoce pantallas ni decide qué jugar, comprar o vender.

`AdbClient` es el único límite activo de ADB. Ningún flow llama ADB directamente.

### Observabilidad y frontends

Structured Observability registra eventos tipados. Failure Evidence conserva contexto diagnóstico acotado. SessionReport resume outcomes de flows, personajes y sesión.

CLI y GUI construyen el mismo runtime. La UI permite selección, orden, ejecución y cancelación; no modifica contratos internos.

## Invariantes

```text
Perception != Policy
ContextResolver != Capture or Input
Flow != ActionExecutor
Rotation != Flow
GUI != Business Logic
ActionExecutor != Verification
AdbClient == sole ADB boundary
```

- Configuración se carga de forma explícita e import-safe.
- Paths locales, seriales y resoluciones no se versionan ni hardcodean.
- Lifecycle y cleanup pertenecen al dueño del recurso.
- Recovery devuelve a un estado conocido; la sesión decide si continúa.
- Ads permanece desacoplado de la percepción normal del juego.

## Filosofía de producto

La persona usuaria es el planner: decide objetivo, orden de flows y configuración. El bot ejecuta operaciones deterministas, pequeñas y verificables. Nuevas abstracciones sólo se incorporan cuando existe un consumidor y evidencia causal; nombres como Sequence, Loop o Condition son posibilidades de composición, no componentes actuales.

## Dirección aceptada, aún no completamente implementada

### Percepción acotada incremental

Los hot paths deberían evaluar sólo evidencia relevante para el estado y la operación actuales. Rotation R1 acota exclusivamente la verificación de `select_predecessor_character` con `ScopeSpec` y `scoped_transition_for`: el reader amarillo local sigue sobre el frame crudo. Rotation R2-A reutiliza ese subset de dos detectores mediante `scoped_observer_for` sólo en el wait post-swipe de Character Select; `stable_for=1.0`, sentinel posterior, frames, geometría y estrategia de scroll conservan sus contratos. B2 acota los retornos conocidos a Lobby de 95 a 77 detectores con vocabulario resolver-complete; no recorta bases u overlays sin evidencia física. Discovery, recovery y postcondiciones de sesión permanecen globales. La expansión será de un flow o hot path por vez, con benchmark y smoke antes de ampliar alcance.

Esta dirección conserva el principio demostrado por el experimento, pero no adopta sus APIs, planes léxicos ni acoplamientos con Inventory Relief.

### Navegación de listas largas

Para una lista ordenada y estable, la primitiva futura aceptable es:

```text
catálogo conocido + landmark visible + target conocido
  → estimar desplazamiento
  → gesto acotado
  → reobservar
  → corrección bounded o stop
```

No se acepta navegación ciega, conteo indefinido de swipes ni taps sobre filas parciales.

### Relief por presión de recursos

Equipment Sell y el compositor transversal ya existen separados del gameplay. El compositor aplica causalidad demostrada y bounds fijos, pero todavía no hay adapters productivos de caller: cada uno debe aportar su resultado Equipment Full, rutas verificadas, facts frescos y plan de venta explícito. No se heredan thresholds, scan, loops, rutas ni lifecycle del experimento.

### Expansión funcional

Nuevos flows deben reutilizar límites existentes, definir entrada/salida, outcomes y eligibility, y cerrar primero un slice simple. Tower y Arena quedan después de estabilizar percepción acotada e Inventory Relief mínima.

## Arquitectura no aceptada

No pertenecen al baseline ni a la dirección comprometida:

- el runtime experimental completo de Inventory Relief;
- un framework general de input lifecycle/readiness;
- retries basados en sleeps o en lentitud accidental de percepción;
- percepción global costosa como mecanismo para esperar que la UI sea interactiva;
- planner automático, navigation graph general o recovery anticipado sin caso demostrado.

Las lecciones y coordenadas de esa línea se preservan en [`docs/HISTORY.md`](docs/HISTORY.md).
