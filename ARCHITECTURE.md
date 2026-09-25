# Arquitectura — contratos estables

`IMPLEMENTATION_CONTRACT`. [GAMEPLAY_GT](docs/GAMEPLAY_GT.md) define la UI física; [CONTEXT](CONTEXT.md) declara wiring y divergencias actuales; [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md) concentra composición económica. Los nombres técnicos base/overlay del resolver no son la clasificación física canónica.

## Flujo y ownership

```text
Capture → Perception / Runtime Facts → ContextResolver
        → RuntimeObserver snapshot → Flow / support operation / SessionRunner
        → operación semántica verificada → ActionExecutor → AdbClient
```

| Owner | Responsabilidad y límite |
| --- | --- |
| ScrcpyFrameSource | Captura y cleanup de sus recursos |
| PerceptionEngine y readers | Observaciones/facts semánticos; nunca navegación o negocio. OCR demand-driven para datos necesarios |
| ContextResolver | Resolución pura y determinista: RESOLVED / UNKNOWN / AMBIGUOUS; no captura, input ni policy temporal |
| RuntimeObserver / TemporalObserver | Snapshot coherente de frame, secuencia, tiempo, observaciones, facts y geometría; evidencia multiframe sólo donde hace falta |
| Flow / activity | Intención de negocio, gates, outcomes y composición de operaciones; sin CV/ADB directos |
| Support operation | Relief concreto y retorno caller-specific; no planner ni recovery general |
| BattleModeZone / PreparedActivity | Entrada/salida del hub y binding de actividad; sin gameplay o policy de inventario |
| SessionRunner / Rotation | Orden explícito y policy de sesión / cambio transversal de personaje |
| Eligibility / Identity | Contexto y skips; no estrategia automática |
| VerifiedTransition | Precondición, acción, efecto esperado; retry bounded y guardado con evidencia fresca |
| ActionExecutor / AdbClient | Intent validado → input según frame.shape / único límite activo ADB |
| CLI / GUI / observabilidad | Configuración, ejecución, cancelación y reporte; no policy de negocio |

El usuario selecciona objetivos/orden. La sesión comparte zona sólo entre actividades preparadas consecutivas compatibles, sin reordenar. Failure/cancelación no dispara navegación ciega en un finally. AdsManager permanece separado de percepción normal.

## Observación y autorización

Hot paths consultan evidencia relevante; discovery/recovery pueden observar ampliamente. Scopes deben conservar contradicciones/blockers relevantes al contrato, no sólo el destino esperado. Clean Lobby significa `RESOLVED screen.lobby` sin overlays; su implementación resolver-complete no prescribe clasificar físicamente todo el catálogo como BASE.

Estado UNKNOWN/AMBIGUOUS aislado nunca autoriza input. Un handoff local puede conservar el source verificado de una acción efectiva y autorizar sólo el siguiente control conocido bajo overlay fresco compatible. Quick Menu y entradas WB emplean ese contrato; no crean bases sintéticas ni estado global en el resolver. Base foreign, contradicción, pérdida observada o recovery invalidan el permiso de retry. Una espera pasiva posterior a input efectivo no equivale a nueva autorización.

`VerifiedTransitionResult.action_source_snapshot` identifica el último source cuyo executor terminó normalmente; `recovery_after_action` impide fabricar un handoff desde cleanup. Geometría siempre del frame fresco. Retry específico, bounded, cancelable y autorizado para **esa** acción; no por sleeps, timeout o baja velocidad de percepción.

Verificar el efecto con señal fiable suficiente. Identidad de contexto se separa de datos económicos; postcondiciones no se convierten en revalidación de cada hecho GT. Landmarks y oclusión siguen GAMEPLAY_GT. Ausencia ambigua de popup no prueba por sí sola éxito o retorno limpio.

## Navegación y economía

Rutas concretas respetan caller/Back de GAMEPLAY_GT. El caller posee su retorno y la intención que reanuda; no hay navigation graph general. Quick Menu usa origen verificado; Lobby no es un hub obligatorio. Relieves vuelven al caller antes de otro cambio de BASE.

- El planner de recursos es puro; el board describe, cada capacidad decide/ejecuta dentro de su operación con facts frescos. El executor de ruta consume un plan, no replantea por su cuenta.
- Economic owners verifican identidad, cantidad, moneda, límites y efecto. No imputar saldos desde acciones previas. Karats no se gastan mediante fallback implícito.
- Equipment Sell requiere autorización+candidato explícitos, confirm único y Item Count decreciente. Composer conserva request causal, Combine primero y Sell sólo si sigue lleno y existe plan autorizado; sin scan ni retry destructivo. Su existencia no prueba wiring de un caller.
- Recovery vuelve a estado conocido; la sesión decide cómo continuar con el resultado. Los límites concretos de MW/Craft/Keys están en RESOURCE_ROUTING.

Configuración import-safe y explícita; paths/seriales locales fuera de código portable. Cleanup de source/proceso/socket/forward pertenece a su owner. No incorporar lifecycle frameworks, planners generales o abstracciones preventivas sin necesidad real conforme a AGENTS.
