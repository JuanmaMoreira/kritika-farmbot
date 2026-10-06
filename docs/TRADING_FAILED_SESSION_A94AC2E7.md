# Trading FAILED manual — 2026-10-06

## Run y primera divergencia

| Campo | Evidencia exacta |
| --- | --- |
| GUI log | `logs/20261006T153842.516960Z_session_ef92f6d3.jsonl` |
| run | `5c599d7e4c5a406394d3c18c46b07fb7` |
| session | `a94ac2e7e19c47389bacda3db00ecc61` |
| Inicio | 12:38:47.602 ART / 15:38:47.602 UTC, session.started event19 |
| Scope | Ice Warlock, índice17/19 de esta continuación manual;16 Rotations completas |
| Routine | Basic Gold Farming (`basic-gold`), step3 `gold_farming`, occurrence1 |
| Caller | MW `final_investment`, attempt2; preparación `keys_promotion` |
| Trading phase | Silver→Gold, post-confirm / adquisición de efecto |
| Primera divergencia | 15:11:14.448 ART / 18:11:14.448 UTC, event25010, frame93095 |
| Trade FAILED | 15:11:17.415 ART, event25031, `after_fact_unreadable` |
| Session FAILED | 15:11:17.670 ART, event25061, `preparation_failed:step_failed:keys_promotion` |

La campaña llamada manual28 por el usuario continuó desde Crimson Assassin
(scope1 de este JSONL, identity event22); `session.started` declara19 personajes.
No presentar este archivo como una ejecución nueva de28 ni confundir índice17
de la continuación con una posición global. El manual anterior `f4663332` se
detuvo en Crimson Assassin, índice10, nueve Rotations; éste es el fallo posterior
de Trading, no Sweep, smoke, MW A1 ni un test.

## Cadena causal desde el log

| Último estado / acción | Evidencia usada y efecto |
| --- | --- |
| Keys limpio, Bronze6/10, Silver215/10 | Consenso fresco frames93029/93034; ready event24987 |
| Abrir fila Gold Key2 | `SelectTradingRow`, source93034, dispatch24991 a15:11:08.478 ART |
| Item Trade válido | Frame93046/event24994: Silver `(215/10)`, output Gold Key, cantidad1/20; identidad/coste/cantidad fuertes, edad final.716s |
| Decidir MAX | `min(20, 215//10)=20`, seleccionado1; `>>` necesario |
| Un `>>` | `SelectTradingMaximum`, source93046, dispatch24998 a15:11:09.797 ART |
| MAX fresco verificado | Frame93057/event25000: `(215/200)`, cantidad20/20; edad final.675s |
| Un confirm | `ConfirmTradingTrade`, source93057, dispatch25004 a15:11:10.864 ART |
| Vuelve lista Keys | Primer frame post-confirm93068 muestra Silver15/10; no Item Trade ni alert acreditado. El miss de título Item Trade al cerrar es esperado |
| Primera divergencia | Frame93095/event25010: Bronze6/10 válido; Silver OCR `15/10J` con.88277, debajo de.90 y fuera del parser estricto |
| Espera sin inputs | Mismo rechazo en93099,93104,93115,93120,93124; nunca consenso completo |
| FAILED | after_fact nulo, `after_fact_unreadable`, inputs exactamente `tap_row,tap_max,tap_confirm` |

**LIVE_EVIDENCE + USER_GT:** el teléfono preservado muestra6 Bronze y15 Silver.
El decremento físico215→15 corresponde a los20 trades ya confirmados; el fallo
es su acreditación perceptiva. No repetir ese consumo. Ningún evento registra
un `>>` desde15/10 ni un popup inesperado en esta operación.

## Causa y fix

El reader blanco unía todos los componentes del footer compatibles por tamaño,
incluyendo decoración del icono fuera de la línea numérica. Esa región permite
texto espurio; el FAILED conserva exactamente el sufijo `J`. El fix local en
`bot/trading_key_row_reader.py::_prepare_pair` ancla la unión a los tops de los
glyphs altos concordantes y conserva todos los componentes alineados, evitando
la cadena izquierda que puede perder un dígito inicial. No cambia las ROIs,
templates, parser, threshold.90, consenso2, bounds ni guards de input.

Límite de evidencia: FailureEvidence conservó los frames originales a960×433,
no los pixels nativos2712×1224. El fixture nativo es una adquisición posterior
del **mismo estado físico preservado**, con procedencia explícita. No se presenta
como recuperación de compresión original. Una perturbación sintética del borde,
sin modificar dígitos, contrasta preparación anterior `15/10J`/.89461 y nueva
`15/10`/.99994; es una prueba de aislamiento de la línea, no otra captura del run.
Las capturas nuevas sin perturbación leen15/10 también con el reader anterior;
no se afirma reproducción natural del fallo original.

## Cantidad y `>>`

La fila izquierda nombra el **output**. `Silver Key2` consume Bronze;
`Gold Key2` consume Silver. La celda derecha `15/10` es inventario/coste de
entrada por trade, no quince trades ni capacidad Gold. En Item Trade el coste
mostrado escala con el numerador seleccionado, y el reader lo divide exactamente
para recuperar coste por unidad. `1/20` significa un trade seleccionado de un
batch de hasta20; el máximo útil actual es `min(cap observado, have//need)=1`.

El C4 existente ya omite `>>` cuando la cantidad fresca satisface el intent.
En el FAILED1→20 sí era necesario y produjo20/20 sin alert. La sospecha no es
la causa: **Caso C**. El caso equivalente15/10 +1/20 está cubierto explícitamente
por una regresión productiva, junto al caso normal215/10 +1/20→20/20.

El corpus previo tiene un alert de límite:
`screencaps/semantic/inventory-relief/trading-trade-limit-popup/01.png`;
el reader acredita “You cannot exceed the available number” / “of items you have
for trade”, botón OK, como `shows_limit`. GT clasifica Item Trade y alerts como
MODAL superior que captura input. No hubo un modal nuevo en este FAILED ni se
adquirió uno artificialmente. C4 retorna la frontera; UNKNOWN nunca habilita
confirm, Cancel o Back detrás del alert. No se añade un detector global.

## Evidencia curada y validación

- `tests/fixtures/trading_session_a94ac2e7/manifest.json`: label
  `trading_keys_bronze6_silver15_post_confirm`, crop nativo de títulos/celdas,
  geometría y SHA256; eventos causales exactos en `events.json`.
- `tests/test_trading_failed_session_replay.py`: seis regresiones. Replay de OCR
  **registrado** reproduce FAILED sin retry; OCR real del fixture acredita efecto
  y SUCCESS con un confirm;15/10 omite MAX;215/10 lo usa una vez; borde fuera de
  línea no contamina el número. Contexto del replay procede de label/observaciones
  acreditadas; los snapshots sintéticos no son una nueva prueba del resolver.
- 209 tests dirigidos passed: replay nuevo, key row reader, Keys productivo/C5,
  C4, panel reader, telemetry y keys_promotion runtime. Incluyen incremental
  perceptivo afectado (ocho positivos previos/cuatro grupos negativos), parser,
  identidad, premium, fresh guards, rechazo tardío y confirm único.
- `git diff --check` limpio. Sin evaluator global ni suite completa.

Raw local en `artifacts/trading_failed_20261006/`:
`preserved_before.png`, streams/observaciones previos al input, crops/preparación,
`quantity_before.png`, `quantity_panel.png`, `quantity_smoke.json`, scripts de
adquisición/contraste. Failure original en
`artifacts/failure_evidence/failure_cc7e9afb653c4e3ca40bcf56f41943ca/`.
Ningún raw grande se añade a archivos productivos o al corpus global.

**Smoke live focal:** reader corregido sobre Keys preservado obtiene6/10 y15/10;
consenso fresco precede un único `SelectTradingRow` Gold Key. Snapshot posterior
a dispatch acredita input Silver `(15/10)`, output Gold Key, cantidad1/20, coste
secundario vacío y máximo útil1. No `>>`, no confirm ni compras/trades adicionales.
Detenido en el último punto seguro; Item Trade queda abierto. La fuente scrcpy
cierra procesos/sockets/forward por su context manager. Efecto económico posterior
al fix validado por replay/integración, no por un nuevo consumo físico.

## Separación del estado local

- **Relief refactor del checkpoint:** policy de rutina v2/migración, coordinator,
  GUI y wiring de owners existentes; consumidores ajenos al contrato de policy.
- **MW fix del checkpoint:** `monster_wave_board_perception`, wiring A1,
  `mw_session_86adecd4`, tests/read-only smoke e informe MW; auditoría MAX y fix
  mínimo de segunda preparación documentados en ese informe.
- **Trading nuevo:** sólo preparación de glyphs Keys, replay/fixture focal,
  este informe y fuentes dueñas GT/estado/pendientes.
- **Trabajo anterior independiente:** Sell K Coins/payment-wrap, helpers locales
  `check_eval.py`, `fix_tests.py`, `test_live.py`, `test_wait.py`, borrado previo del
  plan Astra y demás diff original; sin reset/revert/clean/stage.
- **Ads:** USER_GT de la campaña de hoy con Ads renovadas y dos failures ajenos
  a Ads cierra la deuda de amplitud live. Notas de campañas previas son históricas.
  No se ejecutó Ads; targeted swipe/calibración permanece cerrado y sin cambios.

Cierre conjunto limitado a Reliefs/MW/Trading, sin otra campaña28/28 ni consumo del
trade restante. Índice/run/session se toman del log actual;209 passed es validación
dirigida previa, no se suma a las selecciones consolidadas del checkpoint.
