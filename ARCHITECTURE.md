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
RoutineSpec (id, name, ordered RoutineStep[], relief_policy)
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

Policy usa resultados existentes: COMPLETED incluye no trabajo; FAILED/CANCELLED cortan. El registry declara únicamente los eventos de indisponibilidad conocidos, y SessionPlan alinea su autorización por posición. MANUAL_RESOLUTION puede continuar sólo sin error/failure, con todos sus eventos declarados, policy habilitada y postcondition verificada. El resultado original se conserva; el reporte muestra incompletitud business. Resoluciones manuales no declaradas y RESOURCE_BOARD_PENDING conservan el corte previo. No navegar en cleanup tras failure/cancelación.

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
