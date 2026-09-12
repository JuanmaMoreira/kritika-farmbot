---
name: kritika-hil-acquisition
description: Adquirir y calibrar evidencia visual o física de Kritika FarmBot con HIL controlado. Usar para capturas, ground truth, ROI/OCR, hitboxes y swipes; no para implementar gameplay.
---

# Kritika HIL acquisition

Aplicar las políticas permanentes del `AGENTS.md` raíz y responder una pregunta observable por campaña.

## Antes del live

- Formular la condición a observar, la evidencia que la responderá y el punto seguro de detención.
- Confirmar que la propiedad requiere dispositivo: ground truth visual, hitbox, tap tragado, swipe, timing, loading, animación u overlay físico.
- Consultar `AGENT_LOCAL.md` para paths locales. No asumir Python, ADB o scrcpy en `PATH`.
- Mantener runtime productivo fuera del patch; una adquisición no autoriza fixes incidentales.

## Ejecución HIL

1. Trabajar una condición por vez.
2. Usar chat + `steer`; el usuario navega y opera teléfono/GUI mientras el agente observa y captura.
3. Detenerse antes de input o efecto no autorizado y pedir la acción semánticamente.
4. Registrar ground truth humano antes de atribuir identidad, causalidad, destino o éxito. Predicción y transición visual no sustituyen confirmación.
5. Capturar el mínimo suficiente: positivos, negativos relevantes, contextos visualmente próximos y la regresión concreta. Detener la campaña cuando la pregunta ya esté respondida.

## Curación y calibración

- Mantener raws en `artifacts/`, curados bajo `screencaps/` y promoción reproducible en manifests/assets runtime. No versionar raw ni curados grandes.
- Preservar procedencia, labels humanos, hashes y relación raw→curado; no etiquetar desde predicciones.
- Elegir ROI por estabilidad observable. Auditar oclusión/layering real; una intersección geométrica por sí sola no prueba interferencia.
- Para OCR conservar negativos contextuales y valores difíciles. Para hitboxes/swipes registrar geometría derivada de `frame.shape`, acción exacta y efecto físico observado.
- Evaluar sólo detectores/lectores invalidados y reutilizar cache válida. Full corpus requiere una invalidación amplia concreta.

## Cierre

- Asegurar cleanup de capture sources, procesos, sockets y forwards.
- Reportar pregunta, GT, positivos/negativos, paths raw/curated, assets/manifests promovidos, validación y límites no resueltos.
- No ampliar adquisición, recalibrar vecinos ni modificar runtime una vez respondida la pregunta original.
