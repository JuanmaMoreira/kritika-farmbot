# Estado actual — Kritika FarmBot

## Baseline y consulta

Bot Python para automatizar Kritika en Android con captura scrcpy/ADB, percepción
CV/OCR, contexto semántico, flows guardados y sesiones por personaje desde GUI/CLI.
Checkpoint correctivo de código: `86a9a8f`, rama `rebuild/stable-baseline`
(2026-10-16), sobre el baseline de campaña `9989fd8`. Incluye los fixes focales
WB→Socket, SDK compacto y diagnóstico Craft; no implica aceptación física global.
Validaciones, límites y preparación siguiente: [checkpoint del16/10](docs/CAMPAIGN_20261016_CHECKPOINT.md).

Leer [AGENTS](AGENTS.md), este contexto y el apartado pertinente de
[ROADMAP](ROADMAP.md). Después consultar sólo el contrato del subsistema:

| Pregunta | Fuente dueña |
| --- | --- |
| UI física, USER_GT, layering, controles, UNKNOWN | [GAMEPLAY_GT](docs/GAMEPLAY_GT.md) |
| Arquitectura, ownership, snapshots, handoffs, Session | [ARCHITECTURE](ARCHITECTURE.md) |
| Recursos, reliefs, Equipment/Sell, Trading, Stamina, Stages/Gold | [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md) |
| Monster Wave SKIP y operación de una pasada | [MONSTER_WAVE_SKIP](docs/MONSTER_WAVE_SKIP.md) |
| Arena Single/Auto Repeat, receipts, retorno | [ARCHITECTURE: Arena](ARCHITECTURE.md#arena--percepción-resultado-y-operación-b1-2026-10-08) y su sección B2 |
| Arena Farming, controller, Manual Stages, presupuesto | [ARENA_FARMING_CYCLE](docs/ARENA_FARMING_CYCLE.md) |
| Ads, cierre/progreso/retorno y autoridad del caller | [ARCHITECTURE: Ads](ARCHITECTURE.md#adsmanager-transversal) |
| Identidad, estado persistente, eligibility, GUI | [ARCHITECTURE: estado](ARCHITECTURE.md#character-identity-y-estado-persistente), [GUI_CONFIGURATION](docs/GUI_CONFIGURATION.md) |
| Shared Meteorites y lifecycle por personaje | [ARCHITECTURE: B2](ARCHITECTURE.md#meteorites--integración-b2-de-routinesession-2026-10-08) |
| Fallos/capturas y proyección humana | [FAILURE_EVIDENCE_V1](docs/FAILURE_EVIDENCE_V1.md), [SESSION_REPORT_V1](docs/SESSION_REPORT_V1.md) |
| Aceptaciones, incidentes, checkpoints y decisiones anteriores | [HISTORY](docs/HISTORY.md) |

## Implementación vigente

`Capture → Perception/Runtime Facts → ContextResolver → RuntimeObserver → Flow/
Session → operación verificada → ActionExecutor → ADB`. Resolver puro; readers
sin policy económica; GUI/CLI componen los mismos owners. Código/tests publicados
son autoridad de implementación; los contratos describen sus límites.

- Flows productivos: Black Market, World Boss, Monster Wave SKIP, Stages Daily
  ads-only, Send Stamina, Summon Pet Daily, Daily Quests, Mailbox y Guild Check-In.
  Rotation y rutinas configurables v2 conservan orden literal y config por ocurrencia.
- Basic Gold Farming coordina hasta dos oportunidades Stages Ads y sus inversiones
  MW. Stages/Gold usan Sapphire pressure ≥102 y efecto fresco tras CLEAR; no saldos
  simulados. Arena usa una pasada MW independiente de esa meta de presión.
- Arena está publicado: Single Battle, Auto Repeat x8 y Farming Cycle adaptativo
  Arena→MW→Manual Stages según recursos, con presupuesto/abastecimiento Stamina,
  resultados causales y Session Report analítico. Previous Rewards tiene ACK único;
  el claim pertenece a Mailbox. No hay una policy Daily Arena independiente.
- Reliefs transversales, Equipment Combine/Sell/expansión guardada, Trading Keys/
  Materials, Craft y Treasure Gold están conectados a sus callers acreditados.
  Descubrimiento CV no autoriza ventas; Bulk/compra requieren sus guards y efecto.
- Identidad closed-set de 28 personajes, SQLite/epochs, Ads/WB operativos,
  snapshots informativos separados, Character Data Sweep y VP semanal Arena
  están implementados. Sweep/VP no autorizan gameplay ni completan UNKNOWN.
- Shared Meteorites A/B1/B2 posee setup de once efectos y cleanup por personaje
  en Session, default OFF. Manual Stages consume el scope READY verificado;
  no equipa ni limpia por cuenta propia. REPEAT_CURRENT sigue fuera de alcance.
- Failure Evidence conserva ring semántico y último frame directo/nativo; FAILED
  y MANUAL técnicos comparten bundle/referencia en flow, Session y JSONL. No
  recaptura ni cambia continuación; cancelación/MANUAL sin causa no crean bundle.

## Límites esenciales para continuar

Session decide próximo entry, Navigation la ruta segura y cada owner gameplay/
retorno. Lobby no es obligatorio entre BASE compatibles: MW→QM→Mailbox/Quests/
Rotation puede reutilizar origen; Stages mantiene su entrada desde Lobby.
Un retry necesita evidencia positiva fresca posterior al input, bounds y
cancelación en su owner. UNKNOWN/AMBIGUOUS no autorizan input; no repetir un
consumo incierto. No existe recovery, planner estratégico o navegación general
por inferencia. Aplicar AGENTS sin duplicar aquí sus reglas.

## Incidencias y validación

- **Cierre campaña 16/10:** los tres Character State de Flame Striker, Eilla y
  Blade Dancer conservaron resets tras scopes de identidad UNKNOWN; los tramos
  registran WB/Ads y Rotation, sin asociación nominal suficiente. Reconciliados
  exclusivamente Ads0/WB YES ciclo5 por USER_GT, con backup y procedencia; el
  miss exacto del recognizer sigue UNKNOWN y no se cambiaron sus guards.
  Informe reproducible en `artifacts/supervision_gold28_20261016/closure/`.
  WB→Socket tiene fix validado física/offline; SDK compacto, tests/replay
  sin ocurrencia natural de la rama nueva. El adapter MW/Craft ahora conserva
  fallos técnicos posteriores al relief en vez de sustituirlos por capacidad
  anterior; validado offline, requiere relanzar GUI. El corte de transporte USB
  se mantiene como externo, separado del diagnóstico incompleto de Hastati.
  No se inició otra campaña ni Arena durante el cierre. La reconciliación es
  local y no se repite al publicar; los artifacts/SQLite no forman parte del Git.

- **UNKNOWN — Arena `f5d2a828`:** USER_GT acredita Select Mode al corte de retorno,
  pero faltan los píxeles exactos/causa del recheck fallido. La captura posterior
  restaurada pasa el guard vigente; no reproduce ni explica el miss. La captura
  directa/MANUAL corrige pérdida futura de evidencia, no recupera ese corte.
- Recuperaciones recientes de Stamina (cantidad/cierre), Stages (Inventory/config),
  MW (CLEAR/hub), Mailbox, Equipment paginación, WB Previous Rewards y Ads tienen
  validaciones offline/replay posteriores; no atribuirles smokes nuevos por estar
  publicadas. Arena NORMAL/wait/retorno conserva los límites de cada intervención.
  Detalles y commit de cada cierre: [historia reconciliada](docs/HISTORY.md#consolidación-documental-2026-10-14).
- Aceptaciones previas siguen válidas para su alcance: Gold 28/28 y Arena integral
  GUI→generadores→cleanup→Session COMPLETED. Campaña Stability+Performance completa
  28 IDs en varios runs; no equivale a una Session 28/28. Amplitud Ads cerrada por
  USER_GT 2026-10-06; variantes reparadas después tienen su validación específica.
- SessionReport base no garantiza mostrar la referencia de MANUAL técnico:
  el bundle sigue enlazado en resultados/JSONL; límite de presentación registrado
  en su contrato y ROADMAP, sin cambio de status ni bloqueo de Open Pets.
- Fallos antiguos de harness/temporales/cache no son fallos vigentes acreditados.
  Fixtures reducidas/escalas simuladas no prueban calibración nativa nueva; fuentes
  raw ausentes y retención de bundles limitan reproducción, no reabren GT cerrado.
- Deudas físicas focales (Accessories MAX/result/effect, variantes Arena y Fill All
  sin Gold) y mejoras no bloqueantes están en ROADMAP. No se inicia investigación
  ni otra campaña durante esta fase.

## Siguiente trabajo

Consolidación documental → auditoría focal y limpieza segura de almacenamiento →
**Open Pets**, siguiente funcionalidad importante, todavía no iniciada. Summon Pet
Daily existente no implica Open Pets. No hay diseño ni implementación de Open Pets
como parte de este cierre. La limpieza requiere su propia revisión de consumidores
antes de eliminar evidencia y no se inicia automáticamente.

Los diarios completos, incluido el diff pendiente de 197 líneas, se preservan en
el [snapshot histórico](docs/legacy/CONTEXT_PRE_CONSOLIDATION_20261014.md).
Los contratos anteriores son la entrada técnica; consultar historia sólo cuando
la tarea necesite diagnóstico, evidencia o límites de una aceptación concreta.
