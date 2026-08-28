# Roadmap — Kritika FarmBot 0.2

## Estado

El primer vertical slice de runtime está cerrado. `BlackMarketFlow` cubre `low_gold + inventory_full` como resultados de negocio no fatales, `rotation.standard` quedó validada en un ciclo live 28/28 y la composición de sesión completó el smoke productivo 28/28 con retorno humano-confirmado al personaje inicial.

## Completado

- [x] Fase 0 — auditoría, baseline, preservación legacy y reorganización inicial.
- [x] Fase 1 — configuración, geometría por frame, `AdbClient`, captura scrcpy, composition root y tools reutilizables.
- [x] Fase 2 — observations, estado, resolver determinista, catálogo mínimo y validación offline.
- [x] Fase 3 — Perception local, adquisición y Workbench, repair/revalidación live, Quick Menu, GOLD e Insufficient Gold.
- [x] Fase 4 — semantic actions, `ActionExecutor` y `BlackMarketFlow` single-character `Lobby → Black Market → Lobby`, validado live con 460 tests hardware-free.
- [x] Extensión Black Market — `popup.inventory_full`, `OK` verificado y continuación al siguiente GOLD sin identificar ni gestionar inventarios.
- [x] Maintenance — hot context compactado, historia separada, entorno local persistente y bootstrap/status para agentes.

La cronología de subfases y evidencia está en [`docs/HISTORY.md`](docs/HISTORY.md).

## Activo / siguiente

### Rotation — cerrada aisladamente

- [x] Definir `RotationStrategy` como responsabilidad transversal.
- [x] Implementar y validar aisladamente un `StandardRotation.advance()` con `character_count = 28` configurable.
- [x] Navegar un cambio Quick Menu → Character Select → scroll al final → última posición → Lobby.
- [x] Endurecer bottom con frames A/T/B, movimiento efectivo y bounce validado sobre ROI de la grilla.
- [x] Extraer A/T/B y scroll-to-edge a una primitive transversal reusable sobre `RuntimeObserver + ActionExecutor`.
- [x] Incorporar transición discreta verificada con grace sin input y retry protegido por estado.
- [x] Calibrar thresholds y gesto en 5/5 entradas scroll-only, sin seleccionar personajes.
- [x] Validar el perfil 1+1 y reservar un tercer swipe sólo cuando el segundo todavía muestre progreso.
- [x] Validar tres `advance()` supervisados con bottom confirmado antes de seleccionar y retorno a Lobby.
- [x] Aprovechar el orden MRU sin identificar personajes y sin lógica especial MAIN/SUBS.
- [x] Validar hardware-free primero y mantener todo smoke físico explícitamente opt-in.
- [x] Validar live la transición discreta en 3 advances supervisados, sin regresión de scroll ni navegación.
- [x] Calibrar y verificar hardware-free la postcondición visual de selección de la última tarjeta, con grace y retry state-guarded.
- [x] Validar la selección observada en 5/5 entradas aisladas y 3/3 `advance()` supervisados.
- [x] Completar el loop live 28/28 y validar humanamente el regreso final al personaje inicial sin repetir flows sobre éste.

### Composición mínima de sesión

- [x] Implementar `SessionPlan / SessionRunner → Selected PER_CHARACTER Flow(s) + RotationStrategy`.
- [x] Definir `FlowResult / FlowEvent`, resultados parciales, cancelación segura y abort conservador ante fallos técnicos.
- [x] Mantener flows, Rotation y ADB separados; componer según precondiciones y postcondiciones explícitas sin exigir Lobby universal.
- [x] Preparar `CharacterContext(name=None)` para identidad futura sin implementar OCR.
- [x] Validar live N=2: 2/2 flows, 2/2 advances y Lobby estable entre componentes; smokes incrementales acumularon tres `inventory_full` no fatales.
- [x] Validar la sesión Black Market completa de 28 personajes sin reprocesar al inicial tras el advance final: 28/28 flows, 28/28 advances, business events no fatales, Lobby final y retorno al inicial confirmado humanamente.

### Prerrequisitos transversales para nuevos flows

- [x] Declarar contratos de flow con precondición y múltiples postcondiciones exitosas posibles; `COMPLETED` ya no implica Lobby.
- [x] Modelar `quick_menu_accessible` como capability conservadora y Quick Menu como hub operacional, sin pantalla sintética ni grafo de navegación.
- [x] Componer el próximo componente según su requisito real y reservar Quick Menu → Lobby como única normalización mínima inyectable/verificada.
- [x] Declarar `StandardRotation` sobre acceso a Quick Menu conservando Lobby como única entrada productiva validada.
- [x] Incorporar `ControlledWait` monotónico, periódico, cancelable y bounded para actividad larga sin input.
- [x] Fijar boundaries futuros OCR → extractors → Runtime Facts y VerifiedTransition → failure estructurado → ConflictResolver.

## Siguiente

### World Boss semantic acquisition / perception slice — cerrado

- [x] Promover semántica sólo ante una necesidad funcional y evidencia curada.
- [x] Adquirir y validar live Battle Mode Select, Select Boss, Previous Rewards, World Boss, batalla y Raid Complete, con múltiples frames human-confirmed y sin inferir GT desde taps.
- [x] Promover seis landmarks CV y resolver 44/44 frames del slice sin errores ni ambigüedad; cerrar la regresión productiva conjunta 146/146 y 0 FP/FN por detector.
- [x] Preservar ROIs candidates para facts futuros y evidencia temporal OFF/ON sin implementar OCR, parsers ni detector de Auto Battle.
- [x] Validar live `screen.world_boss` como `quick_menu_accessible`, abrir/cerrar el overlay y restaurar la base antes de ampliar la policy productiva.

### OCR + first Runtime Facts — cerrado

- [x] Implementar `OcrEngine → OcrResult → extractor/parser → RuntimeFact` con RapidOCR/ONNX local, lazy y reusable.
- [x] Exponer adquisición bounded fresca y context-correct mediante `RuntimeFactReader`, con consenso/retry y outcomes explícitos.
- [x] Productivizar `resource.sapphires` y `battle.timer_remaining` con evidencia live human-confirmed; corregir mediante HIL el ROI inicial que apuntaba a melee tickets.
- [ ] Evaluar detector entrenado o fallback VLM provider-agnostic sólo cuando un caso no cubierto y evidencia suficiente lo justifiquen.

### Auto Battle temporal

- [x] Detectar `setting.auto_battle = ON/OFF/UNKNOWN` mediante una ventana fresca de 10 frames y variación robusta del borde del glow, con zona insegura explícita.
- [x] Validar live detección OFF/ON con 0 FP/FN sobre evidencia curada y `ensure_auto_battle_on`: ON inicial 0 taps, OFF → un tap → ON fresco confirmado, sin retry.

### WorldBossFlow

- [x] Implementar `WorldBossFlow + ControlledWait` sobre percepción, facts y Auto Battle; Auto Repeat queda fuera del primer slice.
- [x] Partir de policy `ALWAYS_PARTICIPATE` y reservar `ONLY_IF_NOT_PARTICIPATED` para facts de rank/participation posteriores.
- [x] Validar live sapphires insuficientes sin input, batalla completa hasta Raid Complete y el cierre conservador `Inventory Full → No → World Boss`.
- [ ] Diseñar la liberación de inventario y reanudación del mismo personaje; por ahora el evento termina correctamente su flow.
- [x] Componer y validar live 2/2 `WorldBossFlow + rotation.standard` y 2/2 `BlackMarketFlow + WorldBossFlow + rotation.standard`, sin normalizaciones redundantes.
- [ ] Exponer la composición mediante runtime manual, registry/launcher y mini GUI; ejecutar allí los futuros ciclos 28-character bajo revisión del usuario.

### Fase 6 — expansión y operación unattended

- [ ] Migrar flows adicionales manteniendo límites entre Perception, Rotation, flows y ADB.
- [ ] Añadir priorities, interruptions, conflict/recovery transversal y aislamiento de fallos.
- [ ] Afinar `fast safe retry → retries conservadores → ConflictResolver escalation` con evidencia, sin cambiar por anticipado timings validados.
- [ ] Incorporar estrategias Rotation futuras para MAIN/SUBS, filtros o identidad cuando exista necesidad.
- [ ] Reutilizar TOT como conocimiento legacy sin desplazar el vertical slice vigente.
