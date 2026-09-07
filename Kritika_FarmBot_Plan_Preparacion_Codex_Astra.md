# Kritika FarmBot — Plan maestro de preparación para Codex/Astra

**Estado del plan:** preparación pre-Codex completada; baseline congelada; brief de entrada a Astra listo  
**Fecha de referencia:** 6 de septiembre de 2026  
**Objetivo:** llegar a Codex/Astra con una base estable, decisiones cerradas y exploración previa suficiente para gastar los tokens de Codex sólo en trabajo de alto valor.  
**Fuera de scope de este bloque:** Arena y cualquier feature posterior que no sea necesaria para consolidar esta base.

---

## 1. Objetivo de esta etapa

Cerrar una base V2 sólida y observable antes de seguir agregando features.

La etapa se divide en dos momentos:

1. **Hoy y mañana, antes de Codex/Astra**
   - seguir validando estabilidad live;
   - corregir únicamente bugs concretos si aparecen;
   - terminar el trabajo preparatorio read-only / HIL que reduzca exploración futura de Codex;
   - no introducir nuevas features productivas ni refactors preventivos.

2. **Cuando vuelva Codex/Astra**
   - revisar el lote completo de cambios hecho con OpenCode/Muse;
   - cerrar checkpoint estable;
   - implementar la siguiente base transversal: observabilidad estructurada, failure evidence, SessionReport, cambios mínimos de GUI e identidad mínima;
   - dejar Eligibility como siguiente bloque arquitectónico, pero sin mezclar Arena en este scope.

---

# PARTE I — BASELINE ESTABLE ACTUAL

## 2. Política de estabilización

Hasta el checkpoint de Codex/Astra:

- runtime congelado entre pruebas;
- no hacer optimizaciones preventivas;
- no cambiar waits/guards/navigation sin failure live real;
- todo bug live concreto puede ir a Muse/OpenCode;
- fix mínimo + regresión específica + suite hardware-free + smoke mínimo cuando corresponda;
- no push final de estabilización hasta revisión de Codex/Astra;
- mantener `maintenance/opencode` como lote de trabajo de mantenimiento.

### Criterio live

Las sesiones 28/28 deben evaluarse según qué ramas recorren:

- **28/28 con Daily activas:** pase fuerte de cobertura positiva;
- **28/28 con Daily ya consumidas:** útil para idempotencia, no-op, composición y preconditions, pero no equivalente a un pase completo con ramas positivas.

Estado reciente:

- varios smokes aislados verdes;
- Daily Quests corregido;
- World Boss / Auto Battle rediseñado y validado live OFF→ON y ON persistente;
- StandardRotation migrada a sentinel visual `Create Character (+)` y validada live;
- portal notification obstruction recovery implementado y validado end-to-end para Heaven/Hell;
- suite hardware-free más reciente reportada: **1439/1439 verde**;
- semantic regression global permanece verde;
- un 28/28 completo previo terminó correctamente en **1 h 25 min** con varias Daily ya consumidas;
- un **nuevo 28/28 completo** finalizó posteriormente **sin más interrupciones** sobre la baseline actual.

**Regla:** baseline congelada hasta Codex/Astra. Sólo un failure live concreto justifica tocar runtime antes del review; no hacer tuning preventivo.

---

## 3. Bugs/fixes recientes que forman parte del baseline a revisar

Codex/Astra debe revisar el rango completo de mantenimiento, pero no rediseñarlo automáticamente.

### 3.1 Equipment Combine Relief

Fix live:

- navegación de retorno a Transmute separada del wait pasivo para limpiar guard Ethereal;
- no mezclar navegación + desaparición de indicador en la misma `VerifiedTransition`;
- revisar únicamente que el wait siga context-guarded y bounded.

### 3.2 StandardRotation / Character Select sentinel

El mecanismo anterior basado en inferir bottom mediante movimiento de scroll fue reemplazado por una autoridad visual explícita.

Contrato actual:

- Character Select usa grilla fija de 3 columnas, row-major;
- la última card es siempre `Create Character`, identificada por el símbolo `+`;
- el personaje objetivo es siempre la card inmediatamente anterior al sentinel;
- no hace falta llegar físicamente a bottom: basta con que `+` sea suficientemente visible y confirmado;
- `ObservedScroll` dejó de ser autoridad de Rotation y se conserva intacto como primitive general para otros menús scrolleables;
- geometría compartida vive en `bot/character_select_layout.py`;
- selección usa `SelectCharacterCard(center)` y postcondition dinámica con `CharacterSelectionDetector`.

Detector actual:

- `bot/create_character_sentinel.py`;
- asset `assets/ui/character-select-create-plus-template.png`;
- `TM_CCOEFF_NORMED`, threshold `0.78`;
- calibración inicial: 5 positivos, 10 negativos, mínimo positivo ~0.882, máximo negativo ~0.681;
- sin positivo live de `+` en col3; cubierto por simetría/tests, no por evidencia directa.

Fix live ya cerrado:

- un primer smoke del rediseño falló por `precondition_rejected` antes del tap;
- se corrigió únicamente el guard de `select_predecessor_character`;
- smoke posterior PASS: 1 swipe fuerte, sentinel detectado, predecessor seleccionado first-attempt, confirmación y retorno a Lobby.

Evidencia posterior:

- apareció un `sentinel_not_found_after_max_swipes` donde la card `+` quedó parcialmente visible y el símbolo no era confirmable;
- esto mostró un edge case del patrón de scroll/bound, no una razón para volver a `ObservedScroll`;
- se discutió como dirección futura una estrategia coarse→fine (hasta 2 swipes fuertes y luego swipes cortos/controlados), pero **no hay en este plan evidencia suficiente para afirmar que ese cambio haya sido implementado**;
- el 28/28 completo posterior terminó sin más interrupciones.

**Política pre-Codex:** no tocar Rotation preventivamente. Astra debe revisar el estado real del repo y este edge case durante el review del lote; sólo reabrir antes si reaparece live.

### 3.3 Summon Pet Daily

Contrato live deliberadamente simplificado:

- Manage es entrada natural;
- Daily badge se decide en Manage;
- una vez en Summon, no depender de Daily persistente;
- decidir Epic vs Premium por semántica;
- tap selector Epic/Premium;
- delay fijo **0.25 s**;
- tap directo a `1(Open)`;
- no re-observar dropdown;
- luego esperar sólo outcomes reales;
- mismo comportamiento en retry post-relief;
- Auto selector/dropdown waits eliminados deliberadamente porque causaban falsos timeouts.

**Importante para auditorías:** el doble tap con 0.25 s es **INTENTIONAL_DESIGN validado HIL**, no un bug a corregir automáticamente.

Epic availability:

- ROI estable excluye contador variable `N(Open)`;
- validado live con `8(Open)` y corpus previo con `10(Open)`;
- no generalizar más allá de evidencia observada.

### 3.4 Daily Quests

Dos fixes ya incorporados al baseline:

1. **Retry bounded de selección de Daily tab**
   - si ya está Daily activo → 0 taps;
   - si `RESOLVED screen.quests` y no Daily → tap;
   - reobservar ~1 s;
   - repetir mientras siga Quests limpio y no Daily;
   - UNKNOWN/AMBIGUOUS no autoriza tap;
   - contexto resuelto incompatible aborta;
   - timeout total bounded ~15 s;
   - regresión explícita: primer tap ignorado → segundo tap exitoso.

2. **Precondition contractual corregida**
   - `DailyQuestsFlow` declaraba erróneamente `screen.pets_manage`;
   - corregido a `SCREEN_LOBBY`;
   - regresión de sesión aislada verifica que no se emite `precondition.open_pets`.

### 3.5 World Boss / Auto Battle

Contrato final actual:

- Auto Battle es auxiliar: mejora recompensa, **no es necesario para completar World Boss ni Daily**;
- nunca debe causar `WorldBossFlow FAILED` por sí solo;
- check ligero por batalla, no una sola vez por sesión, porque un tap físico podría desactivarlo;
- OFF confirmado → intentar activar;
- ON / UNKNOWN / timeout / post-tap inconcluso → continuar;
- UNKNOWN/AMBIGUOUS nunca autoriza tap;
- contexto `RESOLVED` contradictorio sí puede abortar;
- Timer es auxiliar para dimensionar espera;
- timer inconcluso usa fallback bounded a 90 s;
- `Raid Complete` / postcondición real del combate es la autoridad final.

Optimización implementada:

- detector temporal completo era demasiado caro porque `perception.analyze()` costaba ~674 ms/frame;
- nueva adquisición focused temporal harvest usa frames crudos frescos de Auto Battle;
- secuencias estrictamente crecientes;
- duplicados/stale no cuentan;
- misma ventana / mediana / thresholds OFF/ON;
- gate de visibilidad verde `AUTO_BATTLE_VISIBLE_GREEN_MIN=0.20` antes de confiar OFF;
- guard semántico completo fresco antes de cualquier tap;
- post-tap re-harvest best-effort;
- path exhaustivo `ensure_on()` permanece para tooling/validación;
- `WorldBossFlow` no hace CV/captura directa.

Validación live:

- OFF deliberado → bot activó correctamente Auto Battle;
- ON persistente → 0 taps, camino rápido;
- ambos smokes verdes.

Beneficio principal:

- robustez;
- eliminación de falsos aborts;
- reducción fuerte de trabajo de percepción global/CPU durante Auto Battle;
- no asumir ahorro equivalente en duración total de World Boss, porque la batalla tiene duración mínima.

### 3.6 Portal notification obstruction recovery

Failure live concreto:

- una notificación Heaven/Hell no modelada podía aparecer después de acciones y obstruir ROIs en Battle Mode Select, World Boss, Guild, Pets y otros screens;
- podía surgir antes, durante o después de un flow, incluso al verificar una postcondition;
- el resultado observado fue `UNKNOWN`/timeout y failure de precondition en Summon Pet.

Contrato implementado:

- portal farming/portal flow sigue fuera de scope;
- Heaven/Hell se modelan sólo como una **obstrucción descartable**;
- hook genérico `ObstructionRecovery.attempt()` dentro de `VerifiedTransition`;
- probe on-demand sobre `frame.image`, fuera del pipeline productivo de Perception;
- dismiss mediante `DismissPortalNotification` por la capa normal de acciones;
- reobserve + verificación bounded de desaparición + reevaluación de la condición original;
- no repetir automáticamente la acción productiva;
- `_current_clean_context` y navegaciones relevantes reutilizan el mismo helper;
- sin side-effects en Perception/ContextResolver y sin lógica Heaven/Hell dentro de flows.

Detector/calibración final:

- ROI `(0.270, 0.085, 0.360, 0.175)`;
- thresholds sin cambios: `confirmed >= 0.80`, `absent <= 0.65`, banda intermedia INCONCLUSIVE fail-safe;
- scorer max sobre tres variantes de template: Heaven base, Hell y Guild;
- cobertura final reportada: 11 positivos `0.915–1.0`, 6 negativos `<=0.564`, corpus de 603 frames `<=0.489`;
- 17/17 casos de adquisición verificados.

Action target / fade:

- target inicial `(0.322, 0.129)` estaba mal calibrado y abría Quick Menu;
- target corregido live: `(0.3434, 0.1397)`, medido sobre núcleo rojo estable de la X;
- el dismissal tiene fade/delay visual; `PortalObstructionRecovery` usa settle pasivo bounded de 5 s para evitar un segundo tap prematuro;
- smoke productivo Guild PASS: CONFIRMED → exactamente 1 tap → settle salió anticipado en ABSENT → Guild limpio;
- validación end-to-end también ejercida en Pets.

Estado:

- failure original resuelto end-to-end;
- suite final reportada después de estos cambios: **1439/1439**;
- raws temporales preservados en `artifacts/portal_notification_acquisition/`;
- no reabrir preventivamente salvo nueva evidencia live.

Known limitation:

- varios flows todavía usan `wait_until` crudo fuera del seam de `VerifiedTransition`; no migrarlos antes de Astra sin failure live concreto. Durante review, Astra puede decidir si conviene normalizar esta cobertura como cambio cross-cutting.

---

# PARTE II — QUÉ APRENDIMOS DE MUSE / OPENCode

## 4. Rol operativo futuro de Muse Spark 1.3

Muse ya demostró suficiente capacidad para ampliar su responsabilidad más allá de bugs triviales.

### Delegable a Muse

- bugs live concretos;
- análisis de logs;
- fixes acotados;
- regresiones hardware-free;
- adquisiciones HIL por chat/steer;
- curación de evidencia;
- negativos difíciles;
- ROI/calibración con corpus suficiente;
- detectores puntuales;
- pequeñas optimizaciones técnicas bien delimitadas;
- auditorías read-only específicas.

### Reservado principalmente a Codex/Astra

- arquitectura nueva;
- cambios cross-cutting;
- contratos nuevos de runtime;
- Structured Observability;
- Failure Evidence architecture;
- SessionReport;
- identidad e integración transversal;
- Eligibility/Routines;
- cambios importantes en SessionRunner/Rotation;
- review/checkpoint final del lote Muse/OpenCode.

### Dinámica recomendada

Una sesión Muse por problema/tarea significativa.

Razón:

- ~1M tokens por sesión gratuita;
- auditoría general: ~78k tokens, 3m44s;
- mapa de observabilidad: ~53k tokens, 3m38s;
- costo de contexto no es preocupación si el scope es acotado por sesión;
- evitar sesiones gigantes acumulativas.

---

# PARTE III — AUDITORÍA READ-ONLY DE MUSE

## 5. Hallazgos que Codex/Astra debe conocer

La auditoría global de Muse reconstruyó correctamente la arquitectura y evitó los errores conceptuales que había cometido Nemotron.

### Findings útiles

#### F1 — Summon Pet double tap

Muse lo marcó como riesgo porque no hay re-observación del dropdown.

**Resolución humana ya cerrada:** no corregir automáticamente.

Es diseño deliberado HIL:

- dropdown inmediato;
- `1(Open)` garantizado después de card disponible;
- waits intermedios anteriores producían falsos timeouts;
- delay 0.25 s agregado sólo como settle conservador.

Codex puede revisarlo, pero debe partir de que es **INTENTIONAL_DESIGN**, no deuda automática.

#### F2 — `SummonPetDailyFlow`: duplicados/literales

Muse encontró:

- métodos privados duplicados/sombreados;
- algunos `"screen.*"` literales en vez de constantes de catálogo.

Impacto actual bajo/nulo, pero sí es deuda de mantenimiento.

**Acción futura:** Codex/Astra revisa y decide si limpiar después del checkpoint. No modificar antes por estabilidad.

#### F3 — `ARCHITECTURE.md` registry stale

Lista 6 flows y falta `summon_pet_daily`.

**Acción:** corregir documentación durante checkpoint de Codex/Astra.

#### F4 — Raid Complete overlay-only

Muse lo reconoció correctamente como **INTENTIONAL_DESIGN**.

No cambiar sin evidencia nueva.

#### F5/F6 — nombres semánticos muertos / allocations de `VerifiedTransition`

Optimización/cosmética solamente.

No prioridad del checkpoint salvo que Codex quiera limpieza trivial sin riesgo.

### Valor principal de la auditoría

Muse entendió correctamente:

- natural contexts;
- que flows no tienen que volver todos a Lobby;
- que `MinimalPreconditionEnsurer` normaliza entre postcondition y siguiente precondition;
- World Boss general-purpose vs Daily eligibility externa futura;
- tolerar badge Daily no implica usarlo como guard de negocio;
- Rotation != Flow.

Esto aumenta la confianza en Muse como maintainer técnico, pero Codex/Astra sigue siendo reviewer arquitectónico final.

---

# PARTE IV — STRUCTURED OBSERVABILITY / FAILURE EVIDENCE / SESSIONREPORT

## 6. Trabajo preparatorio YA COMPLETADO por Muse

Muse hizo un mapa read-only específico de observabilidad.

Conclusión central:

**No hace falta crear observability desde cero.** Ya existe:

```text
RuntimeEventStream
  → RuntimeEvent
  → JsonLineEventConsumer
  → JSONL persistente
```

El `.log` actual productivo ya es JSONL machine-oriented; consola/GUI son vistas filtradas.

Por lo tanto, la dirección acordada es **evolucionar el sistema existente**, no crear streams paralelos.

### Datos ya existentes

- `RuntimeEventStream` con fan-out y `now` inyectable;
- `RuntimeEvent` estructurado;
- `JsonLineEventConsumer` persistente;
- `RuntimeSnapshot` = frame + observations + resolved state + facts + geometry;
- `SessionResult`, `SessionCharacterResult`, `FlowResult`, `FlowEvent`;
- `ControlledWaitResult` con elapsed/poll_count;
- `FactEvidence` / `RuntimeFact` con sequence/timestamp/confidence/quality;
- `VerifiedTransitionResult.final_snapshot`;
- GUI worker/queue ya desacoplados del runtime;
- fakes y clocks inyectables para tests hardware-free.

### Gaps detectados

- sin `run_id/session_id` propagado;
- sin correlation IDs por operation/transition;
- duplicación sistemática de business events entre flow/session/productive runtime;
- failure causes como strings;
- `VerifiedTransition` y `RuntimeObserver.wait_until` pierden elapsed/poll_count/historial útil;
- `FactReader` no emite varios outcomes negativos como eventos;
- `PerceptionEngine` no mide costo runtime;
- no existe ring productivo de últimos snapshots;
- no existe Failure Evidence productivo con PNG/snapshot;
- SessionReport actual existente en tooling no es el SessionReport de sesiones productivas;
- GUI sólo recibe un `GuiExecutionResult` pequeño.

---

## 7. Decisiones de arquitectura YA CERRADAS para Codex/Astra

### 7.1 Fuente machine única

**El JSONL existente evolucionado será la fuente machine canónica.**

No crear:

- telemetry stream separado;
- logs humanos paralelos;
- segunda fuente de verdad para SessionReport.

Posible rename conceptual futuro: `events.jsonl`, pero filename exacto no es decisión prioritaria.

### 7.2 Único output humano relevante

**SessionReport** será la proyección humana principal.

No mantener un `.log` diseñado para lectura humana.

Console/GUI pueden seguir mostrando eventos filtrados para debugging, pero la persistencia se optimiza para agentes/máquinas.

### 7.3 SessionReport

Debe ser **derivado de resultados/eventos estructurados**, nunca una fuente paralela.

Debe distinguir claramente:

- complete;
- Daily/business incomplete;
- technical failure;
- cancelled.

Debe mostrar por personaje razones relevantes, sin información de percepción/sequence/retries salvo referencia diagnóstica mínima.

### 7.4 Failure cause

Migrar hacia causa estructurada, inicialmente de forma aditiva para no romper compatibilidad:

```json
{
  "type": "state_wait_timeout",
  "exception_type": "RuntimeWaitTimeout",
  "message": "...",
  "flow": "daily_quests",
  "step": "select_daily_tab",
  "sequence": 5173,
  "evidence_ref": "failure_..."
}
```

Preservar strings actuales mientras sea útil para compatibilidad/tests.

### 7.5 Failure Evidence

Sólo para **technical failure terminal o diagnóstico realmente relevante**.

No generar bundles por timeouts internos manejados correctamente.

Ejemplo:

- Auto Battle timeout best-effort → NO bundle;
- `DailyQuestsFlow` terminal `state_wait_timeout` → SÍ bundle.

Baseline inicial acordado:

- últimos **3 RuntimeSnapshots**;
- 2–3 PNG bounded/downscaled si resulta razonable;
- snapshot/perception/context serializable;
- `failure.json` / summary estructurado;
- referencia desde el evento de failure;
- política bounded y almacenamiento temporal.

No generar normalmente en `CANCELLED` voluntario.

### 7.6 Telemetría futura

100% local/offline.

```text
events JSONL
+ summaries
→ análisis posterior
```

No sink remoto en esta etapa.

### 7.7 Polling/events densos

Persistir como `DEBUG`.

El JSONL puede conservarlos aunque GUI normal no los muestre.

### 7.8 Métricas futuras importantes

Diseñar eventos desde ahora para permitir luego:

- flow duration p50/p95;
- transition duration p50/p95;
- retry rate;
- timeout rate;
- UNKNOWN/AMBIGUOUS rate;
- tiempo de navegación;
- tiempo en waits;
- perception analyze calls;
- **perception.analyze elapsed total**;
- costo computacional por flow/decision;
- bottlenecks.

El caso Auto Battle mostró por qué medir sólo duración total de sesión no alcanza: una optimización puede ahorrar CPU/recursos sin reducir duración de una batalla bounded por gameplay.

---

## 8. Decisiones que AÚN debe cerrar Codex/Astra en Observability

Estas preguntas quedan deliberadamente abiertas para diseño de alto nivel:

1. Cómo propagar `run_id/session_id/character_index/flow/operation_id` sin ensuciar todas las firmas.
   - Preferencia inicial: EventSink contextual/bound en vez de repetir fields manualmente.

2. Cómo eliminar duplicación de business events y definir un evento canónico único.

3. Dónde vivir exactamente el ring `deque[RuntimeSnapshot](maxlen=3)`.
   - No debe acoplar Capture/Observer de forma incorrecta.

4. Writer de Failure Evidence:
   - async/sync;
   - downscale/compresión;
   - límites de tamaño/tiempo;
   - ubicación de artifacts.

5. Cómo enriquecer `VerifiedTransition` / waits con elapsed/poll_count/evidence sin convertir JSONL en logging por-frame masivo.

6. Cómo incorporar `perception.analyze` timing con overhead mínimo.

7. Si `level/component` sigue derivado parcialmente o pasa a ser explícito en eventos clave.

8. Compatibilidad y migración de `SessionResult.failure_cause`, `GuiExecutionResult.error`, etc.

---

# PARTE V — GUI / SESSIONREPORT / IDENTIDAD

## 9. Cambios funcionales de GUI YA DEFINIDOS

La GUI seguirá siendo provisional; estética no prioritaria.

### 9.1 SessionReport

Prioridad máxima de UI.

Debe aparecer al finalizar sesión y ser legible sin interpretar logs.

Ejemplo conceptual:

```text
Session completed — 28/28
Duration: 01:29:58

25 complete
3 daily incomplete
0 technical failures

Character 4
- Send Stamina Daily incomplete: no eligible friends
```

### 9.2 Run Selected Flows

Reemplazar funcionalmente `Run Flow Once` por una operación de debugging:

- ejecutar **los flows seleccionados**;
- sobre el personaje actual;
- sin rotation;
- respetar el orden elegido en GUI.

### 9.3 Default flow order

La GUI debe reflejar/permitir el orden operativo elegido.

Orden de registry actual auditado:

```text
black_market
→ world_boss
→ send_stamina
→ summon_pet_daily
→ daily_quests
→ mailbox
→ guild_check_in
```

**Pendiente humano:** confirmar si este será también el orden default final deseado o si se quiere cambiar antes de Codex.

### 9.4 Pause/resume

**Diferido.**

No meter en este bloque.

---

## 10. Identidad mínima — contrato YA DEFINIDO + preparación HIL COMPLETADA

Objetivo futuro:

- reconocer identidad mínima para SessionReport;
- usar `personal_name` observado como lookup hacia `class_name`;
- exponer la clase como identidad canónica de display;
- reconocimiento no-bloqueante;
- fallback `Character N`;
- no perfiles complejos;
- no identity-aware rotation todavía.

La identidad se integra después de que exista la base de SessionReport/observability.

### Seam existente confirmado por mapa GUI

El repo ya tiene una base compatible:

- `CharacterContext(name, name_confidence)`;
- `SessionRunner(..., character_context_factory)`;
- si el factory falla, degrada a identidad vacía en vez de fallar la sesión;
- `ProductiveRuntime` todavía no inyecta el factory.

Esto preserva el requisito de identidad no-fatal sin diseñar una segunda vía paralela.

### Approach de reconocimiento cerrado para esta etapa

No reconocer por skin/apariencia: skins personalizadas pueden compartirse y son visualmente poco robustas.

No usar ahora el icono de Character Select como identificador principal: tiene overlay dinámico de fuego violeta y queda reservado para necesidades futuras de búsqueda/rotation específica.

Señal preferida para identidad mínima:

```text
Lobby
→ leer personal_name en HUD superior izquierdo
→ lookup exacto personal_name → class_name
→ display class_name
→ fallback Character N si no se reconoce
```

El ground truth humano completo de 28 personajes ya existe y debe preservarse exactamente, incluyendo Unicode CJK y capitalización. Correcciones confirmadas: `Drakennn15` y `Drakennn17` llevan tres `n`.

### Acquisition / benchmark ya completado

Muse adquirió **84 raws** de Lobby (28 personajes × 3), 2712×1224, sin modificar runtime, en:

`artifacts/identity_name/`

Tamaño aproximado: **375 MB** temporales.

ROI común candidata del nombre:

`(0.080, 0.020, 0.190, 0.062)`

RapidOCR 3.9.2, exact-match de string completo:

- **75/84 = 89.3%**;
- **25/28 personajes perfectos (3/3)**;
- fallos sistemáticos únicamente en:
  - `DRAKEN一BK`: `一 → '-'`;
  - `DRAKEN二DB`: `二 → '-' / omitido`;
  - `DRAKEN三BB`: `三 → '='`;
- preprocessing simple no resolvió esos tres glifos.

Closed-set NCC grayscale:

- **56/56 top-1 correcto** usando seq1 como referencia y seq2/seq3 como test;
- márgenes peligrosamente bajos en varios nombres Latin similares (`10/16/18`, `08/06`, `25/26`) y ~0.04 en `二/三`;
- por lo tanto no adoptar closed-set puro como solución productiva sin diseño posterior.

### Decisión para Astra

No implementar identidad durante Fase 0. Cuando llegue Fase 5, Astra debe decidir entre:

1. OCR + handling explícito/validado para `一/二/三`;
2. matcher acotado sólo como fallback;
3. otro motor OCR con mejor reconocimiento de CJK pequeño.

Mantener lookup exacto `personal_name → class_name` y fallback no-bloqueante.

### Curación/storage pendiente

Antes de borrar raws:

- promover 1–2 crops representativos por personaje + manifest con GT exacto;
- preservar especialmente `一/二/三` y casos de contaminación por power como regresión de ROI;
- luego purgar redundantes temporales.

---

# PARTE VI — ELIGIBILITY

## 11. Decisiones conceptuales YA CERRADAS

Eligibility sigue en scope de base futura, pero **después** de Observability/GUI/SessionReport/identidad.

Separación:

- **Routine** = ordered flows + eligibility;
- **Eligibility** = si una rutina quiere ejecutar un flow ahora;
- **Flow** = cómo ejecutar ese flow.

### World Boss

- `WorldBossFlow` es general-purpose;
- NO debe depender internamente del Daily badge;
- Daily routine eligibility se decide afuera;
- badge Daily real está en Battle Mode → World Boss Select;
- sapphires se leen en Lobby;
- evitar diseño torpe navigate-to-check → back → navigate otra vez.

### SummonPetDailyFlow

Distinto de World Boss:

- es inherentemente Daily-specific;
- puede seguir chequeando su Daily internamente.

### Posible resultado futuro

Considerar `SKIPPED_NOT_ELIGIBLE` o equivalente para representar eligibility externa sin mezclarla con failure técnico.

### Pendiente Codex/Astra

Diseñar el **mínimo consumer real** de Eligibility, probablemente empezando por World Boss Daily vs World Boss general, sin crear framework abstracto sin consumidor.

**No implementar Arena dentro de este bloque.**

---

# PARTE VII — TRABAJO QUE SÍ PODEMOS ADELANTAR HOY/MAÑANA

## 12. Prioridad A — estabilidad live

Estado al cierre pre-Codex:

1. **28/28 completo finalizado sin más interrupciones** sobre la baseline actual;
2. suite hardware-free más reciente reportada: **1439/1439**;
3. PortalObstructionRecovery cerrado end-to-end;
4. Rotation tuvo un edge case posterior de sentinel parcial, pero el siguiente 28/28 completo no volvió a interrumpirse;
5. no se planifica más tuning antes de Astra.

**Política hasta Codex:** congelar estado. Si aparece otro failure real antes del reset, aislar sólo ese bug; de lo contrario, esperar.

No tocar findings cosméticos durante esta fase.

---

## 13. Prioridad B — mapa read-only de GUI

**COMPLETADO por Muse, read-only.**

Hallazgos principales preparados para Astra:

- estructura equivalente a MVC: `gui_model.py` / `gui_controller.py` / `tools/gui.py`;
- worker thread + queue desacoplados de Tk;
- `Run Session` termina aplanando `SessionResult` a un `GuiExecutionResult` pequeño y pierde detalle por personaje/flow;
- `Run Flow Once` ejecuta sólo una definición y el runtime no tiene hoy un path de múltiples flows sin Rotation;
- reusar `run_session(count=1)` sería incorrecto porque rotaría;
- la selección/reorder visible de flows sí define el orden productivo real;
- timer actual es presentación pura y puede preservarse;
- seam mínimo de display de un futuro SessionReport: `KritikaFarmBotGui._finish`;
- seam de construcción/integración más natural a revisar por Astra: `GuiRuntimeController._worker`, donde existe el resultado crudo antes del aplanado;
- existe `CharacterContext` + `character_context_factory` como seam natural de identidad no-bloqueante.

Preguntas para Astra, no para resolver pre-checkpoint:

- `Run Selected Flows`: loop de `run_flow` vs nuevo `run_flows_once`;
- SessionReport: adjunto al RESULT desde resultado/eventos estructurados vs reconstrucción post-hoc;
- punto exacto de inyección del identity factory;
- default flow order final antes de tocar GUI.

---

## 14. Prioridad C — adquisición HIL de identidad

**COMPLETADA.**

Resultado:

- 28/28 personajes cubiertos;
- 3 frames de Lobby por personaje;
- 84 raws full-size (~375 MB);
- mapping humano exacto `personal_name → class_name`;
- benchmark OCR vs closed-set completado;
- ROI común candidata identificada;
- ninguna implementación productiva realizada.

La evidencia es suficiente para que Astra tome la decisión técnica durante Fase 5 sin repetir acquisition básica.

### Política storage

- `artifacts/identity_name/` sigue ignored y debe preservarse hasta curación;
- promover luego 1–2 crops representativos por personaje + manifest;
- preservar casos raros/difíciles;
- cleanup sólo después de esa promoción.

---

## 15. Prioridad D — inventario Git + brief final de Astra

**COMPLETADO.**

Inventario Git read-only final:

- repo: `D:/PROYECTOS/kritika-farmbot`;
- branch: `maintenance/opencode`;
- HEAD/base: `45f6edee20db8fc05831ca8c27ca22049936d42a` (`45f6ede`);
- `main == maintenance/opencode == origin/main` conocido en ese hash;
- `main..maintenance/opencode` = **EMPTY, 0 commits**;
- staged: 0;
- modified unstaged: **36**;
- untracked: **22 archivos** (21 entradas de status por directorio portal colapsado);
- tracked diff aproximado: **4443 insertions / 1318 deletions**;
- sin conflictos ni merge/rebase/cherry-pick en progreso;
- branch actual no tiene upstream; información de `origin` puede estar stale porque no se hizo fetch.

**Consecuencia crítica:** el lote OpenCode/Muse vive 100% en el working tree sucio sobre `45f6ede`; Astra NO debe intentar revisar `main..maintenance/opencode` como rango de commits porque perdería el 100% del lote.

Unidad real de review:

```text
BASE = 45f6edee20db8fc05831ca8c27ca22049936d42a
LOT  = git diff HEAD + untracked relevantes
```

Seguridad al iniciar Astra:

- NO checkout/switch/reset/restore/clean/stash/rebase/merge/cherry-pick antes de entender el lote;
- NO borrar untracked automáticamente;
- NO tocar `wip/session-report-codex` sin coordinación;
- clasificar antes de checkpoint los scripts raíz inciertos `check_eval.py`, `fix_tests.py`, `test_live.py`, `test_wait.py`;
- `git diff --check` reporta trailing whitespace en `tests/test_session.py`; hygiene menor, no deuda semántica;
- `Kritika_FarmBot_Plan_Preparacion_Codex_Astra.md` es doc operativo untracked, no runtime.

Temporales ignored relevantes:

- `artifacts/portal_notification_acquisition/` ~74 MB;
- `artifacts/identity_name/` ~375 MB.

El brief corto de entrada a Astra ya está preparado y debe iniciar por review read-only/correctness del working tree antes de cualquier commit o trabajo de Structured Observability.

---

# PARTE VIII — ORDEN DE TRABAJO CUANDO VUELVA CODEX/ASTRA

## 16. Secuencia propuesta

### Fase 0 — Review del lote de mantenimiento

Astra **no tiene un rango de commits que revisar**: `main..maintenance/opencode` está vacío.

Debe revisar read-only:

```text
base: 45f6edee20db8fc05831ca8c27ca22049936d42a
+ git diff HEAD
+ archivos untracked relevantes
```

Antes de cualquier operación Git destructiva o checkpoint, revisar:

- correctness;
- contracts;
- separación de capas;
- tests;
- docs;
- fixes OpenCode/Muse;
- findings de auditoría relevantes;
- clasificación de scripts/root files inciertos;
- estado real de los 36 modified + 22 untracked.

Puntos explícitos a revisar:

- Equipment Ethereal wait guard;
- StandardRotation sentinel `Create Character (+)`, geometría compartida y edge case de card parcial / search bound;
- confirmar desde código si existe o no algún cambio coarse→fine posterior al último reporte;
- Summon Pet double-tap como intentional HIL design;
- métodos duplicados/literales en Summon Pet;
- Daily Quests retry + Lobby precondition;
- World Boss Auto Battle focused harvest / visibility gate / policy no-fatal;
- PortalObstructionRecovery: detector multi-template Heaven/Hell/Guild, target X corregido, settle bounded y cobertura parcial frente a `wait_until` crudo;
- direct Lobby→Guild realmente verified;
- consistencia de `QUICK_MENU_ACCESSIBLE` entre ensurer y rotation;
- `ARCHITECTURE.md` registry stale.

Resultado:

- fixes obligatorios si existe bug real;
- suite verde;
- checkpoint de estabilización;
- push/merge final sólo después de review.

### Fase 1 — Structured Observability v1

Objetivo:

- evolucionar RuntimeEventStream/JSONL existente a fuente machine canónica;
- añadir IDs/correlation/contexto;
- eliminar duplicación semántica;
- failure causes estructuradas;
- timings útiles de transitions/waits/perception;
- preservar hardware-free tests y zero-impact gameplay si falla un sink.

No hacer analytics/dashboard todavía.

### Fase 2 — Failure Evidence v1

- ring bounded de últimos ~3 RuntimeSnapshots;
- failure bundle sólo terminal/relevante;
- PNG bounded/downscaled si corresponde;
- snapshot/perception/context serializable;
- evidence refs en eventos;
- política de retención/cleanup compatible con almacenamiento actual.

### Fase 3 — SessionReport

- derivado de canonical events/results;
- humano y conciso;
- complete / business incomplete / technical failure / cancelled;
- reasons por personaje;
- referencias mínimas a diagnostics cuando exista failure.

### Fase 4 — GUI funcional mínima

- mostrar SessionReport;
- `Run Selected Flows` actual character / no rotation;
- mantener timer actual;
- confirmar/aplicar default flow order;
- estética fuera de scope;
- pause/resume diferido.

### Fase 5 — Identidad mínima

- integrar mapping class ↔ personal name;
- reconocimiento no-bloqueante;
- fallback `Character N`;
- conectar identidad a SessionReport;
- no perfiles/rotation-aware identity todavía.

### Fase 6 — Eligibility mínima

- diseñar/implementar primer consumer real;
- separar Routine eligibility de Flow execution;
- World Boss Daily como caso principal;
- mantener WorldBossFlow general-purpose;
- evitar framework sobredimensionado.

### STOP de este scope

Después de Eligibility, reevaluar estado y recién entonces abrir siguiente milestone.

**Arena explícitamente fuera de este plan.**

---

# PARTE IX — COSAS QUE NO DEBEN PERDERSE

## 17. Invariantes de proceso

- prompts a Codex/Astra cortos;
- referir a `AGENTS.md`, no repetir baseline entero;
- incluir sólo delta, decisiones cerradas, constraints y acceptance;
- flows se discuten antes de reescribir reglas;
- smoke live sólo cuando sea necesario y lo más corto posible;
- usuario opera GUI para live smoke;
- HIL por chat/steer, una condición por vez;
- no asumir ADB/Python en PATH;
- no push salvo decisión explícita;
- código/tests = implementación real;
- docs = contratos/estado según jerarquía existente;
- UNKNOWN jamás autoriza input;
- retries bounded/state-guarded;
- no abstractions sin consumidor/evidencia.

---

## 18. Invariantes de storage

- raws temporales;
- evidencia curada/manifests/productive assets = persistente;
- no repetir incidente de `artifacts` >30 GiB;
- para acquisition Muse, medir primero consumo real;
- cleanup sólo después de revisar qué evidence es representativa/rare;
- Failure Evidence futura debe ser bounded y sólo ante failure técnico relevante.

---

# PARTE X — CHECKLIST PRE-CODEX

## 19. Cierre pre-Codex — 6 de septiembre

- [x] Completar un nuevo 28/28 sobre baseline actual: **PASS, sin más interrupciones**.
- [x] Mantener suite hardware-free verde: **1439/1439** última cifra reportada.
- [x] Auditoría global read-only Muse completada.
- [x] Mapa read-only de observabilidad Muse completado.
- [x] Resolver failure transversal de portal notification: Heaven/Hell + X calibrada + settle bounded + live end-to-end.
- [x] Preservar raws temporales de portal acquisition para review/curación posterior.
- [x] Mapa read-only GUI completado.
- [x] Acquisition HIL identidad 28/28 + benchmark OCR/closed-set completados.
- [x] Inventario exacto Git/working tree completado.
- [x] Determinar unidad real de review: `45f6ede + working tree`; `main..maintenance/opencode` vacío.
- [x] Brief corto de entrada a Astra preparado.
- [x] Decidir no introducir más tuning preventivo antes de Astra.
- [ ] **Durante Fase 0 Astra:** clasificar scripts raíz inciertos antes del checkpoint.
- [ ] **Durante Fase GUI Astra:** confirmar default flow order final.
- [ ] **Durante Fase Identity Astra:** decidir OCR/fallback a partir del corpus 28/28.

**STOP pre-Codex:** preparación completada. Mantener baseline congelada y esperar Astra, salvo failure live nuevo y concreto.
---

# PARTE XI — PUNTOS QUE REQUIEREN CONFIRMACIÓN HUMANA

## 20. Decisiones humanas no bloqueantes que pasan a Astra

### A. Default flow order final

El registry actual es:

```text
black_market
→ world_boss
→ send_stamina
→ summon_pet_daily
→ daily_quests
→ mailbox
→ guild_check_in
```

No hace falta resolverlo antes del reset. Confirmarlo cuando Astra llegue a la fase GUI, antes de modificar el orden default.

### B. Estrategia productiva de identidad

La acquisition básica ya está completa (28/28 × 3 frames). La decisión que pasa a Astra no es cuánto capturar inicialmente, sino **qué recognizer productivo usar**:

1. OCR + handling validado de `一/二/三`;
2. matcher fallback acotado;
3. motor OCR alternativo con mejor CJK pequeño.

Cualquier opción debe conservar exact lookup `personal_name → class_name`, Unicode sin transliteración y fallback no-bloqueante `Character N`.

Estas decisiones no bloquean el review/checkpoint inicial de Codex/Astra.

---

# Resumen ejecutivo

La prioridad hasta Codex/Astra no es agregar features: es **consolidar una base estable, observable y fácil de diagnosticar**.

Trabajo ya adelantado:

- baseline live muy estabilizado;
- bugs concretos recientes resueltos;
- World Boss/Auto Battle simplificado y optimizado;
- auditoría global Muse;
- mapa técnico completo de observability;
- mapa read-only GUI completo;
- acquisition/benchmark de identidad 28/28 completo;
- inventario Git/worktree exacto completo;
- decisiones principales de Structured Observability / Failure Evidence / SessionReport cerradas;
- brief corto de entrada a Astra preparado;
- rol Muse vs Astra definido.

Estado al cierre pre-Codex:

1. nuevo 28/28 completo verde, sin más interrupciones;
2. suite hardware-free reportada en **1439/1439**;
3. PortalObstructionRecovery cerrado end-to-end para Heaven/Hell;
4. StandardRotation mantiene sentinel visual como autoridad; existe un edge case observado de card parcial que Astra debe revisar contra el repo real, pero no se hará tuning preventivo ahora;
5. GUI ya está mapeada y sus seams/riesgos están documentados;
6. identidad tiene ground truth + 84 raws + benchmark OCR/closed-set, sin implementación productiva;
7. `maintenance/opencode`, `main` y `origin/main` conocido apuntan a `45f6ede`; el lote real está **100% sin commit en working tree** (36 modified + 22 untracked);
8. `main..maintenance/opencode` está vacío, por lo que Astra debe revisar `45f6ede + git diff HEAD + untracked`, no un rango de commits;
9. no hay commit/push final de estabilización.

**No queda trabajo preparatorio relevante antes de Astra.**

Orden al volver Codex/Astra:

```text
Review mantenimiento
→ checkpoint estable
→ Structured Observability v1
→ Failure Evidence v1
→ SessionReport
→ GUI funcional mínima
→ identidad mínima
→ Eligibility mínima
→ reevaluar milestone
```

**Arena queda explícitamente fuera de este scope.**
