# Post-refactor 28/28 benchmark — 2026-09-16

Analysis-only. No code changed, no suite/evaluator/corpus/HIL run, no commit/push.
Branch `rebuild/stable-baseline` @ `04640c2` (`REFACTOR_COMPLETE=YES`), last productive change `6ba5c9b`.

## 1. Sesión analizada

- Log: `logs/20260916T174330.548797Z_session_39c99ad5.jsonl` — **único archivo/event-stream** de la sesión (arquitectura de log único; sin doble-conteo).
- `run_id = bd5fb21c949c493d94b79256612e4f41` · 6591 eventos · 82 tipos de evento.
- Primer timestamp: `2026-09-16T17:43:30.644511+00:00` (`runtime.started`).
- Último timestamp: `2026-09-16T19:00:29.512738+00:00` (`runtime.closed`, tras `session.completed` + `runtime.completed`).
- **Wall-time derivado de logs: 4618.9 s = 76 min 59 s ≈ 77.0 min** — coincide con el wall-time humano (~1 h 17 min).
- Identificación inequívoca: 28 `session.character.started` + 28 `session.character.completed` + 1 `session.completed`; duración ≈77 min; 0 eventos `monster_wave`; 28 flows `world_boss`; 1 probe de relief sin trabajo (ver §13).

### Runs cercanos separados (no pertenecen a la sesión)

| Log (2026-09-16) | Contenido | Clasificación |
|---|---|---|
| `00:52–02:32Z session_*` (8×: 8/12/1/2/3/3/1/1 chars) | runs parciales pre-sesión | HIL/smoke o runs abortados, excluidos por horario + conteo |
| `04:14–04:19Z session_*` (3×, 1 flow c/u) | smokes single-flow | excluidos |
| `10:49Z / 11:12Z flow_world_boss_*` | 2 tests de WB aislados | excluidos (pre-sesión, 6–7 h antes) |

## 2. Configuración (workload)

- Monster Wave: **DESACTIVADO — 0 eventos** en toda la sesión (el path completo se omite, ni siquiera eligibility; ver §12).
- Reliefs con trabajo real: **0** (1 probe de equipment-combine con `no_relief_available`, ver §13).
- World Boss: 28 flows; 26 batallas completas; 1 `insufficient_sapphires` (char 22); 1 `bag_full` sin batalla (char 27).
- Fallos: 0. Reintentos acotados por diseño: 1 (char 11, Black Market).

## 3. Resultado 28/28 y resumen global

**28/28 COMPLETED, limpio desde logs** (no sólo por resultado final):

| Métrica | Valor |
|---|---|
| wall-time | 4618.9 s (77.0 min) |
| personajes completados | 28/28 |
| flows started/completed | 196/196 (7 × 28) |
| transitions started/completed | 768/768 |
| `runtime_wait.completed` | 1492 (2 con `outcome=timeout`, mismo incidente) |
| `controlled_wait` started/completed | 52/52 |
| failures | 0 |
| retries (`transition.retry`) | 1 |
| recoveries | 0 |
| grace attempts | 1 |
| timeouts (nominal+grace, 1 incidente) | 2 |
| aborted waits | 0 |
| retry_guard_rejected | 0 (sin eventos) |
| unexpected states | 0 (sin eventos) |
| UNKNOWN/AMBIGUOUS relevantes | 0 (sin eventos; polls `contradictory=False` 79/79) |
| relief activations con trabajo | 0 |
| Monster Wave runs | 0 |
| World Boss batallas | 26 (28 flows) |
| warnings | 1 (`insufficient_sapphires`, señal de negocio esperada) |
| errors | 0 |

## 4. Wall-time vs flow-time vs perception-CPU vs game-time

- **Wall**: 4618.9 s.
- **Flow-time** (suma de walls `flow.started→completed`): BM 274.0 + SS 106.3 + Summon 119.1 + Guild 65.1 + WB 2642.2 + Daily 140.8 + Mailbox 272.1 = **3619.6 s** + Rotation 268.0 s = 3887.6 s. Resto (~731 s): precondiciones/normalize entre flows, pre-flow WB (~260 s), postcondiciones y rotación de sesión.
- **Perception CPU** (`perception.analyze_summary`): **2337.8 s** agregados (15 920 analyzes). Es CPU de análisis que **bloquea los polls**: cada poll cuesta ~1 frame (global ~0.7 s, scoped 0.01–0.4 s), así que scoping reduce wall-time de espera además de CPU.
- **Game/wait time**: dominado por batalla WB fija **65.0 s × 26 = 1690 s (36.6 % del wall)** con `poll_count=0` (sleep fijo, cero percepción), más loadings/animaciones/estabilidad (`stable_for`) dentro de cada wait.

## 5. Tiempo por personaje

`index | nombre | wall (s) | nota` (orden de rotación; char 1 sin evento `character_name` en logs):

| # | Nombre | Wall | | # | Nombre | Wall |
|---|---|---|---|---|---|---|
| 1 | n/a | 175.1 | | 15 | Galaxy Lord | 169.5 |
| 2 | Halo Mage | 175.1 | | 16 | Eclair | 165.7 |
| 3 | Flame Striker | 174.6 | | 17 | Dark Valkyrie | 167.6 |
| 4 | Monk | 176.7 | | 18 | Hastati | 164.4 |
| 5 | Elemental Fairy | 178.9 | | 19 | Lina | 168.6 |
| 6 | Ice Warlock | 172.2 | | 20 | Berserker | 169.1 |
| 7 | Noblia | 172.0 | | 21 | Demon Blade | 166.8 |
| 8 | Telumpel | 168.9 | | 22 | Cat Acrobat | **72.7** (WB `insufficient_sapphires`) |
| 9 | Strike Archer | 173.0 | | 23 | Dimension Manipulator | 169.2 |
| 10 | Wandering Master | 169.2 | | 24 | Kaiserin | 169.3 |
| 11 | Shadow Mage | **183.5** (retry BM +9 s) | | 25 | Mystic Wolf Guardian | 168.8 |
| 12 | Blade Dancer | 161.9 (mailbox vacío 6.3 s) | | 26 | Eilla | 169.3 |
| 13 | Blood Demon | 170.3 | | 27 | Rang | **102.2** (WB `bag_full`, sin batalla) |
| 14 | Steam Walker | 166.1 | | 28 | Crimson Assassin | 168.7 |

- min 72.7 · max 183.5 · **mean 164.6 · median 169.2 · p90 ≈176.7 · p95 ≈178.9**.
- De más lento a más rápido: 11, 5, 4, 1, 2, 3, 9, 7, 6, … 12, 27, 22.
- **Outliers claros**: 22 y 27 (rápidos, causas de juego §6); 11 (lento, retry acotado §14). Todo lo demás en ±7 s de la mediana (varianza de juego: slots de compra, mails, loadings).

## 6. Tiempo por flow

`flow | runs | total | mean | median | max | retries | recoveries`:

| Flow | Runs | Total (s) | Mean | Median | Max | Retries |
|---|---|---|---|---|---|---|
| Black Market | 28 | 274.0 | 9.8 | 9.7 | 18.7 (ch11 retry) | 1 |
| Send Stamina | 28 | 106.3 | 3.8 | 3.7 | 4.2 | 0 |
| Summon Pet | 28 | 119.1 | 4.3 | 4.2 | 4.8 | 0 |
| Guild Check-in | 28 | 65.1 | 2.3 | 2.3 | 2.6 | 0 |
| World Boss | 28 | 2642.2 | 94.4 | 99.4 | 104.8 | 0 |
| Daily Quests | 28 | 140.8 | 5.0 | 4.9 | 6.9 (ch24 off-tab) | 0 |
| Mailbox | 28 | 272.1 | 9.7 | 10.0 | 11.3 | 0 |
| Rotation (transversal) | 28 | 268.0 | 9.57 | 9.44 | 11.27 | 0 |

- **Monster Wave no incluido: estuvo desactivado** (0 eventos). Este 28/28 no valida performance de MW.
- Gameplay vs perceptivo por flow: los waits scoped (BM open/slot/purchase, Daily claim/open, Mailbox, SS, Summon, Guild completion) cuestan 8–110 ms/frame; los globales (hubs WB, R2-C, postcondiciones) ~650–730 ms/frame (detalle §8–§9).

## 7. World Boss (detalle)

- Sapphire reads: 28 · `entry_handoff`/`selector_handoff`: 27 · `open_selector`/`select_available`: 27 · `ack_previous_rewards` (`previous_rewards`): 22 (4 batallas sin popup) · `auto_battle`: 26 · `timer_read`: 26 · `continue_after_raid`: 26 · `return_to_battle_mode`: 27 · `world_boss.completed`: 27 · `flow.completed`: 28.
- **Total WB wall: 2642.2 s · mean 94.4 · median 99.4 · max 104.8** (batallas completas 96–105 s).
- **Batalla real: 65.0 s fijos × 26 = 1690 s** (`controlled_wait`, `poll_count=0`, sin percepción) — 36.6 % del wall de sesión, tiempo de juego puro, no regresión.
- **Overhead del bot ≈ 34 s/batalla**: ~10 hub-waits globales (~3 s c/u: `open_selector`, `select_available`, `start`, `continue_after_raid`, `return_to_battle_mode`, `battle_mode.*`, `ack_previous_rewards`) + `completion_poll` (mean 4.1 s, 0.7–7.6) + retornos lobby scoped-77.
- Percepción atribuida a WB ≈ 1169 s (50 % de la CPU perceptiva), incluyendo normalize pre-flow (~200 s); el resto es waits globales de hub (DEFER `NEEDS_EVIDENCE-1`, ver §15 del audit).
- Casos cortos (GAME_EXPECTED): ch22 `insufficient_sapphires` 6.8 s (1 WARNING de negocio); ch27 `bag_full` 35.7 s con probe de equipment-combine `no_relief_available` + `dismiss_bag_full`, sin batalla.
- Reintentos/recoveries WB: 0. Waits largos fuera de batalla: hub-waits al 80–100 % de su timeout 6 s de forma **sistemática** (7 polls × ~0.7 s) — costo de diseño diferido, no anomalía (§14).

## 8. Rotation (detalle, 28 rotaciones)

- Total 268.0 s · mean 9.57 · median 9.44 · max 11.27 (ch7) · min 8.60.
- Por transición: R2-C `open_character_select` (global J) 83.8 / 2.99 / 2.87 / 3.67 · `open_quick_menu` (global G) 43.8 / 1.57 / 1.47 / 2.46 · `confirm_character_selection` (scoped 77) 48.0 / 1.71 / 1.81 / 1.96 · `select_predecessor_character` (scoped 2, post-swipe) 15.0 / 0.54 / 0.58 / 0.73.
- **R2-C global justificado no es hot spot desproporcionado**: ~3 s de ~9.6 s por rotación (~31 %), 1 wait global/char como modela la auditoría; su wall es ~95 % frames globales (~4 × 708 ms).
- Ch7 (+1.8 s): R2-C 3.67 (+0.8 s, un poll global extra) + `open_quick_menu` 1.97 (+0.5 s) — varianza de juego, no bug.

## 9. Perception benchmark integral

Fuente: 1993 eventos `perception.analyze_summary` (0 errores). El logger **no serializa el engine/scope por analyze** (ver `bot/runtime_observer.py:flush_analysis_metrics` — agrega por contexto de operación): la atribución global/scoped exacta es **`not observable`** en logs; se reporta total + bandas de latencia (proxy) + mapping a transiciones reales (nombres de log, §9) + mapping a scopes vía `*_scope_active(detector_count)` y `docs/FINAL_GLOBAL_PERCEPTION_AUDIT.md §2`.

- Total analyzes: **15 920** · total CPU: **2337.8 s** · max/frame 1.49 s · mediana/frame 657.6 ms · p90 730.6 · p95 779.7 · min 7.1 ms.
- Bandas (sin gap 150–400 ms — dos poblaciones limpias):
  - `>400 ms` (global-like 95): 1218 summaries · 3016 analyzes (18.9 %) · **1947.0 s CPU (83.3 %)**.
  - `50–150 ms` (scoped medios: lobby-77 ≈430 ms cae aquí parcialmente; summon-17/navigate-5 ≈60–110 ms): 329 · 2770 · 210.1 s (9.0 %).
  - `<50 ms` (scoped pequeños 2–6 det): 446 · 10 134 (63.7 %) · 180.7 s (7.7 %).
- Correspondencia observada transición→latencia (nombres reales de log): `rotation.open_character_select` 708 ms · preconditions/`open_quick_menu`/hubs WB 675–730 ms · `battle_mode.select_lobby`/`precondition.select_lobby`/`black_market.close`/`rotation.confirm_character_selection` 415–445 ms (lobby-77) · `black_market.open/select_slot/accept_purchase` 64–69 ms · daily 27–39 ms · mailbox 24–33 ms · send_stamina 8–35 ms · `precondition.open_pets` 14 ms · rotation selection 8 ms.
- `accept_purchase` (ch11): 109 summaries/1559 analyzes a 66 ms — el retry añade polls baratos, no CPU global.

## 10. Top hot spots

### Por CPU acumulado (`grupo | summaries | analyzes | CPU | % percepción`)

1. WB hub waits directos bajo op de flow (eligibility/entry/ack, mixtos) | 248 | 899 | 267.3 | 11.4 %
2. `<observe>` `world_boss/world_boss` (postcondiciones/entry globales) | 194 | 251 | 157.5 | 6.7 %
3. Mailbox waits (scoped) | 193 | 4032 | 134.4 | 5.7 %
4. `world_boss.start` (global) | 28 | 189 | 132.9 | 5.7 %
5. `black_market.accept_purchase` (scoped 6) | 109 | 1559 | 102.4 | 4.4 %
6. `<observe>` `guild_check_in` | 56 | 112 | 79.8 | 3.4 %
7. `rotation.open_character_select` R2-C (global J) | 28 | 112 | 79.3 | 3.4 %
8. `<observe>` `summon_pet_daily` | 28 | 112 | 79.0 | 3.4 %
9. `world_boss.continue_after_raid` (global) | 26 | 112 | 75.5 | 3.2 %
10. Summon `pets_manage_navigate` (scoped 5) | 84 | 634 | 68.9 | 2.9 %

Lectura: **caro por frame** = hubs WB + R2-C + `<observe>` globales (~0.7 s/frame, pocos frames); **barato pero frecuente** = mailbox/accept_purchase/selection (miles de frames de 8–65 ms); **caro por gameplay** = batalla 65 s (cero percepción).

### Por wall del wait

Hubs WB 2.5–5 s c/u (~10 por batalla) · R2-C ~3 s · lobby-77 ~1.5–2 s · BM/Daily/Mailbox/SS/Summon/Guild 2–13 s por flow total (múltiples waits scoped baratos + juego).

## 11. Global analyzes restantes vs auditoría

Modelo esperado (§11 del audit, en waits): ~9 entry + ~11–13 postcondición + zona + rotation entry + R2-C + Daily tab-loop si off-tab + WB polling + 0 retry.

- `<observe>` flow-level (single `observe()` globales ~700 ms): 473 summaries ≈ **16.9/char**, compuesto por postcondiciones SessionRunner + entry probes + fact reads — consistente con 9 + 11–13 en waits (la instrumentación cuenta **frames**, y cada wait global cuesta ~2–4 frames: 3016 analyzes globales / ~30 waits globales-char ≈ 3.6 frames/wait).
- Sitios globales dominantes reales: hubs WB (~10/char, DEFER), postcondiciones por flow (~7–9/char, G), precondiciones/normalize (`open_quick_menu`, `select_guild`, `select_lobby`-previos), R2-C (J), entry WB.
- Daily tab-loop global: ejercido **2×** (chars 23, 24, eventos `select_tab`/`tab_activated`) — J confirmado en datos.
- Retry/recovery globals: **0 en happy path** (único retry fue scoped BM) — coincide con el modelo.
- Diferencia principal: el audit cuenta waits; el log mide frames (×~3.6 en globales, ×~10–30 en scoped por `stable_for`/polling). Sin discrepancia de modelo.

## 12. Seed reuse — `not observable` en logs

- **0 eventos** con `seed` en el JSON de sesión: hits/misses/fallbacks **no son derivables con certeza** — no se infiere.
- Indicios (no evidencia): flows BM/Daily/Mailbox/SS/Guild/Summon sin waits iniciales globales extra; walls estables y bajos.
- **Summon seed de `6ba5c9b`**: el flow tiene `run_with_initial` en código, pero el log conserva un `<observe>` global-like de 4 analyzes/char indistinguible de postcondición — **ejercicio no demostrable**. No se declara validado.
- Precondiciones sí visibles: `precondition.pets_manage_navigate_scope_active` 28× + `precondition.lobby_return_scope_active` (WB) 28×.

## 13. Daily progress y MW eligibility

- **Daily progress (95→4)**: 0 eventos `daily_quests.progress_reward_*` en 28 chars (sólo `claim_all_executed/completed` 28/28) → **ruta no ejercida** (ningún char tenía progress claimable). Cambio **no validado** por esta sesión.
- **MW eligibility (95→5)**: 0 eventos `monster_wave.*` (ni siquiera `eligibility_scope_active`; sólo se declaró `world_boss.eligibility_scope_active` det=5) → con MW desactivado **el path completo se omite**. Ahorro **no atribuible**; **este 28/28 NO valida performance de Monster Wave activity**.

## 14. Reliefs

- Socket: **0** · Equipment con trabajo: **0** · Pet-space: **0**.
- Único evento: probe `equipment_combine_relief` en ch27 (3 transiciones `success_first_attempt`, `transmute/fuse/ethereal skipped`, `finished=no_relief_available`, ~7.2 s) dentro del path `bag_full` de WB — **check sin trabajo**, invisible como "relief" para el humano. Consistente con "0 relief branches observadas" si rama = trabajo real; se reporta la discrepancia nominal.
- `mailbox.claims_leftover` 2× (chars 12 Blade Dancer, 21 Demon Blade) + `claim_all_skipped` 1× — INFO de negocio esperado (mailbox vacío), no relief.
- Esta sesión, al no tener reliefs reales, es **naturalmente más corta** que una con inventarios sucios — caveat para comparaciones (§16).

## 15. Pausas sospechosamente largas

| Timestamp/ch | Flow | Transition/wait | Duración | Típico | Causa | ¿Sospechoso? |
|---|---|---|---|---|---|---|
| 18:12:40–48 ch11 | BM | `accept_purchase` nominal 5 s + grace 2 s + retry att.2 `success_after_retry` | +9 s vs mediana | ~1 s | confirmación de compra lenta (juego) | No — RETRY acotado por diseño, harmless |
| 26× chars | WB | hub-waits globales al 80–107 % del timeout 6 s (7 polls × 0.7 s) | ~5 s c/u | ~5 s (sistemático) | frames globales + `stable_for` | No anomalía; PERCEPTION_COST diferido (NEEDS_EVIDENCE-1) |
| ch23/24 18:47/18:49 | Daily | tab-loop off-tab (`select_tab`) | +1.6–2 s | on-tab 4.9 s | J-justificado | No — GAME_EXPECTED |
| ch28 Daily | Daily | open/claim | 6.5 vs 4.9 med | 4.9 | varianza loading | No |
| ch7 Rotation | Rotation | R2-C 3.67 + QM 1.97 | 11.27 vs 9.44 | 9.44 | un poll global extra | No |
| ch4/8/25 BM 11–13 s | BM | slots/purchases | — | 9.7 | nº slots comprables | No — GAME variance |

- **Ninguna transición con max > 2× mediana**; 0 waits abortados; 0 near-miss fuera de los hub-waits sistemáticos. No hay bug oculto en outliers.

## 16. Comparación con el 28/28 anterior

Candidatas: `20260908 session_6c70f8d2` (97.1 min, 28/28 COMPLETED, misma cartelera 7×28, MW off) y `20260909 session_021f3d0c` (94.1 min, pero **193 flows**: WB sólo 25 — workload distinto, **excluida** como baseline). Ninguna es literalmente "~85 min" (memoria humana aproximada); la 0908 es la más cercana en workload pero **difiere materialmente** (reliefs con trabajo real, 14 retries/37 timeouts vs 1/1, 23 vs 26 batallas). Comparación **descriptiva, no causal**.

`métrica | old 0908 | new 0916 | delta | %`:

| Métrica | Old | New | Δ | Δ% |
|---|---|---|---|---|
| wall-time | 97.1 min | 77.0 min | −20.1 min | −20.7 % |
| perception CPU | 4026.8 s | 2337.8 s | −1689 s | −42.0 % |
| total analyzes | 5705 | 15 920 | +10 215 | +179 % (frames scoped baratos) |
| global-like analyzes (>400 ms) | 5705 (100 %) | 3016 (18.9 %) | −2689 | −47.1 % |
| global-like CPU | 4026.8 s | 1947.0 s | −2079.8 s | −51.7 % |
| per-char mean/median | 207.9 / 213.0 | 164.6 / 169.2 | −43.3 / −43.8 | −20.8 / −20.6 % |
| Rotation mean | 13.53 | 9.57 | −3.96 | −29.3 % |
| BM / Daily / Guild / Mailbox / SS / Summon (mean) | 21.2/9.1/4.3/17.9/8.7/9.2 | 9.8/5.0/2.3/9.7/3.8/4.3 | ≈−45–56 % c/u | — |
| WB mean/median (overhead, batalla 65 s idéntica) | 86.9 / 96.2 | 94.4 / 99.4 | +7.5/+3.2 | +8.6/+3.3 % (DEFER intacto + workload) |
| retries / timeouts+grace | 14 / 37 | 1 / 1 | −13 / −36 | — |
| reliefs con trabajo | 8 ejecuciones (socket enhance ×4 entre ellas) | 0 (1 probe no-op) | −8 | — |
| WB batallas | 23 | 26 | +3 | — |

Lectura: el perfil perceptivo cambió exactamente como predice el refactor (100 % frames globales → 19 %; CPU −42 %). Los walls de flows scoped se redujeron ~a la mitad (cada poll bloqueaba ~0.7 s y ahora 0.01–0.4 s). WB no mejora (hubs DEFER + batalla fija), como esperaba el modelo.

## 17. Wall-time improvement — descomposición honesta

Humano: ~85 → ~77 min (~8 min, ~9.4 %). Logs comparables: 97.1 → 77.0 (−20.1 min, −20.7 %).

- **Ahorro demostrable de percepción**: CPU −1689 s (−42 %), globales −2689 analyzes (−47 %); walls de flows scoped −45–56 %. Contribuye materialmente, pero **el número exacto en wall no es aislable** (polls × juego entrelazados).
- **Diferencias de workload** (cuantificadas): 8 reliefs con trabajo → 0; retries 14 → 1; timeouts 37 → 1; batallas WB 23 → 26 (+3×~100 s ≈ +5 min en contra); mailbox más vacíos (17.9 → 9.7 s/char incluye contenido).
- **Variación natural**: loadings/red/animaciones (p. ej. R2-C ±0.8 s, BM 6.4–13.1 s por slots).
- **Unknown**: resto sin atribuir — no se fabrica número.

**El ~9.4 % (ni el −20.7 % log-a-log) NO se atribuye entero al refactor.**

## 18. Correctness post-refactor

- 1 WARNING de negocio (`insufficient_sapphires` ch22) — expected.
- 2 timeouts → 1 retry acotado → `success_after_retry` (ch11) — el contrato funciona; harmless.
- 79/79 polls WB `contradictory=False`; 26 detecciones terminales de raid correctas; 0 `UNKNOWN`/`AMBIGUOUS`/stale/rejected/duplicados en eventos (granularidad: sólo taps de Guild se loguean como taps — input de bajo nivel no auditable aquí).
- `mailbox.claims_leftover`/`claim_all_skipped`, `transmute/fuse skipped`, `auto_battle_inconclusive` (sin input enviado) — paths esperados, fail-closed.
- **Ningún correctness concern. Clasificación: todo harmless o expected.**

## 19. Oportunidades restantes (sólo datos de esta sesión)

- **HIGH VALUE: ninguna demostrada.** Los costos grandes son batalla fija (juego), hubs WB (diferidos con motivo) y R2-C/tab-loop (justificados con tests).
- **MEDIUM**: waits de lobby-return scoped-77 (~177 s CPU a ~430 ms/frame: `battle_mode.select_lobby`, `precondition.select_lobby`, `confirm_character_selection`, `black_market.close`) — el camino Lobby<77 ya está diferido (necesita landmarks + evidencia). Hubs WB (~600 s CPU global; un scope resolver-complete ahorraría ~20 % ≈ ~2 min/sesión) — diferido NEEDS_EVIDENCE-1.
- **LOW / NOT WORTH IT**: relief scopes (1 probe no-op/28 chars) · `accept_purchase` (scoped, juego) · off-tab Daily (2×, J) · `completion_poll` 4.1 s (S, correcto).
- **DEFERRED BY DESIGN** (no reabrir): WB/MW hub scopes · relief scopes · carry FlowResult/SessionRunner · Lobby<77 · `TapThroughAnimation` · `D_TRANSVERSAL-1/2`.

## 20. Decisión post-benchmark

- **A. `POST_REFACTOR_28_28 = PASS`** — 28/28 COMPLETED, 0 fallos, 1 retry acotado por diseño, 0 reliefs con trabajo, 0 anomalías humanas confirmadas en logs.
- **B. `PERFORMANCE_REGRESSION = NO`** — percepción −42 % CPU / −47 % analyzes globales; flows scoped −45–56 % wall; WB plano dentro de varianza (DEFER intacto por diseño).
- **C. `NEW_CORRECTNESS_BUG = NO`**.
- **D. `HIGH_VALUE_OPTIMIZATION_REMAINING = NO`** — resto medium/low/deferred con motivo vigente.
- **E. `READY_FOR_V1_CHECKPOINT = YES`** (recomendación basada en evidencia; sin commit ni docs adicionales en esta tarea).

## 21. Git / código (read-only verificado)

- Permitido: sólo este reporte (`docs/POST_REFACTOR_28_28_BENCHMARK.md`).
- No se tocó `bot/`, tests, suite, evaluator, corpus, HIL, ni se hizo commit/merge/push. Preexistentes intactos (ver entrega final).
