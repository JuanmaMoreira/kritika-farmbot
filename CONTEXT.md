# Contexto actual — Kritika FarmBot 0.2

## Estado canónico

El código productivo vigente proviene del checkpoint estable:

```text
71340f58d3a4515facc346ad22addfc0d814a6ec
feat: add monster wave skip activity
```

La rama `rebuild/stable-baseline` preserva ese origen y añadió Rotation R1: percepción acotada únicamente en la verificación de `select_predecessor_character`. Rotation R2-A, en `codex/rotation-r2`, reutiliza el mismo subset para el wait post-swipe de Character Select; R2-B (Select→Lobby) sigue global. No porta código de la línea experimental Inventory Relief. La evidencia Git prevalece sobre referencias históricas que describían Monster Wave como «sin commit» o «sin push».

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

## Limitaciones conocidas

No forman parte del runtime estable:

- Inventory Relief Chain general, Trading, Craft, Treasure o Equipment Sell;
- confirmación Select→Lobby y otros hot paths de Rotation aún no scopeados por R1/R2-A;
- framework temporal de input/readiness;
- estrategia de farming, scheduler, grafo general de navegación o recuperación de conexión post-World Boss;
- Tower y Arena.

Los raws y curados experimentales se conservan físicamente. Su eventual reutilización debe partir de la causa observada y portar sólo conocimiento demostrado, no la arquitectura experimental completa.

## Siguiente paso

Rotation R2-A quedó validada con el wait post-swipe scoped; confirmación a Lobby y recovery permanecen globales. La extensión de Lobby requiere evidencia independiente de overlays y temporada; no iniciar B2 dentro de R2, según [`ROADMAP.md`](ROADMAP.md).
