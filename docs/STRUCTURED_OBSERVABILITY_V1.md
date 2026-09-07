# Structured Observability v1

Implementación local/offline sobre `RuntimeEventStream → RuntimeEvent → JsonLineEventConsumer → JSONL`. No agrega otro stream ni persistencia humana. Console y GUI son proyecciones del mismo evento.

## Baseline y alcance

El 2026-09-07 se verificaron los 45 hashes de código/tests de `artifacts/checkpoint_review/validation.json`, sin discrepancias, y la presencia de los 59 archivos del checkpoint propuesto en `OPENCODE_MUSE_REVIEW.md`. La baseline es ese árbol revisado sin commit sobre `45f6ede`, no sólo HEAD. Se preservaron el lote anterior, assets, adquisición, scripts locales y findings cerrados. Esta fase tampoco hace commit/push.

La reconstrucción encontró el stream productivo existente, publicación duplicada de business outcomes en varios flows y sus runners, `world_boss.transition` duplicando el resultado de la primitive, waits de RuntimeObserver sin métricas, VerifiedTransition sin elapsed y ControlledWait con elapsed/poll_count ya disponibles. Los archivos productivos `.log` existentes ya eran JSONL. El writer `JsonLineEventLog`, usado por smokes antiguos, ahora delega al mismo stream/consumer.

## Envelope y correlación

El payload conserva timestamp UTC, level, component, event, message y fields aplanados. Añade `schema_version=1`, `event_sequence` creciente por stream y estos campos nullable:

| Campo | Dueño / significado |
| --- | --- |
| `run_id` | UUID local del stream, creado una vez por lifecycle productivo; constructor admite ID explícito para tests. No es identidad de dispositivo. |
| `session_id` | UUID por llamada a SessionRunner.run; `null` en Run Flow Once y lifecycle exterior. |
| `character_index` | Posición 1..N dentro de esa sesión; Run Flow Once usa 1. No identifica un personaje. |
| `flow` | Flow activo, incluida normalización de entrada y verificación de salida. `null` durante Rotation. |
| `operation_id` | UUID de ejecución de flow, Rotation, transición o espera; no el nombre repetible del paso. |
| `parent_operation_id` | Enlace al scope contenedor: flow → transición → wait, por ejemplo. |
| `step` | Nombre semántico de operación; RuntimeObserver usa `runtime_wait` para la espera primitiva. |

`event_scope` y `operation_scope` usan ContextVar con restauración por token en finally. No almacenan policy, snapshots ni permisos de input. El stream toma una copia del contexto al crear el evento; los agregados de percepción retienen su contexto original al publicarse más tarde. Los scopes se establecen dentro del worker que ejecuta el runtime: no se depende de heredar contexto de Tk. Nuevos threads no heredan automáticamente ContextVar; tests cubren aislamiento y restauración.

El `event_sequence` identifica y ordena emisiones dentro del stream, no frames. Los campos `sequence`, `before_sequence`, `final_sequence`, `after_sequence`, `first_sequence` y `last_sequence` se refieren a captura. Un sink fallido puede dejar huecos en el JSONL: no se promete entrega durable ni replay. Los consumers son síncronos; en concurrencia, el orden de llegada puede diferir del `event_sequence`.

## Ownership de eventos

| Familia | Fuente canónica | Conservación |
| --- | --- | --- |
| Business outcomes (`event_role=business`) | `FlowResult.events`; `publish_flow_events` invocado una vez por SessionRunner o ProductiveRuntime.run_flow | Nombres actuales, detail y campos específicos. Los resultados siguen sirviendo para contadores existentes. |
| Lifecycle (`event_role=lifecycle`) | Composition root para runtime; SessionRunner para sesión/personaje/flow/Rotation; runner standalone para flow | GUI conserva `flow.started/completed`, `rotation.started` y demás nombres actuales. |
| Transición | VerifiedTransition: `transition.completed` una vez por ejecución, también si propaga excepción/cancelación | Los eventos started/grace/retry mantienen el detalle de fases. |
| Wait y percepción | RuntimeObserver y ControlledWait | Resúmenes por operación/lote; detalles DEBUG. |
| Diagnósticos de dominio (`event_role=diagnostic`) | Componente que observa o verifica el hecho | Por ejemplo `world_boss.completed` conserva su postcondición; no es otro cierre de lifecycle. |

Se eliminaron las emisiones anticipadas duplicadas de los helpers business de Daily Quests, Mailbox, Guild Check-In y Send Stamina, y las cinco ramas business de World Boss. Summon ya acumulaba outcomes sin publicarlos; Black Market mantiene sus nombres históricos cortos en resultados. `publish_flow_events` aplica el prefijo una sola vez. Los campos `sapphires` y `branch` de World Boss pasan al `FlowEvent.fields`, aditivo y keyword-only. No se deduplican por nombre ni por tiempo: dos ocurrencias legítimas siguen siendo dos eventos.

El timestamp canónico representa publicación al devolver el resultado. Para conservar el tiempo del outcome previo a esa publicación, FlowEvent añade `created_at` UTC (keyword-only, explícitamente inyectable y excluido de igualdad), que se conserva en JSONL. Es el instante de construcción del outcome, no el del tap ni causalidad física. La publicación no depende de que el flow termine exitosamente: sus outcomes parciales también se emiten. World Boss conserva la lista parcial si un error/cancelación posterior interrumpe su ejecución; antes su catch exterior la descartaba. Una terminación abrupta del proceso antes del retorno puede perder business outcomes aún no publicados; v1 no es un journal transaccional.

`world_boss.transition` se elimina porque su información ya pertenece a `transition.completed`. Los defaults de BlackMarket/WorldBoss/Rotation entregan el sink a VerifiedTransition también fuera de la composition root. Se conservan diagnósticos útiles de negocio y las trazas en resultados; no se elimina información sólo para reducir líneas.

## FailureCause aditiva

`FailureCause` es un dataclass inmutable con `type`, `message`, `exception_type`, `flow`, `step`, `sequence` y `evidence_ref`. `payload()` produce un objeto JSON. No captura screenshots, stack traces, frames, identidad ni archivos.

FlowResult, SessionResult, RotationResult, VerifiedTransitionResult y ControlledWaitResult añaden `failure` keyword-only. `FlowResult.error`, `SessionResult.failure_cause` y los demás strings conservan su significado y contenido. Una causa legacy tiene `type=legacy_error` y no inventa exception_type a partir de parsing del string. Los boundaries instrumentados que reciben la excepción real conservan su tipo; las transiciones mantienen también secuencia/step. SessionRunner propaga la causa del flow o Rotation cuando está disponible, además del string actual. Algunos callers legacy todavía sólo aportan strings: migración deliberadamente aditiva, no tipado exhaustivo de todos los errores de dominio.

Timeout/abort/cancel de RuntimeObserver conservan sus clases, mensajes y snapshots; al surgir de wait_until reciben `failure`, `elapsed` y `poll_count`. El éxito sigue devolviendo RuntimeSnapshot. Excepciones de callbacks/captura/percepción se vuelven a propagar como antes. VerifiedTransition emite terminal antes de propagar una excepción, sin convertirla en éxito, recovery ni retry.

`evidence_ref` queda `null` en todas las rutas productivas. Es sólo el seam reservado para una futura referencia local: no define formato de evidencia ni inicia Failure Evidence.

## Timings y volumen

Duraciones en segundos. VerifiedTransition y RuntimeObserver reciben `metrics_clock` independiente (default perf_counter); no añaden consultas al reloj de deadlines del gameplay. ControlledWait conserva su reloj inyectable y las mediciones ya existentes.

| Evento / resultado | Métricas |
| --- | --- |
| `transition.completed` / VerifiedTransitionResult | elapsed, operation_id; attempt y grace_count en evento, attempt_count/grace_wait_count en resultado; outcome, secuencias inicial/final cuando hay resultado. Los intentos se cuentan incluso si después se propaga una excepción. |
| `runtime_wait.completed` | elapsed, poll_count, fresh_count, timeout, stable_for, after_sequence, final_sequence, outcome y failure. poll_count cuenta llamadas a observe, incluso stale o fallidas; fresh_count cuenta snapshots realmente evaluados. |
| `controlled_wait.*` terminal | actual_elapsed, poll_count y outcome; correlación de operación añadida, timing anterior preservado. |
| `perception.analyze_summary` | analyze_count, analyze_elapsed total, analyze_max_elapsed, analyze_error_count y secuencias inicial/final. Incluye llamadas fallidas. |

Percepción acumula como máximo **64 llamadas** por lote y vacía al cambiar contexto, al terminar un wait y al cerrar el runtime. No guarda muestras, imágenes ni buffers; memoria constante. Fuera de la composition root, un owner que consume observe directamente debe llamar `flush_analysis_metrics()` al terminar si necesita publicar el lote residual. No se emite por frame. Una espera de un solo frame puede producir un resumen de tamaño 1: la unidad de cierre sigue siendo la operación.

Los resúmenes son DEBUG y siempre llegan al JSONL; la opción debug sólo modifica visibilidad. En una espera de N polls hay un terminal y aproximadamente ceil(N/64) resúmenes de analyze, además de cualquier lote pendiente del contexto anterior. ControlledWait conserva sus pocos eventos de fase. No hay logging nuevo de cada poll.

Para análisis posterior, agrupar por run/session/flow/operation. Retry rate usa transiciones con attempt > 1 sobre ejecuciones con input (attempt > 0); contar también precondition_rejected por separado. El timeout de una espera nominal puede preceder a una transición exitosa durante grace/retry: no confundir la tasa de waits timeout con el fallo terminal de transiciones. `analyze_elapsed` mide tiempo de pared dentro de perception.analyze, no ciclos CPU, captura, resolver ni OCR separado. No sumar elapsed de scopes anidados como si fueran trabajo independiente.

Benchmark sintético local, 3 pruebas × 20.000 observaciones con percepción vacía, mismo frame y baseline preservada: mediana **28,39 µs/observe baseline**, **33,76 µs instrumentado sin escritura**, **45,93 µs con JSONL**. Diferencia aproximada: 5,37 µs de instrumentación y 17,54 µs incluyendo persistencia amortizada. JSONL: 313 eventos y 178.582 bytes por 20.000 llamadas. Artefactos y script reproducible en `artifacts/observability_v1/`; medición ilustrativa, realizada mientras corría la suite, no benchmark de CV real ni garantía de latencia de disco. No hubo medición live ni tuning de gameplay.

## Robustez y compatibilidad

RuntimeEventStream aísla cada consumer; `record` también protege construcción de diagnósticos. Los componentes que aceptan EventSink externo conservan escritura best-effort. JSONL, consola y GUI no intervienen en decisiones de gameplay. No se agregan retries de sinks ni infraestructura remota. Un consumer síncrono lento puede añadir latencia; v1 no introduce una cola background ni promete inmunidad a sinks que nunca retornan.

Los nuevos paths por defecto terminan en `.jsonl`; paths explícitos `.log` siguen aceptados y contienen JSONL. JsonLineEventLog sigue disponible, pero ahora sus payloads llevan el envelope canónico aditivo. Consumidores externos que comparaban objetos JSON completos deben aceptar esos campos nuevos. GUI y CLI existentes mantienen sus interfaces y lifecycle; no se implementa una nueva GUI.

UNKNOWN/AMBIGUOUS, frescura, stable_for, budgets, orden de llamadas, guards y cantidad de inputs se preservan. Tests de estabilización siguen vigentes. La validación dirigida incluye scopes/threads, persistencia fail-safe, metadata legacy, canon de business events, finalizaciones canceladas/fallidas, batches, timings con clocks falsos y retries con las mismas acciones.

## Follow-ups reservados

Failure Evidence podrá vincular una causa/evento a evidencia local mediante evidence_ref; todavía debe diseñar adquisición, límites, persistencia y cleanup. No se crearon screenshots ni ring buffers. SessionReport deberá derivarse de estos eventos/resultados; no se diseñaron agregadores de reporte. GUI funcional, Character Identity, Eligibility y Arena permanecen fuera de esta fase.

## Archivos de esta fase

Validación final: **1485 passed en 242.25 s**, suite hardware-free completa sobre el código final. Los tests dirigidos de observabilidad/sesión/contratos/World Boss dieron **109 passed**; Summon HIL y observabilidad, **36 passed**. `git diff --check` limpio y AST sin definiciones duplicadas en el delta propio. No hubo input físico ni cambios perceptivos que requirieran recalibración. La validación y hashes finales se conservan en `artifacts/observability_v1/validation.json`.

El delta propio se conserva en `artifacts/observability_v1/phase.diff`, comparado con la copia de la baseline sin commit, para no confundirlo con el lote anterior en git diff HEAD.

| Archivos | Cambio |
| --- | --- |
| `bot/event_context.py`, `bot/event_log.py` | Scopes y correlación, envelope canónico, roles, writer legacy delegado y aislamiento de sinks. |
| `bot/failure_cause.py`, `bot/flow_contracts.py` | Causa estructurada aditiva; metadata/created_at de outcomes y publicación compartida. |
| `bot/session.py`, `bot/productive_runtime.py` | Dueños de publicación/lifecycle, scopes, propagación de causas, cierre de métricas y extensión de archivo. |
| `bot/runtime_observer.py`, `bot/verified_transition.py`, `bot/controlled_wait.py` | Medición/agregación, terminales correlacionados y resultados compatibles. |
| `bot/black_market_flow.py`, `bot/rotation.py` | Sink para transiciones por defecto; RotationResult.failure. |
| `bot/world_boss_flow.py` | Metadata business conservada, publicación duplicada retirada, retención de outcomes ante excepción/cancelación y resumen de transición único. |
| `bot/daily_quests_flow.py`, `bot/mailbox_flow.py`, `bot/guild_check_in_flow.py`, `bot/send_stamina_flow.py` | Helpers acumulan business outcomes sin publicarlos otra vez. |
| `tests/test_structured_observability.py` | Nuevas regresiones hardware-free de contratos, métricas, correlación y fallos. |
| `tests/test_event_log.py`, `tests/test_session.py`, `tests/test_productive_runtime.py`, `tests/test_world_boss_flow.py`, `tests/test_summon_pet_daily_flow.py` | Expectations de schema/publicación aditiva y fixtures inicializados por el constructor real; assertions de gameplay preservadas. |
| `CONTEXT.md`, `ARCHITECTURE.md`, `ROADMAP.md`, este documento | Estado, contratos, compatibilidad, mediciones y trabajo reservado. |
