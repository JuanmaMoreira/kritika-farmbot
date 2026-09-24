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

El board de Monster Wave conserva su detector de popup existente. `MonsterWaveBoardReader` se invoca sólo sobre `RESOLVED screen.monster_wave + popup.monster_wave_inventory_board` y lee cinco filas fijas mediante ROIs acotadas. R1 mide primero rojo únicamente dentro del par numérico: un positivo confiable puede emitir `hard_pressure` sin balance exacto cuando la ruta no requiere aritmética; ausencia o incertidumbre conservan OCR. Weapon mantiene OCR exacto si Hero no prueba ya Craft. Identidad, facts de fila y orden deben coincidir en dos frames posteriores a una barrera del caller. `build_monster_wave_board_snapshot` es puro: exige el mismo contexto, último frame del fact igual al snapshot y edad temporal acotada; si el popup está presente sin consenso, el contenido queda `PRESENT_CONTENT_UNKNOWN`. `UNKNOWN`, `AMBIGUOUS`, evidencia contradictoria o previa a la barrera no producen un snapshot válido. Los pares mostrados no son cantidades requeridas ni recetas; `gold_key_capacity` es `NOT_OBSERVABLE`. No hay detector global nuevo, navegación, input ni policy de ruta en este contrato.

`plan_resource_route` es la frontera pura posterior al snapshot: `MonsterWaveBoardSnapshot + NonBoardResourceFacts → ResourceRoutePlan`. Balances actuales y umbrales inclusivos (Bronze 400, Silver 450, Weapon 800, Hero 800) deciden viajes; `IncomingRewardFact` permanece sólo por compatibilidad/debug y no participa. `CraftCapacityFact` permanece en el schema por compatibilidad, pero receta y slots son facts de ejecución y no precondiciones del plan. El planner usa sólo aritmética determinista de la operación propia 40 Weapon→10 Hero para decidir si Craft debe rodear Trading; no calcula batches ni predice drops MW. Los steps son capacidades simbólicas: Craft opcional y una sesión Trading con Keys primero y Materials sólo si Weapon cruzó su umbral. El presupuesto y los facts frescos de cada owner determinan el drenaje hasta Hero <49, Weapon <40 o `NO_MORE_PROMOTIONS`. Equipment Relief no aparece y Treasure es recovery causal interno a C6b. J consume el plan una vez sin replan.

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

I2 separa **entry policy** de **drain policy**: los umbrales deciden si se paga el viaje; dentro de una capacidad se consume todo el trabajo disponible y seguro, aunque el balance caiga bajo el umbral. El GT de drops probabilísticos por sapphire no requiere reward entrante exacto. Gold capacity sigue no observable: si ningún umbral paga Trading, Gold-full puede quedar sin descubrir y se acepta porque no bloquea MW por sí solo. Sólo `Silver→Gold OUTPUT_FULL` inicia Treasure. El display rojo al llegar/superar el límite UI queda para una futura optimización perceptiva separada; I2/J2 usa números existentes. L continúa sin wiring productivo.

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

Craft es una capacidad standalone, no un planner ni un caller adapter. `CraftRuntime.enter()` conserva la entrada desde Equipment Inventory con `capacity - item_count >= 1`. Para la entrada MW, J verifica Craft y llama una vez a `probe_equipment_capacity()` antes del primer craft action: Craft limpio→Quick Menu→Inventory, Item Count por consenso posterior al menú→Back→Craft por fact fresco posterior al Item Count. Sin retorno Craft probado no continúa; cero slots produce `EQUIPMENT_CAPACITY_BLOCKED` y no hay relief. `execute()` lee receta/coste frescos, mantiene un confirm máximo por batch Hero, guards de cantidad, cero Karats/scroll y decremento exacto. `drain_hero_material()` repite `MAX_AVAILABLE` con contexto fresco y presupuesto hasta Hero <49; durante esa visita Craft no revalida slots consumidos por los crafts, conforme al GT de producto. `request_back_to_origin()` exige que J pruebe MW fresco; Quick Menu desde Craft permite abrir Trading modal sin Lobby.

`VerifiedTransitionResult.action_source_snapshot` publica el snapshot que autorizó el último input cuyo executor terminó normalmente, incluyendo el source actualizado tras retry o recovery de precondition. Sin input, o si el executor falla de forma incierta, no publica anchor. `recovery_after_action` distingue cleanup ocurrido después del input y prohíbe convertir su éxito posterior en nuevo handoff. Un callback local `on_recovery` se ejecuta cuando recovery devuelve un snapshot fresco, antes de evaluar un retry; permite invalidar provenance de una operación sin estado global.

Quick Menu separa visibilidad de autorización. Un tile sólo usa el handoff local `QuickMenuHandoff` creado con source del input `RESOLVED`, limpio y permitido para esa operación, menú posterior fresco y base no contradictorio. `UNKNOWN + menu.quick` puede observarse después de abrirlo: el input del tile se autoriza por ese lineage explícito y el overlay fresco, nunca por UNKNOWN aislado. `AMBIGUOUS`, base foreign, pérdida observada del menú o recovery invalidan el handoff y prohíben retry; una espera pasiva por el destino puede continuar. Layout proviene del source verificado y geometría del frame fresco. Discovery/recovery sin handoff permanece fail-closed; `ContextResolver` no conserva origen temporal.

Trading abierto desde Quick Menu es modal: la X vuelve al contexto que quedó debajo, incluido Craft según GT del usuario y evidencia C6b desde Treasure. J2 usa `MW→Craft→Quick Menu→Trading→X→Craft→Back→MW` cuando Materials paga Trading, con drenaje Hero antes y después. Treasure sí cambia de contexto: `MW→Craft→Quick Menu→Treasure→Back→Craft→Back→Lobby` no autoriza un retorno a MW. Por eso Gold-full diferido se resuelve sólo tras volver a MW: Treasure→Back→MW, luego Trading nuevo para el retry exacto. No se introduce jerarquía modal genérica.

`TradingMaterialsRuntime` compone los owners cerrados sin añadir routing: `ensure_general` verifica General/material rows frescos, C2 localiza sólo Weapon→Hero, C3 aporta facts posteriores y C4 ejecuta batches `MAX_ALLOWED` hasta Weapon <40 con presupuesto y progreso probado. No diagnostica otras filas ni llama Craft/relief. C6b conserva `PendingCausalOperation` ante Gold-full; un ACK de un solo OK exige alert C4 fresco y Trading/Keys limpio después (HIL 2026-09-23). El caller puede diferir Treasure hasta MW sin perder pending; E2.2 drena todos los Gold y C6b reintenta exactamente una vez con facts frescos, sin segunda visita de recovery.

`TradingPanelReader` pertenece al dominio Trading/Keys: observa un frame Trading resuelto, reciente y posterior a la barrera y emite `TradePanelFact` para C4 y el ACK C6b, sin input ni navegación. En paneles conocidos Weapon/Bronze/Silver lee ambas identidades, el coste total mostrado y la cantidad; sólo reporta coste por trade cuando la división es exacta. La región de segundo coste debe concordar con los paneles vacíos calibrados; un contenido nuevo falla cerrado. Reconoce los alerts explícitos Gold-full, insuficiencia y límite desde OCR local. No añade detector global.

C2a confirmó en Trading/Keys una conversión individual `10 Bronze→2 Silver` por deltas frescos concordantes (`40→30`, `64→66`). `keys_promotion_runtime.make_budget(FreshKeyFacts)` da un upper bound de decisiones: `floor(Bronze/need_bronze) + floor((Silver + 2*floor(Bronze/need_bronze))/need_silver)`. Cuenta cada conversión como una acción aunque `MAX_ALLOWED` pueda agruparlas; no decide orden, capacidad Gold ni el retry causal único de C6b.

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
