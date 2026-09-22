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

## 18. C6a pure Keys promotion policy (DONE, sin runtime, sin Treasure)

`bot/keys_promotion.py` (nuevo, sin cambios a compartidos): policy pura y stateless que decide UN próximo paso por llamada para C5. Sin UI, sin llamadas C5/C4, sin navegación, sin Treasure/Craft/Relief/MW/planner/stage (imports probados: sólo `KeyTradeOperation` + tipos C4/C3). Sin detectors/readers/assets; engine global intacto.

Ordering rule (determinista, sólo inputs observables): Silver tradeable (`gold_key` have≥need) → `SILVER_TO_GOLD` primero, antes de producir más Silver; si no, Bronze tradeable (`silver_key` have≥need) → `BRONZE_TO_SILVER`; si ninguno → `NO_MORE_PROMOTIONS`. No orden fijo ciego: cada decisión re-evalúa desde estado fresco. Historia no aporta regla más precisa con facts hoy confiables (Astra ordenaba con aritmética de capacidad inferida sin GT de Gold capacity; descartada por diseño). No se afirma optimización de capacidad Silver: es la regla "consumir Silver disponible hacia Gold antes de producir más", sin arithmetic de output-cap.

Quantity mode: todo `NEXT_OPERATION` lleva `MAX_ALLOWED` (C4 ya limita por `have//need` y cap observado del panel; la policy no calcula capacidad de output ni toca `>>`).

Freshness: `decide_next_keys_operation(silver_fact, gold_fact, budget_remaining)` valida identidad/forma; `decide_after_trade(previous, result, budget_remaining, silver_fact?, gold_fact?)` exige, en paths que podrían autorizar otro trade (`SUCCESS`/`INSUFFICIENT_INPUT`/`NO_MORE_INPUT`), fact-set estrictamente más nuevo en AMBAS filas, y re-decide vía `decide_next` (nunca inventa una fila desde el `after_fact` de la otra). Reuso del snapshot pre-trade ⇒ `FAILED/stale_facts`. Paths terminales no requieren relectura.

Gold-capacity boundary: `OUTPUT_FULL` de `SILVER_TO_GOLD` ⇒ `GOLD_CAPACITY_BLOCKED` con `PendingCausalOperation` preservada (operation, quantity original, before_fact ejecutado, boundary, reason, evidence, metadata de sequences). Sin Treasure: no calcula relief Gold, no abre Gold Keys, no arma segundo intento (C6b con Treasure runtime completo). `OUTPUT_FULL` de `BRONZE_TO_SILVER` ⇒ `FAILED/unexpected_output_full` fail-closed. `NO_EFFECT`/`FAILED`/`CANCELLED` ⇒ `FAILED` terminal sin segundo intento; `LIMIT_REACHED` ⇒ `FAILED`.

Budget explícito sin default: `budget_remaining` requerido no-negativo; cero ⇒ `BUDGET_EXHAUSTED`. Cada operación ejecutada la descuenta el caller; la policy no tiene contadores ni loops (decisiones sin `while`/`for`).

No-Treasure proof: cero imports treasure/craft/relief/MW/planner/stage; `GoldKeyOpenRequest`/`route_plan`/`should_`/`promote`/`_key_counts` inexistentes como código; `pending` expone exactamente `{operation, quantity, before_fact, boundary, reason, evidence}`; Gold capacity documentada `NOT OBSERVABLE`.

Tests: `tests/test_keys_promotion.py`, 46 dirigidos verdes (orden 5, refresh 6, quantity 3, boundaries 11, budget 5, facts 4, separación 6 + tradeability). Validación: `py_compile` + `git diff --check` limpios; C6a 46/46; subset trading+treasure 148 passed (C5/C4/row-facts/Treasure, sin regresiones); sin full suite (ningún compartido tocado); sin evaluator/corpus/HIL (policy pura offline).

C6a DONE. Siguiente: E2 Treasure runtime promotion + C6b orchestration (consumer Gold-full → Treasure acotado + retry causal + retorno verificado).

## 19. E2 Treasure runtime promotion (perception + runtime autónomo, HIL smokes pendientes)

E2 promueve Treasure desde capability lógica caller-driven (E) a capacidad autónoma usable por runtime normal, sin decidir por qué se abre y sin conocer GOLD_CAPACITY_BLOCKED, SILVER_TO_GOLD, Keys policy, Trading route ni relief. Frontera: clean Lobby → enter Treasure → screen.treasure + Gold readiness positiva → facts frescos → targets calibrados → GoldKeyOpenRequest existente → consumo verificado → retorno a clean Lobby.

Tabla runtime need (auditoría E2):

| runtime need | hoy existe? | evidencia | promotion needed | HIL needed |
|---|---|---|---|---|
| screen.treasure resoluble | NO (sólo nombres E, sin detectores ni regla) | `treasure_center_semantics.py` + Astra `screen.treasure`/`relief_treasure` | SÍ: title spec + regla resolver + motor global | NO (offline + evaluator) |
| Gold readiness positiva | parcial (predicados sobre snapshots sintéticos) | `treasure_center.py`, E 36 tests | SÍ: detectores Gold con gate de título | SÍ parcial (Smoke A/B) |
| Gold-vs-Karat fail-closed | parcial (allowlist + facts caller) | E `check_currency`, Astra `key==karat`, frame Karat archival | SÍ: detectores Karat + facts runtime de percepción real | Q4 en vivo si mostrable sin costo; si no, HIL_NOT_EXERCISED + ausencia-Gold bloquea |
| entry Lobby→Treasure | NO (doc describe tile legacy) | `constants.py treasure ~(0.722,0.9167)`, Astra OPEN_TREASURE (0.720,0.915), `lobby.png` | SÍ: entry target remedido (0.721,0.892) + op enter | SÍ (Smoke A) |
| selector (Gold chest→popup) | NO (E asume popup; tap manual en HIL B) | Astra GOLD_CHEST + B1 popup | SÍ: gold-chest target + transición verificada | SÍ (Smoke B) |
| 1(Open) productivo | parcial (punto HIL sin profile) | E HIL B2 (0.618,0.548)→(1677,669) 2712x1220 | SÍ: profile + wiring a capability | SÍ (Smoke B, 1 key con aprobación) |
| 10(Open) productivo | NO (control existe, tap no ejercido) | B1/B2 muestran ambos controles Gold | geometría calibrada (0.693,0.540); tap HIL_NOT_EXERCISED salvo aprobación | SÍ sólo con aprobación (Smoke C) |
| result/postcondition | parcial (semántica E sin señal) | B2 resultado + archival karat-cutoff | SÍ: detector result + facts overlay | SÍ (Smoke B) |
| dismiss + Back→Lobby | NO (manual en E) | Astra TREASURE_DISMISS/BACK + GT manual | SÍ: op leave con postcondition fresca | SÍ (Smoke A/B) |
| count Gold Keys | NO (OCR nuevo, campaña grande) | counts visibles 354→353 pero sin reader | NO: count=None; postcondition por transición exclusiva | NO |

Percepción (`bot/perception/treasure_center.py`, nuevo; `TREASURE_SCOPE` 1 spec + 1 detector especializado):

- `TREASURE_TITLE_SPEC`: 3 variantes del banner (Sept brillante, dimmed single-result, April grid) en `assets/ui/landmarks/treasure/`, región top-center, cal (0.52,0.90). Positivos 1.00 (grid/popup/result actuales, grid April, resultado April con filas); banners mismo-plate (Combine/Guild) ≤0.49, Lobby/Trading ≤0.23. Promovido al motor global (96→97) y a `STRONG_LOBBY_COMPLETION` (72→73) como base foreign.
- `TreasureContentDetector` (standalone, todo gateado en título>0): popup por label `1(Open)` (T1 0.207 vs 0.000, cal 0.05/0.12); repeat-label `10(Open)` (0.197 vs spillover grid 0.092, cal 0.12/0.16, +gate popup); iconos Gold vs Karat magenta (Gold T1 0.090/T2-barra 0.133, Karat archival-K 0.122-0.172, púrpura 0.000 en todo Gold; cal Gold 0.05/0.08, Karat 0.03/0.09); grid-gold Needs row (0.110-0.118 vs dimmed 0.000-0.002, cal 0.02/0.08); result cofre abierto (T2 0.390/K 0.426 vs ≤0.029 con título, cal 0.08/0.25).
- Emite: `landmark.treasure_title` (global) + en scope `indicator.treasure_selector_popup`, `indicator.treasure_result`, `gold_key_selector/repeat`, `karat_base/repeat`. Sin título: cero emisiones (silencio cross-screen verificado en lobby/trading/combine/guild).
- Límites: Karat center-popup sin positivo vivo (HIL_NOT_EXERCISED; misma ROI que barra, y ausencia-Gold ya bloquea); resultados gem-row y banner archival totalmente cubierto (K) bajo anchor por diseño; `empty`/count sin señal (no-Keys natural nunca fabricado).

Catálogo/resolver: `SCREEN_TREASURE` + 7 observaciones (`+2` popup/result nuevas), regla base por título; `is_gold_keys_content_ready` intacto (E verde).

Runtime (`bot/treasure_profile.py` + `bot/treasure_facts.py` + `bot/treasure_runtime.py`, nuevos; 6 acciones + `TreasureActionTargets` en executor):

- Profile: entry (0.721,0.892) remedido lobby; gold-chest (0.636,0.380) T0+Astra; single (0.618,0.548) HIL B2 PASS; repeat (0.693,0.540) centroide label B1; dismiss seguro `(0.08,0.65)` en corredor lateral izquierdo, validado por el HIL productivo final de la sección 24; back (0.802,0.073) Astra+glyph T0. Puntos interiores con margen, bboxes popup disjuntas.
- Facts: `fact_for_single/repeat` puros desde snapshot fresco (control-selectivo veraz: el monto codificado SÍ está ofrecido con icono Gold y sin Karat). Karat anywhere→fact karat (contradicción fail-closed); sin Gold ni Karat→unknown (nunca autoriza); count=None; overlay selector/result (result gana); None sólo en foreign/UNKNOWN/AMBIGUOUS. `empty` no observable en E2 v1: depleción = fail-closed sin boundary verificado (límite para C6b).
- Operaciones single-attempt (`max_attempts=1`), sin retry ciego: enter (Lobby limpio→OpenTreasure→screen.treasure), execute (readiness→SelectGoldChest→popup→capability E con plan greedy 10s+1s y read_state fresco por snapshot→consumo verificado), leave (dismiss si result→Back→Lobby limpio verificado), wrapper enter→execute→leave restaurando Lobby siempre (hasta en FAILED/CANCELLED).
- Separación testeada: cero imports Trading/C6a/scroll/Craft/Relief/Equipment/MW/planner/stage; sin GOLD_CAPACITY_BLOCKED; sin combine/inventory en firmas; taps sólo por ADB.

Validación: `py_compile` + `git diff --check` limpios; E2 38 tests (percepción 6 con manifiesto exacto 0 wrong + runtime 32) + E 36 intactos; pines globales actualizados tras revisión (97 detectores, 20 reglas, 105 observaciones, strong-lobby 73, scopes 79); 1 regresión real convertida en evidencia (frame April `171606` Bronze-popup ahora resuelve screen.treasure correctamente); full hardware-free 2786 passed + 1 pin corregido (suite 2787, verde salvo error ambiental tmp_path resuelto con basetemp local).

HIL (canal chat+steer, UNA condición por vez): Q1 lobby-tile, Q2 grid Gold, Q3 popup/result single, Q4 Karat (sólo si mostrable SIN gastar premium), Q5 control 10(Open), Q6 dismiss/Back. Smokes A (entry/exit, 0 opens), B (single, 1 key con aprobación), C (batch 10, sólo con aprobación; si no, HIL_NOT_EXERCISED y C6b usa singles).

E2 DONE sólo con HIL A+B PASS + docs + suite verde + diff limpio. STOP después de E2 (C6b siguiente, Craft/Relief/MW fuera).

## 20. E2 DONE: HIL A+B PASS con freshness por timestamp (2026-09-18)

Smoke A PASS con código `f1d387c` (Lobby→Treasure→Lobby, 2 taps causales, Gold readiness positiva, cero opens). Smoke B bloqueó dos veces en `stale_fact` con cero gasto: `sequence` es contador del decoder (~30fps) y el snapshot autorizador envejece ~0.3s durante el analyze, así que el gap medía latencia del pipeline, no edad del contenido (un bump `max_fact_age` 2→8 falló live y se revirtió).

Fix (`fix: use observation time for treasure freshness`): `TreasureCurrencyFact.observed_at` copiado del capture timestamp monotónico (Capture→Observation→snapshot→fact; builders jamás estampan now), barrera causal (`observed_at` > timestamp del snapshot selector) + `max_fact_age_s=2.0s` (renombrado con unidades; sequence queda sólo para orden/dedup). Tests 86 (runtime 33 + keys 47 + percepción 6, incl. regresión Smoke B con gap 60 seqs/skew 0.3s).

Smoke B PASS con el fix: gate timestamp OK live, 1 tap selector + 1 tap single causal (cero retry, cero premium), after a 0.86s aún con popup (`NO_EFFECT` fail-closed correcto), resultado tardío (~2s+) observado y normalizado por el leave (dismiss verificado) + retorno a Lobby limpio 3/3. Consumo verificado por GT humano: contador cofre Gold 353 (foto) → 352 con exactamente 1 tap. Límite conocido: el after inmediato puede ser prematuro con animaciones lentas; el leave normaliza el result tardío. Batch 10 y Karat live: HIL_NOT_EXERCISED. E2 DONE; C6b next, no iniciado.

## 21. E2.1: ventana post-action bounded para el open (2026-09-18)

Divergencia: con frescura resuelta, el capability hacía UN solo `read_state` post-tap y cerraba `NO_EFFECT` si ese frame aún mostraba el popup (HIL: popup a +0.86s, result a ~3-3.5s en dos noches). Para C6b, un éxito real clasificado como failure es inaceptable.

Fix (`fix: wait for treasure open postcondition`): tras el tap único (nunca repetido), ventana bounded que polea reads frescos hasta evidencia de consumo/result, boundary, cancel o deadline. `post_action_timeout_s=5.0` (~1.4x la latencia observada + margen de carga); `post_action_max_polls=1000` red pura anti-clock-roto que jamás debe mandar (HIL: 48 polls a ~50ms truncaron la ventana a ~2.5s antes del result de ~3.5s). Resample/ilegible = sin evidencia (esperar, jamás failure ni tap). Result con `observed_at` ≤ barrera del tap jamás es SUCCESS. `NO_EFFECT` ahora exige ventana agotada (`state_unchanged` si lo último visto es estable, `no_evidence` si no); reasons `stale_after_fact`/`after_fact_unreadable`/`have_unchanged` eliminados. Tests 91 (runtime 33 + keys 52 + percepción 6).

HIL B2 segunda noche con la ventana (timeout 4.0s/polls 48 iniciales): gate OK, 1+1 taps, `NO_EFFECT` a ~2.5s por el bound de polls, pero SUCCESS físico: frame con cofre abierto + "Laoku's Fatal Helmet" + contador 352→351 (foto) + result normalizado por el leave + Lobby 3/3. Cero premium, cero retry. E2.1 validado por evidencia física en dos noches; el string SUCCESS del runtime se confirma en el próximo open (el fail-mode residual es fail-closed seguro). C6b desbloqueado.

## 22. E2.2: fast gold key drain primitive + cadence HIL (2026-09-18, PARTIAL)

Semantica nueva (amount-agnostic, sin OCR del numero):

- `RIGHT_GOLD_OPEN_MAX` (`bot/treasure_center.py::has_right_gold_open_max`):
  boton derecho accionable respaldado por Gold Keys, abre el maximo que la
  UI ofrezca (1..10). Solo senal repeat Gold sin contradiccion Karat.
- `RIGHT_KARAT_OPEN` (`has_right_karat_open`): mismo rol respaldado por
  Karats/premium. Terminacion normal, cero taps.
- Gold+Karat simultaneo: contradiccion, cero input
  (`has_right_button_contradiction`).
- Boton izquierdo `1(Open)` nunca es target de drain (sin referencias en codigo).

Auditoria UI (raws E/E2/E2.1):

| state | right-button bbox | currency backing | amount text | stable during animation? | HIL status |
|---|---|---|---|---|---|
| grid limpia | N/A (sin boton) | grid gold tile | N/A | N/A | PASS (Smoke A + E2.2 dry) |
| selector popup inicial | x 0.650-0.730 / y 0.395-0.565, punto (0.693, 0.540) | Gold (repeat) | 10(Open); variantes 1..9 HIL_PENDING | NO (persiste ~0.9s post-tap) | PASS B1 (cero taps) |
| overlay/result repeat | barra inferior icono x 0.305-0.365 / y 0.78-0.86, punto (0.335, 0.82) | Gold (bar icon, sin label) | 10(Open); 1..9 HIL_PENDING | NO (batch-10 tapa el titulo) | PASS E2.2 (1 tap = 1 batch-10) |
| batch-10 reward grid | barra inferior 1/10 Gold visible (bar pair 1.0, karat 0.0) | Gold (bar pills) | 10(Open) Gold | NO (transient conocido, titulo oculto) | PASS E2.2-correccion (right button sigue accionable, cero dismiss) |
| Karat boundary | mismo rol, backing premium | Karat | N/A | N/A | HIL_NOT_EXERCISED (offline verde) |

Target inicial y repeat overlay NO son el mismo: el drenaje resuelve por
snapshot (`resolve_right_button_target`: result -> barra, sino selector).
Detector actual distingue Gold vs Karat en ambos (popup: label+icono;
barra: icono bajo gate de result). No se cambio ningun detector/ROI/
threshold: la semantica ignora el numero por construccion.

Primitiva (`bot/treasure_fast_drain.py`, Treasure-only, sin
Trading/C6a/C6b/Craft/Relief/MW/planner/stage/scroll/ADB):

- `drain_gold_keys_fast(...) -> GoldKeyDrainResult` con
  `GoldKeyDrainConfig(tap_interval_s=0.20, watchdog_every=10,
  safety_deadline_s=300.0, max_inputs=10000, transient_wait_s=5.0)`.
- Entrada solo con `initial_open_verified=True` + repeat state + fresh.
- Un tap por observacion fresca (`observed_at` estrictamente mayor;
  resample se salta sin tap). Sin sleeps de animacion, sin result
  completo por tap, sin scope completo por ciclo.
- Watchdog cada N inputs: contexto Treasure, compatibilidad
  popup/result, coherencia Gold/Karat, no foreign, no UNKNOWN/AMBIGUOUS
  accionable, mas fingerprint visual barato del ROI de animacion/result
  (default: hash 4x4 downsampleado de `TREASURE_RESULT_REGION`, numpy
  puro, inyectable). Boton identico + ROI sin variacion ->
  STALL_SUSPECTED, cero taps mas.
- UNKNOWN/AMBIGUOUS post-tap (animacion tapa el landmark): espera
  bounded sin taps, retoma si vuelve RIGHT_GOLD, Karat -> EXHAUSTED,
  timeout -> FAILED fail-closed.
- Terminacion normal solo por RIGHT_KARAT_OPEN sin Gold en ningun lado
  (GOLD_KEYS_EXHAUSTED, cero premium). Remanente 1..9 por boton derecho.
  Sin terminacion por conteo de taps; sin `opened` reportado
  (`inputs_emitted` nunca es batches).
- Outcomes: GOLD_KEYS_EXHAUSTED | STALL_SUSPECTED | CONTEXT_LOST |
  FAILED | CANCELLED | SAFETY_DEADLINE. Telemetria separada:
  inputs_emitted, watchdogs_run, gold_button_observations,
  karat_boundary_seen.

Tests: `tests/test_treasure_fast_drain.py`, 35 dirigidos verdes
(semantica 7, loop 4, watchdog 7, cadence 2, safety 4, terminacion 4,
separacion 4). Validacion: `py_compile` + `git diff --check` limpios;
E2.2 35/35 + E/E2 91 intactos (keys+runtime+percepcion); sin full suite
(solo predicados puros aditivos en `treasure_center.py`, sin cambios de
detectores ni comportamiento existente); sin evaluator (sin cambios de
deteccion); `test_local_cv_perception` 17/17 con basetemp local
(el error tmp_path del sistema es ambiental, no relacionado).

HIL (canal chat+steer, `tools/hil_treasure_fast_drain.py`, raws
`artifacts/hil_e2_fastdrain/` no versionados, aprobacion por rafaga):

- Dry-run: grid limpia Treasure + `gold_key_selector` 1.00, cero Karats,
  cero taps. GT: cofre dorado 319/499.
- Entry E2 OPEN_ONCE: runtime `NO_EFFECT`/`no_evidence` (fail-mode
  residual E2.1, tercera ocurrencia), pero GT fisico prueba 1 open real:
  319->318 + result "Boots (Enhance)" + barra 1/10 Gold (8/8 dry frames
  `right_gold=True` estable).
- Round A (0.20s, max 15, aprobado): fast entry OK sobre GT fisico;
  tap #1 en barra (0.335, 0.82) limpio en su slot; siguiente frame
  UNKNOWN (animacion) -> fail-closed correcto, 1 input, 0.56s.
  Fix aplicado: UNKNOWN/AMBIGUOUS con espera bounded en vez de fallo
  inmediato (offline + test de recuperacion verdes).
- Hallazgo HIL mayor: el tap #1 en 10(Open) consumio UN batch de 10
  (GT usuario: 318->308 + grilla persistente de 10 recompensas). La
  grilla batch tapa el banner del titulo -> UNKNOWN persistente (~40s,
  no auto-dismiss). SUPERSEDED por correccion E2.2 (seccion 23): la
  inferencia de que el drain necesita dismiss fuera de botones era
  conceptualmente incorrecta. Ground truth del usuario: el boton
  derecho Gold-backed permanece accionable durante animacion/reward
  (dual role: corta la animacion o inicia el siguiente batch) y es el
  unico target correcto. La grilla es transient conocido, no loss.
  Cadence multi-tap + full-drain se cerraron en la seccion 23.
- Live probado: hit del target de barra, 1 tap = 1 batch-10, cero taps
  premium (11 keys gastadas, 0 premium), cero mis-taps, fail-closed ante
  UNKNOWN correcto, `bar_repeat_gold` ejercitado en vivo. Cadence
  default queda en 0.20s inicial sin refutar (un tap limpio).
- HIL_NOT_EXERCISED honesto: watchdog live, stall visual live, Karat
  boundary live, remanente 1..9 live, 0.15s/0.10s, full drain.

Performance aproximada live: ~5 analyzes/s con scope Treasure standalone
(2 detectores) en el burst; dry-run ~2.5-3/s con sleeps de 0.25s.
Captures/s del decoder ~100+/s (sequence a video-rate). Sin percepcion
global por ciclo (solo scope Treasure); watchdog/exit usan el mismo
scope barato.

Estado E2.2 al cierre de seccion 22: implementacion DONE + HIL PARTIAL
(single-tap PASS + boundary batch-grid documentado, con inferencia de
dismiss pendiente de correccion). Ver seccion 23 para el cierre.

## 23. E2.2 correccion: causal loop a traves del reward + full-drain PASS (2026-09-18)

Causa del error conceptual anterior: ante el UNKNOWN persistente de la
grilla batch-10 se infirio que el drain necesitaba dismiss fuera de
botones (propiedad del integrador). Ground truth del usuario lo refuta:
el boton derecho Gold-backed sigue disponible durante animacion/reward,
cada tap tiene dual role (corta animacion o inicia batch, sin etiqueta
a priori) y es el unico target correcto. Tocar fuera para avanzar era
incorrecto; la grilla es transient conocido, no context loss.

Contrato corregido (solo `bot/treasure_fast_drain.py` + tests, sin
cambios de detectores/percepcion global):

- `TREASURE_GOLD_REWARD_ACTIVE` (local, no globalizado): post-open con
  lineage verificada + pair Gold title-independent (popup single+repeat
  o barra single+repeat, contrato 0.50 identico al detector) + cero
  Karat + frame fresco. Reutiliza `TreasureContentDetector.measure`
  (mismos ROIs/thresholds; medido en raw Round A: barra 1.0/1.0,
  karats 0.0, titulo 0.0; negativos: Lobby 0.0 en todo, grid limpia
  popup 1.0/barra 0.0). Sin detector nuevo, sin manifest, sin evaluator.
- Loop: observed-RIGHT_GOLD o local-GOLD -> un tap al mismo boton
  derecho (lado por snapshot/lectura); Karat observado o local sin Gold
  -> cero taps + confirmacion bounded; resto -> espera bounded. Entrada
  acepta frame transient con lineage (`entry:reward_transient_local`).
- Watchdog corregido: saludables A (titulo+Gold), B (reward+local
  Gold), C (repeat+Gold). STALL solo si ningun tap de la ventana cambio
  nada observable (fingerprint ROI + nombres de observaciones);
  churn observed<->transient es progreso (falso STALL de Round A
  corregido con test dedicado).
- No-dismiss invariante testeado (sin identificadores dismiss/outside
  en codigo; todo tap cae en punto derecho) + left-button nunca usado.
- Cadence default 0.15 (medida estable, ver HIL).

Tests: 52 dirigidos verdes (35 previos + transient/reward 6,
no-dismiss 2, dual-role 2, watchdog corregido 3, terminacion local 2,
entrada transient 2, flag 1). Regression: keys+runtime+percepcion
intactos (143 totales con fast-drain). `py_compile` + `git diff
--check` limpios; sin full suite (cambios acotados a fast-drain,
predicados aditivos previos intactos); sin evaluator (sin cambios de
deteccion).

HIL (misma herramienta `tools/hil_treasure_fast_drain.py` + medida
local cableada, raws `artifacts/hil_e2_fastdrain/`):

- Round A retry (0.20s, max 20, aprobado): E2 entry SUCCESS (opened=1,
  primer string SUCCESS del runtime con `consumed:1`); 10/10 taps en
  ~4s (7 observed-bar + 3 local-bar), watchdog sano; real ~0.40s/tap
  (overhead ~0.20s analyze+ADB). Falso STALL inicial -> fix watchdog
  (offline verde) antes de seguir.
- Round B (0.15s, max 20, aprobado): un flake de entrada E2
  (`selector_failed`, cero gasto) + retry SUCCESS inmediato; 20/20 taps
  en 7.5s (13 observed + 7 local), 2 watchdogs sanos, cero premium,
  cero contradiction, cero context loss, cero stalls, cero mis-taps.
  Real ~0.375s/tap: 0.15 gana ~6% sobre 0.20 (floor ~0.22s overhead);
  0.10 no aportaria (STOP de tuning por regla). Cadence final 0.15.
- Full drain (aprobado, DRAKEN=BB, ~255 keys): E2 entry SUCCESS +
  48 inputs en 16.7s hasta `GOLD_KEYS_EXHAUSTED` (`karat_boundary`,
  4 watchdogs sanos, 49 gold observations). Frontera observada:
  gold-repeat -> vacio -> `karat_base+karat_repeat` 1.00 (primer
  ejercicio live del detector Karat). Frame final: cofre 0/499,
  Needs 80 karats, barra 1(Open)=80 + 10(Open)=800 en magenta.
  Remanente 1..9 atravesado automaticamente por el boton derecho.
  Cero taps premium, cero fuera/izquierdo, cero contradiction/loss.
- Contabilidad live: 319->318 (E2) ->308 (batch-10) ->298 (manual
  usuario) ->257 (Round A + manual) ->255 ->~0 (full drain 48 inputs
  mixtos). Nunca `inputs == batches`.

Performance live: ~2.5-2.7 taps/s sostenidos (floor analyze+ADB);
scope Treasure de 2 detectores por ciclo; watchdog/exit mismo scope.

Estado E2.2: DONE (implementacion + cadence 0.15 caracterizada +
full-drain PASS hasta Karat con cero premium + docs corregidas).
C6b next (desbloqueado por E2.2 DONE).

## 23-addendum. Finalize post-Karat HIL: punto GT + efecto probado (2026-09-18)

Recuento honesto de la prueba del dismiss:

- Short drain DRAKEN-BK (221 keys): E2 entry SUCCESS + 60 taps sanos
  (0.15s, 6 watchdogs, 0 premium) hasta fuse, sin Karat todavia; el
  contrato prohibe el tap externo con Gold, asi que el intento de
  finalize (0.9, 0.64) corrio en el drain anterior y fallo cerrado
  (`dismiss_no_effect`, 1 tap, 0 premium): el punto Astra cae ~220px
  del habitual y lo traga un tile.
- GT usuario para el punto: matriz 5x10, celda (3,9) -> (0.85, 0.50),
  "a la derecha donde debajo del overlay no hay nada interactuable".
  El punto queda normalizado y poseido por
  `TREASURE_PROFILE.dismiss_point`; `ActionExecutor` y fast-drain lo
  consumen sin literales duplicados.
- El usuario pidio cerrar la animacion con Gold todavia presente; se
  rechazo el tap externo (contrato) y, con aprobacion explicita, se
  emitio UN tap derecho (dual role: abrio un batch nuevo, sin
  cortar): evidencia de que el boton derecho gasta mientras hay Gold.
- Con autorizacion explicita renovada, UN tap fuera en (0.85, 0.50):
  overlay cerrado INMEDIATAMENTE a grid limpia, cofre 0/499 con
  Needs 80 karats, karats intactos (28,963), cero gasto, cero efectos
  laterales. Efecto del punto GT probado en vivo.
- BK tambien dreno a Karat (221->0): segundo full drain implicito con
  la misma protection (0 premium en ambos personajes, ~550 keys
  totales drenadas en la sesion).

Auditoria senior posterior: el unico finalize productivo registrado
(`20260918T021909`) uso el punto viejo y fallo
`dismiss_no_effect`. El tap exitoso (0.85,0.50) fue manual/ad-hoc:
demuestra la geometria fisica, no la ruta productiva. Por eso el
productive-path HIL quedaba PENDING en ese checkpoint; estado superseded por
el cierre físico de la sección 24.

La implementacion final reutiliza `TapThroughAnimation` sin cambiar su
contrato: precondicion fresca result+RIGHT_KARAT_OPEN+no Gold por tap,
timeout/max-taps/cancel bounded, y SUCCESS solo tras snapshot posterior
Treasure sin result ni Gold. La primitiva solo posee el post-Karat;
nunca interviene entre batches Gold.

El incidente de cupo 40->60 tampoco fue overflow del loop: el artifact
`20260918T024337` registra `max_inputs: 60` y 60 taps exactos. La
divergencia fue entre el cupo anunciado y el argumento ejecutado,
agravada porque la entrada E2 no compartia ese contador. La herramienta
ahora exige `--approved-economic-inputs`, resta la entrada E2 del mismo
presupuesto, instala un hard guard independiente en cada tap derecho y
cuenta final tap-through por separado.

Back/exit sigue cubierto por regression E2 leave (Smoke A/B 3/3). El cierre
productivo posterior está documentado en la sección 24.

## 24. E2.2 recovery: cierre físico y falso negativo corregido (2026-09-21)

HIL productivo único (`artifacts/hil_e2_fastdrain/20260921T184146/`):

- Gold Keys 27→0; initial open `SUCCESS`; 10 inputs económicos dentro del
  cap aprobado 20 (entrada 1 + nueve derechos); frontera Karat fresca en
  sequence 623; cero taps derechos posteriores.
- Premium 33,509→33,509 y Gold currency sin cambios. La telemetría registra
  intención/autorización, pero la invariancia física proviene de las capturas
  y GT, no de contadores derivados.
- `TapThroughAnimation` emitió dos taps, ambos mediante
  `DismissTreasureResult` en el único target profile-owned `(0.08,0.65)`.
  GT humano: overlay cerrado y Treasure estable. El target lateral queda PASS
  físico; no se cambió `TapThroughAnimation` ni se creó otro finalizer.

El harness informó `dismiss_no_effect`, pero fue un falso negativo software,
no un fallo físico. El frame posterior 707 resolvió Treasure sin overlay ni
`treasure_result` y conservó sólo `treasure_gold_key_selector@1.00`.
`_final_reward_cleared()` usaba la evidencia amplia `has_gold_signal()` y
confundía ese selector aislado con el retorno del control económico derecho;
por eso `expected`, `tappable` y `transient` resultaron falsos.

Fix offline mínimo: el contrato del finalizer usa
`has_right_gold_open_max()` exclusivamente donde pregunta si reapareció el
control derecho Gold real. La postcondición es Treasure estable + reward/result
ausente + `RIGHT_GOLD_OPEN_MAX` ausente. El selector aislado permite completion;
repeat Gold real continúa siendo incompatible y no autoriza otro tap lateral.
Los usos de `has_gold_signal()` para contradicción Gold+Karat, frontera Karat y
espera por evidencia Gold amplia permanecen intactos. Regresión explícita del
frame 707: TapThrough `COMPLETED` → `GOLD_KEYS_EXHAUSTED`, sin reactivar input
económico.

Validación final offline: sintaxis verde; fast-drain 68 passed; runtime,
Treasure keys, TapThrough + consumidores, ActionExecutor y HIL cap 293 passed
(264 directos + 29 reejecutados con basetemp local por un PermissionError
ambiental de pytest). `git diff --check` limpio. Sin evaluator (ningún cambio
de detector/reader/ROI/asset) y sin full suite (cambio Treasure-local; primitive
TapThrough intacta). No hubo segundo HIL. E2.2 DONE; C6b NO INICIADO.

## 25. Prerrequisito C6b: navegación Trading verificada (2026-09-21)

Gap causal confirmado en `d6fdb52`: C1-C5 aportaban percepción, facts y trade,
pero no existían acciones ni runtime públicos para Lobby↔Trading o restaurar
Avatar & Keys. La coordenada legacy no se promovió por confianza histórica.

Adquisición HIL mínima (`artifacts/hil_trading_navigation/20260921T211707/`,
raw local ignorado), 2712x1220, un input autorizado por condición y GT humano:

- Lobby→Trading es directo, sin Quick Menu: `(662,1089)` abrió Trading fresco
  en General. El target profile usa el centro normalizado del mismo píxel.
- General→Avatar & Keys: `(1317,293)` activó la pestaña y mostró cuatro filas
  Keys frescas; cero scroll y cero inputs de fila.
- Trading→Lobby usa la X roja propia, no Back genérico: `(2108,170)` cerró a
  Lobby limpio, confirmado por el usuario.

Implementación mínima: `OpenTrading`, `SelectTradingAvatarKeys` y
`CloseTrading`; `TradingActionTargets`; profile HIL; y `TradingRuntime` con
`enter_from_lobby`, `ensure_avatar_keys` idempotente y `leave_to_lobby`.
Cada transición usa `VerifiedTransition` single-attempt y sólo completa con
postcondición posterior fresca. `build_trading_navigation_perception` es opt-in:
mantiene vocabulario global resolver-complete para Lobby y agrega los detectores
Trading tabs/rows existentes; el hot path global queda intacto y no hay fallback
scoped→global dentro de una espera.

Smoke productivo posterior al código: Lobby→Trading fresh PASS y salida→Lobby
fresh PASS; la entrada recordó Keys y `ensure_avatar_keys` completó idempotente
sin tap. Segunda condición, preparada manualmente en General: selección
`trading.select_avatar_keys` `SUCCESS_FIRST_ATTEMPT` (seq 110) y cierre
`trading.leave` `SUCCESS_FIRST_ATTEMPT` (seq 239), exactamente dos taps, cero
retry, scroll, filas, trade o gasto.

Validación: sintaxis verde; runtime+ActionExecutor 151 passed inicialmente y
21 tests directos finales; regresiones C1-C5/percepción Trading/navegación Lobby
328 passed. Sin evaluator (ningún detector/reader/ROI/asset cambió) y sin full
suite (default perception y contratos compartidos existentes no cambiaron de
comportamiento; sólo builder opt-in + intents/targets aditivos). Este checkpoint
cierra únicamente el prerrequisito físico; C6b continúa NO INICIADO.
