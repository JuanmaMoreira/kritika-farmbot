# Contexto actual — Kritika FarmBot

## Qué es

Kritika FarmBot 0.2 automatiza tareas por personaje de **Kritika: The White Knights** sobre un dispositivo Android físico. El runtime productivo vigente ejecuta Black Market, World Boss, Daily Quests y Mailbox, los compone en sesiones multicharacter y cambia de personaje con `StandardRotation`.

GUI Tkinter y CLI son frontends finos del mismo composition root. El código y los tests son la fuente de implementación; la cronología y las calibraciones viven en [`docs/HISTORY.md`](docs/HISTORY.md).

## Runtime actual

```text
Capture
  → Perception
  → Semantic Observations / Runtime Facts
  → ContextResolver
  → Flow / Support Operation / SessionRunner / Rotation
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

- primera `popup.socket_inventory_full`: `Yes → SocketInventoryRelief → Back verificado → World Boss`; el permiso positivo se consume sólo tras confirmar Socket y existe una vez por `run()`;
- segunda `popup.socket_inventory_full`: `No → World Boss`, evento no fatal y fin del flow, sin una segunda entrada positiva;
- primera `popup.equipment_inventory_full`: `Combine → EquipmentCombineRelief → Back verificado → World Boss`; el permiso positivo se consume sólo tras confirmar Combine y existe una vez por `run()`;
- segunda `popup.equipment_inventory_full`: `X → World Boss`, evento no fatal y fin del flow, sin una segunda entrada positiva;
- batalla: asegura Auto Battle ON, lee el timer, espera pasivamente timer + margen y luego busca Raid Complete con polling bounded.

Raid Complete se acepta por presencia del overlay, independientemente de que la base esté resuelta, transitoria o `UNKNOWN`. Continue se verifica contra World Boss. Ausencia del overlay termina en timeout, nunca en éxito supuesto. La conexión fallida post-batalla todavía no tiene semántica/recovery productivo.

`SocketInventoryRelief` es una support operation productiva, no un flow ni una entrada del registry. Desde Socket intenta primero Enhance All exclusivamente con GOLD. Una animación positiva usa taps bounded sólo sobre fases inequívocamente tappable y termina al observar Socket; No Material cierra el modal y habilita el fallback. La venta sólo considera ópalos incompatibles con velo rojo y sólo ejecuta Sell in Bulk cuando `item.socket.sell_level == 0` fue confirmado; cualquier nivel no cero o lectura no confirmada cancela. Retorna `RELIEVED`, `NO_RELIEF_AVAILABLE`, `FAILED` o `CANCELLED` y siempre exige el estado exacto declarado por el caller. El único return plan productivo actual es `Socket → Back → World Boss`.

`EquipmentCombineRelief` es una support operation productiva independiente. Exige `screen.combine` fresca, recorre siempre Transmute → Ethereal condicional → Fuse y reevalúa Fuse después de los pasos previos. Cada status sólo se interpreta en su tab activo; un guard presente sin animación/postcondición verificadas es fallo técnico. Las tres ramas reutilizan `TapThroughAnimation`, acumulan efectos sin short-circuit y exigen desaparición fresca del status correspondiente. El popup Ethereal de material insuficiente es una contradicción defensiva explícita, nunca éxito supuesto. Retorna `RELIEVED`, `NO_RELIEF_AVAILABLE`, `FAILED` o `CANCELLED`; el único return plan productivo confirmado es `Combine → Back → World Boss`.

### Daily Quests y Mailbox

`DailyQuestsFlow` y `MailboxFlow` son `PER_CHARACTER` con contrato `screen.lobby → screen.lobby`. Daily omite Claim All cuando no hay `status.daily_quests_claimable`; si lo hay, ejecuta un único intento y exige desaparición estable del status bajo `screen.quests + mode.daily_quests`. El reward independiente de karats nunca es target.

Mailbox entra a Character Mail, omite Claim All sin claims y nunca lo reintenta. Si observa `activity.mailbox_claim_processing`, exige su ausencia estable; una fase oscura aislada reinicia la estabilidad. Si la actividad nunca aparece pero Character Mail con claims persiste estable, registra intento sin efecto y continúa. Leftovers son no fatales y no disparan liberación de inventario. Delete Read sólo se ejecuta con `status.mailbox_read_mail_present` y exige su desaparición estable; Inbox vacío no es postcondición.

### Sesión y Rotation

`FlowRegistry` registra explícitamente `black_market` y `world_boss`, con metadata, contrato y factory compartidos por todos los frontends.

`SessionRunner` ejecuta los flows seleccionados en orden para cada personaje, verifica precondición y una postcondición permitida después de cada componente, agrega business events y hace exactamente un `RotationStrategy.advance()` por personaje, incluido el retorno final que cierra el ciclo. La selección default termina `… → Daily Quests → Mailbox → Rotation`. Si un flow anterior termina en World Boss, el boundary existente de precondiciones normaliza por `Quick Menu → Lobby` antes de Daily. Cancelación conserva progreso parcial; un fallo técnico, postcondición contradictoria o Rotation fallida abortan sin avanzar a ciegas.

`StandardRotation` no es un flow. Requiere la capability `quick_menu_accessible`, abre Quick Menu, entra a Character Select, confirma el final mediante scroll observado A/T/B, verifica la selección de la última tarjeta, confirma y exige Lobby fresco. No identifica personajes. El allow-list productivo de Quick Menu contiene Lobby y World Boss, con layout interno específico para cada origen.

### Runtime manual, GUI, logging y cancelación

`ProductiveRuntime` compone configuración, ADB, captura, percepción, observer, OCR facts, Auto Battle, executor, `TapThroughAnimation`, `SocketInventoryRelief`, `EquipmentCombineRelief`, registry, flows, session y rotation con cleanup explícito. Antes de validar una pre/postcondición limpia tolera frames transitorios durante una espera bounded; no convierte un estado contradictorio en éxito.

- GUI productiva: `tools.gui`, con launcher `Kritika FarmBot.cmd`; permite ordenar/activar flows, `Run Flow Once`, `Run Session`, character count, Debug Mode y `Stop Safely`. `Run Session` muestra elapsed monotónico `HH:MM:SS`, actualizado por Tk y congelado con cualquier resultado terminal.
- CLI productiva: `tools.run_flow` y `tools.run_session`, con el mismo registry/runtime y exit codes documentados en README.
- `RuntimeEventStream`: eventos estructurados a log JSONL por ejecución, consola y suscriptores. INFO/WARNING/ERROR forman la vista normal; debug agrega facts, transiciones, retries y waits.
- GUI: un único worker no-Tk ejecuta el runtime y entrega eventos/resultados por queue; el main thread sólo renderiza. No contiene business logic.
- `CancellationToken` es thread-safe y compartido por GUI/CLI, runner, facts y waits. Stop/Ctrl+C solicita cancelación en boundaries seguros; no mata threads ni clasifica cancelación como fallo técnico.

`ControlledWait` es una primitive monotónica, cancelable y bounded para actividad ya iniciada. Recibe duración o deadline y condiciones opcionales de completion/terminal. Sin condición, alcanzar el límite es completion de la espera pasiva; con condición, vencer sin observarla es timeout. Un check falso sólo continúa; la primitive no ejecuta input, retry ni recovery. `TapThroughAnimation` alterna snapshots frescos y taps state-guarded para una animación ya iniciada, con intervalo, timeout y máximo de taps; flash, `UNKNOWN` o estado incompatible nunca autorizan input.

## Estados, overlays y facts útiles

Contextos base productivos:

- `screen.lobby`
- `screen.quests`
- `screen.mailbox`
- `screen.character_select`
- `screen.battle_mode_select`
- `screen.black_market`
- `screen.combine`
- `screen.socket`
- `screen.world_boss`
- `screen.world_boss_battle`

Overlays/popups productivos:

- `menu.quick`
- `mode.daily_quests`
- `status.daily_quests_claimable`
- `mode.mailbox_character_mail`
- `status.mailbox_claimable`
- `status.mailbox_read_mail_present`
- `popup.purchase_confirmation`
- `popup.insufficient_gold`
- `popup.inventory_full`
- `overlay.world_boss_select_boss`
- `popup.world_boss_previous_rewards`
- `popup.socket_inventory_full`
- `popup.socket_enhance_all`
- `popup.socket_no_material`
- `popup.socket_sell`
- `popup.equipment_inventory_full`
- `mode.combine_fuse`
- `mode.combine_transmute`
- `status.combine_transmute_available`
- `status.combine_ethereal_available`
- `status.combine_fuse_available`
- `panel.combine_awakened_transmute`
- `panel.combine_ethereal_random_part`
- `popup.combine_all`
- `popup.ethereal_mass_combine`
- `popup.ethereal_no_material`
- `overlay.world_boss_raid_complete`

Facts productivos:

- Black Market internos: `currency.black_market.gold(slot)` y `status.black_market.purchased(slot)`.
- Socket: Equipment Home activo e `item.socket.incompatible_opal(slot)` sobre el velo rojo seleccionado o no seleccionado; `activity.socket.enhance_animation_tappable` sólo en fases oscuras inequívocas. El flash brillante queda sin autorización.
- Combine: `landmark.combine_context` deriva `screen.combine` desde el tab estructural izquierdo o desde la actividad inequívoca durante la animación; así el frame tappable nunca necesita autorizar input desde `UNKNOWN`. Los tabs activos asignan modo. `indicator.combine_rows_upper`, `indicator.combine_row_bottom` e `indicator.combine_rows` son evidencia posicional y sólo su conjunción con el modo deriva disponibilidad. `activity.combine_animation_tappable` es común a Transmute, Ethereal y Fuse. Durante la animación Transmute puede seguir visible el `N` inferior real de Ethereal; sin tab Transmute activo no se deriva un status espurio.
- Daily Quests: el `Claim` de filas visibles deriva `status.daily_quests_claimable` únicamente bajo el tab Daily activo. La recompensa de progreso independiente (30 karats en la adquisición) queda fuera de esa ROI y es un negativo confirmado. Tras Claim All, la desaparición estable del status mientras persisten `screen.quests + mode.daily_quests` es la señal adquirida de quiescencia; ausencia inicial admite success/no-op.
- Character Mail: `Claim` y `Delete` de filas derivan statuses independientes sólo bajo el tab Character Mail activo. `activity.mailbox_claim_processing` observa la fase cyan del spinner central; como su rotación contiene frames oscuros, un negativo aislado no indica completion. La espera futura debe exigir ausencia estable en frames frescos, bounded y conservando `screen.mailbox`. Los bubbles transitorios no son señal principal.
- La base Socket exige el tab izquierdo persistente en ROI `(0.16, 0.11, 0.26, 0.24)`, con cinco apariencias que cubren selected/unselected y el sombreado más fuerte de Enhance All. El encabezado superior derecho fue retirado como landmark porque el chat dinámico ocupa la banda observada `(0.44, 0.12, 0.85, 0.21)` y puede ocluirlo.
- Battle Mode Select usa el título fijo de la tarjeta World Boss en ROI `(0.16, 0.58, 0.32, 0.68)`, fuera de esa banda. Sus variantes current/historical sustituyen al encabezado superior ocluible sin cambiar el contrato semántico.
- Los paneles Black Market, popups y overlays se renderizan por encima del chat; una intersección de sus ROIs no implica oclusión. Las pantallas base no tienen esa protección.
- OCR demand-driven: `resource.sapphires` en Lobby, `battle.timer_remaining` en batalla World Boss e `item.socket.sell_level` sólo con `screen.socket + popup.socket_sell`; este último exige dos lecturas y es la barrera destructiva `level == 0`. Como el chat puede cubrir temporalmente la única ubicación visual del timer, su extractor reintenta pasivamente hasta 10 frames frescos separados 0,5 s, siempre dentro del timeout/cancelación del caller y sin enviar input.
- Temporal: `setting.auto_battle = ON/OFF/UNKNOWN`; sólo OFF inequívoco y contexto de batalla vigente autorizan toggle. ON se verifica en una ventana fresca posterior.

`CharacterContext` conserva `name=None` y `name_confidence=None`: el índice de sesión no es identidad. Recursos, timer y otros valores cambiantes son Runtime Facts, no CharacterContext.

## Estado de validación

- Suite hardware-free: **1090/1090 tests verdes**.
- Corpus productivo ampliado: 300 frames × 45 detectores, **13500/13500** pares, 300/300 resoluciones y overlays, cero wrong/ambiguous. Los siete landmarks CV de Daily Quests/Mailbox separan positivos y negativos; su gap más estrecho es `landmark.mailbox_row_delete_button` (`0.081946`). El detector derivado de actividad Mailbox queda cubierto por tests dirigidos.
- Adquisición HIL Daily Quests: apertura desde Lobby, Claim All con desaparición de `Claim`, estado estable con `Start`/ads, segundo Claim All no-op, recompensa de progreso separada y cierre a Lobby confirmados live.
- Adquisición HIL Character Mail: Account Mail → Character Mail, Claim All con spinner/bubbles y transición `Claim → Delete`, quiescencia con Inbox aún 19, Delete Read Mail y cierre a Lobby confirmados live. Por límites de recompensa quedaron cinco mails reclamables; el estado residual se preserva como final válido y no dispara ninguna rutina para liberar espacio.
- Black Market está validado en ramas de compra, no GOLD, Insufficient Gold, Inventory Full, verificación de Purchased y sesión completa previa 28/28.
- World Boss está validado hardware-free en sapphires insuficientes, Previous Rewards, batalla/Raid Complete, ramas positivas únicas y segundas ramas negativas para Socket/Equipment Full, y Rotation desde World Boss.
- Smoke HIL Enhance positivo: `Yes` llegó a Socket, GOLD produjo efecto, `TapThroughAnimation` ejecutó 6 taps guardados, Sell quedó `NOT_RUN` y `Back → World Boss` se verificó. La primera corrida expuso y luego corrigió un abort prematuro durante el frame transitorio World Boss sin popup.
- Smoke HIL No Material + venta: GOLD confirmó `NO_EFFECT`, Equipment Home seleccionó el slot rojo 3, OCR confirmó `Opal (Skill)+0` 2/2 con confidence `0.958` y el usuario autorizó Bulk sobre el popup visible. La venta dejó popup y candidato ausentes e inventario `1/29 → 1/28`; el primer frame limpio precedió al landmark estable, por lo que esa transición ahora tolera el tránsito pasivo sin habilitar retry. La entrada a Socket fue manual, así que correctamente no se ejecutó ni declaró `Back → World Boss`.
- La segunda aparición de Socket Full no se forzó live: el usuario confirmó que preparar ese caso extremo no era razonable. La policy queda cubierta hardware-free (`No`, fin no fatal, nunca segundo `Yes`) y los business events permiten auditarla si sucede en producción.
- La adquisición HIL de Equipment/Combine verificó efectos reales en orden Transmute (`178 → 158`), Ethereal (`158 → 148`) y Fuse (`148 → 123`), desaparición independiente de cada indicador y retorno `Back → World Boss`. La implementación consume exactamente ese contrato; no requirió un smoke adicional después de los tests.
- El landmark chat-safe resuelve los frames Socket live con confidence `1.0`; sus 12 positivos curados quedaron en `0.977370–1.0` frente a máximo de 159 negativos `0.713128`. Una captura legacy Meteorites con chat visible quedó como negativo explícito y dio raw `0.469354`.
- El landmark chat-safe de Battle Mode separa 17 positivos curados (`0.991948–0.999958`) de 154 negativos (máximo `0.390351`) y mantiene la ROI productiva fuera del chat.
- `StandardRotation` pasó un loop aislado 28/28 con retorno al personaje inicial.
- La composición `Black Market → World Boss → Rotation` y la GUI productiva están validadas.
- Primer checkpoint combinado desde GUI: sesión `COMPLETED`, 28/28 personajes, 28 advances, 28 ejecuciones de cada flow y cero fallos técnicos. El detalle auditable está en `docs/HISTORY.md`.

## Deuda y limitaciones relevantes

- Adquirir y diseñar recovery bounded para el popup de conexión post-batalla de World Boss.
- Sólo World Boss tiene return plan adquirido para `EquipmentCombineRelief`; otros callers requieren evidencia live específica antes de integrarse.
- No existe `CharacterContextProvider` ni OCR de nombre. Tampoco costo/rank/participation, Auto Repeat o scheduler.
- `ConflictResolver`, recovery transversal e isolation/continuation unattended siguen futuros. Los retries locales verificados no se trasladan a esa capa.
- Timings y retries pueden seguir ajustándose sólo a partir de logs productivos; no hay necesidad de tuning preventivo.
- `main.py` y módulos legacy preservados no son entrypoints productivos. `AdsManager` continúa standalone y desacoplado.

## Próximo trabajo

Daily Quests y Mailbox quedan cerrados como flows productivos sin smoke adicional: la evidencia HIL ya había fijado targets y señales, y tests/evaluator no dejaron una duda que requiriera hardware. El próximo trabajo vuelve a las deudas enumeradas en [`ROADMAP.md`](ROADMAP.md); no se avanza a routines ni a otro flow desde este checkpoint.
