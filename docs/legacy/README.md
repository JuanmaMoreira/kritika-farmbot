# Material legacy preservado

Este directorio conserva conocimiento histórico útil, pero sus archivos no son fuentes activas del estado o la arquitectura.

- `CHANGELOG-legacy.md`: diario detallado de las versiones 0.0.1 a 0.1.2. Conserva decisiones como la migración de BlueStacks/hd-adb a dispositivo USB, el uso de scrcpy y la evolución del modelo de contextos.
- `PROJECT-CONTEXT-legacy.md`: descripción del proyecto anterior a la auditoría. Varias afirmaciones no coinciden con la implementación preservada.
- `migrate_botones.py`: script one-shot que produjo parte de la migración actual de `bot/constants.py`. Se archiva para trazabilidad y no debe ejecutarse como parte del rediseño.

El estado completo anterior a la reorganización puede recuperarse mediante el tag Git `legacy-pre-hybrid`.

Las fuentes documentales activas son `CONTEXT.md`, `ARCHITECTURE.md`, `ROADMAP.md` y `AGENTS.md` en la raíz del repositorio.
