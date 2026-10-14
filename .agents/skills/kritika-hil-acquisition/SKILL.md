---
name: kritika-hil-acquisition
description: Adquirir y curar evidencia para una pregunta física abierta o calibración perceptiva de Kritika; hardware sólo autorizado, sin iniciar gameplay ni fixes por selección.
---

# Adquisición mínima

Aplicar [AGENTS](../../../AGENTS.md). Consultar primero el rango pertinente de [GAMEPLAY_GT](../../../docs/GAMEPLAY_GT.md) y evidencia existente. Preparación, adquisición, promoción semántica e implementación son fases distintas: seleccionar este Skill no inicia hardware ni gameplay.

1. Nombrar pregunta, evidencia faltante y fase autorizada. Si GT la cierra, no readquirir. Para preparación sin hardware entregar el plan; para curación/evaluación offline trabajar sólo sobre evidencia existente.
2. Antes de consumir un estado único, preparar salida, fuente, etiquetas humanas, condición de aceptación y parada/cancelación. Para hardware consultar AGENT_LOCAL y [herramientas de adquisición](references/acquisition-tools.md); elegir stream para evolución temporal y nativa para píxeles/ROI/hitbox que requieren esa geometría, sin confundirlas.
3. Adquirir el antes→acción autorizada→después necesario. Preservar raw y procedencia: source, dimensiones, timestamps con clock, secuencia/scope y SHA-256. Si una fuente no aporta secuencia o clock correlacionable, registrar esa ausencia; no inventarlos.
4. Curar positivos, negativos relevantes y ambiguos; etiquetas desde GT, no predicciones. Conservar relación raw→curado, hash/origen y transformación. Mantener ambiguos explícitos fuera de etiquetas confirmadas y preservar regresiones vividas.
5. Si la promoción está autorizada, llevar sólo hechos acreditados a la fuente dueña y evidencia revisada al manifest correspondiente. Para promoción o evaluación cargar [herramientas](references/acquisition-tools.md); no generar assets/detectores ni implementar gameplay incidentalmente.
6. Ejecutar sólo evaluators afectados por frames, etiquetas o cambios perceptivos autorizados. Reutilizar cache válida por detector/frame; recomputar etiquetas y resolver fuera de esa cache. Reportar evaluados, hits/invalidaciones y límites de raw ausente sin exigir corpus general por rutina.
7. Cerrar al responder la pregunta o ante primera divergencia, con cleanup del owner incluso al fallar. Entregar hecho/ambigüedad, rutas y procedencia, promoción/evaluación realizadas y límite residual. Un fix posterior requiere encargo de desarrollo; restauración manual corresponde al usuario.
