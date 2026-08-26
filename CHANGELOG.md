# Changelog

Este archivo registra únicamente milestones, migraciones, releases y capacidades relevantes. El diario histórico anterior al rediseño se conserva en `docs/legacy/CHANGELOG-legacy.md`.

## Unreleased

### Added

- Se estableció la Fase 1A del núcleo 0.2: baseline automatizado con pytest, configuración de runtime explícita y geometría visual derivada exclusivamente del frame real.
- Se añadió en Fase 1B un adaptador ADB explícito, testeable sin hardware y desacoplado de geometría, percepción y lógica de negocio.
- Se extrajo en Fase 1C una fuente de frames scrcpy con lifecycle explícito, snapshots BGR versionados y cleanup testeable ante fallos parciales.
- Se integró y validó en Fase 1D el stack `RuntimeConfig → AdbClient → ScrcpyFrameSource` contra hardware real con scrcpy-server 3.3.4.
- Se cerró la Fase 1 retirando captura/input duplicados de `bot/screen.py` y migrando las herramientas reutilizables al composition root 0.2.
- Se completó la Fase 2A con contratos inmutables para observaciones semánticas, batches por frame y estados resueltos que distinguen contexto base, overlays, estado desconocido y ambigüedad.
- Se completó la Fase 2B con un `ContextResolver` determinista e inyectable que explica evidencia seleccionada, expone conflictos base y resuelve overlays sin first-match, fusión de confidence ni estado temporal.
- Se completó la Fase 2C con un catálogo productivo mínimo corregido a tres pantallas, un popup y cinco landmarks semánticos, desacoplado de assets y percepción.
- Se completó la Fase 2D con evaluación reproducible sobre 173 capturas y ground truth confirmado para 27, validando Black Market y Purchase Confirmation y corrigiendo señales semánticas engañosas.
- Se completó la Fase 3A con `PerceptionEngine`, detectores OpenCV de templates precargados y calibración empirical-gap provisional para los dos landmarks validados.
- Se completó la Fase 3B con adquisición dirigida de 30 screenshots etiquetados humanamente, un candidate validado para Lobby y reevaluación offline de Character Select y Battle Mode Select sin ampliar detectores productivos.
- Se completó la Fase 3C promoviendo Lobby y Character Select a Perception productiva con assets curados, calibración reproducible sobre 57 labels y regresión end-to-end sin falsos positivos ni ambigüedades; Battle Mode Select permanece diferido.
- Se completó la Fase 3E con Perception Workbench v1: ground truth humano persistente, captura activa/deduplicada de errores, observación read-only de taps/swipes físicos, asociación before/after, sesiones raw reproducibles y validación live de los falsos negativos de Black Market y Purchase Confirmation sin recalibrarlos.
- Se cerraron las Fases 3D y 3G revalidando en hardware real el repair offline 3F: Black Market y Purchase Confirmation generalizaron al runtime current-season, incluida la composición sobre base conocida y `UNKNOWN`, con igualdad Workbench/3D, latencia operativa y cleanup completo sin input Android.
- Se completó la Fase 3H.1: Perception Workbench usa un vocabulario humano separado con candidate semantics, períodos `UNSET` y confirmación explícita de GT posterior enlazada a gestos raw; un smoke read-only validó Lobby → Guild Shop y swipe sin cambio de contexto, sin crear navegación, acciones ni reglas productivas.
- Se completó la Fase 3H.2 con el census de 75 entradas legacy y la promoción human-confirmed de `menu.quick` como overlay global: 18/18 positivos, 0 FP/FN sobre 77 negativos y 95/95 resoluciones offline, sin implementar navegación ni asignar Quick Menu como prerequisite del futuro Black Market flow.
- Se completó la Fase 3H.3 revalidando `menu.quick` live y promoviendo la policy mínima de Black Market `BUY iff currency == GOLD`: detector GOLD por 10 slots con 24/24 TP, cero FP/FN y cero FP sobre KARATS, más `popup.insufficient_gold` como overlay human-confirmed con retorno seguro a Black Market mediante No. No se implementó el flow ni se añadió OCR.

### Changed

- Se preservó el estado legacy previo al rediseño en el tag `legacy-pre-hybrid`.
- Se estableció la dirección arquitectónica híbrida 0.2: captura, percepción, observaciones semánticas, resolución de contexto, flows y ejecución de acciones como responsabilidades separadas.
- Se reorganizó la documentación activa alrededor de `AGENTS.md`, `CONTEXT.md`, `ARCHITECTURE.md` y `ROADMAP.md`.
- Los assets runtime dejaron de quedar ocultos por una regla global para imágenes.
- `bot/screen.py` quedó como módulo transicional de matching OpenCV puro; los scripts manuales redundantes de `testing/` y el debugger de contextos legacy fueron retirados.
- `AGENTS.md` incorporó como regla canónica el protocolo human-in-the-loop: chat + `steer` como canal principal y Workbench únicamente como instrumentación explícita.

### Preserved

- La taxonomía y migración parcial contenidas en `bot/constants.py`.
- El AdsManager basado en UIAutomator2 como subsistema separado.
- Los assets históricos `960x540` y las 173 screencaps como material legacy fuera del Git normal.
