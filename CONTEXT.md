# Contexto actual — Kritika FarmBot 0.2

## Estado canónico

El código productivo vigente proviene del checkpoint estable:

```text
71340f58d3a4515facc346ad22addfc0d814a6ec
feat: add monster wave skip activity
```

La rama `rebuild/stable-baseline` preserva ese origen y contiene Rotation R1/R2-A (`d7742fd`; `codex/rotation-r2` apunta al mismo checkpoint), Quick Menu verified-origin y Clean Lobby/B2. R2-B (Select→Lobby) usa el contrato B2 resolver-complete. No porta código de la línea experimental Inventory Relief. La evidencia Git prevalece sobre referencias históricas que describían Monster Wave como «sin commit» o «sin push».

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
- **Send Stamina:** un único All autorizado por Daily visible y desaparición fresca.
- **Summon Pet Daily:** apertura diaria acotada; Pet relief incidental admite un solo Combine All verificable.
- **Daily Quests, Mailbox y Guild:** acciones single-attempt o no-op con cierre verificable; Mailbox no libera recursos.
- **Rotation y sesión:** ejecución multi-flow/multicharacter, cancelación, eventos, reporte y selección desde GUI/CLI.

## Validación vigente

- Checkpoint anterior a Rotation R1: **2129/2129 tests hardware-free** (`f4be77a`).
- Rotation R1: **2144/2144 tests hardware-free**; smoke HIL natural **1/1**, con tarjeta `SELECTED` estable, `Select` final y Lobby confirmado por la persona usuaria.
- Rotation R2-A: **2151/2151 tests hardware-free**; smoke HIL natural **1/1**, wait post-swipe scoped 95→2 con `stable_for=1.0`, 1 swipe, tarjeta y Select en primer intento, Lobby confirmado visualmente por la persona usuaria. R2-B quedó global por cobertura insuficiente de overlays en un subset pequeño.
- World Boss WB-1: **2152/2152 tests hardware-free**; `Run Session` natural **1/1** tras el cambio, con elegibilidad 95→5, wait estable 2,61→0,91 s, 0 retries/recoveries y World Boss completado. Detector/asset/ROI/OCR y semántica de batalla intactos; Start, boundaries de inventario y retorno siguen globales por contrato abierto de abort/overlays.
- Quick Menu verified-origin handoff: **2231/2231 tests hardware-free**; action-source lineage y recovery invalidation explícitos; consumers principales migrados sin cambios de hitboxes/detectores. R2-C y waits con vocabulario de contradicción permanecen globales.
- Clean Lobby/B2: **2364/2364 tests hardware-free** y **398/398 regresión dirigida**. CloseFriends, Mailbox, Daily, Black Market, ClosePets, `select_lobby`, BattleModeZone.leave y R2-B acotan sólo el wait final 95→77. Los scopes preservan todas las dependencias de las 17 bases y 57 overlays; benchmark sobre cinco frames reales: 657.53 ms/frame global frente a 411.73–423.54 ms/frame scoped. No cambió detector, ROI, asset ni calibración.
- World Boss correctness: Select Boss y Previous Rewards usan handoffs locales derivados de `action_source_snapshot`; los overlays `UNKNOWN` sólo autorizan el siguiente input si son frescos y causados por el input verificado anterior. Discovery aislado, `AMBIGUOUS`, base foreign, overlay contradictorio y recovery no autorizan input; Ack y Continue son single-attempt. Raid Complete conserva base resuelta, anchor causal, stale rejection y terminal contradictorio. Regresión dirigida **282/282**, incluidas las 44 capturas curadas. HIL natural validó Select Boss, Previous Rewards, Ack, Start, Raid Complete y Continue en primer intento, con 0 retries/recoveries y GT humano sin taps incorrectos. El tap final llegó físicamente a Lobby, pero `BattleModeZone.leave` reportó `FAILED` al abortar sobre un frame transitorio del origin antes de observar el destino; por esa contradicción downstream no se ejecutó la full hardware-free.
- Evaluación semántica de Monster Wave: **510 frames**, sin resoluciones wrong/ambiguous.
- Evidencia live histórica: Rotation 28/28 y sesiones combinadas 28/28 sin fallos técnicos; Monster Wave confirmó ACTIVE, MAX, Start y board negativo.

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

- Inventory Relief Chain general, Trading, Craft, Treasure o Equipment Sell;
- R2-C (Quick Menu→Character Select) conserva observación global porque el subset actual de dos detectores no muestra bases contradictorias bajo el menú;
- no existe aún una señal positiva estructural y multitemporada de Lobby; scopes menores por consumer y reuse D quedan diferidos hasta obtener evidencia física o un carry explícito de snapshot;
- World Boss: el handoff causal restauró y validó físicamente Select Boss y Previous Rewards sin autorización overlay-only. El cierre integral permanece bloqueado por un falso abort downstream de `BattleModeZone.leave`: tras `SelectQuickMenuLobby`, `screen.battle_mode_select + status.monster_wave_daily_active` se considera contradictorio aunque el dispositivo llegue enseguida a Lobby. Los D locales requieren un snapshot fresco equivalente antes de reutilizarse;
- framework temporal de input/readiness;
- estrategia de farming, scheduler, grafo general de navegación o recuperación de conexión post-World Boss;
- Tower y Arena.

Los raws y curados experimentales se conservan físicamente. Su eventual reutilización debe partir de la causa observada y portar sólo conocimiento demostrado, no la arquitectura experimental completa.

## Siguiente paso

Select Boss/Previous Rewards correctness queda cerrado en código y HIL. Antes de la única full hardware-free y del cierre integral debe decidirse por separado el falso abort de `BattleModeZone.leave`; no mezclar ese fix de Quick Menu/B2 con provenance WB ni iniciar performance/scoping.

Un smoke HIL breve es opcional si se solicita evidencia temporal/física de R2-B o de un close concreto; no es requisito para el cambio resolver-equivalente 95→77. No recalibrar `screen.lobby` sin adquisición seasonal específica.
