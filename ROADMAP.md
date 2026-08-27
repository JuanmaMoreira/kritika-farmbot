# Roadmap — Kritika FarmBot 0.2

## Estado

El primer vertical slice de runtime está cerrado. Rotation tiene su primer primitive aislado implementado y validado live; la estrategia completa y la composición de sesión siguen pendientes.

## Completado

- [x] Fase 0 — auditoría, baseline, preservación legacy y reorganización inicial.
- [x] Fase 1 — configuración, geometría por frame, `AdbClient`, captura scrcpy, composition root y tools reutilizables.
- [x] Fase 2 — observations, estado, resolver determinista, catálogo mínimo y validación offline.
- [x] Fase 3 — Perception local, adquisición y Workbench, repair/revalidación live, Quick Menu, GOLD e Insufficient Gold.
- [x] Fase 4 — semantic actions, `ActionExecutor` y `BlackMarketFlow` single-character `Lobby → Black Market → Lobby`, validado live con 460 tests hardware-free.
- [x] Maintenance — hot context compactado, historia separada, entorno local persistente y bootstrap/status para agentes.

La cronología de subfases y evidencia está en [`docs/HISTORY.md`](docs/HISTORY.md).

## Activo / siguiente

### Rotation — continuación funcional de Fase 4

- [x] Definir `RotationStrategy` como responsabilidad transversal.
- [x] Implementar y validar aisladamente un `StandardRotation.advance()` con `character_count = 28` configurable.
- [x] Navegar un cambio Quick Menu → Character Select → scroll al final → última posición → Lobby.
- [x] Endurecer bottom con frames A/T/B, movimiento efectivo y bounce validado sobre ROI de la grilla.
- [x] Extraer A/T/B y scroll-to-edge a una primitive transversal reusable sobre `RuntimeObserver + ActionExecutor`.
- [x] Incorporar transición discreta verificada con grace sin input y retry protegido por estado.
- [x] Calibrar thresholds y gesto en 5/5 entradas scroll-only, sin seleccionar personajes.
- [x] Validar el perfil 1+1 y reservar un tercer swipe sólo cuando el segundo todavía muestre progreso.
- [x] Validar tres `advance()` supervisados con bottom confirmado antes de seleccionar y retorno a Lobby.
- [x] Aprovechar el orden MRU sin identificar personajes y sin lógica especial MAIN/SUBS.
- [x] Validar hardware-free primero y mantener todo smoke físico explícitamente opt-in.
- [x] Validar live la transición discreta en 3 advances supervisados, sin regresión de scroll ni navegación.
- [ ] Retomar el loop de 28, pausado en 14/28 por un tap Select no registrado, y validar el regreso final al personaje inicial sin repetir flows sobre éste.

### Composición mínima de sesión

- [ ] Implementar `SessionPlan / SessionRunner → RotationStrategy + Selected PER_CHARACTER Flow(s)`.
- [ ] Impedir que un flow invoque Rotation o ADB directamente.
- [ ] Definir outcomes y cleanup mínimos para componer el slice existente.

## Después

### Fase 5 — Perception incremental

- [ ] Promover semántica sólo ante una necesidad funcional y evidencia curada.
- [ ] Evaluar detector entrenado cuando exista dataset suficiente.
- [ ] Incorporar OCR para valores dinámicos sólo cuando un flow lo requiera.
- [ ] Incorporar fallback VLM provider-agnostic sólo para casos no cubiertos y guardar evidencia reutilizable.

### Fase 6 — expansión y operación unattended

- [ ] Migrar flows adicionales manteniendo límites entre Perception, Rotation, flows y ADB.
- [ ] Añadir priorities, interruptions, conflict/recovery transversal y aislamiento de fallos.
- [ ] Incorporar estrategias Rotation futuras para MAIN/SUBS, filtros o identidad cuando exista necesidad.
- [ ] Reutilizar TOT como conocimiento legacy sin desplazar el vertical slice vigente.
