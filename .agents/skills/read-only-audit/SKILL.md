---
name: read-only-audit
description: Auditar sin mutaciones arquitectura, Git, almacenamiento, documentación, dependencias o rendimiento de Kritika; sólo ante un encargo de auditoría.
---

# Auditoría focal sin escrituras

Aplicar [AGENTS](../../../AGENTS.md). Delimitar objeto, pregunta y entrega; no activar por una lectura incidental de código ni transformar recomendaciones en ejecución.

1. Inventariar sólo lo necesario para responder: paths, tamaños, revisiones, contratos, consumidores o mediciones existentes. Registrar procedencia y referencias verificables; separar hechos, inferencias e información no disponible.
2. Comprobar dependencias y consumidores antes de declarar algo huérfano, redundante o eliminable. Diferenciar capacidad standalone, wiring productivo, configuración local e historia. Usar [CONTEXT](../../../CONTEXT.md) para elegir la fuente dueña y leer rangos focales.
3. Elegir lecturas sin efectos secundarios. No ejecutar tests, evaluators, benchmarks, imports de módulos del repo, gestores de dependencias ni arranque de hosts que puedan escribir caches, índices, logs, resultados o auxiliares. No guardar el informe en disco ni redirigir salidas a archivos. Si una medición nueva necesita escrituras, proponerla y declarar el límite de la auditoría.
4. Evaluar impacto, riesgos y certeza; entregar recomendaciones concretas priorizadas por utilidad/coste, con condición de aceptación y dependencias. La evidencia insuficiente es incertidumbre, no defecto acreditado.
5. Terminar con el informe. Borrados, staging, fixes, instalación, publicación, mediciones con escritura o hardware necesitan alcance autorizado para una fase de ejecución; no pedir nuevamente una autorización ya explícita, pero no ejecutar esa fase bajo este procedimiento de sólo lectura.

Selección de evidencia, no procedimientos adicionales:

| Frente | Lecturas útiles |
| --- | --- |
| Arquitectura / documentación | Código/tests, enlaces y apartados del contrato; historia sólo como procedencia |
| Git | `git --no-optional-locks status --short`, diff, cached diff, log y show; sin refrescar/escribir el INDEX. Para diff/show desactivar helpers con `--no-ext-diff --no-textconv`. |
| Almacenamiento | Inventario focal, manifests, referencias y owners de retención; sin cleanup |
| Dependencias | Declaraciones/locks y consumidores por búsqueda; no instalar ni importar para enumerarlas |
| Rendimiento | Logs/mediciones existentes, versión, muestra y alcance; sin extrapolar ni correr benchmarks |
