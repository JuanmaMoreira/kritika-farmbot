# Roadmap — Kritika FarmBot 0.2

El orden es deliberado: estabilizar primero el baseline, luego reducir el costo perceptivo y recién después reconstruir Inventory Relief. No se portan commits experimentales en bloque.

## Fases

### 0. Baseline estable reconstruido — DONE

- Checkpoint productivo adoptado: `71340f58d3a4515facc346ad22addfc0d814a6ec`.
- Rama experimental preservada en `archive/inventory-relief-experimental` desde `024ff8e15f981930e3bab962ed116f1e9f3946fe`.
- Rama `rebuild/stable-baseline` creada sin mover `main`, borrar branches, reescribir historia ni hacer push.
- Baseline hardware-free canónica: 1925/1925.

### 1. Disciplina de agentes y skills — DONE

- `AGENTS.md` compacta el ciclo evidencia → primera divergencia causal → clasificación → cambio mínimo → validación mínima → stop.
- `kritika-dev-workflow` cubre desarrollo/diagnóstico ordinario.
- `kritika-hil-acquisition` cubre adquisición y calibración HIL.

### 2. Contexto documental reconstruido — DONE

- `CONTEXT.md` describe sólo el producto actual.
- `ARCHITECTURE.md` separa lo implementado de la dirección aceptada.
- `ROADMAP.md` vuelve a representar el orden real.
- `docs/HISTORY.md` conserva consolidación, experimento, regresiones, rollback y lecciones.
- La contradicción «Monster Wave sin commit/push» queda corregida sin alterar código.

### 3. Smoke corto del baseline — NEXT

Ejecutar desde la GUI productiva una prueba breve y representativa, no otra rotación 28/28. Confirmar startup, composición y una transición física útil; detenerse al primer desvío causal. No modificar arquitectura durante el smoke.

### 4. Percepción acotada incremental

Elegir un único hot path estable, medir baseline, limitar detectores relevantes y conservar escalación amplia sólo donde haga falta. Validar tests dirigidos, benchmark y un smoke corto antes de avanzar al siguiente consumidor.

- Rotation R1 (`select_predecessor_character`) — DONE: 95→2 detectores, policy/reader local intactos, 2144/2144 hardware-free y smoke natural 1/1 hasta Lobby confirmado.
- Rotation R2-A (wait post-swipe Character Select) — DONE: reutiliza el subset semánticamente idéntico de R1, 95→2, `stable_for=1.0` y scroll/sentinel intactos; 2151/2151 hardware-free y HIL natural 1/1 con Lobby confirmado. R2-B (Select→Lobby) — DONE en B2: 95→77 con todas las dependencias de bases/overlays, sin cambiar policy, action count, retry ni recovery.
- World Boss WB-1 (elegibilidad Daily) — DONE: scope 95→5 en snapshot inicial y wait estable; 2152/2152 hardware-free y `Run Session` natural 1/1, sin cambiar policy ni inputs. Correctness Select Boss/Previous Rewards/Raid Complete — CODE+HIL DONE: handoffs locales desde inputs efectivos y evidencia fresca; discovery/UNKNOWN aislado, `AMBIGUOUS`, foreign, contradicción y recovery no autorizan input. Ack y Continue son single-attempt; Raid Complete conserva base resuelta, freshness y terminal contradictorio. Regresión dirigida 282/282 con 44 frames curados; HIL natural incluyó Previous Rewards y llegó físicamente a Lobby, todo first-attempt y sin taps incorrectos. Cierre integral DONE: fix local en `BattleModeZone.leave` que tolera el origin transitorio post-`SelectQuickMenuLobby` sin abort/retry/segundo tap; HIL natural 1/1 hasta Lobby limpio y full hardware-free 2394/2394 (nuevo autoritativo). WB-2 (D locales) queda diferido. No iniciar scoping/performance en este checkpoint.
- Quick Menu verified-origin handoff — DONE en correctness: el verificador expone action source y señal local de recovery; Rotation R2-C, select_lobby, select_guild y BattleModeZone.leave exigen provenance de apertura. R2-C sigue global: el scope de dos detectores pierde bases foreign que invalidan el token y las degrada a UNKNOWN + menu.quick, estado que con lineage podría permitir retry erróneo. B2 acota sólo el wait final de select_lobby/BattleModeZone.leave con vocabulario resolver-complete 95→77; opener y select_guild conservan global por vocabulario de bases/contradicciones no probado en scopes moderados. No adquirir landmarks bajo el panel para normal path.
- Clean Lobby / B2 — DONE en código: discovery/recovery y postchecks de sesión permanecen globales; CloseFriends, Mailbox, Daily, Black Market, ClosePets, select_lobby, BattleModeZone.leave y R2-B usan scopes nombrados de 77 detectores que preservan las 17 bases y los 57 overlays del catálogo. El landmark positivo `Trading Center` sigue seasonal-risk; scopes menores y snapshot reuse quedan diferidos por evidencia/contrato. Ver [`docs/CLEAN_LOBBY_B2_DECISION.md`](docs/CLEAN_LOBBY_B2_DECISION.md).
- Cierre refactor — DONE: scoping BM/Summon/Daily-progress/MW-eligibility, seed reuse BM/Summon (D_REUSE), return fixes productivos (`c449106`, `d1806d4`, `d61bf20`) y auditorías Daily tab-loop y R2-C (J con tests pin); full hardware-free 2459/2459. Auditoría global final — DONE ([`docs/FINAL_GLOBAL_PERCEPTION_AUDIT.md`](docs/FINAL_GLOBAL_PERCEPTION_AUDIT.md), `REFACTOR_COMPLETE=YES`, 0 K/D-local/BUG). Benchmark post-refactor 28/28 — DONE PASS 76:59 ([`docs/POST_REFACTOR_28_28_BENCHMARK.md`](docs/POST_REFACTOR_28_28_BENCHMARK.md)).

### 5. Estabilizar percepción acotada

Extender de a un flow, asegurar observaciones frescas, recovery y diagnóstico. Detener la expansión si aparecen estados omitidos, costo impredecible o acoplamiento con policy.

### 6. Inventory Relief simple — SELL + COMPOSER DONE

Equipment Sell standalone bulk-only quedó reimplementado desde cero y separado del gameplay: facts OCR por consenso, autorización explícita, grupos Poor–Legendary Equipment/Enhance y Ethereal por tipo, Ethereal+ protegido, un confirm máximo y Item Count decreciente como única postcondición de éxito. HIL autorizado: Epic Equipment `120→114` con una sola venta bulk. El compositor puro preserva el request causal y cierra el orden `caller Equipment Full → Combine una vez → contexto fresco + retry una vez → aún full → Sell explícitamente autorizado una vez → contexto fresco + retry una vez → aún full = fail closed`. No porta chain, planner, thresholds, Karats, scan ni lifecycle experimental.

### 7. Integración por presión de recursos — CRAFT STANDALONE DONE / CALLER ADAPTERS NEXT

Conectar el compositor a un caller sólo después de auditar/adquirir sus rutas físicas de entrada y retorno. El adapter debe aportar su resultado Equipment Full, precondición/facts frescos y un `EquipmentSellRequest` con autorización+candidato explícitos; sin plan, el compositor retorna `SELL_REQUIRED_BUT_NO_AUTHORIZED_CANDIDATE` con cero input destructivo. No añadir thresholds de presión ni loops especulativos.

Craft standalone está CLOSED: entrada desde Equipment Inventory exige ≥1 slot libre fresco, Quick Menu shifted→Craft y retorno Quick Menu directo verificados, recetas Hero visibles sin scroll, cantidades `ONE`/`MAX_AVAILABLE`, guardia premium fail-closed y éxito por decremento exacto de material. No contiene caller adapter ni invoca `EquipmentReliefComposer`.

### 8. Expansión de flows

Agregar capacidades de negocio una por vez, con contrato de entrada/salida, eligibility y postcondiciones. Priorizar casos simples y frecuentes; connection recovery, scheduler y estrategias avanzadas requieren necesidad concreta.

### 9. Tower — hacia el final

Adquirir evidencia propia y construir un vertical slice después de estabilizar los bloques anteriores. Arena y automatización más amplia permanecen posteriores y no están comprometidas.

### 10. Checkpoint V1 — DONE

Cerrados: scoped perception refactor, Quick Menu provenance, Clean Lobby/B2, World Boss correctness, Daily tab-loop audit, Rotation R2-C audit, productive QuickMenu return fixes, D_REUSE, final global perception audit, post-refactor 28/28 benchmark y checkpoint V1 (`04640c2`).

Fuera de V1 (futuro, no blockers): validación runtime/performance de Monster Wave al reactivarse; hub scopes WB/MW (`NEEDS_EVIDENCE`); relief scopes; Lobby<77 / landmark estructural seasonal; carry FlowResult→SessionRunner; carry transversal `_navigate_to_guild`/navigation bool→snapshot; nuevos flows post-V1; storage cleanup pospuesto.

### 11. Post-V1 — Resource Routing / Monster Wave Preparation — PLANNING ONLY

Primera frontera post-V1. El documento de reconstrucción conserva el diseño de partida y los checkpoints implementados; el estado vigente por frente se resume abajo.

Decisiones cerradas: board-first planning (Trading nunca como etapa diagnóstica si el board decide); snapshot descriptivo + deterministic route planner separados de executors; Trading/Craft/Treasure como capacidades atómicas independientes; Inventory Relief transversal con Combine Relief siempre primero y venta sólo si sigue necesario, sin ser propiedad de Treasure/Craft/Trading/MW; Gold Key capacity no observable (board ni Trading), popup Silver→Gold full exige navegación manual a Treasure + retorno causal, y abrir Gold Keys es independiente de Equipment Inventory (sin consumo de relief); Craft sin scroll con precondición de entrada ≥1 slot libre de Equipment Inventory; Crafting Materials preventivo por board + fallback defensivo ante popup; directed known-list scrolling como primitive transversal cuyo único consumer actual es Trading Center; MW standalone/debuggable; stage-ready boundary al final.

Orden de fases recomendado (secuencia, no cadena de dependencias; sólo C depende de B): A recon+observ audit → H/I diseño snapshot/planner → B directed scroll → F transversal relief → C Trading → D Craft → E Treasure → G MW board acquisition → I-impl planner → J MW integration → K standalone/debug → L stage-ready. Primer frente propuesto: primitive directed known-list scroll (offline, bounded, desbloqueante; ver mini-brief en el documento).

Estado frentes post-V1: B directed known-list scroll primitive → DONE (`bot/directed_list_scroll.py`, 35 tests dirigidos, sin consumer integrado, sin HIL). C1 Trading readiness → DONE (semántica + predicados + 5 detectores HIL-calibrados + evaluator incremental verde + 12 tests). C2 materials adapter → DONE (catálogo real 22 filas + profile calibrado + adapter + smokes forward/backward/visible PASS con TARGET_READY y cero taps/trades). C3 row facts → DONE (`bot/trading_row_facts.py`: TradingRowFact + readers have/need + consensus + scope Trading + promoción global mínima, evaluator 0 wrong, full suite verde, cero trades). C4 generic verified trade primitive → DONE (`bot/trading_operation.py` + `bot/trading_panel_profile.py` HIL-calibrado + 50 tests; HIL A PASS, HIL B NO_EFFECT con causa hitbox demostrada, C5 calibración No 2/2 + >> 1/20→6/20 + SUCCESS weapon 265→225 EXACT 1 con tap único). C5 Avatar & Keys primitives → DONE (`bot/trading_keys.py`: operaciones BRONZE_TO_SILVER→`silver_key` / SILVER_TO_GOLD→`gold_key`, readiness C1 exclusiva sin scroll, delegación única a C4 con `OUTPUT_FULL` passthrough, 40 tests; HIL A/B por evidencia previa keys-top, HIL C/D NOT_EXERCISED sin gasto). Prerrequisito C6b Trading navigation → DONE (`bot/trading_runtime.py` + profile/actions: Lobby→Trading directo, General→Avatar & Keys fresco/idempotente, X→Lobby fresco; HIL y smoke productivo PASS, single-attempt, sin scroll/trades). E Treasure Gold Keys → DONE (`bot/treasure_center_semantics.py` + `bot/treasure_center.py` + `bot/treasure_keys.py`: readiness Treasure+Gold positiva sin scroll, request bounded OPEN_ONCE/EXACT/UP_TO/MAX_WITHIN_BUDGET con allowlist exacta {"gold_key"} + targets caller-supplied, currency fresca por apertura con stop-before-premium, postcondición de consumo 354→353, 36 tests; HIL A PASS cero aperturas, HIL B1 popup 1/10 Gold cero Karats, HIL B2 SUCCESS x1 con 1 tap autorizado). C6a Keys promotion policy → DONE (`bot/keys_promotion.py` pura/stateless: Silver→Gold primero cuando Silver tradeable, si no Bronze→Silver, si no NO_MORE_PROMOTIONS; quantity MAX_ALLOWED; re-evaluación con facts frescos tras cada SUCCESS; OUTPUT_FULL Silver→Gold ⇒ GOLD_CAPACITY_BLOCKED con causal pendiente preservada sin Treasure; budget explícito sin loops; 46 tests). E2/E2.2 Treasure runtime + safe fast drain → DONE. C6b orchestration → DONE (`bot/keys_promotion_runtime.py` + `bot/quick_menu_trading.py`: pending causal Silver→Gold, X→Lobby→Treasure, OPEN_ONCE+full drain, Treasure→Quick Menu→Trading directo, facts frescos y un retry; sin capacity estimate, Equipment coupling ni scroll). Craft y Treasure no consumen scroll.

F-Sell standalone → DONE (`equipment_sell_{semantics,reader,policy,operation,runtime}.py`, bulk-only, 284 tests dirigidos, evaluator 12/12, HIL Epic Equipment 120→114). F-composer transversal → DONE offline (`bot/equipment_relief.py`, 25 tests directos; request opaco preservado, contexts secuencialmente frescos, 1 Combine + 1 Sell máximos, candidato explícito obligatorio, sin caller/ruta física nueva). D-Craft standalone → DONE (`craft_{semantics,reader,policy,operation,runtime}.py`, evaluator 13/13, HIL Hero Weapon 325→276, Quick Menu directo). F-caller adapter → **NEXT**, con auditoría/HIL sólo para la ruta concreta no publicada.
E2 Treasure runtime → DONE (2026-09-18): HIL A PASS + B PASS con 1 Gold Key verificado por GT humano (contador cofre 353→352 + result normalizado + Lobby limpio); freshness por timestamp con barrera causal (`observed_at`, `max_fact_age_s=2.0s`) tras `stale_fact` HIL. E2.2 fast drain → DONE (cierre 2026-09-21): HIL productivo Gold Keys 27→0, initial open SUCCESS, frontera Karat fresca en seq 623, cero taps derechos después del latch, premium 33,509→33,509 y Gold currency intacta. `TapThroughAnimation` cerró físicamente el overlay con dos taps en el único target profile-owned `(0.08,0.65)` y dejó Treasure estable por GT humano. C6b CLOSED 2026-09-22: HIL directo Treasure→Quick Menu→Trading PASS con target `(0.332,0.6500)` y `screen.trading` fresco; un recovery máximo, todos los Gold Keys drenados, causal retry una vez y sin Lobby entre Treasure y Trading.

## Criterios permanentes

- Código y tests prevalecen sobre documentación histórica.
- Ningún input desde `UNKNOWN`; todo retry es bounded y state-guarded.
- Perception, resolver, flows, Rotation, executor y ADB conservan sus límites.
- Primero tests dirigidos; una única suite hardware-free completa cuando el cambio lo justifique.
- Hardware es explícito, breve, opt-in y con cleanup.
- No ampliar alcance después de obtener la evidencia o validación buscada.
- No versionar raws, screencaps, artifacts, logs, caches ni configuración local.
