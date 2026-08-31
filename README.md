# Kritika FarmBot

Kritika FarmBot es un proyecto de automatización para **Kritika: The White Knights** sobre un dispositivo Android físico conectado por USB.

El runtime híbrido 0.2 productivo ejecuta actualmente Black Market, World Boss, Send Stamina, Daily Quests, Mailbox, Guild Check-In y rotación standard mediante contratos semánticos verificados. El código legacy se conserva sólo como conocimiento histórico.

## Dirección 0.2

El runtime usa scrcpy como fuente de frames, percepción local/OCR, flows deterministas y ADB como único límite de input. `FlowRegistry`, `SessionPlan`, la composición productiva, la cancelación y el event stream son compartidos por CLI y GUI; ningún frontend contiene business logic.

## Plataforma y requisitos básicos

- Python 3.10 o superior.
- Dispositivo Android físico en landscape.
- Depuración USB habilitada.
- `.env` configurado con el serial del dispositivo.
- `AGENT_LOCAL.md` configurado con Python, ADB y scrcpy-server locales.

La preparación del entorno está documentada en [docs/setup.md](docs/setup.md). `main.py` sigue siendo legacy; la GUI y los comandos manuales son los entrypoints productivos.

## GUI operacional

Abrir desde la raíz del repositorio:

```powershell
.\tools\agent_run.ps1 tools.gui
```

En Windows también se puede abrir con doble clic sobre `Kritika FarmBot.cmd` en la raíz del proyecto. Es un launcher provisional mínimo: inicia el mismo `tools.gui` mediante el entorno local configurado y no contiene lógica del bot.

La lista de flows procede directamente de `FlowRegistry`. Seleccionar una fila y usar `Enable / Disable`, `↑ Up` y `↓ Down`; una sesión conserva exactamente el orden visible de los flows activos. `Run Flow Once` exige un único flow activo y no rota. `Run Session` usa todos los flows activos, `SessionPlan`, `SessionRunner` y el número positivo de Characters; el default es 28.

`Run Session` muestra un contador monotónico `HH:MM:SS`, reseteado por cada sesión y congelado en su duración final. `Stop Safely` solicita el mismo token de cancelación que la CLI y no mata threads; el contador sigue hasta el resultado `CANCELLED`. Durante una ejecución, los controles de configuración quedan bloqueados. Si se intenta cerrar la ventana, la GUI ofrece solicitar la parada segura y espera el boundary antes de salir.

La Debug Console muestra eventos en vivo con timestamp, nivel, componente y campos estructurados; Debug Mode agrega facts OCR, transiciones, retries y telemetría de waits. `Clear`, `Copy selected` y `Copy all` sólo modifican la vista. El log persistente completo siempre queda bajo `logs/` y su path aparece en Status / Progress.

## Ejecución manual por CLI

Ejecutar desde la raíz del repositorio. El wrapper resuelve el Python, ADB y scrcpy-server registrados localmente, sin asumir que están en `PATH`.

```powershell
# Ver los flows productivos disponibles
.\tools\agent_run.ps1 tools.run_flow --list-flows

# Ejecutar una vez sobre el personaje actual
.\tools\agent_run.ps1 tools.run_flow black_market
.\tools\agent_run.ps1 tools.run_flow world_boss --debug
.\tools\agent_run.ps1 tools.run_flow send_stamina
.\tools\agent_run.ps1 tools.run_flow daily_quests
.\tools\agent_run.ps1 tools.run_flow mailbox
.\tools\agent_run.ps1 tools.run_flow guild_check_in

# Ejecutar una sesión; el orden escrito se conserva
.\tools\agent_run.ps1 tools.run_session black_market world_boss send_stamina daily_quests mailbox guild_check_in --characters 2

# Sin --characters se usa el default productivo actual: 28
.\tools\agent_run.ps1 tools.run_session black_market world_boss send_stamina daily_quests mailbox guild_check_in --debug
```

La consola normal muestra `INFO`, `WARNING` y `ERROR`; `--debug` agrega facts OCR, transiciones, grace/retries y telemetría de `ControlledWait`. Cada ejecución crea un `.log` estructurado bajo `logs/`, con timestamp e id de sesión. No se guardan frames.

`Ctrl+C` solicita cancelación segura; pulsarlo una segunda vez fuerza la interrupción. El resumen final distingue `COMPLETED`, `FAILED` y `CANCELLED`. Exit codes: `0` completado, `1` fallo del flow/sesión, `2` argumentos/config/runtime inválidos y `130` cancelado.

El usuario debe dejar el personaje actual en la precondición declarada o en un contexto que el normalizador soporte explícitamente. La selección default ubica Send Stamina antes de Daily Quests, seguida por Mailbox y Guild Check-In. Si World Boss termina en su pantalla principal, el boundary de precondiciones usa la ruta adquirida `World Boss → Quick Menu → Lobby`; Guild usa acceso directo desde Lobby o Quick Menu desde contextos compatibles. Una sesión rota exactamente una vez después de los flows de cada personaje, incluido el último retorno que cierra el ciclo.

## Documentación

- [CONTEXT.md](CONTEXT.md): snapshot del sistema productivo actual y limitaciones vigentes.
- [ARCHITECTURE.md](ARCHITECTURE.md): componentes, contratos y límites 0.2 vigentes.
- [ROADMAP.md](ROADMAP.md): próximo trabajo y futuro conocido.
- [docs/HISTORY.md](docs/HISTORY.md): cronología, calibraciones y checkpoints cerrados (cold context).
- [CHANGELOG.md](CHANGELOG.md): milestones relevantes.
- [AGENTS.md](AGENTS.md): reglas operativas permanentes para Codex.
- [docs/legacy/](docs/legacy/): documentación e instrumentos históricos preservados.

El estado inmediatamente anterior a esta reorganización está preservado en el tag Git `legacy-pre-hybrid`.
