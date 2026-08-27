# Arquitectura — Kritika FarmBot 0.2

Este documento define componentes, contratos, data flow e invariantes vigentes. El estado implementado está en [`CONTEXT.md`](CONTEXT.md); los antecedentes están en [`docs/HISTORY.md`](docs/HISTORY.md).

## Data flow runtime

```text
Capture
  ↓
Perception
  ↓
Semantic Observations / Runtime Facts
  ↓
ContextResolver
  ↓
Flow
  ↓
Semantic Actions
  ↓
ActionExecutor
  ↓
AdbClient
```

Invariantes centrales:

```text
Rotation ≠ Flow
Flow ≠ ActionExecutor
ActionExecutor ≠ Perception
```

- Perception observa; no navega ni decide gameplay.
- El resolver interpreta evidencia; no captura ni ejecuta acciones.
- Un flow decide según estado/facts y solicita intents; no hace matching ni llama ADB.
- `ActionExecutor` conoce targets y geometría; no reconoce pantallas ni aplica policy de negocio.
- `AdbClient` conoce comandos físicos; no conoce frames ni semántica.

## Configuración y composition root

`bot/config.py` define `RuntimeConfig` inmutable. La construcción explícita no lee environment; `RuntimeConfig.from_env()` lo hace sólo cuando el caller lo solicita. Rutas locales y seriales no se hardcodean.

`bot/runtime.py` ensambla `RuntimeConfig → AdbClient → ScrcpyFrameSource` sin iniciar infraestructura durante imports o construcción. Los tools y futuros entry points poseen el lifecycle de la composición.

Toda geometría visual deriva de `frame.shape` en orden `(height, width, ...)`. Los puntos normalizados representan índices de píxel; las regiones usan límite final exclusivo. `adb wm size` puede ser diagnóstico, nunca fuente de geometría de captura.

## Capture

`bot/capture.py` implementa `ScrcpyFrameSource` como única captura activa 0.2. Recibe un `AdbClient` y el path de scrcpy-server, prepara push/forward, proceso, socket y decoder PyAV, y publica el último frame BGR.

`FrameSnapshot` contiene copia del ndarray, sequence y timestamp monotónico. La fuente posee todos los recursos adquiridos y garantiza cleanup best-effort e idempotente, incluso tras startup parcial. Los fallos del receiver permanecen observables.

Capture no importa Perception, Resolver, flows ni acciones.

## Perception

`PerceptionEngine` recibe detectores explícitos y produce un `ObservationBatch` con la identidad temporal exacta del `FrameSnapshot`. No conserva historial, contexto ni estado de gameplay.

El backend actual usa OpenCV local:

- templates precargados y matching a tamaño nativo;
- regiones normalizadas proyectadas desde el ndarray;
- raw score separado de semantic confidence;
- calibración empírica por detector;
- cero IO de assets por frame;
- múltiples variantes sólo cuando representan el mismo significado visual.

Los detectores productivos cubren Lobby, Character Select, Black Market, Quick Menu, Purchase Confirmation, Insufficient Gold e Inventory Full. Este último usa el botón `OK` común con gating explícito de Black Market, no el mensaje variable. Detectores especializados emiten GOLD y Purchased por slot. La lista y evidencia actual están en `CONTEXT.md`; paths, regiones y anchors son verdad de código/tests.

OCR y VLM deberán implementar el mismo límite de detector. VLM será provider-agnostic y ninguna capa superior dependerá de proveedor, modelo o API concretos.

### Observaciones y facts

`Observation` es evidencia semántica inmutable: nombre namespaced, confidence normalizada, `ObservationSource`, valor escalar opcional y `RelativeRegion` opcional. No transporta frames, templates ni objetos de detector.

`ObservationBatch` agrupa evidencia ordenada de un único frame y permite nombres repetidos. Sus helpers buscan; no fusionan fuentes ni aplican policy.

Hay dos consumos deliberadamente distintos:

- landmarks de pantalla alimentan `ContextResolver`;
- facts internos como `currency.black_market.gold(slot)` y `status.black_market.purchased(slot)` son consumidos por el flow correspondiente.

Un fact no se convierte en contexto sólo para facilitar navegación.

## ContextResolver

`bot/resolver.py` es puro, determinista y stateless. Recibe reglas base y overlay explícitas. Cada `ContextRule` exige observations namespaced con un threshold común; selecciona la mayor confidence de cada nombre y usa el mínimo sólo como diagnóstico.

La resolución base no tiene first-match ni desempate por confidence:

- cero candidatos → `UNKNOWN`;
- uno → `RESOLVED`;
- varios → `AMBIGUOUS` con candidatos explícitos.

Los overlays se resuelven independientemente y pueden coexistir con cualquier estado base. El resolver no implementa hysteresis, voting, debounce, transiciones ni memoria. `ResolvedState` separa base, subcontexto opcional, overlays y candidatos conflictivos.

## RuntimeObserver

`RuntimeObserver` une captura, Perception y Resolver sin mezclarlos. Cada `RuntimeSnapshot` conserva el `FrameSnapshot` BGR y garantiza que observations, estado resuelto, runtime facts y geometría proceden de ese mismo frame. La imagen permite comparaciones visuales acotadas sin saltarse el observer.

Las esperas son bounded, rechazan sequences stale posteriores a una acción y pueden exigir estabilidad continua sobre frames distintos. La estabilidad pertenece a la espera del caso de uso, no introduce estado implícito en `ContextResolver`.

Todo efecto de una acción que tenga una postcondición observable fiable se verifica antes de continuar, incluso cuando la pantalla no cambia. Una interacción observada/verificada combina `RuntimeObserver + ActionExecutor`; el Flow o Rotation declara el efecto requerido y los guards, pero no implementa retries físicos manuales. Si no existe una señal robusta, la acción permanece explícitamente no verificable y usa policy conservadora: no se inventan postcondiciones débiles.

## Rotation

`bot/rotation.py` define `RotationStrategy.advance()` como contrato transversal. `StandardRotation` decide cómo cambiar una vez de personaje mediante estado semántico y solicita intents al `ActionExecutor`; no conoce flows, identidad de personajes ni ADB.

`bot/observed_scroll.py` es una operación transversal que compone `RuntimeObserver + ActionExecutor`. Conserva un frame settled A, observa frames transitorios T mientras se ejecuta un `Swipe` y exige un settled B fresco posterior al release/bounce. Clasifica progreso, edge candidate e intento inefectivo; aplica confirmaciones, timeout y máximo de intentos bounded. La similitud A/B por sí sola nunca prueba edge: debe existir movimiento transitorio efectivo del mismo intento.

`bot/character_select_scroll.py` sólo aporta el perfil específico de Character Select: ROI, thresholds, gestos de progreso/confirmación, settle y policy bounded. `StandardRotation` navega, delega `scroll_to_edge` y sólo intenta seleccionar si el resultado confirma edge; no contiene medición A/T/B ni detección de bounce. Después verifica la selección de la tarjeta con `bot/character_selection.py`, un detector local del marco amarillo de la posición target que no identifica personajes.

`bot/verified_transition.py` verifica acciones discretas contra una postcondición, tanto transiciones de contexto como efectos intra-screen: input, espera nominal, ventana de gracia sin input y, sólo cuando el consumidor aporta un guard que acepta el estado fresco actual, retry bounded. Una policy opcional puede esperar pasivamente que un guard inicialmente inconcluso se estabilice; nunca repite input desde `UNKNOWN`. Distingue éxito inicial, retrasado o posterior a retry, rechazo del guard, agotamiento, estado inesperado, timeout y fallo. No implementa recovery ni decide qué estados son seguros; Rotation o el Flow aportan precondición, postcondición y `retryable_from`.

## Flows

Los flows contienen intención y reglas de negocio deterministas. Declaran scope, prerequisites y outcomes; reaccionan a `RuntimeSnapshot` y emiten semantic actions.

`bot/flow_contracts.py` define el contrato transversal `FlowResult(status, events)`. `COMPLETED` garantiza que el flow terminó y recuperó Lobby; `FAILED` indica que continuar no es seguro. `FlowEvent(kind, detail=None)` representa resultados de negocio extensibles y no controla la sesión.

`BlackMarketFlow` es `PER_CHARACTER`, comienza y termina en Lobby y no cambia de personaje. Su closure semántico incluye Black Market, Purchase Confirmation, Insufficient Gold, Inventory Full, GOLD y Purchased; Quick Menu no es prerequisite. Cada selección GOLD es una transición verificada hacia una de las tres ramas esperadas y sólo admite retry desde Black Market limpio; el retorno de cada rama debe permanecer estable antes del siguiente slot. Low Gold e Inventory Full producen business events no fatales; este último se reconoce mediante una transición verificada, pero el flow no identifica ni libera inventarios. La policy funcional detallada está en `CONTEXT.md`.

Los support operations futuros seguirán `check → bounded support operation → recheck → continue/skip/fail`; no se permiten llamadas recursivas arbitrarias entre flows.

## Semantic Actions y ActionExecutor

Los intents modelan acciones del dominio y primitives físicas tipadas. El slice actual define acciones de Black Market —incluido el `OK` de Inventory Full— y las mínimas de Rotation: abrir Quick Menu, entrar a Character Select, elegir la última tarjeta visible y confirmar selección. `Swipe(start, end, duration)` es genérico y no contiene policy de scroll, bounce ni conocimiento de pantallas.

`ActionExecutor` es el único traductor de intent a input físico. Valida taps o swipes normalizados, deriva pixels desde la geometría del frame y delega en `AdbClient`. No consulta Perception, no interpreta movimiento/bounce, no espera postcondiciones y no decide gameplay.

El boundary de interacción queda: `Rotation / Flow → {VerifiedTransition para acciones discretas observables | ObservedScroll para operaciones continuas} → RuntimeObserver + ActionExecutor → AdbClient`. `ActionExecutor` sólo emite input físico; la interacción observada comprueba su efecto. Retry y verificación no pertenecen a `ActionExecutor`; Conflict/Recovery queda reservado para estados inesperados o fallos que no resuelve una interacción local. `SessionRunner` está por encima de flows y Rotation y sólo consume sus contratos.

## Device / ADB

`bot/adb.py` define `AdbClient`, límite único para procesos y comandos ADB. Recibe ejecutable, serial y timeout explícitos; construye argumentos separados y traduce fallos a `AdbError` o `AdbTimeoutError` con contexto.

Expone estado, shell, taps/swipes pixel, push, forwards y procesos persistentes. El owner de un proceso o forward conserva su lifecycle. Tests normales inyectan un runner fake y no requieren ADB instalado.

## Perception Workbench

Workbench es una composición humana paralela, fuera del runtime de gameplay:

```text
ScrcpyFrameSource → PerceptionEngine → ContextResolver ─┐
Android touch → HumanInputObserver (read-only) ─────────┴→ Workbench UI / raw evidence
```

`HumanInputObserver` observa `getevent`, reconstruye gestos y normaliza coordenadas/rotación; nunca envía input. La UI trabaja sobre copias, conserva ground truth explícito, limita escritura y separa vocabulary de adquisición del catálogo productivo.

La evidencia de una interacción es observacional. Sólo una confirmación humana explícita puede registrar destino semántico; ni el frame posterior ni una prediction rellenan ground truth, prueban causalidad o crean targets. Raw sessions viven en `artifacts/`; sólo manifests curados bajo `datasets/` alimentan evaluación productiva.

El protocolo conversacional y las restricciones de hardware están centralizados en `AGENTS.md`.

## Orquestación de sesión

El producto objetivo es un orquestador configurable, no un agente general:

```text
User Control Panel
  → SessionPlan
    → SessionRunner
      ├── Selected PER_CHARACTER Flow(s)
      └── RotationStrategy.advance()
```

`SessionPlan` expresa intención: `character_count`, flows ordenados y strategy. `SessionRunner` ejecuta todos los flows del personaje activo, verifica el boundary contractual Lobby mediante una sonda semántica inyectada y sólo entonces solicita un advance. El composition root productivo espera Lobby estable de forma pasiva para no confundir frames `UNKNOWN` de carga con una contradicción. Repite el bloque exactamente `character_count` veces, incluido el advance final que cierra el ciclo; no trata 27 como caso especial ni reprocesa el personaje inicial después del retorno.

Business events se agregan y registran sin interpretación específica. Un `FlowResult.FAILED`, una postcondición contradictoria o un `RotationResult` fallido abortan la sesión sin intentar el siguiente personaje. La cancelación se observa únicamente antes/después de componentes completos. `SessionCharacterResult` y `SessionResult` preservan el progreso parcial.

El primitive de `rotation.standard` usa Quick Menu → Character Select → bottom confirmado → última posición → Lobby. El comportamiento MRU permite recorrer personajes sin identidad visual y `character_count = 28` es configuración explícita compartida. La captura transitoria concurrente no cambia los límites: Rotation solicita un intent semántico y `ActionExecutor` sigue siendo quien ejecuta el input físico. El loop aislado 28/28 y el regreso final al personaje inicial están validados; MAIN/SUBS quedan para strategies futuras.

La identidad futura sigue un boundary independiente:

```text
OCR / Perception extractors
  → CharacterContextProvider
    → CharacterContext
      → SessionRunner / logging / flows
```

`SessionRunner` coordinará como máximo una adquisición opcional desde Lobby por personaje. Identidad ausente no es fatal cuando sólo alimenta logging. `StandardRotation` no identifica personajes y una strategy futura identity-aware será otra implementación de `RotationStrategy`, no una modificación de la standard.

`CharacterContext` contiene identidad y metadata estable. Los datos dinámicos —stamina, recursos u otros runtime facts— se adquieren cuando un flow los solicita y no se almacenan como identidad. OCR pertenece a Perception/extractors; ni el runner ni los flows lo implementan. En este checkpoint el contexto queda en `name=None` y no existe provider productivo.

El runtime unattended futuro necesita timeouts, recovery transversal, logging, aislamiento de fallos, cleanup y policy de continuación. Hasta entonces, el vertical slice aborta ante errores técnicos después de registrar y limpiar.

## AdsManager

`bot/ads_manager.py` sigue siendo un subsistema standalone basado en UIAutomator2 para aplicaciones o packages externos. No participa en Perception ni `ContextResolver`; su contrato futuro es recuperar control y devolverlo al juego.

## Legacy y migración

El tag `legacy-pre-hybrid` y `docs/legacy/` preservan la implementación anterior. `constants.py` conserva taxonomía y conocimiento de dominio, pero no es configuración objetivo. Los consumers legacy rotos no se reparan mediante shims: cada capacidad se migra incrementalmente a los límites 0.2 cuando un caso funcional la requiere.

OpenCV, scrcpy y ADB no son legacy por sí mismos; lo legacy es acoplar captura, reconocimiento, decisión y coordenadas en el mismo modelo.
