# Arena Farming Cycle — aceptación integral 2026-10-09

**PASS.** Una misma ejecución ordinaria de Session, con Crimson Assassin,
acreditó GUI persistida, setup completo de Shared Meteorites, seis entradas
Abyssal Rion 09, cuatro Monster Wave, cuatro Arena Auto Repeat, abastecimiento
anticipado único, corte funcional por presupuesto360 y cleanup normal completo.
No hubo Easy0 ni cambio de personaje durante el farming.

Baseline/HEAD `c607b601b9ba79d49ec0261e3dd5d475b94aea46`; rama
`rebuild/stable-baseline`; worktree `D:/PROYECTOS/kritika-farmbot`.
Sin commit/push ni staging. El trabajo local anterior e independiente se conserva.

## Ejecución y evidencia principal

- Run `ffb31f514a074ad5bcb82db1e17874d4`.
- Session `d6205777fdc14ecd971a28b4095b20a5`.
- [Log completo](../artifacts/arena_e2e_20261009/logs/20261009T220833.531536Z_session_7621171c.jsonl).
- [Auditoría de resultados](../artifacts/arena_e2e_20261009/acceptance_metrics.json): `pass=true`,
  Session completada, runtime cerrado, set original restaurado.
- [Tiempos y recursos por actividad](../artifacts/arena_e2e_20261009/activity_times.json).
- [Probe final independiente de sólo lectura](../artifacts/arena_e2e_20261009/acceptance_final/result.json):
  Lobby antes/después, sin overlays, sources cerrados.

Runtime22:08:33.588032–22:59:43.363540UTC: **3069.776s (51m09.776s)**.
Session22:08:41.170610–22:59:43.235016UTC: **3062.064s (51m02.064s)**.
La diferencia es inicialización/cierre del runtime; no se atribuye a performance
de gameplay. No hay comparación homogénea que permita afirmar una mejora.

## GUI real y configuración efectiva

Se creó la rutina separada **`a360`**, ID `61b225b73b6c44278955dac6b4a90f0f`,
desde `tools.gui`: un único paso visible habilitado **Arena**, modo **Farming Cycle**,
thresholds defaults **40/100/80**, **Maximum Stamina Consumption360** y
**Change MeteoritesON**. Apply del paso, Apply de rutina y Save Routine;
se volvió a abrir la GUI y se acreditó la persistencia antes de Run Session.
Characters=1. Session registra ese mismo ID/nombre. No hubo configuración interna
inyectada ni farming por invocaciones aisladas de owners.

Se mantuvo `resource_snapshot_mode=BEFORE_CHARACTER_ROTATION` y reliefs por defecto.
360 permitía seis entradas causales de60 y repetición suficiente para observar
las tres ramas. [Configuración guardada](../artifacts/arena_e2e_20261009/routine_saved.json)
y [backup anterior íntegro](../artifacts/arena_e2e_20261009/routines_before.json).
Las rutinas existentes conservaron su configuración efectiva; el serializer
explicitó únicamente `change_meteorites:false` donde antes faltaba ese default.

## Identidad, setup y scope

Identidad física **Drakenn09**, clase canónica **Crimson Assassin**, ID estable
`crimson_assassin`, adquisición `canonical_ocr`. No es uno de los cuatro fuertes;
requiere el set compartido para seleccionar Rion09. No se dedujo clase del nombre.

Set original **Set1**, sólo slot1 ocupado (índices0..10); CP original **41,829,408**.
Se conservó sin modificaciones durante el farming. El lifecycle equipó Shared
Meteorites en **Set2**, inicialmente vacío: flare+30 en posición2, normales desde
posición6, anchor15/cell14/page1 conforme a la precondición existente.

Session verificó **once efectos Equip0..10**, once slots ocupados y scope **READY**
a22:09:04.484978UTC. Setup **21.866s**, cero retries. CP observado con el set
**247,294,766**; con buffs Manual **320,790,924**. Manual Stages recibió la condición
completa acreditada y eligió **`abyssal_rion_09`** en las seis entradas. No usó
Chaos06 ni modificó el equipamiento compartido. Scope permaneció READY durante
todo el farming; cleanup comenzó sólo después de la terminación funcional.

## Routing real y recursos físicos

Inicial: **2Badges / 80Sapphires**. Cada actividad cerró su operación y devolvió
control al coordinador, que releyó recursos antes de elegir la siguiente rama.
Los saldos son observados; los tiempos abarcan routing→refresh siguiente e
incluyen preparación, relief y navegación. Se usan `created_at` de los eventos,
porque los eventos de negocio del ciclo se publican al finalizar el flow.

| Op | Actividad | Badges antes→después | Sapphires antes→después | Segundos |
| --- | --- | --- | --- | --- |
| 1 | manual_stages | 2→2 | 80→134 | 114.761 |
| 2 | monster_wave | 2→106 | 134→34 | 66.218 |
| 3 | arena | 106→2 | 34→34 | 533.003 |
| 4 | manual_stages | 2→2 | 34→94 | 140.304 |
| 5 | manual_stages | 2→2 | 94→154 | 91.225 |
| 6 | monster_wave | 2→106 | 154→54 | 54.710 |
| 7 | arena | 106→2 | 54→54 | 510.139 |
| 8 | manual_stages | 2→2 | 54→138 | 136.294 |
| 9 | monster_wave | 2→101 | 138→38 | 86.628 |
| 10 | arena | 101→5 | 38→38 | 480.564 |
| 11 | manual_stages | 5→5 | 38→104 | 96.111 |
| 12 | monster_wave | 5→106 | 104→4 | 85.215 |
| 13 | arena | 106→2 | 4→4 | 509.786 |
| 14 | manual_stages | 2→2 | 4→88 | 89.002 |

Después de op14, routing15 eligió Manual porque **2Badges<40** y **88Sapphires<100**.
Se rechazó antes de otra preparación/compra/Start porque remaining_budget0<60.
El presupuesto gobierna Manual; Arena/MW conservaron prioridad durante el ciclo.
No se inventaron ni forzaron los estados iniciales o transiciones.

Monster Wave fue elegida cuatro veces con Badges insuficientes y Sapphires≥100.
Cada entrada acreditó debit100Sapphires y resultado `monster_wave.completed` con
retorno seguro. Generación física por refresh de Badges: **+104,+104,+99,+101**.
No se sustituyen esas diferencias físicas por un supuesto rendimiento fijo100.
Total debit observado **400Sapphires**; Manual generó **408Sapphires** netos
acreditados por sus before/after:80+408−400=88finales.

## Manual Stages y ledger causal

Las seis entradas acreditaron Rion09 por `meteorites_verified=true`, x4,
PenanceON, buffs1/2/3ON, coverage del cuarto buff y Support activo.
Primer Start→`select_striker`; segundo Start→`battle`; AutoON positivo.
Todas: **Clear Time→Home→Lobby**, refresh de recursos, receipt causal60.

| Entrada | Stamina física antes→después | Sapphires | Receipt | Ledger | Restante | Espera terminal s |
| --- | --- | --- | --- | --- | --- | --- |
| 1 / op 1 | 382→322 | 80→134 | 60 | 60 | 300 | 39.046 |
| 2 / op 4 | 323→263 | 34→94 | 60 | 120 | 240 | 40.563 |
| 3 / op 5 | 263→203 | 94→154 | 60 | 180 | 180 | 39.016 |
| 4 / op 8 | 204→144 | 54→138 | 60 | 240 | 120 | 45.078 |
| 5 / op 11 | 145→85 | 38→104 | 60 | 300 | 60 | 48.062 |
| 6 / op 14 | 86→27 | 4→88 | 60 | 360 | 0 | 40.562 |

Ledger nuevo de esta instancia: **0→60→120→180→240→300→360**. Nunca reutilizó
los120 consumidos del intento anterior. Claims, compra y regeneración no alteran
el ledger. El último delta físico59 sigue siendo receipt60: la diferencia entre
saldo y consumo no autoriza otra entrada. Desde382 posterior a Trade hasta27finales
hay un neto adicional5 en saldos; no se adjudica un monto aislado de recompensa
Claim sin evidencia separada. Ninguna entrada falló en la ejecución aceptada;
los contratos afectados mantienen la contabilidad60 también ante derrota.

La navegación comprobó Claim antes de configuración y déficit. En la preparación
inicial, Claim ya estaba inactivo al calcular demanda. Hay un Claim efectivo
en op5,22:23:35.052760UTC: **2taps/2ciclos**, terminado en **0.579s**.
Su recompensa individual no se aisló; no se suma al presupuesto de consumo.

## Trading Center

Sólo se compró al corresponder la rama Manual, después del chequeo Claim y
refresh. Stamina disponible **282**, demanda presupuestada **360**, déficit **78**.
Una preparación anticipada; **2Trades de50=100Stamina**, **400KCoins**, una
confirmación consumptiva. Selección2/20 y pago fresco **HAVE119246/COST400**.
Efecto físico **282→382**, panel cerrado, Trading Center→Lobby, duración **7.781s**.
La captura nativa `0004_220933.png` del directorio del log acredita el importe.

No se gastaron Karats en Trading/buffs ni se duplicó una confirmación incierta.
El coste se acredita por selección/precio/confirmación y receipt; no se presenta
un saldo KCoin posterior inventado como observación física.

## Arena Auto Repeat y adaptación

Controller nuevo para esta ejecución, Hard inicial. Sólo los cuatro resultados
terminales válidos siguientes actualizaron el controller. `used_tickets` proviene
de Brawler's Badge Used; `won_tickets` de Acquired Karats conforme a USER_GT.

| Op | Dificultad | Used | Won / Karats obtenidos | Winrate derivado | Próxima / motivo | Wall owner s |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | HARD | 104 | 80 | 76.923% | HARD / `collect_recent_batches` | 525.167 |
| 7 | HARD | 104 | 88 | 84.615% | NORMAL / `adjacent_uncertainty` | 502.135 |
| 10 | NORMAL | 96 | 72 | 75.000% | NORMAL / `collect_recent_batches` | 472.334 |
| 13 | NORMAL | 104 | 96 | 92.308% | HARD / `recent_reward_advantage` | 501.768 |

Total **408tickets usados / 336ganadores / 72perdedores**; **336Karats adquiridos**
según los modales, no deducidos del HUD. Double Points no multiplica Karats.
Todos los batches terminaron COMPLETED con `physical_operation_may_be_active=false`.
Hard→Normal exploró la dificultad adyacente ante incertidumbre; tras dos muestras
por nivel, `recent_reward_advantage` seleccionó Hard para una eventual próxima
Arena. Scores internos derivados: Hard145.385 y Normal100.385; no son un saldo
físico de Victory Points. Esa próxima Arena no se ejecutó: recursos insuficientes
y corte posterior de Manual. **Easy no se ejecutó; Easy0 no ocurrió.**

Op3 tuvo un primer Start rechazado inequívocamente por Socket inventory blocker.
El relief existente resolvió, revalidó preparación y autorizó el Start efectivo.
No hubo repetición consumptiva ambigua ni segundo batch acreditado para op3.

## Terminación, cleanup y estado final

`arena.farming.terminated.created_at` **22:59:09.720490UTC**:
**`stamina_budget_reached`**, stamina_consumed360, remaining_stamina_budget0.
Últimos saldos de Crimson: **27/440Stamina, 88/102Sapphires, 2/106Badges**.

Cleanup normal de Session comenzó22:59:10.586323UTC. El owner verificó
**once Unequip10..1,0**, Set2 vacío, activó Set1 original con sus slots preservados
y devolvió a Lobby. Scope **RELEASED22:59:26.979054UTC**, phasecomplete,
cleanup_outcomecomplete, pendingnone, cero retries; cleanup **16.389s**.
CP volvió a **41,829,408**. La captura `0094_225929.png` muestra Crimson en Lobby
tras RELEASED; sus contadores Gold/Karats transitorios no se aceptan como ceros.

Session hizo después su **único Rotation.advance habitual** y cerró **COMPLETED**
con characters_processed1, advances_completed1 y runtime cerrado. No procesó
otro personaje ni inició un segundo farming. El teléfono quedó en Lobby limpio
del personaje siguiente, HUD **DRAKEN六FS**; su clase no se infiere del nombre.
Sus saldos visibles son de ese personaje y no se atribuyen a Crimson.
El probe final independiente confirmó Lobby sin overlays, sin inputs de gameplay.
La GUI permanece abierta con el resultado completado para revisión.

## Divergencias, correcciones y recuperaciones

1. **Setup inicial interrumpido**, Session `94b76b6db8da44009466dcc61f8c1b56`,
   run `9de89631f3af4e15867151ba8b8c2e20`, log21:32:18, runtime28.045s.
   Equip0..6 verificados; selección7 abrió Fury+30 en overlay informativo,
   `selection_unverified`, antes de octavo Equip/farming/Claim/Trade.
   USER_GT: sólo aparece por tap mantenido, se cierra con tap lateral seguro.
   El log ADB acredita un `input tap`/dispatch87ms; no demuestra duración DOWN→UP
   ni por qué Android lo interpretó como mantenido. No se atribuye causa al backend.
   Recovery con owner existente: siete Unequip, Set2vacío, Set1original, Lobby;
   final118Stamina/14Sapphires/106Badges, Gold/Karats conservados, cero consumo.
   [Recovery](../artifacts/arena_e2e_20261009/setup_recovery/report.json) y probe
   `recovery_final/result.json`. Los cortes de adquisición/exportación del helper
   no autorizaron repetir efectos: cierre físico acreditado por probe independiente.
   Fix mínimo `meteorites_reader/runtime`: detección positiva específica y un
   cierre/reselect bounded previo a Equip, bag/set/page/slots frescos idénticos.
   Recurrencia/cambio/cancelación detienen; no retry genérico ni retry de Equip.

2. **Primer farming parcial**, Session `3ded963aecfe46f88b21748024fce1cf`,
   run `d42aaeb7bb3b4fb29563804e32f9e415`, log21:47:24, runtime824.745s.
   Once Equip/READY; Hard104/88, dos Rion09; ledger120/restante240.
   Compra única anticipada250Stamina/1000KCoins,120→370, una confirmación,
   HAVE120162/COST1000,5/20,10.078s. Entradas370→310 Sapphires14→50;
   310→281 Sapphires50→80; receipts60 cada una pese a delta29 del segundo saldo.
   Tercera preparación: Equipment relief correcto, variante PenanceON no reconocida
   antes de tercer Start. Terminó MANUAL_RESOLUTION/subordinate_stop; no FAILED
   artificial ni continuación con ledger reconstruido. Recovery dirigida de
   preparación→Lobby y once Unequip→Set2vacío→Set1original→Lobby seguro.
   [Recovery](../artifacts/arena_e2e_20261009/cycle_recovery/report.json): final_verifiedtrue.
   Fix mínimo Reader/profile: template local ON tras relief con margen suficiente,
   threshold0.94 intacto, OFF/negativos preservados. Se inició otra Session completa
   independiente sólo después del cierre seguro, con nuevos ledger y controller.

3. **Recoveries durante PASS**, sin intervención del operador: Equipment blockers
   en op4 y op8, combine no disponible→bulk sale con decremento de items→retorno
   y revalidación de x4/Penance/buffs/Support; Socket relief op3 con enhance efectivo
   y siete taps de animación→retorno Arena. Ambos casos de Penance tras relief
   ejercitaron el fix live. Dos reliefs adicionales de Equipment quedaron dentro
   de las operaciones productivas MW y cerraron sus boundaries exactos; no se
   confunden fases manual_resolution ya resueltas con un corte del ciclo.

4. **Reporte GUI**, descubierto al revisar el cierre: statusCOMPLETED y meteorites
   RELEASED correctos, pero assessmentunavailable por whitelist sin Farming Cycle.
   Replay curado de los71 eventos reales reprodujo el fallo sin teléfono.
   Fix local `session_report`: eventos conocidos informativos y terminación funcional
   explícita budget/Easy0; unknown/missing reason siguen unassessed, fallos/cancelación
   y reliefs sin resolución conservan su clasificación. No alteró gameplay/ledger.
   La GUI ya abierta conserva su proyección anterior; el fix se verifica con replay
   de esta ejecución cerrada, sin reiniciar ni volver a gastar recursos.

Todos los intentos usaron Crimson; no hubo otro personaje de farming ni Easy0.
Consumo total de la campaña: **480Stamina causal** (120parcial+360PASS),
**350Stamina comprada** (250+100), **1400KCoins** (1000+400).
La aceptación corresponde exclusivamente a los360 de la última instancia.

## Validación afectada y residuales

- Meteorites: **197passed/21.03s**, `test_meteorites_phase_a`, `test_shared_meteorites`,
  `test_meteorites_session`; replay positivo/negativo, cierre bounded/recurrencia/set/cancel.
- Penance: **129passed/5.63s**, `test_manual_stages`, `test_manual_stages_replay`,
  `test_manual_stamina_supply`, `test_arena_stamina_budget`; replays ON stream/nativo,
  OFF/dimmed/otros contextos. Evaluator incremental: cinco casos existentes correctos.
- Reporte: **116passed/2.17s**, `test_session_report`, `test_arena_stamina_budget`,
  `test_arena_farming_cycle`; replay real71 eventos y negativos de terminación/fallo/relief.
  Antes del fix, el test de la ejecución real fallaba con statusNone.
- La ejecución integral fue la validación física; no se multiplicaron smokes aislados,
  no hubo campaña28/28, REPEAT_CURRENT, suite/evaluator global por costumbre.

Cambios propios residuales: manejo local del overlay Meteorites, reader/template
Penance, proyección SessionReport, tests/replays curados, dos hechos de GAMEPLAY_GT,
estado CONTEXT y este informe. Assets runtime/fixtures pequeños permanecen locales
sin staging. Configuración GUI separada y evidencia/logs/helpers bajo artifacts
son locales ignorados; no se agregaron datasets/capturas grandes al versionado.
El resto del diff anterior (Arena/Manual/recursos y trabajo Ads/Equipment/MW, etc.)
se conserva íntegro y no se atribuye a esta aceptación. HEAD y rama sin cambios.

Los nueve criterios quedan acreditados por una misma Session completa; no queda
cleanup pendiente ni meteorito compartido en estado incierto. Alcance cerrado.

## Session Report y checkpoint posteriores

La entrega posterior agrega un resumen analítico y una tabla expandible por
ocurrencia, validados contra los eventos conservados de esta misma ejecución.
No repite la Session ni cambia su aceptación. El ciclo histórico no registró
wall del owner: se muestra explícitamente el intervalo observado de routing
49m53,965s, separado del runtime51m09,776s y Session51m02,064s. Las nuevas
ocurrencias instrumentan su wall conservada al reanudar dentro de la instancia.
Fuente, agregación, validación del INDEX y publicación en el
[checkpoint integral](ARENA_FARMING_CHECKPOINT_20261009.md).
