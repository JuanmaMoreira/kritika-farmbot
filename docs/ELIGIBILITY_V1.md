# Eligibility mínima v1

Baseline: `main@a5c264899e259a026d49ede64f8321c7526dbcda`, Identity mínima consolidada y última suite anterior de 1730 tests. Eligibility v1 aceptada por el usuario; este checkpoint cierra el bloque arquitectónico actual.

## Reconstrucción y diseño

Routine expresa flows ordenados; Eligibility decide si corresponde ejecutar cada posición ahora; Flow conserva la actividad. No se añade un motor de reglas ni una policy global al registry.

`SessionPlan` conserva flows y Rotation y añade una tupla opcional `eligibility`, alineada por posición: un objeto con `evaluate()` o `None`. Una tupla omitida equivale a todos `None`. Esto distingue también ocurrencias repetidas del mismo flow. La composición productiva `run_session` conecta únicamente World Boss; `SessionPlan.standard()` por sí solo no impone Daily. La selección y su orden siguen expresando la routine, sin crear un framework de routines.

`FlowDefinition` continúa describiendo identidad, scope, contrato y factory. `GuiExecutionRequest.SESSION` llama `ProductiveRuntime.run_session`; `SELECTED_FLOWS` llama `run_flows_once`, que compone `run_flow` sin SessionPlan ni Rotation. Run Selected Flows y Run Flow Once no construyen ni evalúan Eligibility Daily. CLI de sesión y GUI de sesión comparten la conexión, sin configuración nueva.

El runner asegura la precondición vigente y obtiene Identity con el snapshot existente de la primera precondición. Después evalúa Eligibility, antes de `flow.started`. La evaluación concreta observa/navega mediante operaciones semánticas; el runner no recibe captura, acciones ni reglas World Boss. Una decisión definitiva debe devolver la precondición del flow verificada, y el runner vuelve a comprobarla sin intentar normalización. Sin check se mantiene exactamente el camino anterior.

## Resultados y UNKNOWN

- `ELIGIBLE`: ejecutar el flow por su contrato normal.
- `NOT_ELIGIBLE`: guardar `FlowResult(SKIPPED_NOT_ELIGIBLE, skip_reason=...)` en la posición del plan, sin llamar al flow ni exigir sus postcondiciones de actividad.
- `UNKNOWN`: inconcluso técnico; abortar la sesión conservando `FailureCause`, sin skip ni continuación/Rotation.
- `FAILED`: conservar la causa técnica, incluida evidencia; abortar.
- `CANCELLED`: propagar cancelación sin disfrazarla de skip o fallo.

Un skip requiere razón y no admite error, FailureCause ni business events. Sólo el runner puede producirlo antes de ejecutar el flow. No se afirma que la evaluación sea libre de navegación: consultar el badge exige abrir su pantalla. El skip no ejecuta selector, selección de boss, recompensas, Start ni ninguna operación productiva de World Boss.

## World Boss Daily: evidencia y recorrido

La señal vigente es `status.world_boss_daily_active`, derivada del detector posicional `indicator.world_boss_daily_active` en la tarjeta World Boss de `screen.battle_mode_select`. No se encuentra en Lobby ni se deriva de sapphires. El [manifest Daily](../datasets/daily_activity_semantic_manifest.json) conserva tres positivos y tres negativos human-confirmed; los negativos contienen badges Daily de otras tarjetas. El [manifest World Boss](../datasets/world_boss_semantic_manifest.json) aporta contexto adicional. La regresión Daily de 22 frames sigue verde; no se cambian detector, ROI ni thresholds.

`WorldBossDailyEligibility` abre Battle Mode Select mediante la transición adquirida desde Lobby. Exige badge presente o ausente consistente durante 0,75 s sobre secuencias frescas posteriores a la apertura, con budget de 6 s. Un cambio de presencia, UNKNOWN, AMBIGUOUS u overlay incompatible reinicia la estabilidad. Agotar la espera es UNKNOWN técnico. Un error de captura conserva la excepción técnica. No se envía retorno ni otro input desde una lectura inconclusa. La apertura utiliza VerifiedTransition con un máximo de dos intentos y retry autorizado únicamente por Lobby fresco confirmado.

**Decisión de diseño:** preservar `WorldBossFlow` intacto y volver a Lobby después de consultar el badge. Elegible ejecuta su recorrido habitual, incluida una segunda apertura de Battle Mode Select si sus recursos permiten entrar. Es el costo explícito de conservar su contrato Lobby y su lectura inicial de sapphires. Eliminar esa apertura duplicada exigiría una entrada preparada y transferencia de recursos al flow; no se ha introducido esa ampliación. No hay caché de elegibilidad entre personajes ni evaluación anticipada para toda la sesión.

**Retorno adquirido:** el usuario confirmó y operó `Battle Mode Select → Quick Menu → Lobby` el 8 de septiembre UTC. Se conservaron tres frames por condición y la confirmación separada de Daily activo. El [manifest de retorno](../datasets/world_boss_eligibility_return_manifest.json) vincula nueve frames curados con sus raws y hashes; todos los raws permanecen por instrucción explícita. El layout y los targets existentes de `OpenQuickMenu` y `SelectQuickMenuLobby` corresponden a los controles adquiridos. No hubo replay automático ni medición continua de latencia; la captura fue pasiva y cada fuente se cerró al terminar.

El adaptador productivo reutiliza `_quick_menu_to_lobby`, extraído del normalizador existente sin cambiar los inputs de sus callers anteriores. Cada transición se verifica y tiene como máximo dos intentos state-guarded. La apertura exige Battle Mode Select resuelto con cero overlays o sólo su Daily; la selección de Lobby exige `menu.quick` observado. La base puede ser UNKNOWN bajo ese menú porque la autorización la proporciona el overlay conocido, no la base desconocida. No se amplía el allow-list de Rotation ni se habilitan otros destinos desde Battle Mode Select: esta fase adquiere exclusivamente el retorno necesario para Eligibility. Fallar el retorno conserva FailureCause y no produce skip ni ejecuta el flow.

## Clasificación de los demás flows

| Flow | Contrato y policy actuales | Eligibility v1 |
| --- | --- | --- |
| Black Market | General-purpose; actividad útil al inicio, guards propios de GOLD/inventario | Sin check nuevo; conservar al inicio |
| World Boss | General-purpose, Lobby → Lobby/World Boss, ALWAYS_PARTICIPATE | Check externo sólo en sesión Daily; manual conserva participación |
| Send Stamina | Propósito Daily; guard correcto del badge en Friends | Sin doble policy |
| Summon Pet Daily | Inherentemente Daily; guard propio en Pet Manage | Sin doble policy |
| Daily Quests | Inherentemente Daily; claims y reward de progreso bajo guards propios | Sin check nuevo |
| Mailbox | General-purpose; útil al final, guards de claims y Delete Read | Sin check nuevo |
| Guild Check-In | Propósito Daily; guard activo/completado del botón Attendance | Sin check nuevo; conservar el guard existente |

Hay dos diferencias respecto de las premisas del pedido que se informaron por chat: Guild **no** exige el badge Daily verde (sólo lo tolera); el negativo discriminante Attendance activo + Daily ausente sigue pendiente. El registry default termina `Daily Quests → Mailbox → Guild Check-In → Rotation`. No se reordenó el plan ni se cambió Guild para uniformar policies; ambos asuntos requieren resolver la intención si se desea cambiar el baseline.

## Observability y SessionReport

El runner publica exactamente un `flow.skipped_not_eligible` de lifecycle con razón, posición e identidad. No publica `flow.started`, `flow.completed` ni un business event para el flow omitido. Las transiciones de evaluación conservan su observabilidad técnica. Un fallo de evaluación termina en `session.failed`, preservando el componente/posición terminal y su FailureCause.

SessionReport proyecta el resultado existente como `skipped (not eligible)` y muestra la razón. No suma el skip a `flows_completed`, business incomplete ni technical failure. Si los otros componentes y Rotation completan, el personaje y la sesión son complete. No hay persistencia ni eventos nuevos desde el builder/renderer. GUI muestra el estado del skip sin incrementar flows completados; Run Selected Flows conserva ejecución manual.

## Validación

Loop dirigido final: **258 passed**. Incluye integración real de `ProductiveRuntime` con dobles semánticos de dispositivo: sesión aplica Daily, selección manual la omite, no hay checks en los otros seis flows, los inputs de esos flows conservan el orden original y Rotation mantiene su advance final. También cubre fallos de ambas transiciones del retorno, causa/evidencia, cancelación durante el probe final, flows repetidos, UNKNOWN/AMBIGUOUS, badge fluctuante, secuencias viejas y ausencia de lifecycle/business events duplicados.

Regresión productiva incremental: **413 frames, cero wrong/ambiguous, 31.801 pares, 31.108 hits, 693 evaluados, cero invalidaciones y sin reconstrucción de cache**. Incluye el corpus anterior y los nueve frames nuevos; no se cambiaron detectores, assets, ROIs ni thresholds. La regresión específica Daily conserva sus 22 frames. El manifest nuevo queda incluido en la evaluación productiva default. Suite hardware-free final: **1771/1771 passed en 251,48 s**, 41 tests nuevos sobre el baseline de 1730. `git diff --check`, enlaces locales y whitespace de archivos nuevos verificados.

## Archivos y follow-ups

- Contrato y ejecución: `bot/eligibility.py`, `bot/flow_contracts.py`, `bot/session.py`.
- Consumidor/composición: `bot/world_boss_eligibility.py`, `bot/productive_runtime.py`.
- Proyección: `bot/session_report.py`, `bot/event_log.py`, `bot/gui_model.py`.
- Evidencia: manifest de retorno y `tools/production_perception_evaluation.py`.
- Tests: `tests/test_eligibility.py`, `tests/test_world_boss_eligibility.py`, `tests/test_eligibility_integration.py`.
- Documentación: este documento, Context, Architecture, Roadmap y SessionReport.

El siguiente paso es reevaluar el milestone completo, sin iniciar otra implementación automática. Una eventual optimización del recorrido elegible requiere discutir el contrato de entrada preparada; no es requisito para el consumidor actual. El negativo discriminante de Guild sigue separado de esta fase. No se añadieron Arena, scheduler, profiles, planner, pause/resume ni Rotation identity-aware. Los cuatro scripts raíz locales ajenos están preservados y excluidos del commit.
