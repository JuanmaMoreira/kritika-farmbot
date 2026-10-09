# Gold Farming Cycle — investigación 2026-10-09

Estado: cerrado con **28/28 reales verificados** el 2026-10-09; campaña en siete segmentos con reanudaciones seguras, no un runtime ininterrumpido.
Estado al cierre físico previo al checkpoint: sin commit/push. Evidencia local ignorada: `artifacts/gold_cycle_20261009/`.

## Evidencia e identificación de los intentos

Los únicos dos logs locales próximos al checkpoint indicado son
`logs/20261009T031013.447283Z_session_ce769b04.jsonl` y
`logs/20261009T031451.462413Z_session_b7436bf9.jsonl`.
En UTC−3 comenzaron el **9 de octubre**, 00:10:13 y 00:14:51;
ambos registran fallo en el índice 2 y completion del índice 1.
No hay logs con nombre 20261008. Se explicita la diferencia con el reporte
del usuario; no se altera la evidencia para ajustarla al recuerdo.

El primer runtime.started precede por ~1s al commit 92667ee (00:10:14);
el segundo es posterior. Los logs no contienen hashes del código ni snapshot
de configuración completo: HEAD efectivo exacto y cambios locales cargados
**UNKNOWN**. Historial delimita dd99928→92667ee; no prueba los bytes importados.
La nueva campaña guarda hashes, rutina y ledger por ejecución.

Ambos ejecutaron basic-gold, cinco steps: Black Market → World Boss → Gold
Farming → Mailbox → Daily Quests. El config actual preservado usa WB
CURRENT_WB_NOT_PARTICIPATED, MW compra SKIP habilitada y warning no bloqueante
no declinable; relief policy compartida incluye Weapon Ethereal sin Enhance,
Socket Enhance+Sell, Craft tres categorías y Gold Keys. Config histórica
completa no archivada: comportamiento emitido es autoridad de lo ocurrido.

## A. Primer fallo

Session 4a1f148741b84237b55d3d95143bed5a; Burst Breaker terminó todos los
steps y Rotation (evento209); Stages Video0 y MW no_work, sin ad.
Kaiserin resolvió identidad (213), BM y WB completaron (263/268).
Gold oportunidad1 emitió Video (476), rechazó Video Pass Ticket (477),
observó Google AdActivity (481/482), progreso multipart y dos visitas
automáticas Finsky; Back recuperó cada visita sin CTA. Progreso final
registrado .7572 a52.906s (496). Luego no acreditó cierre; terminó por
stall61.031s a114.594s (498), terminal recovery sin nuevos inputs seguros
y AD_RECOVERY_FAILED (501). No Results/reward/cierre de personaje acreditado.

Las capturas1579/1580/1581 en failure_457cdceba7744755a472452078ce6352
muestran Google Play end card con X circular y sin sonido. USER_GT explícito
2026-10-09 confirma recompensa completa y cierre habilitado. La primera
divergencia observable es el rechazo perceptivo de esa terminal (sólo hay
frames terminales preservados al final; onset exacto UNKNOWN), no el traceback.
El detector exigía X+sonido para esa rama; replay scores originales en el
frame reducido: X .7686, sonido .1524, ambos <.94. No hubo acción incierta
ni segundo Video posterior. El resultado físico quedó en ad; recuperación
segura ahora acreditada por ese USER_GT y retorno posterior a juego en el
intento siguiente, cuya intervención intermedia no está logueada.

## B. Segundo fallo

Session 029afcbf4d6c45d4873a736c30c90e8d; Kaiserin completó rutina y
Rotation (1038). Su anuncio multipart retornó Results (549/550); Gold
completó (961/976). Dimension Manipulator resolvió identidad (1042), BM/WB
completaron (1092/1095). Stamina trade confirmó una vez (1123).
Stages encontró Equipment Full (1193), ejecutó Combine y luego Sell.
Bulk confirmó una sola vez y acreditó Item Count128→127 (1311);
relief SUCCESS (1313), ExitEquipmentInventory (1316), Lobby fresco (1319/1321).
OPEN Stage se despachó desde4681 a(.82,.28), píxel2223/342 (1323).
No cambió superficie: wait13frames/6.453s (1326), snapshot4747 RESOLVED Lobby,
sin capas y timestamp226645.218. Frames4737/4742/4747 lo confirman.
La primera divergencia es **ausencia de efecto de la navegación OPEN**;
el relief económico ya había tenido efecto verificado. No repetir Bulk.
Condición final: timeout al reconstruir caller, trasladado como stages
equipment relief FAILED (1329/1330). Lobby permite reentrada segura.
No hay evidencia para atribuir por qué Android/game ignoró ese tap.

## C. Comparación e hipótesis

Son defectos distintos. Certeza alta sobre la terminal no reconocida y sobre
OPEN sin efecto; certeza baja/UNKNOWN sobre onset terminal y causa del tap
inefectivo. No hay prueba de regresión reciente ni de acumulación: el segundo
intento completó Kaiserin, que había fallado antes, y el segundo fallo siguió
a un relief acreditado. Stages/Ads/actions no cambiaron entre ce44fe5 estable
y HEAD (salvo extensiones Arena/Meteorites discriminadas por tipo). Session
añade Meteorites sólo detrás de flag; no prueba causal para estos fallos.
Perception/resolver/capture/Quick Menu/ReliefCoordinator principales no cambiaron
en ese rango. Los cambios locales de Arena se preservan; su capacidad standalone
no se usa como prueba de wiring Gold. La nueva variante visual es variabilidad
del anuncio + cobertura insuficiente. La navegación necesita tolerar un no-effect
acreditado; llamarlo mala suerte o leak sería especulación.

## D–E. Cambios y validación inicial

Owners: AndroidAdsObserver, assets Stages (dos templates), StagesNavigation.
Sin retries genéricos, sleeps nuevos ni cambios en compras/reliefs/economía.
Los templates sólo usan chrome fijo; fixture recortada sin creative; procedencia
raw→fixture en manifest. Mantienen .94, activity/focus y freshness; Next ad suprime
cierre. OPEN reintenta una vez sólo desde Lobby posterior/fresco/sin capas.

192 tests directos iniciales y 402 afectados verdes (último incluye directos),
`artifacts/gold_cycle_20261009/tests.xml`; replays positivos/negativos y geometry
de evidencia/nativa. Evaluator incremental terminal10casos/0mismatches,
`ad_evaluator/result.json`; corpus global no invalidado.
Smoke no consumptivo Stages: Config65→Lobby92, `stages_entry/result.json`.
Smoke Gold focal con política guardada en `focal/`: dos Stages y MWs completados,
session.completed y gold_farming.completed; 474.469s incluyendo runtime.
El primer harness falló después del resultado al usar asdict sobre mappingproxy;
runtime cerró y se corrigió serialización del harness, sin repetir smoke.
Campaña: nuevo end card reproducido naturalmente dos veces en Mystic Wolf Guardian
(sequences7675/10460, cierre68.391/68.109s, retorno y rewards acreditados).
Native screenshot y metadata en campaign/run_01/store_card_terminal.*;
fixture sólo X/footer, sin creative, en tests/fixtures/ads_store_card/live_manifest.json.
Handles worker538→524 entre inicio y personaje5; RSS340.5→401.8MB,
private486.2→569.0MB. Warmup posible; no prueba ausencia de leaks futuros.

## F–I. Campaña, performance, deudas y estado final

Run01: 5/28 COMPLETE (Dimension Manipulator, Monk, Mystic Wolf Guardian,
Cat Acrobat, Crimson Assassin), 2678.532s; Flame Striker PARTIAL.
Primera nueva divergencia: selector Hero Armor/Helmet, coste49 leído con
confianza .78394<.80, reader recipe_economics_unavailable en14frames
26923→26960. No MAX ni confirm de Armor en ese intento; Weapon y Accessory
anteriores tienen efectos verificados. `after.png` conserva el selector nativo.
La ROI vieja (.480,.570,.550,.680) incluía icono/bordes; recorte sólo dígitos
(.499,.638,.526,.677) lee49/confianza1.0. Cambio mínimo en CraftReader,
threshold .80, moneda/identidad/consenso/MAX/efecto intactos.
91tests Craft/consumidores y evaluator13/13; fixture nativa sólo ROIs y negativo
sin coste en tests/fixtures/craft_cost_failure. No cambios Arena.
Cleanup físico posterior: reader verificó Craft BASE (Cancel ya había tenido
efecto tras el frame inmediato after), Back único y Lobby96 fresco;
craft_cleanup/result.json. No repetición de confirmaciones.
Run02 reanuda sólo Flame Striker desde Gold+Mailbox+Quests, conservando el
prefijo BM/WB por flow.completed del run01. Identity guard exige el mismo ID;
rutina efectiva y carry quedan por run. La campaña conserva los5COMPLETE.
Run02 terminó COMPLETE, 322.718s, Rotation y Lobby3227 fresco: acumulativo6/28.
Los22restantes comienzan run03 con la rutina completa guardada.

Run03 completó Halo Mage, Elemental Fairy y Noblia: acumulativo9/28.
Steam Walker falló antes del primer Video por `stages relief bound exhausted`.
El primer Socket relief confirmó Enhance EFFECT (3784/3882); un nuevo Start
observó Full fresco (3895), autorizando segundo relief. Este volvió a Enhance
EFFECT (3914/4016), Sell NOT_RUN; el tercer Full cortó (4029–4032).
No ad ni recompensa incierta: el problema es confundir efecto de Enhance con
headroom suficiente y repetir la misma estrategia en lugar de intentar Sell
permitido. `StagesReliefs` reduce localmente Enhance a False en la segunda
visita y conserva el permiso Sell global, límite de dos y retorno/cancelación.
149 tests de Socket/policy/Stages/Gold pasan, `socket_tests.xml`; el primer
intento tuvo ocho errores ambientales de tmp_path, resueltos usando basetemp
único dentro de artifacts, sin cambios de producto por ese fallo ambiental.
Focal recovery `socket_recovery`: dos receipts de Enhance y ausencia de Video
son precondiciones; blocker fresco exacto → Sell incompatible slot3 + nivel0
→ bulk efecto verificado (42) → retorno Stage (47/48) → Start Select Striker
sin consumo → cierre y Lobby247. No repitió Enhance, anuncios ni BM/WB.
Run04 reanuda Steam Walker desde Gold con prefijo BM/WB conservado.
Termina COMPLETE con dos rewards Stage y ambas inversiones MW verificadas,
Mailbox+Quests+Rotation; 642.156s, Lobby6436 fresco, acumulativo10/28.
En la segunda oportunidad hubo un relief Enhance con efecto y Start pudo
continuar; no se presume que toda Enhance exige Sell. Run05 comienza los18
restantes desde Eclair, sin repetir los10COMPLETE.
Run05 alcanzó14/28 y Galaxy Lord activa Craft por presión real, sin smoke extra.
Coste49/confianza1.0 en Weapon, Hero Armor/Helmet y Accessories. Armor confirma
dos batches x10 con efecto fresco999→509→19 (eventos6307/6329,
sequences20326/20441); Weapon810→320→26 y Accessory472→31 también verificados.
Esto añade validación física del fix Craft a su replay/test/evaluator previo.

Seguimiento intermedio; el cierre definitivo y la auditoría de los 28 figuran abajo.
Auditoría intermedia20/28: los cinco flow.completed por cada COMPLETE
están presentes, incluidos prefijos conservados; cero manual/controlled_unavailable.
Run05 worker mismoPID: character11→14→20 handles511→513→513;
WorkingSet336.9→319.9→324.0MB, Private475.9→568.9→761.8MB.
La retención de pixels es una explicación por implementación, no heap profile:
Session conserva FlowResult.final_snapshot de Gold/Mailbox/Quests, cada imagen
nativa2712×1224×3=9.958MB; tres imágenes≈29.875MB por personaje.
El incremento observado≈31–32MB/personaje es compatible con ese ownership
del resultado. No hay reutilización de estos frames como permiso para inputs,
ni crecimiento de handles, ni vínculo causal demostrado con los fallos originales.
No se amplía alcance con una optimización de memoria. Los resúmenes perceptivos
pueden flush-ear más tarde conservando su contexto original (RuntimeObserver);
no interpretar timestamp de emisión como reutilización de estado del personaje.
Run05 completó11 personajes consecutivos (Eclair→Rang), acumulativo21/28.
Strike Archer completó su primera recompensa y MW367→267→167→67; antes de
la segunda oportunidad, OpenTrading de Stamina no produjo efecto desde
Lobby53361 (16685/16686), timeout6.317s/53426, Lobby53434 final.
**USER_GT explícito: el usuario recibió una llamada y descalifica este fail.**
Se conserva la evidencia como interrupción externa, no regresión ni defecto
del bot; no patch/retry nuevo por este episodio. Run05 duración5305.063s.
Run06 reanuda sólo Strike Archer, con prefijo BM/WB y recursos/ads restantes
reacreditados físicamente; no repetir anuncio completo ni MW previos.
Baseline2026-10-07 fue acumulativo28/28 (2previos+26), no una sesión continua
comparable. Métricas y ledger conservados en full_roster_performance_campaign.
Inventario initial_status/initial_hashes/initial_worktree.diff identifica trabajo
independiente; INDEX vacío, rama rebuild/stable-baseline y HEAD92667ee al inicio.


## F. Cierre físico 28/28

Run06 completó Strike Archer en234.829s y regresó a Lobby2332.
Run07 completó Telumpel, Berserker, Demon Blade, Blade Dancer, Burst Breaker
 y Kaiserin sin fallos, en1970.078s; Lobby19847 sin overlays, runtime.closed5911.
Durante este último tramo hubo reliefs Socket normales con efecto y retorno;
Demon Blade, Blade Dancer y Kaiserin continuaron sin agotar el bound.

Auditoría offline `closure.json`: 28 identidades distintas, un único
session.character.completed por identidad y los cinco flow.completed por
identidad, incluyendo los prefijos BM/WB conservados en reanudaciones.
Cero PARTIAL/UNSEEN, omisiones, duplicados COMPLETE, manual_resolution,
flow.unavailable o controlled_unavailable. Los siete runtimes tienen runtime.closed.
54 ads.result RETURNED; ambos rewards y sus inversiones se verificaron según
recursos diarios frescos. No_work probado por el owner es un resultado válido,
incluido Dimension Manipulator con anuncios agotados al comenzar esta campaña.
57 Stages activity.result COMPLETED incluyen reevaluaciones sin nuevo Video
tras reanudar; ese contador no significa 57 anuncios. No se forzó un nuevo
anuncio cuando el contador diario fresco estaba agotado.

Dos stops atribuibles al bot durante la nueva campaña: Craft ROI en Flame
Striker y estrategia Socket en Steam Walker, ambos corregidos y recuperados.
Run05 mantiene session.failed como evidencia cruda, pero se excluye de fallos
del bot por USER_GT de llamada externa. No se modificó el producto por ese caso.
No se reinició el roster: sólo Flame Striker, Steam Walker y Strike Archer
reanudaron sus partes pendientes con identidad física y recursos reacreditados.
El máximo tramo de cierres consecutivos fue11, Eclair→Rang.

Tiempo de runtimes de campaña: **12391.891s = 3h26m31.9s**.
Ventana inicio→cierre: **13290.188s = 3h41m30.2s**, incluye14m58.3s entre
segmentos para diagnóstico/corrección/cleanup. Smokes, replays, tests y lectura
final del teléfono quedan fuera del tiempo de campaña. Los tiempos por identidad
suman sus segmentos activos, incluidos los fallidos; excluyen gaps y smokes.
`characters.csv` contiene inicio/fin UTC, orden, segmentos, duración y resultado.
`audit.json` conserva timelines con acciones, guards/waits, recursos y flows.

| Orden | Identidad | Activo (s) | Baseline observado (s) | Segmentos |
| --- | --- | ---: | ---: | --- |
| 1 | dimension_manipulator | 44.4 | 388.7 | run_01 |
| 2 | monk | 533.4 | 804.9 | run_01 |
| 3 | mystic_wolf_guardian | 748.9 | 567.0 | run_01 |
| 4 | cat_acrobat | 479.9 | 538.0 | run_01 |
| 5 | crimson_assassin | 545.1 | 535.8 | run_01 |
| 6 | flame_striker | 636.0 | 552.8 | run_01, run_02 |
| 7 | halo_mage | 366.9 | 819.5 | run_03 |
| 8 | elemental_fairy | 348.6 | 861.5 | run_03 |
| 9 | noblia | 461.3 | 602.9 | run_03 |
| 10 | steam_walker | 690.5 | 634.0 | run_03, run_04 |
| 11 | eclair | 486.1 | 528.8 | run_05 |
| 12 | wandering_master | 389.3 | 563.0 | run_05 |
| 13 | shadow_mage | 370.4 | 682.6 | run_05 |
| 14 | blood_demon | 459.7 | 647.6 | run_05 |
| 15 | galaxy_lord | 569.1 | 688.7 | run_05 |
| 16 | hastati | 472.4 | 657.5 | run_05 |
| 17 | dark_valkyrie | 526.9 | 757.5 | run_05 |
| 18 | ice_warlock | 350.8 | 596.7 | run_05 |
| 19 | eilla | 423.0 | 677.8 | run_05 |
| 20 | lina | 386.2 | 630.8 | run_05 |
| 21 | rang | 720.1 | 533.3 | run_05 |
| 22 | strike_archer | 371.3 | 546.6 | run_05, run_06 |
| 23 | telumpel | 347.7 | 630.4 | run_07 |
| 24 | berserker | 277.1 | 637.1 | run_07 |
| 25 | demon_blade | 306.9 | 588.6 | run_07 |
| 26 | blade_dancer | 382.2 | 1059.4 | run_07 |
| 27 | burst_breaker | 337.5 | sin log comparable | run_07 |
| 28 | kaiserin | 311.6 | sin log comparable | run_07 |


## G. Performance y confiabilidad

Baseline Oct7: cobertura acumulativa28 (dos ya completos y26 completados
por los seis logs disponibles),16798.079s de runtimes registrados=4h39m58.1s.
No hay registro completo de duración para los dos previos. Tabla por identidad
usa sólo logs observados y no extrapola los faltantes. No es una comparación
controlada: en baseline WB ejecutó25 flows productivos (2679.428s, mediana109.369s)
y cinco skips; hoy WB acreditó no_work en los28, sin ese coste productivo.
Stocks, reliefs, anuncios disponibles y latencias también difieren. Menor tiempo
bruto no demuestra una aceleración causada por estos fixes.

Medianas por invocación, incluyendo invocaciones fallidas/reanudadas:
Gold431.971→339.104s, Black Market8.705→9.412s, Mailbox10.857→8.859s,
Quests7.141→7.250s. Gold ocupa11254.974s en31 invocaciones y sigue siendo el
flow dominante. WB no_work no emite flow.started: su ausencia de duración en
esa tabla se identifica, no se computa como coste cero del control completo.
Mediana activa por personaje nueva406.167s. Los más lentos: Mystic Wolf
Guardian748.9s (anuncios largos), Rang720.1s (routing Keys/Treasure/Craft),
Steam Walker690.5s y Flame Striker636.0s (incluyen segmentos fallidos).
No runtime_wait.completed superó10s en los logs de ambas campañas; los
anuncios largos tienen lifecycle propio. No se introdujeron sleeps.

Percepción:32122→27791 análisis; media0.250160→0.272921s (+9.1% bruto),
compute8035.638→7584.756s. El máximo nuevo3.131s frente a4.399s del baseline.
La diferencia de corpus/workload impide atribuir ese promedio al detector nuevo;
no se amplía el frente con una optimización global. Un escenario terminal
natural diferente del original también retornó con reward, sin creative como señal.

Recuperaciones/eventos de nueva campaña:53 Equipment reliefs,31 Socket reliefs,
32 stages.relief y tres transition.retry del owner existente. No hubo stages.entry.retry
natural: el caso no-effect específico queda cubierto determinísticamente y la
entrada/salida real focal acredita la navegación, sin fabricar fallos del juego.
63 ConfirmEquipmentBulkSale,107 ConfirmTradingTrade y24 ConfirmCraftMaterial
son inputs registrados, no un saldo monetario calculado. Los efectos y recursos
concretos están en los timelines/receipts; el Sell focal de Socket es externo a
estos conteos de campaña. No se repitieron confirmaciones por un timeout.

Handles estables y memoria retenida por resultados se documentan arriba.
No evidencia causal de estado cruzado/stale frames/crecimiento de handles que
explique los dos fallos originales. La retención de snapshots por Session es
acotada al runtime y queda como observación de coste, sin rediseño.

## H. Límites y deudas

Los bytes/código efectivo y config completa de los intentos originales son
UNKNOWN; el historial y el comportamiento registrado sólo delimitan posibilidades.
Onset exacto de terminal original y motivo físico del tap OPEN ignorado siguen
UNKNOWN. No atribuir regresión a 92667ee por proximidad temporal.
No se acredita un único proceso28/28 ininterrumpido: sí los28 completos reales
con cierres y reanudaciones. Variantes publicitarias no cubiertas deben seguir
parando con bounds; una X genérica o UNKNOWN no autoriza cerrar.
La segunda estrategia Socket fue probada determinísticamente y con recovery
focal basado en el blocker y dos efectos previos; no hubo un nuevo doble-Full
natural posterior que requiriera ese segundo Sell en la campaña.
Baseline y sesión nueva difieren en trabajo, economía y recursos; no afirmar
speedup causal ni leak basado únicamente en media/RSS. La llamada se conserva
como interrupción externa descalificada. No se ejecutaron Manual Stages ni Arena.

## I. Estado final y preservación

Teléfono conectado, Kritika en Lobby limpio de Dimension Manipulator/Drakenn22,
tras la rotación final. Observación posterior sin inputs: final_phone/result.json,
sequences5→11, BASE Lobby sin overlays; imagen after.png muestra
Gold8538914001,Karats106447,Stamina71/440,Survival77/102,Badges106/106.
No operación física activa o incierta. Todos los runtimes/sources de campaña,
smokes y observación final cerrados. Sin Python/scrcpy propios activos ni forwards
ADB; permanece el servidor ADB compartido preexistente, no se lo mata.

Rama rebuild/stable-baseline, HEAD92667ee26c11d8c90bc54b4d2faeeebcc7a274de,
INDEX vacío; sin commit/push/staging. Arena y trabajo independiente preservados
por comparación SHA256 de57 paths iniciales: sólo ARCHITECTURE, ads_manager,
GAMEPLAY_GT y la actualización final de CONTEXT tienen hunks Gold compartidos.
El contenido previo de CONTEXT se conserva íntegro después del encabezado Gold.
Cambios propios además: stages_runtime,craft_reader,stages_reliefs,
assets/profile+dos landmarks,regresiones/fixtures,herramientas Gold y este informe.
initial_status/initial_worktree.diff/initial_hashes y final_state.json permiten
separar trabajo preexistente de los cambios de esta tarea; artifacts/logs no se
versionan. git diff --check sin errores. Validaciones afectadas reutilizadas:
402 tests iniciales,91 Craft,149 Socket/Stages/Gold;10/10 Ads evaluator y13/13
Craft evaluator, además de replays y smokes descritos. Los conteos de suites
pueden solaparse; no se suman como tests únicos. No se invalidó Arena.


## Checkpoint de estabilización Gold

Publicación aislada sobre92667ee en rebuild/stable-baseline, autorizada después
del cierre físico. Publica exclusivamente Ads Store end card sin sonido,
reentrada Stages OPEN desde Lobby fresco, ROI de coste Craft y segunda estrategia
Socket, con regresiones, crops curados, evaluator Ads y documentación relacionada.
El commit de este archivo es la identidad del checkpoint; el HEAD92667ee y el
INDEX vacío de la sección anterior describen el estado anterior a su publicación.

Se preservan sin publicar Arena Farming Cycle, Manual Stages pendiente y los
arreglos históricos locales de progreso Ads inset, MW readiness, payment-wrap
Sell, Summon y demás trabajo independiente. Las herramientas de adquisición y
campaña Gold quedan locales; sus artifacts son evidencia histórica, no una
dependencia de los tests/crops publicados. La campaña28/28 se ejecutó con esos
cambios residuales presentes: acredita el worktree físico de entonces, no el
snapshot aislado. Los tests/replays/evaluadores del snapshot aislado complementan
esa evidencia y verifican que los cuatro fixes no dependen de hunks sin publicar.
No se repiten campaña ni smokes físicos para este checkpoint.


Validación adicional de publicación: copia de los27 paths staged sobre el
baseline, sin código residual. 504 tests afectados verdes en31 archivos;
496 son autocontenidos y ocho tests ya existentes requieren22 capturas históricas
ignoradas, copiadas sólo como datos con hashes verificados. Las regresiones nuevas
usan exclusivamente fixtures curados publicados. Primer intento:23 errores de
setup por directorio padre temporal ausente, corregidos sin cambiar producto;
ocho fallos por corpus externo ausente, separados y reejecutados con esos datos.
Ads evaluator10/10 sin mismatches en el snapshot; Craft13/13 dentro del test de
corpus histórico. Integridad SHA256/geometría de crops y PNGs runtime verificada.
git diff --cached --check limpio. No teléfono/ADB durante el checkpoint.
Evidencia local: artifacts/gold_checkpoint_20261009/ (XML, hashes y diff staged).
