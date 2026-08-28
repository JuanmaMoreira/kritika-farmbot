# Contexto actual — Kritika FarmBot

## Qué es

Kritika FarmBot 0.2 automatiza tareas por personaje de **Kritika: The White Knights** sobre un dispositivo Android físico. El runtime productivo vigente ejecuta Black Market y World Boss, compone ambos en sesiones multicharacter y cambia de personaje con `StandardRotation`.

GUI Tkinter y CLI son frontends finos del mismo composition root. El código y los tests son la fuente de implementación; la cronología y las calibraciones viven en [`docs/HISTORY.md`](docs/HISTORY.md).

## Runtime actual

```text
Capture
  → Perception
  → Semantic Observations / Runtime Facts
  → ContextResolver
  → Flow / SessionRunner / Rotation
  → operaciones semánticas verificadas
  → ActionExecutor
  → AdbClient
```

- `ScrcpyFrameSource` posee captura, proceso, socket, decoder y cleanup; publica frames BGR con sequence/timestamp.
- `PerceptionEngine` observa un frame y `ContextResolver` produce estado `RESOLVED`, `UNKNOWN` o `AMBIGUOUS`, con overlays independientes.
- `RuntimeObserver` conserva frame, observaciones, estado, facts y geometría coherentes; sus esperas usan frames frescos, timeout y cancelación.
- `RuntimeFactReader` adquiere OCR demand-driven y tipado. `TemporalObserver` sirve facts multiframe como Auto Battle.
- Flows y Rotation declaran intención, postcondiciones y guards; no hacen matching ni llaman ADB.
- `ActionExecutor` traduce intents a input físico normalizado por `frame.shape`; `AdbClient` es el único límite ADB.
- Una acción observable se considera exitosa sólo tras verificar su efecto. Retries son bounded y state-guarded; `UNKNOWN` no autoriza input ni retry.

## Capacidades productivas

### Black Market

`BlackMarketFlow` es `PER_CHARACTER` y declara `screen.lobby → screen.lobby`. Abre Black Market, lee una vez los diez slots, procesa únicamente GOLD en orden row-major y nunca compra KARATS.

Purchase Confirmation exige `Purchased` fresco en el mismo slot. Insufficient Gold ejecuta `No`; Inventory Full ejecuta `OK` y continúa con el siguiente GOLD sin reintentar ese slot. Ambos son resultados de negocio no fatales. Cero GOLD es success/no-op. Navegación, selección y respuestas usan `VerifiedTransition`; cualquier postcondición no verificable o estado incompatible produce fallo técnico conservador.

### World Boss

`WorldBossFlow` es `PER_CHARACTER`, aplica `ALWAYS_PARTICIPATE` y declara Lobby como entrada, con Lobby o World Boss como salidas exitosas. Su primera operación es leer sapphires por OCR; `<5` emite `world_boss.insufficient_sapphires` y termina en Lobby sin input.

Con recursos suficientes navega Lobby → Battle Mode Select → Select Boss → World Boss. Previous Rewards es una rama opcional que se estabiliza y confirma antes de Start. Después de Start:

- `popup.world_boss_inventory_full`: `No → World Boss`, evento no fatal y fin del flow;
- `popup.world_boss_bag_full`: `X → World Boss`, evento no fatal y fin del flow;
- batalla: asegura Auto Battle ON, lee el timer, espera pasivamente timer + margen y luego busca Raid Complete con polling bounded.

Raid Complete se acepta por presencia del overlay, independientemente de que la base esté resuelta, transitoria o `UNKNOWN`. Continue se verifica contra World Boss. Ausencia del overlay termina en timeout, nunca en éxito supuesto. La conexión fallida post-batalla todavía no tiene semántica/recovery productivo.

### Sesión y Rotation

`FlowRegistry` registra explícitamente `black_market` y `world_boss`, con metadata, contrato y factory compartidos por todos los frontends.

`SessionRunner` ejecuta los flows seleccionados en orden para cada personaje, verifica precondición y una postcondición permitida después de cada componente, agrega business events y hace exactamente un `RotationStrategy.advance()` por personaje, incluido el retorno final que cierra el ciclo. Cancelación conserva progreso parcial; un fallo técnico, postcondición contradictoria o Rotation fallida abortan sin avanzar a ciegas.

`StandardRotation` no es un flow. Requiere la capability `quick_menu_accessible`, abre Quick Menu, entra a Character Select, confirma el final mediante scroll observado A/T/B, verifica la selección de la última tarjeta, confirma y exige Lobby fresco. No identifica personajes. El allow-list productivo de Quick Menu contiene Lobby y World Boss, con layout interno específico para cada origen.

### Runtime manual, GUI, logging y cancelación

`ProductiveRuntime` compone configuración, ADB, captura, percepción, observer, OCR facts, Auto Battle, executor, registry, flows, session y rotation con cleanup explícito. Antes de validar una pre/postcondición limpia tolera frames transitorios durante una espera bounded; no convierte un estado contradictorio en éxito.

- GUI productiva: `tools.gui`, con launcher `Kritika FarmBot.cmd`; permite ordenar/activar flows, `Run Flow Once`, `Run Session`, character count, Debug Mode y `Stop Safely`.
- CLI productiva: `tools.run_flow` y `tools.run_session`, con el mismo registry/runtime y exit codes documentados en README.
- `RuntimeEventStream`: eventos estructurados a log JSONL por ejecución, consola y suscriptores. INFO/WARNING/ERROR forman la vista normal; debug agrega facts, transiciones, retries y waits.
- GUI: un único worker no-Tk ejecuta el runtime y entrega eventos/resultados por queue; el main thread sólo renderiza. No contiene business logic.
- `CancellationToken` es thread-safe y compartido por GUI/CLI, runner, facts y waits. Stop/Ctrl+C solicita cancelación en boundaries seguros; no mata threads ni clasifica cancelación como fallo técnico.

`ControlledWait` es una primitive monotónica, cancelable y bounded para actividad ya iniciada. Recibe duración o deadline y condiciones opcionales de completion/terminal. Sin condición, alcanzar el límite es completion de la espera pasiva; con condición, vencer sin observarla es timeout. Un check falso sólo continúa; la primitive no ejecuta input, retry ni recovery.

## Estados, overlays y facts útiles

Contextos base productivos:

- `screen.lobby`
- `screen.character_select`
- `screen.battle_mode_select`
- `screen.black_market`
- `screen.world_boss`
- `screen.world_boss_battle`

Overlays/popups productivos:

- `menu.quick`
- `popup.purchase_confirmation`
- `popup.insufficient_gold`
- `popup.inventory_full`
- `overlay.world_boss_select_boss`
- `popup.world_boss_previous_rewards`
- `popup.world_boss_inventory_full`
- `popup.world_boss_bag_full`
- `overlay.world_boss_raid_complete`

Facts productivos:

- Black Market internos: `currency.black_market.gold(slot)` y `status.black_market.purchased(slot)`.
- OCR demand-driven: `resource.sapphires` en Lobby y `battle.timer_remaining` en batalla World Boss.
- Temporal: `setting.auto_battle = ON/OFF/UNKNOWN`; sólo OFF inequívoco y contexto de batalla vigente autorizan toggle. ON se verifica en una ventana fresca posterior.

`CharacterContext` conserva `name=None` y `name_confidence=None`: el índice de sesión no es identidad. Recursos, timer y otros valores cambiantes son Runtime Facts, no CharacterContext.

## Estado de validación

- Última suite hardware-free conocida en `1814ddc`: **921/921 tests verdes**; no hubo cambios de código posteriores a ese checkpoint.
- Black Market está validado en ramas de compra, no GOLD, Insufficient Gold, Inventory Full, verificación de Purchased y sesión completa previa 28/28.
- World Boss está validado en sapphires insuficientes, Previous Rewards, batalla/Raid Complete, Inventory Full, Bag Full y Rotation desde World Boss.
- `StandardRotation` pasó un loop aislado 28/28 con retorno al personaje inicial.
- La composición `Black Market → World Boss → Rotation` y la GUI productiva están validadas.
- Primer checkpoint combinado desde GUI: sesión `COMPLETED`, 28/28 personajes, 28 advances, 28 ejecuciones de cada flow y cero fallos técnicos. El detalle auditable está en `docs/HISTORY.md`.

## Deuda y limitaciones relevantes

- Adquirir y diseñar recovery bounded para el popup de conexión post-batalla de World Boss.
- Inventory Full/Bag Full de World Boss aplican policy conservadora de skip; liberar espacio y reanudar requiere una policy futura acordada.
- No existe `CharacterContextProvider` ni OCR de nombre. Tampoco costo/rank/participation, Auto Repeat o scheduler.
- `ConflictResolver`, recovery transversal e isolation/continuation unattended siguen futuros. Los retries locales verificados no se trasladan a esa capa.
- Timings y retries pueden seguir ajustándose sólo a partir de logs productivos; no hay necesidad de tuning preventivo.
- `main.py` y módulos legacy preservados no son entrypoints productivos. `AdsManager` continúa standalone y desacoplado.

## Próximo trabajo

Usar GUI/runtime productivo para recopilar problemas reales y resolver bugs o tuning a partir de logs. Antes de implementar otro flow/capacidad, elegirlo y definir con el usuario intención, outcomes y policy. Las prioridades conocidas están en [`ROADMAP.md`](ROADMAP.md).
