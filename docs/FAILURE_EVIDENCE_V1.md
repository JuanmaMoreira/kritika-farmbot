# Failure Evidence v1

Consolidada en `16f2d41` sobre `main@95c6bd68b8c3162b2d424a1cf90a4e03d9a00861`. Las menciones posteriores a revisión/ausencia de commit describen el cierre histórico de esta fase. JSONL sigue siendo la fuente machine canónica: un bundle es un attachment diagnóstico local, no otro log ni un sistema de reporting. Su consumidor humano actual se documenta en [`SESSION_REPORT_V1.md`](SESSION_REPORT_V1.md).

## Ownership y lifecycle

`open_productive_runtime` crea un `FailureEvidence` por ejecución, conecta `RuntimeObserver.snapshot_consumer` con su ring y lo instala como enriquecedor del stream existente. El owner conserva la evidencia hasta después de publicar `runtime.failed` y libera imágenes/desconecta el enriquecedor en `finally`, incluso si falla la construcción del runtime. GUI y CLI usan automáticamente esa misma composición; no cambian controles ni policy.

`RuntimeObserver` entrega el `RuntimeSnapshot` validado después de resolver, sin capturar de nuevo. El callback no devuelve decisiones y sus errores se aíslan. Capture, Perception y ContextResolver no conocen el storage. No se añaden eventos por frame, OCR, reprocesamiento perceptivo, input ni waits.

El ring conserva las últimas **3 secuencias estrictamente crecientes** observadas durante ese runtime. Repetidas/regresivas no desplazan muestras. No es una ventana de segundos ni promete incluir todos los frames decodificados. Puede cruzar flows/personajes: cada metadata conserva el scope observado y su timestamp de captura, para distinguir evidencia previa de la del fallo. Si captura/percepción/resolver fallan antes de construir el snapshot, se conserva la última ventana válida; no se inventa un snapshot del error.

## Contenido y serialización

No se retiene el `RuntimeSnapshot` completo: contiene la imagen original y mantendría memoria proporcional a su resolución. Se proyectan explícitamente sus campos pequeños a JSON estricto, ordenado y sin `default=str`, pickle ni `repr` de objetos. La proyección contiene:

- `sequence`, `timestamp` y `timestamp_clock=capture_monotonic`;
- scope de observación: run/session/character/flow/operation/parent/step, nullable según contexto disponible;
- observations en orden del detector: name, confidence, source, value y ROI relativa;
- estado completo: status, base, overlays, subcontext, candidatos, sequence y timestamp;
- `RuntimeFacts` intra-snapshot: gold_slots y purchased_slots ordenados;
- geometría original y metadata del PNG reducido.

Los facts demand-driven OCR/temporales no son campos de `RuntimeSnapshot` y no se fabrican ni se vuelven a leer. Sus eventos existentes siguen en JSONL, correlacionados por scopes. No se guardan engines, dispositivos, sockets, datos de `CharacterContext.name` ni trazas de excepción. Los píxeles pueden contener el chat o texto visible del juego; v1 no hace redacción visual.

Cada muestra posee una imagen BGR uint8 independiente con lado máximo **960 px**, relación de aspecto preservada y sin upscale. `INTER_AREA` crea directamente la copia reducida; sólo las imágenes ya pequeñas requieren `.copy()`. El ndarray se marca read-only y no se retiene el original. La reducción pertenece exclusivamente a evidencia: jamás se devuelve a percepción ni se usa para decidir input.

Hay un máximo de **256 KiB de JSON por archivo**. Un error de muestreo/serialización descarta esa muestra y conserva la ventana válida anterior. La falta de muestras produce un bundle válido con lista vacía; el writer también admite muestras sin imagen, aunque el RuntimeSnapshot productivo actual exige imagen y geometría coherentes.

## Trigger y propagación

`FailureEvidence.enrich` es el único seam de elegibilidad, invocado por `RuntimeEventStream.emit` después de asignar secuencia/timestamp/correlación y **antes de cualquier consumer**. Sólo reconoce causas estructuradas en `flow.failed`, `rotation.failed`, `session.failed` y `runtime.failed`.

| Situación | Evidencia |
| --- | --- |
| Daily termina FAILED por una espera | Un bundle en `flow.failed`; referencia propagada a sesión |
| Rotation aborta técnicamente | Un bundle en `rotation.failed`; referencia propagada a sesión |
| Fallo de pre/postcondición del runner | Bundle en su primer evento terminal disponible |
| Excepción terminal de configuración/captura | Bundle en `runtime.failed`, aunque no haya snapshots |
| Timeout best-effort de Auto Battle o espera recuperada | Ninguno |
| `transition.completed` con timeout/abort o excepción manejada | Ninguno; sólo el caller terminal puede promoverlo |
| Cancelación voluntaria | Ninguno |
| Error del propio writer | Ningún evento nuevo ni bundle recursivo |

Los eventos de cancelación no están en la allow-list. Además se excluyen `type=cancelled/cancellation` y exception types `RuntimeWaitCancelled`, `KeyboardInterrupt`, `SystemExit`, `CancelledError`, incluso si un boundary legacy publica `.failed`. No se parsean strings para inferir cancelaciones o excepciones. Daily actualmente aporta `state_wait_failed` dentro de una causa legacy; no se renombra a `state_wait_timeout` ni se inventa el tipo perdido por ese caller.

`publish_failure` publica una vez y devuelve el mismo `FailureCause` con la referencia persistida. SessionRunner y el runner standalone reemplazan el resultado inmutable conservando su clase, campos de dominio, strings y status. FlowResult y RotationResult anidados comparten la referencia con SessionResult. Una referencia existente evita un segundo bundle en la propagación; una excepción standalone lleva esa misma causa al boundary exterior. Si una escritura falla, una publicación terminal exterior todavía puede intentar escribir: cada intento es síncrono y acotado por la profundidad existente del lifecycle, nunca un retry loop del writer.

Un resultado FAILED sin los campos opcionales error/failure recibe metadata `legacy_error` con el nombre del terminal, conservando `error=None`. Si falla incluso la resolución inicial del root de storage, evidencia queda desactivada y el runtime continúa con su comportamiento original.

`RuntimeEventStream.record` ahora devuelve aditivamente el `RuntimeEvent` publicado o `None` ante fallo de construcción; sinks legacy que devuelven `None` siguen funcionando. No cambia el schema JSONL v1 ni `FailureCause`. VerifiedTransitionResult y ControlledWaitResult permanecen intactos: sus fallos internos no son terminales de gameplay y no reciben evidencia anticipada. No se reabre su policy ni la de UNKNOWN/AMBIGUOUS, guards, stable_for, retries o deadlines.

## Formato y referencias

```text
artifacts/failure_evidence/
  failure_<uuid32>/
    .owner
    snapshot_<capture_sequence>.json
    frame_<capture_sequence>.png
    ... (hasta 3 pares)
    failure.json
```

`failure.json` contiene `evidence_schema_version=1`, la `FailureCause` publicada, el envelope de su evento canónico y una lista ordenada de `{sequence, snapshot, frame}`. El envelope incluye `run_id`, `session_id`, `character_index`, `flow`, `operation_id`, `parent_operation_id`, `step`, `event_sequence`, timestamp UTC, event y component. `(run_id, event_sequence)` identifica el evento JSONL; no se confunde con la secuencia de captura. La causa conserva sus propios step/sequence si los tenía.

`evidence_ref` es una URI `file:///.../failure_<uuid>/failure.json` absoluta, estable al cambiar el cwd y escapada mediante `Path.as_uri()`. Los paths internos de snapshots/frames son relativos al bundle, que puede copiarse completo para inspección. La URI original no sigue una mudanza del directorio y puede expirar por retención; un futuro SessionReport debe tratar referencias ausentes como evidencia ya no disponible. No se guarda una segunda copia de todo el JSONL.

## Escritura, límites y retención

El writer es **síncrono**: codifica 0–3 PNGs con compresión **1**, serializa metadata y valida tamaño antes de crear el directorio. Usa UUID y creación exclusiva de directorio/archivos. Escribe `failure.json` al final; sólo después publica `evidence_ref`. No promete fsync, durabilidad ante corte eléctrico ni atomicidad frente a lectores externos que inspeccionen directorios aún incompletos.

Errores de mkdir, encode PNG, JSON, cuota, pruning o escritura dejan el evento y la causa originales. El fallo original nunca se sustituye por el error del writer. La limpieza de un intento parcial sólo elimina archivos creados por ese intento y hace `rmdir` no recursivo. La señal de fallo de evidencia es `evidence_ref=null`; no hay otro failure reporter. Un JSONL consumer fallido puede dejar un bundle completo sin línea durable, igual que la entrega best-effort existente.

Límites por root gestionado:

| Límite | Valor |
| --- | --- |
| Ring | 3 muestras |
| Imagen | 960 px lado máximo, BGR uint8 |
| JSON por archivo | 256 KiB |
| Bundle completo | 10 MiB |
| Bundles retenidos | 20 |
| Storage gestionado | 128 MiB |
| Antigüedad | 7 días desde mtime del directorio |

La retención se evalúa al abrir y antes de escribir, reservando espacio para el bundle nuevo y quitando primero los más antiguos. No hay daemon: un runtime inactivo no elimina archivos al cumplirse exactamente siete días; la siguiente apertura/escritura aplica la retención. Restos parciales con marcador propio también entran al cleanup.

Sólo se reconocen directorios `failure_<uuid32>` con marcador exacto `.owner` y archivos de la allow-list de este formato; no se siguen symlinks/junctions ni se borran subdirectorios. Una adición curada ajena a ese formato deja el bundle fuera de gestión automática. Los límites corresponden al storage gestionado, no a otros datos bajo `artifacts/`. Un fallo de cleanup cancela la nueva escritura. Cada runtime serializa sus operaciones con un lock; v1 presupone un único runtime productivo activo por root, como la GUI actual. UUID evita colisiones entre ejecuciones; no es una cuota transaccional entre procesos concurrentes independientes.

Estos bundles son adquisición diagnóstica temporal, ignorada por Git. Antes de promover evidencia a datasets, copiar los frames necesarios a almacenamiento curado y actualizar el manifest; nunca referenciar un bundle sujeto a retención como asset runtime permanente. No se tocaron raws portal/identidad referenciados por manifests.

## Memoria y mediciones locales

`tools.benchmark_failure_evidence` usa tres imágenes locales existentes y una segunda carga de ruido determinista con sus mismas dimensiones. Agrega 80 observations sintéticas por snapshot, sin ejecutar percepción ni OCR. Mide ingestión, escritura real del bundle y variantes de encode; elimina todos sus bundles temporales, conservando únicamente estadísticas. Los paths y resultados quedan en `artifacts/failure_evidence_v1/`.

Para tres capturas de 2712×1224, originales: **29.875.392 bytes (28,49 MiB)**. Ring reducido a 960×433 más metadata: **3.768.696 bytes (3,59 MiB)**. Esto cuenta buffers y bytes serializados, más un overhead Python pequeño no incluido; no es RSS. El máximo teórico retenido por las tres muestras es **8,66 MiB** con imágenes cuadradas y metadata al límite. Durante el reemplazo hay una imagen adicional transitoria; al escribir se añaden buffers PNG/JSON hasta el límite del bundle y workspace interno de OpenCV. No se retienen secuencias largas ni video.

La primera comparación aislada dio, para los tres PNGs reales:

| Variante | Bytes PNG | Encode mediano |
| --- | --- | --- |
| Original, compresión 1 | 7.960.578 | 471,09 ms |
| Original, compresión 3 | 7.443.363 | 645,95 ms |
| 960 px, compresión 1 (elegida) | 1.782.386 | 81,27 ms |
| 960 px, compresión 3 | 1.707.106 | 116,80 ms |
| 960 px, compresión 6 | 1.624.944 | 268,69 ms |

La compresión 1 conserva exactamente los mismos píxeles reducidos que 3/6. El ahorro adicional de 3 es sólo 4,2% frente a 1, con ~44% más tiempo de encode. El downscale sí pierde detalle de píxeles pequeños, por lo que los PNGs son diagnóstico visual y no reemplazan evidencia original para recalibrar detectores.

Medición final con compresión 1, sin la suite ejecutándose en paralelo: 10 escrituras por carga y 30 ingresos de snapshots. JSON crudo: `artifacts/failure_evidence_v1/benchmark-final.json`. p95 es empírico sobre esas muestras pequeñas.

| Carga | Bundle mediano | Ingreso por snapshot mediana / p95 | Escritura mediana / p95 |
| --- | --- | --- | --- |
| Capturas reales locales | 1.810.828 bytes (1,73 MiB) | 4,64 / 5,74 ms | 106,54 / 116,67 ms |
| Ruido determinista | 3.274.301 bytes (3,12 MiB) | 5,71 / 6,91 ms | 174,65 / 216,30 ms |

La escritura medida incluye encode, metadata, pruning y archivos locales; el benchmark no agrega un JSONL consumer a ese tiempo. El costo terminal observado favorece mantener la solución síncrona sencilla. No hay garantía de deadline de IO ni benchmark live: un disco bloqueado puede detener un writer síncrono. La evidencia consume CPU en el callback y añade latencia de cierre ante fallos; no modifica la configuración de gameplay. Los tests verifican clocks/policy/inputs con evidencia activada, desactivada y fallida; no prueban inmunidad física a cualquier latencia de disco.

Comando reproducible desde la raíz:

```powershell
./tools/agent_run.ps1 tools.benchmark_failure_evidence --frames artifacts/portal_notification_acquisition/positive_battle_select_1_seq1.png artifacts/portal_notification_acquisition/positive_guild_1_seq1.png artifacts/portal_notification_acquisition/positive_hell_battle_select_1_seq1.png --output artifacts/failure_evidence_v1/benchmark-final.json
./tools/agent_run.ps1 pytest -q tests/test_failure_evidence.py tests/test_structured_observability.py tests/test_productive_runtime.py tests/test_session.py tests/test_runtime_observer.py tests/test_event_log.py
./tools/agent_run.ps1 pytest -q
git diff --check
```

## Archivos y follow-ups

Validación final: **1523/1523 tests hardware-free passed**; **110 dirigidos passed en 1,73 s**, con 38 casos nuevos de evidencia. La primera suite integrada pasó 1521 tests en 251,23 s; tras añadir las dos regresiones de root inválido/causa opcional y sus fixes se repitió la suite completa. La última ejecución reportó 15.852,93 s de elapsed; ese dato de ejecución no se utiliza como benchmark de gameplay ni del writer. Resultados y hashes del delta están en `artifacts/failure_evidence_v1/validation.json`.

`git diff --check` limpio, whitespace de archivos nuevos y enlaces Markdown locales válidos. No hubo hardware, input Android ni recalibración. Los tests de composición escriben en tmp_path; se eliminaron exactamente dos bundles sintéticos redundantes de configuración generados antes de aislar esos tests, tras verificar su contenido y referencias. Los benchmarks limpian sus propios bundles temporales; las capturas originales, manifests y cuatro scripts raíz ajenos permanecen preservados.

`bot/failure_evidence.py` implementa ring, serialización, writer, retención y helper de propagación. Los cambios en `event_log.py`, `runtime_observer.py`, `productive_runtime.py` y `session.py` conectan esos seams. `tests/test_failure_evidence.py` cubre los doce casos de aceptación, runners reales, Daily real, fallos de storage y preservación de inputs. `tests/test_productive_runtime.py` verifica cleanup/fallo inicial y aísla todos sus bundles en tmp_path. El benchmark es `tools/benchmark_failure_evidence.py`.

Próximo trabajo, sólo tras revisión: SessionReport consumidor de referencias, seguido del orden de ROADMAP. GUI nueva, Character Identity, Eligibility y Arena no se iniciaron. No se necesita una recalibración perceptiva: ningún detector, ROI, asset, preprocessing productivo ni regla del resolver cambió.
