# Kritika FarmBot

Kritika FarmBot es un proyecto de automatización para **Kritika: The White Knights** sobre un dispositivo Android físico conectado por USB.

El proyecto se encuentra en transición hacia la versión híbrida 0.2. El runtime legacy combina scrcpy, OpenCV, templates, coordenadas y ADB, pero actualmente no debe considerarse funcional ni robusto: la auditoría de la Fase 0A encontró contratos incompatibles, geometría legacy y ausencia de tests automatizados.

## Dirección 0.2

El rediseño conservará scrcpy como fuente de frames y ADB como mecanismo final de interacción. La percepción combinará detectores locales, OCR y un fallback VLM intercambiable, produciendo observaciones semánticas para un resolvedor de contexto y flows deterministas.

Esta arquitectura todavía no está implementada.

## Plataforma y requisitos básicos

- Python 3.10 o superior.
- Dispositivo Android físico en landscape.
- Depuración USB habilitada.
- `adb` disponible en `PATH`.
- `scrcpy-server.jar` para la captura legacy preservada.

La preparación del entorno está documentada en [docs/setup.md](docs/setup.md). La ejecución de `main.py` no constituye actualmente un procedimiento validado.

## Documentación

- [CONTEXT.md](CONTEXT.md): estado real, decisiones cerradas y limitaciones vigentes.
- [ARCHITECTURE.md](ARCHITECTURE.md): arquitectura legacy y dirección objetivo 0.2.
- [ROADMAP.md](ROADMAP.md): trabajo futuro por fases.
- [CHANGELOG.md](CHANGELOG.md): milestones relevantes.
- [AGENTS.md](AGENTS.md): reglas operativas permanentes para Codex.
- [docs/legacy/](docs/legacy/): documentación e instrumentos históricos preservados.

El estado inmediatamente anterior a esta reorganización está preservado en el tag Git `legacy-pre-hybrid`.
