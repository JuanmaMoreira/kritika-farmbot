# Roadmap — Kritika FarmBot 0.2

## Estado

El primer vertical slice de runtime está cerrado. Rotation sigue siendo el próximo trabajo funcional; la optimización documental/tooling posterior a Fase 4 no añade gameplay.

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

- [ ] Definir `RotationStrategy` como responsabilidad transversal.
- [ ] Implementar `rotation.standard` con `character_count = 28` configurable.
- [ ] Navegar Quick Menu → Character Select → scroll al final → última posición → Lobby.
- [ ] Aprovechar el orden MRU sin identificar personajes y sin lógica especial MAIN/SUBS.
- [ ] Validar hardware-free primero y mantener cualquier prueba física separada y opt-in.

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
