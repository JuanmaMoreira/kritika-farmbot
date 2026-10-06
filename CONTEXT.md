# Estado actual — Kritika FarmBot

## Character Identity + Persistent Character State — 2026-10-05/06

Checkpoint conjunto sobre parent `fe774abcef3a636c138028717a0d2a0b514c5e6f`,
rama `rebuild/stable-baseline`. Resolver closed-set84/84 frames,
28/28 identidades, cero wrong/UNKNOWN; DRAKEN一BK/二DB/三BB requieren discriminador
visual focal, sin relajación OCR ni identidad por posición. Demon Blade validado live.

SQLite runtime/schema1,28 IDs permanentes, operational Ads/WB y snapshots informativos
separados; GUI Character State, WB eligibility por occurrence y captura configurable
OFF/BEFORE_CHARACTER_ROTATION. Collector productivo reutiliza el mismo QM de Rotation.
Character State → **Character Data Sweep — All 28** permite refrescar recursos sin
flows productivos. Session explícita reutiliza identity/collector/Rotation y un QM
por personaje; no altera el modo de captura de rutinas normales. Aceptación desde
GUI real: **28 identidades,28 snapshots completos,28 Rotations,0 failures**,5:49
incluyendo inicialización (345.545s de Session). Mediana por personaje12.101s;
reader+persistencia0.159s, total5.266s. Auditor verificó scopes/secuencias/timestamps,
sin duplicados ni contaminación; cierre/reapertura de GUI y SQLite conserva28 filas.
Natural Video0 de Demon Blade escribió0 durante el frente previo.
Backfill causal explícito del run27ae46d4 acreditó26 personajes en el epoch actual;
Burst Breaker permanece UNKNOWN, sin deducir el scope histórico por índice.

Countdown live `1d4h14m` observado2026-10-06T02:15:52Z: cierre WB estimado
2026-10-07T06:30Z (03:30 -03), reset sincronizado07:00Z (04:00 -03);
siguiente reset diario2026-10-06T07:00Z. Precisión del display1min, normalizada
al próximo límite de minuto; lecturas posteriores mantuvieron el anchor.
Runtime scheduler/Tk timer y startup/read catch-up implementados, transitions
determinísticos validados con reloj controlado, sin esperar físicamente al reset.

Pareja rank/damage está físicamente en World Boss main; Select Battle Mode expone
rank/card sin ese damage. Numeric live, blank y previous reward históricos acreditados.
No nuevo Raid necesario: el estado natural era participado; escritura RAID_COMPLETE
validada en integración incluso con cleanup posterior fallido. Deuda focal: balance0
natural en QM; separadores/comas y magnitudes de1 a193061 adquiridos en el sweep;
el parser0/comas y los tres Unicode tienen pruebas/corpus. Informe y límites en
[CHARACTER_STATE_IMPLEMENTATION](docs/CHARACTER_STATE_IMPLEMENTATION.md).

Estado runtime de aceptación Sweep: Ads0 acreditado en27, Burst BreakerUNKNOWN; WBYES en6,22UNKNOWN;
snapshots completos en28. Sweep no modifica los facts operativos: comparación antes/después
idéntica. Última observación countdown2026-10-06T02:41:19.864Z: `1d 3h48m`, mismo
anchor2026-10-07T07:00Z. Suite afectada Sweep:241 passed; git diff --check limpio.
Run final `2c282440554f480a9d9a59c366650195`; artifacts locales en
`artifacts/character-data-sweep/` (audit, recursos, operational y reopen).

GUI cleanup conserva Step Settings por occurrence, Routine Settings para Resource
snapshot y Application para Appearance. Forms contextuales con scroll; tabla sortable
con valores tipados y UNKNOWN al final en ambos sentidos; Light/Dark dinámico y
preferencia global runtime-local. Auditoría Tk normal/reducida y reopen acreditados.
Contrato en [GUI_CONFIGURATION](docs/GUI_CONFIGURATION.md); validación consolidada,
índice y límites del cierre en [CHARACTER_STATE_CHECKPOINT](docs/CHARACTER_STATE_CHECKPOINT.md).
Durante el cierre conjunto se registró catch-up SYNCHRONIZED_RESET del diario
2026-10-06T07:00Z (observado12:27:50.521Z): Ads28=2, siguiente diario07:00Z del día7.
WB6YES/22UNKNOWN y los28 snapshots conservados; no se completaron facts manualmente.
El informe checkpoint separa este epoch nuevo del estado de aceptación Sweep.
Open Pets permanece posterior y sin implementar. Trabajo independiente previo preservado.

## Checkpoint full roster — aceptación técnica28/28 2026-10-05

Parent `656460c4b16526ced5ae46b36764240aa5ec71cb`, rama `rebuild/stable-baseline`.
Nuevo checkpoint único `fix: stabilize full roster farming session`; commit/push
autorizados para el cierre verde. Campaña GUI manual principal
`20261005T234827.311080Z_session_27ae46d4`, run
`e4d8ec7e6aaf403ca5f919685b22cd81`, session
`6c2c6ad1abff47ffb4648262e26368bb`:28 scopes consecutivos/28 Rotation,
Session COMPLETED, cero flow/session/runtime.failed,20:48:32→21:49:50 -03,
61:17.608. Rutina BM→WB→Gold→Mailbox→DailyQuests→Rotation verificada por scope.
26 nombres de clase registrados y2 UNKNOWN (18/21), conservados sin inferencia.
25 personajes ads_exhausted;6 Ads con efecto Sapphire; WB28 no elegibles;
23 inversiones MW en5 personajes. Chaining MW directo3, Lobby legítimo25,
cero violaciones. Business incomplete27 es resultado real, no failure técnico.

AdsManager ahora reconoce primitivas del chrome SDK independientes del fondo,
y lee exclusivamente Reward granted/Next ad en el campo fijo SDK bajo ownership
Android concordante. Terminal fresco autoriza cierre inmediato sin edad mínima;
Next ad es intermedio sin cierre. Timeout/progreso no acreditan recompensa.
No se añadieron templates por creative; propuesta aislada descartada. Implementación
offline e integración28/28 verdes; amplitud live de short-ad/multipart limitada
por agotamiento diario. En este run hubo6 SDK Back terminales (ads9.922–25 s),
sin afirmar cobertura exhaustiva ni un ad físico de5 s. Próxima campaña manual
con reset diario aportará cobertura natural; no bloquea el checkpoint.
Causas/fixes/validaciones anteriores y rojos en
[COMBINED_28_ACCEPTANCE_AUDIT](docs/COMBINED_28_ACCEPTANCE_AUDIT.md).
Hashes, límites de configuración, cierre/INDEX y tabla28 en
[FULL_ROSTER_CHECKPOINT](docs/FULL_ROSTER_CHECKPOINT.md). Siguen pendientes
triple explícito post-latest-fix, No Ads temporal full recovery, Accessories
MAX/result/effect y whitelist informativa `monster_wave.sapphire_effect`.
X sola SDK adquirida está implementada/offline; su amplitud live tras este ajuste
sigue pendiente. Trabajo independiente Summon Pet/scripts fuera del checkpoint.

## Checkpoint local — estabilización combinada 2026-10-05

Sobre `31ecf4642db02d6a90fce871360f38cc45e92650`, rama `rebuild/stable-baseline`.
Campaña GUI final `20261005T050411.404714Z_session_2808930b.jsonl`: Cat Acrobat,
Crimson Assassin, Flame Striker consecutivos, tres Rotation, Session COMPLETED,
cero technical failures,33:19 de Session. Código/assets idénticos durante los tres.
Offline final una invocación:1906 passed,4 skips históricos Rotation,451,65 s.
Cierre en un único commit local `fix: stabilize combined farming sessions`, sin push;
trabajo independiente previo preservado y excluido del índice. Reconstrucción, rojos,
eventos y límites en [SESSION_STABILIZATION_AUDIT](docs/SESSION_STABILIZATION_AUDIT.md).

Fixes causales: contexto fresco Auto OFF/ON y retry VerifiedTransition; Ads stall
desde último progreso SDK, no60 s globales; Gold publica MW final para QM chaining;
hub WB no elegible→MW sin Lobby; crop Hero Armor; board OCR memo por pixels exactos;
Select Striker/H&H bajo obstrucción; Keys0/10 rojo; assets Sell Normal/Poor y popup
K Coin multiline. WB usa el owner Sell existente una vez tras Full post-Combine,
restaura WB y conserva su caller; no repite Combine ni delega el Full a MW.

Business final: Cat Video0; Crimson mail restante tras procesamiento acreditado;
Flame UNASSESSED sólo por proyección Gold (whitelist informativa omite
`monster_wave.sapphire_effect`). No son technical failures ni se ocultan en historia.
Quedan esa whitelist, chrome Ads X sola con cierre tardío/reward acreditado, GT
Accessories MAX/result/effect abierto, triple explícitamente identificado post-fix
y No Ads temporal full recovery natural. Craft focal Hero Armor114→16 adquirido;
campaña final no necesitó Craft. H&H se cierra sólo ante obstrucción causal.

## Bloque cerrado — checkpoint local 2026-10-04

Sobre `3f4acf3ea94cb04164c92cea795d98561109806e` (`feat: add productive stages daily
and ads automation`), rama `rebuild/stable-baseline`. Cierre conjunto de Configurable
Routines v1, Gold Farming, estabilización causal y navigation handoff. Sin push.

`RoutineSpec → ordered RoutineSteps → FlowRegistry → flows/capabilities` está productivo:
save/load, rename/duplicate/delete, enable/disable, reorder, repeticiones, config por
occurrence y snapshot estable al ejecutar desde GUI. Basic Gold Farming selecciona
`Gold Farming Cycle`; no cuatro steps hardcodeados en runner, DAG ni planner.

La capability coordina hasta dos oportunidades Stages Ads por personaje: readiness
Sapphire causal, Stages si corresponde e inversión MW posterior/final. Video0/alert diario
omiten la oportunidad restante sin quitar la inversión final; resultado business incomplete.
UNAVAILABLE temporal no es daily exhausted. El fact se comparte sólo dentro del personaje;
same-character reentry conserva, Rotation cambia scope. Failure/cancel detienen.

Policy productiva Sapphire: pressure ≥102, safe <102. Stages e inversión MW usan
`sapphire_pressure_passes` y el mínimo necesario; después de cada CLEAR exigen saldo
fresco y recalculan, sin aritmética acreditada ni consumo por debajo del umbral.

## Live aceptado y estabilización

Campaña GUI final `20261003T134838.410066Z_session_d8419f31.jsonl`: Ice Warlock, Eilla,
Lina consecutivos, una Rotation por personaje, Eilla/Lina con ambas ads completas,
Ice Warlock business incomplete por Video0, **0 technical failures**. Persistencia y
reapertura de la rutina verificadas. Runs rojos anteriores se conservan como rojos;
no repetir la campaña ni atribuir al smoke los cambios offline posteriores.

Fixes causales incluidos: Stamina batch (selector 1/20, N−1 taps, cantidad final y
confirmación únicas); Claims bounded con señal mínima; Abyssal antes de Claims y cero
World Map si ya está activo; crops calibrados sin bajar thresholds; agotamiento por
personaje; MW no-work antes de navegación; Keys Bronze/Silver con fase estable; Sell
block CV/logical delta y reutilización del panel SELLABLE; count/capacity causal tras
Combine; Craft Weapons→Armor→Accessories en una visita; Socket animation handoff/scoped
perception, positive-only taps y flashes/UNKNOWN sin input; layering/recovery causal.

## Navigation final

Flow/Activity hace gameplay y devuelve resultado/superficies verificadas. Session conserva
orden literal y pide el entry del siguiente step útil; Navigation/Zone ejecuta la ruta
segura mínima. MW no conoce el siguiente flow ni normaliza arbitrariamente a Lobby.

WB preparado→MW comparte hub; MW→ToT útil usa Back→Battle Mode Select. `routing_no_work`
sólo admite prueba owner pura/barata/concluyente, sin capture/input/gameplay/gasto;
UNKNOWN no se salta ni se anticipan Eligibility/readiness contextuales.

Quests/Mailbox entran por Quick Menu desde BASE acreditada, cierran y prueban exactamente
su origen con snapshot nuevo. Rotation acepta BASE verificada QuickMenu-capable:
MW→QM→Quests→close→MW→QM→Mailbox→close→MW→QM→Character Select→Rotation→nuevo Lobby.
Sin Lobby intermedio. Battle Mode Select tiene QM, pero hacia Lobby gana un Back directo;
hacia Pets/Quests/Mailbox/Rotation gana QM directo. Capability explícita, no universal;
modal/actividad incompatible/UNKNOWN/AMBIGUOUS no autorizan inputs. Rutas ajenas fail-closed.
Stages usa Lobby para Stamina y su entrada física, después del prerequisite MW directo
desde hub cuando corresponde. Gold conserva la BASE MW de la inversión final para el
siguiente step literal; no exige Lobby terminal.

## Evidencia reutilizable y deuda

Stabilization loop: 1917 casos previos verificados (cobertura combinada, no una invocación).
Cleanup: 1546 passed / 4 skipped, Craft evaluator 13 frames, Socket scope 17 frames y audit
Abyssal 111 frames. Navigation handoff y QM fix: 752 passed / 4 skipped en cobertura
combinada; todos los runs rojos de validación se preservan. Skips: evidencia histórica
local Rotation ausente. No nueva suite completa ni smoke por ritual en el cierre.

Hero Armor/Helmet tiene adquisición natural MAX2/10, coste49, una confirmación y efecto
114→16 en DemonBlade; Accessories Hero Earrings sigue sin MAX/result/effect completo.
Poor/Normal adquiridos y vendidos por el owner; Rare/Epic tienen assets/replays positivos.
Cadena MW→QM Mailbox→restore MW→QM Quests→restore MW→QM Rotation acreditada en Mystic.
Deuda real no bloqueante: chat desplegado
completo no adquirido (banners existentes pasan); ahorro físico final Socket 0.2 s pendiente
natural; Ads multipart/triple post-fix y No Ads temporal full recovery no forzados end-to-end;
chrome de ad X sola sin texto reward-granted aún no reconocido (cierre tardío con reward
verificado). Otras deudas menores conservadas en ROADMAP.
Targeted swipe/ordered-list navigation (2026-10-04): primitive transversal implementada;
único consumidor productivo actual Trading Center / Hero Weapon Crafting Materials.
Orden relativo del suffix/nueve anchors CV y física adquiridos. Coarse robusto .94→.02
a 250 ms, luego un único loop dirigido con curva empírica independiente, safe-window
.43–.87 y objetivo .65; feedback bounded, cancelación, guards frescos y fallback con
presupuesto restante. Código final repetido diez veces: 10/10 con 2 swipes, 6 capturas,
cero correcciones/fallbacks; 5.06–6.19 s. Incremental en el mismo source PTS: 5 swipes,
21–22 capturas y 18.80–19.06 s. Benchmark v1 nativo 4/7 y baseline 5/12 conservados
como historia, sin mezclar pipelines. [Informe](docs/TARGETED_SWIPE_AUDIT.md).
Futuro previsto: ToT cuando se implemente y se adquiera su GT propio, sin auditoría/adopción
de otras listas en este frente. Character Select es dynamic-order por USER_GT; Rotation
intacta. 145 tests afectados verdes, replay local y live no consumptivo; C3 366/40.
Checkpoint local independiente `feat: add directed trading list navigation`, sin push;
teléfono en Lobby y cleanup de los sources completado.

Históricos: checkpoint Stages/Ads `3f4acf3e` y MW `73313497`; smokes aceptados
`stages_progress_smoke`/`f1c24b514e4e40128d5875a7c1ed74f4` y `mw_final_native_d1e5d83e`
siguen como procedencia de sus versiones. Contratos: [ARCHITECTURE](ARCHITECTURE.md),
[GAMEPLAY_GT](docs/GAMEPLAY_GT.md), [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md).

Fuera del checkpoint, preservados: Summon Pet Daily previo y su hunk Registry, tests portal
previos, eliminación histórica del plan y `check_eval.py`, `fix_tests.py`, `test_live.py`,
`test_wait.py`. Logs completos/diagnósticos/outputs y corpus grande permanecen locales;
sólo assets runtime y fixtures causales curados forman parte del commit. AGENTS sin cambios.
