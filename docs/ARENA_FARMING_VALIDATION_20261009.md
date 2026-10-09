# Arena Farming Cycle — entrega y validación 2026-10-09

Baseline publicada y HEAD conservado:
`92667ee26c11d8c90bc54b4d2faeeebcc7a274de`.
Worktree `D:/PROYECTOS/kritika-farmbot`, rama `rebuild/stable-baseline`.
Sin commit/push ni segundo frente. Manual Stages impide cierre completo end-to-end.

## Arquitectura entregada

[Contrato, parámetros y escenarios](ARENA_FARMING_CYCLE.md) describe los owners:
`ArenaFarmingCycle` compone routing/refresh/progreso/terminaciones;
`ArenaAdaptiveController` conserva sólo evidencia reciente de una ejecución;
`ArenaFarmingResourceReader` acredita saldos nativos Lobby;
`ArenaFlow` conserva economía/receipt/una operación AUTO_REPEAT x8;
MW expone `run_resource_pass()` de generación única con los mismos guards;
Session conserva navegación, carácter, pasos posteriores, cancelación y lifecycle
Shared Meteorites/Rotation. No cambios a Session ni REPEAT_CURRENT.

Un único paso visible Arena. Step Settings ofrece Single Battle, Auto Repeat y
Farming Cycle. Default nuevo Single/Easy. Farming inicia Hard, oculta dificultad
fija y muestra exclusivamente thresholds por ocurrencia40/100/80, validados y
persistidos por Apply/Save. Rutinas anteriores conservan schema/config.

Routing exacto Badges→Arena / Sapphires→MW / ambos insuficientes→Manual. Cada
operación exitosa tiene refresh posterior; no saldo calculado. Progreso Arena
acreditado por resultado del owner, MW por CLEAR/consumo fresco y ganancia Badge.
Bound32operaciones y seis batches consecutivos sin victorias impiden farming
indefinido sin utilidad. Manual es interfaz independiente, sin coste/stage/reward/
terminal inventados; ausente termina `manual_stages_not_implemented` funcional.

Política: media de últimos3batches por dificultad, caducidad12batches, peso igual
por batch (no ocho tickets independientes), reward70/120/180×winrate. Mínimo2batches
por decisión/permanencia ordinaria, mejora>10% para cambio por eficiencia,
exploración adyacente ante falta de datos y reconsideración después de4batches.
Excepciones de UN batch>=umbral tienen prioridad: Hard0→Easy; Easy0→fin funcional.
Sin estadísticas históricas, Victory Points leídos ni modelo ML.

## Validación offline y replay

**741 tests afectados PASS**, pytest-final63.87s. Conjunto: controlador/ciclo/
generación MW/recursos/settings; Arena A/B1/B2 y replay; Routine/GUI/Tk; Runtime/
Session/Meteorites; MW entry/productive/pressure/skip expiry/points/resource route/
readiness; Stages Daily y Gold Farming. No suite global ni28/28.

Las secuencias determinísticas del contrato cubren límites40/100, prioridadArena,
refresh, no progreso, Hard inicial, rewards/exploración/histéresis, estado nuevo,
excepciones80 y thresholds personalizados, modosB2, Apply/Save/migración,
continuación/cancelación/UNKNOWN/consumos únicos y cleanup antes de Rotation.
Generación MW se prueba en100/101/102/250 con un solo pase y sin drenaje de presión;
no consumo fresco, ambigüedad y stops no autorizan otro pase. Son simulaciones,
no estadísticas físicas de matchmaking ni contrato de Manual Stages.

Evaluator incremental **9/9**,5reutilizados y4calculados para crops live nuevos:
`artifacts/arena_farming/evaluation/report.json`. Eight number-pair replays nativos
B1/B2/Farming y un stock999, con hashes/source/ROI en
`tests/fixtures/arena_farming/manifest.json` y `buff_stock_manifest.json`.
No detector global/ROI de resultado alterados, ni evaluator global repetido.

Primer intento pytest usó el temp/cache externo con permisos insuficientes; se
resolvió usando basetemp nuevo en artifacts y sin cacheprovider. No fallos pendientes
en el conjunto final. Los11fallos históricos GUI functional de baseline no forman
parte de esta validación y no se tocaron.

## Live focal y primera divergencia

Preflight read-only `artifacts/arena_farming/live-preflight-02/result.json`:
Lobby limpio119Badges/95Sapphires, cero inputs. El primer intento sandbox de ADB
no pudo iniciar daemon; la ejecución autorizada fuera del sandbox resolvió acceso.

`live-cycle-01`: Battle→Arena→Hard, stop antes de seleccionar buffs/config/Start.
Stock visible999, OCR gris conf.94631<.95. Primera divergencia perceptiva, no
compra Gold real. Fix limitado a stocks: margen negro8% del alto del crop sólo si
la lectura original falla; color/gris deben seguir concordando>=.95. No cambia
Badge/result reader, precios o autorizaciones. Replay stock999 y regresiones pasan.
Tres Back adquiridos y frescos restauraron Lobby sin consumo; fuentes cerradas.

`artifacts/arena_farming/live-cycle-02/result.json`: Dimension Manipulator,
inicio Hard x8, Upon DefeatOFF, stocks iniciales999, reserva8 verificada en los
tres buffs. Un solo Start interno efectivo y operación continua:

- Modal nativo: Used112 / Acquired Karats112; winrate100% de ESTE batch.
- Badges119→7; Karats103165→103277, +112. Gold6930610473 sin cambio durante Arena.
- ControlledWait526.906s,175observaciones; intervalo medio3.028s/máximo3.172s;
  cero OCR,1.072s CV y4.850s trabajo del observer durante wait. Un terminal
  positivo; sin reinicio, handoff ni inputs de batalla. Flow total548.110s.
- Onset terminal sólo bracket observado262269.359–262272.453 monotónico;
  no duración física exacta ni latencia inventadas.
- OK/Insufficient-No y New Ranking-OK adquiridos, Back hasta Lobby acreditado.
  Fresh resources7Badges/100Sapphires. Controller permanece Hard tras un batch.

Ese smoke expuso una divergencia de composición: el MW anterior se limitaba a
Sapphire pressure>=102 de Gold y devolvió no_work en100, sin input. El ciclo
terminó no_progress y Session continuó el Lobby probe. Corrección mínima en el
mismo owner: `run_resource_pass()` hace un pase ordinario verificado, sin la meta
de presión. `run()`/`prepared()` de callers existentes mantienen su comportamiento.
No costes/recompensas inferidos desde el threshold100.

Se repitió **sólo MW**, sin otro Arena largo:
`artifacts/arena_farming/live-mw-01/result.json`, budget1operación. Board/planner
NO_PREREQUISITES, preparación/SKIP/board/CLEAR existentes, consenso fresco:
Sapphires100→0 yBadges7→106. Consumo100Sapphires acreditado por el owner,
ganancia99Badges observada (no recompensa fija codificada). Retorno normal a
Lobby, refresh, fin safety_limit del smoke y paso posterior Session COMPLETED.
No relief ni venta/trade extra, ningún segundo Start Arena.

Autonomía prolongada acreditada para el batch Hard112/112 continuo. No se afirma
campaña multibatch/multiciclo ni que toda la versión final recorrió Arena+MW+
Manual bajo una sola ejecución: MW se validó separadamente por invalidación.

## Consumos y estado físico final

Total consumptivo de esta entrega: un batch Arena112Badges y un pase MW
100Sapphires; no Single Battle. Buffs1/2/3 seleccionados desde stock conocido y
reserva8 cada uno; no se adquirió una lectura posterior de sus stocks para
cuantificar saldo final. Arena no compró Gold ni Karats; MW compró tickets SKIP
mediante el owner existente y entregó Gold. Cambio neto Gold observado desde el
preflight:6930610473→7127809094 (+197198621), sin inferir ingreso bruto ni coste
de ticket desde ese neto. Karats finales103277: +112, sin gasto premium.

Final nativo `live-mw-01/physical_final.png`: **Lobby limpio**, Dimension
Manipulator,106Badges/0Sapphires,Gold7127809094,Karats103277. No modal/batalla
activa. Runtimes/sources/procesos/forwards propios cerrados por context managers;
no rotación ni intervención Shared Meteorites física en estos smokes. Su lifecycle
completo y continuación tras Easy0 se validaron offline con setup/cleanup reales
simulados, no se confundieron con una adquisición física nueva.

## Gaps y residual

Pendiente físico/productivo: Manual Stages (stage, stamina, reward, repetición y
terminal). No bloquea la implementación Arena+MW. Permanecen derrota Single,
modal informativo por umbral de puntos, compra Gold en agotamiento de buffs,
cancelación física y retorno Arena tras relief. No aparecieron en el camino
consumptivo y no se forzaron. REPEAT_CURRENT fuera de alcance.

Archivos propios: Arena config/flow guard/reader; tres owners nuevos; factoryArena
en Registry; operación MW resource-pass; GUI; tests/fixtures; tooling/evaluator;
documentación dueña. `bot/monster_wave_flow.py` conserva el readiness observer
independiente y añade sólo la operación; `bot/flow_registry.py` conserva los hunks
independientes MW/Summon. CONTEXT conserva íntegros sus cambios locales previos.

Residual ajeno preservado: AdsManager, Equipment reader, RuntimeFactReader,
MW readiness/scope, Summon, portal recovery test, eliminación del plan histórico,
scripts experimentales y fixtures/tests Ads/Sell/MW. Sin staged changes, commit,
push, reset/clean/revert ni adquisición de otro frente. Raw/artifacts/temporales
permanecen locales ignorados; sólo crops pequeños y manifests curados son nuevos
artefactos versionables. HEAD/rama no cambiaron.
