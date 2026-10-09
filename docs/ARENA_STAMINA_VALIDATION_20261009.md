# Arena Farming — presupuesto y abastecimiento de Stamina

Baseline publicada/HEAD `c607b601b9ba79d49ec0261e3dd5d475b94aea46`, rama
`rebuild/stable-baseline`. Implementación sobre el trabajo no publicado previo.
Sin commit/push, sin reset/clean; cambios independientes preservados.

## Configuración y persistencia

Un único paso Arena conserva Single Battle, Auto Repeat y Farming Cycle.
Maximum Stamina Consumption aparece exclusivamente en Farming Step Settings.
`ArenaConfig.maximum_stamina_consumption`: ausente/null/vacío sin límite; entero
no negativo, cero permite Arena/MW pero impide Manual. Apply modifica draft,
Save persiste; recarga conserva el valor por occurrence. Sin valor, JSON omite
el campo y mantiene compatibilidad; rutinas existentes no se reescriben.

## Contabilidad y reanudación

Una entrada física acreditada cuenta60, incluyendo derrota, error de Auto,
cancelación o fallo posterior de retorno/lectura. Start de Select Striker pendiente
de efecto devuelve consumo desconocido, no0. Recibo `entry_id` se acredita una
sola vez. Reanudar la misma instancia conserva consumo, preparación y controller;
el owner observa batalla/terminal antes de otro Start. Si Home ya confirmó Lobby
y faltó el balance, reanuda leyendo balances, sin otra entrada.

No se infiere consumo por before-after: Claim, compra y regeneración no reducen
el ledger. Live137→78 implica delta59, pero entrada60 y regeneración1. El gate
remaining≥60 se aplica antes de Manual;500 permite8×60=480, no una novena.
Cancelación entre entradas conserva contador/preparación. Ejecución nueva luego
de un fin funcional comienza0. Instancias y scopes distintos no comparten ledger.

## Política con límite y sin límite

Con límite, primera ruta Manual: Claim por navegación normal→Lobby→refresh del
routing→Stamina fresca. Saldo requerido floor(remaining/60)×60; compra sólo déficit.
Preparación registrada una vez, incluso sin compra o parcial. No visita TC entre
entradas. Si Claim vuelve elegible Arena/MW, difiere la preparación económica.
Ejemplo offline600, saldo180+Claim30: déficit390→ocho trades400→saldo610;
10entradas consumen600 y dejan10. Sin límite, saldo≥60 ejecuta; inferior usa
Claim y compra para alcanzar60, con excedente mínimo por unidad50. No reserva300.

La aclaración posterior de Claim ya está contemplada: el saldo previo sólo sirve
al preflight; jamás calcula ni confirma una compra. El déficit se calcula con
Stamina fresca después de completar Claim. Al reabrir Stages, `claim_rewards`
observa `claim_inactive` y retorna sin taps (logs: un único loop activo de4taps
en `cycle_supply_01`). Configuración x4/dificultad/buffs se aplica después del
abastecimiento, sin perder una configuración ya aplicada. Se conserva ruta
Stages→Lobby→TC→Lobby→Stages; Quick Menu desde Stages no se adoptó por no estar
acreditado para este owner. Sin cambios adicionales de código/smokes por esa
aclaración.

## Trading Center y seguridad económica

Mismo owner `StaminaPurchase`, mismos OpenTrading/Currency/fila Stamina, selector
unitario `>`, ConfirmTradingTrade y cierre/retorno verificados. Ads conserva
`ensure(before)` objetivo300 sin OCR KCoins. Manual `supply(before,required)`
lee par KCoins HAVE/coste en ROI C4; identidad K Coin+Stamina acreditada, precio
200/unidad50, cap disponible≤20. Selección final y coste total200×N se verifican
antes del único Trade. Un cap no acreditado nunca permite setup unbounded.

Compra limitada por déficit, cap y KCoins disponibles. Parcial registra comprado,
cobertura falsa y motivo, continúa sólo si saldo real permite60. Cap/monedas
agotados con saldo insuficiente son terminación funcional; lectura ambigua o
efecto incierto MANUAL_RESOLUTION; fallo técnico FAILED. Trade incierto guarda
recibo: débito exacto KCoins más aumento Stamina permiten reconciliar sin Trade
adicional. Regeneración por sí sola no prueba compra. Ninguna compra Karats.

## Terminaciones y lifecycle

`stamina_budget_reached` y `stamina_supply_unavailable` son COMPLETED. Arena/MW
mantienen prioridad; presupuesto sólo limita Manual. Refresh después de Claim,
compra y operación productiva, sin saldo predicho. Easy0 termina funcionalmente
aunque haya Stamina sobrante, sin gastarla ni compensarla. Controller Hard/Easy
y excepciones unchanged. Session conserva siguiente paso, Meteorites setup y
cleanup al final del personaje, Rotation y orden literal. Sin REPEAT_CURRENT.

USER_GT posterior: los tres primeros buffs Manual se activan/verifican ON sin
OCR de disponibilidad. Cuarto usa cobertura de tickets, insuficiente/ambiguo OFF,
sin Karats, como último Arena. No cambio perceptivo para esa simplificación.

## Evidencia física focal

- `artifacts/stamina_budget/payment_inspect_02`: panel nativo KCoins140471/200,
  cantidad1/20; No→Currency→X→Lobby acreditados; cero confirmaciones de compra.
- `cycle_supply_01`, run `11d1eda4ae604bf7a646aebb09953fe3`: Cat Acrobat, inicial
  Stamina57/Sapphires66/Badges106. Claim+30→87; déficit33 para presupuesto120:
  un Trade50, coste200, saldo137 y preparación registrada cubierta. Se detuvo
  antes de Start por Hell UNKNOWN transitorio; cero entrada/consumo. No repitió
  Trade. Config estable reconoció Hell OFF con NCC0.99997: causa fue apertura
  animada. Fix mínimo observa hasta dificultad conocida, bounded, sin inputs
  UNKNOWN ni bajar thresholds. Cierre adquirido Config→BASE→Lobby.
- `cycle_prepared_retry_02`, run `a1d45c91244c4dfdba20d9ce0e1b113b`: saldo ya
  preparado137, cero compras/visitas TC. Chaos06Hell; socket relief transversal,
  configuración revalidada. Un StrikerStart, AutoON20samples/peak0.158 conservado.
  Wait31.610s/2polls/0OCR, Clear Time positivo, Home y único retry tras mismo
  Clear fresco→Lobby limpio. Saldo78 (coste60+regen1), Sapphires66→110 (+44 real).
  Ledger60, remaining60/presupuesto120. Next routing MW para occurrence107/100;
  smoke limitado1operación evita lanzar MW/Arena. Lobby probe y Session COMPLETED.

No se atribuye el delta44 a una recompensa contractual fija. Default40Badges
haría Arena con106; el threshold107 fue sólo la occurrence del smoke para adquirir
la rama Manual, sin cambiar defaults ni rutinas guardadas.

## Validación y límites

Batch afectado584tests verdes: configuración/GUI/Store, presupuesto, supply,
Manual y replay, Stage Ads/navigation/Claims/socket, Trading operation/runtime/
panel, Arena/controller/MW, Session/Meteorites y routines. Tras los últimos guards
de receipt/reconciliación:132directos/afectados verdes y57del ciclo tras ajustar
el reporte de actividad física y rechazar receipts ausentes como UNKNOWN.
Evaluator nuevo de pago
3/3: panel nativo, panel dimmed y UNKNOWN; curación pequeña con hash raw→crops
en `tests/fixtures/stamina_supply`. Reader/templates globales no cambiados;
resultados anteriores de Manual/Arena siguen válidos. Sin28/28 ni Arena largos.

Compra parcial, falta de KCoins/cap y reanudaciones se verificaron offline; no
se agotaron monedas/trades ni se forzaron compras adicionales para probarlos.
La reanudación segura es de la misma instancia; no se agregó persistencia durable
de Session después de cerrar proceso. Un refresh de routing incierto conserva
ledger y corta sin permitir otra entrada; no hay recovery genérico nuevo.
Los nuevos guards no justifican repetir Arena/MW físicamente.

Final físico: Cat Acrobat, Lobby limpio, Stamina78/440, Sapphires110/102,
Badges106/106. Runtime terminado/cerrado y fuentes limpiadas por su owner.
Worktree contiene esta entrega y los cambios previos; sin commit/push.
