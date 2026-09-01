# Contexto actual — Kritika FarmBot

## Qué es

Kritika FarmBot 0.2 automatiza tareas por personaje de **Kritika: The White Knights** sobre un dispositivo Android físico. El runtime productivo vigente ejecuta Black Market, World Boss, Send Stamina, Summon Pet Daily, Daily Quests, Mailbox y Guild Check-In, los compone en sesiones multicharacter y cambia de personaje con `StandardRotation`.

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

Con recursos suficientes navega Lobby → Battle Mode Select → Select Boss → World Boss. En Battle Mode Select tolera el status auxiliar `status.world_boss_daily_active`, pero no lo exige ni lo usa como autorización de negocio. Previous Rewards es una rama opcional que se estabiliza y confirma antes de Start. Después de Start:

- primera `popup.socket_inventory_full`: `Yes → SocketInventoryRelief → Back verificado → World Boss`; el permiso positivo se consume sólo tras confirmar Socket y existe una vez por `run()`;
- segunda `popup.socket_inventory_full`: `No → World Boss`, evento no fatal y fin del flow, sin una segunda entrada positiva;
- primera `popup.equipment_inventory_full`: `Combine → EquipmentCombineRelief → Back verificado → World Boss`; el permiso positivo se consume sólo tras confirmar Combine y existe una vez por `run()`;
- segunda `popup.equipment_inventory_full`: `X → World Boss`, evento no fatal y fin del flow, sin una segunda entrada positiva;
- batalla: asegura Auto Battle ON, lee el timer, espera pasivamente timer + margen y luego busca Raid Complete con polling bounded; si Raid Complete interrumpe la ventana temporal de Auto Battle, reacquire el overlay y continúa directamente sin exigir un timer que ya dejó de ser aplicable.

Raid Complete se acepta por presencia del overlay, independientemente de que la base esté resuelta, transitoria o `UNKNOWN`. La ventana temporal de Auto Battle busca diez frames dentro de `8 s` y, si el plazo vence, sólo clasifica la evidencia parcial cuando ya reunió al menos nueve muestras válidas; ocho o menos conservan el timeout. Si vence en el borde de un raid rápido, el flow hace una espera pasiva bounded por Raid Complete y sólo continúa si observa ese overlay. Continue se verifica contra World Boss. Ausencia del overlay conserva el fallo, nunca se convierte en éxito supuesto. La conexión fallida post-batalla todavía no tiene semántica/recovery productivo.

`SocketInventoryRelief` es una support operation productiva, no un flow ni una entrada del registry. Desde Socket intenta primero Enhance All exclusivamente con GOLD y nunca repite ese tap. Una animación positiva usa taps bounded sólo sobre fases inequívocamente tappable y termina al observar Socket. Si percepción pierde todas esas fases y el outcome bounded termina ya en Socket limpio, una segunda confirmación fresca del mismo terminal permite declarar efecto sin taps de animación; un terminal incompatible o inestable falla. No Material cierra el modal y habilita el fallback. La venta sólo considera ópalos incompatibles con velo rojo y sólo ejecuta Sell in Bulk cuando `item.socket.sell_level == 0` fue confirmado; cualquier nivel no cero o lectura no confirmada cancela. Retorna `RELIEVED`, `NO_RELIEF_AVAILABLE`, `FAILED` o `CANCELLED` y siempre exige el estado exacto declarado por el caller. El único return plan productivo actual es `Socket → Back → World Boss`.

`EquipmentCombineRelief` es una support operation productiva independiente. Exige `screen.combine` fresca, recorre siempre Transmute → Ethereal condicional → Fuse y reevalúa Fuse después de los pasos previos. Cada status sólo se interpreta en su tab activo; un guard presente sin animación/postcondición verificadas es fallo técnico. Las tres ramas reutilizan `TapThroughAnimation`, acumulan efectos sin short-circuit y exigen desaparición fresca del status correspondiente. Una combinación Ethereal corta puede volver directamente a Random Part antes de que aparezca una fase tappable; ese retorno sólo continúa hacia la verificación en Transmute y no se declara efecto si el guard permanece. El popup Ethereal de material insuficiente es una contradicción defensiva explícita, nunca éxito supuesto. Retorna `RELIEVED`, `NO_RELIEF_AVAILABLE`, `FAILED` o `CANCELLED`; el único return plan productivo confirmado es `Combine → Back → World Boss`.

### Daily Quests y Mailbox

`DailyQuestsFlow` y `MailboxFlow` son `PER_CHARACTER` con contrato `screen.lobby → screen.lobby`. Quests restaura el último tab visitado por personaje: Daily primero verifica el shell `screen.quests` y, sólo si falta `mode.daily_quests`, selecciona ese tab una vez y valida el modo antes de continuar. Luego omite Claim All cuando no hay `status.daily_quests_claimable`; si lo hay, ejecuta un único intento y exige desaparición estable del status bajo `screen.quests + mode.daily_quests`. El reward independiente de karats nunca es target.

Mailbox entra a Character Mail, omite Claim All sin claims y nunca lo reintenta. Después de la ventana breve de onset, la espera de resultado de Claim All dispone de un budget de `30 s` porque cada mail puede producir su propio bubble, pero termina antes al confirmar la postcondición. Si observa `activity.mailbox_claim_processing`, exige su ausencia estable; una fase oscura aislada reinicia la estabilidad. Si el onset no llega a observarse, reutiliza ese mismo budget y exige Character Mail sin actividad estable: claims persistentes producen intento sin efecto y su desaparición confirma completion. Leftovers son no fatales y no disparan liberación de inventario. Delete Read sólo se ejecuta con `status.mailbox_read_mail_present` y exige su desaparición estable; un frame transitorio `screen.mailbox` donde una burbuja tapa el tab consume espera pero no satisface éxito ni aborta. Inbox vacío no es postcondición.

### Send Stamina

`SendStaminaFlow` es `PER_CHARACTER` con contrato `screen.lobby → screen.lobby` y verifica el estado intermedio `screen.friends`. Daily ausente es success/no-op sin tocar All. Daily presente autoriza exactamente un `SendStaminaToAllFriends`; la completion exige desaparición fresca del status durante `0.75 s` dentro de `3 s`. Si ese budget vence y Friends conserva Daily, el flow exige una confirmación fresca estable durante `0.75 s`, emite `send_stamina.all_no_effect` y `send_stamina.daily_pending`, y cierra hacia Lobby como resultado no fatal. Estados incompatibles, pending no verificable o postcondición de cierre no verificable fallan sin retry; cancelación se propaga. El spinner/bubble y el oscurecimiento de botones individuales no forman parte de la condición de negocio.

### Semántica Daily restante sin consumidores funcionales

Friends, Guild Attendance y la tarjeta World Boss comparten exactamente el mismo asset verde de Daily, pero lo observan con ROIs contextuales independientes. Guild expone `status.guild_attendance_daily_active` sin alterar la clasificación active/completed; World Boss expone `status.world_boss_daily_active` únicamente en Battle Mode Select. Esta última señal es evidencia para eligibility externa futura: `WorldBossFlow` la tolera como overlay contextual, pero no la consume para decidir participación.

### Summon Pet Daily y Pet Summon Space Relief

`SummonPetDailyFlow` es `PER_CHARACTER`, usa el id `_daily` `summon_pet_daily` y declara `screen.pets_manage → screen.pets_manage/screen.pet_summon`. La composición abre Pets y verifica Manage antes de invocarlo. Daily ausente es success/no-op y permanece en Manage. Daily presente entra a Summon y elige Epic sólo con `status.pet_epic_available`; si observa unavailable usa Premium sin distinguir ticket de GOLD. Ambas rutas ejecutan exactamente `1 (Open)`, exigen `screen.pet_summon_result` estable y sólo completan después de cerrar el resultado y confirmar la desaparición estable de la Daily; las terminaciones no fatales quedan también en Summon.

Epic expone estados mutuamente excluyentes disponible/no disponible a partir del brillo estable de la tarjeta, sin OCR de fragmentos ni umbral hardcodeado de costo. El juego puede habilitar eventos de summon Epic por 7 runas; el render brillante/apagado sigue siendo el guard autoritativo. La lectura se suprime mientras un selector o popup cubre la pantalla. Premium distingue sólo las variantes observables ticket/GOLD y sus selectores; el juego, no el flow, decide cuál recurso consume. Un resultado exitoso se reconoce por banner dorado + panel de pergamino, independientes de identidad y rareza del pet.

`popup.insufficient_gold` usa la rama segura existente `No`, emite un business event no fatal y deja la Daily pendiente. Pet Full usa `Yes`, exige `screen.pet_combine` e invoca `PetSummonSpaceRelief` una sola vez por `run()`. `RELIEVED` autoriza un único retry fresco; `NO_RELIEF_AVAILABLE` y un segundo Pet Full producen resolución manual no fatal, `FAILED` es fallo técnico y `CANCELLED` se propaga. Toda rama que entró a Combine selecciona y verifica Summon antes de completar.

`PetSummonSpaceRelief` es una support operation incidental separada con precondición `screen.pet_combine` y outcomes `RELIEVED`, `NO_RELIEF_AVAILABLE`, `FAILED` y `CANCELLED`. Ejecuta un único Combine All, confirma su popup y sólo declara efecto después de `screen.pet_combine_result` + `TapThroughAnimation` + retorno estable a Combine. No material, runas Epic llenas u otro caso seguro sin progreso producen `NO_RELIEF_AVAILABLE`; una contradicción técnica produce `FAILED`. No busca candidatos Normal/Rare, no ejecuta Mass Evolve, no navega a Summon, no abre Epic `10 (Open)` y no hace un segundo Combine All. La semántica, assets y regresiones perceptivas adquiridas para esas rutas permanecen preservadas para futuras rutinas específicas de Pets.

### Guild Check-In

La semántica productiva reconoce `screen.guild`, `status.guild_attendance_active`, `status.guild_attendance_completed` y el status independiente `status.guild_attendance_daily_active`. Attendance deriva del valor HSV de una franja interior del botón: pendiente es rojo brillante (`V 167.16–168.41`) y completado es oscuro/presionado (`V 81.89–84.58`). La ROI queda fuera del bubble transitorio y la lectura de ambos estados del botón se suprime mientras `menu.quick` está abierto. Navegación y flow toleran el status Daily junto al estado de Attendance, pero no lo consumen como autorización de negocio.

`GuildCheckInFlow` es `PER_CHARACTER` con contrato `screen.guild → screen.guild`. Completado inicial es success/no-op; activo autoriza exactamente un `CheckInGuildAttendance` y espera hasta `10 s` por completion estable durante `0.75 s` sobre snapshots frescos. Timeout, estados incompatibles/contradictorios o postcondición no verificable fallan sin segundo tap; cancelación se propaga. El flow no navega ni usa `ControlledWait` o bubble text.

La navegación live `Lobby → Quick Menu → Guild` terminó en `screen.guild`, y Guild abrió Quick Menu con el layout desplazado. Pet Manage y Pet Summon también tienen acceso físico confirmado a Quick Menu. Para normalizar un requisito Guild, `MinimalPreconditionEnsurer` prioriza el acceso directo adquirido `Lobby → Guild`; desde otros orígenes permitidos, como World Boss o las dos salidas estables de Pets, usa `Quick Menu → Guild` con layout desplazado. Todas las operaciones exigen `screen.guild` observable y, si ya está en Guild, no navega.

### Sesión y Rotation

`FlowRegistry` registra explícitamente `black_market`, `world_boss`, `send_stamina`, `summon_pet_daily`, `daily_quests`, `mailbox` y `guild_check_in`, con metadata, contrato y factory compartidos por todos los frontends.

`SessionRunner` ejecuta los flows seleccionados en orden para cada personaje, verifica precondición y una postcondición permitida después de cada componente, agrega business events y hace exactamente un `RotationStrategy.advance()` por personaje, incluido el retorno final que cierra el ciclo. La selección default conserva `… → Send Stamina → Summon Pet Daily → Daily Quests → Mailbox → Guild Check-In → Rotation`, de modo que el progreso de las actividades previas pueda reclamarse en Daily Quests durante el mismo personaje. El boundary de precondiciones normaliza Lobby, Pet Manage o Guild mediante transiciones explícitas verificadas. Manage/Summon → Guild usa Quick Menu directamente, sin retorno preventivo a Lobby; cuando el siguiente requisito sí es Lobby, usa el `ClosePets` directo. Cancelación conserva progreso parcial; un fallo técnico, postcondición contradictoria o Rotation fallida abortan sin avanzar a ciegas.

`StandardRotation` no es un flow. Requiere la capability `quick_menu_accessible`, abre Quick Menu, entra a Character Select, confirma el final mediante scroll observado A/T/B, verifica la selección de la última tarjeta, confirma y exige Lobby fresco. No identifica personajes. El allow-list productivo contiene Lobby, World Boss, Guild, Pet Manage y Pet Summon; los orígenes no-Lobby usan el layout desplazado y conservan sólo sus statuses compatibles.

### Runtime manual, GUI, logging y cancelación

`ProductiveRuntime` compone configuración, ADB, captura, percepción, observer, OCR facts, Auto Battle, executor, `TapThroughAnimation`, `SocketInventoryRelief`, `EquipmentCombineRelief`, `PetSummonSpaceRelief`, registry, flows, session y rotation con cleanup explícito. Antes de validar una pre/postcondición limpia tolera frames transitorios durante una espera bounded; no convierte un estado contradictorio en éxito.

- GUI productiva: `tools.gui`, con launcher `Kritika FarmBot.cmd`; permite ordenar/activar flows, `Run Flow Once`, `Run Session`, character count, Debug Mode y `Stop Safely`. `Run Session` muestra elapsed monotónico `HH:MM:SS`, actualizado por Tk y congelado con cualquier resultado terminal.
- CLI productiva: `tools.run_flow` y `tools.run_session`, con el mismo registry/runtime y exit codes documentados en README.
- `RuntimeEventStream`: eventos estructurados a log JSONL por ejecución, consola y suscriptores. INFO/WARNING/ERROR forman la vista normal; debug agrega facts, transiciones, retries y waits.
- GUI: un único worker no-Tk ejecuta el runtime y entrega eventos/resultados por queue; el main thread sólo renderiza. No contiene business logic.
- `CancellationToken` es thread-safe y compartido por GUI/CLI, runner, facts y waits. Stop/Ctrl+C solicita cancelación en boundaries seguros; no mata threads ni clasifica cancelación como fallo técnico.

`ControlledWait` es una primitive monotónica, cancelable y bounded para actividad ya iniciada. Recibe duración o deadline y condiciones opcionales de completion/terminal. Sin condición, alcanzar el límite es completion de la espera pasiva; con condición, vencer sin observarla es timeout. Un check falso sólo continúa; la primitive no ejecuta input, retry ni recovery. `TapThroughAnimation` alterna snapshots frescos y taps state-guarded para una animación ya iniciada, con intervalo, timeout y máximo de taps; flash, `UNKNOWN` o estado incompatible nunca autorizan input.

## Estados, overlays y facts útiles

Contextos base productivos:

- `screen.lobby`
- `screen.guild`
- `screen.quests`
- `screen.mailbox`
- `screen.pets_manage`
- `screen.pet_summon`
- `screen.pet_summon_result`
- `screen.pet_combine`
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
- `status.guild_attendance_active`
- `status.guild_attendance_completed`
- `mode.mailbox_character_mail`
- `status.mailbox_claimable`
- `status.mailbox_read_mail_present`
- `status.pet_summon_daily_active`
- `status.pet_epic_available`
- `status.pet_epic_unavailable`
- `status.pet_premium_ticket_available`
- `status.pet_premium_gold`
- `overlay.pet_epic_selector`
- `overlay.pet_premium_ticket_selector`
- `overlay.pet_premium_gold_selector`
- `popup.pet_epic_insufficient_fragments`
- `popup.pet_inventory_full`
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
- Friends/Daily: el título y All resuelven `screen.friends`; el badge posicional deriva `status.friends_send_stamina_daily_active`. Su desaparición estable es la señal de negocio adquirida y el bubble queda fuera de la ROI.
- Guild: `landmark.guild_message_tab` resuelve el shell fuera del bubble y del chat superior. `GuildAttendanceDetector` clasifica exclusivamente la franja estable del fill rojo como active/completed, emite estados mutuamente excluyentes y no los emite bajo Quick Menu. Un detector separado observa el badge Daily junto a Attendance; el bubble sólo aporta una variante positiva de completion.
- Pet Summon/Combine: el shell superior y los tabs izquierdos resuelven Manage/Summon/Combine sin usar el título ocluible. Epic usa luminancia de tarjeta, no cantidad asumida. Pet Combine añade candidatos low-tier por color de frame y región, modo Mass Evolve, confirmación tier-valued, popups de Combine All/no material/runas Epic llenas y un `RESULT` común resuelto. Estas observaciones no eligen estrategia ni autorizan venta/slots.
- Character Mail: `Claim` y `Delete` de filas derivan statuses independientes sólo bajo el tab Character Mail activo. `activity.mailbox_claim_processing` observa la fase cyan del spinner central; como su rotación contiene frames oscuros, un negativo aislado no indica completion. La espera futura debe exigir ausencia estable en frames frescos, bounded y conservando `screen.mailbox`. Los bubbles transitorios no son señal principal.
- La base Socket exige el tab izquierdo persistente en ROI `(0.16, 0.11, 0.26, 0.24)`, con cinco apariencias que cubren selected/unselected y el sombreado más fuerte de Enhance All. El encabezado superior derecho fue retirado como landmark porque el chat dinámico ocupa la banda observada `(0.44, 0.12, 0.85, 0.21)` y puede ocluirlo.
- Battle Mode Select usa el título fijo de la tarjeta World Boss en ROI `(0.16, 0.58, 0.32, 0.68)`, fuera de esa banda. Sus variantes current/historical sustituyen al encabezado superior ocluible sin cambiar el contrato semántico. `status.world_boss_daily_active` deriva sólo del badge en la esquina de esa tarjeta; badges simultáneos de Monster Wave/Tower son negativos contextuales.
- Los paneles Black Market, popups y overlays se renderizan por encima del chat; una intersección de sus ROIs no implica oclusión. Las pantallas base no tienen esa protección.
- OCR demand-driven: `resource.sapphires` en Lobby, `battle.timer_remaining` en batalla World Boss e `item.socket.sell_level` sólo con `screen.socket + popup.socket_sell`; este último exige dos lecturas y es la barrera destructiva `level == 0`. Como el chat puede cubrir temporalmente la única ubicación visual del timer, su extractor reintenta pasivamente hasta 10 frames frescos separados 0,5 s, siempre dentro del timeout/cancelación del caller y sin enviar input. El timer World Boss tiene límite confirmado de 90 s: una lectura mayor, como el outlier productivo `2479`, se rechaza y se reacquire en vez de iniciar una espera inválida.
- Temporal: `setting.auto_battle = ON/OFF/UNKNOWN`; sólo OFF inequívoco y contexto de batalla vigente autorizan toggle. Cada lectura busca 10 muestras frescas dentro de un budget bounded de 8 s y conserva una ventana de 9/10 al vencer el plazo; menos evidencia sigue sin autorizar input. El mínimo evita descartar una mediana ya clasificable sin volver a ampliar repetitivamente el timeout a medida que crece el costo de percepción.

`CharacterContext` conserva `name=None` y `name_confidence=None`: el índice de sesión no es identidad. Recursos, timer y otros valores cambiantes son Runtime Facts, no CharacterContext.

## Estado de validación

- Suite hardware-free: **1309/1309 tests verdes**.
- Corpus productivo ampliado: 400 frames únicos × 75 detectores, **30000/30000** pares, 400/400 resoluciones y overlays, cero wrong/ambiguous. La auditoría incremental posterior a la integración invalidó y reevaluó los 30.000 pares, incluidos los detectores Pet Combine contra el corpus histórico y todos los detectores productivos contra la evidencia nueva.
- Adquisición HIL Daily Quests: apertura desde Lobby, Claim All con desaparición de `Claim`, estado estable con `Start`/ads, segundo Claim All no-op, recompensa de progreso separada y cierre a Lobby confirmados live.
- Adquisición HIL Character Mail: Account Mail → Character Mail, Claim All con spinner/bubbles y transición `Claim → Delete`, quiescencia con Inbox aún 19, Delete Read Mail y cierre a Lobby confirmados live. Por límites de recompensa quedaron cinco mails reclamables; el estado residual se preserva como final válido y no dispara ninguna rutina para liberar espacio.
- Adquisición HIL Guild: shell estable, Attendance pendiente, transición a oscuro/completado, completado ya asentado, `Lobby → Quick Menu → Guild` y `Guild → Quick Menu` confirmados live; los targets, policy, normalización y flow consumen esa evidencia.
- Adquisición HIL Daily: Friends activo/inactivo, transición All, ausencia estable y Close→Lobby; Guild activo con Daily y completado sin Daily; World Boss activo/inactivo con otros badges aún visibles. La combinación Guild `Attendance activo + Daily ausente` no pudo reproducirse y queda como negativo pendiente.
- La adquisición HIL Pet Summon cubrió Manage con chat, Daily activa/ausente, Epic disponible/no disponible y su mensaje defensivo, Premium ticket/GOLD, los tres selectors, resultados Epic/Premium, GOLD insuficiente, Pet Full, cierres a Summon y `Yes → Pet Combine`. Todo input fue navegación humana; no se ejecutó flow ni relief.
- La adquisición HIL de Pet Combine cubrió Combine All con efecto/no-effect, runas Epic llenas desde dos ramas, candidatos Normal/Rare sin identidad, selección/cancelación, confirmaciones Mass Evolve con tier explícito, resultado compartido, aperturas Epic unitarias y el ciclo extremo que termina conceptualmente en `NO_RELIEF_AVAILABLE`. El relief incidental consume sólo Combine All; el resto de la evidencia perceptiva sigue curada y sin consumidor runtime.
- Black Market está validado en ramas de compra, no GOLD, Insufficient Gold, Inventory Full, verificación de Purchased y sesión completa previa 28/28.
- World Boss está validado hardware-free en sapphires insuficientes, Previous Rewards, batalla/Raid Complete, ramas positivas únicas y segundas ramas negativas para Socket/Equipment Full, y Rotation desde World Boss.
- Smoke HIL Enhance positivo: `Yes` llegó a Socket, GOLD produjo efecto, `TapThroughAnimation` ejecutó 6 taps guardados, Sell quedó `NOT_RUN` y `Back → World Boss` se verificó. La primera corrida expuso y luego corrigió un abort prematuro durante el frame transitorio World Boss sin popup.
- Smoke HIL No Material + venta: GOLD confirmó `NO_EFFECT`, Equipment Home seleccionó el slot rojo 3, OCR confirmó `Opal (Skill)+0` 2/2 con confidence `0.958` y el usuario autorizó Bulk sobre el popup visible. La venta dejó popup y candidato ausentes e inventario `1/29 → 1/28`; el primer frame limpio precedió al landmark estable, por lo que esa transición ahora tolera el tránsito pasivo sin habilitar retry. La entrada a Socket fue manual, así que correctamente no se ejecutó ni declaró `Back → World Boss`.
- La segunda aparición de Socket Full no se forzó live: el usuario confirmó que preparar ese caso extremo no era razonable. La policy queda cubierta hardware-free (`No`, fin no fatal, nunca segundo `Yes`) y los business events permiten auditarla si sucede en producción.
- La adquisición HIL de Equipment/Combine verificó efectos reales en orden Transmute (`178 → 158`), Ethereal (`158 → 148`) y Fuse (`148 → 123`), desaparición independiente de cada indicador y retorno `Back → World Boss`. La implementación consume exactamente ese contrato; no requirió un smoke adicional después de los tests.
- Un debug HIL posterior registró el tap físico `Combine All` en `(0.625622, 0.938166)` y confirmó el popup `Combine All - Identical`. El executor conserva el target táctil históricamente validado `(0.6073, 0.9297)`: usar el centro visual `(0.45, 0.92)` sobre el frame rotado abría `Awakened Transmute`.
- El landmark chat-safe resuelve los frames Socket live con confidence `1.0`; sus 12 positivos curados quedaron en `0.977370–1.0` frente a máximo de 159 negativos `0.713128`. Una captura legacy Meteorites con chat visible quedó como negativo explícito y dio raw `0.469354`.
- El landmark chat-safe de Battle Mode separa 17 positivos curados (`0.991948–0.999958`) de 154 negativos (máximo `0.390351`) y mantiene la ROI productiva fuera del chat.
- `StandardRotation` pasó un loop aislado 28/28 con retorno al personaje inicial.
- La composición `Black Market → World Boss → Rotation` y la GUI productiva están validadas.
- Primer checkpoint combinado desde GUI: sesión `COMPLETED`, 28/28 personajes, 28 advances, 28 ejecuciones de cada flow y cero fallos técnicos. El detalle auditable está en `docs/HISTORY.md`.
- La fase de debug productiva posterior cerró otra sesión completa `COMPLETED` 28/28 con el runtime actual, después de endurecer World Boss, Equipment Combine, Daily Quests y Mailbox a partir de fallos reales observados.

## Deuda y limitaciones relevantes

- Adquirir y diseñar recovery bounded para el popup de conexión post-batalla de World Boss.
- Sólo World Boss tiene return plan adquirido para `EquipmentCombineRelief`; otros callers requieren evidencia live específica antes de integrarse.
- No existe `CharacterContextProvider` ni OCR de nombre. Tampoco costo/rank/participation, Auto Repeat o scheduler.
- `ConflictResolver`, recovery transversal e isolation/continuation unattended siguen futuros. Los retries locales verificados no se trasladan a esa capa.
- Timings y retries pueden seguir ajustándose sólo a partir de logs productivos; no hay necesidad de tuning preventivo.
- Falta validar live `Attendance activo + Daily ausente` antes de usar ausencia de Daily como guard definitivo de Guild; el detector visual y la independencia de reglas están cubiertos, pero esa combinación no tiene ground truth físico.
- Pet Summon/Pet Combine sólo tiene evidencia de una temporada/render. La disponibilidad Epic depende del render del juego y tolera costos promocionales, pero no se leyó cantidad. Low-tier, Mass Evolve y aperturas Epic conservan semántica y evidencia perceptiva, pero ya no pertenecen al relief incidental y requerirán diseño propio antes de tener un consumidor runtime. El soft block extremo no tiene resolución general.
- `main.py` y módulos legacy preservados no son entrypoints productivos. `AdsManager` continúa standalone y desacoplado.

## Próximo trabajo

`SummonPetDailyFlow` y el relief incidental de un solo Combine All están integrados; no se avanza a Arena todavía. El mantenimiento general de Pets permanece fuera de alcance.
