# Pendientes

Estado en [CONTEXT](CONTEXT.md); GT físico en [GAMEPLAY_GT](docs/GAMEPLAY_GT.md);
contratos en [ARCHITECTURE](ARCHITECTURE.md) y [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md).

## Bloque cerrado — 2026-10-04

Configurable Routines v1 (persistencia/GUI/config por occurrence/snapshot), Gold Farming
Cycle live validado en tres personajes, fixes causales, Sapphire pressure <102 y navigation
caller-owned quedan cerrados conjuntamente sobre `3f4acf3e`. Hub sharing, Quick Menu chaining
y Rotation desde BASE capaz están implementados y validados offline; no push ni nueva campaña.
Los smokes históricos de MW y Stages/Ads conservan su resultado/procedencia; runs rojos
anteriores permanecen rojos. No hay nuevo planner, DAG ni framework de workflow.

## Próximos frentes, en orden

1. Targeted swipe / ordered-list navigation: **cerrado para el alcance actual**
   ([informe](docs/TARGETED_SWIPE_AUDIT.md)): primitive reusable y Trading Center productivo,
   Materials: coarse robusto + un loop dirigido, 10/10 repeticiones finales con 2 swipes,
   6 capturas y cero fallback. Incremental comparable PTS: 5 swipes/21–22 capturas;
   benchmarks nativos anteriores conservados. Calibración, fallback y replays verdes.
   ToT reutilizará la primitive cuando se implemente y se adquiera explícitamente su GT
   de lista. No hay requisito de segunda superficie ni adopciones inferidas de otros menús.
2. Completar GT Craft naturalmente: Weapons tiene cadena productiva completa. Armor sólo
   Expert adquirido; faltan Hero/MAX/result/effect completos. Accessories Hero Earrings
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
   - Ads multipart/triple post-fix y No Ads temporal full recovery end-to-end.
   - MW→Quests→Mailbox→Rotation y QM desde Battle Mode Select; Back sólo hacia Lobby.
   - Sell logical transform entre Bulks si sigue Full; expansión Equipment +4 positiva
     sólo por necesidad real; Poor/Normal y Ethereal Enhance positivos cuando hagan falta.
   - Lifecycle SKIP tras pausas muy largas; portabilidad del corpus; Fill All con Gold
     insuficiente sigue UNKNOWN de baja prioridad.

Estas deudas no bloquean el checkpoint. No fabricar Full/materiales/ads ni provocar
variantes para validarlas. No repetir la campaña de tres personajes ni seguir optimizando
paths cerrados. Combate/manual Stages, scheduler y planner general permanecen fuera de scope.
