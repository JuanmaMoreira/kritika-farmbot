# Changelog

Este archivo registra únicamente milestones, migraciones, releases y capacidades relevantes. El diario histórico anterior al rediseño se conserva en `docs/legacy/CHANGELOG-legacy.md`.

## Unreleased

### Added

- Se estableció la Fase 1A del núcleo 0.2: baseline automatizado con pytest, configuración de runtime explícita y geometría visual derivada exclusivamente del frame real.
- Se añadió en Fase 1B un adaptador ADB explícito, testeable sin hardware y desacoplado de geometría, percepción y lógica de negocio.

### Changed

- Se preservó el estado legacy previo al rediseño en el tag `legacy-pre-hybrid`.
- Se estableció la dirección arquitectónica híbrida 0.2: captura, percepción, observaciones semánticas, resolución de contexto, flows y ejecución de acciones como responsabilidades separadas.
- Se reorganizó la documentación activa alrededor de `AGENTS.md`, `CONTEXT.md`, `ARCHITECTURE.md` y `ROADMAP.md`.
- Los assets runtime dejaron de quedar ocultos por una regla global para imágenes.

### Preserved

- La taxonomía y migración parcial contenidas en `bot/constants.py`.
- El AdsManager basado en UIAutomator2 como subsistema separado.
- Los assets históricos `960x540` y las 173 screencaps como material legacy fuera del Git normal.
