# GUI funcional mínima

Consolidada en `454d111` sobre `main@7865c55559856f539a6eaa5ccdb13659c1d38d2b`. Las referencias a ausencia de commit/revisión al cierre son históricas. Sin rediseño estético, cambios perceptivos ni input físico durante la implementación. La integración posterior de [`Character Identity mínima`](CHARACTER_IDENTITY_V1.md) muestra clase o `Character N` desde el report existente, sin OCR ni lookup en Tk; el progreso conserva índice/total.

## Mapa GUI actual

| Superficie | Contrato |
| --- | --- |
| Flows | Registry único; `[x]` indica activo. La fila resaltada sirve para activar/desactivar o mover, no limita la ejecución. |
| Run Selected Flows | Todos los activos, una vez en orden visible sobre el personaje actual, sin Rotation. Characters no se utiliza. |
| Run Session | Sesión normal con todos los activos, Characters positivo y Rotation normal incluido el advance final. |
| Debug Mode / Stop Safely | Visibilidad de eventos / token compartido, sin matar workers ni cambiar policy. |
| Status / Progress | Status, Character, Flow, State, Session elapsed, resumen legacy y log path conservados. |
| Session Report | Texto íntegro de `render_session_report`, seleccionada automáticamente al recibir un report. Independiente del límite de 5000 líneas de consola. |
| Locate evidence | Selector de referencias técnicas únicas, acción explícita para localizar el bundle, mensaje de disponibilidad separado del resultado de ejecución. |
| Debug Console | Eventos filtrados, Clear/Copy selected/Copy all y queue drain existentes. Visible al iniciar una ejecución. |

Default confirmado en código y tests, sin cambios: `black_market → world_boss → send_stamina → summon_pet_daily → daily_quests → mailbox → guild_check_in`.

## Ejecución seleccionada

`GuiExecutionRequest.selected_flows` toma los IDs activos en orden y exige al menos uno. El nuevo modo `SELECTED_FLOWS` llama a `ProductiveRuntime.run_flows_once`; conserva un runtime/worker/log para todo el conjunto. El API legacy `flow_once` permanece para consumidores existentes; el botón productivo usa la nueva operación.

El seam compone el `run_flow` real, incluidas normalización de entrada, ejecución, verificación de salida, eventos y evidencia existentes. No construye Rotation, SessionPlan ni SessionRunner. No añade input, observaciones, waits, retries, guards ni nuevos eventos. COMPLETED técnico (incluido no-op o business incomplete) permite continuar. FAILED/CANCELLED detiene la secuencia. El token se consulta antes de cada componente; una cancelación solicitada tras completar el último componente no invalida retroactivamente el conjunto terminado.

`FlowsOnceResult` frozen vive en `bot/productive_runtime.py`: status, tuple de FlowResult parciales, error y FailureCause terminal. Conteos de completados/business events se derivan de los resultados conservados. Ante una excepción, `run_flow` ya publicó el fallo y enriqueció la causa; el agregado conserva esa causa y el prefijo anterior sin republicar eventos. RuntimeWaitCancelled conserva CANCELLED. Las comprobaciones internas de cada flow siguen siendo las standalone existentes.

El controller adapta campos al resultado GUI: characters_processed es 1 sólo si todo el conjunto terminó, flows_completed cuenta contratos técnicos completados y advances_completed permanece 0. `report=None`: no se fabrica una sesión ni se alteran las reglas de SessionReport para simular un advance. SessionReport sigue reservado para Run Session.

## Report y evidencia

`_finish` congela el timer y conserva campos legacy; entrega el objeto al renderer existente y muestra su texto completo. Sin report, muestra disponibilidad ausente y conserva el resumen anterior de ejecución. Al iniciar otra ejecución se limpia el report y su selección de evidencia. El timer de sesión continúa midiendo el lifecycle exterior; la duración del report sigue midiendo SessionRunner.

`bot/gui_evidence.py` enumera referencias únicas sólo de nodos ya clasificados como technical failure. No deduce negocio desde strings. Builder/renderer siguen puros. `locate_evidence` acepta únicamente URI file absoluta local sin host/query/fragment y un archivo `failure.json` existente. Decodifica espacios/caracteres escapados, rechaza destinos de red y abre la carpeta mediante `os.startfile(..., "explore")` en Windows; nunca ejecuta el archivo ni invoca un shell con la referencia. El opener es inyectable para tests sin escritorio.

La disponibilidad se comprueba en cada clic, no al renderizar ni por polling/watchers. El botón se habilita si hay referencias; una referencia puede haber expirado, y en ese caso el clic sólo informa que no está disponible. La carrera entre comprobación y apertura, permisos y errores del opener quedan aislados. No cambia status, causa, timer, log ni report; tampoco reescribe referencias. La referencia original queda legible en el report aunque desaparezca el bundle.

View sólo contiene widgets y callbacks de presentación. Controller no importa Tk ni flows concretos, worker entrega queue-only; el helper de evidencia no se ejecuta en el worker. La etiqueta `Character N` llega del renderer, sin formato ni reconocimiento duplicados en Tk; podrá cambiar en la proyección futura.

## Validación y follow-ups

Tests dirigidos: selección de uno/varios, orden GUI, comparación de trazas pre/input/post contra composición standalone, ninguna Rotation/sesión, failure/excepción intermedia, cancelación antes/entre/dentro de flows, Stop Safely, contratos rechazados, cleanup/queue/worker, render exacto en `_finish` y drain, resultados legacy, timer/progress, referencias disponibles/expiradas/no locales, fallo del opener y etiqueta suministrada por el modelo.

Comprobación separada con Tk real, ventana oculta: widgets, report, pestaña seleccionada y botón correctos, sin iniciar runtime. Fue necesario ejecutar fuera del sandbox para cargar Tcl; la suite normal conserva dobles de widgets y no requiere escritorio.

Comandos desde raíz:

```powershell
./tools/agent_run.ps1 pytest -q tests/test_gui_functional.py tests/test_gui_entrypoint.py tests/test_gui_controller.py tests/test_gui_model.py tests/test_productive_runtime.py tests/test_session_report.py tests/test_session.py tests/test_failure_evidence.py tests/test_structured_observability.py
./tools/agent_run.ps1 pytest -q
git diff --check
```

Validación final: **195 tests dirigidos verdes** y **1597/1597 tests hardware-free verdes en 262,76 s**, incluidos 25 casos nuevos. `git diff --check`, whitespace de archivos nuevos y referencias Markdown locales válidos. Sin hardware ni recalibración: no cambian flows, inputs productivos existentes, percepción, assets, waits o guards. Los cuatro scripts raíz locales ajenos permanecen preservados. Sin commit ni push.

Character Identity mínima está implementada y pendiente de revisión en su fase propia; después sigue Eligibility mínima y reevaluar milestone. Arena, pause/resume, dashboards/analytics y rediseño estético no se iniciaron. Los errores exteriores sin SessionResult siguen sin report, conforme al contrato v1. El smoke productivo físico queda para el usuario desde la GUI tras revisión y eventual commit; no se ejecutó en esta tarea.
