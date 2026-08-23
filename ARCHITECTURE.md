# Arquitectura — Kritika FarmBot

Este documento distingue el sistema legacy que existe en el repositorio de la arquitectura objetivo 0.2. La segunda sección expresa responsabilidades y límites acordados; no implica que esas capas ya estén implementadas.

## Arquitectura legacy

La implementación preservada sigue aproximadamente este flujo:

```text
main.py
  → flow TOT
    → actions y matching directo
      → estado global de context.py
        → catálogo de constants.py
          → templates y coordenadas
      → antigua API de screen.py (retirada)
```

Responsabilidades reales:

- `bot/constants.py` mezcla configuración de host, resolución, taxonomía, templates, regiones, botones, offsets y políticas aún incompletas.
- `bot/screen.py` implementaba a la vez captura scrcpy, almacenamiento del frame, percepción por templates y comandos ADB. Desde Fase 1E conserva solamente matching OpenCV puro y transicional sobre un frame explícito.
- `bot/context.py` captura un frame y recorre templates hasta encontrar el primer contexto coincidente.
- `bot/actions.py` resuelve botones mediante estado global y coordenadas del catálogo.
- `bot/flows.py` contiene lógica TOT, percepción específica, regiones, thresholds y acciones físicas.
- `bot/ads_manager.py` es un programa standalone basado en UIAutomator2.
- `main.py` no contiene un loop general: conecta el dispositivo e intenta ejecutar exclusivamente TOT.

Problemas estructurales confirmados:

- captura, percepción e input están acoplados;
- el contexto depende directamente de templates;
- actions depende de globals y coordenadas;
- flows contiene percepción y dependencias directas de la API de input retirada;
- la geometría no usa de forma confiable las dimensiones landscape del frame;
- prioridad y outcomes están modelados pero no configurados efectivamente;
- el runtime legacy no es importable en su estado preservado;
- el entry point y sus módulos legacy ya no importan porque siguen solicitando esa API retirada.

El uso de scrcpy, OpenCV o ADB no es por sí mismo legacy. Lo legacy es el acoplamiento que obliga a representar cada estado y transición mediante templates y coordenadas mantenidos manualmente.

## Arquitectura objetivo 0.2

```text
Capture
  ↓
Perception
  ↓
Semantic Observations
  ↓
ContextResolver
  ↓
Flows / Decision
  ↓
ActionExecutor
  ↓
Device / ADB
```

## Fundamentos implementados en Fase 1A

La primera porción implementada de 0.2 permanece desacoplada del runtime legacy:

- `bot/config.py` contiene `RuntimeConfig`, un objeto inmutable para configuración de host y runtime. Puede construirse explícitamente y solo consulta environment o dotenv cuando se invoca `from_env()`; no inicia infraestructura al importarse.
- `bot/geometry.py` contiene conversiones puras de puntos y regiones normalizados. Las dimensiones visuales proceden de `frame.shape`, cuyo orden es `(height, width, ...)`.
- Los puntos representan índices de píxel: usan floor y el extremo normalizado `1` se satura al último índice válido. Las regiones representan límites de slicing con extremo final exclusivo, por lo que la región completa termina en `(width, height)`.
- `adb shell wm size` puede conservarse como metadata, diagnóstico o validación auxiliar, pero no puede decidir la geometría de un frame capturado.

Estos módulos son consumidos por el núcleo 0.2, las herramientas de captura y los helpers visuales transicionales. `constants.py`, `ads_manager.py` y los flows todavía no migraron. La suite automatizada vive exclusivamente en `tests/`; el antiguo directorio `testing/` fue retirado en Fase 1E.

## Composition root y validación real

La Fase 1D añadió `bot/runtime.py` como composition root mínimo. `build_adb_client(config)` y `build_frame_source(config, adb_client=...)` ensamblan el núcleo 0.2 de forma explícita y no ejecutan operaciones externas. La carga de environment/dotenv continúa siendo responsabilidad del caller.

`tools/smoke_capture.py` es una entrada diagnóstica separada de pytest y del runtime legacy. Carga configuración solo dentro de `main()`, comprueba ADB, recibe cinco snapshots distintos y valida ndarray BGR `uint8`, shape, landscape, sequence y timestamps. Usa el context manager de captura y verifica después que el forward utilizado fue retirado.

La validación física con scrcpy-server 3.3.4 confirmó el stack completo con frames `(1224, 2712, 3)`. También cerró una diferencia respecto de la extracción legacy: en H.264, los packets de configuración SPS/PPS se retienen y se anteponen al siguiente media packet antes de enviarlo a PyAV.

### Capture

Obtiene frames landscape desde scrcpy y expone sus dimensiones reales. No reconoce contextos ni toma decisiones.

La Fase 1C implementó esta responsabilidad en `bot/capture.py`. `ScrcpyFrameSource` recibe un `AdbClient` y el path de `scrcpy-server.jar`, prepara el server y el port forwarding, mantiene el proceso ADB y socket, decodifica H.264 con PyAV y publica el frame BGR más reciente. Su API pública es `start()`, `get_frame()`, `stop()`, `is_running`, `failure` y context manager.

Cada `FrameSnapshot` contiene una copia del ndarray, timestamp monotónico y sequence number. Sus dimensiones se consultan desde el shape de esa imagen; la metadata de scrcpy y `adb wm size` no sustituyen esa fuente de verdad. Un `Event` permite cancelar el receptor y los timeouts de socket evitan bloquear el shutdown indefinidamente. Los fallos del thread se conservan y quedan visibles al owner.

La fuente es dueña del lifecycle de socket, decoder, proceso y forward, incluido cleanup best-effort ante startup parcial. `AdbClient` solo construye el proceso persistente mediante `spawn_shell()` y devuelve su handle. Desde Fase 1E es la única implementación activa del protocolo scrcpy: `tools/asset_capture.py` y `tools/screencap_batch.py` la construyen mediante el composition root y no abren sockets, procesos ADB ni decoders propios.

### Perception

Transforma frames en observaciones semánticas. Puede combinar:

- detectores locales y OpenCV para elementos conocidos;
- OCR para valores dinámicos;
- un fallback VLM para estados desconocidos.

El fallback VLM debe permanecer detrás de un límite provider-agnostic. Ninguna capa superior debe depender de un proveedor, API o modelo específico.

### Semantic Observations

La Fase 2A implementó esta frontera mediante contratos inmutables y puramente estructurales:

- `Observation` representa un hecho semántico con nombre namespaced, confianza normalizada, categoría de origen, valor escalar opcional y una `RelativeRegion` opcional.
- `ObservationSource` expresa categorías extensibles (`LOCAL_CV`, `OCR`, `VLM`, `SYSTEM`), no proveedores, modelos, templates ni motores concretos.
- `ObservationValue` se limita a `bool`, `int`, `float`, `str` o `None`; frames, crops y objetos de detector no atraviesan esta frontera.
- `ObservationBatch` asocia una colección ordenada de evidencia con el `sequence` y `timestamp` de un único frame lógico, pero no retiene el ndarray.
- Un batch preserva observaciones repetidas e independientes. `find(name)` devuelve todas y `best(name)` ofrece sólo una conveniencia por confianza reportada; no constituye una política de fusión.

Las ubicaciones permanecen normalizadas en `[0,1]` y con área positiva. `bot/geometry.py` expone `normalize_relative_region()` para compartir esa validación sin convertirlas todavía en targets de acción ni coordenadas pixel.

### ContextResolver

La Fase 2B implementó `bot/resolver.py` como motor puro para transformar un `ObservationBatch` en `ResolvedState`. Se construye con tuplas explícitas de `ContextRule` para contextos base y overlays; no contiene catálogo de Kritika, imports legacy, percepción, IO ni estado temporal.

Una `ContextRule` declara un nombre de resultado, requirements semánticos únicos y un threshold común. Para cada requirement, `match_rule()` consulta la observación de mayor confidence de ese nombre. La fuente y región permanecen disponibles en la evidencia, pero no alteran el resultado. Las confidences no se suman, promedian, votan ni ponderan entre fuentes no calibradas.

Una regla sólo coincide si todos sus requirements alcanzan el threshold inclusivo. El `RuleMatch` diagnóstico conserva la regla y exactamente una observación seleccionada por requirement; su confidence es el mínimo conservador de esas evidencias y no una probabilidad estadística.

La resolución base aplica estas reglas sin first-match ni prioridades:

- cero candidatos producen `UNKNOWN`;
- un candidato produce `RESOLVED`;
- varios candidatos distintos producen `AMBIGUOUS`, aun si sus confidences difieren.

Reglas, candidatos y overlays se normalizan por nombre para que el orden de inyección no decida semántica. Los overlays se evalúan independientemente y todos los que coinciden se conservan, incluso con base `UNKNOWN` o `AMBIGUOUS`; no existe ambigüedad ni prioridad propia de overlays en esta fase.

La Fase 2A sí definió su contrato de salida en `bot/state.py`. `ResolvedState` conserva la identidad `sequence`/`timestamp` del batch y separa:

- `base_context`, que sólo está seleccionado para un resultado `RESOLVED`;
- un `subcontext` opcional y explícito, sin jerarquías arbitrariamente profundas;
- cero o más `overlays`, independientes del contexto base;
- `base_candidates` conflictivos para un resultado `AMBIGUOUS`.

`ResolutionStatus.UNKNOWN` es first-class: la imposibilidad de resolver el contexto base no es una excepción y aun puede coexistir con overlays conocidos. La policy de subcontexto permanece pendiente y el resolver de 2B produce siempre `subcontext=None`. Tampoco implementa hysteresis, debounce, historial, transiciones ni voting entre frames.

### Catálogo semántico mínimo

La Fase 2C añadió `bot/catalog.py` como configuración semántica productiva separada del motor genérico. Su API pública es `BASE_CONTEXT_RULES`, `OVERLAY_RULES`, `SEMANTIC_OBSERVATION_NAMES` y `build_default_resolver()`. No importa `constants.py`, assets ni capas de percepción.

El primer slice contiene cuatro bases y un overlay:

| Resultado semántico | Tipo | Requirement | Referencia legacy | Región legacy | Threshold legacy |
|---|---|---|---|---|---|
| `screen.lobby` | base | `landmark.lobby_header` | `lobby` / `assets/ui/lobby-id.png` | `(0.2039, 0.0302, 0.2434, 0.0899)` | `0.85` |
| `screen.character_select` | base | `landmark.character_select_header` | `select-character` / `assets/ui/select-character-id.png` | `(0.3971, 0.0417, 0.6036, 0.134)` | `0.85` |
| `screen.survival` | base | `landmark.survival_title` | `survival` / `assets/ui/survival-id.png` | `(0.1707, 0.2337, 0.2994, 0.2974)` | `0.85` |
| `screen.black_market` | base | `landmark.black_market_title` | `black-market` / `assets/ui/black-market-id.png` | `(0.4395, 0.0997, 0.5579, 0.1495)` | `0.85` |
| `popup.black_market_purchase_confirmation` | overlay | `landmark.black_market_purchase_dialog` | `black-market-purchase-confirmation` / `assets/ui/black-market-purchase-confirmation-id.png` | `(0.4624, 0.4828, 0.5376, 0.5294)` | `0.85` |

Esta tabla es trazabilidad histórica, no configuración runtime. Los landmarks describen señales visibles; no prescriben template matching y podrían provenir de cualquier backend futuro.

Todas las `ContextRule` usan `SEMANTIC_CONFIDENCE_THRESHOLD = 0.80`. Es una policy uniforme y provisional sobre confidence reportada, distinta del threshold de matching legacy de la tabla. No existe calibración visual hasta validar assets y screencaps en 2D/3.

Las cinco rules tienen conjuntos mínimos de evidence distintos y por ello no generan solapamiento estructural. Proporcionar simultáneamente landmarks de dos bases sigue produciendo `AMBIGUOUS`, como exige el resolver. El overlay de confirmación coexiste con `screen.black_market` y no reemplaza la base.

TOT no se incorporó: aunque `flow_tot()` consume `lobby → survival → tot`, los assets `tot-id.png` y sus subcontextos físicos/mágicos no están entre los assets runtime activos y la entrada conserva coordenadas pixel legacy. `bag-full-alert` tampoco se incorporó porque su comentario legacy cuestiona si representa siempre el mismo tipo de inventario lleno. No se inventaron señales para cubrir esos huecos.

### Flows / Decision

Contienen intención y reglas de negocio deterministas. Solicitan acciones semánticas y reaccionan a estados resueltos; no hacen template matching ni llaman a ADB.

### ActionExecutor

Traduce una intención de acción validada a interacción con el dispositivo. La resolución geométrica debe usar el frame landscape real y coordenadas normalizadas en `[0,1]` cuando corresponda.

### Device / ADB

Es el límite de infraestructura para taps, swipes y demás comandos del dispositivo. Debe poder sustituirse por un fake en tests normales.

La Fase 1B implementó este límite en `bot/adb.py`. `AdbClient` recibe explícitamente el ejecutable ADB y el serial, y concentra la ejecución en primitivas `subprocess` con argumentos separados, timeout y traducción a `AdbError`/`AdbTimeoutError`. Expone `get_state`, `shell`, input en coordenadas pixel, push y administración de port forwarding. La extensión `spawn_shell()` de Fase 1C crea un proceso persistente sin apropiarse de su lifecycle.

`AdbClient` no conoce frames, resolución, coordenadas relativas, percepción ni acciones semánticas. Puede construirse desde los campos ADB de `RuntimeConfig`, pero no retiene configuración de scrcpy o del juego. Desde Fase 1E es el único límite activo de procesos ADB; `bot/screen.py` ya no captura, conecta ni ejecuta taps o swipes.

## Cierre del núcleo reutilizable — Fase 1E

`bot/screen.py` permanece con nombre legacy solo como módulo transicional de visión. Expone `find_image_on_screen()` y `find_all_on_screen()`, recibe el ndarray explícitamente, calcula regiones normalizadas desde `frame.shape` y no consulta globals, dispositivo ni configuración. La política de escalado/selección de templates queda deliberadamente para Perception en Fase 2/3.

Los consumers legacy `main.py`, `bot/context.py`, `bot/actions.py` y `bot/flows.py` conservan imports de captura/input ya retirados. No se añadieron shims: no forman parte del runtime activo y repararlos implicaría migrar resolución semántica, ejecución de acciones y flows fuera del alcance de Fase 1. El tag `legacy-pre-hybrid` conserva su implementación anterior.

Las herramientas activas quedan delimitadas así:

- `tools/smoke_capture.py`: diagnóstico opt-in sin escritura de frames ni input físico;
- `tools/screencap_batch.py`: adquisición interactiva de capturas mediante `ScrcpyFrameSource`;
- `tools/asset_capture.py`: curación de templates/regiones desde carpeta o desde la misma fuente 0.2.

`tools/debug_context.py` y `testing/` fueron retirados porque duplicaban captura, dependían del modelo de contexto legacy o contenían IDs/acciones manuales cubiertas por herramientas vigentes. No se migró percepción ni gameplay.

## AdsManager

Los anuncios pertenecen a aplicaciones o packages externos y se inspeccionan mediante UIAutomator2:

```text
external ad detected
  ↓
AdsManager / UIAutomator2
  ↓
return to game
```

AdsManager es una interrupción externa separada de Perception y ContextResolver. Su resultado relevante para el bot principal es recuperar el control y volver al juego.

## Estrategia de migración

La migración será incremental. Se extraerán primero captura, dispositivo y contratos testeables; después se incorporarán el modelo semántico y casos de percepción concretos. Los templates y flows legacy se reutilizarán únicamente cuando aporten evidencia o conocimiento de negocio verificable.
