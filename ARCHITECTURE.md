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
      → screen.py
        → scrcpy / OpenCV / ADB
```

Responsabilidades reales:

- `bot/constants.py` mezcla configuración de host, resolución, taxonomía, templates, regiones, botones, offsets y políticas aún incompletas.
- `bot/screen.py` implementa a la vez captura scrcpy, almacenamiento del frame, percepción por templates y comandos ADB.
- `bot/context.py` captura un frame y recorre templates hasta encontrar el primer contexto coincidente.
- `bot/actions.py` resuelve botones mediante estado global y coordenadas del catálogo.
- `bot/flows.py` contiene lógica TOT, percepción específica, regiones, thresholds y acciones físicas.
- `bot/ads_manager.py` es un programa standalone basado en UIAutomator2.
- `main.py` no contiene un loop general: conecta el dispositivo e intenta ejecutar exclusivamente TOT.

Problemas estructurales confirmados:

- captura, percepción e input están acoplados;
- el contexto depende directamente de templates;
- actions depende de globals y coordenadas;
- flows contiene percepción y ADB directo;
- la geometría no usa de forma confiable las dimensiones landscape del frame;
- prioridad y outcomes están modelados pero no configurados efectivamente;
- el runtime legacy no es importable en su estado preservado;
- no existe una suite automatizada.

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

### Capture

Obtiene frames landscape desde scrcpy y expone sus dimensiones reales. No reconoce contextos ni toma decisiones.

### Perception

Transforma frames en observaciones semánticas. Puede combinar:

- detectores locales y OpenCV para elementos conocidos;
- OCR para valores dinámicos;
- un fallback VLM para estados desconocidos.

El fallback VLM debe permanecer detrás de un límite provider-agnostic. Ninguna capa superior debe depender de un proveedor, API o modelo específico.

### Semantic Observations

Representan evidencia sobre la UI —elementos, valores, estados candidatos y confianza— sin codificar decisiones del flow ni comandos físicos.

### ContextResolver

Consume observaciones y determina el estado semántico vigente, incluidos subestados, prioridades e interrupciones. No captura frames ni ejecuta acciones.

### Flows / Decision

Contienen intención y reglas de negocio deterministas. Solicitan acciones semánticas y reaccionan a estados resueltos; no hacen template matching ni llaman a ADB.

### ActionExecutor

Traduce una intención de acción validada a interacción con el dispositivo. La resolución geométrica debe usar el frame landscape real y coordenadas normalizadas en `[0,1]` cuando corresponda.

### Device / ADB

Es el límite de infraestructura para taps, swipes y demás comandos del dispositivo. Debe poder sustituirse por un fake en tests normales.

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
