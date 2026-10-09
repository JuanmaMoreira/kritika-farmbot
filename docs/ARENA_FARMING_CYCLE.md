# Arena Farming Cycle — contrato de implementación

Baseline publicada `c607b601b9ba79d49ec0261e3dd5d475b94aea46`, rama
`rebuild/stable-baseline`. Tres owners conectados; no REPEAT_CURRENT.

## Ownership y ocurrencia

- `ArenaConfig`, RoutineEditor/Store y GUI: un único Arena con Single Battle,
  Auto Repeat o Farming Cycle. Nuevas ocurrencias Single/Easy. Single/Auto guardan
  dificultad fija; Farming guarda mode, los tres thresholds y el límite opcional
  `maximum_stamina_consumption` (entero≥0; ausente/null sin límite).
  Apply modifica draft, Save Routine persiste. JSON anterior sigue válido.
- `ArenaFarmingCycle`: routing, refresh, progreso, límites, excepciones y resultado
  completo. No acciones físicas directas, Rotation, Meteorites ni clase/loadout.
- `ArenaAdaptiveController`: decisión determinística de dificultad con estado
  nuevo en cada ejecución; una reanudación de la misma instancia conserva su
  estado, sin compartirlo entre ciclos/personajes/sesiones.
- `ArenaFlow`: una operación AUTO_REPEAT x8 y retorno Lobby, con economía, receipt,
  wait, result reader y cierres existentes. Single nunca sirve al farmeo.
- MW: factory productivo existente y operación `run_resource_pass()` de un pase,
  con los mismos settings, reliefs y planner del Resource Board. `run()`/`prepared()`
  conservan la meta Sapphire pressure102 de Gold Farming; generación usa readiness
  y preparación ordinarias, CLEAR y consumo fresco acreditados, sin esa meta.
  Caller solicita Lobby tras éxito; un error conserva
  su status/error/failure y sus resultados, sin transformarlo en agotamiento.
- Session: verificación habitual de postconditions, pasos siguientes, cancelación,
  estado de personaje y cleanup Shared Meteorites al final de todos los pasos.

## Recursos y progreso

Orden exacto: Badges >=mínimo Arena → Arena; de lo contrario Sapphires >=mínimo
MW → MW; de lo contrario Manual Stages. Defaults40/100; configurable por
ocurrencia. El mínimo técnico x8 es8; mínimo configurable Arena>=8. Threshold
cero victorias default80, entero positivo; mínimo Sapphires entero positivo.
Recompensas70/120/180 son USER_GT, nunca opciones económicas de GUI.

Reader adquiere saldos Lobby nativos, dos frames distintos concordantes;
color/gris mismo crop >=.95, contexto limpio y edad<=4s después del trabajo.
Cada recurso conserva secuencia, timestamp y hash. Badges usa el par amarillo
acreditado del Battle tile; Sapphires usa el ROI existente de Survival. No rechaza
saldo mayor al límite mostrado (119/106 existe). Ningún fallo equivale a cero.
Refresh al entrar y tras cada éxito Arena/MW/Manual; nunca routing con saldo
calculado. Tras un stop subordinado no se navega sobre un estado incierto.

Arena: resultado propio acreditado más refresh de saldos posterior. Victoria produce
rendimiento; un cero válido aporta una observación exploratoria finita. Máximo6
batches consecutivos sin victorias (dos observaciones por cada nivel) incluso si
MW repone Badges. No se exige igualdad entre delta HUD y Used Tickets: saldos
de routing y de Start son lecturas distintas; el receipt del owner acredita el
consumo y las victorias, no una predicción de saldo. MW: CLEAR propio acreditado
y ganancia fresca de Badges; gastar
Sapphires sin ganar Badges no autoriza otra operación. Manual disponible debe
poseer su terminal propio y aportar ganancia fresca de Sapphires. Una
operación sin ganancia útil termina antes de otro input de esa rama.

Bound interno32operaciones por ejecución, además de los bounds y cancelación de
cada owner. Es un guard, no una meta de farming ni un coste inferido. El smoke
puede reducirlo y acotar autorización del batch natural; nunca fragmenta x8.

`ArenaFarmingResult.termination` distingue `easy_zero_wins`, `no_progress`,
`no_productive_route`, `manual_stages_not_implemented`, `safety_limit`,
`stamina_insufficient`, `stamina_budget_reached`, `stamina_supply_unavailable`,
`sapphire_capacity_full`, `manual_stage_defeated`,
`ambiguous`, `subordinate_stop`, `technical_failure`, `cancelled`.
Los motivos funcionales son COMPLETED con evento; Session verifica
Lobby antes de continuar. Las demás conservan MANUAL_RESOLUTION/FAILED/CANCELLED
según origen. Operaciones subordinadas permanecen en el resultado con métricas,
evidencia y riesgo de operación física activa. Una entrada Manual pendiente se
reconcilia por su owner, sin otro Start; incertidumbre ajena conserva el corte.

## Presupuesto y abastecimiento de Stamina

El límite pertenece a la ocurrencia y al personaje. Vacío no impone un corte
total; cero impide Manual. Una ejecución nueva inicia consumo0. Una ejecución
interrumpida conserva contador, preparación, receipts y controller en la misma
instancia. No existe reanudación durable de Session tras cerrar el proceso.

Cada entrada x4 cuyo efecto físico fue acreditado consume60, incluso si falla
Auto, pierde, se cancela o falla el retorno. `entry_id` evita contabilizar otra vez
el mismo receipt reconciliado. Un segundo Start de efecto incierto devuelve
`stamina_consumed=None`: bloquea otra entrada hasta acreditar batalla/terminal.
Si Home ya acreditó Lobby y falló el balance, se reconcilia sólo el balance fresco.
Compra, Claim y regeneración no descuentan ni reinician este contador. No se usa
el delta de saldos para inferir consumo. El saldo real puede aumentar mientras
se gasta Stamina. Presupuesto500 autoriza ocho entradas/480, no una novena.

Sólo al seleccionar Manual y con remaining≥60 se prepara abastecimiento. Con
límite, la primera preparación navega normalmente al episodio, incorpora Claim,
vuelve a Lobby y refresca recursos. Si Arena/MW ya resultan elegibles, difiere
la compra. En caso contrario solicita saldo `(remaining//60)*60`; el déficit se
calcula desde Stamina fresca posterior a Claim. La preparación acreditada queda
registrada una vez, incluso si fue parcial o no necesitó comprar. No se visita
Trading entre entradas ni se vuelve a preparar anticipadamente tras reanudar.

Sin límite, saldo≥60 ejecuta Manual; saldo<60 usa Claim y solicita sólo60.
Puede abastecerse otra vez únicamente al volver a faltar Stamina. Las unidades
físicas50 pueden dejar excedente; no se fuerza el objetivo300 de Ads.

`StaminaPurchase.supply` reutiliza navegación Currency, identidad Stamina/K Coin,
selector `>` y Trade/retorno del owner Ads. Lee el par de pago en el ROI C4:
200KCoins por trade, total200×N, HAVE suficiente; cap fresco≤20, selección final
verificada y una sola confirmación. Compra `ceil(deficit/50)` limitado por cap y
KCoins disponibles. Un batch que agota la capacidad acreditada puede ser parcial;
registra N×50 reales, cobertura y motivo, sin afirmar que cubrió el presupuesto.
No compra Karats. Saldo fresco after≥before+50×N y regreso Lobby prueban efecto.
Un Trade incierto conserva receipt: sólo débito exacto fresco de KCoins más
Stamina ganada permiten reconciliar; nunca confirma otra vez. Cap explícito0 o
KCoins insuficientes son agotamiento funcional, lectura incierta MANUAL_RESOLUTION.
Ads conserva `ensure(before)` con300 y su protocolo anterior, sin OCR KCoins.

`stamina_budget_reached` y abastecimiento imposible con saldo<60 son COMPLETED.
Easy0 puede finalizar dejando saldo comprado, trade-off USER_GT aceptado: no se
consume sobrante, compensa ni adelanta cleanup Meteorites. Session continúa
normalmente. Un refresh de routing incierto corta conservando el ledger; no
permite reiniciar entradas a partir de esa incertidumbre.

## Política adaptativa y justificación

Inicio Hard. Cada dato es un batch acreditado `difficulty/used_tickets/won_tickets`;
Acquired Karats posee autoridad aun con Double Points. Victory Points no se lee.
Un run duplicado, dificultad ajena o resultado ausente se rechaza sin actualizar.

Estimación: media de winrates de los últimos3batches de cada dificultad cuya edad
sea menor a12batches del ciclo. Cada batch tiene un voto; ocho tickets de una
entrada no se modelan como ocho pruebas independientes. No hay intervalos de
confianza ni tamaño muestral inventado. Score = recompensa×media reciente.
Sin observaciones, score=None; nunca0%. La ventana y caducidad son heurísticas
internas para un matchmaking no estacionario, no estadísticas de la temporada.

Tras un cambio se observan al menos2batches antes de decidir normalmente:

1. Si ambos niveles poseen >=2observaciones recientes, cambiar al adyacente con
   mayor score sólo si supera al actual por >10%. Éste es margen de histéresis,
   no ratio económico; las comparaciones económicas vienen de70/120/180.
2. Si falta evidencia en un adyacente, explorar el menos reciente (no observado
   primero); mínimo2batches de permanencia también al explorar.
3. Si no hay ventaja ni incertidumbre, mantener hasta4batches en ese nivel y
   reconsiderar el adyacente observado hace más tiempo. Una decisión cambia
   normalmente un solo nivel. Permite reabrir un nivel descartado y no oscila
   por cada resultado marginal.

Caducidad12 permite adquirir las tres dificultades y sostener una permanencia
de4sin convertir la falta de una observación antigua en cambios constantes.
Todos los parámetros son constantes internas documentadas y escenarios de test.

Excepciones prioritarias sobre UN batch: used>=threshold y won=0 en Hard → Easy
directo; en Easy → fin funcional. No se suman batches pequeños para llegar80.
La excepción puede actuar antes de las2observaciones/permanencia normal.

## Escenarios sintéticos verificables

Tests `test_arena_adaptive`, `test_arena_farming_cycle`, `test_arena_farming_settings`
y `test_arena_farming_resources` separan simulaciones y replay de pixels:

| Secuencia / condición | Decisión o efecto esperado |
| --- | --- |
| Hard25%,25%; Normal75%,75%; Easy100%,100% | Hard→Normal→Easy→Normal; scores45/90/70 |
| Hard8tickets0%; luego160tickets100% | Media por batch50%, no160/168; sin excepción80 |
| Hard50%; Normal≈75%, resultados56/64 de80 | Diferencia marginal mantiene Normal; exploración al cuarto batch |
| Hard inicialmente débil y Normal fuerte | Hard se reconsidera; observaciones caducadas no asignan0% |
| Hard0/72 o40+40 con umbral80 | Sin salto excepcional; puede explorar Normal por policy ordinaria |
| Hard0/80; MW repone80; Easy0/80 | Hard→Easy; fin funcional y siguiente paso Session |
| Thresholds8/50/8 | Routing y excepciones usan esa ocurrencia |
| Badges40/Sapphires100 | Arena tiene prioridad |
| Badges39/Sapphires100 o39/99 | MW o Manual, respectivamente |
| MW termina sin CLEAR/ganancia Badge | No se repite; fin sin progreso |
| UNKNOWN, recurso stale/futuro, batch ausente, flow fallido o cancelado | Sin nuevo consumo; stop explícito |
| Fin Easy0 bajo Shared Meteorites | Paso siguiente, cleanup completo y Rotation en su orden habitual |
| Config previa / nuevas ocurrencias repetidas | Single/Easy default, Apply/Save independiente y reload compatible |

## Manual Stages y deudas

`ManualStagesOperation` tiene implementación independiente en `bot.manual_stages`
y wiring productivo en el único paso Arena. Se ejecuta sólo cuando ambos saldos
son insuficientes. Su precondición propia exige Stamina≥60 y Sapphire<capacidad
por StageBalances fresco; abastecimiento se prepara separadamente antes de Start.
El ciclo distingue insuficiencia
y capacidad llena como terminaciones funcionales, sin retries.

Burst Breaker/Berserker/Demon Blade/Kaiserin→Rion09; otra identidad sólo con
`MeteoritesCharacterScope.full_set_equipped_verified(cid)`→09, de lo contrario
Chaos06. READY/11effects completos, identidad coincidente, sin pending/released
son la autoridad; un flag, set parcial o setup iniciado no acreditan. Manual
no equipa ni limpia. Session mantiene el scope durante todos los pasos y limpia
al terminar el personaje. Stage08 sigue en Ads.

x4 se verifica/configura exclusivamente en BASE después de Claim: conservarON,
doble tap adquirido sóloOFF, verificar efecto fresco. Primer MODAL: Rion Penance,
Chaos Hell y MaoSupport ACTIVE usando el owner Ads; buffs1/2/3ON sin contador,
buff4 sólo seguro con ticket
disponible o reserva ON ya pagada. Un ticket por entrada x4 adquirido; nunca
Karats ni acciones de compra inventadas. Primer Start→Select Striker; segundo
Start→batalla, una entrada sin Auto Repeat. Reliefs transversales existentes
recuperan BASE/config, revalidan x4/readiness y permiten otro Start sólo tras
rechazo acreditado por blocker. Incertidumbre consumptiva conserva latch.

Auto usa destellos laterales, dos segundos de señal fresca y glyph Pause
independientes de otros owners. OFF→activar una vez→ON verificado; UNKNOWN
impide wait normal. Pausa cancelable30s y polling1.5s bounded120s adicionales;
cero OCR/resolver global en wait. Clear Time es overlay específico sobre batalla,
Home→Lobby limpio. MuerteMODAL→Abandon→segundoMODAL Get stronger→X→Lobby.
Reward requiere Sapphire after>before; ausencia de progreso y derrota cortan
funcionalmente. Lectura ambigua/fallo/cancelación no autorizan otra entrada.
Tras Manual, el coordinador refresca Badges/Sapphires y decide de nuevo.

Adquisición, costes, validación y límites en
[Manual Stages](MANUAL_STAGES_VALIDATION_20261009.md).

Autonomía prolongada acreditada en un batch continuo Hard112/112, sin reinicio,
wait526.906s,175observaciones y cero OCR. No equivale a una campaña de múltiples
ciclos/personajes. Deudas Arena preservadas: derrota Single; modal informativo por
umbral; Gold con buffs agotados; cancelación
física; retorno tras relief. No se fuerzan esas ramas. Nunca se compra Double
Points ni Badges con Karats; stock Double Points desconocido mantiene ese buff
OFF y permite continuar Arena con buffs1/2ON, sin gates de sus contadores.

Herramientas focales: `tools.arena_farming_evaluation` (cache por código/pixels)
y `tools.arena_farming_smoke` (preflight sin inputs, rutina real más Lobby probe,
STOP, ceiling Badge, budget, evidencia y cleanup de runtime). Validación/live
de esta entrega se registra en CONTEXT y el informe final de campaña.

## Session Report analítico

El resumen permanece visible incluso si el personaje cerró sin incidencias:
identidad/ocurrencia, resultado y terminación, duración con su autoridad,
badges usados/ganadores/perdedores y winrate global ponderado, combates x8 si
son íntegros/divisibles, secuencia y decisión final del controller, ledger/presupuesto,
Manual/MW, Sapphires, Trading y lifecycle final del personaje. Show Arena batches
expande una tabla cronológica con scroll, sin volcar logs en la GUI.

La proyección consume eventos acreditados del owner, no Victory Points ni saldo
global de Karats. Un resultado ausente/ambiguo no es cero. Identidad causal de
batch/operación permite contar una sola vez un receipt repetido; contradicciones
quedan parciales. Totales nunca cruzan personaje/ocurrencia/Session. Los batches
con conteos no divisibles siguen mostrando badges/winrate, pero no combates.
Duraciones de batch son wall del owner (incluyen preparación/retorno), no sólo
tiempo de combate. Nuevos ciclos registran wall total conservada en una reanudación
de la misma instancia; logs históricos muestran sólo el intervalo observado
resources→termination si falta esa medida. El replay Crimson acredita408/336/72,
82,35%,51/42/9,6Manual/4MW,360/360,408/400Sapphires,100Stamina/400KCoins y
RELEASED11/11. [Aceptación](ARENA_E2E_ACCEPTANCE_20261009.md) y
[checkpoint](ARENA_FARMING_CHECKPOINT_20261009.md).
