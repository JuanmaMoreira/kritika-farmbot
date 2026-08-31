# Roadmap — Kritika FarmBot 0.2

## Estado cerrado

El vertical slice productivo está cerrado: runtime híbrido, percepción semántica, Runtime Facts OCR/temporales, Black Market, World Boss, `StandardRotation`, sesiones multi-flow, CLI, GUI, cancelación y event stream.

Los checkpoints live incluyen Black Market 28/28, Rotation aislada 28/28 y la primera sesión combinada `Black Market → World Boss → Rotation` 28/28 desde GUI, sin fallos técnicos. Detalles y evolución están en [`docs/HISTORY.md`](docs/HISTORY.md).

La deuda de escalabilidad del evaluator offline quedó cerrada con evaluación incremental detector×frame, invalidación conservadora y full audit explícito; el corpus curado conserva toda su cobertura.

La Fase 2 de Socket Inventory Relief quedó cerrada hardware-free: support operation fuera del registry, Enhance All sólo por GOLD, taps bounded que excluyen flash/`UNKNOWN`, fallback Bulk sólo para ópalo incompatible con level `0` confirmado, retorno exacto y una única rama positiva local a cada ejecución de World Boss. Una segunda aparición usa `No`.

Los smokes HIL cerraron Enhance positivo y No Material + venta segura. La segunda aparición no se forzó porque el usuario confirmó que preparar ese caso extremo no era razonable; queda cubierta por tests y por eventos productivos que registrarán `No` y el fin no fatal si ocurre naturalmente. La rama positiva bounded se considera cerrada.

La rama Equipment Inventory Full quedó cerrada para el caller confirmado World Boss: support operation independiente, orden fijo Transmute → Ethereal condicional → Fuse, acumulación sin short-circuit, animación común mediante `TapThroughAnimation`, postcondiciones por desaparición, retorno exacto y un único intento positivo por `run()`. Una segunda aparición usa el cierre negativo no fatal. No se agregó un flow ni una entrada de GUI/registry.

Daily Quests y Character Mail quedaron cerrados como flows productivos `PER_CHARACTER`, ambos Lobby → Lobby. La selección default termina Daily Quests → Mailbox → Rotation; Claim All es single-attempt, Mailbox conserva leftovers no fatales y no existe ninguna rutina de liberación de espacio. La integración reutiliza el normalizador adquirido World Boss → Quick Menu → Lobby sin modificar la policy de flows anteriores ni `SessionRunner`.

Guild quedó cerrado a nivel de adquisición semántica: shell, Attendance pendiente/completado, transición con bubble independiente, `Lobby → Quick Menu → Guild` y Quick Menu accesible desde Guild. Todavía no existe flow, intent de Attendance, normalizador a Guild ni ampliación del allow-list.

## Próximo trabajo

### Known future

- Implementar `GuildCheckInFlow` con contrato Guild → Guild, no-op explícito cuando Attendance ya está completado, un único tap cuando está activo y completion fresca/estable bounded; añadir después la normalización verificada `Quick Menu → Guild` y sólo entonces incorporar Guild a `quick_menu_accessible`.
- Adquirir semántica del error de conexión post-batalla de World Boss y diseñar su recovery bounded antes de automatizarlo.
- Ampliar retornos de Equipment Inventory Full a otros farming flows sólo con evidencia live específica; por ahora únicamente `Combine → Back → World Boss` está verificado.
- Ampliar retornos de Socket a otros farming flows sólo con evidencia live específica; por ahora únicamente `Socket → Back → World Boss` está verificado.
- Implementar `CharacterContextProvider`/nombre sólo cuando identidad tenga un consumidor concreto.
- Incorporar `ConflictResolver`, recovery transversal, aislamiento de fallos y policy de continuación unattended cuando la evidencia lo requiera.
- Evaluar costo/rank/participation, Auto Repeat y scheduler cuando exista un caso funcional definido.
- Agregar estrategias Rotation identity-aware o MAIN/SUBS sólo si dejan de bastar MRU + `StandardRotation`.
- Hacer polish de UI más adelante; la GUI actual ya es el frontend operativo.
- Evaluar detector entrenado o fallback VLM provider-agnostic sólo ante un caso no cubierto y evidencia suficiente.

## Criterios permanentes de avance

- Mantener `Perception`, flows, Rotation, `ActionExecutor` y ADB separados.
- Promover semántica con evidencia curada y ground truth humano cuando corresponda.
- Verificar postcondiciones observables y permitir retries únicamente desde estado fresco inequívoco; `UNKNOWN` no autoriza input.
- Validar hardware-free antes de smokes físicos. Los smokes rutinarios se ejecutan desde la GUI por el usuario.
