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
