# Material legacy preservado

Este directorio conserva conocimiento histórico útil, pero sus archivos no son fuentes activas del estado o la arquitectura.

- `CHANGELOG-legacy.md`: diario detallado de las versiones 0.0.1 a 0.1.2. Conserva decisiones como la migración de BlueStacks/hd-adb a dispositivo USB, el uso de scrcpy y la evolución del modelo de contextos.
- `PROJECT-CONTEXT-legacy.md`: descripción del proyecto anterior a la auditoría. Varias afirmaciones no coinciden con la implementación preservada.
- `migrate_botones.py`: script one-shot que produjo parte de la migración actual de `bot/constants.py`. Se archiva para trazabilidad y no debe ejecutarse como parte del rediseño.

El estado completo anterior a la reorganización puede recuperarse mediante el tag Git `legacy-pre-hybrid`.

Las fuentes documentales activas son `CONTEXT.md`, `ARCHITECTURE.md`, `ROADMAP.md` y `AGENTS.md` en la raíz del repositorio.

## Snapshot de consolidación 2026-10-14

[CONTEXT_PRE_CONSOLIDATION_20261014](CONTEXT_PRE_CONSOLIDATION_20261014.md) conserva
el diario íntegro sobre `7f80a184`, incluidas las 197 líneas pendientes. Su estado,
conteos y frases de publicación son históricos; el [índice reconciliado](../HISTORY.md#consolidación-documental-2026-10-14)
relaciona los nueve bloques nuevos con los contratos y commits productivos.

[DOC_RESET_20260925](DOC_RESET_20260925.md) preserva documentos completos en fences:
sus enlaces internos son literales relativos al archivo original, no enlaces
activos de `docs/legacy/`. No reinterpretar snapshots como estado vigente.

Auditorías, adquisiciones y campañas fechadas que permanecen en `docs/` también
son historia para estado/validación; [HISTORY](../HISTORY.md) las indexa sin mover
archivos ni romper referencias. Sus USER_GT/evidencias mantienen procedencia.
Los nueve scripts locales Summon Pet/Arena/Gold archivados en fase11 no son
componentes productivos ni dependencias portables; no se requiere su ubicación
absoluta para consultar contratos o ejecutar el bot.
