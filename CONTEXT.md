# Contexto actual — Kritika FarmBot 0.2

## Estado canónico

El código productivo vigente proviene del checkpoint estable:

```text
71340f58d3a4515facc346ad22addfc0d814a6ec
feat: add monster wave skip activity
```

La rama `rebuild/stable-baseline` preserva ese origen y contiene Rotation R1/R2-A (`d7742fd`; `codex/rotation-r2` apunta al mismo checkpoint), Quick Menu verified-origin y Clean Lobby/B2. R2-B (Select→Lobby) usa el contrato B2 resolver-complete. No porta código de la línea experimental Inventory Relief. La evidencia Git prevalece sobre referencias históricas que describían Monster Wave como «sin commit» o «sin push».

### Checkpoint V1 (canónico vigente)

- Rama `rebuild/stable-baseline` @ `04640c2`; último cambio productivo `6ba5c9b`.
- `REFACTOR_COMPLETE = YES`: auditoría global final cerrada ([`docs/FINAL_GLOBAL_PERCEPTION_AUDIT.md`](docs/FINAL_GLOBAL_PERCEPTION_AUDIT.md)); 0 K, 0 D-local y 0 BUG abiertos.
- Validación: **2459/2459 hardware-free**; **28/28 post-refactor PASS** ([`docs/POST_REFACTOR_28_28_BENCHMARK.md`](docs/POST_REFACTOR_28_28_BENCHMARK.md)): wall **76:59**, 196/196 flows, 768/768 transitions, 1 retry bounded, 0 recoveries, 0 failures.
- Performance (sintético, comparación descriptiva vs sesión comparable 2026-09-08): perception CPU 4026.8 s → **2337.8 s (−42 %)**; analyzes global-like 5705 → 3016 (~−47 %); flows scoped principales −45–56 % wall. No todo el ahorro wall es atribuible al refactor (el workload difiere: reliefs, retries, batallas WB).
- Caveats del benchmark: Monster Wave OFF (path omitido, no valida MW); 0 reliefs con trabajo (no valida reliefs); scopes nuevos de Daily-progress 95→4 y MW-eligibility 95→5 no ejercidos; World Boss ampliamente ejercido (28 flows / 26 batallas).
- Veredictos: `PERFORMANCE_REGRESSION = NO`, `NEW_CORRECTNESS_BUG = NO`, `HIGH_VALUE_OPTIMIZATION_REMAINING = NO`.
- `READY_FOR_V1_CHECKPOINT = YES`.

Kritika FarmBot automatiza tareas por personaje de **Kritika: The White Knights** sobre Android físico. GUI Tkinter y CLI son frontends del mismo composition root. Código y tests determinan lo implementado; [`ARCHITECTURE.md`](ARCHITECTURE.md) fija contratos, [`ROADMAP.md`](ROADMAP.md) ordena el trabajo y [`docs/HISTORY.md`](docs/HISTORY.md) conserva la evolución.

## Runtime productivo

```text
Capture
  → Perception / Runtime Facts
  → ContextResolver
  → Flow / Support Operation / SessionRunner / Rotation
  → operación semántica verificada
  → ActionExecutor
  → AdbClient
```

- `ScrcpyFrameSource` posee captura y cleanup.
- `PerceptionEngine` emite observaciones; `ContextResolver` resuelve estado y overlays.
- `RuntimeObserver` mantiene frame, observaciones, facts y geometría coherentes, con esperas frescas, bounded y cancelables.
- `RuntimeFactReader` obtiene OCR demand-driven; `TemporalObserver` cubre facts multiframe.
- Los flows contienen policy de negocio. `ActionExecutor` proyecta intents según `frame.shape`; `AdbClient` es el único límite ADB.
- Toda acción con efecto observable exige postcondición. Un retry requiere estado fresco que autorice exactamente repetir; `UNKNOWN` nunca autoriza input.

## Capacidades actuales

El registry productivo ejecuta, en orden configurable:

1. Black Market
2. World Boss
3. Monster Wave
4. Send Stamina
5. Summon Pet Daily
6. Daily Quests
7. Mailbox
8. Guild Check-In

La GUI permite habilitar, deshabilitar y reordenar esos flows. `SessionRunner` los compone por personaje; `StandardRotation` recorre la rotación mediante sentinel; Character Identity y Eligibility aportan contexto y skips estructurados. Structured Observability, Failure Evidence y SessionReport exponen resultados sin trasladar policy a la UI.

### Límites por capacidad

- **Black Market:** procesa sólo ofertas GOLD, con compra y outcomes verificados; nunca compra con KARATS.
- **World Boss:** hace precheck de sapphires, usa `BattleModeZone` y activa Auto Battle sólo desde OFF confirmado. Puede intentar una vez Socket Relief y una vez Equipment Combine Relief; una segunda obstrucción se cierra de forma conservadora.
- **Monster Wave:** procesa una sola operación SKIP en MAX por llamada. La compra de tickets y el board son configurables; no incluye Start manual, Auto Battle, countdown ni farming loop.
- **Monster Wave board G (post-V1):** reader demand-driven y snapshot descriptivo puros, fuera de la orquestación MW. El popup muestra cinco pares `balance/límite mostrado` por identidad y orden: Brawler's Badges, Weapon Material, Hero Weapon Material, Bronze Key y Silver Key. Dos lecturas OCR iguales y frescas producen un fact; el snapshot exige contexto/popup coherentes y barrera de secuencia. Gold-key capacity, reward quantities, recetas y necesidades de materiales no se derivan del board.
- **Resource Route Planner I2 + executor J2 (post-V1):** `plan_resource_route` usa balances actuales y umbrales inclusivos Bronze 400, Silver 450, Weapon 800 y Hero 800. El umbral decide entrada; Craft, Trading y Keys drenan con facts frescos y presupuestos, nunca hasta el umbral. Materials paga Keys primero aun bajo umbral; Keys solo no paga General. Craft+Materials usa `MW→Craft→Trading modal→Craft→MW`. Gold-full se reconoce con OK verificado, conserva el pending y difiere Treasure hasta MW después del trabajo ya pagado. Unknown/contradictory no emiten input; `NO_PREREQUISITES` devuelve el snapshot corriente. Sin reward prediction, replan, relief de Equipment/Socket ni wiring L.
- **Send Stamina:** un único All autorizado por Daily visible y desaparición fresca.
- **Summon Pet Daily:** apertura diaria acotada; Pet relief incidental admite un solo Combine All verificable.
- **Daily Quests, Mailbox y Guild:** acciones single-attempt o no-op con cierre verificable; Mailbox no libera recursos.
- **Equipment Sell standalone (post-V1):** capacidad bulk-only fuera del registry productivo. Parte de Equipment Inventory ya abierto, exige Item Count y detalle por consenso, autorización explícita de tipo/grado/Enhance/grupo, confirma una sola vez y sólo declara éxito con Item Count fresco menor. Poor–Legendary separan grupos Equipment/Enhance; Ethereal usa tipo exacto; Ethereal+ y candidatos accesorios/unknown están protegidos. No navega, no escanea ni expande con Karats.
- **Equipment Relief composer (post-V1):** composición transversal pura, todavía sin caller productivo: intenta el request opaco del caller; sólo ante Equipment Full ejecuta Combine una vez, readquiere contexto/facts posteriores y reintenta exactamente el mismo request una vez; sólo si el retry sigue Equipment Full admite un `EquipmentSellRequest` explícito con autorización+candidato y ruta caller-specific, ejecuta Sell una vez, exige Item Count menor, readquiere otra vez y hace el último retry. Un tercer Equipment Full falla cerrado. No hay scan, recursion, segundo Combine, segundo Sell ni retry destructivo.
- **Craft standalone (post-V1):** entrada verificada con ≥1 slot Equipment libre; cada operación Hero `ONE`/`MAX_AVAILABLE` conserva sus guards de receta, coste, no premium y decremento exacto. I2/J2 añaden un composer Hero-only con batches `MAX_AVAILABLE` frescos hasta <49, presupuesto explícito y sin nuevo check de slots durante el mismo contexto Craft. Quick Menu queda accesible directamente desde Craft; no invoca Equipment Relief.
- **Rotation y sesión:** ejecución multi-flow/multicharacter, cancelación, eventos, reporte y selección desde GUI/CLI.

## Validación vigente

- I2/J2 2026-09-23: **332/332 regresiones dirigidas** (planner, Craft, Trading C4/C5/materials, C6a/C6b, J/K, G snapshot, Quick Menu/navigation). HIL mínimo de Gold-full: un OK humano cerró el aviso y dejó Trading/Keys limpio; raw ignorado en `artifacts/hil_i2_j2_gold_full/20260923/`. Sin evaluator ni full suite: no cambió percepción ni infraestructura productiva compartida.

- Checkpoint anterior a Rotation R1: **2129/2129 tests hardware-free** (`f4be77a`).
- Rotation R1: **2144/2144 tests hardware-free**; smoke HIL natural **1/1**, con tarjeta `SELECTED` estable, `Select` final y Lobby confirmado por la persona usuaria.
- Rotation R2-A: **2151/2151 tests hardware-free**; smoke HIL natural **1/1**, wait post-swipe scoped 95→2 con `stable_for=1.0`, 1 swipe, tarjeta y Select en primer intento, Lobby confirmado visualmente por la persona usuaria. R2-B quedó global por cobertura insuficiente de overlays en un subset pequeño.
- World Boss WB-1: **2152/2152 tests hardware-free**; `Run Session` natural **1/1** tras el cambio, con elegibilidad 95→5, wait estable 2,61→0,91 s, 0 retries/recoveries y World Boss completado. Detector/asset/ROI/OCR y semántica de batalla intactos; Start, boundaries de inventario y retorno siguen globales por contrato abierto de abort/overlays.
- Quick Menu verified-origin handoff: **2231/2231 tests hardware-free**; action-source lineage y recovery invalidation explícitos; consumers principales migrados sin cambios de hitboxes/detectores. R2-C y waits con vocabulario de contradicción permanecen globales.
- Clean Lobby/B2: **2364/2364 tests hardware-free** y **398/398 regresión dirigida**. CloseFriends, Mailbox, Daily, Black Market, ClosePets, `select_lobby`, BattleModeZone.leave y R2-B acotan sólo el wait final 95→77. Los scopes preservan todas las dependencias de las 17 bases y 57 overlays; benchmark sobre cinco frames reales: 657.53 ms/frame global frente a 411.73–423.54 ms/frame scoped. No cambió detector, ROI, asset ni calibración.
- World Boss correctness: Select Boss y Previous Rewards usan handoffs locales derivados de `action_source_snapshot`; los overlays `UNKNOWN` sólo autorizan el siguiente input si son frescos y causados por el input verificado anterior. Discovery aislado, `AMBIGUOUS`, base foreign, overlay contradictorio y recovery no autorizan input; Ack y Continue son single-attempt. Raid Complete conserva base resuelta, anchor causal, stale rejection y terminal contradictorio. Regresión dirigida **282/282**, incluidas las 44 capturas curadas. HIL natural validó Select Boss, Previous Rewards, Ack, Start, Raid Complete y Continue en primer intento, con 0 retries/recoveries y GT humano sin taps incorrectos. El tap final llegó físicamente a Lobby, pero `BattleModeZone.leave` reportó `FAILED` al abortar sobre un frame transitorio del origin antes de observar el destino. Fix local posterior (`cf82d62` + `tolerate battle mode during lobby return`): el origin todavía visible post-`SelectQuickMenuLobby` se tolera mientras se espera (sin abort, sin retry, sin segundo tap); HIL natural 1/1 con `select_lobby` en primer intento y full hardware-free **2394/2394**, nuevo count autoritativo.
- Evaluación semántica de Monster Wave: **510 frames**, sin resoluciones wrong/ambiguous.
- Evidencia live histórica: Rotation 28/28 y sesiones combinadas 28/28 sin fallos técnicos; Monster Wave confirmó ACTIVE, MAX, Start y board negativo.
- Cierre refactor + auditoría global final: **2459/2459 hardware-free** (`6ba5c9b`, `04640c2`; nuevo count autoritativo); `REFACTOR_COMPLETE = YES`, 0 K/D-local/BUG.
- Post-refactor 28/28 PASS: wall 76:59, 196/196 flows, 768/768 transitions, 1 retry bounded, 0 recoveries/failures; percepción 2337.8 s (−42 % vs baseline comparable). Caveats: MW OFF, sin reliefs con trabajo, scopes nuevos de Daily-progress/MW no ejercidos. Detalle en [`docs/POST_REFACTOR_28_28_BENCHMARK.md`](docs/POST_REFACTOR_28_28_BENCHMARK.md).
- Equipment Sell standalone 2026-09-22: **284 tests dirigidos** (policy/operation/runtime/ActionExecutor/Combine regression), evaluator incremental **12/12**, HIL destructivo autorizado exactamente una vez: `Laoku's Fatal Armor`, Epic Chest no-Enhance, popup `equipment_grade`, un `Sell (Bulk)`, Item Count **120→114**. La lectura inmediata agotó cuatro frames durante la transición y falló cerrada; una observación pasiva posterior probó el efecto. El bound se separó a 48 frames dentro de 4 s, con test de animación tardía y sin retry/input adicional.
- Equipment Relief composer 2026-09-22: **25 tests directos** y **159/159** en la regresión Combine+Sell afectada. Prueba request causal por identidad, contexts estrictamente posteriores a las barreras de retorno, bounds 1 Combine/1 Sell/1 retry tras cada uno, ausencia de Sell sin plan autorizado y cero retry tras Sell no probado. Sin evaluator, full suite ni HIL: no cambió percepción/acción/ruta física ni se conectó un caller.
- Craft standalone 2026-09-22: **211 tests afectados** (Craft operation/runtime/ActionExecutor + Quick Menu), evaluator incremental **13/13** y HIL productivo con aprobación: Equipment Inventory **111/112**, Quick Menu→Craft, Hero Weapon `49`, `1/10`, `Laoku's Destructive Sword`, material **325→276**, cierre de resultado por lateral negro seguro `(0.20,0.50)` y Quick Menu abierto otra vez directamente desde Craft. Karats **33,794** sin cambios; frontera separada `Need 3 material → 15 Karats` fue rechazada por `No`.
- MW board G 2026-09-22: GT humano sobre tres frames scrcpy actuales: Brawler's Badges `258/72`, Weapon Material `412/999`, Hero Weapon Material `284/999`, Bronze Key `322/499`, Silver Key `129/499`. Evaluator incremental board **7/7** con negativos clean MW, retorno histórico tras `No`, Socket Full y foreign; **16 tests nuevos**, **129 regresiones MW/percepción/eligibilidad** y gate contextual sobre los **97 frames** MW históricos. Sin input, consumo ni cambio de comportamiento MW.
- Resource Route Planner I-impl 2026-09-22: **15 tests directos** y **31/31** junto con la regresión del snapshot G. Modelos frozen/hashable, reasons/evidence tipados, stale/foreign/contradictory sin pasos, casos no-op/Keys/material/Craft-first/Keys+materials y separación estática de runtimes/input físico. Sin evaluator, full suite ni HIL: no cambió percepción, infraestructura compartida, executor ni integración MW.
- Resource Route Executor J 2026-09-23: **631/631 regresiones afectadas** (J, C6b/C6a/C5/C4, materials/rows/scroll, Trading, Craft, Treasure, Quick Menu, ActionExecutor y snapshot MW). La suite hardware-free amplia llegó a **3178 passed / 4 failed** únicamente porque faltan cuatro directorios locales ignorados `artifacts/failure_evidence/*`; los cuatro fallos son `FileNotFoundError` del fixture de Rotation y no tocan J. Sin evaluator: no cambió percepción, OCR, ROI, detector ni asset. Sin HIL nuevo: todas las transiciones físicas usadas proceden del audit `artifacts/hil_j_navigation/20260922/`.
- K standalone 2026-09-23: `bot/monster_wave_standalone.py` compone G→I→J→MW con modos acquire/plan/prerequisites/full-one-shot, `NonBoardResourceFacts` caller-supplied y límites planner/J/MW 1/1/1. HIL nuevo: `ExitMonsterWave` desde MW limpio `needs_tickets` seq 116 → Battle Mode Select resuelto seq 187, un intento y cero SKIP. 23 tests K y 316 regresiones afectadas verdes. No evaluator ni suite amplia: no cambió percepción ni wiring productivo. Smokes K A/B no ejercidos porque el board no estaba abierto y no se fabricó un intento.

Estas cifras describen el checkpoint, no autorizan repetir suites ni hardware en tareas docs-only. Los detalles de adquisición y calibración viven en [`docs/HISTORY.md`](docs/HISTORY.md).

## Decisiones cerradas

- Perception observa; no navega ni decide gameplay.
- `ContextResolver` resuelve observaciones; no captura ni ejecuta.
- Flows expresan intención; no hacen matching ni llaman ADB.
- Rotation es transversal y no pertenece a un flow.
- Geometría portable deriva del frame; no se fijan resoluciones ni device IDs.
- La persona usuaria sigue siendo el planner. El producto ejecuta una lista explícita de flows y policies acotadas; no existe un planner automático general.
- El experimento Inventory Relief se preserva como evidencia y código archival, no como arquitectura aceptada.
- Quick Menu usa verified-origin handoff local: overlay visible y origin autorizado son hechos distintos. Un UNKNOWN con menú descubierto no habilita tile input/retry; UNKNOWN post-open sólo lo hace con source de input verificado, menú fresco y sin contradicción. Recovery invalida el handoff antes de retry. Véase [`ARCHITECTURE.md`](ARCHITECTURE.md) y [`docs/QUICK_MENU_HANDOFF_DECISION.md`](docs/QUICK_MENU_HANDOFF_DECISION.md).
- Clean Lobby separa uso, no significado: discovery/recovery/postchecks permanecen globales; transiciones conocidas usan observación resolver-complete 95→77 con source/action/freshness en el caller. `Trading Center` sigue siendo la única señal positiva y está clasificada seasonal-risk. Véase [`docs/CLEAN_LOBBY_B2_DECISION.md`](docs/CLEAN_LOBBY_B2_DECISION.md).

## Limitaciones conocidas

No forman parte del runtime estable:

- Inventory Relief Chain general y adapters de caller. Craft standalone existe, pero no consume el compositor transversal; una integración futura debe aportar reconocimiento Equipment Full, ruta verificada a Combine/Inventory y retorno fresco. Sell exige un `EquipmentSellRequest` caller-supplied con autorización+candidato explícitos;
- Trading Center: C6a usa facts frescos y presupuesto hasta `NO_MORE_PROMOTIONS`. C6b preserva `PendingCausalOperation` ante `SILVER_TO_GOLD + OUTPUT_FULL`; el OK requiere alert C4 fresco y postestado Trading/Keys limpio. J puede diferir Treasure hasta volver a MW, drenar todos los Gold y reintentar el pending exacto una vez. Un segundo `OUTPUT_FULL` falla cerrado; no hay estimación de capacidad Gold, `UP_TO(n)`, Equipment Relief ni scroll de Keys;
- E2 Treasure (post-V1, hot-context): runtime autónomo + fast Gold drain cerrados físicamente de punta a punta. HIL productivo 2026-09-21: Gold Keys 27→0, frontera Karat fresca, premium intacto y Treasure estable. C6b lo compone sin añadir policy a Treasure. HIL directo 2026-09-22: Treasure abrió Quick Menu con el header compartido y el nuevo target `(0.332,0.650)` abrió `screen.trading` fresco (confianza 1.000), sin Lobby intermedio, gasto ni trade;
- Regla de routing: Trading abierto desde Quick Menu es modal; su X restaura Craft cuando Craft lo abrió. Treasure sí navega de contexto y su Back conserva sólo el origen inmediato. J usa `MW→Craft→Trading→X→Craft→Back→MW` si Materials justifica Trading; Craft+Keys sin Materials vuelve primero a MW y abre Trading sólo para Keys. Gold-full causal diferido usa `MW→Treasure→Back→MW→Trading` para retry único. No hay reconstrucción de MW desde Lobby;
- Optimización aceptada: sin umbral de Keys ni Materials, Trading no se abre para diagnosticar Gold; Gold-full puede permanecer oculto porque por sí solo no bloquea MW. El color rojo al llegar o superar el límite UI queda como futuro fast-path perceptivo separado de I2/J2;
- R2-C (Quick Menu→Character Select) conserva observación global porque el subset actual de dos detectores no muestra bases contradictorias bajo el menú;
- no existe aún una señal positiva estructural y multitemporada de Lobby; scopes menores por consumer y reuse D quedan diferidos hasta obtener evidencia física o un carry explícito de snapshot;
- World Boss: el handoff causal restauró y validó físicamente Select Boss y Previous Rewards sin autorización overlay-only. El falso abort downstream de `BattleModeZone.leave` quedó corregido con un predicate local que tolera el origin transitorio post-`SelectQuickMenuLobby`; foreign, `UNKNOWN`/`AMBIGUOUS` y clean Lobby intactos. Los D locales requieren un snapshot fresco equivalente antes de reutilizarse;
- framework temporal de input/readiness;
- estrategia de farming, scheduler, grafo general de navegación o recuperación de conexión post-World Boss;
- Tower y Arena.

Los raws y curados experimentales se conservan físicamente. Su eventual reutilización debe partir de la causa observada y portar sólo conocimiento demostrado, no la arquitectura experimental completa.

## Siguiente paso

K permanece standalone/debug. L0-A entrega un board causal opt-in; el default mantiene Yes/No y la sesión se detiene cerrada si el handoff no tiene consumidor. I2 ya no exige rewards entrantes exactos: los drops probabilísticos no intervienen en la ruta. L stage-ready no se inició; faltan facts productivos frescos de capacidad Craft y composición del caller, además del HIL específico del handoff L0.
El smoke L0 autorizado sólo ejerció la rama `NEEDS_TICKETS` con compra desactivada: Open MW y Exit first-attempt, cero Start/Yes/No, retorno Battle Mode Select. El board no apareció naturalmente; el yield físico sigue `NEEDS_HIL`.
L0 offline: 158 tests dirigidos verdes; full hardware-free 3211 passed / 4 Rotation fixture `FileNotFoundError` idénticos al baseline J (`KNOWN_ENVIRONMENTAL_FIXTURE_GAP`), cero fallos nuevos. Sin evaluator por no tocar percepción.
