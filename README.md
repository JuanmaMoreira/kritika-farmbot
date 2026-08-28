# Kritika FarmBot

Kritika FarmBot es un proyecto de automatización para **Kritika: The White Knights** sobre un dispositivo Android físico conectado por USB.

El runtime híbrido 0.2 productivo ejecuta actualmente Black Market, World Boss y rotación standard mediante contratos semánticos verificados. El código legacy se conserva sólo como conocimiento histórico.

## Dirección 0.2

El runtime usa scrcpy como fuente de frames, percepción local/OCR, flows deterministas y ADB como único límite de input. `FlowRegistry`, `SessionPlan`, la composición productiva, la cancelación y el event stream son compartidos por los entrypoints y por la futura GUI; esa GUI no está implementada todavía.

## Plataforma y requisitos básicos

- Python 3.10 o superior.
- Dispositivo Android físico en landscape.
- Depuración USB habilitada.
- `.env` configurado con el serial del dispositivo.
- `AGENT_LOCAL.md` configurado con Python, ADB y scrcpy-server locales.

La preparación del entorno está documentada en [docs/setup.md](docs/setup.md). `main.py` sigue siendo legacy; los comandos productivos son los siguientes.

## Ejecución manual

Ejecutar desde la raíz del repositorio. El wrapper resuelve el Python, ADB y scrcpy-server registrados localmente, sin asumir que están en `PATH`.

```powershell
# Ver los flows productivos disponibles
.\tools\agent_run.ps1 tools.run_flow --list-flows

# Ejecutar una vez sobre el personaje actual
.\tools\agent_run.ps1 tools.run_flow black_market
.\tools\agent_run.ps1 tools.run_flow world_boss --debug

# Ejecutar una sesión; el orden escrito se conserva
.\tools\agent_run.ps1 tools.run_session black_market world_boss --characters 2

# Sin --characters se usa el default productivo actual: 28
.\tools\agent_run.ps1 tools.run_session black_market world_boss --debug
```

La consola normal muestra `INFO`, `WARNING` y `ERROR`; `--debug` agrega facts OCR, transiciones, grace/retries y telemetría de `ControlledWait`. Cada ejecución crea un `.log` estructurado bajo `logs/`, con timestamp e id de sesión. No se guardan frames.

`Ctrl+C` solicita cancelación segura; pulsarlo una segunda vez fuerza la interrupción. El resumen final distingue `COMPLETED`, `FAILED` y `CANCELLED`. Exit codes: `0` completado, `1` fallo del flow/sesión, `2` argumentos/config/runtime inválidos y `130` cancelado.

El usuario debe dejar el personaje actual en la precondición declarada. Los flows vigentes parten de Lobby. Una sesión rota exactamente una vez después de los flows de cada personaje, incluido el último retorno que cierra el ciclo.

## Documentación

- [CONTEXT.md](CONTEXT.md): estado real, decisiones cerradas y limitaciones vigentes.
- [ARCHITECTURE.md](ARCHITECTURE.md): arquitectura legacy y dirección objetivo 0.2.
- [ROADMAP.md](ROADMAP.md): trabajo futuro por fases.
- [CHANGELOG.md](CHANGELOG.md): milestones relevantes.
- [AGENTS.md](AGENTS.md): reglas operativas permanentes para Codex.
- [docs/legacy/](docs/legacy/): documentación e instrumentos históricos preservados.

El estado inmediatamente anterior a esta reorganización está preservado en el tag Git `legacy-pre-hybrid`.
