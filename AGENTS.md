# Instrucciones operativas

## Autoridad y lectura

- Leer siempre este archivo. [GAMEPLAY_GT](docs/GAMEPLAY_GT.md) es la fuente física canónica; [ARCHITECTURE](ARCHITECTURE.md), los contratos de software; [CONTEXT](CONTEXT.md), estado caliente; [ROADMAP](ROADMAP.md), pendientes; [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md), contrato y wiring de recursos. [HISTORY](docs/HISTORY.md) y documentos marcados históricos son sólo procedencia.
- Gameplay/UI: `USER_GT` explícito → nueva `LIVE_EVIDENCE` que físicamente lo contradiga → evidencia curada/replay → OCR/detectores/inferencia (`HEURISTIC`). Un miss, UNKNOWN, baja confianza o título ilegible no contradice GT. Un hecho cerrado no se readquiere por un fallo perceptivo.
- Implementación: código + tests actuales → contratos/intención activos → historia. Capacidad standalone no equivale a wiring productivo. Marcar diferencias, no inventar conciliaciones. Usar `USER_GT`, `LIVE_EVIDENCE`, `IMPLEMENTATION_CONTRACT`, `HEURISTIC`, `LEGACY_STALE`, `UNKNOWN` cuando aclare procedencia.
- Inspeccionar headings y rangos relevantes, no cargar documentos largos por hábito. Releer el rango vigente antes de un patch pequeño. Contextos físicos nuevos/ambiguos requieren USER_GT antes de implementar: nunca derivar clase de nombres técnicos.

## Cambio mínimo y simplicidad

- Ciclo: GT conocido → implementación mínima → validación dirigida → un smoke live si hace falta → primera divergencia causal → fix mínimo → sólo validación invalidada → siguiente smoke. No resolver ramas futuras hipotéticas.
- Preferir composición directa dentro de los owners existentes y ramas explícitas para estados pequeños conocidos. Una API imperfecta puede quedarse si es segura, local, comprensible, testeable y suficiente.
- Una abstracción nueva normalmente requiere varios consumidores reales, una frontera real de ownership, comportamiento duplicado actual o una frontera de seguridad que no pueda expresarse localmente. No crear factories/coordinators/providers/value objects/recovery genérico para una rama.
- Un bug local no autoriza refactor vecino. Mayor capacidad del agente no amplía alcance; agentes pequeños reciben trabajo mecánico acotado con policy/ownership ya conocidos.
- Si el fix acumula excepciones, estado oculto o capas, o no se puede explicar el próximo input, parar y proponer simplificación/reimplementación local. Un problema arquitectónico demostrado requiere acordar alcance antes de ampliarlo; la arquitectura actual no necesita reconstrucción por defecto.
- Verificar el efecto con la señal fiable suficiente; no añadir gates decorativos o postcondiciones redundantes. Un input/retry requiere autorización concreta y fresca, bounds y cancelación; UNKNOWN/AMBIGUOUS por sí solos nunca autorizan input.

## HIL sólo para una pregunta física abierta

- Consultar primero GAMEPLAY_GT y evidencia existente. Pedir HIL sólo por gameplay realmente UNKNOWN, input económico/destructivo nuevo, control/hitbox no verificado, estados indistinguibles con seguridad, contradicción física nueva con GT o bug live no atribuible con logs/capturas existentes.
- No reconfirmar transiciones deterministas, clase/layering, controles conocidos, cada rama antes de implementar ni una pantalla que el usuario vio abrirse. OCR decorativo no exige HIL si hay evidencia funcional/contextual más fuerte.
- Un USER_GT explícito o un antes→acción→después inequívoco normalmente cierra el hecho determinista. No imponer múltiples campañas/muestras por costumbre.
- Hardware siempre explícito y autorizado por la tarea. Usuario opera teléfono/GUI; chat + steer es el canal principal. Smoke breve hasta la primera divergencia, sin efectos extra y con cleanup incluso al fallar. Tests normales sin teléfono.

## Validación por invalidación

| Cambio | Validación suficiente inicial |
| --- | --- |
| Documentación/proceso | Referencias/formato y diff; sin tests de código |
| Lógica local | Tests directos y regresiones afectadas |
| Orquestación compartida | Directos + afectados; suite completa sólo por invalidación real o checkpoint/release deliberado |
| ROI/reader/detector local | Replay relevante + evaluator incremental afectado |
| Infraestructura perceptiva global | Evaluator/corpus más amplio según invalidación concreta |

Sin cambio perceptivo, sin evaluator. Reutilizar resultados aún válidos; fallos ambientales conocidos se reportan aparte y no bloquean trabajo ajeno. Tests protegen contratos reales, regresiones vividas o fronteras de seguridad significativas, no conteos. Antes de trabajo caro explicar qué cambió, qué invalida y por qué no alcanza algo más barato. Offline no demuestra una propiedad física, pero tampoco obliga a repetir GT conocido.

## Entorno, preservación y cierre

- Consultar `AGENT_LOCAL.md` antes de redescubrir Python/ADB/scrcpy; no asumir PATH. Es local, sin secretos/seriales y no se versiona. Tools Python con imports internos desde raíz, como módulos, preferentemente `./tools/agent_run.ps1 tools.nombre`.
- Geometría desde `frame.shape`; no hardcodear resoluciones, IDs ni paths portables. Respetar cleanup del owner de sources/procesos/sockets/forwards.
- Preservar todo trabajo ajeno/local, staged o no. No reset/revert/clean, borrar evidencia/branches, reescribir historia ni push sin instrucción explícita. Revisar status/diff/staged antes de cualquier commit autorizado y status después; checkpoints coherentes, no micro-checkpoints por hábito.
- Revisar consumidores antes de borrar evidencia. No versionar datasets grandes, screencaps, artifacts, logs, caches, .env ni AGENT_LOCAL. Separar adquisición de implementación; manifests curados y assets runtime sí son versionables tras revisión.
- Actualizar sólo la fuente dueña del cambio: GT, contrato, estado o pendientes. CHANGELOG se reserva para milestones/capacidades importantes. Informar causa, cambio, validación afectada y límites de forma compacta; detenerse al completar el alcance.
