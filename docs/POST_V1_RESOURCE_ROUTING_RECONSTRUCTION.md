# Post-V1 — Resource Routing / Monster Wave Preparation (reconstruction)

Planning-only frontier. No runtime implemented, no code/tests/assets/manifests touched.

## 0. Estado V1 de partida

- Rama `rebuild/stable-baseline` @ `a4acad5` (`docs: close v1 checkpoint after post-refactor 28/28`).
- V1 cerrada: `REFACTOR_COMPLETE = YES` (`04640c2`), hardware-free **2459/2459**, benchmark post-refactor **28/28 PASS** (76:59, 196/196 flows, 768/768 transitions), detalle en `docs/POST_REFACTOR_28_28_BENCHMARK.md`.
- Caveats vigentes (`CONTEXT.md`): Monster Wave OFF en el benchmark (path omitido), 0 reliefs con trabajo, scopes nuevos Daily-progress/MW-eligibility no ejercidos.
- Límites vigentes (`CONTEXT.md`, `ARCHITECTURE.md`): Trading, Craft, Treasure, Equipment Sell e Inventory Relief Chain general **no** forman parte del runtime estable. MW estable = una sola operación SKIP en MAX por llamada, compra de tickets configurable, sin Start manual / Auto Battle / countdown / farming loop (`docs/MONSTER_WAVE_SKIP.md`, `bot/monster_wave_activity.py`).
- Doctrina vigente: `ARCHITECTURE.md` §§ Navegación de listas largas / Relief por presión / Arquitectura no aceptada; `docs/HISTORY.md` rollback y reconstrucción.

## 1. Reconstrucción Astra (read-only)

Preservado en `archive/inventory-relief-experimental` y `feature/inventory-relief-chain`, tip `024ff8e`. Base `71340f5`. Cero cherry-picks al baseline (ver `docs/HISTORY.md:110-121`).

| commit | subject | alcance | idea |
|---|---|---|---|
| `4612fd8` | Implement inventory relief chain with caller-driven Equipment recovery | 97 files, +5360/−59; 37 assets `inventory-relief/*`, `bot/{trading_operations,craft_operations,craft_sink,treasure_operations,treasure_sink,equipment_relief,sell_*​,inventory_relief_*}`, `docs/INVENTORY_RELIEF_CHAIN.md`, manifest 2123 líneas | Fundacional: `TradingReliefFlow` PASS1 Keys+Materials → sinks Craft→Treasure → PASS2; Equipment caller-driven (Combine→retry caller→Sell autorizado); `ReliefFactReader` OCR consenso |
| `9e5e9fc` | Fix Trading search tolerance and adaptive key promotion order | 9 files; `trading_operations.py`, `docs/INVENTORY_RELIEF_SMOKE_FIX.md`, `tests/test_trading_search_and_order.py` | Smoke 20260910T163429: overshoot swipe deja fila parcial → gesto `0.95*(n-1)*pitch`, tolerar overlap con progreso, orden adaptativo Keys por aritmética `499-silver` |
| `f568c25` | Scope runtime perception and streamline relief decisions | 27 files; `perception/scopes.py`, `runtime_plans.py`, `docs/RUNTIME_SCOPED_PERCEPTION.md` | Smoke 20260910T180757: 70.8 s/99.9 s en CV global 120 detectores → scopes local/plausible/global; Trading 120→14 detectores |
| `eb0a843` | Bound TRADE_MAX full-cap retry and General swipe touchdown | 4 files; `trading_operations.py`, `test_trade_max_retry.py`, `test_trade_locate_telemetry.py` | `>>` no-idempotente: 1 re-tap sólo si esperado 20/20 vs popup 1/20 confiado; touchdown General a `x=.33` (HIL: tap sobre slot lleno tragado); telemetría locate/row/delta |
| `3c8c0a7` | Model verified input lifecycle for inventory relief | 24 files; `bot/interaction_timing.py`, `docs/INPUT_LIFECYCLE.md`, `verified_transition.py` +188 | Generaliza `VerifiedTransition` (effect_timeout/grace/readiness, 6 perfiles); elimina `_remax_once`; Treasure conserva departure+resultado |
| `024ff8e` | Fix Trading entry readiness and separate Keys from material scrolling | 10 files; `trading_operations.py`, `docs/TRADING_LIVE_REGRESSIONS.md`, `tests/test_trading_live_regressions.py` | 3 smokes 20260912: `precondition_rejected` desde Trading-limpio-en-Pets + swipe Keys indebido → entrada desde Trading limpio, `_locate_keys` sin scroll (espera pasiva `relief_keys_rows`), `_locate_materials` único con scroll |

`git diff --stat 71340f5..024ff8e`: **122 files, +9016/−99**; `M 41, A 81, D 0, R 0`.

Aclaración: `Kritika_FarmBot_Plan_Preparacion_Codex_Astra.md` (trackeado, borrado unstaged en working tree, idéntico en `HEAD` y `024ff8e`, de `fc66d60`) es un brief pre-Codex de observabilidad/GUI/identidad/eligibility; **no** propone Trading/Craft/Treasure/Keys/Monster/scroll. La propuesta del chain vive en `docs/INVENTORY_RELIEF_CHAIN.md` y docs hijas (`SMOKE_FIX`, `RUNTIME_SCOPED_PERCEPTION`, `INPUT_LIFECYCLE`, `TRADING_LIVE_REGRESSIONS` en `024ff8e`).

### Por qué se volvió atrás (sólo evidencia)

- Arquitectura: entrelazamiento percepción-relief-planes + framework lifecycle sin consumidor separado (`docs/HISTORY.md:94-96,98-108,131`; `ARCHITECTURE.md:143-151` lo veta).
- Routing/readiness: `precondition_rejected` antes de readiness, scroll Keys indebido, ACTIVE confundido con contenido listo (`docs/HISTORY.md:100-106`; `024ff8e` + `TRADING_LIVE_REGRESSIONS.md §§1-9`).
- Observabilidad: fixes reactivos por smoke (tolerancia→scopes→retry→lifecycle→readiness) sin smoke verde intermedio; suites siempre verdes (2133→2281) pero HIL rompía → stop-condition offline-verde/hardware-roto → revert parcial (`docs/HISTORY.md:110-121`).
- Scroll fue síntoma, no causa raíz. Stale assumptions documentadas: `retop==win00`, Gold desconocido, Keys search heredado, aritmética `499-silver` sin GT de capacidad. Causa única "implementation bug" descartada por suites/evaluators verdes (673 frames 0 wrong citados en el intento).

## 2. Salvage matrix

Verificación hoy: `bot/trading_operations.py`, `treasure_operations.py`, `craft_operations.py`, `equipment_sell_operations.py`, `inventory_relief_runtime.py`, `trading_relief_flow.py` → `Test-Path = False`. Sobreviven Combine (`bot/equipment_combine_relief.py:93`), Socket relief (`bot/socket_inventory_relief.py:99`), Pet relief (`bot/pet_summon_space_relief.py`), full-popup sólo Black Market (`bot/inventory_full_transition.py`), scroll genérico (`bot/observed_scroll.py`, ya no consumido por Rotation) y `CharacterSelectScrollProfile` (único directed-scroll productivo).

| component | what existed | what worked | what failed | salvage |
|---|---|---|---|---|
| Trading primitives (enter/tab/row/promote Bronze→Silver→Gold, Weapon/Armor/Accessory, popups full/insufficient/limit, `>>`=min(have//need,20), verificación disminución) | `4612fd8:bot/trading_operations.py` → `024ff8e` | consenso 2-frame misma have/center_y, mismatch-check popup-vs-fila, trade_amount verificado pre-confirm | source exigía General exclusivo (smokes 1/2); ACTIVE≅contenido (smoke 3); orden adaptativo con `499-silver` sin GT | **REIMPLEMENT**: conservar exclusividad de tab, consenso de fila, verificación input/disminución; descartar `_key_counts` aritmético y acople a `ReliefRuntime` |
| Craft (Hero: costo 49, cap /999, batch 10, fail-closed Karats, retorno estable, disminución reobservada) | `4612fd8:bot/craft_operations.py`, `craft_sink.py` | `KARATS_NO` + boundary/contradicción; triple-verificación tier+costo+cantidad | sin fallo HIL propio; cayó con el chain/runtime rechazado | **KEEP_CONCEPT → REIMPLEMENT**: los 4 hechos son dominio rescatable; sink se reescribe por caller |
| Treasure / Gold Keys (enter/salir, `gold_key_boundary` selector-1 vs repeat-10 por currency fresca, `open_gold_once` departure+resultado estable, budget 900 s, Karats corta) | `4612fd8:bot/treasure_operations.py`, `treasure_sink.py` | diseño más limpio del experimento; repeat-10 sólo si icono sigue Gold Key fresco; Equipment-Full no autoriza nada | sin regresión HIL registrada; no portado por decisión de reconstrucción | **KEEP_CONCEPT** (máximo rescate): copiar semántica, no código |
| Combine-first composer | `4612fd8:bot/equipment_relief.py` sobre `equipment_combine_relief.py:93` (éste vive hoy) | reutiliza Combine, `return_plan=None`, retorna al caller, reintenta exactamente la acción bloqueada | compositor murió con el runtime experimental | **KEEP_CONCEPT**: reimplementar compositor (~30 líneas) contra el Combine actual cuando un caller real lo pida |
| Sell fallback | `4612fd8:bot/equipment_sell_{policy,operations,relief}.py` | Item Count autoridad, Ethereal+/accesorios inmutables, 6 tipos configurables, `bulk_group_matches`, `tail_slot` + scan tail-atrás + rescan total, bulk único sin retry, postcondición have↓ | destructivo irreversible; Karats-expansión mezclada en el loop; thresholds de presión no aceptados; cero HIL propio | **KEEP_TEST_EVIDENCE + REIMPLEMENT con cautela**; expansión Karats separada/opt-in o descartada en v1 del relief |
| Inventory navigation (paginación verificada por indicador, detalle open/close pareado, tail-backwards) | `4612fd8:bot/equipment_sell_operations.py`, `craft_sink` routes | fail-closed `capacity_page_outside_inventory` / `postcondition_failed` | acoplada a sprites/ROIs experimentales; variantes Trading incompatibles (12 vs 13, `.95`) | **REIMPLEMENT**: reglas sí, coordenadas/ROIs sólo vía calibración nueva |
| Known-list / directed scroll | `4612fd8` (12 ciegos) → `9e5e9fc` (13+settle) → `eb0a843` (x=.33+telemetría) → `024ff8e` (Keys sin scroll) | punto final `024ff8e` hoy consagrado en `ARCHITECTURE.md:121-133` + `HISTORY.md:84` | `keys=True` mezclaba familias/estrategias; scroll reverso Keys causó smoke 3; swipe sobre slot lleno tragado | **KEEP_CONCEPT (sólo diseño `024ff8e`)**; todo scroll previo se **DISCARD** |
| Full-popup handling (`TRADE_FULL/GOLD_FULL/HERO_WEAPON_FULL`, `TradeBoundary::{NO_MORE_INPUT,OUTPUT_FULL}`, PASS1 evalúa ambas familias, PASS2 + `unexpected_output_full_after_sink`) | `4612fd8:bot/trading_operations.py`, `inventory_relief_semantics.py` | taxonomía con ACK reutilizable | have/need nunca modeló capacidad output (asumida, no medida) | **KEEP_CONCEPT** contra vocabulario actual de popups |
| Retry/return (`fresh precondition → input → grace → resultado`; NO_EFFECT+source exacto = 1 retry mismo action; UNKNOWN/contradicción = sin retry; budgets) | `024ff8e:bot/trading_operations.py`, `TRADING_LIVE_REGRESSIONS §9`, `inventory_relief_contracts.py` | reglas finales sanas | framework general que las envolvía causó 3 regresiones (`HISTORY:98-108`) | **KEEP_CONCEPT (reglas) / DISCARD (framework)** |

**Treasure útil:** enter/salir, boundary por currency fresca, `open_gold_once`, leave con dismiss, budget temporal, todo fail-closed.
**Relief útil:** Combine-first con rutas por caller, `EquipmentSellAuthorization`, Item Count autoridad, tail-scan+rescan, bulk único con postcondición, taxonomía full/insufficient/limit.
**Se descarta:** `ReliefRuntime`, `ReliefFactReader` experimental, `interaction_timing`/perfiles, planes léxicos/scopes atados a relief, `inventory_relief_actions/targets`, scroll Keys en todas sus formas, `_key_counts` con `499`, `_remax_once` 20/20-vs-1/20, PASS1-doble + PASS2 automático "por las dudas", Karats-expansión en loop de venta, thresholds de presión, `INPUT_LIFECYCLE`/`RUNTIME_SCOPED_PERCEPTION` como arquitectura.
**Riesgos:** (1) Karats: exigir `key ∧ ¬karat` fresco por acción; (2) ventas: grade/tipo/Enhance/nombre desconocidos, grouping contradictorio o count no-decreciente → abort, nunca asumir; (3) loops: cada loop nuevo necesita bound + progreso propios; (4) tabs "por las dudas": cada sink lo pide un caller con recurso concreto.

## 3. Monster Wave board — observability matrix (hoy, `a4acad5`)

Base: 16 landmarks `assets/ui/landmarks/monster-wave/*.png` + 5 legacy, `bot/monster_wave_{activity,semantics,config,actions,flow,eligibility}.py`, `bot/perception/monster_wave.py`, `datasets/monster_wave_{semantic,ocr}_manifest.json` (97/79 entries), `tools/curate_monster_wave_evidence.py`, `tests/test_monster_wave*.py`. Corpus: 510 frames, 0 wrong/ambiguous. Astra `024ff8e --stat` filtrado monster/wave/board → 0 líneas (no añadió observabilidad de board).

| board signal | observable? | stable? | detector / evidencia | planning consequence |
|---|---|---|---|---|
| contexto board limpio (`screen.monster_wave` + 0 overlays) | YES | condicional | `bot/monster_wave_semantics.py:3,5`; `bot/perception/monster_wave.py:11-15`; `bot/catalog.py:321`; `bot/monster_wave_activity.py:39-45` | sin `clean_mw` nada autoriza input/decisión |
| tickets faltantes (`NEEDS_TICKETS`) / tickets OK (`READY` 30/30) | YES binario | condicional | `bot/monster_wave_semantics.py:6,7`; `bot/perception/monster_wave.py:16-25`; `bot/monster_wave_activity.py:48-59` | planner distingue NEEDS vs READY; sin cantidades |
| popup compra `30/30` (`purchase_full`) | YES binario | narrow pero estable (gap negro en `docs/MONSTER_WAVE_SKIP.md:240-244`) | `bot/monster_wave_semantics.py:14`; `bot/perception/monster_wave.py:56-60`; `bot/monster_wave_activity.py:203-210` | Fill All una vez o nada; prohibido contar `saldo-5` o x1 repetido |
| conteo numérico tickets N/30, costo GOLD restante, GOLD-insuficiente | NO | — | sin extractor tickets; OCR MW sólo sapphires `bot/ocr_extractors.py:320-329`; gap explícito `docs/MONSTER_WAVE_SKIP.md:275-276`, manifest `limitations: No GOLD-insufficient purchase evidence` | planner no gatea compra por GOLD; compra no verificable → fallo conservador sin reintento |
| `ACTIVE` (timer + Start SKIP) | YES presencia coherente | condicional | `bot/monster_wave_semantics.py:8,9`; `bot/perception/monster_wave.py:26-35`; `bot/monster_wave_activity.py:60-66` | SKIP activado vs no; timer no se cachea |
| valor countdown / expiración | NO | — | sin extractor; `build_timer_extractor` sólo WB `bot/ocr_extractors.py:332-346`; `bot/monster_wave_config.py` sin countdown | planner no programa por tiempo; si ACTIVE se pierde durante MAX → no Start |
| `MAX` / controles x2/x3 visibles / tooltip / botón Start SKIP | YES | estable | `bot/monster_wave_semantics.py:10-12`; `bot/perception/monster_wave.py:31-50`; `bot/monster_wave_activity.py:69-71,214-215` | planner sólo pide MAX fijo; tooltip persistente → terminar sin Start; Start sólo desde `max_ready` fresco, 1 intento + postcondición `boundary()` |
| Start manual / batalla / Auto Battle | NO (excluido por producto) | — | `bot/monster_wave_actions.py:70`; `docs/MONSTER_WAVE_SKIP.md:6-7`; `docs/BATTLE_MODE_SHARED_ZONE.md:168-169` | fuera de contrato |
| sapphires HUD (guard Daily ≥4) | YES | fresco+limpio | `bot/ocr_extractors.py:320-329`; `bot/monster_wave_activity.py:173-195`; `datasets/monster_wave_ocr_manifest.json` valores {0,70,83,183} | 0..3 → business sin intento; ilegible → técnico sin input; nunca `saldo-5` ni reuse WB→MW |
| popup insufficient sapphires | YES presencia | estable | `bot/monster_wave_semantics.py:15,22`; `bot/perception/monster_wave.py:61-65`; `bot/monster_wave_activity.py:216-219` | business; sin intent Yes |
| inventory board popup | YES presencia ciega | presencia estable / contenido NO | `bot/monster_wave_semantics.py:16,23`; `bot/perception/monster_wave.py:66-70`; `bot/catalog.py:422-424`; `bot/monster_wave_activity.py:221-229` | decisión bool ciega `continue_when_nonblocking_inventory_full`; Yes = aceptar pérdida desconocida |
| board contenido por ítem / tiers / materiales / necesidades crafting / capacidad por tier / trades crafting | NO | — | sin detector por fila, sin OCR board (siempre `context_mismatch`), un solo crop global `tools/curate_monster_wave_evidence.py:31,70`; texto board sólo en docs (`MONSTER_WAVE_SKIP.md:197-200`, `BATTLE_MODE_SHARED_ZONE.md:180-186`); gap `MONSTER_WAVE_SKIP.md:283-284` | planner no puede distinguir tier, pedir material concreto, cuantificar overflow ni tradear desde el board |
| **capacidad de Gold Keys** | **NOT OBSERVABLE FROM BOARD** | — | sin detector/key-count/treasure-reader en MW; Bronze/Silver sólo mención textual; Gold Keys ni aparece en board; `docs/semantic_census.md:105-106` treasure/gold-key legacy-only/FUTURE | planner la trata como inexistente desde el board; requiere Treasure/Trading Keys, nunca inferencia del popup board |
| Bronze/Silver/Arena Tickets/Badges en board | PARTIAL textual, no medida | — | sólo GT textual; `MW_BOARD` global, no por fila | contexto humano, no autoriza relief Keys/Arena |
| blockers Socket/Equipment | YES presencia, sin relief | estable presencia | `bot/monster_wave_activity.py:78,90-93,230-233`; `docs/MONSTER_WAVE_SKIP.md:203-220` | detenerse (`MANUAL_RESOLUTION`), sin fingir retorno ni relief WB |
| CLEAR / Weekly / Ranking | YES | estable | `bot/monster_wave_semantics.py:17,19-20`; `bot/perception/monster_wave.py:71-85`; `bot/monster_wave_activity.py:79-87` (máx 2 acks) | obstrucciones operacionales con OK verificado |
| elegibilidad Daily MW (badge hub) | YES | estable (scope compartido 5-detector) | `bot/monster_wave_eligibility.py`; `bot/productive_runtime.py:418-…`; `tests/test_monster_wave_eligibility_scope.py` | NOT_ELIGIBLE → skip sin entrar; UNKNOWN/FAILED → abort técnico |

**No observable hoy** (requiere adquisición HIL + curados ≤3/estado + manifests + calibración pos/neg/próximos sin relajar thresholds + reglas resolver + OCR con consenso + tests + evaluator incremental): conteo tickets, GOLD-insuficiente, countdown, contenido board por fila, tiers/materiales/recetas, capacidad por tier, trades crafting, capacidad Gold Keys, returns relief→MW, layouts no-MAX.

## 4. Decisiones arquitectónicas (cerradas en esta frontera)

1. **Board-first planning.** Trading Center nunca es etapa diagnóstica si el board snapshot ya decide qué falta. Flujo: `Monster Wave board → semantic board snapshot → resource needs → deterministic route plan → ejecutar sólo Craft/Trading/Treasure/Relief necesarios → continuar MW`. Snapshot describe; planner decide recorrido; executors ejecutan capacidades. Sin mezcla.
2. **Snapshot descriptivo, planner aparte.** `MonsterWaveBoardSnapshot` candidato (nombres/campos no finales): resource counts/status observables, material-tier needs, target-tier capacity/fullness *si observable*, craft prerequisites, trading opportunities, battle eligibility/resources, evidence sequence/freshness. Prohibido `should_visit_trading`, `should_craft_first`, `route=[...]` dentro del snapshot.
3. **Capacidades atómicas, no flow monolítico.** Trading/Craft/Treasure son executors de un plan ya decidido. Routing: sin necesidad de keys → no visitar Avatar & Keys; sin material trades → no scrollear a Crafting Materials; si se paga el viaje, agrupar operaciones útiles del mismo viaje; nunca tabs "por las dudas". Craft: sin scroll; precondición de entrada ≥1 slot libre de Equipment Inventory al momento de entrar; sin modelar relief por craft individual.
4. **Inventory Relief transversal.** Contrato: `operación original → inventory-full → Equipment Combine Relief primero → reintentar original → si sigue lleno → Inventory Relief fallback → reintentar original`. El caller conserva causalidad. Prohibido relief específico por MW/Trading/Treasure/Craft, y no es propiedad de ninguno de ellos: se invoca ante `equipment-full` del caller que lo requiera. Combine-first preservado (`HISTORY.md:87`); venta sólo si sigue necesario, con guards de §2.
5. **Crafting Materials preventivo + fallback defensivo.** Si el snapshot demuestra tier destino completo o necesidad de consumir/craftear antes → Craft primero, Trading después sólo si sigue necesario; nunca viajar a Trading sólo para descubrir que el trade no entra. El executor sigue defensivo ante `inventory-full` por stale/race con la política transversal, pero como fallback, no como planificación normal.
6. **Gold Keys — comportamiento exacto.** Trading Keys hace únicamente `Bronze→Silver` y `Silver→Gold` (orden por cantidades/necesidades). Capacidad Gold Keys **no observable** ni desde board ni desde Trading. `Silver→Gold` sin hueco intenta procesarse y levanta popup; ese popup **no** navega a Treasure: salir/navegar manual a Treasure, abrir Gold Keys, retomar causal y reintentar `Silver→Gold`. Chocar el popup no es mala planificación: es la primera evidencia de falta de capacidad. No inventar precondición observable inexistente. Abrir Gold Keys NO depende del estado de Equipment Inventory (puede hacerse incluso con Equipment Inventory lleno) y NO provoca ni dispara `equipment-full`.
7. **Treasure/Gold Keys — independencia de Equipment Inventory (corrección: se elimina la Opción B).** La decisión anterior (Opción B: relief causal durante la liberación de Gold Keys, Treasure como consumer de la política transversal) queda eliminada: partía del supuesto falso de que abrir Gold Keys podía chocar con `equipment inventory-full`. Cadena correcta ante Gold capacity: `Trading Silver→Gold → popup Gold Keys full → navegación manual a Treasure → abrir suficientes Gold Keys → volver a Trading → retry Silver→Gold`, sin consumo de Inventory Relief en ningún paso de la apertura.
8. **Treasure independiente y bounded.** Abrir desde contexto soportado → entrar a Gold Keys → aperturas bounded hasta objetivo explícito (mínimo: "suficiente capacidad para el Silver→Gold pendiente"; nunca "vaciar todo" por defecto) → postcondición/verificación al caller → reanudar plan. La apertura no consume Inventory Relief. Fail-closed ante Karats/otras monedas.
9. **Directed known-list scrolling (primitive transversal, sin semántica de consumer).** `catálogo conocido + landmark visible + target conocido → estimar desplazamiento → gesto acotado → reobservar → corrección bounded o stop`. Sin búsqueda ciega bidireccional por defecto ni navegador genérico. Consumidor actual: Trading Center únicamente; Craft y Treasure NO lo consumen. Aun así se diseña reutilizable porque habrá consumidores futuros; el helper no incluye semántica de Trading (el caller decide qué targets existen y qué estrategias están prohibidas, p.ej. Keys sin scroll). Contrato geométrico `024ff8e` + `ARCHITECTURE.md:121-133`: viewport con n filas/pitch, avance ≤(n−1)·pitch·.95, touchdown en zona no-interactiva, 1 gesto acotado, reobservar bajo mismos guards, progreso→iterar (máx 12), sin progreso→stop, target visible→consenso de fila (2 acuerdos/≤4 muestras), viewport ilegible/guard perdido/familia ajena→stop sin input.
10. **MW standalone/debuggable.** Niveles separables: acquire board → build snapshot → derive route plan → execute prerequisites → return/reorient → enter MW → battle/rewards → reliefs sólo por evidencia → postcondition/return. Permite debuggear sólo-adquisición, sólo-planning, full MW y prerequisite route sin implementar todavía.
11. **Stage-ready boundary.** La frontera termina con contratos + plan + validación offline; HIL/opt-in y stages quedan para fases de implementación con su propia evidencia.

## 5. BoardSnapshot candidato (post-audit, no final)

```text
MonsterWaveBoardSnapshot  # descriptivo, sin routing
  skip_state            # NEEDS_TICKETS | READY | ACTIVE | MAX_READY | ...
  tickets               # sólo binarios observables hoy (needs/ready/full-30-30); sin N/30
  sapphires_daily       # value | below_minimum | unverified (fresco, contexto MW)
  max_state             # max_selected | controls_clear | tooltip_present | start_present
  board_popup           # absent | present_content_unknown
  blockers              # socket_full | equipment_full | insufficient_sapphires | none (presencia)
  tier_material_signals # sólo lo que futura adquisición demuestre; hoy vacío
  gold_key_capacity     # NOT_OBSERVABLE (constante, documenta el límite)
  evidence              # sequence/freshness de frames que lo sostienen
```

Todo campo numérico/por-tier exige antes su detector+OCR+manifest+evaluator; no se rellena por imaginación.

## 6. Route planner (modelo determinista, testeable)

Función pura `plan(snapshot + non-board discoveries) → ResourceRoutePlan` (lista ordenada de capacidades atómicas con parámetros verificables, sin optimizer):

- Caso 1 (sólo materials, tier con capacidad): `Trading(CraftingMaterials, trades=[…]) → salir`.
- Caso 2 (craft-previo): `Craft(recipe, qty) → Trading(CraftingMaterials, trades=[…])`.
- Caso 3 (sólo keys): `Trading(Avatar&Keys, trades=[Bronze→Silver?, Silver→Gold?])`, con rama `on GoldKeyFull: Treasure(open_until=enough_for_pending, sin relief) → Trading(retry Silver→Gold)`.
- Caso 4 (keys+materials): ordenar minimizando viajes/scrolls, sin tabs inútiles.
- Caso 5 (sin necesidad): `[]` (no viajar).

## 7. Dependency graph y fases finales

```text
A(recon+observ audit, esta tarea)
 └→ H(snapshot contract design, sin código) + I(planner model design, sin código)
     ├→ B(directed scroll primitive; único consumer: C)
     │    └→ C(Trading primitives, consume B)
     ├→ D(Craft primitives; precond ≥1 slot libre; sin scroll, sin relief propio)
     ├→ E(Treasure/Gold Keys; independiente de B, de F y de Equipment Inventory)
     ├→ F(transversal relief: contrato + Combine composer; Sell con cautela;
     │     sin dueños; lo invoca el caller que choque con equipment-full)
     └→ G(MW board acquisition)
          └→ I-impl(planner puro) → J(MW integration)
              → K(standalone/debug) → L(stage-ready)
```

Orden final recomendado: **A → H/I-diseño → B → F → C → D → E → G → I-impl → J → K → L** (secuencia de implementación, no cadena de dependencias; sólo C depende de B).

Razones y respuestas a dependencias:

- **¿G/H antes de C/D/E?** Sí en diseño (contratos primero para saber qué APIs necesita el planner), no en adquisición física (G-física va después de tener executors que consumirían sus señales; evita adquirir señales sin consumidor, regla `AGENTS.md`).
- **¿Relief (F) antes de Treasure (E)?** No hay dependencia: E no consume F (la apertura Gold Keys es independiente de Equipment Inventory). F vive como capacidad transversal que invoca el caller que choque con `equipment-full`.
- **¿Scrolling (B) antes de Trading/Craft?** B sólo antes de Trading (su único consumer). Craft y Treasure no consumen B. B sigue siendo el próximo frente por ser offline, acotado y reutilizable por futuros consumidores.
- **¿Qué offline antes de HIL?** B (mocks de observer), H (dataclass + tests puros), I (función pura + tabla casos 1-5), F-contrato y Combine-composer (tests con caller falso). HIL sólo para: pitch/settle/toque (C), currency Gold-vs-Karat, conteos board, capacidad Gold Keys, returns físicos.

## 8. Primer frente implementable (siguiente prompt, no empezado)

| campo | contenido |
|---|---|
| goal | Primitive `directed known-list scroll` transversal y reutilizable (contrato geométrico `024ff8e` + `ARCHITECTURE.md:121-133`); consumer actual Trading Center únicamente; sin gameplay, sin HIL |
| scope | `catálogo+landmark+target → estimar → 1 gesto acotado → reobservar → bounded-correct/stop`; target totalmente visible/accionable para actuar; budgets por caller; sin semántica de Trading dentro del helper (p.ej. la prohibición de scrollear Keys vive en el caller Trading, no en el helper); sin `ReliefRuntime`/`interaction_timing`/planes léxicos |
| evidence needed | `docs/TRADING_LIVE_REGRESSIONS.md §§7-9` en `024ff8e`, `bot/observed_scroll.py:37,159,200,256,278`, `bot/character_select_scroll.py:13` como referencia de perfil dirigido |
| code areas | nuevo helper acotado (no framework) + tests dirigidos; no tocar `bot/` productivo salvo el helper nuevo ni `assets`/manifests |
| tests | unitarios con observer falso: progreso→itera, sin-progreso→stop, target-visible→consenso, guard-perdido/viewport-ilegible→stop sin input; `git diff --check` |
| HIL need | ninguno en este frente; pitch/settle/touchdown se calibran en C con HIL propio |
| acceptance | helper bounded y puro en IO salvo gesto inyectado; todos los casos anteriores en verde; sin semántica de consumer dentro del helper; documentado en el doc del frente, sin cambiar `ARCHITECTURE.md` |

## 9. Cambios de esta tarea

- `ROADMAP.md`: nueva frontera post-V1 (resumen; decisiones cerradas sin marcar implementación DONE).
- Este documento (detalle).
- `CONTEXT.md`: **no** tocado (no cambió estado runtime; sólo planificación).
- `ARCHITECTURE.md`: **no** tocado (sin inconsistencia factual extrema; §§ scroll/relief ya alineados).
- Sin código/tests/assets/manifests, sin HIL/evaluator/corpus/suite, sin stages, sin push.
- Corrección posterior: ver §10 (supuestos corregidos sin reescribir el análisis válido).

## 10. Corrección de supuestos (tarea posterior, sin runtime)

Correcciones de dominio cerradas aplicadas sobre §§4, 6–8:

1. Treasure/Gold Keys: la apertura no depende de Equipment Inventory, puede hacerse con Equipment lleno y no provoca `equipment-full`. Decisión Treasure↔Relief Opción B eliminada; Treasure no consume Inventory Relief. Cadena: `Silver→Gold → popup Gold full → Treasure → abrir suficientes Gold Keys → Trading → retry`.
2. Inventory Relief: transversal ante `equipment-full` del caller (Combine → retry → Sell → retry); no es propiedad de Treasure/Craft/Trading/MW.
3. Craft: sin scroll; precondición de entrada ≥1 slot libre de Equipment Inventory; sin relief por craft individual.
4. Directed scroll: consumer actual Trading Center únicamente (Craft y Treasure no lo consumen); primitive transversal sin semántica Trading dentro del helper.
5. Dependency graph: B sólo alimenta a C; E independiente de B, de F y de Equipment Inventory; F transversal sin dueños. B sigue como próximo frente.

## 11. Frente B implementado (sin consumer, sin HIL)

- Módulo nuevo `bot/directed_list_scroll.py` (no se extendió `bot/observed_scroll.py`: ese helper mide movimiento ciego de píxeles hacia un borde y no conoce orden/catálogo; extenderlo habría contaminado su semántica).
- API: `KnownListScrollProfile` (pitch, filas visibles, factor de overlap 0.95 por defecto, lane/touchdown y límites verticales del caller, tolerancia de fila, consenso 2 acuerdos/≤4 muestras) + `ViewportReading` (ids visibles top→bottom, row_y del target, secuencia, readable, guard_ok) + `plan_directed_gesture` (pura) + `advance_toward_target` (≤1 gesto) + `scroll_to_target` (driver bounded con `max_gestures` explícito, sin default).
- Contrato: dirección por orden conocido (sin búsqueda ciega); desplazamiento proporcional con clamp a `(visible_rows−1)·pitch·0.95` y a la zona segura del profile; reobservación tras cada gesto; progreso por leading edge del catálogo (no por cambio de imagen); no-progress/movimiento contrario → stop; ilegible/guard perdido → stop sin más input; consenso de target consecutivo y bounded con evidencia `stable_row_y`/`stable_sequence`; freshness local por secuencias estrictamente crecientes (stale nunca prueba progreso/ready); budgets explícitos; la primitive nunca toca el target (sólo emite `PlannedGesture` por callback inyectado).
- Límites: geometría de producción (pitch, filas, lane, top/bottom, tolerancia) sin calibrar — los tests usan geometría sintética; HIL pendiente en el frente C con el consumer real. Sin semántica de consumer dentro del helper (la prohibición de scroll en Keys vive en el futuro adapter, no aquí).
- Trading sigue sin integrar; Craft/Treasure/Relief/MW sin cambios; runtime productivo intacto.
- Tests: `tests/test_directed_list_scroll.py`, 35 dirigidos verdes con observer/gesto falsos; `git diff --check` limpio; sin full suite (módulo nuevo sin consumidores), sin evaluator/corpus (sin detectors/readers/assets), sin HIL.

## 12. Frentes C1/C2 offline (HIL pendiente, sin calibración inventada)

Tabla de reconstrucción (fact | evidencia actual | reutilizable | necesita HIL | propuesta):

- Entrada Lobby→Trading | coords legacy `(0.2441,0.893)` + landmark runtime `lobby-trading-center-label` | coords NO, label SÍ | SÍ (tap + llegada) | C1: entry op tras HIL; offline sólo predicados
- `screen.trading` base | Astra `landmark.relief_trading` (asset ausente en repo) | NO | SÍ (crop título) | `landmark.trading_center_title` (nombre; detector con HIL)
- Tab General/Keys activas | templates legacy `*-tab-id.png` sin calibrar | sólo referencia visual | SÍ | `indicator.trading_general_active` / `trading_keys_active`
- Contenido Keys/Materials listo | Astra `relief_keys_rows` + guard 30 frames (frames no versionados) | concepto SÍ, asset NO | SÍ | `indicator.trading_keys_rows` / `trading_material_rows` (readiness positiva estilo Daily)
- Filas/títulos/pitch | Astra `TradeViewportRow` (OCR ≥.90, pitch, `.003`, color-check) + prefijos hero crafting | modelo SÍ, números NO ciegos | SÍ (pitch, títulos, orden) | C2: reader futuro → `ViewportReading`; catálogo ordenado sólo con GT
- Bound scroll `.95·(n−1)·pitch`, x=.33, 900ms, settle .6s, ≤12 | bound SÍ (ya en B); lane/tiempos NO canónicos | SÍ (lane, pitch, settle) | `KnownListScrollProfile` calibrado con HIL
- Keys sin scroll | Astra §8 + smoke 3 (Keys al comienzo, cero scroll) | diseño SÍ | parcial (confirmar UI actual) | policy en adapter Trading, no en B
- Regresión readiness | `TRADING_LIVE_REGRESSIONS.md` §§1-9 (ACTIVE≠contenido; Pets→precondition_rejected) | diseño SÍ | SÍ (tabs iniciales reales) | readiness = tab exclusivo + rows + limpio
- Scoped perception 14-detector | arquitectura Astra descartada | NO | — | correctness primero con mecanismo actual; scope sólo con vocabulario completo

C1 offline DONE (predicados puros + 12 tests): `bot/trading_center_semantics.py` (nombres) + `bot/trading_center.py` (`is_trading_screen`, `clean_trading`, `trading_tab` GENERAL/KEYS/UNKNOWN/CONTRADICTORY, `is_keys/materials_content_ready` estilo Daily: chrome + rows + limpio, misma snapshot). Sin entry action (requiere coords HIL), sin detectores, sin registro en catálogo.

C2 adapter offline DONE (16 tests), calibración pendiente: `bot/trading_materials_scroll.py` (`MaterialRow`/`MaterialViewport`, `viewport_to_reading` que excluye parciales, `locate_material_target` con gate `content_ready`, rechazo `keys_no_scroll` sin input, short-circuit parcial sin input, exit-confirm de READY contra fila completa fresca). Sin `MATERIAL_CATALOG` ni profile físico: orden/títulos/pitch/lane/settle/tolerancia requieren HIL; no se fijó ningún valor físico.

B_FIT = GOOD: el adapter consume B directo (profile, reading, driver, outcomes) sin bypasses ni duplicación de dirección/progreso/budget; la única lógica propia es policy de dominio Trading (parciales, keys, readiness-gate) que pertenece al adapter. B sin cambios.

HIL pendiente (usuario con Trading accesible, diferido a otra sesión): Q1 entrada+tab inicial; Q2 General/materials orden top→bottom, headers, pitch, filas visibles; Q3 Keys al comienzo sin scroll + títulos; Q4 readiness (spinner/tiempos/señal); Q5 safe lane (verificar x=.33); Q6 swipe settle/parciales/top-bottom; Q7 smoke forward/back/visible sin tocar target. Luego: curar→assets→specs→calibración→evaluator incremental→catálogo+profile→smoke→C1/C2 DONE.

Validación offline: 63/63 (35 B + 12 C1 + 16 C2), `git diff --check` limpio; sin full suite (ningún archivo existente tocado), sin evaluator/corpus, sin HIL. Sin trades: el adapter nunca tapea (sólo emite `PlannedGesture`).

## 13. C1/C2 DONE con HIL (calibración física cerrada)

Dispositivo `2311DRK48G` (2712×1220, serial configurado), ADB repo-local con `-s`. Captura: shell screencap + pull (exec-out directo se corrompe en PowerShell).

Q1 readiness: Trading abre en Avatars & Keys (GT humano); General con bienes temporarios. Positivo = título + tab exclusivo + filas completas con contadores. Sin spinner observado (loading-state sin GT: rows-ausentes ⇒ no-ready por defecto).

Q2 catálogo General (22 filas, GT humano + capturas, orden top→bottom): super_awakening_stone, mao_coins, light_essence, dark_essence, nature_essence, lapiz_400, stamina_100, gold_pouch_10m, gold_10m, sapphire_5, brawlers_badge, lapiz_5, ring_enhance, melee_badge, accessory_crafting_material, weapon_crafting_material, hero_weapon_crafting_material, hero_armor_crafting_material, hero_accessory_crafting_material, r_ticket, k_coin, guild_commodity. Ids nombran ROWS (lapiz_400 vs lapiz_5; gold_pouch_10m vs gold_10m). Sin headers ni duplicados base. Tabs reales: General/Pets/Avatars & Keys/Currency/Special Currency.

Q3 parciales: slivers en bordes en ~30% de posiciones manuales; regla: parcial nunca accionable, excluido de ids (posición vía índices de completas). Q4 geometría: pitch 0.1418 estable en 8 capturas y ambos tabs; 4 completas; centros de referencia 0.4283/0.5701/0.7119/0.8537; zona gestos y∈[0.36,0.94]. Q5 lane: x=0.33 sobre texto estático (sin controles/slots; Trade en x≈0.75), humano-confirmada ×2, cero mis-taps. Q6 settle: burst +0.4/+0.9/+1.5 idénticos a 4 decimales (asentada a 0.4s; harness usa 1.5s conservador), sin momentum. Q7: 4 consensus físicos (2+1 bonus+1), y estable a 4 decimales; tolerancia 0.015 conservadora y validada.

Detectores (`bot/perception/trading_center.py`, standalone, fuera del engine global): título (template; 1.00 vs 0.52 lobby), tabs por orange-fill (general 0.528 vs 0.130/0; keys 0.395 vs 0.120/0; text-template 0.93 vs 1.00 insuficiente → color), rows estructural por proyección (8/8 frames =5, lobby 0; Hough descartado por misses 30%). Grid-fit de bandas a pitch (un miss no corre índices; fallback raw). Evaluator incremental verde: labels exactos 9/9, gaps título/tabs, bandas en pitch-grid. Corpus `screencaps/semantic/trading-center/` (local, ignorado) + manifest versionado. Sin registro en catálogo/resolver ni wiring global (C3 lo promueve; cero tests de conteo afectados).

Adapter final: `MATERIAL_CATALOG` + `TRADING_MATERIALS_SCROLL_PROFILE` (pitch 0.1418, 4 filas, lane 0.33, top 0.36, bottom 0.94, tol 0.015, consenso 2/4; max_delta 0.4041). Tests reales offline (forward/back/visible) verdes.

Smokes (`tools/smoke_trading_scroll.py`, por pasos, sin tap path, títulos por sidecar con epoch anti-stale): A forward 1 gesto [11,14]→[14,17] READY y=0.8213; B backward 1 gesto [18,21]→[15,18] READY y=0.4597 (+bonus READY y=0.5377); C visible 0 gestos READY y=0.6975. Cero taps, cero trades, gates sostenidos.

B_FIT final = GOOD: B sin cambios (adapter consume profile/reading/driver directo; única lógica propia = policy Trading). Tests: 79/79 (35 B + 12 C1 + 21 C2 + 11 percepción). Sin full suite (ningún archivo compartido tocado), sin full corpus (sólo vocabulario nuevo), `git diff --check` limpio.

## 14. C3 DONE: TradingRowFact + promoción global (cero trades)

Fact table (fact | evidencia | OCR | HIL | consumidor): have/need materials primario | corpus 8 frames + RapidOCR PP-OCRv6 | hecho | cubierto | C4; have/need keys (need=10 constante HIL) | keys-top | hecho 4/4 | cubierto | C4; fila Bronze | ausente (no-scroll Keys, steer usuario) | n/a | pendiente | C4 bloqueado hasta GT; Gold capacity | ausente en UI | no | documentado NOT OBSERVABLE | nadie; second costs (gold/AD) + expiry | visibles | diferido C4 | no | C4 pre-confirm; trade_available | botón siempre rojo (no codifica) | no | no | omitido; title identity | corpus + OCR | hecho | cubierto | C3/C4.

`bot/trading_row_facts.py`: `TradingRowFact` (item_id, section, row_y, have, need, sequence, evidence; sin decisions ni planner) + `CATALOG_TITLES` (26) + `TradingPairReader` (segmentación por baseline de glifos con outline, continuación multi-línea, margin-stability, fullmatch estricto, conf≥0.5) + `TradingTitleReader` (2 strips, prefix-anchor + fuzzy≤2; infix rechazado: accessory⊄hero_accessory) + `consensus_row_samples` pura (2/4, misma id/section/y±0.015/have/need, seq crecientes) + `read_row_fact` bounded sin input. Correcciones vs Astra: need leído por OCR (no hardcode 40/10; HIL refutó 40), have None ⇒ no fact, семьи ambiguous ⇒ no fact.

HIL numérico: have < need ⟺ texto rojo (5 casos, documentado como regularidad NO usada por C3); second costs y "Remaining" visibles pero fuera de fact. Sizes: pares blancos y rojos leen (keys 4/4 con scale-2 color).

Evaluador (`datasets/trading_row_pairs_manifest.json`, 32 rows GT): 21 facts, **0 wrong**; 11 unreadable (wide-gold, two-line parciales, rojo pequeño) fail-closed documentados por fila. Cobertura incluye hero_weapon/accessory, weapon, keys 4/4; hero_armor rechazado-safe ("39/4"→margin mismatch) — C4 no puede asumirlo sin re-verificar.

Promoción: regla `screen.trading` en catálogo (19 reglas, 98 observaciones) + `landmark.trading_center_title` en STRONG completion (71→72, revisado) + detector título al engine global (+1: 95→96) + `TRADING_SCOPE` (base + tabs/rows especializados) + `build_trading_perception` standalone. Tabs/rows especializados NO entran al engine global (costo por frame sin consumer; C4 los promueve con su flow). To-lobby scopes absorben el título por diseño (counts 77→78 revisados).

Validación: full hardware-free **2386 passed** (justificada: engine global + regla + vocabulario); 23 fallos iniciales todos mecánicos (counts 95→96/77→78/18→19/93→98, slice MW) + 1 NameError propio (import faltante) — cero divergencias semánticas; resto ERRORs ambientales tmp_path (WinError 5, preexistentes). Evaluator incremental trading verde (labels 9/9, gaps, bandas, 0 wrong reads, cross-screen title 15/15 silencio). `git diff --check` limpio. HIL nuevo: sólo Bronze-check (negativo por policy, sin scroll Keys). Cero taps, cero trades (módulo sin adb/tap; smoke tool intacto).

## 15. C4 generic verified trade primitive (offline DONE, HIL pendiente)

Executor, no planner: `bot/trading_operation.py` (nuevo, ~600 líneas con docstring de contrato) consume un `TradingRowFact` fresco y ejecuta UNA operación económica acotada. Sin routing, sin sinks externos, sin Treasure/Craft/Relief/MW/planner/stage (imports probados: sólo stdlib + `TradingRowFact`; cero `should_*`, cero `route_plan`).

Astra evidence reused (read-only `024ff8e`, sin copiar coordenadas/ROIs/aritmética/retry): tap de fila en columna Trade (x del consumer); popup Item Trade con línea `Label (have/need)`, cantidad `n/20`, `>>`=TRADE_MAX, CONFIRM/NO, ACK de boundaries, overlay quantity-limit; `>>` no-idempotente (principio, no la excepción `20/20`-vs-`1/20`); popup-vs-row mismatch aborta confirm; éxito exige disminución reobservada; `have<need` pre-open ⇒ NO_MORE_INPUT sin input. Correcciones vs Astra: cap/denominador observados por panel (no `20` constante); second costs como dato/guard con allowlist explícita (Astra Trading no los modelaba); sin re-tap de `>>` sin prueba exacta (la excepción vieja exige HIL actual); sin aritmética `499-silver`/balances por cálculo.

Panel/layout findings (UI 2712×1220 HIL C4 + 2712×1224 HIL C5 2026-09-17, `artifacts/hil_c4a/` + `hil_c4b/` + `hil_c5/` raws locales): popup Item Trade x 0.275–0.724 / y 0.208–0.849; prompt "Would you like to proceed with the trade?"; cantidad `n/20` (inicial `1/20` exacto por OCR en ambas filas); hitboxes finales HIL C5 (`bot/trading_panel_profile.py`): No 0.2961–0.4148 / 0.7533–0.8080 punto (0.3555, 0.7806), Trade 0.4336–0.5531 / 0.7467–0.8170 punto (0.4934, 0.7819), `>>` 0.6619–0.7139 / 0.7729–0.8309 punto (0.699, 0.802); Astra 0.699/0.802 cercano sólo para `>>`, X de No/Trade diferían: no hardcodear. Términos GT humano: 40 weapon → 10 hero weapon (fila 1), trade directo de accessory sin second cost (fila 3); sin línea de costo Gold/AD en las filas probadas. Fila = oferta de output (identidad output), panel muestra identidad del input + `(have/need)`: el futuro adapter mapea identidad de output, sin cambio al contrato genérico. `>>` con máximo ya seleccionado invoca el popup quantity-limit (GT usuario; la primitive omite `>>` si la selección fresca ya satisface la intención). Por eso C4 es layout-agnostic: `TradePanelFact` inyectado, `TradePanelTargets` sin defaults, tap_x del caller.

API final: `TradeRequest(row_fact, quantity, allowed_cost_kinds, row_tap_x, expected_item_id?, max_fact_age=2)`; `TradeQuantity(EXACT|UP_TO|MAX_ALLOWED, amount?)`; `TradeCostFact(kind, amount?, sufficient?|None, evidence)`; `TradePanelFact(item_id?, input_have?, input_need?, quantity?, costs, sequence, panel_open, shows_insufficient/output_full/limit, evidence)`; `TradePreconditionContext(is_trading_screen, section, clean, unknown/ambiguous/contradictory, sequence)`; `TradeResult(outcome, before_fact, after_fact?, boundary?, reason?, inputs, evidence)`; outcomes `SUCCESS | INSUFFICIENT_INPUT | OUTPUT_FULL | LIMIT_REACHED | NO_MORE_INPUT | NO_EFFECT | FAILED | CANCELLED`.

Precondition contract: Trading válido + sección correcta + fact fresco (`0 ≤ ctx.seq − fact.seq ≤ max_fact_age`) + `expected_item_id` + `need>0` + `have≥need` (si no, NO_MORE_INPUT cero input) + limpio + no UNKNOWN/AMBIGUOUS/contradicción. Todo fallo ⇒ cero input. Sin re-navegación dentro de C4.

Row tap contract: un único tap en `(row_tap_x, stable_row_y)`; exige panel fresco (`panel.seq > fact.seq`); si no abre, no confirma; sin retry global (primer intento único).

Panel-open verification: panel ausente/cerrado/stale ⇒ FAILED bounded, cero inputs más. Boundaries al abrir (insufficient/output_full/limit) se devuelven sin más input.

Second-cost model: `TradeCostFact` como DATO/GUARD; allowlist explícita del caller; kind fuera ⇒ `unexpected_currency` + cancel, sin confirm; amount None ⇒ `unreadable_cost` + cancel; `sufficient=False` observable ⇒ INSUFFICIENT_INPUT. Nunca Karats por inferencia (el caller lista sólo lo permitido).

Quantity modes: EXACT (selected debe igualar), UP_TO (`min(wanted, cap, affordable)`), MAX_ALLOWED (`min(cap, affordable)`); cap observada del panel + bound independiente `have//need`; imposible ⇒ fail closed + cancel, sin confirm.

`>>` behavior: como máximo un tap causal; si la selección fresca ya satisface la intención se omite `>>` (HIL B GT: `>>` sobre máximo ya seleccionado invoca el popup quantity-limit en vez de seleccionar); si se tapea, efecto observado en panel fresco (`seq` estrictamente mayor); sin efecto ⇒ `max_no_effect` fail-closed + cancel; NUNCA segundo tap por timeout; sin excepción `20/20` rescatada.

Confirm contract: como máximo un tap a confirm, sólo tras panel match + costs OK + cantidad satisfecha + no-cancel; re-chequeo de costs/match post-`>>`; sin doble confirm.

Popup-vs-row validation: `panel.item_id == fact.item_id`, `panel.input_need == fact.need`, `panel.input_have == fact.have`; mismatch ⇒ cancel (si hay punto) + FAILED, sin confirm. Sin identidad por posición de popup.

SUCCESS postcondition: `after.have < before.have` con fact fresco (`after.seq > filled.seq`) e identidad conservada; sin aritmética exacta. Unchanged fresco ⇒ NO_EFFECT; stale ⇒ FAILED (`stale_after_fact`), nunca SUCCESS. Popup tras confirm con signals ⇒ boundary correspondiente.

Boundaries: INSUFFICIENT_INPUT / OUTPUT_FULL / LIMIT_REACHED se devuelven con `boundary` explícito; ACK/dismiss posterior es responsabilidad del caller (consumidor C5/C6); cero navegación externa en C4. Para Silver→Gold, OUTPUT_FULL será la señal que el consumer traduzca a Treasure→retry (NO implementado aquí).

Cancel path: mismatch/currency/ilegible/cantidad-imposible/max-sin-efecto/cancel-usuario ⇒ un tap a cancel si el caller dio punto, si no retorno sin más input (cero gasto en ambos casos). Retorno a Trading estable lo verifica el caller.

Promoted semantics/detectors: NINGUNO en esta tarea (panel vía readers inyectados, no detectores). Scope final: `TRADING_SCOPE` existente reutilizado para gates de contexto (1 spec + 2 especializados); engine global intacto en 96 detectores; to-lobby counts intactos.

Manifests/evaluator: no aplica (sin detectors/readers/assets nuevos); evaluator trading previo sigue vigente sin invalidación.

Tests: `tests/test_trading_operation.py` (44 dirigidos) + `tests/test_trading_panel_profile.py` (6 geometría/wiring), 50 passed (precond incl. stale/wrong-section/row-mismatch/UNKNOWN/AMBIGUOUS/contradicción; panel open/lost/stale; costs allowed/unexpected/unreadable/insufficient/change-after-max; qty exact/up-to/max/impossible/sin-aritmética-oculta; `>>` single-tap/no-retry; confirm-only-after-guards/cancel/no-double; postcond have↓/unchanged/stale/identity; boundaries open/after-max/on-confirm; separation sin imports ni routing; profile puntos interiores/márgenes/orden/bboxes/ROW_TAP_X/wiring). Sin full suite (sólo módulo nuevo + tests, ningún compartido tocado) y sin corpus (sin cambios de percepción).

HIL A result: PASS (2026-09-17, fila 1 hero weapon 265/40): fact fresco consenso 2/2 + contexto General verificado; 1 tap autorizado en (0.75, 0.4357)→(2034, 531) abrió el panel correcto; controles/costs leídos (sin second cost, GT humano); Cancel manual del usuario; retorno estable (gates 1.00, bandas idénticas) + `have` intacto 265/40 = cero gasto. Taps agente: 1.

HIL B result: NO_EFFECT, no SUCCESS (fila 3 hero accessory 53/40, EXACT 1): fact fresco + panel correcto (1/20 OCR exacto, trade directo GT); `>>` omitido por regla HIL (máximo ya seleccionado); 1 tap CONFIRM autorizado en botón "Trade" (0.43, 0.79)→(1166, 963), centro medido a 3px; panel sin cambios (53/40 GT + OCR) tras ~1 min y reobservación: sin éxito ni boundary. Sin retry (económico a ciegas prohibido). Cancel manual + retorno estable + 53/40 intacto = gasto cero. Causa final demostrada en C5 (no GT pendiente): miss de hitbox clase A — el tap cayó ~10px a la izquierda del interior rojo (fondo BGR 26,59,93); centro real (0.4934, 0.7819) 171px a la derecha; `btns.txt` No era borde y `>>` apuntaba bajo el panel. No fue trade sin efecto. Taps agente: 2. HIL B NO bloqueó el contrato genérico (fail-closed), pero SÍ bloqueó C4 DONE hasta SUCCESS.

HIL C/boundaries: quantity-limit por `>>`-en-máximo confirmado sólo como GT/mecanismo (no ejercido como outcome C4); OUTPUT_FULL/INSUFFICIENT/LIMIT como outcomes: HIL_NOT_EXERCISED; cubiertos offline + evidencia Astra.

HIL C5 calibration + SUCCESS (2026-09-17, fila 1 hero weapon 265/40, `artifacts/hil_c5/`): panel reabierto 1/20 sin second cost; No 2/2 PASS en (0.3555, 0.7806) (cierre a Trading estable, 265 intacto); `>>` PASS en (0.699, 0.802): 1/20→6/20 causal (output 10→60, input 265/40→265/240), luego cancel con No sin gasto; SUCCESS EXACT 1 en (0.4934, 0.7819): tap fila (0.75, 0.4357) + un único Trade, sin `>>`, allowlist {gold}; panel 265/40 1/20 → retorno Trading 225/40 fresco (225 < 265), cero retry, cero boundary, sin premium. Taps agente C5: No + (>> + cancel) + (fila + Trade) = 6, cada uno autorizado. C4 DONE.

Límites: sin routing externo; sin Bronze→Silver/Silver→Gold policy; sin Treasure/retorno/retry post-Treasure (C5/C6).

## 16. C5 Avatar & Keys primitives (executor DONE, sin policy, cero trades)

`bot/trading_keys.py` (nuevo, sin cambios a compartidos): capability independiente de Trading Center que confirma Avatar & Keys, verifica readiness C1 positiva y delega UNA operación pedida por el caller a C4. Cero scroll: sin imports de `directed_list_scroll`/`trading_materials_scroll`/swipes/gestos, sin fallback; rows no-ready o tab perdido = fail closed con cero input (el caller espera bounded sin swipe fuera de C5).

Modelo de operaciones (enum mínimo, el caller elige una; C5 nunca ordena ni cuantifica globalmente):

- `BRONZE_TO_SILVER` → fila causal `silver_key` ("Silver Key 2", output Silver; `have`/`need` = Bronze, HIL 5/10). No existe fila output `bronze_key` en catálogo ni HIL: Bronze es sólo input aquí, observado vía la fila Silver.
- `SILVER_TO_GOLD` → fila causal `gold_key` ("Gold Key 2", output Gold; `have`/`need` = Silver, HIL 9/10).
- Sin `Gold→X`: no existe en la UI. Filas Gem (`silver_gem_key`, `gold_gem_chest_key`) visibles pero fuera de alcance: sin operaciones definidas.

Readiness: `check_keys_ready`/`is_keys_ready` reusan C1 (`is_trading_screen` + `trading_tab==KEYS` exclusivo + `clean_trading` + `is_keys_content_ready`) con razones explícitas (`unknown_state`/`ambiguous_state`/`not_trading`/`tab_not_keys`/`contradictory_state`/`overlays_present`/`rows_not_ready`). `build_keys_context` traduce el snapshot a `TradePreconditionContext(section="keys")` sin autorizar input por sí mismo.

Adapter: `execute_key_trade(operation, snapshot, row_fact, quantity, targets, tap, read_panel, read_row, ...)` valida enum + mapping (`row_operation_mismatch` con cero input si la fila no es la causal) + readiness (cero input), construye `TradeRequest(row_fact, quantity, allowed={"gold"}, row_tap_x=ROW_TAP_X=0.75, expected_item_id, max_fact_age)` y delega una vez a `execute_verified_trade`. El `TradeResult` vuelve con la misma semántica C4 más `evidence += operation:<valor>`; `OUTPUT_FULL` en Silver→Gold se retorna tal cual (C6 lo consumirá hacia Treasure+retry; C5 nunca navega). Quantity `EXACT`/`UP_TO`/`MAX_ALLOWED` pasan del caller; sin aritmética `_key_counts`, sin inferencia de capacidad Gold (sigue `NOT OBSERVABLE`, sin 499/cálculos), sin retries, sin Treasure/Craft/Relief/MW/planner/stage (imports probados).

Percepción/scope: se reusa `TRADING_SCOPE` existente; cero detectores/readers/assets nuevos; engine global intacto en 96; counts to-lobby intactos.

Tests: `tests/test_trading_keys.py`, 40 dirigidos verdes (readiness ready/no-activo/sin-rows/overlays/contradictorio/foreign/UNKNOWN/AMBIGUOUS; no-scroll por imports+firma+vocabulario de taps; mapping Bronze=silver_key/Silver=gold_key/rechazos/gemas/materiales/operación desconocida; delegación EXACT/UP_TO/MAX_ALLOWED + `ROW_TAP_X` + guards gold/karats/ilegible + `NO_MORE_INPUT` sin tap; passthrough SUCCESS/INSUFFICIENT/OUTPUT_FULL/NO_EFFECT + independencia de orden + sin routing; separación sin imports externos ni `_key_counts`/`promote`/`should_`/`route_plan` + `NOT OBSERVABLE` presente).

Validación: `py_compile` + `git diff --check` limpios; C5 40/40; subset trading 127 passed (C4/panel/C1/row-facts/materials/percepción, sin regresiones); sin full suite (ningún compartido tocado, baseline vigente no invalidado); sin evaluator incremental (sin detectors/readers); sin corpus nuevo.

HIL: mappings sostenidos por evidencia HIL previa (keys-top/01.png + manifest `keys-top` 4/4 + C1/C2 Q3 sin-scroll + C3 evaluator keys 4/4, `need=10` constante observada, pitch 0.1418 ambos tabs). HIL A (Bronze fact vía `silver_key` 5/10) y HIL B (Silver fact vía `gold_key` 9/10): cubiertos por esa evidencia, cero trade. HIL C (Bronze→Silver SUCCESS) y HIL D (Silver→Gold SUCCESS): `HIL_NOT_EXERCISED` (requieren gasto/uso con aprobación del usuario; no se provoca Gold-full artificialmente). Cero taps live en C5.

C5 DONE. Siguiente: C6 Keys policy + Gold-full consumer (orden Bronze→Silver/Silver→Gold por cantidades/necesidades, consumo de `OUTPUT_FULL` vía Treasure + retry causal).

## 17. E Treasure Gold Keys capability (executor DONE, sin Trading, HIL B PASS)

`bot/treasure_center_semantics.py` (nombres) + `bot/treasure_center.py` (predicados puros estilo C1: `is_treasure_screen`, `clean_treasure`, `has_gold/karat_signal`, `is_gold_keys_content_ready`; Treasure + Gold positivo + limpio, Karat+Gold = contradictorio) + `bot/treasure_keys.py` (capability que confirma readiness, observa currency fresca antes de cada tap, abre acotado con puntos caller-supplied, prueba consumo fresco y se detiene antes de premium). Cero scroll (sin imports swipes/gestos; tiers todos visibles en HIL), cero Equipment Relief (sin imports ni checks; full no bloquea), cero Trading/OUTPUT_FULL/planner/MW/stage (imports probados). Sin detectores/readers/assets nuevos; engine global intacto; sin scope nuevo (consumidor futuro lo promoverá con vocabulario completo).

Contrato: `GoldKeyQuantity(OPEN_ONCE|EXACT|UP_TO|MAX_WITHIN_BUDGET, amount?)` (overshoot nunca confirma: EXACT falla, UP_TO capa con lo verificado); `TreasureCurrencyFact(currency gold_key|karat|empty|unknown|otra-premium, amount_offered 1|10 solo si gold, count?|None, overlay selector|result|None, sequence, evidence)`; `TreasureOpenTargets(open_single_point, open_repeat_point)` caller-supplied, HIL-UNCALIBRATED hasta B (sin hardcode); `GoldKeyOpenRequest(quantity, allowed=={"gold_key"} exacto, targets, max_actions>=1, max_fact_age, source/return_to descriptivos sin navegar)`; `GoldKeyOpenResult(outcome, before?, after?, opened, boundary?, reason?, inputs, evidence)`. Outcomes `SUCCESS|NO_KEYS|PREMIUM_CURRENCY_BOUNDARY|NO_EFFECT|FAILED|CANCELLED|BUDGET_EXHAUSTED`. Currency fresca por apertura (`0<=curr-snap<=max_fact_age`, luego estrictamente creciente); premium/otra no permitida => `PREMIUM_CURRENCY_BOUNDARY` cero taps adicionales; `empty` => `NO_KEYS` (con parcial: EXACT incompleto => FAILED, UP_TO/MAX parcial => SUCCESS con boundary); ilegible/stale => FAILED cero confirm. Postcondición: count disminuye preferido (incremento = diferencia verificada), fallback result exclusivo mínimo demostrado cuando counts ilegibles; unchanged fresco => `NO_EFFECT` sin retry; stale/ilegible => FAILED nunca SUCCESS. Loop acotado por `quantity` + `max_actions` (sin loops ocultos; `BUDGET_EXHAUSTED` si EXACT/UP_TO/OPEN_ONCE no se satisface en budget; MAX usa budget como request). Entry audit: única fuente soportada Lobby (tile `treasure` ~(0.722,0.9167) legacy NO canónico, ningún hardcode); entrada termina en Treasure resolved + Gold ready + primer fact fresco (HIL A manual). Return: capability nunca navega (targets sin back/dismiss); `after` + evidencia para verificación externa (dismiss = tap fuera de botones, Back a Lobby solo si se entró desde Lobby, GT usuario).

No-scroll proof: tiers + popup centrales en capturas, sin gestos; tests de imports/firma/vocabulario. Equipment independence: apertura con 354 Gold Keys e inventario irrelevante; Dorado 354→353 con Equipment intacto (sin Combine/Relief invocados, 1 tap total). No-Trading proof: `OUTPUT_FULL` inexistente como outcome/boundary/`__all__`; `should_open`/`should_return_to_trading`/`retry_silver_to_gold`/`route`/`plan` inexistentes como código.

Tests: `tests/test_treasure_keys.py`, 36 dirigidos verdes (readiness ready/selector/repeat/foreign/overlays/contradictorio/sin-gold/UNKNOWN/AMBIGUOUS; currency gold/karat/otra-premium/empty/unknown/stale/ilegible; open once/batch EXACT 11 repeat+single/no-effect count y estado/stale-after/ilegible/overshoot/mínimo-sin-counts; quantity OPEN_ONCE/EXACT/UP_TO parcial y capa/MAX; budget exacta/agotada/sin-loop-oculto/cancel; equipment-full irrelevante + sin imports/callbacks; routing sin imports ni OUTPUT_FULL + allowlist exacta; return sin navegación + `after` explícito + sin scroll).

Validación: `py_compile` + `git diff --check` limpios; 36/36 Treasure; subset trading+treasure 159 passed (C4/panel/C1/row-facts/materials/keys + Treasure, sin regresiones); sin full suite (ningún compartido tocado); sin evaluator incremental ni corpus (sin detectors/readers/assets).

HIL (canal chat+steer, raws locales `artifacts/hil_treasure_a/` no versionados, 1 tap agente total autorizado explícito): A PASS (entrada manual Lobby→Treasure, grilla tiers 188/104/Free/354/155 + Gem, Gold dorado 354/499 Needs:1 GT, cero Karats en grilla GT, salida manual a Lobby, cero aperturas, cero taps agente, 1 captura). B1 PASS (popup dorado: 1(Open)/10(Open) ambos icono Gold Key, cero Karats, Needs:1; cero gasto, cero taps agente, 1 captura + GT). B2 PASS (1 tap agente autorizado en 1(Open) interior (0.618,0.548)→(1677,669) 2712x1220; dorado 354→353, recompensa Laoku's Fatal Faulds GT, oro/Karats intactos, cero premium, sin retry; 1 captura resultado + GT; dismiss manual tap-fuera + Back a Lobby GT). C batch/repeat: `HIL_NOT_EXERCISED` (control 10(Open) existe en captura + batch EXACT 11 offline verde; gastar 10 keys requiere aprobación no pedida aquí). D boundary premium: `HIL_NOT_EXERCISED` honesto (353 restantes, sin low/no-keys natural; no se fabricó boundary gastando keys; cubierto offline + Astra `key==karat` fail-closed).

E Treasure DONE (capability independiente, HIL open-once PASS). Resta C6: policy/orchestration Keys (orden/cantidades por necesidades) + consumer Gold-full (`OUTPUT_FULL` Silver→Gold → Treasure `UP_TO(n)` suficiente sin vaciar + retry causal + retorno verificado).
