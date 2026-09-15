# Arquitectura — Kritika FarmBot 0.2

Este documento define contratos vigentes y dirección aceptada. El estado observable está en [`CONTEXT.md`](CONTEXT.md), la secuencia de trabajo en [`ROADMAP.md`](ROADMAP.md) y las alternativas históricas en [`docs/HISTORY.md`](docs/HISTORY.md).

## Arquitectura implementada

```text
Capture
  → Perception ───────────────┐
  → Runtime Facts ────────────┤
                              ▼
                       ContextResolver
                              ▼
 Flow / Support Operation / SessionRunner / Rotation
                              ▼
                  verified semantic operation
                              ▼
                       ActionExecutor
                              ▼
                         AdbClient
```

Los facts demand-driven pueden llegar directamente al consumidor cuando parten de un snapshot context-correct. Las operaciones verificadas coordinan observación y ejecución sin fusionar sus responsabilidades.

### Capture

`ScrcpyFrameSource` obtiene frames BGR con sequence y timestamp. Posee proceso, socket, decoder y cleanup. No reconoce pantallas ni contiene policy.

### Perception y facts

`PerceptionEngine` aplica detectores semánticos a un frame y emite observaciones, no decisiones. Los módulos específicos encapsulan templates, OCR y reglas de evidencia.

`RuntimeFactReader` calcula OCR tipado sólo cuando un consumidor lo solicita. `TemporalObserver` agrega evidencia multiframe para estados que no son seguros en una captura, como Auto Battle.

### Resolución y observación runtime

`ContextResolver` es puro y determinista: combina contexto base y overlays y devuelve `RESOLVED`, `UNKNOWN` o `AMBIGUOUS`. No captura, no acciona y no conserva policy de flows.

`RuntimeObserver` crea snapshots coherentes de frame, observaciones, estado, facts y geometría. Las esperas exigen secuencias frescas, timeout, estabilidad cuando corresponde y cancelación explícita.

### Intención y policy

- **Flows:** contienen intención de negocio, gates, outcomes y orden de operaciones.
- **Support operations:** resuelven una obstrucción concreta y vuelven al caller conocido; no son flows ni recovery general.
- **`BattleModeZone`:** comparte entrada/normalización del hub entre actividades sin absorber su gameplay.
- **`SessionRunner`:** compone flows habilitados, proyecta resultados y aplica policy de sesión.
- **Rotation:** cambia de personaje de forma transversal; no ejecuta flows.
- **Eligibility e Identity:** aportan contexto y skips, pero no seleccionan estrategia.

La lista productiva sigue siendo explícita y ordenada. La GUI configura esa lista; no contiene lógica de negocio.

### Operaciones verificadas

`VerifiedTransition` modela precondición, una acción y postcondición observable. Una falla no se convierte en éxito por demora ni por desaparición ambigua.

Todo retry es:

1. bounded;
2. autorizado por un estado fresco;
3. específico de la acción que se repite;
4. cancelable.

`UNKNOWN` y contradicciones fallan cerrados. Cuando no existe una señal robusta, la policy debe ser conservadora y quedar documentada.

### Ejecución física

`ActionExecutor` traduce intents validados a taps, swipes o texto usando geometría derivada de `frame.shape`. No reconoce pantallas ni decide qué jugar, comprar o vender.

`AdbClient` es el único límite activo de ADB. Ningún flow llama ADB directamente.

### Observabilidad y frontends

Structured Observability registra eventos tipados. Failure Evidence conserva contexto diagnóstico acotado. SessionReport resume outcomes de flows, personajes y sesión.

CLI y GUI construyen el mismo runtime. La UI permite selección, orden, ejecución y cancelación; no modifica contratos internos.

## Invariantes

```text
Perception != Policy
ContextResolver != Capture or Input
Flow != ActionExecutor
Rotation != Flow
GUI != Business Logic
ActionExecutor != Verification
AdbClient == sole ADB boundary
```

- Configuración se carga de forma explícita e import-safe.
- Paths locales, seriales y resoluciones no se versionan ni hardcodean.
- Lifecycle y cleanup pertenecen al dueño del recurso.
- Recovery devuelve a un estado conocido; la sesión decide si continúa.
- Ads permanece desacoplado de la percepción normal del juego.

## Filosofía de producto

La persona usuaria es el planner: decide objetivo, orden de flows y configuración. El bot ejecuta operaciones deterministas, pequeñas y verificables. Nuevas abstracciones sólo se incorporan cuando existe un consumidor y evidencia causal; nombres como Sequence, Loop o Condition son posibilidades de composición, no componentes actuales.

## Dirección aceptada, aún no completamente implementada

### Percepción acotada incremental

Los hot paths deberían evaluar sólo evidencia relevante para el estado y la operación actuales. Rotation R1 acota exclusivamente la verificación de `select_predecessor_character` con `ScopeSpec` y `scoped_transition_for`: el reader amarillo local sigue sobre el frame crudo, y post-swipe, confirmación a Lobby y recovery permanecen globales. La percepción más amplia queda para descubrimiento, recovery y evaluación. La expansión será de un flow o hot path por vez, con benchmark y smoke antes de ampliar alcance.

Esta dirección conserva el principio demostrado por el experimento, pero no adopta sus APIs, planes léxicos ni acoplamientos con Inventory Relief.

### Navegación de listas largas

Para una lista ordenada y estable, la primitiva futura aceptable es:

```text
catálogo conocido + landmark visible + target conocido
  → estimar desplazamiento
  → gesto acotado
  → reobservar
  → corrección bounded o stop
```

No se acepta navegación ciega, conteo indefinido de swipes ni taps sobre filas parciales.

### Relief por presión de recursos

Una futura Inventory Relief debe separarse del gameplay y activarse sólo por causalidad demostrada: blocker fresco, caller conocido y recurso concreto. Cada operación verifica progreso y retorno. Umbrales, orden de conversiones y ventas requieren evidencia propia; no se heredan automáticamente del experimento.

### Expansión funcional

Nuevos flows deben reutilizar límites existentes, definir entrada/salida, outcomes y eligibility, y cerrar primero un slice simple. Tower y Arena quedan después de estabilizar percepción acotada e Inventory Relief mínima.

## Arquitectura no aceptada

No pertenecen al baseline ni a la dirección comprometida:

- el runtime experimental completo de Inventory Relief;
- un framework general de input lifecycle/readiness;
- retries basados en sleeps o en lentitud accidental de percepción;
- percepción global costosa como mecanismo para esperar que la UI sea interactiva;
- planner automático, navigation graph general o recovery anticipado sin caso demostrado.

Las lecciones y coordenadas de esa línea se preservan en [`docs/HISTORY.md`](docs/HISTORY.md).
