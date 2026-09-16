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

`clean Lobby` significa `RESOLVED screen.lobby + overlays vacíos`. Discovery,
recovery y postcondiciones de sesión observan globalmente. Una transición
conocida a Lobby puede usar un observer resolver-complete: incluye todas las
dependencias de bases y overlays del catálogo, por lo que conserva blockers,
bases foreign y `AMBIGUOUS`, aunque omite readers que no alimentan resolución.
Source, acción, freshness, retry y recovery siguen perteneciendo al caller. Ver
[`docs/CLEAN_LOBBY_B2_DECISION.md`](docs/CLEAN_LOBBY_B2_DECISION.md).

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

`VerifiedTransitionResult.action_source_snapshot` publica el snapshot que autorizó el último input cuyo executor terminó normalmente, incluyendo el source actualizado tras retry o recovery de precondition. Sin input, o si el executor falla de forma incierta, no publica anchor. `recovery_after_action` distingue cleanup ocurrido después del input y prohíbe convertir su éxito posterior en nuevo handoff. Un callback local `on_recovery` se ejecuta cuando recovery devuelve un snapshot fresco, antes de evaluar un retry; permite invalidar provenance de una operación sin estado global.

Quick Menu separa visibilidad de autorización. Un tile sólo usa el handoff local `QuickMenuHandoff` creado con source del input `RESOLVED`, limpio y permitido para esa operación, menú posterior fresco y base no contradictorio. `UNKNOWN + menu.quick` puede observarse después de abrirlo: el input del tile se autoriza por ese lineage explícito y el overlay fresco, nunca por UNKNOWN aislado. `AMBIGUOUS`, base foreign, pérdida observada del menú o recovery invalidan el handoff y prohíben retry; una espera pasiva por el destino puede continuar. Layout proviene del source verificado y geometría del frame fresco. Discovery/recovery sin handoff permanece fail-closed; `ContextResolver` no conserva origen temporal.

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

Los hot paths deberían evaluar sólo evidencia relevante para el estado y la operación actuales. Rotation R1 acota exclusivamente la verificación de `select_predecessor_character` con `ScopeSpec` y `scoped_transition_for`: el reader amarillo local sigue sobre el frame crudo. Rotation R2-A reutiliza ese subset de dos detectores mediante `scoped_observer_for` sólo en el wait post-swipe de Character Select; `stable_for=1.0`, sentinel posterior, frames, geometría y estrategia de scroll conservan sus contratos. B2 acota los retornos conocidos a Lobby de 95 a 77 detectores con vocabulario resolver-complete; no recorta bases u overlays sin evidencia física. Discovery, recovery y postcondiciones de sesión permanecen globales. La expansión será de un flow o hot path por vez, con benchmark y smoke antes de ampliar alcance.

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
