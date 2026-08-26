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

Los detectores productivos cubren Lobby, Character Select, Black Market, Quick Menu, Purchase Confirmation e Insufficient Gold. Detectores especializados emiten GOLD y Purchased por slot. La lista y evidencia actual están en `CONTEXT.md`; paths, regiones y anchors son verdad de código/tests.

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

## Rotation

`bot/rotation.py` define `RotationStrategy.advance()` como contrato transversal. `StandardRotation` decide cómo cambiar una vez de personaje mediante estado semántico y solicita intents al `ActionExecutor`; no conoce flows, identidad de personajes ni ADB.

`bot/character_select_scroll.py` contiene la comparación visual determinista del viewport. El final se reconoce cuando un swipe settled deja la grilla sin cambio material, siempre bajo timeout y límite máximo. Esta lógica no pertenece a Perception contextual ni a policy de Flow.

## Flows

Los flows contienen intención y reglas de negocio deterministas. Declaran scope, prerequisites y outcomes; reaccionan a `RuntimeSnapshot` y emiten semantic actions.

`BlackMarketFlow` es `PER_CHARACTER`, comienza y termina en Lobby y no cambia de personaje. Su closure semántico incluye Black Market, los dos popups, GOLD y Purchased; Quick Menu no es prerequisite. La policy funcional detallada está en `CONTEXT.md`.

Los support operations futuros seguirán `check → bounded support operation → recheck → continue/skip/fail`; no se permiten llamadas recursivas arbitrarias entre flows.

## Semantic Actions y ActionExecutor

Los intents modelan acciones del dominio, no coordenadas. El slice actual define acciones de Black Market y las mínimas de Rotation: abrir Quick Menu, entrar a Character Select, scrollear su grilla, elegir la última tarjeta visible y confirmar selección.

`ActionExecutor` es el único traductor de intent a input físico. Valida el intent, obtiene el target normalizado, deriva pixels desde la geometría del frame y delega en `AdbClient`. No consulta Perception, no espera postcondiciones y no decide si una compra corresponde; esas responsabilidades permanecen en observer/flow.

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

## Orquestación futura

El producto objetivo es un orquestador configurable, no un agente general:

```text
User Control Panel
  → SessionPlan
    → SessionRunner
      ├── RotationStrategy
      └── Selected PER_CHARACTER Flow(s)
```

`SessionRunner` compondrá en el futuro Rotation y flows. El contrato `RotationStrategy` y el primer `StandardRotation.advance()` ya existen; cada flow sigue operando sólo sobre el personaje activo. Ninguno conoce la implementación interna del otro.

El primitive de `rotation.standard` ya usa Quick Menu → Character Select → scroll al final → última posición → Lobby. El comportamiento MRU permite recorrer personajes sin identidad visual y `character_count = 28` es configuración explícita. El loop completo y regreso final al personaje inicial siguen pendientes; MAIN/SUBS quedan para estrategias futuras.

El runtime unattended futuro necesita timeouts, recovery transversal, logging, aislamiento de fallos, cleanup y policy de continuación. Hasta entonces, el vertical slice aborta ante errores técnicos después de registrar y limpiar.

## AdsManager

`bot/ads_manager.py` sigue siendo un subsistema standalone basado en UIAutomator2 para aplicaciones o packages externos. No participa en Perception ni `ContextResolver`; su contrato futuro es recuperar control y devolverlo al juego.

## Legacy y migración

El tag `legacy-pre-hybrid` y `docs/legacy/` preservan la implementación anterior. `constants.py` conserva taxonomía y conocimiento de dominio, pero no es configuración objetivo. Los consumers legacy rotos no se reparan mediante shims: cada capacidad se migra incrementalmente a los límites 0.2 cuando un caso funcional la requiere.

OpenCV, scrcpy y ADB no son legacy por sí mismos; lo legacy es acoplar captura, reconocimiento, decisión y coordenadas en el mismo modelo.
