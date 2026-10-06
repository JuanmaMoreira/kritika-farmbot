# Checkpoint causal Reliefs / MW / Trading — 2026-10-06

Parent `d97e899b9fac3fbc26583d595b21abd4267b0ce9`, branch `rebuild/stable-baseline`.
Un único commit: `refactor: centralize relief policies and harden farming runtime`.
Scope exclusivo: Relief architecture refactor, MW freshness + auditoría MAX,
Trading Keys OCR post-confirm y reconciliación causal Ads. Sin Open Pets, otro28/28
ni consumo del trade restante.

## Contrato preservado

Reliefs are routine-level transversal policies. Consumers are not part of the policy contract.
`ReliefPolicy` / `ReliefCoordinator` instala configuración compartida durante la rutina
y restaura contexto en finally. Callers detectan presión/block y solicitan relief;
owners existentes conservan navegación, fresh evidence, effects verified,
cancellation/bounds y prohibición de retry económico ciego.

Socket: Enhance All y Sell incompatible opals independientes, cuatro combinaciones.
Equipment: Combine-first sin configuración; Sell allowlist con labels inequívocos
Sell Ethereal, Enhance propio y Ethereal+ protegido. Craft: Weapon/Armor/Accessories
independientes, las tres migradas habilitadas para preservar runtime previo.
Treasure: Gold Keys OPEN_ONCE/drain existente; objeto de schema extensible,
Platinum rechazado hasta operación/GT, sin checkbox falso ni gameplay nuevo.
GUI: Step Settings / Routine Settings / Reliefs / Application; eligibility WB por
occurrence, reliefs en rutina; Light/Dark, scroll reducido y persistence cubiertos.
JSON v2: Load read-only, backup anterior a escritura, original/archive conservados,
Save/reopen, corrupt config deniega permisos y contradicciones v1 intersectan con
warning; nunca permiso arbitrariamente más amplio.

## MW

Run `ff4b8797565f445695ef2cad0c2987ea`, session
`c385af509b7c4b2ba214f169e8af3b7f`, Burst Breaker, Gold step3,
final_investment attempt2. BASE/board correctos; OCR/perception agotó freshness:
edad2.422s >2s → `mw_board_consensus_unavailable`, sin fallo de navegación.
Memoización A1 de CV puro por ROI grayscale byte-identical; batch nuevo con
sequence/timestamp nuevos, specialized detectors siempre ejecutados.
Replay real old FAILED → continuation; smoke previo board-open gap.297s,
edad final.875s, cinco filas concordantes,0 inputs. Sin CLEAR live nuevo.

Auditoría obligatoria: eventos298–301 y840–843 ejecutaron dos selecciones reales
de MAX, cada una con los dos taps de la operación GT. No son dos observaciones.
Primera divergencia: preparación incondicional de MAX en el segundo investment.
Fix local conserva MAX en entrada fresca seleccionada; readiness incompleta con
MAX presente falla sin retap. Regresión: dos preparaciones independientes,
tres passes, una selección; selected-MAX sin controles nunca autoriza retap.
Evidencia/limitación de telemetría en [informe MW](MW_FAILED_SESSION_86ADECD4.md).

## Trading

Run `5c599d7e4c5a406394d3c18c46b07fb7`, session
`a94ac2e7e19c47389bacda3db00ecc61`, Ice Warlock17/19 de continuación manual,
Basic Gold Farming step3 occurrence1, MW final_investment attempt2→keys_promotion.
FAILED2026-10-06 15:11:17 ART, Silver→Gold post-confirm, `after_fact_unreadable`.
215/10 +1/20 → un >> → MAX fresco coste200/cantidad20/20 → un confirm →
Silver físico15/10 → OCR15/10J confidence.88277 → consenso de efecto indisponible.
Caso C: >> era correcto, sin popup inesperado. Fix: glyphs alineados a línea numérica,
decoración fuera de línea excluida; ROI/parser estricto/.90/consenso/identity/quantity
y confirm único conservados. 15/10+1/20 omite MAX;215/10 usa exactamente uno.
209 tests dirigidos previos preservados como procedencia, sin sumarlos aquí.
Replay OCR registrado FAILED sin retry, reader corregido acredita efecto; borde
sintético con procedencia explícita. Smoke previo: Keys6/10 Bronze,15/10 Silver,
Gold row abierta,1/20, útil1, sin >> ni confirm. No consumo nuevo.
Targeted swipe/calibration/viewport/gestures permanecen cerrados y sin diff.
[informe Trading](TRADING_FAILED_SESSION_A94AC2E7.md).

## Ads

**Live breadth debt: CLOSED** por USER_GT2026-10-06 y campaña natural posterior
al reset: los dos failures observados fueron MW/Trading, causalmente ajenos a Ads.
Broad live coverage, short ads y multipart natural coverage dejan de ser deuda
activa. Notas previas son historia superseded, salvo regresión futura concreta.
No se afirma que esa campaña terminó28/28 COMPLETED.

## Validación consolidada única del worktree

Desde raíz, Python según AGENT_LOCAL. Invocation exacta (salida redirigida a
`artifacts/checkpoint-worktree.txt`):

```powershell
& .\.venv\Scripts\python.exe -m pytest -q tests/test_relief_policy.py tests/test_routines.py tests/test_gui_cleanup.py tests/test_gui_model.py tests/test_gui_controller.py tests/test_gui_entrypoint.py tests/test_gui_launcher.py tests/test_character_state_gui.py tests/test_socket_inventory_relief.py tests/test_socket_inventory_relief_perception.py tests/test_socket_inventory_full_perception.py tests/test_socket_animation_scope.py tests/test_socket_animation_live_replay.py tests/test_equipment_relief.py tests/test_equipment_block_relief.py tests/test_equipment_combine_relief.py tests/test_equipment_inventory_relief.py tests/test_equipment_sell_runtime.py tests/test_equipment_sell_capability.py tests/test_world_boss_equipment_sell.py tests/test_craft_runtime.py tests/test_craft_operation.py tests/test_craft_visit.py tests/test_craft_action_executor.py tests/test_craft_count_live_replay.py tests/test_craft_armor_live_replay.py tests/test_mw_craft_capacity_entry.py tests/test_mw_craft_live_regressions.py tests/test_treasure_runtime.py tests/test_treasure_keys.py tests/test_treasure_fast_drain.py tests/test_keys_promotion.py tests/test_keys_promotion_runtime.py tests/test_keys_phase.py tests/test_keys_effect_fact_reuse.py tests/test_keys_zero_live_replay.py tests/test_productive_runtime.py tests/test_session.py tests/test_session_report.py tests/test_flow_registry.py tests/test_flow_contracts.py tests/test_smoke_session_composition.py tests/test_productive_monster_wave_session_binding.py tests/test_gold_farming.py tests/test_stages_daily.py tests/test_stages_claim_loop.py tests/test_stages_navigation.py tests/test_world_boss_flow.py tests/test_monster_wave.py tests/test_monster_wave_board.py tests/test_monster_wave_board_acquisition_scope.py tests/test_monster_wave_entry.py tests/test_monster_wave_integration.py tests/test_monster_wave_ocr.py tests/test_monster_wave_points_reward.py tests/test_monster_wave_productive.py tests/test_monster_wave_resource_route.py tests/test_monster_wave_standalone.py tests/test_resource_route_planner.py tests/test_mw_failed_session_replay.py tests/test_trading_key_row_reader.py tests/test_trading_keys.py tests/test_trading_keys_productive.py tests/test_trading_keys_facts_telemetry.py tests/test_trading_operation.py tests/test_trading_panel_reader.py tests/test_trading_row_facts.py tests/test_trading_panel_profile.py tests/test_trading_runtime.py tests/test_trading_failed_session_replay.py --basetemp=artifacts/checkpoint-worktree-tmp -o cache_dir=artifacts/checkpoint-worktree-cache --junitxml=artifacts/checkpoint-worktree.xml *> artifacts/checkpoint-worktree.txt
```

**1816 passed, 0 failed, 0 skipped, 0 deselected; 334.68s**. No se suman ejecuciones anteriores superpuestas.

## Validación del INDEX aislado

Export completo con `git checkout-index --all --prefix=<export-absoluto>/`;
sin copiar archivos del worktree ni capturas raw. Mismos contratos, selección
portable de55 módulos: policy/migration/GUI/runtime/Session/wiring, Socket/Equipment/
Craft/Treasure, MAX y replays curados MW/Trading. Dos replays legacy de Combine
dependen de raw histórico ignorado y se deselectan explícitamente; el smoke/corpus
Socket histórico ausente tiene skip declarado. Desde la raíz del export, sin
PYTHONPATH del worktree:

```powershell
& D:\PROYECTOS\kritika-farmbot\.venv\Scripts\python.exe -m pytest -q tests/test_relief_policy.py tests/test_routines.py tests/test_gui_cleanup.py tests/test_gui_model.py tests/test_gui_controller.py tests/test_gui_entrypoint.py tests/test_gui_launcher.py tests/test_character_state_gui.py tests/test_socket_inventory_relief.py tests/test_socket_animation_scope.py tests/test_equipment_relief.py tests/test_equipment_block_relief.py tests/test_equipment_combine_relief.py tests/test_equipment_inventory_relief.py tests/test_equipment_sell_runtime.py tests/test_equipment_sell_capability.py tests/test_world_boss_equipment_sell.py tests/test_craft_runtime.py tests/test_craft_operation.py tests/test_craft_visit.py tests/test_craft_action_executor.py tests/test_mw_craft_capacity_entry.py tests/test_treasure_runtime.py tests/test_treasure_keys.py tests/test_treasure_fast_drain.py tests/test_keys_promotion.py tests/test_keys_promotion_runtime.py tests/test_keys_phase.py tests/test_keys_effect_fact_reuse.py tests/test_productive_runtime.py tests/test_session.py tests/test_session_report.py tests/test_flow_registry.py tests/test_flow_contracts.py tests/test_smoke_session_composition.py tests/test_productive_monster_wave_session_binding.py tests/test_gold_farming.py tests/test_stages_daily.py tests/test_stages_claim_loop.py tests/test_stages_navigation.py tests/test_world_boss_flow.py tests/test_monster_wave.py tests/test_monster_wave_board_acquisition_scope.py tests/test_monster_wave_integration.py tests/test_monster_wave_productive.py tests/test_monster_wave_resource_route.py tests/test_monster_wave_standalone.py tests/test_resource_route_planner.py tests/test_mw_failed_session_replay.py tests/test_trading_keys.py tests/test_trading_keys_facts_telemetry.py tests/test_trading_operation.py tests/test_trading_panel_profile.py tests/test_trading_runtime.py tests/test_trading_failed_session_replay.py --deselect=tests/test_equipment_combine_relief.py::test_native_ethereal_result_veil_and_clean_panel --deselect=tests/test_equipment_combine_relief.py::test_native_fuse_result_resolves_tappable_without_lowering_confidence --basetemp=artifacts/checkpoint-index-tmp -o cache_dir=artifacts/checkpoint-index-cache --junitxml=artifacts/checkpoint-index.xml
```

**1565 passed, 0 failed, 0 errors, 1 skipped, 2 deselected; 86.47s**.
El skip corresponde al corpus nativo Socket histórico ignorado ausente; los dos
deselected son los replays raw de Combine nombrados en la invocation.
Imports productivos y assets resuelven dentro del export; código/fixtures staged
comparados contra el export y hunks históricos excluidos verificados.

Primer intento INDEX:1469 passed,1 skipped,2 deselected,96 setup errors,99.59s;
todos los errores eran FileNotFoundError al crear basetemp, porque el export limpio
no tenía el padre artifacts ignorado. Se creó sólo ese directorio vacío y se repitió
la misma selección, sin copiar raw ni cambiar código. Resultado final anterior;
no sumar ambos intentos. Sólo el informe se actualiza después de los tests.

## Baseline debt

Sin suite global ni recheck de deuda en este cierre. El último cierre publicado
[Character State](CHARACTER_STATE_CHECKPOINT.md) verificó **24 failures heredados**,
356 passed,0 skipped, mismo conjunto contra HEAD. El artifact inicial de25 es
anterior a la corrección de catalog y no sustituye esa reconciliación:
11 GUI functional harness anterior a Session;7 lobby-return scope;2 pets-manage
scope;4 handoffs de Mailbox/Daily con `_initial_lobby` retirado. No se modifica código
ajeno para ocultarlos. La selección causal final no incluye esos módulos históricos;
cualquier fallo nuevo causado por el diff bloquea el cierre.

## Auditoría de paths/hunks anterior al staging

### RELIEF_REFACTOR

- ARCHITECTURE.md
- bot/craft_runtime.py
- bot/equipment_relief.py
- bot/gui_model.py
- bot/keys_promotion_runtime.py
- bot/monster_wave_resource_route.py
- bot/productive_runtime.py
- bot/relief_policy.py
- bot/routines.py
- bot/socket_inventory_relief.py
- bot/stages_reliefs.py
- docs/GUI_CONFIGURATION.md
- tests/test_gui_cleanup.py
- tests/test_relief_policy.py
- tests/test_routines.py
- tools/gui.py
- tools/gui_cleanup_smoke.py
- tools/reliefs_gui_smoke.py

### MW_FIX

- bot/monster_wave_activity.py
- bot/monster_wave_board_perception.py
- docs/MW_FAILED_SESSION_86ADECD4.md
- tests/fixtures/mw_session_86adecd4/
- tests/test_monster_wave.py
- tests/test_mw_failed_session_replay.py
- tools/mw_board_readonly_smoke.py

### TRADING_FIX

- bot/trading_key_row_reader.py
- docs/TRADING_FAILED_SESSION_A94AC2E7.md
- tests/fixtures/trading_session_a94ac2e7/
- tests/test_trading_failed_session_replay.py

### HISTORICAL_INDEPENDENT

- Kritika_FarmBot_Plan_Preparacion_Codex_Astra.md (borrado previo)
- bot/equipment_sell_reader.py (payment-wrap K Coins)
- bot/summon_pet_daily_flow.py
- tests/test_portal_obstruction_recovery.py
- tests/fixtures/equipment_payment_wrap/
- tests/test_equipment_payment_wrap_replay.py
- check_eval.py
- fix_tests.py
- test_live.py
- test_wait.py

### SHARED

- bot/flow_registry.py: import coordinator + WB/Socket/Equipment/Craft/Keys wiring = RELIEF_REFACTOR; A1 board observer = MW_FIX; _build_summon_pet_daily = HISTORICAL_INDEPENDENT excluido
- CONTEXT.md: Reliefs/MW/Trading y Ads = causal; sección FAILED manual28 Sell = HISTORICAL_INDEPENDENT excluida
- ROADMAP.md: cierre Reliefs/MW/Trading y deuda Ads = causal
- docs/GAMEPLAY_GT.md: MAX USER_GT = MW_FIX; Keys balances/quantity = TRADING_FIX
- docs/RESOURCE_ROUTING.md: policy = RELIEF_REFACTOR; A1 = MW_FIX; cierre Ads = reconciliación causal

### RUNTIME_ARTIFACT

- logs/
- screencaps/
- artifacts/
- runtime/ (DB/WAL/SHM, GUI preferences)
- routines.json y routines.json.*.bak
- AGENT_LOCAL.md
- .pytest_cache/ y __pycache__/

Archivos compartidos staged por contenido selectivo: `flow_registry.py` conserva
el builder Summon Pet original de HEAD en INDEX; `CONTEXT.md` omite la sección Sell
independiente en INDEX. El worktree conserva ambos sin modificación destructiva.
No Open Pets, unrelated Sell, historical Summon Pet, DB runtime, logs/raw artifacts
ni targeted swipe en el staged diff. Sólo fixtures pequeños curados MW/Trading.
El export valida precisamente esos hunks staged, no la copia mixta del worktree.

## Cierre

Antes de commit: staged stat/name-status, diff semántico y cached --check.
Después: HEAD/parent/message/branch, índice vacío y worktree --check/status.
Push autorizado sólo con validación causal/INDEX verde; sin force ni reset/rebase.
El hash y verificación local/tracking/remote se informan después del commit.
