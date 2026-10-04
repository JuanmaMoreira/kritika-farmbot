# Targeted swipe — Trading Center implementado y validado

2026-10-04. Baseline `baf9b6345ece4e81c945a366a7ec350f31c4f1fb`, rama
`rebuild/stable-baseline`. Sin commit ni push. Alcance final autorizado: primitive
transversal y **un consumidor productivo, Trading Center**. La futura reutilización
prevista es ToT cuando se implemente su flow y se adquiera su GT específico; no se
implementó ni continuó una auditoría ToT. No se requieren otros consumidores ahora.

## Trading audit y autoridad

La adquisición actual confirma el tramo regular General desde Lapiz 400 hasta
Guild Commodity, conservando el orden del suffix del catálogo anterior. El prefix
histórico de cinco filas **no es el top actual**: hoy preceden ofertas temporales.
No convertir ese catálogo histórico de 22 filas en un índice absoluto vigente.

Prefix observado hoy: Ethereal Rune 1; Legendary Rune 1; cuatro Ethereal Rune 2
con costes visuales distintos (gemas verde, celeste, azul y dorada); Epic Ticket 1.
Es evidencia de esta sesión, no una promesa de siete ofertas en futuras aperturas.

| Índice relativo del suffix | Fila General observada | Caller actual |
| --- | --- | --- |
| 0 | Lapiz 400 | Anchor de navegación |
| 1 | Stamina 100 | Sin nuevo caller; distinta de Currency/Stamina 50 |
| 2 | 10M Gold Pouch | Anchor |
| 3 | Gold 10,000,000 | Sin nuevo caller |
| 4 | Sapphire 5 | Sin nuevo caller |
| 5 | Brawler's Badge | Sin nuevo caller |
| 6 | Lapiz 5 | Anchor |
| 7 | Ring (Enhance) | Anchor |
| 8 | Melee Badge | Sin nuevo caller |
| 9 | Accessory Crafting Material | Anchor |
| 10 | Weapon Crafting Material | Sin nuevo caller |
| 11 | Hero Weapon Crafting Material 10 | **Target productivo Materials** |
| 12 | Hero Armor Crafting Material | Sin nuevo caller |
| 13 | Hero Accessory Crafting Material | Anchor |
| 14 | R Ticket | Sin nuevo caller |
| 15 | K Coin | Sin nuevo caller |
| 16 | Guild Commodity 10 | Anchor de tail |

| Lista / target | Clasificación actual | Navegación productiva |
| --- | --- | --- |
| General / Materials | B: orden regular acreditado, posición requiere identidad CV | Anchor → swipe calculado → feedback → target fuerte |
| Currency / Stamina 50 | C para este cambio: primera fila ya accesible | Cero swipe; selector/cantidad/confirm/efecto existentes |
| Avatars & Keys / promociones Bronze→Silver y Silver→Gold | C para este cambio: dos primeras filas adquiridas | Cero swipe por contrato; lectores y owners existentes |

No se integran otras ofertas por estar identificadas. Los títulos sólo acreditan
posición; no prueban saldo, coste, policy ni permiso para Trade.

## Física recalibrada: coarse máximo robusto

LIVE_EVIDENCE nativa 2712×1220; stream de producción 2712×1224 (padding de encoder).
Geometría de cada input desde `frame.shape`. Pitch .1418, viewport .35–.95, lane X .33.
Swipe hacia arriba expone índices superiores. No snap-to-row; hay inercia y fases entre
filas. Guild Commodity limita el bottom, con clipping y sin progreso sostenido extra.

El protocolo inicial fechaba PNG al terminar su transferencia: podía aceptar pixels
adquiridos durante la inercia aunque el timestamp pareciera posterior al settling.
Ese protocolo se conservó como diagnóstico, pero se descartó del modelo estabilizado.
La recalibración fecha **antes de adquirir pixels** y exige acquisition-start fresco
posterior a dispatch completion +.6 s. Guard de adquisición nativa ≤5 s por coste de
transferencia; guard **productivo ≤2 s intacto**, validado con timestamps PTS reales.

| Coarse X=.33 | N | Filas min | Mediana | Max |
| --- | --- | --- | --- | --- |
| .94→.02, 250 ms, elegido | 6 | 8.62 | 8.95 | 9.51 |
| .94→0, 250 ms | 6 | 8.30 | 9.14 | 9.63 |
| .94→.02, 180 ms, incluidos seeds de directed | 33 | 8.09 | 9.06 | 10.21 |
| .94→.02, 120 ms | 3 | 7.96 | 9.75 | 9.94 |
| .94→.35, 80 ms | 3 | 4.62 | 5.61 | 5.72 |
| .94→.35, 40 ms | 3 | 3.01 | 3.01 | 6.07 |
| .945→.02, 180 ms | 3 | 3.01 | 3.01 | 3.01 |

Barrido exploratorio previo: starts .935/.94/.945/.955/.965/.98; endpoints
.35/.30/.20/.10/.02/0; duraciones 650/400/350/300/250/220/180/160/120/80/40 ms.
No todas las combinaciones se probaron. Las mediciones estabilizadas de la tabla son
la autoridad para elegir el perfil; no se promueve el mayor outlier exploratorio.
Inicio máximo útil acreditado .94; .945 y más bajos entran fuera del área fiable.
Endpoint robusto elegido .02, travel .92; llegar a Y=0 no mejoró el mínimo de las seis
muestras comparables. 120 ms registra el travel largo, pero con dispersión; 250 ms
maximiza el mínimo observado con menor dispersión entre los candidatos medidos.
No es una prueba de óptimo global ni de duración mínima absoluta en todos los layouts.
Ningún gesto adquirido desde el top actual alcanzó Materials: no se persiguió 1 total.

El coarse sólo sale del prefix variable. No necesita su longitud, identidad ni índice
absoluto. Después, la captura fresca establece el offset del suffix desde uno o varios
anchors concordantes. Sapphire 5 llena el hueco Gold Pouch parcial→Lapiz 5 parcial.
No se usa en runtime el conteo de siete ofertas empleado sólo para medir esta sesión.

## Física dirigida y ventana útil

Modelo independiente del coarse: tres muestras estabilizadas por distancia/dirección,
250 ms. Envelopes min/median/max de desplazamiento normalizado se interpolan sin
extrapolar travel máximo adquirido. Curva forward desde .94; reverse desde .36.

| Travel | Forward filas min/med/max | Reverse filas min/med/max |
| --- | --- | --- |
| .04 | .04/.06/.21 | — |
| .14 | 1.18/1.23/1.35 | 1.06/1.28/1.32 |
| .34 | 3.12/3.21/3.41 | 3.23/3.27/3.38 |
| .58 | — | 5.45/5.64/5.82 |
| .59 | 5.92/5.93/6.12 | — |
| .84 | 7.93/7.95/8.45 | — |
| .92 | 8.65/8.67/8.96 | — |

Safe visibility window conservadora del centro: **.43–.87**, objetivo **.65**. Deriva
del row completo/pitch/viewport adquiridos y margen respecto de ambos bordes. READY
exige título fuerte, geometría completa y consenso fresco; no exige centrado exacto.
La cobertura del envelope dentro de la ventana es una heurística de ranking, no una
probabilidad garantizada; luego se minimiza error de la mediana al centro. Las diez
ejecuciones finales terminaron entre Y=.551 y .695, aún dentro de la ventana útil.

Distribuciones, muestras y procedencia: [calibración](../datasets/trading_swipe_calibration.json).

## Primitive e integración

`navigate_to_target(catalog, target, profile, observe, emit, max_gestures, coarse=...)`
no importa Trading, ADB, OCR, policies ni flows. IDs opacos o índices enteros;
`columns` convierte items a filas. `ViewportReading` aporta IDs, centros, guard,
readability, sequence, revision y bounds. Offset = `index // columns - y / pitch`;
múltiples anchors deben concordar. UNKNOWN no inventa posición ni autoriza un input.

Un coarse opcional sólo se emite una vez con lista/contexto fuerte y fresco y sin
anchor. Nunca actualiza el modelo dirigido. Después opera **un único loop**:
locate → proyectar distancia → elegir gesto → emitir exactamente uno → observar fresco.
El mismo cálculo resuelve undershoot y overshoot, con escala adaptada sólo durante la
invocación y por dirección. No hay `swipe_2`, `swipe_3` ni persistencia entre mutaciones.

Budget total incluye coarse, directed y fallback. Máximo dos inversiones del driver;
progreso mínimo .1 fila, stale, guard perdido, inconsistent anchors, revision distinta,
calibration mismatch, stuck y límites detienen. Consenso posterior al último gesto
no consume budget de inputs. Telemetry cuenta correcciones/inversiones despachadas,
no planes cancelados. Bounds/layout/modelo no se heredan automáticamente a otra lista.

Registry → TradingMaterialsRuntime → ProductiveMaterialsAdapter activa targeted por
defecto; no se modificó Registry aquí. `_swipe` conserva cancelación, General positivo
y limpio, edad 0..2 s, ActionExecutor normalizado/source_sequence y fresh post-input.
MODAL bloqueante/UNKNOWN no permiten swipe. `.read` C3, MAX, C4, costes, confirm único
y efecto mantienen sus owners/policies. Stamina Currency y Keys siguen en cero swipe.

Si falla anchor/modelo/convergencia: log de fallback, descartar modelo, reacquirir
contexto y scan previo (.40413, 900 ms, gate 1.5 s, inversión bounded) con el presupuesto
restante; guard/cancel/mutación no habilitan ese fallback. No se abre Trade por navegar.

## Benchmark y aceptación del código final exacto

Baselines históricos conservados: incremental nativo **5 swipes, 12 capturas,
24.03–25.06 s**; targeted v1 **4 swipes, 7 capturas, 15.39–15.78 s**. Sus wall times
no se comparan directamente con la pipeline actual PTS. Son historia, no aceptación v2.

Comparación actual: ScrcpyFrameSource nativo con PTS, 12fps, mismo scope Trading del
caller, mismo teléfono/roster/catálogo, reset Keys→General; setup excluido. Incremental
usa la misma geometría local de título corregida: se compara navegación, no un checkout
alternado. Capturas son frames distintos consumidos por RuntimeObserver, no todos los
frames continuamente decodificados. Capturas = perception cycles en estos doce runs.

| Run | Path | Swipes | Capturas/ciclos | s | Correcciones | Inversiones | Fallbacks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v2_stream_old1 | incremental | 5 | 21 | 18.797 | 0 | 0 | 0 |
| v2_stream_old2 | incremental | 5 | 22 | 19.062 | 0 | 0 | 0 |
| v2_final1 | coarse + directed | 2 | 6 | 5.281 | 0 | 0 | 0 |
| v2_final2 | coarse + directed | 2 | 6 | 6.187 | 0 | 0 | 0 |
| v2_final3 | coarse + directed | 2 | 6 | 5.125 | 0 | 0 | 0 |
| v2_final4 | coarse + directed | 2 | 6 | 5.140 | 0 | 0 | 0 |
| v2_final5 | coarse + directed | 2 | 6 | 5.110 | 0 | 0 | 0 |
| v2_final6 | coarse + directed | 2 | 6 | 5.172 | 0 | 0 | 0 |
| v2_final7 | coarse + directed | 2 | 6 | 5.234 | 0 | 0 | 0 |
| v2_final8 | coarse + directed | 2 | 6 | 5.125 | 0 | 0 | 0 |
| v2_final9 | coarse + directed | 2 | 6 | 5.063 | 0 | 0 | 0 |
| v2_final10 | coarse + directed | 2 | 6 | 5.172 | 0 | 0 | 0 |

**N=10: 2 swipes=10; 3=0; >3=0; fallbacks=0; failures=0.** Todos tienen dos frames
frescos concordantes del target completo y los mismos SHA256 del código final. Mediana
5.156 s. La tercera intervención no apareció naturalmente en esta muestra; el mismo
loop tiene undershoot/overshoot/reverse y budget probados offline y física reverse live.
No hay garantía estadística absoluta ni porcentajes extrapolados a otros dispositivos.

| Run | Coarse filas ≈ | Coarse adquisición s | Directed gestos | Filas predicted | Actual | Y expected | Y final | Directed s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v2_final1 | 9.46 | 2.937 | 1 | 6.96 | 7.32 | 0.652 | 0.598 | 2.344 |
| v2_final2 | 8.32 | 2.937 | 1 | 8.09 | 8.32 | 0.653 | 0.619 | 3.250 |
| v2_final3 | 8.66 | 2.844 | 1 | 7.78 | 8.22 | 0.649 | 0.585 | 2.281 |
| v2_final4 | 9.49 | 2.859 | 1 | 6.96 | 6.61 | 0.647 | 0.695 | 2.281 |
| v2_final5 | 9.56 | 2.844 | 1 | 6.89 | 7.12 | 0.648 | 0.613 | 2.266 |
| v2_final6 | 9.23 | 2.875 | 1 | 7.19 | 7.01 | 0.652 | 0.674 | 2.297 |
| v2_final7 | 8.36 | 2.859 | 1 | 8.09 | 8.19 | 0.647 | 0.633 | 2.375 |
| v2_final8 | 8.65 | 2.890 | 1 | 7.78 | 7.74 | 0.650 | 0.655 | 2.235 |
| v2_final9 | 9.51 | 2.782 | 1 | 6.89 | 7.31 | 0.654 | 0.594 | 2.281 |
| v2_final10 | 8.66 | 2.844 | 1 | 7.78 | 8.46 | 0.649 | 0.551 | 2.328 |

Coarse adquisición incluye primera observación General, dispatch, settling y anchor;
no es tiempo puro del dedo. Coste inicial 2.782–2.937 s; loop dirigido y strong verify
posteriores 2.235–3.250 s. No existe autoridad barata para indexar el prefix temporal
desde el primer frame; el gesto no se sustituye por un índice inferido. Filas coarse
≈8.32–9.56 en PTS se miden con prefix acreditado sólo en esta sesión; runtime no lo usa.
Cada post-frame se reutiliza como precondición siguiente, sin emitir dos gestos ciegos.

C3 final, medida aparte: **366/40**, dos samples concordantes, 2 capturas, 3.938 s.
No se abrió Item Trade, MAX ni confirm. Otros casos con el mismo código: Materials→tail
Guild 1 swipe/5 capturas/4.563 s; tail→Materials reverse 1/4/5.609 s; target ya visible
0/2/1.344 s. Guild es un caso de adquisición/validación, no un nuevo caller productivo.

Evidencia: [benchmark con v1 preservado](../datasets/trading_targeted_benchmark.json),
[anchors](../datasets/trading_ordered_anchors_manifest.json),
[replay](../datasets/ordered_navigation_replay.json). Raw PNG/reports/helpers ignorados
en `artifacts/targeted_swipe/`; sólo nueve títulos, trece strips grises y metadata curada.

## Divergencias, fixes y validación

- Timestamp PNG al final de transferencia admitía frames durante inercia y aparentaba
  reverse equivocado. Recalibrar con acquisition-start y PTS separó causa y movimiento.
- Coarse fuerte podía caer con Gold Pouch/Lapiz 5 parciales: Sapphire 5, ya acreditado,
  aporta un anchor focalizado, sin bajar NCC .94 ni cambiar orden.
- Primer smoke v2 colocó target Y=.651 tras dos gestos, título .998, pero separadores
  devolvieron fase errónea y rechazo de target completo. Fallback completó 6 gestos;
  el run sigue rojo para aceptación v2. `target_geometry` deriva top/center del título
  adquirido (.014 desde row top) y pitch, con bounds completos y NCC .90 intacto.
  Replay causal confirma identidad y C3 366/40; no se cambió el detector global.
- Auditoría de métricas corrigió inversión fallback no contada y planes cancelados
  contados antes de dispatch; la campaña final exacta se repitió después del fix.

**145 passed**: 45 primitive nueva, 35 legacy directed-list, 22 adapter productivo,
16 replay y 27 standalone/runtime Materials. Cubren coarse sin anchor/contexto fuerte,
fresh posterior, visible target, centro útil, undershoot/overshoot en mismo loop,
budget total, bounds, stuck, modal/lost guard, cancellation, revision/mutation,
anchors contradictorios, strong target, fallback y repetición independiente.
Sin cambio perceptivo global: evaluator global no invalidado; replay focalizado y
readers/guards afectados verdes. Warning ambiental `.pytest_cache` WinError5, sin fallo.
Wiring smoke real: ProductiveMonsterWaveFlow y ProductiveMaterialsAdapter targeted
default, 9 assets, cero capturas/inputs. `git diff --check` verde.
Validación de cierre desde índice aislado: 138 tests con archivos versionados y siete
tests legacy tras aportar sus capturas locales ignoradas preexistentes; todos verdes.
Esas capturas no forman parte del checkpoint. No hubo nuevo desarrollo ni smoke live.

## Alcance, límites y worktree

Único consumidor productivo actual: **Trading Center**. Futuro previsto: **ToT**, al
implementar su flow y adquirir específicamente orden/dirección/anchor/viewport/pitch/
bounds/perfiles. No se auditó ni implementó ToT. No adopciones de otras superficies.
Character Select es dynamic-order por USER_GT; mediciones previas no establecen
identity→index persistente. Rotation, Equipment y policies económicas no cambiaron.

Prefix futuro/layout/idioma distintos o catálogo contradictorio requieren GT propio
o fallback. Modelo empírico pequeño y sin persistencia; no promete 1 swipe total.
No se forzó una tercera intervención live; se probó el mismo loop offline y reverse
físico. No hubo campaña económica/ads/consumo. Sin bugs conocidos del nuevo path.
Cleanup: teléfono en Lobby original, sources/procesos/sockets/forwards liberados por
sus owners, daemon ADB de adquisición cerrado. Ninguna ventana GUI nueva fue lanzada.

Trabajo independiente preservado: plan histórico eliminado; hunks previos Registry,
SummonPetDaily y tests portal; `check_eval.py`, `fix_tests.py`, `test_live.py`, `test_wait.py`.
Parent del checkpoint `baf9b6345ece4e81c945a366a7ec350f31c4f1fb`, branch
`rebuild/stable-baseline`. Checkpoint local independiente:
`feat: add directed trading list navigation`, **sin push**.
El status siguiente conserva el estado histórico de la entrega previa al checkpoint
(entonces sin staging/commit), incluido el trabajo independiente excluido:

```text
 M ARCHITECTURE.md
 M CONTEXT.md
 D Kritika_FarmBot_Plan_Preparacion_Codex_Astra.md
 M ROADMAP.md
 M bot/directed_list_scroll.py
 M bot/flow_registry.py
 M bot/summon_pet_daily_flow.py
 M bot/trading_materials_productive.py
 M docs/GAMEPLAY_GT.md
 M docs/RESOURCE_ROUTING.md
 M tests/test_portal_obstruction_recovery.py
 M tests/test_trading_materials_productive.py
?? assets/ui/landmarks/trading-center/ordered/
?? bot/trading_list_anchors.py
?? check_eval.py
?? datasets/ordered_navigation_replay.json
?? datasets/trading_ordered_anchors_manifest.json
?? datasets/trading_swipe_calibration.json
?? datasets/trading_targeted_benchmark.json
?? docs/TARGETED_SWIPE_AUDIT.md
?? fix_tests.py
?? test_live.py
?? test_wait.py
?? tests/fixtures/ordered_navigation/
?? tests/test_ordered_navigation.py
?? tests/test_trading_ordered_replay.py
```
