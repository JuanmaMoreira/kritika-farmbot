# Estado actual — Kritika FarmBot

## Arena Farming — Session Report analítico y checkpoint 2026-10-09

Proyección por ocurrencia sin IO/OCR/input: resumen visible y tabla de batches
expandible en GUI. Receipts únicos por batch/operación, conflictos y ausentes N/D;
winrate ponderado408/336/72→82,35%, x8 íntegro51/42/9. Replay Crimson real:
6Manual/4MW, ledger360/360, Sapphire408/400, TC100/400KCoins, RELEASED11/11.
Duración histórica sólo routing observado49m53,965s; runtime51m09,776s separado.
Owners registran vínculo causal/multiplicador/wall y coste confirmado ya conocidos;
wall de ciclo nueva conservada al reanudar en misma instancia. Sin nuevo gameplay.
GUI revisada con replay offline; ninguna Session ni acceso al teléfono.
Gold/Single/Auto y reportes antiguos siguen compatibles. Checkpoint aislado por
paths/hunks; Ads multipart, Equipment payment wrap, MW readiness scope, Summon Pet,
helpers Gold y eliminación histórica del plan permanecen fuera.
[Fuentes, snapshot y validación](docs/ARENA_FARMING_CHECKPOINT_20261009.md).
Snapshot afectado:1055passed; evaluatorsArena9/Manual20/Stamina3, wrong0.
Suite amplia5085passed/296failed/27skipped; mismos296 fallos reproducidos en
parent limpio, sin test nuevo fallando. INDEX130paths/hunks; residual preservado.

## Arena Farming — aceptación GUI integral PASS 2026-10-09

GUI real `a360`, Characters1: Arena único/Farming40/100/80, máximo360,
Change MeteoritesON, Apply/Save/recarga acreditados; rutinas previas preservadas.
Crimson Assassin/Drakenn09 (`crimson_assassin`), necesita Shared para Rion09.
Run `ffb31f514a074ad5bcb82db1e17874d4`, Session `d6205777fdc14ecd971a28b4095b20a5`:
once Equip→READY21.866s; seis Manual Rion09, cuatro MW, cuatro Arena.
Controller nuevo Hard104/80→Hard104/88→Normal96/72→Normal104/96; próximaHard
por recent_reward_advantage, no otro batch elegible. Sin Easy0.
Claim comprobado antes de déficit; compra anticipada única100Stamina/400KCoins,
282→382, una confirmación. Ledger nuevo0→6×60=360/restante0; saldo final físico
27Stamina/88Sapphires/2Badges. Corte funcional stamina_budget_reached.
Cleanup normal once Unequip→Set2vacío→Set1original→RELEASED16.389s;
CP41,829,408 restaurado. SessionCOMPLETED, processed1/advance1, runtime cerrado
51m09.776s. Rotation habitual sólo después de cleanup; Lobby limpio del siguiente
HUD DRAKEN六FS, sin setup/farming sobre él. Probe final independiente sin overlays.

Primer setup interrumpido tras7Equip recuperado íntegro, cero farming. USER_GT:
panel informativo por tap mantenido/cierre lateral; causa del hold Android no
demostrada por dispatch ADB. Fix local positivo+cierre/reselect único antes de
Equip, estado fresco idéntico, sin retry económico;197tests afectados pasan.
Primer farming parcial: Hard104/88, dosRion09/ledger120, compra250/1000KCoins;
tercera preparación PenanceON tras Equipment relief no reconocido. Corte seguro
MANUAL_RESOLUTION, recovery onceUnequip/Set1/Lobby; nueva Session independiente,
sin reconstruir ledger120. Template local ON threshold0.94 intacto;129tests y
cinco casos existentes de evaluator correctos. PASS ejercitó dosreliefsPenance.
Reporte GUI antiguo mostraba assessmentunavailable pese a COMPLETED: fix local
SessionReport para eventos conocidos y terminación budget/Easy0; replay71 eventos
reales y116tests afectados pasan, unknown/fallos/relief incierto preservados.
GUI abierta conserva la proyección previa; no necesita otro farming.

Campaña total480Stamina causal,350comprada/1400KCoins; PASS sólo360/400KCoins.
[Informe completo y evidencia](docs/ARENA_E2E_ACCEPTANCE_20261009.md).
Sin commit/push/staging; baseline c607b601, rebuild/stable-baseline, todo trabajo
previo preservado. Cleanup completo y alcance cerrado; no iniciar otro frente.

## Arena Farming — presupuesto/abastecimiento Stamina 2026-10-09

Campo opcional Maximum Stamina Consumption sólo Farming Step Settings;
Apply/Save/recarga conservadores, vacío sin límite. Ledger por ejecución/carácter,
receipts de60 por entrada física (fallida también), independiente de Claim,
compra y regeneración;500→ocho entradas480. Preparación anticipada única con
presupuesto, sólo en ruta Manual después de Claim y refresh; sin presupuesto,
refill sólo al faltar60. `StaminaPurchase.supply` reutiliza TC/KCoin200→50,
demanda parametrizada, cap/coste/cobertura frescos, Trade único, efecto/retorno.
Ads conserva300 y protocolo previo. Parcial/imposible funcional con saldo real;
UNKNOWN no repite Trade. Reanudación en misma instancia conserva ledger y
preparación, reconcilia entrada/pago pendientes antes de más consumo. No resume
durable de Session al cerrar proceso, ni REPEAT_CURRENT/controller alterado.
Easy0 puede terminar con Stamina comprada sobrante; Session/Meteorites intactos.

USER_GT posterior: Manual buffs1/2/3ON sólo selección/effect, cero OCR contadores;
cuarto coverage/insufOFF sin Karats como último Arena. Divergencia live: config
se resolvía durante animación antes de Hell legible; fix espera señal conocida
bounded, sin nuevo template/threshold/tap UNKNOWN.

Live: Cat Acrobat `payment_inspect_02`:140471KCoins/200,1/20, cero compras.
`cycle_supply_01`: Claim57→87; una compra50 por200→137; preparación registrada;
stopped antes de Start por dificultad transitoria, ceroStamina consumida.
Tras cierre verificado, `cycle_prepared_retry_02`: ceroTC compras, Chaos06Hell,
socket relief transversal, AutoON, Clear Time, Home retry guardado→Lobby limpio.
137→78 por entrada60 más regeneración1;66→110Sapphires (+44); receipt60,
remaining60/presupuesto120, siguiente routing MW para esa occurrence107/100.
Bound smoke1operación, Session y Lobby probe COMPLETED. No nuevo batch Arena/MW.
Estado final medido: Cat Acrobat, Lobby limpio,78Stamina/110Sapphires/106Badges,
runtime/source cerrados; worktree preservado, sin commit/push.
Validación afectada584tests +132receipt/cycle y57del ciclo tras últimos guards; evaluator
de pago3/3. Reporte y límites en [informe](docs/ARENA_STAMINA_VALIDATION_20261009.md).

## Manual Stages — tercera rama Arena completada 2026-10-09

Owner productivo conectado a Farming Cycle: identidad fuerte o once efectos
Shared Meteorites acreditados→Rion09/Penance; resto→Chaos06/Hell. No Stage08 ni
reequipamiento por entrada. Stamina≥60 y Sapphire<capacidad frescos; x4 sólo en
BASE, MaoSupport del owner Ads, buffs1/2ON sin OCR de contador, buff3con ticket y
buff4ticket seguro sin Karats. Dos Start distintos, una entrada, AutoON adquirido
antes de pausa30s/polling1.5s; Clear Time overlay y Home→Lobby.

Smokes: Burst Breaker Rion09 produjo29→71Sapphires (+42). Blade Dancer sin set
verificado completó Chaos06Hell, Clear Time31s,28→68Sapphires (+40), Stamina
89→Claim119→59 (coste60). Socket relief transversal recuperó configuración y
SupportACTIVE; un único Start en Select Striker. Home temprano sin efecto admite
un retry sólo con Clear fresco, validado live. Nueva invocación con59Stamina
terminó `stamina_insufficient`; Session siguió al siguiente paso y COMPLETED.

Regresión AutoOFF de Monk corregida: brillo del bisel estático no cuenta; destellos
laterales en ventana2s distinguen ON/OFF. Muerte→Abandon→Get stronger→X adquirida.
Capacidad llena explica primer Rion sin ganancia129→129; ahora es precondición.
USER_GT vigente Arena buffs1/2: activar y verificar ON, sin contadores/gates; x2
insuficiente queda OFF y Arena sigue. Controlador adaptativo intacto.

Tests dirigidos/regresiones afectados PASS; evaluator Manual20/20 (18reusados,
2nuevos), recursos Arena9/9. Cadena Manual→MW→Arena validada por composición/tests;
smokes previos MW y Arena reutilizados, sin otro batch largo ni campaña28/28.
Shared Meteorites conserva setup/cleanup al final del personaje; integración
Session/scope verificada offline. Límites/evidencia en
[informe Manual](docs/MANUAL_STAGES_VALIDATION_20261009.md).

Final: Blade Dancer, Lobby limpio,59Stamina/68Sapphires/106Badges, runtime y sources
cerrados. Baseline c607b601 intacta, `rebuild/stable-baseline`, sin commit/push;
Arena no publicado y todo trabajo independiente preservados. Los estados físicos
de los informes anteriores son los finales de sus respectivos smokes.

## Gold Farming Cycle — 28/28 verificado 2026-10-09

Campaña real de los28 completada con reanudaciones seguras; cinco flows y cierre
por identidad,54 anuncios retornados, runtime activo3h26m31.9s. Fallos originales:
terminal Store end card sin sonido no reconocida y OPEN Stage sin efecto desde
Lobby fresco. Fixes acotados Ads/Stages; durante campaña se corrigieron ROI de
coste Craft y segunda estrategia Socket. Llamada externa descalificada por USER_GT.
Sin regresión reciente ni acumulación causal demostradas. Teléfono Lobby limpio,
runtimes cerrados. Checkpoint Gold aislado sobre92667ee; Arena y trabajo histórico
permanecen locales, fuera de este checkpoint. [Diagnóstico, evidencia y límites](docs/GOLD_CYCLE_DIAGNOSIS_20261009.md).

## Arena Farming Cycle — implementación y validación focal 2026-10-09

Un único paso Arena: Single Battle / Auto Repeat B2 conservados, tercer modo
Farming Cycle con thresholds por ocurrencia40/100/80, Apply/Save compatible y sin
dificultad fija visible. Coordinator propio, controller reciente por ejecución,
siempre ArenaFlow AUTO_REPEAT x8 y MW productivo `run_resource_pass()` de un pase.
Routing exacto por saldos nativos frescos; Manual Stages es owner independiente
conectado, con cierre y validación descritos arriba.
No REPEAT_CURRENT. [Contrato/policy](docs/ARENA_FARMING_CYCLE.md).

Smoke real en Dimension Manipulator: Hard112used/112won,119→7Badges,
Karats103165→103277, Gold6930610473 intacto. Un único Start, wait continuo526.906s,
175observaciones, intervalo medio3.028s/máximo3.172s, cero OCR y sin handoff.
Autonomía prolongada acreditada para ese batch, no campaña multi-ciclo.
Refresh expuso100Sapphires; MW anterior devolvía no_work por presión102.
Fix de composición local: operación MW de generación única, guards/economía/
board/planner/reliefs existentes; `run()`/`prepared()` de Gold mantienen presión.
Smoke MW focal posterior:100→0Sapphires,7→106Badges, CLEAR y consumo frescos;
Lobby y paso posterior Session COMPLETED, bound de smoke1operación.

Primer smoke se detuvo sin gasto/Start por OCR del stock999: margen negro focal
en buffs conserva gate>=.95/color-gris; no cambia lectura Badge/result ni precios.
Recuperación pre-start con tres Back adquiridos. No se repitió el batch largo;
repetición de MW sólo validó la operación nueva. Evaluator incremental9/9,
cinco resultados reutilizados y cuatro crops live nuevos calculados.

Final físico Lobby limpio, Dimension Manipulator,106Badges,0Sapphires,
Gold7127809094,Karats103277; sin operación activa. Runtimes/sources cerrados.
Persisten derrota Single, modal informativo de umbral,
Gold agotamiento buffs, cancelación física y retorno tras relief. Validación y
residual del worktree: [informe](docs/ARENA_FARMING_VALIDATION_20261009.md).
Sin commit/push; cambios independientes Ads/MW/Sell/Summon y demás preservados.

## Arena B2 — operación y rutina validadas 2026-10-08

ArenaFlow SINGLE_BATTLE/AUTO_REPEAT, dificultad por ocurrencia y retorno externo
Lobby implementados reutilizando B1. Editor draft/Apply/Save persiste modos distintos;
default nuevo SINGLE_BATTLE/EASY, Arena OFF en defaults existentes. Single posee
receipt/reader/result propios (VICTORY, consumo8/deltaKarats8, sin won_tickets).
Start individual automático, WIN OVERLAY sobre BASE Arena Battle, cierre a selección;
Back adquirido a Select Mode Arena distinto de Survival y luego Lobby. QM→Lobby
adquirido pero no cambia navegación global. Gold buff1 autorizado/acreditado a3000
por faltante, sólo entrada8 con controles antes/después; nunca Karats.

Smoke continuo productivo EASY x8:90→82badges,101084→101092Karats,24000Gold para
buff1; único Start, cero OCR durante wait, resultado/cierre/retorno y siguiente
paso Session de sólo lectura COMPLETED. Adquisición+smoke fallido recuperado+
única repetición causal:3 entradas/24badges/24Karats,54000Gold total. Fallos CV
de pausa/prompt corregidos con fixtures; los stops no repitieron Start. El test
continuo Single no acredita autonomía prolongada de Auto Repeat B1.

Final físico Lobby limpio,82badges,Gold9045329472,Karats101092; runtime cerrado.
Deudas: derrota individual, Goldbuff2/batches largos, umbral de puntos, cancelación
física, Upon DefeatON, refund3 y retorno tras relief. Sin controller/Farming Cycle/
Manual Stages/REPEAT_CURRENT ni generación MW. B2 aceptado; checkpoint aislado
Arena A/B1/B2 autorizado, conservando trabajo independiente. Evidencia, gaps y
validación: [B2](docs/ARENA_B2_20261008.md).

Checkpoint de publicación: revisión aislada Arena A/B1/B2,966tests PASS;
11fallos GUI functional reproducidos en baseline y separados de Arena. Evidencia
live/evaluators B2 reutilizados, sin teléfono ni otro batch.

## Arena A+B1 — checkpoint anterior 2026-10-08

USER_GT cierra Acquired Karats→won_tickets, independiente de Double Points
(sólo duplica Victory Points). Batch adquirido EASY x8:104used/104won,100%.
ArenaVisuals/Detector, catálogo/scopes, result reader tipado y wait focal pasivo
implementados; validación offline/corpus en [informe](docs/ARENA_HIL_ACQUISITION_20261008.md).
ArenaFlow standalone B1 ejecuta un batch x8 por invocación, dificultad explícita,
entrada Lobby→Battle→Select Mode→Arena→Challenge y salida BASE Arena limpio al
caller. Buffs/stock sin compras, inicio interno único, wait focal cancelable,
reader y cierre positivo; [B1](docs/ARENA_B1_20261008.md). Único smoke autorizado:
50→2Badges,48used/48won,100%, sin compras. Hubo interrupciones del observer,
handoff pasivo y cleanup verificado; no aceptación continua/performance de wait largo.
New Ranking de entrada y configuración transitoria incorporados; retorno no acepta
Challenge detrás de Insufficient y maneja aparición tardía sin repetir OK.
Sin controller, Farming Cycle,
Manual Stages ni REPEAT_CURRENT; no wiring de rutina/Rotation ni generadores MW.
Modal informativo de umbral: existencia/clase MODAL USER_GT; título/umbral/cierre
pendientes de adquisición natural, sin detector ni taps ciegos. QM, cancelación y
Start standalone siguen pendientes. Final físico: Challenge EASY limpio BASE Arena,
2Badges, x8ON, buffsON707/796/887; Gold6436020953, Karats101068.
Sources/procesos del bot cerrados; teléfono conserva ese estado. No otro batch.
Sin commit/push; trabajo independiente preservado. No iniciar siguiente frente.

## Shared Meteorites A+B1+B2 — checkpoint 2026-10-08

Preparación transversal por personaje: Change Meteorites en Routine Settings,
default OFF; Apply al draft/Save persistente. Session acredita stable ID, setup
antes de pasos y cleanup después de todos, antes de Rotation/completion. Excepciones
berserker/demon_blade/kaiserin; burst_breaker incluido. UNKNOWN no equipa, FAILED
no libera a ciegas, Stop Safely sólo READY y contexto seguro. Ejecuciones nuevas
no reutilizan READY; incertidumbre exige preparación manual antes de reanudar.

Acceptance preservada: A3+3 con selección desde slots; B1 once+once/ancla15;
B2 Telumpel once→Send Stamina→once→Set 1, ancla14/Flare1, sin retries/Ads/Rotation/
compras. Set 2 vacío, compartidos desequipados, Set 1 activo y originales preservados,
sin overlay/Loading. B2 setup26.411s/cleanup27.155s, coordinator9.606ms;
I/O evidencia23.830s separado. Sin nuevo smoke ni cambios físicos de checkpoint.

[Checkpoint](docs/SHARED_METEORITES_CHECKPOINT.md) posee selección/INDEX portable,
procedencia, exclusiones y publicación; [A](docs/METEORITES_PHASE_A_20261008.md),
[B1](docs/METEORITES_B1_20261008.md), [B2](docs/METEORITES_B2_20261008.md) poseen detalle.
31 assets y28fixtures focales hash-verificables; raw/full-curated externos no son
requisitos de pytest. No-efecto live y QM shifted no adquiridos; Arena/REPEAT_CURRENT/
ToT/Elite no implementados. No iniciar otro frente automáticamente.

## Campaña acumulativa Stability + Performance cerrada — 2026-10-07

28/28 stable `character_id` COMPLETE hoy: inicial2COMPLETE/1PARTIAL/25UNSEEN;
26 restantes acreditados acumulativamente, sin reiniciar cobertura. Runs03:9,
04:2,05:14,06:1 nuevos;02 preflight STOPPED y01 fallo de instrumentación.
Run06 Blade Dancer completó rutina y Rotation; runtime cerrado. Ledger,
procedencia, métricas/versiones y reporte en
`artifacts/full_roster_performance_campaign/` (ignorados).

Fixes locales nuevos: Stages permite un segundo Socket relief normal sólo tras
efecto y blocker fresco (Yes, no salida No); MW prepara de nuevo SKIP en pass
si observa NEEDS/READY fresco tras relief; Capture impide que PTS atrasado
sobrescriba una adquisición más reciente. Blade Dancer tuvo un stall compatible
con trabón PC (native7.36/11.32s, Config correcto pero viejo); causa OS específica
no acreditada. La carrera de publicación sí fue reproducida y corregida, sin
relabeling, gate más amplio ni input stale. Retry target1 SUCCESS.

Performance adoptada con medición: Stages handoff stream≤150ms antes del fallback
nativo; scope existente4detectors sólo dentro de Stages verificado. Lobby entry
y completion conservan percepción completa. Misma cadena live n4/variante:
A→B median9.420→4.957s, native16→1; stream reads64→153, no son capturas
físicas ni ahorro de compute total. Mismo frame n30:81→4detectors,375.46→46.58ms
mediana de cómputo; producto final D2smokes, median5.345s/native1 separados.
Validación: Socket142tests, MW172, Capture47; Stages performance161 afectados,
13replays equivalentes,12cadenas comparativas +2smokes de código productivo final.
Equipment cromático natural:72Bulk SUCCESS, todos1confirm;51Ads returned durante
campaña. Dos snapshots informativos de recursos rechazados por confianza<.95,
sin acreditar valores. Trading confirm p951593ms/max1688ms (gate2s) queda como
candidato medido sin patch especulativo. Cierre conjunto autorizado; aceptación y
separación en [checkpoint causal](docs/FULL_ROSTER_STABILITY_PERFORMANCE_CHECKPOINT.md).
Cierre offline: worktree1155/0failed/0skipped/3deselected; INDEX portable
1126/0failed/12skipped/20deselected (corpus históricos ausentes separados).
Arena/Open Pets no iniciados. Trabajo histórico/local independiente preservado.

## Equipment Sell — smoke físico cromático SUCCESS 2026-10-07

Ownership PC/teléfono/ADB autorizado por usuario; Inventory ya abierto en
Drakenn22, página8/22, count135/128. Un único candidato slot15/índice127:
Laoku's Destructive Gear físico, Helmet no Enhance. Tier LEGENDARY desde título
naranja,2141 pixels interiores/22 glyphs, soporte/margen.9981317; selected-name
OCR0, fact.name vacío. Subtype OCR.99844, Sell/guard visual positivos; policy
productiva vigente autorizó. Select slot→Sell→ConfirmEquipmentBulkSale, exactamente
un Sell intent y una confirmación. Item Count confirmado **135→134**, delta1;
outcome SUCCESS/item_count_decreased. Sigue Full134/128: se detuvo tras el Bulk
focal autorizado, sin otras ventas ni expansión.

El popup volvió a leer `Laoku's Desructive Gear`, confianza.99925/.99926. Binding
causal panel1295→OpenSell frame1302→popup1338/1357, sin input intermedio,
source_item_sequence1295 y group equipment_grade exacto. Count after1412/1416.
NCC title.998255<.999 activó una relectura semántica bounded sin input, exitosa;
no divergencia ni patch productivo. Capturas verificadas, source cerrado,
Inventory final limpio. Sin Back ni confirm/retry adicional.

Live4 muestras: capture timestamp PTS→tier mediana146.4ms/rango95.6–221.4;
→detail224.9ms/rango189.6–299.4; procesamiento detail86ms/rango63–94.
Reloj monotonic local con granularidad≈16ms, valores aproximados y sin p95 n4;
tier processing debajo de esa granularidad, no coste cero. Edad al Sell del
panel ligado533.6ms/revalidación fresca299.4ms; popup al confirm609ms, gate2s.
OCR detail1/muestra,4 total; nombre0. No demuestra mejora end-to-end frente al
old live; benchmark offline anterior sin captura sigue independiente.

Gear y popup live curados como nuevos replays con hashes (corpus20 contextos,
seis nombres Legendary); no inventar pixels históricos de fd48d8bf. Validación
smoke-sensitive:9 replays nuevos +63 binding/selected-panel passed; sin repetir
543 ni modificar código productivo. Evidencia/métricas/resultados en
`artifacts/equipment_color_validation/live_smoke_20261007/report.md`.
Sin commit/push/staging/28/28; trabajo local independiente preservado.

## Equipment Sell — tier por tinta del título 2026-10-07

Selected detail productivo ya no transcribe el nombre libre ni usa grade OCR
como tier authority. Reader focal separa tinta interior del título por color,
soporte y margen; UNKNOWN no autoriza. Mapping físico curado: Poor blanco,
Normal verde, Rare azul, Epic violeta/magenta, Legendary naranja; Ethereal y E+
comparten rojo y requieren distinguir visualmente su marcador de grade. Enhance
usa marcador visual genérico. Subtype mantiene un OCR focal del suffix finito;
el API de autorización existente exige ese tipo para todos los tiers. Inventory
y popup conservan sus OCR estructurales y grupos Bulk exactos. El harness HIL
opcional con nombre humano aprobado conserva su guard adicional separado.

Facts cromáticos omiten el nombre del consenso/recheck semántico bajo candidate,
continuidad visual e input lineage existentes. Binding causal panel→Sell→popup
fresco sin input intermedio sigue vigente; regression Destructive/Desructive
pasó, incluido fact cromático sin nombre. No cambian ReliefPolicy, E+ protegido,
confirmación única, Item Count efecto ni cancelación/retries. Corpus inicial18 contextos
incluye cinco nombres Legendary, otros tiers, Enhance, negativos y variaciones
de captura/AA/brillo/escala. Failures Earrings/Phantom/Shortsword tienen panel
replay; Shortsword repetido usa el mismo item, Gear sólo log/regression semántico
porque no quedaron pixels seleccionados. Sus causas históricas fueron popup,
no un fallo demostrado del tier seleccionado.

Validación:543 tests focales consolidados passed +4 directos del harness;
evaluator Equipment Sell14/14. Benchmark120 muestras/frame nativo: tier median/
p95 29.74/33.42ms→1.24/1.34ms; detail58.39/65.50→32.87/35.54ms. OCR detail2→1
por muestra; sin coste de captura ni auditoría global. Probes live de lectura
encontraron Lobby, cero taps/consumos; ese pendiente fue cerrado por el smoke
físico documentado arriba. Sources cerrados. Sin commit/push/28/28; trabajo local
independiente preservado. Auditoría causal completa y métricas en
`artifacts/equipment_color_validation/audit.md`; corpus y assets tienen manifests
con procedencia/hashes. El estado del fix previo de abajo permanece como historia
de esa intervención, no como descripción de la autoridad perceptiva nueva.

## FAILED Sell Equipment — origen causal corregido localmente 2026-10-07

Último log `20261007T151933.728847Z_session_fd48d8bf`, personaje2 /
Dimension Manipulator / MW investment. FAILED12:34:46 ART:
`bulk_not_started:confirmation_item_mismatch`, count135/capacity128 y cero
confirmaciones de ese Bulk. Panel9191/9193: Legendary Helmet,
`Laoku's Destructive Gear`, guard visual y Sell positivos. Open Sell desde9193;
popup9198/9202: `Laoku's Desructive Gear`, confianza.99925/.99922 y scope
Equipment-grade correcto. Primera divergencia: igualdad literal entre dos OCR
del nombre rechazó una transición determinista verificada; consenso repitió el
mismo error de letra. Las capturas del failure bundle son anteriores al popup;
la atribución usa los diagnósticos/acciones del log, no un replay de esos pixels.

Solución general en el owner existente: Open Sell recibe el panel verificado;
runtime acredita `source_item_sequence` sólo con dos muestras frescas posteriores
al tap y sin input intermedio. Operación/policy usan ese origen para la relación
panel→popup; nombres arbitrarios/transcripciones distintas no requieren assets,
aliases ni tolerancia difusa. Scope Bulk exacto, policy/tier/type/Enhance, E+
protegido, confirmación única y delta posterior permanecen. Cualquier input
invalida el origen; su pérdida no permite fallback por igualdad de nombre.
Facts standalone sin origen conservan comparación estricta.

Validación offline:500 tests directos y consumidores afectados passed, incluido
el par OCR del fallo, nueve tipos y las tres familias Bulk, origen incorrecto,
input intermedio, stale/pre-tap/unconfirmed, scope incompatible y efecto inconcluso
sin retry. Item Count posterior del replay semántico es simulado; no prueba venta
física nueva. Sin cambio perceptivo ni evaluator, sin hardware ni nuevo smoke;
reader/payment-wrap y todos los cambios locales previos preservados.

## FAILED Stages post-ad — corregido localmente 2026-10-06

Log `20261006T192430.058419Z_session_b2f41405`, session
`fac392bee3cb41a09e84c66c772d9be4`, personaje2 / Gold step3 / Stages attempt1.
FAILED16:29:37 ART tras ad RETURNED y un único Results OK. Capturas3092/3105/3146
confirman Config: no faltó la transición. El scope de81 detectores gastó hasta
2.5225s por análisis; la reacquisición nativa también agotó la guard2s
(análisis2.3554s). Primera divergencia: rechazo por edad de Config matching.

Fix focal: Results→Config→Normal observa cuatro detectores, con toda la familia
upper de Stages, Quick Menu y blockers Equipment/Socket. Reutiliza Config fresco
para su cierre; Back→Lobby conserva el observer completo. Guard2s, cancelación,
timestamps reales, fallback nativo bounded y confirm único permanecen.
Replay semántico curado reproduce timeout anterior y cierre corregido sin repetir
OK; tests afectados y equivalencia perceptiva12/12 en corpus existente.
Evaluator incremental48/48 pares reutilizados, cero invalidaciones de detectores.
Informe local: `artifacts/stages_return_validation/report.json`.
Sin nuevo smoke/campaña live, commit ni push; cambios previos preservados.

## Checkpoint causal Reliefs / MW / Trading — 2026-10-06

Scope exclusivo posterior a `d97e899b`: policy/coordinator transversal de rutina,
schema/migración v2 y GUI Reliefs; freshness A1 MW; OCR Keys post-confirm.
La auditoría MAX confirma dos selecciones reales entre preparaciones independientes;
fix mínimo conserva MAX ya seleccionado con evidencia fresca, sin rediseñar MW.
Validación consolidada, INDEX aislado y exclusiones en
[cierre del checkpoint](docs/RELIEFS_FARMING_CHECKPOINT.md).

## FAILED manual Trading — corregido 2026-10-06

Run `5c599d7e4c5a406394d3c18c46b07fb7`, session
`a94ac2e7e19c47389bacda3db00ecc61`, log `20261006T153842.516960Z_session_ef92f6d3`.
Continuación manual19 desde Crimson Assassin; Ice Warlock scope17/19, Gold step3
occurrence1, MW final_investment attempt2 / keys_promotion / Silver→Gold.
MAX correcto: Silver215/10, selector1/20→20/20, confirm único, efecto215→15.
Primera divergencia: OCR post-confirm `15/10J` / .88277, secuencia93095;
FAILED15:11:17 ART por `after_fact_unreadable`, sin retry económico.

Fix focal del reader Keys: anclar unión de glyphs blancos a la línea numérica;
excluir componentes decorativos fuera de línea. Parser estricto, threshold.90,
consenso2, freshness y C4 conservados. Corpus afectado y209 tests dirigidos verdes.
Live: Keys Bronze6/10/Silver15/10; apertura única Gold Key2 verifica1/20,
máximo útil1 y omisión de `>>`. Detenido antes de confirm, Item Trade abierto,
cero trades nuevos y cleanup de fuente. Replays/logs/límites en
[informe Trading](docs/TRADING_FAILED_SESSION_A94AC2E7.md).

**USER_GT Ads:** amplitud live cerrada por la campaña manual de hoy con Ads
renovadas y dos failures, ninguno en Ads. No queda campaña de amplitud pendiente.
**Ads live breadth debt: CLOSED**: broad coverage, short ads y multipart natural
coverage. No se afirma nuevo28/28 COMPLETED. Notas de amplitud pendiente en campañas
previas son historia superseded, salvo regresión futura concreta. Sell K Coins y
trabajo histórico independiente quedan preservados fuera de este checkpoint.

## Reliefs y FAILED manual MW — cierre causal 2026-10-06

Baseline `d97e899b`, branch `rebuild/stable-baseline`. Config Reliefs pasa a rutina v2,
con coordinator compartido, migración v1 conservadora/archivo original y GUI Step Settings /
Routine Settings / Reliefs / Application. Ethereal checked autoriza vender, ahora explícito.
Craft conserva tres categorías habilitadas al migrar. Platinum no implementado ni mostrado.

Intento manual28 anterior: session `c385af509b7c4b2ba214f169e8af3b7f`, run
`ff4b8797565f445695ef2cad0c2987ea`, log `20261006T123851.620375Z_session_86adecd4`.
Falló 09:49:04 ART en Burst Breaker (primer personaje), Gold step3 occurrence1,
MW final_investment attempt2. BASE MW + resource board correctamente resuelto; A1 agotó
edad durante OCR y spacing durante percepción. Último CLEAR/accounting:276→176.
Fix local A1 memoiza resultados CV por pixels exactos de ROI, conservando guards y
ventanas. Replay curado demuestra old FAILED / fixed continuation YES + finish.
Smoke live read-only: gap0.297s, edad0.875s, cinco filas, cero inputs y cleanup.
Investigación/validación en [informe MW](docs/MW_FAILED_SESSION_86ADECD4.md).

Validación dirigida: 1060 passed/16 failed inicialmente; un test GUI de routines
usaba un control MW retirado y se actualizó (routines:53 passed). Los otros15 son
fallos heredados presentes en `artifacts/character_state_baseline_failures.txt`:
11 harness GUI anterior a Session y4 handoffs que llaman `_initial_lobby` retirado.
Seis casos corrupt adicionales pasan (policy:38 passed). Resultados reutilizados:
1067 verdes únicos,15 heredados; sin suite global. GUI real y migración/reopen local
verificados. Estos conteos acumulados quedan como procedencia; la selección final
única y validación del INDEX están en el cierre del checkpoint. No Open Pets.


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
natural. Amplitud Ads cerrada por USER_GT2026-10-06; los límites de campañas
anteriores conservan sólo procedencia. Otras deudas menores conservadas en ROADMAP.
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
