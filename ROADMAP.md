# Pendientes

Estado en [CONTEXT](CONTEXT.md); GT físico en [GAMEPLAY_GT](docs/GAMEPLAY_GT.md);
contratos en [ARCHITECTURE](ARCHITECTURE.md) y [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md).

## Full roster combinado cerrado técnicamente — 2026-10-05

Campaña GUI manual27ae46d4:28/28 scopes,28 Rotation, Session COMPLETED,
cero fallos técnicos,61:17.608.25 personajes con Ads agotados;6 Ads/Sapphire
verificados; WB28 no elegibles. No exigir business completeness. Código/assets
coinciden con preparación anterior al run y cierre; límite de hash de config
explicado en [FULL_ROSTER_CHECKPOINT](docs/FULL_ROSTER_CHECKPOINT.md).
Nuevo checkpoint causal sobre656460c4; sin nuevas features ni cambio de policy.

Ads cortos: terminal fuerte permite cierre inmediato, sin duración mínima;
primitivas/texto chrome SDK independientes del creative, Next ad intermedio,
progreso/reset, stall y180 s conservados. Offline/integration verdes; live breadth
limitada por agotamiento diario. X sola adquirida ya implementada, pendiente
cobertura natural amplia post-latest-fix, igual que multipart/triple explícito
y recovery No Ads temporal. Usuario hará otro28 manual con reset diario.
No bloquear este checkpoint ni fabricar anuncios para cubrir esas variantes.
Accessories MAX/result/effect y SessionReport whitelist siguen pendientes.

## Checkpoint anterior de tres personajes — 2026-10-05 (histórico)

Campaña GUI final2808930b: tres personajes consecutivos/Rotation, COMPLETED,
cero fallos técnicos con código final idéntico; offline1906 passed,4 skips históricos.
Detalle y business incompleto/UNASSESSED conservados en
[SESSION_STABILIZATION_AUDIT](docs/SESSION_STABILIZATION_AUDIT.md). WB→Sell tras
Full post-Combine y assets Normal/Poor quedan productivos y físicamente validados.
Un único checkpoint local `fix: stabilize combined farming sessions`, sin push;
targeted swipe sigue cerrado. Deuda causal no bloqueante: chrome Ads X sola,
whitelist informativa SessionReport, Accessories MAX/result/effect físico,
triple explícitamente identificado post-fix y No Ads temporal full recovery natural.

## Bloque cerrado — 2026-10-04

Configurable Routines v1 (persistencia/GUI/config por occurrence/snapshot), Gold Farming
Cycle live validado en tres personajes, fixes causales, Sapphire pressure <102 y navigation
caller-owned quedan cerrados conjuntamente sobre `3f4acf3e`. Hub sharing, Quick Menu chaining
y Rotation desde BASE capaz están implementados y validados offline; no push ni nueva campaña.
Los smokes históricos de MW y Stages/Ads conservan su resultado/procedencia; runs rojos
anteriores permanecen rojos. No hay nuevo planner, DAG ni framework de workflow.

## Próximos frentes, en orden

Character Identity + Persistent Character State: **cerrado como checkpoint conjunto**
sobre parent `fe774abc`.28 IDs/corpus84, SQLite, clock dinámico/scheduler,
Ads/WB causal, eligibility por occurrence, collector QM sin apertura adicional y GUI
con persistencia están productivos. **Character Data Sweep cerrado**: acción GUI
dedicada All28, sin flows productivos,28/28 recursos e identidades y28 Rotations,
0 failures en5:49; atribución, SQLite/GUI reopen y241 tests afectados verdes.
GUI cleanup incluido: ownership Step/Routine/Application, contextualidad/scroll,
sorting y Light/Dark persistido con reopen. Ads/WB previos preservados, sin completar UNKNOWN
por inferencia. Validación del índice y separación histórica en
[checkpoint](docs/CHARACTER_STATE_CHECKPOINT.md).
Detalle/validaciones/deuda física focal en
[informe](docs/CHARACTER_STATE_IMPLEMENTATION.md). Open Pets queda posterior:
no implementarlo como parte de este frente.

1. Targeted swipe / ordered-list navigation: **cerrado para el alcance actual**
   ([informe](docs/TARGETED_SWIPE_AUDIT.md)): primitive reusable y Trading Center productivo,
   Materials: coarse robusto + un loop dirigido, 10/10 repeticiones finales con 2 swipes,
   6 capturas y cero fallback. Incremental comparable PTS: 5 swipes/21–22 capturas;
   benchmarks nativos anteriores conservados. Calibración, fallback y replays verdes.
   ToT reutilizará la primitive cuando se implemente y se adquiera explícitamente su GT
   de lista. No hay requisito de segunda superficie ni adopciones inferidas de otros menús.
2. Completar GT Craft naturalmente: Weapons tiene cadena productiva completa. Hero Armor
   Helmet ahora tiene MAX/result/effect adquirido (DemonBlade114→16, coste49). Accessories Hero Earrings
   adquirido; faltan MAX/result/effect completos. La visita de tres familias ya existe,
   pero cada operación sigue exigiendo evidencia real y sus guards consumptivos.
3. Daily ToT/Arena/Melee cuando vuelva a ser prioridad: ToT entrada rápida/piso bajo y
   readiness propia ≥1 Sapphire; Arena batalla izquierda/menor dificultad; Melee entrada
   rápida desde Battle y daily badge. No implementados. Composición económica futura
   WB→MW→ToT; WB no está garantizado después de MW ni ToT por posición. Cada owner decide
   su readiness, sin reordenar rutinas ni insertar actividades automáticamente.
4. Deudas live menores existentes, sólo ante aparición natural:
   - Chat desplegado completo en Abyssal; banners Channel Global Chat existentes pasan.
   - Ahorro físico final de Socket animation/scoped perception 0.2 s.
   - Ads multipart/triple explícito post-latest-fix y No Ads temporal full recovery end-to-end;
     implementación/tests e integración28/28 ya verdes, amplitud live limitada.
   - QM desde Battle Mode Select hacia destinos aún no ejercidos naturalmente; Back sólo hacia Lobby.
   - Sell logical transform entre Bulks si sigue Full; expansión Equipment +4 positiva
     sólo por necesidad real; Ethereal Enhance positivo cuando haga falta. Poor/Normal
     cerrados mediante assets físicos y tres Bulks guarded127→126→125→122.
   - Chrome SDK X sola sin reward-granted: autoridad adquirida implementada y replay verde;
     falta amplitud live natural tras ajuste general, sin confundir fin de parte con fin del ad.
   - SessionReport: reconocer el evento informativo `monster_wave.sapphire_effect` para
     no proyectar Gold como UNASSESSED cuando sus efectos y resultado están acreditados.
     La campaña2808930b conserva la proyección histórica; no convertirlo en failure.
   - Lifecycle SKIP tras pausas muy largas; portabilidad del corpus; Fill All con Gold
     insuficiente sigue UNKNOWN de baja prioridad.

Estas deudas no bloquean el checkpoint. No fabricar Full/materiales/ads ni provocar
variantes para validarlas. No repetir la campaña de tres personajes ni seguir optimizando
paths cerrados. Combate/manual Stages, scheduler y planner general permanecen fuera de scope.
