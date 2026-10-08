# Meteorites — B2, integración Routine/Session 2026-10-08

Baseline `ce44fe55ef0490e068f972b59e96c1e9a3c58350`. Worktree:
`meteorites-hil`.
Sin commit/push. Cambios B1 y trabajo independiente preservados.

## Configuración y owners

`RoutineSpec.change_meteorites` opcional, bool estricto, default OFF. Esquema v2
conservado: v1/v2 anteriores sin campo cargan OFF; campo corrupto carga OFF,
warning y backup conservador antes de Save. `RoutineEditor` posee el draft;
Apply en Routine Settings modifica draft, Save Routine persiste, reopen y
Duplicate conservan el valor. Una casilla Change Meteorites con la aclaración
USER_GT exacta al activarla. Sin configuración por flow/Step/Reliefs.

`ProductiveRuntime.run_routine` instala/restaura la bandera en finally.
`run_flows_once` y `run_session` usan el mismo `SessionRunner`; el primero conserva
SessionResult para SessionReport aunque no haya Rotation. El setup se llama al
comienzo del scope del personaje después del seam de Lobby/identidad estable;
el cleanup se llama después de todos los pasos y antes de Rotation o completion.
Cada fin funcional de flow conserva READY y permite continuar los pasos restantes.

`MeteoritesCharacterScope` en `bot/meteorites_session.py` conserva estados/guards y
proyección del progreso. `SharedMeteoritesPreparation` sigue siendo el único owner
del algoritmo B1; `MeteoritesRuntime` posee freshness/lineage/input/efecto/readiness
/recovery. No se duplicaron lectores, geometría ni reconciliación.
Navegación del caller sale de Meteorites por X a Lobby y sigue el entry del próximo
flow o Rotation. No se habilitó Quick Menu desde una geometría no adquirida.

## Identidad, finalización y reanudación

Excepciones fijas por stable ID: `berserker`, `demon_blade`, `kaiserin` omiten ambos
procedimientos. `burst_breaker` participa. Identidad UNKNOWN no autoriza Equip
ni pasos productivos con esta configuración ON; el índice/nombre OCR libre nunca
selecciona policy.

Estados: NOT_REQUESTED → SETUP_IN_PROGRESS → READY → CLEANUP_IN_PROGRESS → RELEASED;
un corte incierto produce INTERRUPTED. Guard de entrada único y terminal impide
setup/cleanup repetidos por callbacks. Setup parcial bloquea pasos; cleanup fallido
bloquea Rotation. Los efectos provienen de B1, nunca de un tap enviado.

Finalización normal siempre exige cleanup, incluso sin Rotation. Stop Safely soft
intenta sólo la liberación completa desde READY si el gate fresco acredita BASE
limpia conocida. UNKNOWN/overlay no navega. Segundo Stop/señal dura aborta inputs.
FAILED o interrupción incierta no hace cleanup ciego ni Rotation. Session sigue
CANCELLED si una liberación durante Stop Safely llegó a RELEASED.

Cada ejecución crea scopes/progreso nuevos, sin persistir ni reutilizar READY.
SessionReport/eventos incluyen stable ID, outcomes, efectos acreditados, inputs,
retries y tiempos. INTERRUPTED advierte explícitamente desequipar manualmente el
set compartido antes de reanudar y señala si puede seguir equipado. La casilla
significa preparación manual y cinco precondiciones asumidas; sin auditoría completa
ni confirmación adicional en cada personaje roster.

## Validación offline

Selección consolidada: **786 passed, 4 skipped, 41 deselected**, 24.47s.
Session, Report, Routine, GUI/Tk real, ProductiveRuntime, Rotation, preconditions,
Quick Menu/handoffs, identidad, Lobby return, Meteorites A/B1/B2.

Incluye OFF sin scope, ON antes del primer paso, cleanup tras todos los pasos antes
de Rotation/sin Rotation, roster con scopes nuevos, tres excepciones/Burst Breaker,
UNKNOWN, setup/cleanup parcial, FAILED/manual resolution, Stop seguro/inseguro y
segundo Stop, cancelación antes/durante setup, excepción incierta sin primer efecto,
reanudación sin READY viejo, callbacks
repetidos, no-work de un flow, migración/corruptos/draft/Save/reopen/duplicate y GUI.
Una prueba recorre run_routine → run_flows_once → run_session reales con operaciones
B1 portables. Tests nuevos no dependen de artifacts raw ignorados.

Exclusiones separadas: 37 casos antiguos requieren raw ausentes (35 Lobby return,
2 Rotation); 4 harness históricos llaman `_initial_lobby`, API retirada antes de B2
(documentado en CONTEXT). No son fallos causados por esta integración. No se tocaron
esos casos ni se añadieron dependencias raw.

Readers/detectores/assets no cambiaron: sin evaluator nuevo. Los 142 tests y replays
portables A/B1 están incluidos; evaluator Fase A 63/63 positivos y 513/513 negativos
conserva validez. `git diff --check` limpio (avisos Git de LF/CRLF preexistentes).
CLI `tools.smoke_meteorites_b2 --help` comprobada sin teléfono.

## Smoke focal: Session COMPLETED sin Rotation

Preparación confirmada por chat «listo». Primer intento sin cable de datos: ADB sin
dispositivos, cero inputs. Corregido el cable por el usuario, una sola cadena física
completa mediante `ProductiveRuntime.run_routine`: Change Meteorites ON → setup B1
→ Send Stamina real → cleanup B1 → Set 1. Identidad acreditada por el owner existente:
**telumpel**, canonical `Drakenn26`, método canonical_ocr. No cambio de personaje.

Eventos reales, mismo session_id/routine_id:

| Hito | UTC | Event sequence |
| --- | --- | --- |
| Session started | 18:15:42.999711 | 8 |
| Identity resolved telumpel | 18:15:46.129878 | 11 |
| SETUP_IN_PROGRESS | 18:15:46.130882 | 12 |
| READY, 11 Equip acreditados | 18:16:12.541585 | 104 |
| Send Stamina COMPLETED / Lobby | 18:16:20.867076 | 121 |
| CLEANUP_IN_PROGRESS | 18:16:20.867076 | 122 |
| RELEASED | 18:16:48.029399 | 209 |
| Session COMPLETED, 1 personaje / 0 Rotation | 18:16:48.031476 | 210 |

El paso ejecutó All y acreditó Send Stamina completed; no Ads ni compras ni
consumo de recursos propios para probar. Flare E+ +30 posición **1**; frontera normal
**5**; ancla única **14**, página1/cell zero-based13. Flare→centro desde1; normales
1..10 desde14 exactamente. Cleanup10..1/centro, un input lateral por efecto.
**22/22 efectos**, cero retries y reconciliaciones; recovery físico no ejercitado.

Final: Set 2 vacío por sus once efectos individuales; Set 1 activo, página1,
11 slots vacíos en este personaje, sin overlay/Loading. Todos los Equip/Unequip
acreditados actuaron exclusivamente sobre Set 2: Set 1 no recibió modificaciones.
El set compartido está completamente desequipado. Source/procesos cerrados por su
owner. No segundo barrido de Set 2 ni navegación/input extra para reparar reportes.

[Manifest curado](../datasets/meteorites_b2_smoke_20261008_manifest.json) contiene
before/after, índices, slots, cada result/effect, métricas y paths/hash de los 22
pares de evidencia. Raw local ignorado: `artifacts/meteorites_b2/20261008_151539`.
Estado final en `restored_set1_restored_set1.png`; `session_report.txt` muestra
Meteorites RELEASED [telumpel], 11/11 +11/11, Session completed y Rotation0.

### Divergencia exclusivamente del exportador

Después de RELEASED y Session COMPLETED, `asdict(FlowsOnceResult)` intentó deep-copy
de `FlowEvent.fields` (mappingproxy) y falló. Ninguna divergencia física/lifecycle.
Se sustituyó sólo la serialización del tool por fields/Mappings/timestamps; frames
siguen separados, sin deep-copy del snapshot. Regresión portable de exportación:
**1 passed**, sin teléfono. No se repitieron las 22 operaciones.

El JSON original del fallo se preservó como `report_export_original.json`. El reporte
se reparó desde eventos reales y progreso B1 completos, con procedencia/hash explícita.
SessionReport se reconstruyó de esos facts; su duración65.031765s deriva de timestamps
lifecycle, no del perf timer perdido. `routine_seconds`65.031s sí se conservó en el
export original. Manifest identifica esta reparación; no oculta el fallo inicial.

### Tiempos y percepción

| Medida | Segundos | Alcance |
| --- | ---: | --- |
| Routine real | 65.031 | identidad, setup, caller/step, cleanup e I/O |
| Scope setup | 26.411 | callback B1 completo e I/O |
| Scope cleanup | 27.155 | navegación de entrada + B1 cleanup e I/O |
| B1 setup / cleanup | 26.406 / 22.782 | procedimiento físico e I/O |
| 22 operaciones | 20.296 | primitives, excluye I/O de evidencia |
| Coordinator | **0.009606** | transiciones/reporting fuera de callbacks |
| Entrada de cleanup / navegación | 4.365 | gate/caller/entry fuera de B1 cleanup |
| READY→cleanup | 8.325 | caller hacia Lobby + Send Stamina y postcondition |
| I/O evidencia total | 23.830 | medido; no se guardó split por fase |
| Callbacks setup+cleanup sin I/O | 29.736 | incluye navegación de cleanup |

Las 22 primitivas:476 capture queries,66 OCR,962 detector,2199 CV,309 stale rejects;
capture0.622s/perception2.625s; Bag navigation0.344s. Entrada/discovery B1 añade
61capture/12OCR/121detector/409CV/39stale, capture0.108s/perception0.376s y Bag0.359s.
Sumas locales537/78/1083/2608/348 excluyen percepción global de caller/identity/flow
y restore Set 1 posterior al último resultado. No presentar esas sumas como todos
los calls de Session. Stale rejects nunca autorizaron inputs.

Selección→overlay total6.639s; tap→efecto11.363s; efecto→readiness0.590s en las22
operaciones. Tap→efecto incluye juego + captura/percepción; no es tiempo puro del
motor. La navegación, percepción e I/O se informan aparte sin inventar separación
más precisa de la latencia del juego.

### Evidencia y wall por operación

En cada fila el before/after corresponde al slot esperado, Set 2. Sequence acredita
el efecto; el manifest enlaza before/overlay/action/effect/final con hash individual.
Tiempos en segundos; 1 input por fila, 0 retries en todas.

| Operación | Posición Bag | Efecto slot | Sequence | Wall | Selección→overlay | Tap→efecto | Efecto→ready |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| equip_0 | 1 | empty→occupied | 100 | 0.890 | 0.265 | 0.516 | 0.015 |
| equip_1 | 14 | empty→occupied | 118 | 0.906 | 0.297 | 0.516 | 0.031 |
| equip_2 | 14 | empty→occupied | 137 | 0.985 | 0.281 | 0.610 | 0.031 |
| equip_3 | 14 | empty→occupied | 155 | 0.922 | 0.297 | 0.516 | 0.031 |
| equip_4 | 14 | empty→occupied | 177 | 1.078 | 0.390 | 0.610 | 0.031 |
| equip_5 | 14 | empty→occupied | 196 | 0.859 | 0.219 | 0.500 | 0.016 |
| equip_6 | 14 | empty→occupied | 214 | 0.890 | 0.297 | 0.469 | 0.015 |
| equip_7 | 14 | empty→occupied | 232 | 0.906 | 0.297 | 0.515 | 0.016 |
| equip_8 | 14 | empty→occupied | 250 | 0.875 | 0.250 | 0.516 | 0.016 |
| equip_9 | 14 | empty→occupied | 269 | 1.015 | 0.297 | 0.625 | 0.015 |
| equip_10 | 14 | empty→occupied | 288 | 1.000 | 0.360 | 0.531 | 0.031 |
| unequip_10 | — | occupied→empty | 442 | 0.969 | 0.312 | 0.500 | 0.015 |
| unequip_9 | — | occupied→empty | 462 | 0.922 | 0.313 | 0.532 | 0.031 |
| unequip_8 | — | occupied→empty | 488 | 1.062 | 0.390 | 0.563 | 0.046 |
| unequip_7 | — | occupied→empty | 511 | 0.937 | 0.360 | 0.485 | 0.046 |
| unequip_6 | — | occupied→empty | 530 | 0.875 | 0.281 | 0.515 | 0.016 |
| unequip_5 | — | occupied→empty | 548 | 0.907 | 0.296 | 0.500 | 0.032 |
| unequip_4 | — | occupied→empty | 566 | 0.875 | 0.234 | 0.484 | 0.031 |
| unequip_3 | — | occupied→empty | 583 | 0.797 | 0.250 | 0.438 | 0.031 |
| unequip_2 | — | occupied→empty | 604 | 0.922 | 0.328 | 0.516 | 0.031 |
| unequip_1 | — | occupied→empty | 624 | 0.797 | 0.266 | 0.422 | 0.031 |
| unequip_0 | — | occupied→empty | 644 | 0.907 | 0.359 | 0.484 | 0.032 |

## Límites de integración

REPEAT_CURRENT no implementado: hooks fuera de ocurrencias de flow permiten que
el futuro dueño del personaje agrupe varios ciclos antes de un único cleanup.
Arena/ToT/Stages Elite no implementados. Arena deberá declarar sus terminaciones
funcionales y postcondiciones compatibles; 0% wins de un batch válido no implica
FAILED ni cierre del scope de personaje. No generalizar recovery de Meteorites.
Stop Safely requiere salida limpia conocida: un flow detenido en battle/overlay/
UNKNOWN puede necesitar intervención manual. Roster y Stop Safely están validados
offline; el smoke focal acreditó finalización normal sin Rotation.
