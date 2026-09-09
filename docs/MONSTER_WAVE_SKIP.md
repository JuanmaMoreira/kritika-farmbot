# Monster Wave SKIP-only

Implementado en `feature/monster-wave-skip`, pendiente de revisión, sin commit ni
push. Segundo consumidor real de `BattleModeZone`, con una única implementación
de gameplay en `MonsterWaveActivity`. Cada invocación hace **un proceso SKIP con
MAX**. La cantidad interna que el juego resuelva (x1, x83, x100, etc.) no crea un
loop del bot. No hay acción ni target de Start manual, batalla MW o Auto Battle.

## Máquina de estados

```text
hub fresco → OpenMonsterWave → observar entrada
  Weekly Results / New Ranking → OK verificado → reobservar (máximo 2 acknowledgements)
  MW limpio → sólo Daily: leer sapphires frescos antes de cualquier operación SKIP
    0..3 → daily_sapphires_below_minimum → Back → hub, sin iniciar intento
    >=4 → continuar; OCR inconcluso/fallido → técnico conservador, sin input SKIP
  NEEDS_TICKETS
    purchase=false → tickets_missing_purchase_disabled → Back → hub
    purchase=true → Purchase SKIP Ticket → Fill All una vez
      → verificar 30/30 en popup → cerrar → verificar READY
  READY → Activate SKIP una vez → verificar ACTIVE
  ACTIVE → double tap MAX → frame fresco estable: ACTIVE + MAX + controles visibles
    → Start SKIP process una vez
      insufficient sapphires → No → MW limpio → Back → hub
      inventory board
        continue=false → No → MW limpio → Back → hub
        continue=true → Yes → CLEAR o blocker duro
      blocker duro → resolución manual, sin más input
      CLEAR → OK → MW limpio → Back → hub
```

Las esperas y acciones usan `VerifiedTransition`, estabilidad de 0,25 s, budget
normal de 6 s y gracia pasiva de 2 s. Cada operación del activity tiene un único
intento: no repite compras, activaciones, selección MAX, Start SKIP ni confirmaciones.
UNKNOWN, AMBIGUOUS, señales contradictorias y postcondiciones no verificadas nunca
autorizan el paso siguiente ni cleanup a ciegas. Cancelación detiene la ejecución.
Las navegaciones externas de `BattleModeZone` conservan su retry de dos intentos
con origen fresco y guard exacto.

## Normalización de entrada

Weekly / previous season results y New Ranking son obstrucciones operacionales
con ground truth humano **OK → MW limpio**. No son MANUAL_RESOLUTION ni generan
BUSINESS_INCOMPLETE por sí mismos. Cada reconocimiento requiere MW resuelto y
exactamente el overlay conocido; la acción OK exige su desaparición y un frame
nuevo estable antes del siguiente paso. No hay input adicional si están ausentes.

Weekly se identifica por el pie fijo “Ranking rewards will be sent to mailbox.”,
sin usar season, clase, ranks o cantidades dinámicas. Aparece por personaje tras
reset semanal y no reclama directamente rewards, consume sapphires ni modifica
tickets/SKIP. New Ranking informa una actualización de la temporada actual.

La normalización observa iterativamente, con máximo dos acknowledgements. No
presupone aparición, coexistencia ni orden combinado. Un popup persistente no
autoriza repetir OK; UNKNOWN, overlay desconocido o budget agotado detienen con
resultado técnico y sin taps especulativos. Los tests defensivos de alternancia
validan el límite, no afirman una secuencia combinada adquirida.

## Estado SKIP y frescura

`skip_state(snapshot)` es puro y exige MW resuelto, sin overlays incompatibles:

| Estado | Evidencia positiva | Contradicciones rechazadas |
| --- | --- | --- |
| NEEDS_TICKETS | Activate SKIP gris | READY, timer o Start SKIP |
| READY | 30/30 y Activate SKIP verde | NEEDS_TICKETS, timer o Start SKIP |
| ACTIVE | Time Remaining y Start SKIP process | NEEDS_TICKETS o READY |

La compra abre el popup sólo desde NEEDS_TICKETS. Fill All delega al juego la
cantidad faltante según el contador actual: la ruta adquirida incluye 20/30 →
30/30, costo 1.400.000 GOLD y costo restante cero. No se simulan incrementos ni se
pulsa x1 repetidamente. 30/30 verificado en el popup es requisito de cierre, y
READY verificado en MW es requisito de activación. Si la compra no progresa o la
postcondición es ilegible, la ejecución falla conservadoramente y no recompra.

El timer es account-wide, pero no se almacena `skip_active`, countdown, recursos o
decisiones entre invocaciones/personajes. ACTIVE directo omite compra y activación.
Una entrada posterior NEEDS_TICKETS manda aunque antes se haya observado ACTIVE.
Si el timer expira durante MAX y deja de verificarse ACTIVE, no se inicia SKIP.
No hay recovery de expiración ni farming loop en esta fase.

## MAX fijo y tooltip

`SelectMonsterWaveMax` es una acción semántica indivisible de dos taps al mismo
control normalizado. `ActionExecutor` llama dos veces consecutivas a `AdbClient.tap`,
sin observar, decidir, esperar ni verificar entre ambos. No es un retry. Un error
físico detiene la acción; no se intenta compensar con más taps. La cancelación se
comprueba antes y después de esta operación acotada.

La verificación posterior requiere en el mismo frame fresco:

- MW limpio y ACTIVE coherente.
- MAX con su check y aro de selección dorado.
- Los controles adyacentes x2/x3 descubiertos: señal positiva de visibilidad,
  **sin seleccionarlos**. Su ROI está cubierta por el tooltip adquirido.
- Ausencia del landmark/overlay del tooltip informativo.

La ausencia de un detector de tooltip por sí sola no autoriza Start. Un recuadro
persistente o MAX sin verificar consume sólo espera y termina sin Start ni más
taps MAX. La señal de controles visibles también se evalúa contra Tower, los
popups, selecciones no MAX y el corpus global. MAX es fijo y puede consumir hasta
100 sapphires según disponibilidad; esa regla no se usa para calcular el saldo.
El popup real de sapphires insuficientes conserva su handling general. Daily añade
el guard previo descrito abajo; no se atribuye un popup a ese guard.

## Configuración y composición

`RuntimeConfig.monster_wave` contiene `MonsterWaveConfig` con sólo dos booleanos,
ambos `false` por defecto. GUI y CLI los cargan mediante su configuración `.env`
habitual; las variables del entorno tienen la precedencia existente:

```dotenv
MW_PURCHASE_SKIP_TICKETS=false
MW_CONTINUE_WHEN_NONBLOCKING_INVENTORY_FULL=false
```

No se agrega framework de options ni opciones x1/x2/x3/MAX. Activar compra autoriza
únicamente Fill All en Purchase SKIP Ticket; activar continuación del board acepta
la pérdida de rewards que excedan los límites mostrados.

Standalone y Run Selected Flows:

```text
Lobby → BattleModeZone.enter → MonsterWaveActivity → BattleModeZone.leave → Lobby
```

Daily instala `MonsterWaveDailyEligibility` exclusivamente en la sesión. Observa
el badge de la card MW en el hub, con la misma ventana estable de 0,75 s y budget
de 6 s que WB. Badge ausente produce `SKIPPED_NOT_ELIGIBLE` sin entrar a MW; UNKNOWN,
AMBIGUOUS o fluctuación no equivalen a ausencia. MW manual ignora ese badge.

### Guard Daily de sapphires frescos

Daily requiere MW x4; ejecutar MAX con 1–3 consume recursos sin poder completarla.
Sólo `ProductiveRuntime.run_session` habilita el guard mediante el binding
`prepared(zone, daily=True)`. Standalone / Run Selected Flows siguen ejecutando
MAX con 1–3 sin imponer un mínimo Daily ni solicitar esa lectura.

El orden es badge en hub → entrada MW → normalización → MW limpio → OCR fresco.
NOT_ELIGIBLE omite entrada y lectura. UNKNOWN/failure de eligibility aborta antes
de ambas. Con eligibility positiva, la lectura ocurre antes de comprar tickets,
activar, seleccionar MAX o Start, incluso si hay NEEDS_TICKETS.

`read_sapphires(context=screen.monster_wave, after_sequence=entrada_limpia, timeout=6)`
selecciona un extractor específico del HUD superior: ROI normalizada
`(.617,.040,.676,.082)`, sólo el número entre icono azul y botón +, fuera del chat.
Usa el engine compartido, escala 2, parser entero y confianza mínima 0,50 existentes.
Exige **dos valores iguales en hasta tres frames nuevos**, separados al menos
0,20 s, con MW resuelto y sin overlays. Un popup invalida el contexto aunque su
HUD se pueda leer. WB mantiene el extractor Lobby y su ROI Survival sin cambios.

La activity rechaza facts con contexto ajeno o evidencia anterior a la entrada
limpia, y reobserva estado SKIP después de la última muestra OCR antes del input.
No conserva saldo entre actividades/personajes ni calcula `saldo_anterior - 5`.
Así WB → MW con 8 antes de WB y 3 observados después sale sin intentar SKIP.

Saldo 0..3 produce `monster_wave.daily_sapphires_below_minimum` con
`observed_balance`, `required_sapphires=4`, `attempt_started=false` y secuencia de
observación; Back → hub debe verificarse. SessionReport lo clasifica
BUSINESS_INCOMPLETE sin afirmar Insufficient Sapphire. Saldo >=4 permite la máquina
SKIP normal. Lectura ilegible/incierta, timeout, contexto incompatible o fallo OCR
detiene técnicamente, sin input SKIP; cancelación conserva su resultado propio.

El runtime vincula los wrappers WB y MW a una misma instancia de zona. Sólo las
posiciones consecutivas comparten visita, en el orden seleccionado, incluidos
skips y el terminal WB por pocos sapphires. WB → MW y MW → WB abren una vez y
cierran una vez. Un flow intermedio cierra y vuelve a abrir. No se reordena ni
amplía la allow-list de Rotation, scopes, Identity o planning.

## Boundaries y reports

| Evidencia / decisión | Resultado del flow | Business event |
| --- | --- | --- |
| CLEAR observado y retornos verificados | COMPLETED | `monster_wave.completed` |
| Daily ausente en hub | SKIPPED_NOT_ELIGIBLE | Skip del runner, sin activity |
| Daily con saldo fresco 0..3 | Back y retorno verificado | `monster_wave.daily_sapphires_below_minimum` |
| Tickets faltantes y compra desactivada | COMPLETED | `monster_wave.tickets_missing_purchase_disabled` |
| Insufficient Sapphire | No y retorno verificado | `monster_wave.insufficient_sapphires` |
| Board y continuación desactivada | No y retorno verificado | `monster_wave.inventory_warning_declined` |
| Blocker duro sin return adquirido | MANUAL_RESOLUTION | `monster_wave.manual_resolution` |
| Cancelación | CANCELLED | Lifecycle existente |
| Input/captura/guard/retorno sin verificar | FAILED | FailureCause y Failure Evidence existentes |

`monster_wave.tickets_purchased` informa sólo progreso a 30/30 verificado.
El evento CLEAR conserva evidencia de gameplay aunque falle posteriormente OK,
Back o el cierre de zona; el resultado final conserva la precedencia técnica.
Los terminales business limpios se proyectan como BUSINESS_INCOMPLETE, sin failure.

`MANUAL_RESOLUTION` es el mínimo terminal operacional necesario para detenerse en
un popup sin fingir un retorno exitoso al hub ni convertir un blocker conocido en
fallo técnico. SessionRunner publica el evento, conserva la posición y detiene la
sesión sin cerrar zona, ejecutar otro flow o rotar. El wrapper y Run Selected Flows
también se detienen. GUI muestra “Manual resolution required”; SessionReport lo
proyecta como BUSINESS_INCOMPLETE. No hay reanudación automática del proceso desde
ese popup: la próxima ejecución debe comenzar desde su precondición adquirida.

El inventory board es no bloqueante. Su texto advierte pérdida de rewards y los
inventarios incluyen Arena Tickets/Brawler's Badges, Weapon Material, Hero Weapon
Material y Bronze/Silver Keys. No es un error técnico. La respuesta No no compra
sapphires ni consume un intento; el activity termina, sin reintento estratégico.
El popup de insufficient sapphires siempre recibe No; no existe intent MW para Yes.

## Corrección de semántica compartida y reliefs

La documentación anterior confundía el literal del blocker. Los assets y las
adquisiciones productivas establecen:

- **`popup.socket_inventory_full`**: “The bag is full. Would you like to organize
  your bag?”. Coincide con `monster-wave-bag-full`. Su handling WB tiene Yes hacia
  Socket, support operation acotada y return adquirido exclusivamente a WB.
- **`popup.equipment_inventory_full`**: “Bag is full. You need at least 1 empty
  slot to continue. Select a method to organize your bag.” Su handling WB permite
  Combine y retorno verificado desde Combine a WB.

Se corrige el documento de zona y se reutiliza Socket para la captura MW, sin
renombrar vocabulario productivo ni duplicar detectores. MW reconoce ambos
blockers compartidos y no llama sus reliefs: ningún return plan MW está adquirido.
No se infiere destino desde un tap o un match. Para promover
`MW → blocker → support relief → MW`, hace falta adquirir explícitamente el return;
el ownership de la intención seguirá en la activity, no en la zona o percepción.

## Evidencia y calibración

`datasets/monster_wave_semantic_manifest.json` contiene 97 frames curados (hasta
tres muestras por estado) de las tres adquisiciones. Todas las capturas raw se
preservan; las copias curadas bajo `screencaps/` son locales e ignoradas. Los assets
runtime están en `assets/ui/landmarks/monster-wave/`. La curation no incorpora
identidad personal, seriales ni valores de recursos al runtime.

El título usa un fragmento fijo a la izquierda, fuera del chat observado en
`[0.44,0.12,0.85,0.21]` y de los paneles adquiridos. La entrada day2 con chat visible
es positiva real. Se descartó `View Ranking Reward` como landmark porque también
existe en WB. El tooltip y los popups renderizan por encima de la pantalla; no se
movieron ROIs por mera intersección geométrica.

Se revisaron y ampliaron etiquetas MW de 22 frames históricos de Battle Mode en
tres manifests. Existen positivos con WB Daily ausente y negativos MW con WB/Tower
activos; un badge de otra card no autoriza MW. No se altera el ground truth WB.

Calibración: 16 landmarks contra los 510 frames del corpus productivo, con separación
positiva/negativa para cada nuevo detector. El gap más estrecho es 30/30 del popup
(raw positivo mínimo 0,96093; negativo 20/30 máximo 0,93132); el umbral semántico
0,80 y su calibración exigen raw ≥0,95501. MAX separa seleccionado de no seleccionado
(mínimo positivo 0,94050, máximo negativo 0,57798). Los thresholds no se relajan.
Weekly separa positivo mínimo 0,98110 de negativo máximo 0,39252. Se conservan
todos los thresholds anteriores. La nueva evidencia también se evalúa contra
todos los detectores productivos.

`datasets/monster_wave_ocr_manifest.json` conserva positivos HUD reales 0, 70, 83
y 183 en NEEDS/READY/ACTIVE/MAX y retornos, más negativos de popups, tooltip, hub
y Tower. Los tests reproducen OCR y exigen rechazo contextual antes de invocar el
engine. Los valores bajos no nulos 1–4 se cubren como decisiones/consenso mediante
tests deterministas; no se presentan como evidencia live de OCR adquirida.

Herramientas offline, desde la raíz:

```powershell
./tools/agent_run.ps1 tools.curate_monster_wave_evidence
./tools/agent_run.ps1 tools.calibrate_monster_wave
./tools/agent_run.ps1 tools.production_perception_evaluation --output artifacts/semantic_slice/monster-wave-weekly-production.json
./tools/agent_run.ps1 pytest -q
git diff --check
```

La calibración genera un informe para revisión; no cambia automáticamente los
thresholds productivos. El evaluator reutiliza pares válidos por contenido y
recalcula resolver/labels. Resultado del patch: **510 frames, 0 wrong, 0 ambiguous**;
los 70 UNKNOWN son negativos de contextos fuera del catálogo. Las 75 capturas MW
resuelven correctamente. El live previo del usuario confirmó ACTIVE, MAX, Start
hacia inventory board y policy false → No → inventory_warning_declined. Este
patch se valida offline, sin nuevo smoke físico; el default del board sigue false.

## Gaps y exclusiones

- GOLD <140.000 con tickets faltantes: sin literal/ground truth. No se reutiliza
  el popup GOLD de Black Market por suposición. Compra no verificable no se repite.
- Returns de Socket/Equipment a MW y rama negativa del blocker: sin navegación
  automática. Weekly y New Ranking ya son normalizaciones automáticas adquiridas.
- Expiración real durante una operación: se rechaza pérdida de ACTIVE; no hay
  reactivación automática ni adquisición temporal nueva.
- Sólo selecciones MAX y no-MAX adquiridas; rendering/layouts futuros requieren
  evidencia, como el resto de percepción local del runtime.
- Tower, Stages, Arena, loops, RoutineSpec, nuevos scopes, Keys Relief y Crafting
  Materials Relief permanecen fuera del alcance.

## Validación

Resultado del patch: **1925/1925 tests hardware-free** en 292,48 s y **438 dirigidos**
verdes, sobre baseline de 1857 tests. Evaluator: **510 frames, 0 wrong, 0 ambiguous**.
`git diff --check`, hashes de 97 curados/108 raws, enlaces y whitespace válidos.
La validación nueva
incluye normalización, guard Daily, lectura fresca WB → MW, saldos 0..4 y mayores,
manual 1..3, OCR/contexto/consenso, reports y regresiones WB. Resultados finales del
patch en `CONTEXT.md`; reportes locales `artifacts/monster-wave-weekly-directed.txt`,
`artifacts/monster-wave-weekly-pytest.txt` y
`artifacts/semantic_slice/monster-wave-weekly-production.json`. Sin commit ni push.

Pruebas dirigidas: policy de tickets/board, estado fresco entre invocaciones,
READY/ACTIVE, exactamente dos taps MAX sin observación intermedia, tooltip persistente,
MAX no verificado, expiry/UNKNOWN, No de sapphires, CLEAR/OK/Back, cancelación y
compra fallida sin repetición. Integración real con WB/MW en ambos órdenes,
Daily/manual, zona compartida, separación por otro flow, precheck WB, reports,
resolución manual, GUI y causas técnicas. Estado final de suite en `CONTEXT.md`.
