---
name: kritika-dev-workflow
description: Desarrollar o depurar Kritika FarmBot con causa demostrada, cambio mínimo y validación afectada. No usar para campañas puras HIL.
---

# Desarrollo causal

Aplicar [AGENTS](../../../AGENTS.md); consultar [GAMEPLAY_GT](../../../docs/GAMEPLAY_GT.md) antes de interpretar un fallo físico o pedir HIL.

1. Leer estado/diff local y sólo el contrato relevante. Separar GT, implementación y heurística; no inferir wiring desde componentes standalone.
2. Localizar la primera divergencia en logs/capturas/código. Un miss de percepción no reabre un hecho físico cerrado.
3. Implementar la composición mínima en el owner existente. No resolver vecinos ni ramas hipotéticas; ramas explícitas bastan para un conjunto pequeño de estados.
4. Elegir validación capaz de falsar el cambio: docs/referencias para docs, directos + afectados para lógica, replay/incremental si cambió percepción. Reutilizar resultados no invalidados.
5. Si queda una pregunta física realmente abierta, usar un smoke autorizado y breve; detenerlo en la primera divergencia, corregir mínimamente y repetir sólo lo invalidado. No exigir HIL para cada rama o postcondición ya establecida.
6. Cerrar al resolver el alcance: diff acotado, trabajo ajeno preservado y fuente documental dueña actualizada. No añadir mejoras por oportunidad.

Si aparecen varias capas nuevas, excepciones o estado implícito para una acción simple, detener el patch y proponer la alternativa local más simple. Cambios transversales requieren causa compartida real y alcance acordado; no preservar complejidad por inversión previa.
