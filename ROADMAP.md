# Roadmap — Kritika FarmBot 0.2

El roadmap contiene únicamente trabajo futuro y fases completadas del rediseño. La prioridad inmediata es establecer un núcleo testeable; no completar el catálogo legacy de templates y coordenadas.

## Fase 0 — Baseline y documentación

- [x] 0A — Auditoría read-only del repositorio.
- [x] 0B — Preservación legacy, limpieza segura y reorganización documental.

## Fase 1 — Núcleo reutilizable

- [x] 1A — Establecer baseline pytest sin hardware, configuración explícita y geometría derivada del frame real.
- [x] 1B — Separar ADB en un adaptador explícito y testeable sin hardware.
- [x] 1C — Extraer `ScrcpyFrameSource` con lifecycle y cleanup de captura testeables sin hardware.
- [x] 1D — Integrar configuración/lifecycle y validar captura real mediante smoke test opt-in.
- [x] 1E — Retirar infraestructura duplicada de `screen.py` y migrar tools reutilizables al núcleo 0.2.

## Fase 2 — Modelo semántico

- [x] 2A — Definir `Observation`, `ObservationBatch`, `ResolvedState` y sus validaciones estructurales.
- [x] 2B — Construir un `ContextResolver` determinista, explicable e independiente del catálogo.
- [x] 2C — Extraer un primer catálogo semántico mínimo desde el conocimiento legacy.
- [x] 2D — Validar el catálogo mínimo contra assets y screencaps históricos.

## Fase 3 — Percepción local

- [x] 3A — Implementar el pipeline productivo `FrameSnapshot → PerceptionEngine → ObservationBatch` para Black Market y Purchase Confirmation, con templates precargados y calibración empirical-gap provisional.
- [x] 3B — Adquirir 30 screenshots con ground truth humano, validar un landmark real de Lobby y reevaluar Character Select y Battle Mode Select sin ampliar Perception productiva.
- [x] 3B.1 — Reevaluar offline Lobby ante variación estacional esperada: auditar el ancla de oro posicional, aislar rótulos comerciales y elegir una señal mínima sin cambiar Perception productiva.
- [x] 3C — Curar assets y calibración productiva para `landmark.lobby_trading_center_label` y el candidate actual de `landmark.character_select_header`; conservar `landmark.lobby_commerce_pair` como alternativa offline y mantener Battle Mode Select fuera hasta ampliar diversidad o separación.
- [x] 3D — Smoke end-to-end completado en hardware real después del repair offline 3F y la revalidación 3G: Lobby, Character Select, reentrada, `UNKNOWN`, Black Market, composición con Purchase Confirmation, latencia y cleanup validados sin acciones Android.
- [x] 3E — Perception Workbench v1 completado y validado en hardware: igualdad 3D/Workbench, preview limpia/live, ground truth base/overlay, falsos negativos de Black Market y Purchase Confirmation, marcadores tap/swipe alineados, before/after, writer sin backlog y cleanup. La primera sesión degradada permanece diagnóstica/no curada; las sesiones válidas son raw input para 3F. Hay 348 tests hardware-free verdes.
- [x] 3F — Curar cinco frames human-confirmed de Workbench, reparar Black Market mediante recalibración y Purchase Confirmation mediante variantes nativas del mismo prompt, reevaluar los cuatro detectores sobre 62 labels y proteger la promoción frente a sesiones diagnósticas. El repair offline produjo 62/62 estados esperados y quedó sujeto a la revalidación live completada en 3G.
- [x] 3G — Repair 3F revalidado live, sin acciones, sobre la season actual: igualdad Workbench/3D, estados base, Black Market, Purchase Confirmation sobre base conocida y `UNKNOWN`, latencia y cleanup completos. La corrida cerró 3D sin introducir gameplay, temporalidad ni nuevos contextos.
- [x] 3H.1 — Abrir Perception Workbench a candidate semantics mediante un acquisition vocabulary separado y registrar transition evidence observacional con GT posterior exclusivamente confirmado por el humano.
- [x] 3H.2 — Auditar las 75 entradas legacy, adquirir/revisar Quick Menu sobre Lobby e Inventory y promover `menu.quick` como overlay global mediante 18 positivos/77 negativos, cerrando la semántica contextual mínima del flow Black Market multi-character.
- [x] 3H.3 — Revalidar `menu.quick` live, promover percepción GOLD por slot sobre el grid Black Market 5×2 y modelar `popup.insufficient_gold` con trigger/recovery human-confirmed, sin implementar navegación, compras ni flow.
- [ ] 3H.4 — Curar y promover próxima cobertura semántica priorizada sólo cuando un flow o recovery concreto la requiera, sin convertir candidates automáticamente en reglas productivas.
- [ ] Navigation foundation — Diseñar posteriormente el modelo de navegación a partir de evidencia observada y curada; no derivarlo directamente de taps aislados.
- [ ] Reutilizar OpenCV y templates donde aporten valor medible.
- [ ] Evaluar un detector visual entrenado cuando exista dataset suficiente.
- [x] Ampliar el manifest de dataset con nuevos positivos confirmados.

## Fase 4 — OCR

- [ ] Leer stamina cuando un flow lo necesite.
- [ ] Leer monedas y recursos relevantes.
- [ ] Incorporar otros valores dinámicos de forma incremental.

## Fase 5 — VLM fallback

- [ ] Definir una interfaz provider-agnostic.
- [ ] Detectar y escalar estados desconocidos.
- [ ] Analizar visualmente casos no cubiertos por percepción local.
- [ ] Guardar casos útiles para incorporarlos después a detectores locales.

## Fase 6 — Flows

- [ ] Migrar lógica de negocio de forma incremental.
- [ ] Definir prioridades e interrupciones semánticas cuando un flow real las necesite.
- [ ] Mantener los flows separados de percepción y ADB directo.
- [ ] Seleccionar el primer flow según valor y facilidad de validación.
- [ ] Usar TOT como conocimiento legacy cuando sea útil, sin asumir que será el primer flow reconstruido.
