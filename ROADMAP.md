# Roadmap — Kritika FarmBot 0.2

## Estado cerrado

El vertical slice productivo está cerrado: runtime híbrido, percepción semántica, Runtime Facts OCR/temporales, Black Market, World Boss, `StandardRotation`, sesiones multi-flow, CLI, GUI, cancelación y event stream.

Los checkpoints live incluyen Black Market 28/28, Rotation aislada 28/28 y la primera sesión combinada `Black Market → World Boss → Rotation` 28/28 desde GUI, sin fallos técnicos. Detalles y evolución están en [`docs/HISTORY.md`](docs/HISTORY.md).

La deuda de escalabilidad del evaluator offline quedó cerrada con evaluación incremental detector×frame, invalidación conservadora y full audit explícito; el corpus curado conserva toda su cobertura.

La Fase 2 de Socket Inventory Relief quedó cerrada hardware-free: support operation fuera del registry, Enhance All sólo por GOLD, taps bounded que excluyen flash/`UNKNOWN`, fallback Bulk sólo para ópalo incompatible con level `0` confirmado, retorno exacto y una única rama positiva local a cada ejecución de World Boss. Una segunda aparición usa `No`.

## Próximo trabajo

### Immediate next

- Validar mediante HIL los casos live razonablemente reproducibles de la rama positiva Socket Full, sin forzar estados destructivos; antes de la primera venta real debe confirmarse por chat el item preparado.

### Known future

- Adquirir semántica del error de conexión post-batalla de World Boss y diseñar su recovery bounded antes de automatizarlo.
- `popup.world_boss_bag_full` conserva el cierre negativo no fatal; cualquier alivio de ese inventario requiere adquisición y diseño propios.
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
