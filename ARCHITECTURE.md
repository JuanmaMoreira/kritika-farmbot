# Arquitectura — contratos estables

`IMPLEMENTATION_CONTRACT`. [GAMEPLAY_GT](docs/GAMEPLAY_GT.md) define la UI física; [CONTEXT](CONTEXT.md) declara wiring y divergencias actuales; [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md) concentra composición económica. Los nombres técnicos base/overlay del resolver no son la clasificación física canónica.

## Flujo y ownership

```text
Capture → Perception / Runtime Facts → ContextResolver
        → RuntimeObserver snapshot → Flow / support operation / SessionRunner
        → operación semántica verificada → ActionExecutor → AdbClient
```

| Owner | Responsabilidad y límite |
| --- | --- |
| ScrcpyFrameSource | Captura y cleanup de sus recursos |
| PerceptionEngine y readers | Observaciones/facts semánticos; nunca navegación o negocio. OCR demand-driven para datos necesarios |
| ContextResolver | Resolución pura y determinista: RESOLVED / UNKNOWN / AMBIGUOUS; no captura, input ni policy temporal |
| RuntimeObserver / TemporalObserver | Snapshot coherente de frame, secuencia, tiempo, observaciones, facts y geometría; evidencia multiframe sólo donde hace falta |
| Flow / activity | Intención de negocio, gates, outcomes y composición de operaciones; sin CV/ADB directos |
| AdsManager / AndroidAdsObserver | Lifecycle transversal de publicidad; ownership Android, progreso/cierre seguro y retorno. El caller prueba reward y decide retry |
| Support operation | Relief concreto y retorno caller-specific; no planner ni recovery general |
| BattleModeZone / PreparedActivity | Entrada/salida del hub y binding de actividad; sin gameplay o policy de inventario |
| Routine/Session | Secuencia literal, scope por personaje y próximo step útil |
| Rotation | Cambio de personaje desde entry capability verificada; selección/identidad propias |
| Eligibility / Identity | Contexto y skips en flows que lo requieren; MW no usa Eligibility. Sin estrategia automática |
| VerifiedTransition | Precondición, acción, efecto esperado; retry bounded y guardado con evidencia fresca |
| ActionExecutor / AdbClient | Intent validado → input según frame.shape / único límite activo ADB |
| CLI / GUI / observabilidad | Configuración, ejecución, cancelación y reporte; no policy de negocio |

El usuario selecciona objetivos/orden. La sesión solicita entries compatibles y puede compartir hub/contexto, sin reordenar. Failure/cancelación no dispara navegación ciega en un finally. AdsManager permanece separado de percepción normal.

## Character Identity y estado persistente

`LobbyNameRecognizer` resuelve el conjunto cerrado de28 nombres personales
conocidos desde clean Lobby. Los25 nombres ordinarios requieren canonical OCR;
los tres DRAKEN Unicode requieren además coincidencia visual del nombre y margen
independiente del sufijo. Evidencia insuficiente devuelve UNKNOWN. Los IDs explícitos
de `CHARACTER_IDS` son permanentes; ni posición de Character Select, índice de
Rotation ni texto OCR crudo son claves. El display es metadata.

`CharacterStateStore` posee `runtime/character_state.sqlite3` ignorado por Git,
SQLite schema1, FK, WAL y transacciones atómicas. Separa `characters`, estado
`operational`, snapshots informativos completos y procedencia compacta. Una DB
nueva comienza con Ads/WB UNKNOWN en el epoch actual; no inventa disponibilidad.
La inicialización versionada0→1 conserva archivos incompatibles para diagnóstico.

Session establece scope por identidad usando el snapshot de su primera entrada
compatible; también lo hace la ejecución standalone. UNKNOWN no permite escrituras.
`CharacterStateEvents` consume Video count/efecto Sapphire/agotamiento/no-ad y Raid
Complete existentes. Los recursos informativos nunca autorizan gasto. Los guards
consumptivos frescos permanecen en sus owners.

`ResetClock` calibra un anchor UTC absoluto desde countdown WB observado +30min.
Proyecta resets diarios y ciclos WB de aproximadamente3 días entre observaciones;
una lectura nueva recalibra el anchor, incluso ante desplazamiento estacional.
No existe hora local permanente. Startup y lecturas operativas hacen catch-up;
el runtime posee `ResetScheduler` cancelable y la GUI posee timer Tk. El reset
diario pone Ads2 en los28; el ciclo WB nuevo pone participación NO. WB cierra
en los30min previos a su reset. Historia y snapshots anteriores se conservan.

`WorldBossEligibilityPolicy` configura cuándo ejecutar el único `WorldBossFlow`:
DAILY_QUEST, CURRENT_WB_NOT_PARTICIPATED o GENERAL. Participación YES del ciclo
actual permite NO_WORK; NO/UNKNOWN conduce a inspección física antes de Start.
El reader usa reward anterior y pareja damage/rank acreditada en World Boss main;
no interpreta ausencia OCR como NO. YES es monotónico dentro del ciclo, especialmente
tras Raid Complete, emitido antes de Continue/cleanup. Daily Quest es un fact distinto.

Routine v1 conserva compatibilidad mediante campos opcionales: eligibility por
occurrence y `resource_snapshot_mode` por rutina. Default BEFORE_CHARACTER_ROTATION;
OFF desactiva el collector. Config WB corrupta se recupera como DAILY_QUEST; modo
snapshot corrupto como OFF. Duplicate/Save/reopen preservan ambas configuraciones.

Session/runtime instala el hook `CharacterDataCollector` antes de Character Select,
aprovechando el frame del Quick Menu que Rotation ya abrió. Rotation sólo entrega
un callback genérico; no conoce balances. El collector hace cinco OCR focales;
una lectura insuficiente admite un único reintento sobre el mismo crop con margen
negro, conservando el mismo texto y el gate de confianza ≥0.95. Persiste sólo un
snapshot completo; errores informativos se registran y no fallan la
sesión ni reemplazan balances válidos. Abrir Quick Menu por otro motivo no es trigger.
La GUI muestra28 filas y actualiza automáticamente epochs/ciclos sin visitar personajes.
Sorting es una proyección tipada en memoria: UNKNOWN al final en ambos sentidos,
sin escrituras ni cambios de Rotation; refresh conserva columna/dirección.
Step Settings edita exclusivamente la occurrence seleccionada mediante Apply;
Routine Settings posee Resource snapshot, independiente del step. Application
posee Appearance Light/Dark en `runtime/gui_preferences.json`, separado de SQLite
y routines. Ambos forms crecientes tienen scroll. Los tokens de tema están
centralizados y el switch no inicia lógica de runtime. Detalle en
[GUI_CONFIGURATION](docs/GUI_CONFIGURATION.md).

La acción GUI **Character State → Character Data Sweep — All 28** compone una
`SessionPlan.character_data_only` explícita, sin definitions/flows productivos.
Reutiliza el resolver sobre la entrada de Rotation, scopes permanentes, collector
y Rotation existentes. El modo fuerza captura para esa ejecución y restaura la
policy normal al salir; no modifica configuraciones de rutina. Cada personaje
usa el mismo QM para snapshot y Character Select. UNKNOWN/unreadable conserva
datos previos; identidad repetida no escribe por segunda vez en la misma pasada.
La adquisición incompleta se informa como MANUAL_RESOLUTION; errores de navegación
mantienen el contrato técnico. Stop Safely conserva escrituras verificadas y limpia
scope. El resumen distingue identities/snapshots/Rotations/failures; Ads/WB sólo
cambian por sus eventos y ResetClock. Los fallos de lectura guardan evidencia local
del frame ya disponible, sin captura adicional.

## Rutinas configurables v2

```text
RoutineSpec (id, name, ordered RoutineStep[], relief_policy, change_meteorites=False)
  → ProductiveRuntime.run_routine
  → FlowRegistry existente (resolución por flow_id, una instancia por ocurrencia)
  → run_flows_once (personaje actual) / SessionPlan → SessionRunner → Rotation
  → flows productivos existentes
```

`RoutineStep` conserva flow_id, enabled, overrides mínimos de config y policy booleana continue_on_unavailable. Repeticiones y orden son por posición, sin unicidad ni deduplicación de prerequisites. Presets son specs normales editables; ningún runner reconoce IDs/nombres de presets. Config propia se reconstruye con `MonsterWaveConfig` legacy; una copia de dependencias para construir cada step comparte hardware, cancelación y eventos, sin modificar el config global ni contaminar otra ocurrencia.

`RoutineStore` posee JSON local v2 (routines, selected_id, ordered steps, relief_policy), con lectura/migración v1; `RoutineEditor` posee CRUD y edición posicional independiente de Tk. `Custom` inicial reproduce el orden del registry; `.env` y APIs legacy no migran ni se sobrescriben. Un flow desconocido conserva su entrada y se omite con advertencia; nuevos flows siguen disponibles para añadir. Config inválida se conserva deshabilitada, otros entries válidos se recuperan; archivos/entries ilegibles se respaldan antes de Save. Escritura mediante archivo temporal y replace.

**Reliefs transversales:** la configuración pertenece a la routine-level relief policy,
no a los flows consumidores actuales. Consumers are not part of the policy contract.
`ProductiveRuntime.run_routine` instala un único
`ReliefCoordinator(ReliefPolicy)` compartido por bindings y lo restaura en finally.
El consumidor conserva la evidencia de presión, intención, navegación y retorno; el
coordinator delega una vez a owners existentes. Socket recibe dos permisos independientes;
Equipment composer conserva Combine-first y recibe el allowlist Sell; WB recibe esa misma
policy desde contexto. Craft probe/drain reciben familias permitidas; Treasure consulta
permiso antes de su recovery OPEN_ONCE/drain. No se mueven guards, bounds, cancellation,
effect verification ni accounting a una abstracción nueva.

Migración intersecta permisos de venta incompatibles (incluyendo defaults implícitos v1),
emite warning y archiva todos los configs explícitos. Load no modifica disco; Save v1
hace backup + temporary/replace. Policy corrupta/faltante v2 desactiva suboperaciones
productivas configurables, sin modificar el contrato Combine/low-tier Sell. Platinum es
un slot futuro del objeto Treasure, sin permiso ejecutable/UI hasta contar con GT.

Policy usa resultados existentes: COMPLETED incluye no trabajo; FAILED/CANCELLED cortan. El registry declara únicamente los eventos de indisponibilidad conocidos, y SessionPlan alinea su autorización por posición. MANUAL_RESOLUTION puede continuar sólo sin error/failure, con todos sus eventos declarados, policy habilitada y postcondition verificada. El resultado original se conserva; el reporte muestra incompletitud business. Resoluciones manuales no declaradas y RESOURCE_BOARD_PENDING conservan el corte previo. No navegar en cleanup tras failure o interrupción incierta. Stop Safely puede liberar Meteorites desde READY sólo con contexto limpio conocido y cancelación dura activa; no autoriza cleanup de otros owners.

Basic Gold Farming selecciona la capability Gold Farming Cycle: hasta dos oportunidades de Stages Ads, readiness causal MW dentro de Stages e inversión MW posterior/final. El agotamiento diario explícito omite oportunidades restantes; MW productivo con Sapphires frescos <102 termina sin navegación. Stages e inversiones intermedia/final comparten `sapphire_pressure_passes`; tras cada CLEAR se verifica consenso fresco y se reevalúa pressure, sin aritmética simulada. Rutinas custom conservan su orden literal. Rotation sigue después de la rutina completa por personaje, nunca entre actividades del ciclo.

## Observación y autorización

Hot paths consultan evidencia relevante; discovery/recovery pueden observar ampliamente. Scopes deben conservar contradicciones/blockers relevantes al contrato, no sólo el destino esperado. Clean Lobby significa `RESOLVED screen.lobby` sin overlays; su implementación resolver-complete no prescribe clasificar físicamente todo el catálogo como BASE.

Capture conserva orden de adquisición bajo su lock: un frame PTS en backlog no
sobrescribe pixels adquiridos más recientemente, incluidos los de refresh nativo.
La captura nativa mantiene su timestamp de inicio; una adquisición lenta sigue
siendo stale y no extiende el gate del consumer. Sequence avanza sólo al publicar.

Estado UNKNOWN/AMBIGUOUS aislado nunca autoriza input. Un handoff local puede conservar el source verificado de una acción efectiva y autorizar sólo el siguiente control conocido bajo overlay fresco compatible. Quick Menu y entradas WB emplean ese contrato; no crean bases sintéticas ni estado global en el resolver. Base foreign, contradicción, pérdida observada o recovery invalidan el permiso de retry. Una espera pasiva posterior a input efectivo no equivale a nueva autorización.

`VerifiedTransitionResult.action_source_snapshot` identifica el último source cuyo executor terminó normalmente; `recovery_after_action` impide fabricar un handoff desde cleanup. Geometría siempre del frame fresco. Retry específico, bounded, cancelable y autorizado para **esa** acción; no por sleeps, timeout o baja velocidad de percepción.

Verificar el efecto con señal fiable suficiente. Identidad de contexto se separa de datos económicos; postcondiciones no se convierten en revalidación de cada hecho GT. Landmarks y oclusión siguen GAMEPLAY_GT. Ausencia ambigua de popup no prueba por sí sola éxito o retorno limpio.

H&H se recupera sólo cuando bloquea una observación o un input; su mera presencia no provoca trabajo. `VerifiedTransition` entrega las ROIs de la señal necesaria fallida (también ante abort) o consulta el target real del executor. `PortalObstructionRecovery` sólo prueba si esa geometría intersecta el envelope de GAMEPLAY_GT y el contexto es compatible; nunca por timeout/UNKNOWN aislado. Un único dismiss requiere CONFIRMED fresco y una espera pasiva bounded/cancelable debe confirmar ABSENT; persistencia, evidencia inconclusa o frame stale propagan fallo técnico. El caller revalida su condición original con el snapshot fresco, conservando intención/caller. Inputs directos afectados pueden usar `VerifiedTransition.recover_input` y conservar su espera y cancelación; los no afectados no adquieren probes ni capturas adicionales.

H&H no es observación permanente: primero se decide el conflicto causal sin probe; una condición satisfecha no habilita probe por ROI. En entrada MW, los MODAL conocidos se normalizan antes de evaluar la BASE oculta o intentar H&H. El handoff local de entrada efectiva permite sólo el ACK establecido bajo UNKNOWN y, una vez sin MODAL, recovery causal del landmark MW ausente; véase [contrato MW](docs/MONSTER_WAVE_SKIP.md). CONFIRMED siempre conduce a dismiss; después se reevalúa la entrada desde el principio con evidencia fresca, sin repetir la entrada ni cambiar caller.

## Handoff entre flows

```text
Routine/Session (orden literal y próximo step útil)
  → Navigation handoff (ruta segura mínima)
  → Flow entry requirement
  → gameplay owner
  → result + surface/postconditions verificadas
```

Flow/Activity no conoce el siguiente flow. Session finaliza/publica el resultado antes
de pedir el entry siguiente; failure/cancel corta antes del handoff. MW productivo puede
conservar MW limpio; hub/Lobby de no-work/ramas existentes siguen siendo salidas válidas.
`FlowResult.final_snapshot` transporta evidencia opcional, sin sustituir freshness previa
a input. `PreparedActivity.exit_postconditions` reutiliza Zone/contracts; no otra jerarquía.

Entry se expresa en `ComponentRequirement`/`FlowContract` o PreparedActivity/Zone.
`QuickMenuPolicy` declara el catálogo acreditado (GT en GAMEPLAY_GT); el guard compartido
exige RESOLVED, BASE compatible y sólo status facts compatibles, sin MODAL/actividad activa.
UNKNOWN/AMBIGUOUS nunca autorizan QM ni Back. `QuickMenuHandoff` conserva únicamente el
source efectivo verificado y lineage de overlay fresco; pérdida/recovery invalidan el permiso.

Capability y route selection son distintos. Rutas concretas prefieren el acceso directo
seguro; QM evita normalización si es útil. Battle Mode Select admite QM pero Back gana
hacia Lobby. MW→otro Battle Mode útil usa hub; MW→Pets/Quests/Mailbox/Character Select
usa QM. Quests/Mailbox cierran al origen exacto, comprobado con snapshot nuevo/global,
no a otra BASE capaz. StandardRotation pide capability QM, sin entry Lobby preferida;
su postcondition Lobby después del cambio de personaje permanece. Scopes Lobby de paneles
sólo aplican cuando ése fue el origen. Ningún flow continúa inputs de salida en paralelo.

`routing_no_work` es opt-in del owner: prueba pura/barata/concluyente sin capture, inputs,
gameplay futuro ni gasto. None/UNKNOWN conserva entry normal. No se anticipan Eligibility
ni readiness contextual; una Eligibility instalada conserva precedencia. Cada step mantiene
posición y resultado. WB mantiene readiness propia; una futura ToT también. Sin graph engine.

Entradas Lobby conservadas por sus contratos actuales: Black Market/Send Stamina (accesos
adquiridos, alternativas desconocidas). Stages/Gold Farming aceptan BASE acreditada
QuickMenu-capable: desde Battle Mode Select, Stages delega primero su pressure prerequisite
al MW preparado, que lee Sapphires fresco en el hub; sólo después solicita Lobby para
Stamina/Stages. En otros orígenes solicita Lobby por Navigation antes de balances.
Gold Farming conserva la BASE publicada por su inversión MW final y su `final_snapshot`;
sólo pide Lobby al reanudar una oportunidad de Stages. Su postcondition acepta las
salidas verificadas de MW; Session sigue decidiendo el siguiente entry literal.
WB/MW standalone conservan entry Lobby; PreparedActivity permite hub. Guild/Pets piden su
panel exacto, alcanzable por Navigation. No se infieren rutas de un contrato desconocido.

Observabilidad mínima: `flow.completed.current_surface`, `navigation.handoff` con requested/
useful step, ruta/destino/motivo y `*.base_restored` tras panel close. No policy económica
en Session ni normalización general a Lobby porque exista Rotation.

## Arena — percepción, resultado y operación B1 (2026-10-08)

`bot/arena_semantics.py` posee dificultad, preparación, receipt de ejecución,
provenance y `ArenaBatchResult(difficulty, multiplier, used_tickets, won_tickets,
observed_at, provenance)`. Winrate/lost_tickets se derivan en badges, no combates.
Acquired Karats acredita won_tickets por USER_GT, independiente de Double Points;
Victory Points nunca participa del reader. La previsión `(badges//8)*8` es sólo
candidata para repetición natural x8; interrupciones/blockers pueden reducirla.
`double_points_covered` requiere saldo libre, consumo previsto y reserva conocidos;
no extrapola el refund de buffs1/2 al tercero ni autoriza gasto.

`ArenaVisuals`/`ArenaDetector` en `bot/arena_reader.py` poseen CV focal sin OCR:
selección y Challenge identifican la misma BASE `screen.arena`; configuración,
resultado, insuficiencia y New Ranking son MODAL. Ranking combina título compartido
con label Arena; no invade el owner MW. Buffs/dificultad/x8 son facts de Challenge
limpio. Buff3 ON y x8 OFF reutilizan indicadores adquiridos de controles hermanos,
con pruebas sintéticas explícitas; no acreditan nuevas transiciones físicas.
Upon Defeat OFF está adquirido; otras lecturas devuelven UNKNOWN. Batalla con
versus y banda Auto Repeat publica actividad positiva; B2 USER_GT además acredita
BASE Arena Battle y el overlay individual. Ausencia de banda/Challenge/WIN nunca
acredita final. WIN transitorio de batch no equivale al resultado individual.
`build_arena_perception()` compone el scope focal; default y scopes que preservan
dependencias del resolver incluyen el nuevo detector. No hay ruta Arena en el hub
Survival. B1 compone un owner standalone, descrito debajo.

`ArenaResultReader` devuelve resultado tipado o `None` (UNKNOWN). Exige título,
Badge Used, Acquired Karats, estructura y OK del modal final, con ROIs desde shape.
Padding numérico se compara en color absoluto para rechazar tails corruptos que
OCR podría leer como prefijos plausibles. Ambos enteros vienen de una copia del
mismo snapshot, OCR focal color/gris concordante ≥.95 y una sola línea, sin caché
de campos entre frames: used>0 y0≤won≤used. Zero explícito válido; missing no es0.
Provenance conserva run/source lifetime, secuencia, hash de pixels y confianza.

`ArenaBatchExecution` es el receipt **del owner ArenaFlow**, de un único inicio verde
efectivo dentro del modal, dificultad/x8 conocidos y post-start positivo acreditado.
No se crea leyendo el resultado ni con un tap intentado. El reader rechaza receipt
no verificado, run/source distintos, frames anteriores al inicio/secuencia,
stale/futuros; revalida edad después de OCR (default2s). El owner debe
invalidarlo por cancelación, otro batch, discontinuidad de source o navegación
ajena. La identidad causal no se puede inferir de los pixels del modal; Phase A
valida este contrato sin ejecutar un inicio real.

`wait_terminal` reutiliza `ControlledWait`, deadline configurable obligatorio,
sondeo focal3s inicial, secuencia/timestamp crecientes y cancelación. No usa OCR
durante polling; devuelve snapshot terminal positivo para lectura fresca separada.
El callback de observación puede usar refresh nativo existente ante ambigüedad;
UNKNOWN requiere otra observación, nunca rescate por plausibilidad. Cancelar el
wait no cancela físicamente el juego. Fase A validó sólo esta interfaz pasiva.

`ArenaFlow` (`bot/arena_flow.py`) posee una operación acotada, navegación,
preparación, lineage y retorno. `ProductiveRuntime.build_arena_flow(difficulty)`
compone observer/source/actions/OCR compartidos y los reliefs existentes; no está
acoplado a Rotation, Meteorites, budget de Stamina ni generadores de badges. Entrada
contractual Lobby limpio: Battle→Select Mode con tarjeta Arena→selección→Challenge.
New Ranking acreditado al entrar se cierra con un único OK antes de la dificultad.
Challenge solo no acredita idle, pues es transitorio dentro del batch. Salida
standalone legacy conserva `screen.arena` sin overlays. B2 registra la ocurrencia
de rutina con contrato Lobby→Lobby y ruta Back adquirida; el caller posee la
navegación desde ese Lobby al próximo contexto.

`ArenaFlowReader`/`ArenaFlowVisuals` poseen navegación/economía focal B1; reutilizan
result reader de A. B1 permite edad máxima4s por coste nativo medido conservando
timestamps; A mantiene default2s. Extienden autoridades con brillo absoluto y
exclusión de modales conocidos para no aceptar Challenge detrás de insuficiencia.
Economía requiere captura nativa fresca en
el sequence space del source, enteros OCR color/gris del mismo frame y x8/dificultad
acreditados. Prewarm precede un nuevo snapshot. Buffs1/2 ON se conservan; OFF se
seleccionan y se verifica reserva8. Requieren stock para toda la previsión ordinaria:
faltante detiene preparación salvo la compra acotada de buff1 B2 para una entrada8.
Buff3 ON
sin reserva conocida exige cobertura por saldo libre; insuficiente/UNKNOWN→OFF
verificado. Activación OFF sólo con cobertura; reserva3 se acredita por delta8
observado, sin inferir refund. No intención de compra Karats ni badges. Un techo
opcional de autorización rechaza batches naturales mayores; nunca los fragmenta.

`ArenaAction`/`ArenaControl` poseen targets normalizados adquiridos independientes
de Survival. `ActionExecutor` aplica doble tap x8 únicamente desde OFF acreditado.
Configuración debe acreditar Upon Defeat OFF; ON sólo puede corregirse con evidencia
positiva (detector ON aún no adquirido). Start usa un input interno verde y exige
Loading/batalla posteriores antes de emitir receipt. Un inicio incierto no se repite.
Socket blocker + contador nativo sin consumo acreditan no-inicio: entrada verificada
a Socket→ReliefCoordinator→relief existente→retorno limpio fresco→revalidación total.
Máximo un relief y un nuevo intento sólo tras ese no-inicio; retorno desconocido
detiene el owner. Equipment Full sigue UNKNOWN. No nuevos reliefs.

Wait productivo `ControlledWait`: sondeo focal3s configurable, bound1800s ajustable
(safety heuristic, no duración contractual), cero OCR durante wait, secuencias/edad
reales y cancelación. Challenge/WIN transitorio/Loading no terminan el wait de batch. Configuración
propia transitoria tras Loading se observa sin input bajo el bound UNKNOWN persistente.
Modales conocidos
distintos o superficie desconocida persistente conservan evidencia y detienen el
observer, sin cerrar. Terminal positivo→nativo fresco→reader de A; máximo dos lecturas
frescas, sin otro Start. Resultado con used superior a badges acreditados al inicio
se reporta ambiguo. OK único, Insufficient→No y New Ranking→OK sólo por autoridad
positiva; retorno BASE fresco. `ArenaFlowResult` conserva resultado, fase, receipt,
evidencia y `physical_operation_may_be_active`; detener observer invalida receipt
de lectura y no declara cancelación física. La misma instancia no reinicia una
operación física incierta/activa. Métricas separan capturas, CV, OCR, intervalos/edad,
elapsed y trabajo del observer; aparición terminal sólo tiene bracket observado,
no una latencia física inventada. Sources/ADB/process cleanup sigue en runtime.
`observe_started_batch(execution, started_badges)` continúa sólo observación/cierre
de un batch ya acreditado: nunca preparación/Start. El caller acredita handoff
explícito con inicio histórico positivo, ownership físico sin inputs intermedios
y un nuevo segmento source/sequence; conserva run/configuración/started_at.
Actividad/Loading/terminal frescos son obligatorios. El receipt archivado sigue
invalidado; no se resucita ni se deduce un inicio desde el resultado. Safety bound
mantiene el tiempo del inicio original. Insufficient tardío durante acreditación
global del retorno se adopta fresco y se cierra con No, sin repetir OK del resultado.

Modal de umbral de puntos: deuda explícita de adquisición, literal/umbral/cierre
UNKNOWN; no detector inventado. ArenaFlow conserva evidencia/no taps ciegos
ante ese modal no reconocido. Cancelación física sigue abierta. Farming Cycle,
controller adaptativo, Manual Stages y REPEAT_CURRENT
quedan fuera de A/B1. Smoke físico B1 cerrado: único batch EASY x8,48used/48won,
2Badges finales y BASE Arena limpio. Hubo interrupciones del observer y handoff;
no acredita ejecución continua ni performance de wait largo. [B1](docs/ARENA_B1_20261008.md) y
[adquisición/A](docs/ARENA_HIL_ACQUISITION_20261008.md) poseen evidencia y límites.

### Arena B2 — modos y ocurrencias

`ArenaMode`/`ArenaConfig`: SINGLE_BATTLE o AUTO_REPEAT, dificultad fija
EASY/NORMAL/HARD, exclusivamente x8. Default nuevo SINGLE_BATTLE/EASY; Arena es
seleccionable en FlowRegistry pero OFF en defaults de rutinas. Config JSON por
ocurrencia `arena: {mode, difficulty}`, validado sin opciones económicas/adaptive;
draft→Apply→Save Routine existente. Esquema v2 admite la sección sin bump:
faltante usa default conservador, inválido conserva datos y deshabilita el paso.
`_step_runtime` resuelve cada ocurrencia y evita heredar Arena global accidentalmente.

Preparación y owners B1 compartidos; SINGLE_BATTLE despacha únicamente
`SINGLE_START`, sin configuración Auto Repeat. Loading/actividad positivos mintan
`ArenaSingleExecution`; no retries después de Start incierto. Reader específico
exige WIN+estadísticas+Reward+prompt acreditado, freshness y receipt de esa entrada.
`ArenaSingleResult` VICTORY acredita consumo8 y deltaKarats8 mediante balances
nativos antes/después del cierre, con provenance separada. No `won_tickets`;
derrota no adquirida detiene observer sin input. AUTO_REPEAT conserva su reader,
Upon DefeatOFF, cierre y `used_tickets/won_tickets` de B1.

Gold buff1 sólo si stockOFF0..7, consumo previsto8, precio3000 positivo y balance
fresco suficiente: input único, reserva exacta y debitGold esperado, Karats/badges
intactos antes de Start. Buff2 agotado y reposición Gold de batches largos siguen
deteniendo preparación. Double Points nunca compra Karats. Déficit rojo sólo cuenta
con recibo local de la compra; stock ilegible nunca se convierte en cero.

Single cierra a selección; batch a Challenge. Retorno externo exige BASE limpia y
Backs positivos hasta `screen.arena_select_mode` y Lobby fresco acreditado por
resolver+CV. New Ranking→OK sólo con evidencia positiva. SUCCESS externo no puede
emitirse desde Challenge/selección. Session existente continúa desde Lobby conocido;
FAILED/CANCELLED/incertidumbre detienen el avance. No políticas diarias ni cambios
de Rotation/Shared Meteorites. Handoff explícito `observe_started_single` conserva
único Start/balances y requiere revalidar actividad/terminal en nuevo source; nunca
prepara ni inicia. [B2](docs/ARENA_B2_20261008.md) detalla evidencia y límites.

## Meteorites — primitivas Fase A (2026-10-08)

`MeteoritesDetector` incorpora el landmark estructural del Bag principal,
detail OVERLAY y Loading al catálogo/default perception y a los scopes que
preservan todos los contextos. Los cuatro tabs hermanos son negativos del
landmark principal; siguen siendo vistas físicas de la misma BASE por USER_GT.
`MeteoritesReader` lee tab, set, página, once slots, sprite Flare, marco de tier,
título/nivel y acción lateral de forma focal. UNKNOWN no autoriza input.

`ProductiveRuntime.build_meteorites_runtime()` compone `MeteoritesRuntime` con
el source, OCR, ActionExecutor, cancelación y events existentes. No está conectado
directamente a Routine Settings ni a rotación; B2 lo compone desde el scope del personaje. `enter()` reutiliza
VerifiedTransition y el handoff Quick Menu existente. Sólo el tile del layout
Lobby está adquirido; un origen shifted no habilita una coordenada inferida.

`equip(index)` selecciona una celda one-based de Bag; `unequip_slot(slot)`
selecciona el slot 0 (Flare) o 1..10 (orden USER_GT). `unequip_bag(index, slot)`
conserva la ruta adquirida y exige E del set activo y un slot único compatible.
Candidate, set/página previos, sprite, overlay fresco, acción e input lineage
vinculan selección e input. Continuidad fuerte conserva el panel sin OCR extra;
pérdida de continuidad exige lectura semántica fresca. No se toca el lock inferior.
La revalidación espera pasivamente un nuevo tick si el stream repite su último
frame; conserva plazos, cota de samples, cancelación y rechazo de frames stale.

Cada acción lateral se despacha una vez y acredita EMPTY→OCCUPIED u
OCCUPIED→EMPTY del slot esperado, preservando los otros diez. La página/readiness
se verifica después del efecto, separadamente de Loading, CP o cierre de overlay.
Barriers de timestamp y sequence, edad máxima, plazos, cota de samples y cancelación
limitan toda espera. Los budgets son configurables, no latencias físicas estimadas.

Recovery local: positivo, `effect_not_ready`, `in_progress`, `no_effect` y ambiguo
son resultados distintos. Sólo un overlay original retenido durante el budget,
revalidado y cerrado mediante su ruta segura, seguido de Bag/item/set/slots
explícitamente iguales y estables acredita no-efecto. `retry_no_effect=True`
permite una nueva selección completa y un único retry. Timeout, Loading, input
incierto, frame stale o overlay perdido no habilitan repetición. No hay workaround
seleccionar otro/regresar, cleanup completo ni algoritmo de ancla.

Métricas agregadas por operación: selección→overlay, tap→efecto,
efecto→readiness, wall incluyendo navegación inicial, capture/perception,
captures, OCR, consultas CV y matches de templates, retries y freshness rejects.
El pager/readiness reutiliza el frame del efecto si todavía es fresco; de otro
modo espera uno nuevo. Un efecto tardío durante la reconciliación cancela el retry.
Efecto/readiness acreditados en el mismo sample no miden 0 ms físico. Evidencia bounded
retiene before/overlay/action/effect/final en memoria; el smoke la escribe
fuera del tramo cronometrado y preserva la primera divergencia.

## Meteorites — procedimiento posicional B1 (2026-10-08)

`SharedMeteoritesPreparation` (`bot/shared_meteorites.py`) es una support operation
compuesta sobre las primitivas Fase A. B2 la reutiliza desde Session; el procedimiento
no posee policy de personajes ni navegación de Arena/ToT/Elite. El caller asume
las cinco precondiciones USER_GT; Set 2 es el único destino temporal.

Setup: entry compatible → Set 2 activo/vacío → sprite Flare en 1–12 con overlay
Ethereal+ positivo → recorrer suffix Flare hasta primer normal → calcular una vez
`anchor = first_normal + 9`, índices absolutos one-based, 16 por página → Flare
centro → diez normales desde el mismo anchor, slots 1..10. No OCR de todos los
nombres en Bag. `group_cell` e `inspect` reutilizan readers, navegación y binding
de selección existentes; `expected_slot`/`require_shared` rechazan antes del input
lateral un destino incorrecto o propiedades insuficientes.

Cleanup sólo desde setup completo acreditado: slots 10..1 → Flare central →
Set 1 activo y ready. Las once verificaciones individuales acreditan Set 2 vacío;
no segundo barrido. `required_set=2` impide Unequip desde otro set. `MeteoriteResult.effect`
conserva el fact físico positivo independientemente de la readiness posterior.

El progreso conserva cada efecto acreditado y cualquier acción pendiente incierta.
Recovery local Fase A autoriza como máximo un retry por no-efecto estable fresco;
B1 reconcilia resultados ambiguos únicamente observando slots Set 2 compatibles
con el progreso, sin reselección ni repetición lateral. Loading conserva transición.
Si no reconcilia/readiness falla/cancela, se detiene con estado conocido y progreso;
no cleanup ciego, replay de setup ni restauración anticipada de Set 1.

`tools.smoke_meteorites_b1` registra individualmente los 22 efectos, frames/hash,
posiciones y métricas; requiere preparación humana por chat/steer y detiene inputs
al primer desvío. El source y sus recursos se cierran por ProductiveRuntime. Wall
setup/cleanup incluye la escritura de evidencia, informada aparte; wall de cada
primitiva la excluye. Capture counts son consultas al source, no frames distintos.
Tap→efecto es latencia observada (juego + captura/percepción), no tiempo puro del
motor; capture/perception y navegación de Bag tienen mediciones separadas.

## Meteorites — integración B2 de Routine/Session (2026-10-08)

`RoutineSpec.change_meteorites` es booleano opcional del esquema v2; v1/v2 sin
campo carga OFF. Valores corruptos cargan OFF con warning/backup conservador.
Routine Settings muestra Change Meteorites y el aviso de las cinco precondiciones.
Apply modifica draft; Save Routine persiste; reopen y Duplicate conservan el valor.
No hay configuración en Step Settings ni Reliefs.

`ProductiveRuntime.run_routine` instala/restaura la bandera en finally. Tanto
personaje actual sin Rotation (`run_flows_once`) como roster (`run_session`) usan
`SessionRunner`. Al comienzo del character scope, Session acredita Lobby e identidad
estable antes del primer paso; `MeteoritesCharacterScope.begin(context)` delega setup
B1. Al terminar todos los pasos normales, `finish()` delega cleanup B1 antes de Rotation
o de completion sin Rotation. Un COMPLETED/no-work de un flow no cierra este scope.
Meteorites sale por su X acreditada a Lobby y el caller sigue hacia el entry requerido;
no se habilita geometría de Quick Menu desde Meteorites por esta configuración.

La policy fija omite setup/cleanup para `berserker`, `demon_blade`, `kaiserin`;
`burst_breaker` participa. Sólo `CharacterContext.character_id` acreditado mediante
el owner de identidad puede autorizar setup. UNKNOWN corta sin Equip ni pasos.
Los estados transitorios son NOT_REQUESTED, SETUP_IN_PROGRESS, READY,
CLEANUP_IN_PROGRESS, RELEASED, INTERRUPTED; guards impiden callbacks duplicados.
Cada ejecución/personaje obtiene scope/progreso nuevos; no persiste ni reusa READY.
La frontera es el personaje, no la ocurrencia de flow ni una futura iteración repeat.

Finalización normal exige RELEASED. Setup fallido bloquea pasos; cleanup fallido
bloquea Rotation. FAILED/interrupción incierta registra progreso sin limpieza ciega.
Stop Safely soft permite únicamente cleanup completo acreditado desde READY después
de un gate fresco de BASE limpia conocida; UNKNOWN/overlay no navega. Un segundo
Stop o señal dura conserva cancelación en cada input de los owners B1. El resultado
de Session sigue CANCELLED aunque esa liberación alcance RELEASED.

SessionResult/SessionReport incluyen DISABLED, SKIPPED_EXCEPTION, READY, RELEASED,
INTERRUPTED, stable ID, outcomes, efectos, inputs/retries, duración y aviso explícito
de desequipar manualmente antes de reanudar si quedó incierto. Los eventos
`session.meteorites` conservan el progreso físico; no hay inventario/historia nuevos.
`coordinator_seconds` mide transiciones/reporting fuera de callbacks setup/cleanup;
`navigation_seconds` separa entrada de cleanup; B1 conserva métricas por operación.
`tools.smoke_meteorites_b2` usa run_routine real con Send Stamina y sin Rotation.

## Navegación y economía

Rutas concretas respetan caller/Back de GAMEPLAY_GT. El caller posee su retorno y la intención que reanuda; no hay navigation graph general. Quick Menu usa origen verificado; Lobby no es un hub obligatorio. Relieves vuelven al caller antes de otro cambio de BASE.

- El planner de recursos es puro; el board describe, cada capacidad decide/ejecuta dentro de su operación con facts frescos. El executor de ruta consume un plan, no replantea por su cuenta.
- Economic owners verifican identidad, cantidad, moneda, límites y efecto. No imputar saldos desde acciones previas. Karats no se gastan mediante fallback implícito; USER_GT Equipment autoriza explícitamente la siguiente fila +4 tras Combine y scan Sell sin candidato accesible.
- Equipment conserva request causal y Combine primero. Sell productivo aplica policy USER_GT y scan desde tail accesible fresco; cada Bulk confirma una vez y prueba Item Count decreciente. Sin candidato, expansión secuencial +4 con coste y efecto verificados. CV de bloques sólo descubre candidatos; panel/policy/popup siguen autorizando cada Bulk. Tras Bulk compatible se invalidan pixels/crops/templates/geometría y se transforman rangos lógicos protegidos por delta fresco; navegar a la región nueva sin reinspección innecesaria. Expansión, contexto/resort o delta contradictorio invalidan también ese modelo y restauran scan secuencial. Nunca retry destructivo inconcluso. Su existencia standalone no prueba wiring de un caller.
- Equipment selected detail separa authorities: tier desde tinta del título con soporte/margen suficientes; familia roja requiere además marcador visual Ethereal/Ethereal+ inequívoco. Subtype conserva OCR focal del vocabulario finito; Enhance usa su marcador visual genérico. UNKNOWN no produce un item autorizable. El nombre libre no se transcribe ni participa del consenso/continuidad de facts cromáticos; el panel conserva continuidad visual, candidate, freshness e input lineage. Popup binding usa el panel verificado → tap Sell → consenso modal fresco posterior, sin input intermedio; no igualdad de nombres. Scope Bulk exacto, ReliefPolicy, E+ protegido, una confirmación y efecto Item Count permanecen en sus owners existentes.
- WB productivo tiene wiring Inventory/Sell: un nuevo Full tras Combine autoriza una visita bounded a QM Inventory; el owner existente verifica venta/capacidad y WB acredita su BASE restaurada antes de Start. Full posterior a esa visita termina business-incomplete sin repetir relief. Tras Inventory, sólo un Lobby fresco observado al salir WB autoriza restablecer el hub.
- Recovery vuelve a estado conocido; la sesión decide cómo continuar con el resultado. Los límites concretos de MW/Craft/Keys están en RESOURCE_ROUTING.

Configuración import-safe y explícita; paths/seriales locales fuera de código portable. Cleanup de source/proceso/socket/forward pertenece a su owner. No incorporar lifecycle frameworks, planners generales o abstracciones preventivas sin necesidad real conforme a AGENTS.

## Navegación dirigida de listas ordenadas

`directed_list_scroll.navigate_to_target` separa catálogo/target/posición lógica de
geometría física del gesto. Caller aporta orden adquirido, anchors identificados y
centros, pitch/columns, lane/bounds calibrados, revision, guard y observación fresca.
Un perfil coarse opcional permite un único gesto sin anchor previo, exclusivamente con
lista/contexto positivo, limpio y fresco. No estima el target ni inventa índices del
prefix. Su respuesta no calibra el modelo dirigido; la lectura posterior fija el anchor.
La primitive calcula offset/filas restantes y apunta al centro de una safe visibility
window, independiente de los endpoints del dedo. El perfil puede aportar envelopes
empíricos min/median/max por travel/duración y dirección; interpolación bounded prioriza
margen útil y luego error al centro, sin extrapolar el travel adquirido. Esa cobertura
es una heurística de ranking, no una garantía probabilística. Cada emit inyectado exige
feedback fresco; el mismo loop recalcula ante undershoot/overshoot sin fases numeradas.
Gain/escala de respuesta se ajustan dentro de esa invocación; no hay cache/persistencia.
Los IDs pueden ser índices enteros; UNKNOWN nunca crea una posición. Consenso fuerte
del target, budget de gestos/inversiones, progreso mínimo y mismatch/stuck acotan el
driver. Revision distinta invalida viewport/modelo; cancel/guard/stale detienen inputs.
Callers aportan calibración de duración/settling, freshness previa a input, ActionExecutor
y fallback. Budgets incluyen coarse y directed; métricas cuentan sólo gestos despachados.
La primitive no selecciona ni autoriza operaciones económicas.

Consumidor actual: `ProductiveMaterialsAdapter.locate` de Trading Center. Usa el suffix
acreditado y títulos CV; prefix temporal sin anchor usa el coarse máximo robusto adquirido.
Cada lectura posterior se reutiliza, incluidos los facts del seed ya analizados.
Fallback conserva el presupuesto total y readquiere contexto antes del scan anterior.
READY conserva identidad fuerte y geometría completa desde título/pitch acreditados,
con consenso fresco; una fase errónea de separadores no mueve la identidad. C3/C4 y Trade siguen bajo
sus owners. Telemetry distingue adquisición, predicted/actual rows, correcciones,
inversiones, observaciones aceptadas, elapsed y fallback; métricas reales de captura
pertenecen al source/RuntimeObserver. No verbose frame logging nuevo en producción.

Futuro previsto: ToT al implementar su flow y adquirir explícitamente su GT de lista.
Cada nuevo consumidor exige orden/dirección/target/anchor/viewport/pitch/bounds propios;
el GT de Trading no se generaliza a otra UI. No hay segundo consumidor actual requerido.

## AdsManager transversal

AdsManager no pertenece a Stages ni selecciona contenido publicitario. `AndroidAdsObserver` reúne pixels frescos y activity/window; el adapter despacha acciones Android/semánticas y el manager mantiene el lifecycle bounded. Stages es un caller: navegación/configuración/Mao permanecen concretos, y su success exige Results y Sapphire after > before. No se crea un framework general de stages.

- Activity/focus deben concordar. Package/activity son contexto, no prueba de reward ni de fase closable. Usar `dumpsys window` completo donde `windows` no aporta foco. Cada input fuerza screencap nativa fresca; no reinterpretar pixels SDK stale sobre main como permiso para otro Back. UI hierarchy actual sin affordances útiles es diagnóstico, no dependencia de cleanup.
- Chrome fijo SDK reward-ready permite cierre normal; CV de la barra SDK sólo prueba progreso, nunca autoriza un input. Movimiento ≥.01/reset conserva observación, con grace 15 s y límite absoluto 180 s multipart. No reconocimiento de marca ni OCR del contenido publicitario. Bajo Google AdActivity resumed/focus concordantes, se lee exclusivamente el campo fijo del SDK: `Reward granted` exacto con confianza≥.85 más X circular adquirida acredita cierre; `Next ad` exacto identifica un paso intermedio y suprime cierre. No se adquiere ni despacha un botón Next por inferencia.
- No hay edad mínima del anuncio para evaluar o actuar sobre terminal authority acreditada:5/8/12 s son válidos cuando la evidencia fuerte lo autoriza. Deadline/stall son fallback, no un gate anterior al cierre normal. La grace4 s comienza sólo después del retorno al juego sin results; no retrasa un terminal SDK ni un resultado ya resuelto. Las primitivas X/sonido adquiridas se comparan con máscaras que excluyen el fondo variable; umbral local .94 y contorno circular siguen obligatorios. X blanca requiere Reward granted explícito; X negra sola requiere además el sonido SDK adquirido. Ninguna X genérica ni fin de parte acredita completion. Tras Android/OCR, evidencia terminal de más de2 s no autoriza input y se espera el siguiente frame fresco.
- ~60 s limita inactividad desde el último movimiento/reset SDK verificado (o desde launch si nunca lo hubo), con límite absoluto 180 s. Un límite temporal termina sin input si falta autoridad de recompensa: ownership SDK/embedded, desaparición de barra o fin de parte no permiten Back. Sólo chrome terminal fresco acreditado autoriza cierre SDK, con hasta dos Back en total y presupuesto compartido de close steps; una señal terminal en el límite absoluto también puede actuar inmediatamente. La X circular adquirida exige su posición/estructura, chrome de sonido y resumed/focus Google AdActivity concordantes. Main + superficie conocida detiene inputs; results tienen grace bounded4 s. Cada visita externa admite hasta dos retornos sujetos al presupuesto total, reiniciados sólo por retorno fresco al SDK. No CTA/install/permisos/compras.
- `AdsOutcome.RETURNED` señala retorno con results; **AD_COMPLETED** funcional sólo después de que el caller pruebe reward. `AD_ABORTED_RECOVERED` no es success ni supone reward/debit; el caller restaura estado y puede reintentar bounded. `UNAVAILABLE` por intento puede terminar en ADS_UNAVAILABLE/MANUAL_ENTRY_REQUIRED según policy del caller. `EXHAUSTED` corresponde a agotamiento explícito. `AD_RECOVERY_FAILED` sólo si no puede verificarse recuperación segura.
- Freshness y resultado inconcluso conservan los guards consumptivos. Policy concreta No Ads/same-character reset y prerequisites de Stages pertenecen a RESOURCE_ROUTING; límites físicos adquiridos a GAMEPLAY_GT.


## Resource owners y optimizaciones causales

Board MW conserva dos frames frescos acordes, spacing ≤1 s y edad final ≤2 s.
El reader memoriza únicamente OCR puro de un crop idéntico byte por byte, con una
entrada por fila; cada muestra conserva su propia secuencia/timestamp y reevalúa
contexto/red pressure. Pixels cambiados vuelven a OCR. No se cachean balances ni
autoridad de consumo; el input exige el guard fresco del owner existente.

La policy Sapphire es una primitive compartida `sapphire_pressure_passes`, no un planner
económico en RoutineRunner. MW productivo verifica saldo fresco tras cada CLEAR y recalcula
el mínimo para <102. `PreparedActivity.entry_readiness` permite no-work antes de zona sólo
sin Eligibility; World Boss conserva su precheck/Eligibility pendiente, sin shortcut Daily.
Disponibilidad explícita Stages vive en scope session-character; same-character conserva,
Rotation separa. UNAVAILABLE/UNKNOWN/abort no se convierten en daily exhausted.

Craft usa una visita Weapons→Armor→Accessories con el owner consumptivo existente; cada
selector/MAX/confirm/efecto exige evidencia propia. Lectura inconclusa no autoriza consumo;
failure real corta. Equipment conserva count/capacity posterior a Combine porque su resultado
no acredita capacidad fresca suficiente para decidir Sell/expansión/retry. Sin cache global.
Sell puede reutilizar el mismo panel SELLABLE fuerte; CV descubre, no autoriza consumo.
Socket conserva TapThroughAnimation con positive-only taps, scope local seguro y BASE estable
reclasificada globalmente. Flashes/UNKNOWN esperan; no segundo consumo por timeout.
Los límites concretos/visitas/retornos pertenecen a RESOURCE_ROUTING, sin duplicar GT físico.
