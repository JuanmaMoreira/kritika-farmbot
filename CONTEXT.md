# Estado actual — Kritika FarmBot

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
Stages/Gold Farming conservan su contrato Lobby propio, sin imponerlo a todas las activities.

## Evidencia reutilizable y deuda

Stabilization loop: 1917 casos previos verificados (cobertura combinada, no una invocación).
Cleanup: 1546 passed / 4 skipped, Craft evaluator 13 frames, Socket scope 17 frames y audit
Abyssal 111 frames. Navigation handoff y QM fix: 752 passed / 4 skipped en cobertura
combinada; todos los runs rojos de validación se preservan. Skips: evidencia histórica
local Rotation ausente. No nueva suite completa ni smoke por ritual en el cierre.

Deuda real no bloqueante: Craft Armor Expert adquirido sin Hero/MAX/result/effect natural
completo; Accessories Hero Earrings adquirido sin MAX/result/effect completo; chat desplegado
completo no adquirido (banners existentes pasan); ahorro físico final Socket 0.2 s pendiente
natural; Ads multipart/triple post-fix y No Ads temporal full recovery no forzados end-to-end;
smoke natural de handoff/QM chaining pendiente. Otras deudas menores conservadas en ROADMAP.
Próximo frente: targeted swipe/ordered-list navigation, todavía sin iniciar.

Históricos: checkpoint Stages/Ads `3f4acf3e` y MW `73313497`; smokes aceptados
`stages_progress_smoke`/`f1c24b514e4e40128d5875a7c1ed74f4` y `mw_final_native_d1e5d83e`
siguen como procedencia de sus versiones. Contratos: [ARCHITECTURE](ARCHITECTURE.md),
[GAMEPLAY_GT](docs/GAMEPLAY_GT.md), [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md).

Fuera del checkpoint, preservados: Summon Pet Daily previo y su hunk Registry, tests portal
previos, eliminación histórica del plan y `check_eval.py`, `fix_tests.py`, `test_live.py`,
`test_wait.py`. Logs completos/diagnósticos/outputs y corpus grande permanecen locales;
sólo assets runtime y fixtures causales curados forman parte del commit. AGENTS sin cambios.
