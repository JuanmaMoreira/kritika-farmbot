# Character State — checkpoint conjunto 2026-10-06

Parent `fe774abcef3a636c138028717a0d2a0b514c5e6f`, branch
`rebuild/stable-baseline`, mensaje `feat: add persistent character state tracking`.
Un único cierre causal de Identity, Persistent State, ResetClock, Ads/WB,
Quick Menu snapshots, Data Sweep y GUI/config. No incluye Open Pets ni el trabajo
histórico independiente. [Informe de implementación](CHARACTER_STATE_IMPLEMENTATION.md)
conserva los runs anteriores y sus resultados, sin sumarlos al run de aceptación.

## Acceptance conservada

- Identity closed-set: **84/84 frames, 28/28 identidades, 0 wrong, 0 UNKNOWN**,
  incluyendo los tres Unicode. Stable IDs no dependen de OCR/posición/Rotation.
- Sweep productivo: run `2c282440554f480a9d9a59c366650195`, session
  `406ad33e80154781a8b426898b1f27d2`: **28 processed, 28 unique identities,
  28 snapshots completos, 28 Rotations, 0 acquisition/technical failures**;
  GUI349.2s (~5:49), Session345.545s. Sin flows productivos; una apertura útil QM
  por personaje, snapshot antes de Character Select; progreso y Stop Safely.
- Rutina normal + `BEFORE_CHARACTER_ROTATION`: mismo QM de Rotation → snapshot
  completo → persistencia → Character Select, sin apertura adicional. Integración
  desde el request GUI prueba OFF/BEFORE, dos identidades y atribución separada.
- GUI: Step Settings sólo occurrence seleccionada; WB eligibility/relief en WB,
  MW/relief en MW y prerequisites realmente consumidos en Stages/Gold. BM y otros
  sin config muestran empty-state. Routine Settings posee Resource snapshot;
  Application posee Appearance. Apply/Save, repeated steps y JSON v1 conservados.
- Sorting tipado y sólo visual; UNKNOWN al final en ambos sentidos; WB asc
  NO→YES→UNKNOWN, desc YES→NO→UNKNOWN. Refresh conserva columna/dirección.
- Light/Dark dinámico centralizado, persistencia global independiente, dialogs
  propios y reopen. GUI real revisada a1100×760/760×560, escala Tk1.33465,
  stress de30 filas, scroll, report/console, Character State28 y headers.
  Auditoría local: `artifacts/gui_cleanup_df0f5e5c/audit.json`,19 screenshots
  ignorados, cero callback errors, Dark reopen, filas idénticas. El progreso
  Sweep de esta auditoría es sintético; no se repitió el sweep físico.

## Validación consolidada

Invocation desde raíz (Python local indicado en AGENT_LOCAL):

```powershell
.venv/Scripts/python.exe -m pytest tests/test_character_identity.py tests/test_character_state.py tests/test_character_data.py tests/test_character_data_sweep.py tests/test_character_state_gui.py tests/test_gui_cleanup.py tests/test_stages_daily.py tests/test_stages_claim_loop.py tests/test_world_boss_flow.py tests/test_world_boss_eligibility.py tests/test_world_boss_equipment_sell.py tests/test_gold_farming.py tests/test_productive_runtime.py tests/test_ocr_extractors.py tests/test_session.py tests/test_session_report.py tests/test_rotation.py tests/test_routines.py tests/test_gui_entrypoint.py tests/test_gui_controller.py tests/test_gui_model.py tests/test_gui_launcher.py -q -p no:cacheprovider --basetemp=<directorio-local-unico>
```

**698 passed, 0 skipped, 0 deselected, 44.96s**. No se suman selecciones anteriores
solapadas. Logs, inventory por archivo y hashes de preservación en
`artifacts/character_state_checkpoint_d265cfb1/`, ignorado.

Validación INDEX: export portable de todo el índice con `git checkout-index`,
Python local ejecutado desde ese árbol, sin PYTHONPATH/worktree original.
Mismos22 módulos: **694 passed, 0 skipped, 4 deselected, 20.85s**. Los cuatro
replays requieren capturas live históricas ignoradas y pasaron en el worktree.
No se añaden esos originales grandes al commit. Flags adicionales de la invocation:

```text
--deselect=tests/test_rotation.py::test_live_preselected_predecessor_succeeds_with_real_detectors
--deselect=tests/test_rotation.py::test_live_frame_detector_drives_predecessor_tap
--deselect=tests/test_world_boss_eligibility.py::test_acquired_return_frames_are_recognized_by_unchanged_production_detectors
--deselect=tests/test_world_boss_eligibility.py::test_scoped_daily_decision_matches_global_on_curated_hub_and_foreign_frames
```

Los imports apuntan al export INDEX, incluido `flow_registry.py` de baseline:
no dependen del hunk Summon Pet ni de fixtures nuevos sin stage.

No se repite la suite amplia (~15min): su resultado original4333 passed,
4 skipped,26 failed está reconciliado en el informe. Los dos afectados fueron
corregidos; los24 restantes se reprodujeron contra HEAD. El cierre vuelve a
comparar sus cinco módulos contra la lista exacta de24: **356 passed, 24 failed,
0 skipped,123.20s**, mismo conjunto exacto, sin fallos nuevos. Ese recheck no es una
nueva suite amplia ni se suma a la selección causal verde. Invocation:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_gui_functional.py tests/test_lobby_return_scope.py tests/test_pets_manage_navigate_scope.py tests/test_precondition_snapshot_handoff.py -q -p no:cacheprovider --basetemp=<directorio-local-unico>
```

## Runtime preservado y límites

Auditoría mediante SQLite raw `mode=ro`, sin inicializar Store/catch-up:
integrity_check OK,28 IDs,28 snapshots completos actuales,63 entradas de historia.
DB/WAL/SHM, `runtime/gui_preferences.json`, routines locales, logs y artifacts
permanecen fuera del commit. Los datos reales no se recrean ni corrigen.

Estado acreditado en la aceptación Sweep y auditoría inicial: **Ads27=0,
Burst Breaker UNKNOWN; WB6=YES,22 UNKNOWN**. Provenance VIDEO0/LOG_BACKFILL y
WB_PANEL conservada en historia. Clock inicial almacenado:
última observación2026-10-06T02:41:19.864Z, `1d 3h48m`, anchor/next WB reset
2026-10-07T07:00Z, next daily2026-10-06T07:00Z, cycle1. Es el estado persistido;
el catch-up productivo evoluciona epochs/ciclos. Durante el cierre apareció un
catch-up registrado `SYNCHRONIZED_RESET`, efectivo2026-10-06T07:00Z y
observado2026-10-06T12:27:50.521Z: **Ads28=2**, epoch2026-10-06T07:00Z,
next daily2026-10-07T07:00Z. WB6YES/22UNKNOWN, anchor/cycle y todos los snapshots
permanecen iguales; history conserva todos los facts anteriores y añade sólo ese
reset. No se restauró el epoch anterior ni se escribieron facts manuales. Archivo
DB principal, preferencias y routines locales conservan hash; WAL/SHM contienen
la evolución runtime y siguen ignorados. `runtime_after.json` registra esta diferencia.
Pareja Rank/Damage adquirida en **World Boss main**, no en Battle Mode Select.

Única deuda física de este frente: valor natural0 visible en Quick Menu aún no
adquirido; parser/tests lo cubren. UNKNOWN operacional no es deuda de implementación.

## Separación del índice

`CHARACTER_STATE`: identity/assets/manifests, store/reset, Ads/WB, reader, tests y
contratos físicos/software. `DATA_SWEEP`: Session/request/controller/runtime,
auditor y crops pequeños del reintento. `GUI_CLEANUP`: forms/model/preferences,
theme, smoke, tests y docs. Owners compartidos auditados por hunk:
session/runtime/routines/model/controller/gui sólo contienen trabajo causal.
Assets nuevos: tres máscaras ~1KB y41 crops pequeños (máximo63KB), manifest incluido;
los84 frames originales y screenshots de auditoría no se versionan.

`HISTORICAL_INDEPENDENT`, preservado y excluido completo:

```text
 D Kritika_FarmBot_Plan_Preparacion_Codex_Astra.md
 M bot/flow_registry.py
 M bot/summon_pet_daily_flow.py
 M tests/test_portal_obstruction_recovery.py
?? check_eval.py
?? fix_tests.py
?? test_live.py
?? test_wait.py
```

`flow_registry.py` sólo contiene el hunk histórico Summon Pet; el wiring WB del
frente está en ProductiveRuntime. No se absorbió ese hunk. El índice se revisa
por name-status/stat, diff semántico y `git diff --cached --check` antes de commit.
