# Checkpoint Stability + Performance — 2026-10-07

Baseline: `b673177db3ac58fb7619c929ca1a85395f36f904`;
branch `rebuild/stable-baseline`. Alcance: Equipment Sell cromático y binding
causal, fixes full-roster, cronología de Capture y performance de Stages.

## Aceptación acumulativa

**28 unique stable character IDs completed across multiple runs.**
Inicio: 2 COMPLETE + 1 PARTIAL + 25 UNSEEN; los 26 pendientes alcanzaron
completion sin reiniciar cobertura ni editar operational facts. Final: 28 COMPLETE.
Blade Dancer terminó rutina completa y Rotation en R6. No es una única Session
verde 28/28. Stable ID gobierna el ledger; retries no añaden personajes.

| Character / stable ID | Status | Run(s) / session(s) | Ads encountered | Failures / retries |
|---|---|---|---:|---|
| Burst Breaker / `burst_breaker` | COMPLETE | Manual previo / USER_GT | 0 | 0 FAILED / 0 retry |
| Berserker / `berserker` | COMPLETE | R5 | 2 | 0 FAILED / 0 retry |
| Demon Blade / `demon_blade` | COMPLETE | R5 | 2 | 0 FAILED / 0 retry |
| Kaiserin / `kaiserin` | COMPLETE | Manual previo / USER_GT | 0 | 0 FAILED / 0 retry |
| Noblia / `noblia` | COMPLETE | R3 | 2 | 0 FAILED / 0 retry |
| Ice Warlock / `ice_warlock` | COMPLETE | R5 | 2 | 0 FAILED / 0 retry |
| Crimson Assassin / `crimson_assassin` | COMPLETE | R3 | 2 | 0 FAILED / 0 retry |
| Rang / `rang` | COMPLETE | R5 | 2 | 0 FAILED / 0 retry |
| Telumpel / `telumpel` | COMPLETE | R5 | 2 | 0 FAILED / 0 retry |
| Halo Mage / `halo_mage` | COMPLETE | R3 | 2 | 0 FAILED / 0 retry |
| Strike Archer / `strike_archer` | COMPLETE | R5 | 2 | 0 FAILED / 0 retry |
| Galaxy Lord / `galaxy_lord` | COMPLETE | R5 | 2 | 0 FAILED / 0 retry |
| Wandering Master / `wandering_master` | COMPLETE | R4, R5 | 2 | 1 FAILED / 1 retry |
| Steam Walker / `steam_walker` | COMPLETE | R3, R4 | 2 | 1 FAILED / 1 retry |
| Mystic Wolf Guardian / `mystic_wolf_guardian` | COMPLETE | R3 | 2 | 0 FAILED / 0 retry |
| Blood Demon / `blood_demon` | COMPLETE | R5 | 2 | 0 FAILED / 0 retry |
| Eclair / `eclair` | COMPLETE | R4 | 2 | 0 FAILED / 0 retry |
| Dark Valkyrie / `dark_valkyrie` | COMPLETE | R5 | 2 | 0 FAILED / 0 retry |
| Elemental Fairy / `elemental_fairy` | COMPLETE | R3 | 2 | 0 FAILED / 0 retry |
| Hastati / `hastati` | COMPLETE | R5 | 2 | 0 FAILED / 0 retry |
| Flame Striker / `flame_striker` | COMPLETE | R3 | 2 | 0 FAILED / 0 retry |
| Eilla / `eilla` | COMPLETE | R5 | 2 | 0 FAILED / 0 retry |
| Lina / `lina` | COMPLETE | R5 | 2 | 0 FAILED / 0 retry |
| Cat Acrobat / `cat_acrobat` | COMPLETE | R3 | 2 | 0 FAILED / 0 retry |
| Shadow Mage / `shadow_mage` | COMPLETE | R5 | 2 | 0 FAILED / 0 retry |
| Monk / `monk` | COMPLETE | R3 | 2 | 0 FAILED / 0 retry |
| Blade Dancer / `blade_dancer` | COMPLETE | R5, R6 | 2 | 1 FAILED / 1 retry |
| Dimension Manipulator / `dimension_manipulator` | COMPLETE | R1, R3 | 1 | 1 FAILED / 1 retry |

Ads encountered cuenta sólo eventos de esta campaña: **51 Ads returned**. Los dos personajes iniciales ya tenían 0; Dimension Manipulator conservaba 1. Los cinco consumos previos al inicio quedan fuera de esta columna. Session exacta por R está en la tabla de runs y en el ledger.

## Runs y fronteras de versión

| Run | Session | Target | Nuevos COMPLETE | Resultado | Wall seconds |
|---|---|---:|---:|---|---:|
| R1 | `5684f1f0c9a6450090d0d5ea46cb0321` | 26 | 0 | FAILED | 158.2 |
| R2 | preflight | 26 | 0 | STOPPED | 9.5 |
| R3 | `03f0908530b042f3a960c548706f189d` | 26 | 9 | FAILED | 5951.5 |
| R4 | `0ae133c44da64a199f0ab6f807138369` | 17 | 2 | FAILED | 1156.1 |
| R5 | `5a5b36ed69d947aeb6f50e46c933b226` | 15 | 14 | FAILED | 9063.9 |
| R6 | `92fa6a74922b41719bb898bde0f072cf` | 1 | 1 | COMPLETED | 459.2 |

Cada fix inició runtime nuevo: la evidencia previa sigue perteneciendo a su
versión. Wall-clock incluye Ads/batallas/red y no es benchmark de compute.
R2 fue preflight desde Stages, sin inputs productivos; se reutilizó la salida
existente. La campaña ejerció el worktree local con cambios independientes;
la validación portable del INDEX comprueba el subconjunto de este checkpoint.

## First divergences y fixes

| Character | Primera divergencia / causa | Fix / validación |
|---|---|---|
| Dimension Manipulator, R1 | Wrapper de instrumentación no aceptaba `claim_only`/kwargs | Harness temporal conserva args/kwargs, tuples y exceptions; replay equivalente. CAMPAIGN_ONLY ignorado, sin cambio productivo |
| Steam Walker, R3 | Nuevo Socket Full fresco rechazado por el bound después de Enhance EFFECT | Yes → relief normal; exactamente un segundo relief si anterior RELIEVED y blocker fresco. Tercero/no effect paran; regresiones directas, smoke y completion R4 |
| Wandering Master, R4 | SKIP volvió a NEEDS durante relief; pass suponía ACTIVE/MAX anterior | NEEDS/READY coherente fresco reutiliza preparación normal, con MAX/Start guards intactos. NEEDS→Fill→READY→Activate→MAX→board live; completion R5 |
| Blade Dancer, R5 | Config correcto pero stale, native 7.36/11.32 s y backlog; PTS anterior podía publicarse después de native nuevo | Carrera reproducida; `_publish` rechaza timestamps anteriores bajo frame lock. Tests, native fresco/cleanup y full completion R6 |

Un freeze de PC es compatible con Blade Dancer, pero **NO OS root cause proven**.
La carrera de publicación es la causa reproducida corregida; no se afirma curar
Windows stalls. Sin relabel timestamps, gate ampliado ni blind retry: el gate
de 2 s evitó input unsafe. R5 retornó la segunda Ad antes de verificar Sapphire;
DB conservó 1. R6 ejecutó MW/reliefs y Stamina 64→314, y Video0 acreditó Ads0
naturalmente, sin otra Ad ni manipulación DB. No describir retry como sin consumos.

## Equipment Sell

Tier authority = title color: Poor white, Normal green, Rare blue, Epic
violet/magenta, Legendary orange; Ethereal/+ red family + marcador separado.
UNKNOWN/ambiguous → no sell. Nombre seleccionado libre irrelevante para
tier/continuity; subtype conserva OCR donde el contrato lo requiere. Popup scope,
Item Count y Bulk group mantienen readers propios.

Binding: verified detail → Sell → popup fresco posterior al tap, sin input
intermedio y con Bulk group compatible; no igualdad OCR de nombres.
Smoke: Legendary Laoku's Destructive Gear / Helmet naranja, selected-name OCR0;
popup OCR `Laoku's Desructive Gear`; count **135→134**, decrement1, un Sell intent,
un Bulk confirm, SUCCESS. Campaña: **72 Bulk SUCCESS, 72 con exactamente una
confirmación** (R1=1/R3=33/R4=9/R5=25/R6=4); no equivale a 72 items/IDs únicos.

Referencia offline independiente: tier median29.74→1.24 ms, p9533.42→1.34;
detail median58.39→32.87 ms, p9565.50→35.54; OCR2→1/sample. Live smoke sólo
contexto: frame→tier≈146 ms median, frame→detail≈225 ms, processing≈86 ms;
Sell fresh revalidation299 ms, popup→confirm609 ms. Sin atribución retroactiva
de mejora end-to-end live.

## Optimizaciones adoptadas

| Owner / comparación | Before | After | Semántica / aceptación |
|---|---|---|---|
| Stages handoff, misma cadena A→B, n4 por variante | median9.420 s; native16; reads64; detector calls1636; OCR0 | median4.957 s (−47.4%); native1; reads153; detectors3373; OCR0 | Stream post-input ≤150 ms/8 polls, fallback nativo y gate2s intactos; ahorro de adquisición/latencia, no menor compute total |
| Stages scoped perception, mismos pixels n30 | 81 detectors; median375.46/p95403.53 ms | 4 detectors; median46.58/p9549.52 ms (−87.6% compute) | Sólo Stages ya verificado; familia/modal blockers preservados. Lobby origin/entry/completion full |

Scope: 0 capturas live y 0 OCR por sample, misma fixture; wrappers con offset
de adquisición50 ms: age median425→97/p95456→112 ms. Cadena A/B: 0 age rejects
medidos y 0 input retries, gate2s intacto. Replay original13 equivalentes (12
curados portables +1 frame live ignorado), 30 pares offline, 12 cadenas live;
versión productiva final D: 2 cadenas, native1, reads75, median5.345 s.
Results→Config→Normal scoped return previo es dependencia directa preservada;
la campaña no se atribuye su creación. Thresholds y pixels no cambian.

## Candidatos rechazados / residual

| Candidato | Evidencia / decisión |
|---|---|
| Lobby→Stages scope | Prototype C timeout6 s, permaneció Lobby tras Open inefectivo; failure `69f35dd9` preservado. NO adoptado, entry/origin full. Comparaciones posteriores mismo idle1 s fuera del intervalo |
| Equipment exact-ROI cache | Pixel variation subtype44.7%, popup identity24.7%, groups14.1/22.2/18.8%, count61.4%. Sin beneficio comparable demostrado; sin cache approximate/fuzzy/global |
| ReliefCoordinator | Delegación≈1 µs; no hotspot relevante, sin refactor |
| Trading Keys consensus | n12; 2 samples×2 OCR; reader p5062.1/p9572.5 ms, bookkeeping≈0.1 ms; sin threshold/confidence/swipe changes |
| Equipment unreadable-count Page OCR | Potencial≈2 s total, sin after comparable ni beneficio significativo validado; no adoptado |

Trading confirm: n69 consumer-entry age p50≈626/p90≈1531/p95≈1593/max≈1688 ms,
gate2s. **Measured performance candidate, non-blocking; NO patch adopted**.
Mapa R5: Gold engine n3756 processing p50406/p95609 ms; resolved n3856 age
p50500/p951625/max29888 ms. 155 observations produced >2s: 48 stale-by-computation,
107 ya viejas al empezar; no equivale a 155 consumers/rejects. WB n42
processing p50453/p95500 ms, age p50550/p95615 ms. Detail n114 processing
p5031/p9547 ms; popup n67 p50329/p95485 ms. Instrumentación incompleta por owner:
conteos de freshness rejects/retries no disponibles no se declaran cero.

Ads live breadth debt **CLOSED**; 51 Ads returned durante campaña, sin Ads FAILED.
Ads/battles/animaciones no son compute hotspots por duración. Character State
informational rejects no fatales: Elemental Fairy Lapiz56,986 confidence.91767;
Shadow Mage Dark71 .92492. Gate.95 preservado; no facts dudosos acreditados.

## Validación y separación del checkpoint

Tests directos protegen binding/color, recurrencia, expiry, chronology y handoff;
replays portables comprueban capas/resolución equivalentes del scope sobre pixels
curados. Cierre: selección consolidada de worktree y selección causal portable desde
export aislado del INDEX, con dependencias históricas faltantes separadas.

PRODUCTIVE: owners causalmente afectados y assets runtime. PERMANENT_TOOL:
adaptaciones del evaluator Sell y del harness HIL (guard humano de nombre exacto
adicional separado, sin OCR de nombre productivo), tests y crops curados pequeños.
CAMPAIGN_ONLY: wrappers/loggers/benchmarks temporales; ARTIFACT: ledger, telemetry,
logs/capturas grandes. Estos últimos permanecen ignorados.

Fuera del commit: Summon Pet/Registry, payment-wrap en reader, Ads inset,
MW readiness (fact_reader/monster_wave_flow/perception/registry), sus tests/fixtures,
scripts locales y eliminación documental histórica. CONTEXT se stagea por sección.
No runtime DB/routines/GUI preferences/raw artifacts ni Arena/Open Pets.

**READY FOR ARENA DESIGN/IMPLEMENTATION** tras cierre verde; no inicia ese frente.

## Resultados consolidados del cierre

| Ejecución | Passed | Failed | Skipped | Deselected |
|---|---:|---:|---:|---:|
| Worktree, selección consolidada48 archivos | 1155 | 0 | 0 | 3 |
| Primer INDEX, misma selección (diagnóstico preservado) | 1126 | 17 | 12 | 3 |
| INDEX portable, todos los tests causales incluidos | 1126 | 0 | 12 | 20 |

No sumar suites solapadas. Tres deselections iniciales: dos native Combine y un
native Points reward requieren artifacts históricos. Los 17 fallos iniciales del
INDEX son exclusivamente imágenes ausentes bajo screencaps ignorados: cuatro
casos Equipment Inventory Full/Combine y trece MW board. Sus tests/readers no
cambian en este diff; todos pasaron en worktree. Se excluyeron sólo esos casos
del INDEX portable. Doce skips existentes son corpus históricos Socket ausentes.
Sin cambio de contratos ajenos para fabricar una suite global verde.

Todos los assets/fixtures nuevos y imports de owners causales se resolvieron
desde INDEX aislado, sin AGENT_LOCAL, DB, routines, artifacts ni untracked ajenos.
Los12 replays portables de equivalencia Stages están incluidos en ambas suites;
el replay13 de campaña conserva su frame live ignorado como evidencia anterior.
Tras tests sólo se completaron docs, sin invalidación de código/percepción.
Auditoría semántica y `git diff --cached --check`/`git diff --check` verdes;
23 paths independientes conservados byte por byte y dos archivos mixtos stageados
por hunk. Invocaciones completas, JUnit y diagnóstico local se preservan ignorados
en `artifacts/full_roster_checkpoint_20261007/`.

Selección exacta worktree (Temp/JUnit apuntaron a un directorio workspace nuevo):

```text
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_equipment_title_color.py tests/test_equipment_selected_panel.py tests/test_equipment_sell_origin.py tests/test_equipment_sell_runtime.py tests/test_equipment_sell_capability.py tests/test_equipment_sell_hil_approval.py tests/test_equipment_low_tiers_live_replay.py tests/test_equipment_name_wrap_replay.py tests/test_equipment_coin_wrap_replay.py tests/test_equipment_inventory_relief.py tests/test_equipment_relief.py tests/test_equipment_combine_relief.py tests/test_equipment_inventory_full_perception.py tests/test_equipment_block_relief.py tests/test_world_boss_equipment_sell.py tests/test_socket_inventory_relief.py tests/test_socket_inventory_relief_perception.py tests/test_socket_inventory_full_perception.py tests/test_socket_animation_scope.py tests/test_socket_animation_live_replay.py tests/test_monster_wave.py tests/test_monster_wave_skip_expiry.py tests/test_monster_wave_entry.py tests/test_monster_wave_productive.py tests/test_monster_wave_standalone.py tests/test_monster_wave_integration.py tests/test_monster_wave_resource_route.py tests/test_monster_wave_board.py tests/test_monster_wave_points_reward.py tests/test_mw_failed_session_replay.py tests/test_productive_monster_wave_session_binding.py tests/test_stages_daily.py tests/test_stages_navigation.py tests/test_stages_native_wait.py tests/test_stages_claim_loop.py tests/test_stages_episode_replay.py tests/test_stages_start_replay.py tests/test_stages_no_ads_replay.py tests/test_stages_results_return.py tests/test_stages_socket_retry.py tests/test_stages_wait_performance.py tests/test_stages_scope_replay.py tests/test_capture.py tests/test_capture_native_chronology.py tests/test_runtime_observer.py tests/test_session.py tests/test_productive_runtime.py tests/test_smoke_session_composition.py -k "not test_native_ethereal_result_veil_and_clean_panel and not test_native_fuse_result_resolves_tappable_without_lowering_confidence and not test_native_points_title_and_post_ack_clear_are_distinct"
```

INDEX portable usa los mismos48 archivos, con esta expresión `-k` adicional
a las tres exclusiones iniciales:

```text
not test_all_red_board_skips_every_ocr_call_and_keeps_consensus and not test_all_three_effects_emit_one_shared_tappable_activity and not test_consensus_rejects_changed_row_stale_and_contradictory_samples and not test_curated_representatives_resolve_the_confirmed_combine_states and not test_current_human_confirmed_board_exact_values_and_consensus and not test_equipment_full_popup_is_global_over_the_only_confirmed_caller and not test_existing_monster_wave_corpus_context_gate and not test_individual_red_shortcuts_skip_exactly_one_ocr_call and not test_low_confidence_row_still_rejects_sample and not test_positional_indicators_gate_independent_statuses_and_postconditions and not test_red_measure_separates_acquired_rows_and_ignores_nearby_red_ui and not test_snapshot_rejects_foreign_or_prior_board_fact and not test_uncertain_measure_falls_back_to_original_ocr and not test_weapon_red_keeps_exact_ocr_when_hero_is_normal
```
