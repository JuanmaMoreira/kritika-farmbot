# Meteorites — B1, aceptación 2026-10-08

Baseline `ce44fe55ef0490e068f972b59e96c1e9a3c58350`. Worktree `meteorites-hil`:
`meteorites-hil`. Sin commit/push.
Fase A estaba en el checkout principal: se trasladaron sólo sus owners, integración,
assets, fixtures y contratos, comprobando destinos idénticos al baseline. Adquisición
local del worktree y fixes independientes del checkout principal preservados.

## Algoritmo y owners

`SharedMeteoritesPreparation` en `bot/shared_meteorites.py` compone `MeteoritesRuntime`.
Runtime conserva selección, overlay, acción lateral, freshness, lineage, un input,
efecto esperado y readiness; reader/actions conservan percepción focal/geometría.
`group_cell` utiliza sprite/tier existentes; `inspect` utiliza el overlay OCR existente.
No se reimplementaron readers ni operaciones individuales.

Las cinco precondiciones USER_GT se asumen. Entrada compatible, Set 2 activo con
destino vacío, Flare E+ positivo en 1–12, recorrido del suffix Flare hasta normal,
ancla absoluta única `first_normal + 9`, Flare primero y normales 1..10 desde el
mismo índice. Guard `expected_slot`/`require_shared` antes del lateral; cada avance
se acredita por el efecto. Equip reconstruye página/slot desde el ancla inmutable.
Cleanup desde setup completo: slots 10..1 y centro, efectos OCCUPIED→EMPTY,
Set 1 al final. No segundo barrido ni selección desde Bag durante cleanup.

## Flare, frontera y posiciones observadas

Preparación autorizada por chat «listo». El personaje visible al final es **Drakenn19**;
no se adquirió ni infirió un stable character ID, y no hubo Rotation.
Flare Ethereal+ **+30**, posición absoluta **2**, página 1/celda visual 2.
Primer normal **6**; ancla **15 = 6 + 9**, página **1**, celda visual **15**
(`anchor_cell=14` zero-based). Equip Flare usó 2; los diez normales usaron exactamente
15, aunque Bag se reordenó. Diferente configuración respecto a la adquisición Rang
(ancla25): esta cadena acredita el algoritmo completo en el inventario preparado.
Fronteras/anclas en páginas posteriores tienen tests/replay de navegación, no una
segunda aceptación física B1 en otro inventario.

## Los 22 efectos individuales y tiempos

Cada fila tuvo overlay/acción lateral ligados, un único input, slot esperado
EMPTY→OCCUPIED (Equip) u OCCUPIED→EMPTY (Unequip) y readiness acreditada.
`before→effect` son sequences frescas del source; los otros diez slots se preservan.
Frames/hash, facts, métricas completas y lineage runtime en el
[manifest durable](../datasets/meteorites_b1_smoke_20261008_manifest.json). Raw/report
permanecen ignorados en `artifacts/meteorites_b1/20261008_133829/`; tests no dependen de ellos.
Revisión visual individual en `effects_contact_sheet.png`.

| Acción / slot | Bag absoluto | Nivel | before→effect | Wall s | Selección→overlay s | Tap→efecto s | Efecto→ready s | Navegación Bag s | Capt/OCR/Detector/CV | Stale rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Equip Flare | 2 | 30 | 81→89 | 0.750 | 0.250 | 0.391 | 0.031 | 0.031 | 18/3/44/123 | 11 |
| Equip 1 | 15 | 20 | 96→107 | 1.063 | 0.235 | 0.672 | 0.032 | 0.031 | 27/3/57/166 | 17 |
| Equip 2 | 15 | 21 | 115→124 | 0.953 | 0.329 | 0.500 | 0.032 | 0.046 | 23/3/51/132 | 14 |
| Equip 3 | 15 | 21 | 131→140 | 0.843 | 0.250 | 0.516 | 0.015 | 0.031 | 21/3/49/124 | 13 |
| Equip 4 | 15 | 30 | 148→158 | 1.031 | 0.313 | 0.594 | 0.015 | 0.031 | 26/3/52/127 | 17 |
| Equip 5 | 15 | 30 | 166→176 | 1.015 | 0.344 | 0.579 | 0.015 | 0.031 | 25/3/52/120 | 16 |
| Equip 6 | 15 | 30 | 185→194 | 0.907 | 0.312 | 0.531 | 0.016 | 0.032 | 21/3/45/98 | 14 |
| Equip 7 | 15 | 30 | 206→215 | 0.969 | 0.344 | 0.515 | 0.032 | 0.031 | 24/3/47/94 | 16 |
| Equip 8 | 15 | 30 | 224→234 | 0.969 | 0.265 | 0.593 | 0.032 | 0.047 | 24/3/50/97 | 16 |
| Equip 9 | 15 | 30 | 243→252 | 0.860 | 0.266 | 0.532 | 0.000 | 0.016 | 21/3/45/80 | 14 |
| Equip 10 | 15 | 30 | 262→271 | 0.875 | 0.265 | 0.531 | 0.031 | 0.032 | 21/3/45/74 | 14 |
| Unequip 10 | slot directo | 30 | 281→291 | 0.953 | 0.360 | 0.500 | 0.015 | 0.000 | 23/3/42/66 | 15 |
| Unequip 9 | slot directo | 30 | 301→310 | 0.875 | 0.281 | 0.516 | 0.015 | 0.000 | 21/3/40/70 | 14 |
| Unequip 8 | slot directo | 30 | 320→329 | 0.891 | 0.282 | 0.516 | 0.016 | 0.000 | 21/3/40/76 | 14 |
| Unequip 7 | slot directo | 30 | 339→349 | 0.969 | 0.360 | 0.516 | 0.016 | 0.000 | 23/3/46/92 | 14 |
| Unequip 6 | slot directo | 30 | 359→367 | 0.812 | 0.312 | 0.438 | 0.015 | 0.000 | 19/3/41/86 | 11 |
| Unequip 5 | slot directo | 30 | 377→386 | 0.906 | 0.328 | 0.515 | 0.031 | 0.000 | 21/3/42/96 | 13 |
| Unequip 4 | slot directo | 30 | 398→407 | 0.921 | 0.360 | 0.437 | 0.031 | 0.000 | 21/3/37/88 | 14 |
| Unequip 3 | slot directo | 21 | 417→427 | 0.937 | 0.328 | 0.469 | 0.031 | 0.000 | 22/3/46/116 | 13 |
| Unequip 2 | slot directo | 21 | 436→445 | 0.891 | 0.360 | 0.437 | 0.032 | 0.000 | 21/3/37/98 | 14 |
| Unequip 1 | slot directo | 20 | 455→464 | 0.875 | 0.297 | 0.500 | 0.016 | 0.000 | 20/3/40/118 | 13 |
| Unequip Flare | slot directo | 30 | 474→483 | 0.922 | 0.313 | 0.515 | 0.016 | 0.000 | 22/3/42/126 | 14 |

## Performance y separación de costes

Setup total **25.172 s**, cleanup **22.063 s**; cadena **47.235 s**.
Escritura/hash de evidencia: setup **10.471 s**, cleanup **11.315 s**.
Procedimiento excluyendo ese I/O del harness: setup **14.701 s**, cleanup **10.748 s**, total **25.449 s**.
La escritura sucede entre primitivas: no entra en el wall de cada fila. Startup,
calentamiento OCR y cierre final del source no están en esos totales. La escritura
es coste del smoke auditable, no delay/readiness del algoritmo standalone.

- Equip: wall acumulado 10.235 s; medianas wall 0.953, selección→overlay 0.266, tap→efecto 0.531, efecto→ready 0.031 s. Capture 0.577 s, percepción 1.190 s, navegación Bag 0.359 s; 251 capturas/33 OCR/537 detector/1235 matches CV; 162 stale rejects.
- Unequip: wall acumulado 9.952 s; medianas wall 0.906, selección→overlay 0.328, tap→efecto 0.500, efecto→ready 0.016 s. Capture 0.578 s, percepción 1.263 s, navegación Bag 0.000 s; 234 capturas/33 OCR/453 detector/1032 matches CV; 149 stale rejects.

En las 22 primitivas: **485 consultas capture**, **66 OCR**, **990 consultas detector**,
**2267 matches CV**, **311 freshness rejects**, **0 retries**. Capture total
**1.155 s**, percepción **2.453 s**, navegación Bag Equip **0.359 s**.
Entrada/Set 2 3.110 s; descubrimiento 1.656 s (incluye callback de inspección). Sus contadores focales separados están en el manifest; general perception de entrada y selección final Set 1 no se suman a los contadores de primitivas.
Capture cuenta consultas, no frames únicos/screencaps. Rechazos incluyen ticks
repetidos/barriers/edad; no prueban UI vieja del juego. Tap→efecto es latencia
observada de juego + transporte/captura/percepción; no hay medición interna del motor.
No restar CPU como si fuera tiempo puro del juego: las fases se superponen.
0.000 s de readiness es resolución del clock/same-frame proof, no latencia física cero.

## Recovery y validación

Recovery **no ejercitado live**: los 22 resultados fueron `slot_effect_verified`,
sin retry, reconciliación ni workaround. Offline: no-efecto explícito estable permite
único retry fresco en Fase A; Loading es transición; ambigüedad se reconcilia sólo
por observación pasiva de los slots Set 2 compatibles con el progreso. Efectos tardíos
no duplican inputs. Si no reconcilia, detiene y conserva progreso/estado conocido.
El fact `effect` sobrevive aunque readiness expire. No replay ni cleanup ciego.

Validación dirigida: **142 directos Meteorites** (65 procedimiento B1 +77 runtime/replay),
incluidos anclas distintas, cruce de páginas, ancla inmutable, slots 1..10, cleanup
inverso, cancelación por cada operación, fallos/ambigüedades a mitad de ambas fases,
reconciliación sin duplicación, efectos tardíos y Set 1 sólo al final. Dos precisiones
del reporte de fallos (no-efecto conocido sin pending; Set 1 incierto preserva último
Set 2 acreditado) se añadieron después del smoke y pasaron en los 65 tests B1;
no alteran la ruta positiva físicamente aceptada y no invalidan el smoke.

399 passed en directos/runtime/action/nav (incluyendo los 140 directos previos),
4 skips históricos existentes, 5 replays históricos sin corpus separados. Catálogo/
scopes 299 passed (292 válidos reutilizados +7 asserts invalidados repetidos),
35 replays históricos sin corpus separados. Los dos nuevos casos de reporte de
fallos pasan adicionalmente. TEMP inaccesible resuelto mediante basetemp nuevo local.
No suite completa. Readers/assets intactos: se reutilizan Fase A **63/63 curados**
y **513/513 negativos**; no evaluator nuevo ni global por ausencia de cambio perceptivo.

Primer arranque B1 no llegó a teléfono: faltaba DISPOSITIVO_ADB en el worktree.
Se añadió `--dotenv-path`, reutilizando la configuración local principal en memoria
sin copiar .env/seriales. Segundo arranque completó la cadena; sin desvío físico.

## Estado final y límites de integración

Set 2: **11 EMPTY**, probado por los once Unequip individuales (último efecto
sequence483). Set 1 **activo**, página1/40, tab Meteorites, **sin overlay/Loading**,
sequence500. Original visible en slot10; preservación de originales por todos los
inputs de Equip/Unequip exclusivamente en Set 2. Conjunto compartido completo
desequipado. Source/proceso/socket/forward cerrados por ProductiveRuntime.

B2/Session/Routine Settings siguen pendientes: binding por identidad y lifecycle
de preparación/cleanup, política de cancelación y entrega de progreso ambiguo al
caller. No conectar automáticamente ni cambiar de personaje. No-efecto no ejercitado
físicamente; inventarios con ancla posterior cubiertos offline, no universalizar
aceptación live. Layout Quick Menu shifted sin adquisición; sólo entry compatible
existente. No Arena, ToT ni Stages Elite. No commit/push ni inicio de B2.
