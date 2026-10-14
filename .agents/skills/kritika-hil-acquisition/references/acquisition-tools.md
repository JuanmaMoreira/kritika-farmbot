# Selección de herramientas reales

Cargar para adquisición hardware, promoción o evaluación, sólo la fila pertinente. Inspeccionar argumentos y efectos de la herramienta antes de ejecutarla; estos enlaces no autorizan su ejecución.

| Necesidad | Capacidad actual |
| --- | --- |
| Evolución pasiva / PNG nativo puntual | [arena_hil_observe](../../../../tools/arena_hil_observe.py): modo stream acotado con archivo STOP; `--native-label` captura un PNG mediante ADB y registra dimensiones, UTC, scope y SHA-256. No ejecuta input/OCR/resolver. El modo nativo no aporta secuencia stream. |
| Etiquetado humano de bases conocidas | [capture_semantic_dataset](../../../../tools/capture_semantic_dataset.py): GUI de captura stream por `get_frame`, labels Lobby/Character Select/Battle Mode Select y manifest de adquisición. No es captura nativa ni etiquetador genérico para cualquier contexto. |
| Curación / evaluación del corpus productivo | [production_perception_evaluation](../../../../tools/production_perception_evaluation.py) y curadores del subsistema: verificar argumentos, manifest, paths y transformaciones actuales. Pueden escribir curados, resultados o caches; no son herramientas de auditoría sólo lectura. |
| Evaluación incremental | [incremental_perception_evaluation](../../../../tools/incremental_perception_evaluation.py): API de pares detector/frame, fingerprints y cache derivada; no es un CLI autónomo. Usar el evaluator caller afectado, inspeccionando su soporte de cache. |
| Labels semánticos y ambiguos | [semantic_slice_evaluation](../../../../tools/semantic_slice_evaluation.py): schema/review_status y evaluación de confirmados; preservar el manifest y estados admitidos por ese schema. |

Herramientas Python desde raíz según AGENTS/AGENT_LOCAL. Raw diagnósticos en artifacts y curados locales en screencaps según sus owners; no renombrar esquemas existentes para imponer un manifest universal. Registrar hashes y transformaciones que el capturador no produzca.

Si la fuente es un bundle temporal, consultar [retención de Failure Evidence](../../../../docs/FAILURE_EVIDENCE_V1.md#escritura-límites-y-retención) antes de promover: copiar evidencia necesaria a almacenamiento curado autorizado y relacionarla con el origen; no dejar un asset runtime apuntando al bundle temporal. ROI y layering se resuelven desde GT, no desde esta tabla.
