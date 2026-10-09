# Arena Farming Cycle — checkpoint integral y Session Report

Parent publicado `c607b601b9ba79d49ec0261e3dd5d475b94aea46`, rama
`rebuild/stable-baseline`. Alcance: controller/routing, Manual Stages, Trading/
Stamina, wiring GUI/Session/Shared Meteorites, fixes de aceptación, reporte analítico,
tests y corpus focal. [Aceptación real](ARENA_E2E_ACCEPTANCE_20261009.md) permanece
PASS: una Session Crimson Assassin, seis Rion09, cuatro MW, cuatro Arena,
ledger360/360, setup/cleanup11/11. No se repitió gameplay ni se accedió al teléfono.

## Diseño y fuentes

Session Report muestra un resumen por personaje/identidad y ocurrencia, incluso
cuando el personaje terminó sin incidencias. Un botón Show Arena batches abre
la tabla cronológica con scroll horizontal/vertical; Hide la contrae. La tabla
identifica personaje/ocurrencia, batch, dificultad, multiplicador, used/won,
winrate, combates ganados/totales, wall del owner, próxima dificultad y motivo.
Otra sesión limpia la tabla anterior. No hay un visor de logs dentro del reporte.

| Dato | Autoridad |
| --- | --- |
| Personaje/identidad | CharacterContext de Session, stable character_id |
| Status/terminación | FlowResult y arena.farming.terminated, sin transformar fin funcional en FAILED |
| Used/won | Batch tipado y decisión aceptada por controller; Used y Acquired Karats físicos |
| Multiplicador/vínculo/duración batch | ArenaBatchResult/provenance y ArenaFlowResult.metrics ya acreditados |
| Próxima dificultad/motivo | Decisión del controller vinculada al mismo batch |
| Consumo/presupuesto | Ledger causal del coordinador/config de la ocurrencia, nunca delta neto de saldo |
| Entradas Manual/pases MW | Receipts60 únicos y completed acreditados de las operaciones subordinadas |
| Sapphires | Before/after frescos de Manual/progress y MW/sapphire_effect |
| Stamina comprada/coste | StaminaSupplyResult confirmado del owner Trading, tras una sola confirmación |
| Shared Meteorites final | Scope/report final del personaje en Session; no IO ni cleanup del proyector |

Instrumentación mínima: el coordinador añade batch_id, operation_index, multiplicador
y wall del owner a su decisión existente; receipts Manual y metadata terminal
del ledger/ciclo; StaminaPurchase devuelve el coste ya verificado; MW publica
su before existente junto al after. No nuevas lecturas, timers de polling,
intents económicos, retries ni cambios de gameplay para generar el reporte.

Winrate global **sum(won)/sum(used)**; badges perdedores **used−won**.
No promedia winrates por batch. Combates sólo con x8 acreditado y ambos conteos
divisibles; en otro caso N/D conserva los badges. Double Points no cambia Acquired
Karats→won_tickets; no usa Victory Points ni saldos globales de Karats.

Receipts exactos duplicados cuentan una vez por identidad causal dentro de la
ocurrencia. Dos receipts incompatibles para el mismo batch/operación se excluyen
y quedan parciales. Operaciones sin terminal no son cero victorias. Los totales
válidos pueden mostrarse como parciales; ausentes son N/D. Personajes/ocurrencias/
Session no se agregan entre sí. UNKNOWN no crea victorias, compras ni consumo.

Duración nueva de ciclo: wall del owner, conservada durante una reanudación
de la misma instancia (incluye el intervalo de interrupción). Histórico Crimson:
faltaba esa medición, por lo que se etiqueta el intervalo resources→termination
**49m53,965s**; Session **51m02,064s**, runtime **51m09,776s**, no se confunden.
Duraciones batch incluyen preparación/espera/cierre/retorno, no sólo combate.

## Replay real de Crimson

`tests/fixtures/session_report_arena/crimson_cycle.json` cura los71 eventos de
negocio del log `20261009T220833.531536Z_session_7621171c.jsonl`, con SHA256 del
source y autoridad de cada join. No inventa nuevos valores físicos. Routing y
attempt vinculan decisiones con los cuatro arena.finished; el multiplicador
hereda USER_GT y el contrato x8 requerido por el resultado/controller aceptado.
Identidad histórica de batch deriva de run/flow operation/attempt del log,
sin fabricar UUID de Arena. Pago400 se enlaza con stages.stamina_purchase;
before MW con el receipt diagnóstico existente. Presupuesto360 proviene de la
rutina GUI guardada y ledger terminal; entradas usan los seis segundos Start
acreditados. Metadata lifecycle se copia del último session.meteorites.

| Batch | Dificultad | Used | Won | Winrate | Ganadas/totales | Próxima / razón |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Hard | 104 | 80 | 76,92% | 10/13 | Hard / collect_recent_batches |
| 2 | Hard | 104 | 88 | 84,62% | 11/13 | Normal / adjacent_uncertainty |
| 3 | Normal | 96 | 72 | 75,00% | 9/12 | Normal / collect_recent_batches |
| 4 | Normal | 104 | 96 | 92,31% | 12/13 | Hard / recent_reward_advantage |

Resumen verificado: **408used / 336won / 72lost**, **82,35%**, **51/42/9combates**,
**6Manual / 4MW**, **360/360Stamina**, **408/400Sapphires**, **100Stamina por
400KCoins**, `stamina_budget_reached`, Shared **RELEASED/11Unequip**.
Hard final del controller es la selección para el próximo batch; el último
batch ejecutado fue Normal. Easy0 es fin funcional válido, distinto de aceptación
integral por presupuesto. Tests cubren ambos motivos y fallos/cancelación.

## Compatibilidad y preservación

Gold y Single/Auto no exigen metadata Farming ni crean esa sección. Legacy
Farming sin datos causa información parcial, sin excepción ni ceros inventados.
Lifecycle, continuación y cancelación de Session no se modifican para el reporte.

INDEX se arma por paths y hunks concretos. Fuera del checkpoint: SDK inset Ads,
Equipment payment wrap, MW readiness scope/fact observer, Summon Pet/transición,
sus tests/corpus y secciones CONTEXT, helpers/campañas Gold, scripts exploratorios,
la eliminación del plan histórico y raw/logs/config local. No git add -A/reset/clean.
El export del INDEX contiene únicamente lo publicable; se compara con el parent
para separar regresiones de tests antiguos/limitaciones del entorno.

Corpus versionado: assets runtime y fixtures focales portables, manifests curados.
El corpus ancho sparse de Manual permanece local ignorado; para evaluator se
copia únicamente lo referenciado por manifest y se verifican sus SHA256. No se
publican capturas grandes ni logs/artifacts/AGENT_LOCAL/.env/rutinas privadas.

## Validación del snapshot

Validación offline sobre exportaciones del INDEX, con imports comprobados desde
esas copias. El snapshot final de código/tests/assets pasa **1.055 tests afectados**
de Arena, Manual, Stamina, MW, Meteorites, Session, GUI y Gold. Incluye replay real,
ponderación, cero explícito, ausencia/ambigüedad, duplicados/reanudación, separación
de personajes/ocurrencias, adaptación, Stamina/Easy0, recursos, Trading y lifecycle.
Los tests directos del reporte/GUI/ledger/compra pasan **171/171**.

Evaluators del snapshot: **Arena9/9**, **Manual20/20**, **Stamina3/3**, wrong=0,
sin cache reutilizada. La última corrección sólo afecta el proyector/recibo Manual
incompleto→N/D y su test; los hashes de los owners perceptivos, assets y entradas
de esos evaluators permanecen iguales. GUI offline revisada con resumen y tabla
expandida, sin ejecución productiva ni teléfono.

Suite amplia del INDEX: **5.085 passed / 296 failed / 27 skipped**. Los mismos
**296 nodeids** fallan en una exportación limpia del parent publicado; ninguno es
un test nuevo de este checkpoint. **293 mensajes normalizados coinciden**; los
otros tres difieren en el path temporal o el orden de sets en el mensaje. Incluyen
corpus histórico local ausente, scopes/vocabulario antiguos y once tests GUI
desfasados/URI Windows. No se presenta la suite amplia como verde. El filtro GUI
de la corrida final incluyó Guild incidentalmente: siete fallos por corpus ausente
ya reproducidos en parent, aparte de los 1.055 tests afectados passing.

Se revisa `git diff --cached --check`, alcance de los 130 paths/hunks, identidad
del export con blobs del INDEX mediante filtros Git (CRLF Windows), SHA256 de
fixtures/manifest y preservación del inventario independiente. Los780 inputs
sparse del evaluator Manual se copian sólo después de verificar sus hashes;
permanecen fuera del INDEX. La revisión documental final no invalida los tests:
código, tests y assets se comparan con la exportación efectivamente probada.

Resultados, XML, selección de tests, hashes y auditorías permanecen locales en
`artifacts/arena_checkpoint_20261009/`. Sin campaña física, smoke ceremonial,
corrección de fallos ajenos ni frente nuevo.
