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

## Rutinas configurables v1

```text
RoutineSpec (id, name, ordered RoutineStep[])
  → ProductiveRuntime.run_routine
  → FlowRegistry existente (resolución por flow_id, una instancia por ocurrencia)
  → run_flows_once (personaje actual) / SessionPlan → SessionRunner → Rotation
  → flows productivos existentes
```

`RoutineStep` conserva flow_id, enabled, overrides mínimos de config y policy booleana continue_on_unavailable. Repeticiones y orden son por posición, sin unicidad ni deduplicación de prerequisites. Presets son specs normales editables; ningún runner reconoce IDs/nombres de presets. Config se reconstruye con `MonsterWaveConfig`/`EquipmentSellPolicy`; una copia de dependencias para construir cada step comparte hardware, cancelación y eventos, sin modificar el config global ni contaminar otra ocurrencia.

`RoutineStore` posee JSON local v1 (routines, selected_id, ordered steps); `RoutineEditor` posee CRUD y edición posicional independiente de Tk. `Custom` inicial reproduce el orden del registry; `.env` y APIs legacy no migran ni se sobrescriben. Un flow desconocido conserva su entrada y se omite con advertencia; nuevos flows siguen disponibles para añadir. Config inválida se conserva deshabilitada, otros entries válidos se recuperan; archivos/entries ilegibles se respaldan antes de Save. Escritura mediante archivo temporal y replace.

Policy usa resultados existentes: COMPLETED incluye no trabajo; FAILED/CANCELLED cortan. El registry declara únicamente los eventos de indisponibilidad conocidos, y SessionPlan alinea su autorización por posición. MANUAL_RESOLUTION puede continuar sólo sin error/failure, con todos sus eventos declarados, policy habilitada y postcondition verificada. El resultado original se conserva; el reporte muestra incompletitud business. Resoluciones manuales no declaradas y RESOURCE_BOARD_PENDING conservan el corte previo. No navegar en cleanup tras failure/cancelación.

Basic Gold Farming selecciona la capability Gold Farming Cycle: hasta dos oportunidades de Stages Ads, readiness causal MW dentro de Stages e inversión MW posterior/final. El agotamiento diario explícito omite oportunidades restantes; MW productivo con Sapphires frescos <102 termina sin navegación. Stages e inversiones intermedia/final comparten `sapphire_pressure_passes`; tras cada CLEAR se verifica consenso fresco y se reevalúa pressure, sin aritmética simulada. Rutinas custom conservan su orden literal. Rotation sigue después de la rutina completa por personaje, nunca entre actividades del ciclo.

## Observación y autorización

Hot paths consultan evidencia relevante; discovery/recovery pueden observar ampliamente. Scopes deben conservar contradicciones/blockers relevantes al contrato, no sólo el destino esperado. Clean Lobby significa `RESOLVED screen.lobby` sin overlays; su implementación resolver-complete no prescribe clasificar físicamente todo el catálogo como BASE.

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
adquiridos, alternativas desconocidas), Stages/Gold Farming (entry efectiva actual).
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
- Chrome fijo SDK reward-ready permite cierre normal; CV de la barra SDK sólo prueba progreso, nunca autoriza un input. Movimiento ≥.01/reset conserva observación, con grace 15 s y límite absoluto 180 s multipart. No OCR ni reconocimiento de marca/contenido del anuncio.
- ~60 s es fallback sólo para estado desconocido/estancado sin progreso conocido. Back 1 → pixels/Android frescos → Back 2 únicamente si sigue ownership positivo ad/external. Main + superficie conocida detiene inputs inmediatamente; results tienen grace bounded 4 s. Nunca Back→Back a ciegas ni segundo Back dentro del juego. External package se recupera con Back bounded, sin CTA/install/permisos/compras.
- `AdsOutcome.RETURNED` señala retorno con results; **AD_COMPLETED** funcional sólo después de que el caller pruebe reward. `AD_ABORTED_RECOVERED` no es success ni supone reward/debit; el caller restaura estado y puede reintentar bounded. `UNAVAILABLE` por intento puede terminar en ADS_UNAVAILABLE/MANUAL_ENTRY_REQUIRED según policy del caller. `EXHAUSTED` corresponde a agotamiento explícito. `AD_RECOVERY_FAILED` sólo si no puede verificarse recuperación segura.
- Freshness y resultado inconcluso conservan los guards consumptivos. Policy concreta No Ads/same-character reset y prerequisites de Stages pertenecen a RESOURCE_ROUTING; límites físicos adquiridos a GAMEPLAY_GT.


## Resource owners y optimizaciones causales

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
