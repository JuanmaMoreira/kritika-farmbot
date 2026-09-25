---
name: kritika-hil-acquisition
description: Resolver hechos físicos realmente abiertos de Kritika FarmBot con adquisición mínima autorizada y calibración dirigida; no implementar gameplay.
---

# Adquisición mínima

Aplicar [AGENTS](../../../AGENTS.md) y consultar primero [GAMEPLAY_GT](../../../docs/GAMEPLAY_GT.md), logs y evidencia existente. No reconfirmar GT por OCR/detector/UNKNOWN ni por formalidad de campaña.

1. Nombrar la pregunta física aún abierta y por qué no la cierra evidencia existente. Si GT ya la responde, no adquirir. Consultar AGENT_LOCAL para herramientas.
2. Definir la menor captura/acción útil, autorización y punto seguro de parada. Chat + steer; usuario opera teléfono/GUI. Input económico/destructivo nuevo requiere autorización concreta.
3. Un USER_GT explícito o un antes→acción→después inequívoco normalmente cierra el hecho. No hay regla de una condición por campaña ni cuota de muestras: una observación puede cerrar varios hechos claros. No atribuir éxito desde la predicción o el tap aislado.
4. Detener al responder la pregunta o ante primera divergencia. Cleanup de sources/procesos/sockets/forwards incluso al fallar; no ampliar adquisición ni modificar runtime incidentalmente.

Para calibración conservar positivos, negativos relevantes, contextos próximos y regresiones reales. Etiquetas desde GT, no predicciones; procedencia y relación raw→curado preservadas. Raw en artifacts, curados locales en screencaps; no versionar datasets grandes.

ROI de identidad según oclusión/layering de GAMEPLAY_GT; para hitboxes/gestos registrar geometría desde frame.shape, acción y efecto. Evaluar sólo readers/detectores invalidados con cache válida; corpus amplio sólo por invalidación concreta.

Reportar hecho cerrado, evidencia/rutas, promoción si la hubo y límite residual. No reabrir una campaña porque el hecho determinista ya cerrado tenga otra representación técnica.
