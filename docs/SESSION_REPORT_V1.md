# SessionReport v1

Consolidado en `7865c55` sobre `main@16f2d418fd5bd081a87a8177a93a1ca9cd7962c3`. Las menciones posteriores a revisión/ausencia de commit describen el cierre histórico de esta fase. Proyección humana transitoria de una sesión terminada. No agrega log, persistencia machine, eventos, dependencias ni policy de gameplay. El consumo GUI actual y la localización explícita de evidencia están documentados en [`GUI_FUNCTIONAL_MINIMUM.md`](GUI_FUNCTIONAL_MINIMUM.md).

## Diseño y fuentes

`bot/session_report.py` contiene dataclasses frozen, `build_session_report` y `render_session_report`. No importa Tk, consulta relojes, captura, ejecuta input ni hace IO. Recibe resultados; no mantiene un collector de eventos ni reabre JSONL. El JSONL/event stream sigue siendo la fuente machine persistente canónica; el report no sirve como entrada de decisiones del runtime.

La fuente principal es `SessionResult`, sus `SessionCharacterResult` y los `FlowResult.events` canónicos conservados en memoria. Usa además los flags explícitos `daily_pending`, `claims_leftover` y `no_op` cuando están disponibles en resultados parciales. No interpreta `detail`, `error`, `FailureCause.message` ni campos diagnósticos para decidir outcomes. No agrega ni vuelve a publicar business events.

`SessionResult` añade metadata opcional keyword-only:

| Campo | Contrato |
| --- | --- |
| `expected_character_count` | Total del plan ejecutado; `None` en resultados legacy sin metadata. |
| `flow_names` | IDs en orden del plan, incluidas repeticiones; tuple vacía en legacy. Los resultados parciales corresponden a su prefijo. |
| `duration` | Segundos de `SessionRunner.run()` con `perf_counter`, incluye sus publicaciones terminales; excluye setup/cleanup exterior y construcción/render del report. `None` cuando no se midió. Excluido de igualdad. |
| `failure_flow_position` | Posición **zero-based** en el plan del flow terminal, incluso si falló su precondición antes de `run()`. `None` para Rotation y legacy. Distingue flows repetidos sin parsear causas. |

El runner agrega la metadata al devolver el resultado, usando un reloj de medición separado de los deadlines de gameplay. No se agregan eventos ni campos al JSONL. Los frontends pueden proporcionar total y nombres sólo como fallback para metadata legacy ausente; nunca sustituyen metadata existente. Los nombres humanos de flows pueden suministrarse desde `FlowDefinition.display_name`; los IDs permanecen estables.

## Modelo reusable

| Objeto | Contenido |
| --- | --- |
| `SessionReport` | `status`, `execution_status` original, duración, procesados/esperados, flows completados, advances completados, `counts`, personajes, causa terminal, `data_gaps`, run/session IDs para correlación diagnóstica. |
| `CharacterReport` | Índice, etiqueta `Character N`, categoría, flows, advance completado, causa y componente terminal cuando se conoce. |
| `FlowReport` | ID opcional, etiqueta, categoría, contrato completado, motivos, causa técnica opcional y no-op. |
| `ReportReason` | Identificador del evento de negocio existente y su interpretación humana; para flags legacy sin evento, nombre del flag y explicación genérica. No es una taxonomía de failures. |
| `ReportCounts` | Conteos exclusivos de personajes complete, business incomplete, technical failure, cancelled y unassessed. |

`ReportStatus` tiene exactamente `COMPLETE`, `BUSINESS_INCOMPLETE`, `TECHNICAL_FAILURE`, `CANCELLED`. `status=None` es falta de información para evaluar un resultado legacy, no otra clase de failure ni una Daily incompleta. `data_gaps` expone metadata ausente y resultados no evaluables. Los objetos y sus colecciones son inmutables; no se guardan snapshots ni los mappings de metadata de eventos.

Se ordenan personajes por índice de sesión y flows por orden de ejecución del plan. No se ordenan por timestamp ni alfabéticamente. Se conserva una ocurrencia por ejecución, incluso si se repite su ID. Sin nombres del plan, se usan `Flow N`; no se adivinan nombres desde mensajes. Identity no se implementa: incluso si un resultado legacy contiene nombre, v1 usa `Character N`.

## Clasificación de negocio

La tabla de proyección utiliza identificadores exactos existentes, no coincidencias de substrings. Los prefijos de Black Market se normalizan para sus dos nombres históricos cortos. Los demás flows ya conservan nombres canónicos completos.

| Evidencia disponible | Clasificación / explicación |
| --- | --- |
| Send Stamina `daily_pending` / `all_no_effect` | Business incomplete: Daily pendiente tras All sin efecto. Se muestra un solo motivo si aparecen ambas señales. |
| Summon Pet `insufficient_gold` | Business incomplete: GOLD insuficiente para el summon Daily. |
| Summon Pet `space_relief_unavailable`, `manual_resolution` | Business incomplete: liberación de espacio no disponible / inventario requiere resolución manual. |
| Black Market `low_gold`, `inventory_full` | Business incomplete: alguna compra no pudo completarse. |
| Mailbox `claims_leftover`, `claim_all_no_effect` | Business incomplete: queda mail sin reclamar / Claim All sin efecto. Se prioriza el motivo final de leftovers si están ambos. |
| World Boss `insufficient_sapphires`, `inventory_full`, `bag_full`, `meteor_full` | Business incomplete: no se pudo entrar o completar la raid por recurso/espacio. No se afirma completion de una Daily World Boss: ese flow no tiene guard Daily. |
| `noop` de Send Stamina, Summon Pet, Guild, Daily Quests o Mailbox | Complete: no había acción pendiente según el contrato del flow. No implica que todas las Dailies del juego estén hechas. |
| World Boss `previous_rewards` | Informativo, no implica incompletitud de la raid posterior. |
| Otros eventos actuales de ejecución/completion/skip | Informativos; el estado técnico exitoso y el cierre del personaje determinan completion. Un skip no implica por sí solo una tarea incumplida. |
| Evento de negocio desconocido sin otro motivo reconocido | Sin evaluar; se expone una limitación, nunca se inventa complete/failure a partir de su texto. |

**Límites de causalidad comprobados:** Send Stamina no observa elegibilidad individual de amigos. `all_no_effect + daily_pending` no prueba “no eligible friends”. V1 no emite esa explicación. Pet Space Relief distingue `NO_RELIEF_AVAILABLE` de fallo/cancelación, pero su resultado no conserva la causa específica del popup; Summon sólo conserva los eventos generales de relief/manual. “No material” no se infiere de ese outcome genérico: puede representar otras ramas sin progreso. El report tampoco interpreta un evento interno de no material como incompletitud terminal si un recovery posterior logra completar la actividad.

La estructura actual basta para las cuatro categorías y motivos veraces; no se modifica ningún flow. Si más adelante se requiere mostrar **la causa específica** no-material, el cambio mínimo es conservar el motivo semántico en `PetSummonSpaceReliefResult` y copiarlo al `fields` del FlowEvent terminal ya existente, sin un evento adicional. Para “no eligible friends” hace falta primero una señal adquirida que lo demuestre; agregar un campo sin esa observación no resolvería el problema. Ambos detalles quedan fuera de v1.

## Estado global y conteos

El estado de ejecución y el estado de negocio son distintos. Una sesión `SessionStatus.COMPLETED` puede proyectarse como business incomplete: la composición y Rotation terminaron normalmente, aunque alguna acción de negocio quedó pendiente. No cambia el exit code ni el status de ejecución GUI.

Un fallo técnico terminal tiene precedencia sobre motivos de negocio previos; la cancelación explícita queda separada de failure. Se conservan los motivos de los flows anteriores aunque el personaje o la sesión acaben fallando/cancelados. No se interpreta una causa incidental de un flow exitoso o cancelado como fallo técnico.

`characters_processed` conserva el significado del runner: personajes cerrados, incluido su advance final verificado. El personaje interrumpido se representa en el detalle y sus conteos, pero no se suma a procesados. No se fabrican filas para personajes nunca iniciados. Por eso los conteos de categorías describen **personajes representados**, no todo el total esperado ni el número de sesiones: una cancelación anterior al primer personaje tiene cero personajes cancelados.

`flows_completed` cuenta contratos técnicos completados, incluidos los no-op y business incompletes. Un flow cuyo `run()` devolvió COMPLETED pero cuya postcondición fue rechazada por SessionRunner se muestra técnico fallido y se excluye de ese contador. Un fallo de precondición agrega sólo el flow fallido, sin inventar resultados para los flows posteriores. Rotation fallida conserva los flows anteriores completados. El flag de advance por personaje requiere `SessionCharacterResult.completed`, porque un RotationResult exitoso todavía puede fallar su postcondición exterior.

Resultados aggregate-only conservan procesados/advances originales pero no inventan categorías ni filas. Un plan/detalle truncado o evento desconocido queda sin evaluar. Un fallo legacy sin `FailureCause` sigue siendo technical failure con “cause unavailable”; si SessionResult ya construyó una causa desde su string legacy, se conserva tal cual. En flows repetidos sin posición terminal legacy se explicita la ambigüedad y no se reetiquetan ejecuciones previas como fallidas.

## Diagnóstico y renderer

`failure` conserva el mismo `FailureCause` inmutable, incluido message, exception_type, step, sequence y `evidence_ref`. Esto permite drill-down futuro sin exponer sus detalles en la vista normal. El renderer usa una allow-list: tipo de fallo y referencia; omite mensajes crudos que pueden contener secuencias, trazas o dumps perceptivos. Los run/session IDs se conservan en el objeto y se omiten del texto.

`evidence_ref` sigue siendo la URI opaca original de Failure Evidence. El builder/renderer no consulta, abre ni valida su destino y no promete disponibilidad: el texto dice explícitamente “availability not checked”. Una URI caducada por retención sigue siendo una referencia útil para correlación, no un nuevo failure. La referencia propagada a sesión/personaje/flow se muestra una sola vez; otros fallos distintos conservan sus propias referencias. Sólo se renderiza evidencia asociada a un fallo técnico.

La duración se trunca a segundos y se formatea `HH:MM:SS`, sin timestamps actuales ni locale implícito. El renderer produce siempre el mismo texto para el mismo objeto; no imprime sequence numbers, poll_count, retries, confidence, UNKNOWN rates, operation IDs ni detalles de percepción.

## Integración y compatibilidad

- `GuiExecutionResult.report` es opcional y keyword-only. El worker lo construye después de salir del contexto runtime para sesiones que devolvieron `SessionResult`; la queue, status, counters y error legacy conservan sus contratos. No se modifica Tk ni se agregan controles GUI.
- `Run Flow Once` y excepciones de setup/cleanup sin un resultado de sesión mantienen `report=None`. No se sintetiza una sesión a partir de una excepción ni se implementa replay del lifecycle exterior en esta fase.
- `tools.run_session` renderiza SessionReport y el path del JSONL al terminar; los códigos de salida permanecen basados en SessionStatus. `tools.runtime_cli.session_summary` conserva su firma y salida legacy para consumidores existentes. El resumen standalone no cambia.
- El timer GUI mide la ejecución exterior, mientras `report.duration` mide SessionRunner; no son métricas intercambiables. Legacy sin medición muestra duración no disponible.
- SessionRunner añade únicamente metadata de resultado y medición. No cambia contratos de éxito, guards, pre/postcondiciones, cancelación, input, waits, retries o cantidad/orden de advances. Observability y Failure Evidence permanecen intactos.

## Validación y follow-ups

Tests nuevos cubren las categorías, outcomes actuales, no-op, parcialidad legacy, causas/referencias ausentes o caducadas, identidad fallback, orden/repeticiones, postcondiciones, Rotation, rendering reproducible y ausencia de ruido. Tests del runner comprueban que construir/renderizar dos veces no agrega llamadas ni eventos, y que una incompletitud business no impide Rotation. Controller y CLI verifican compatibilidad de status/exit codes y acceso al objeto sin Tk.

Comandos desde raíz:

```powershell
./tools/agent_run.ps1 pytest -q tests/test_session_report.py tests/test_session.py tests/test_gui_controller.py tests/test_runtime_cli.py tests/test_structured_observability.py tests/test_failure_evidence.py
./tools/agent_run.ps1 pytest -q
git diff --check
```

Validación final: **144 tests dirigidos passed** y **1572/1572 tests hardware-free passed en 265,46 s** sobre el código final, incluyendo 49 casos nuevos. `git diff --check`, whitespace de archivos nuevos y enlaces Markdown locales de la documentación modificada válidos. Sin hardware ni cambios perceptivos; no corresponde recalibración. Los cuatro scripts raíz locales ajenos permanecen preservados. Sin commit ni push.

Después de revisión, GUI funcional mínima podrá consumir `report.characters`, categorías y motivos, y abrir evidencia bajo acción explícita comprobando que todavía existe. El drill-down técnico puede usar `FailureCause` y el JSONL; no necesita reconstruir business policy. Identity podrá sustituir la etiqueta en una fase posterior. Character Identity, Eligibility, Arena, nuevas causas semánticas y replay de sesiones interrumpidas antes de producir resultado no se implementan aquí.
