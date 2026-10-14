# Correlación y límites de evidencia

Cargar únicamente ante dudas sobre correlación, procedencia o falta de bundle. Las fuentes enlazadas son dueñas del formato; inspeccionar sus headings/rangos pertinentes, sin copiar sus contratos aquí.

| Pregunta | Fuente y búsqueda focal |
| --- | --- |
| Evento y causa original | JSONL de la ejecución: run/session/operation, parent, step y terminal anterior a la propagación |
| Bundle, frames y scopes | [Failure Evidence](../../../../docs/FAILURE_EVIDENCE_V1.md): «Trigger y propagación», «Formato y referencias», «Ownership y lifecycle» |
| MANUAL proyectado como incompletitud | [SessionReport](../../../../docs/SESSION_REPORT_V1.md): «Clasificación de negocio», «Diagnóstico y renderer»; contrastar FlowResult/SessionResult/JSONL |
| Guard y wiring actuales | Código/tests del owner; [CONTEXT](../../../../CONTEXT.md) dirige al contrato pertinente |

`(run_id, event_sequence)` identifica un evento; la secuencia de captura identifica una muestra. Correlacionar scopes y clocks: timestamps monotónicos de captura y UTC de eventos no se restan directamente. Un ring puede contener evidencia de otro flow/personaje; no atribuir su semántica a un frame directo de otra secuencia.

Comprobar `capture.source`, `capture.original_shape` y dimensiones guardadas antes de llamar nativa a una captura. Una imagen reducida o derivada no demuestra calibración nativa nueva. Si el raw existe, usarlo para el replay que lo requiera.

MANUAL sin causa técnica puede carecer legítimamente de bundle. MANUAL técnico puede tener referencia en resultados/JSONL y no mostrarla en el reporte humano. Un bundle sujeto a retención puede faltar: declarar el límite, buscar evidencia ya existente y no recapturar ni promoverlo automáticamente.
