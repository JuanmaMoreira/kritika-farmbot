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
- [ ] 3D — Completar el smoke end-to-end en hardware real. La primera corrida validó Lobby, Character Select, reentrada, `UNKNOWN`, latencia y cleanup, pero Black Market y Purchase Confirmation fallaron con scores live inferiores a la calibración offline; adquirir evidencia current-season confirmada, diagnosticar sin bajar thresholds arbitrariamente y repetir la sesión completa.
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
