# Checkpoint Arena Stabilization + Character State Arena VP

Parent: `56b472d0e008d7e9d2b8f6842491c7feced095a0`; rama `rebuild/stable-baseline`.
La publicación comprende sólo Arena stabilization y Arena VP. La auditoría causal,
runs exactos, secuencias, saldos y capturas están en
[ARENA_STABILIZATION_20261010](ARENA_STABILIZATION_20261010.md).

## Revisión y alcance

Ice Warlock `16fdb15e` y Eilla `a81d6af4` comparten la primera divergencia:
Combine NO_RELIEF→Sell intenta Quick Menu desde Lobby con hitbox incorrecta.
El adapter Stages ahora abre Inventory directo con barriers existentes; el
coordinador y los guards de Sell/retorno/retry siguen siendo sus owners.
Se incluyen Muse post-Clear/post-Claim, deadline/cancelación, captura PNG nativa
independiente del stream, observación pasiva Mao tras relief y diagnósticos de
MANUAL_RESOLUTION. Sin cambiar routing40/100/80, adaptativo o Shared Meteorites.

VP es best-effort por identidad estable, schema2 conservador, semana según fase
WB y rechazo de escrituras anteriores. El frame proviene del retorno normal de
Auto Repeat. La revisión mueve el OCR después del Lobby ya acreditado: no puede
gastar freshness de Back ni originar una espera extra. Frame expirado/oclusión/
error conserva el dato anterior válido; sin taps ni reentrada. Regresión de OCR
lento/fallido acredita resultado y ausencia de inputs/observaciones posteriores.

## Aislamiento

INDEX inicialmente vacío. Inventario/hash de66 paths modificados/untracked y patch
inicial conservados localmente en `artifacts/arena_checkpoint_20261010`.
Hunks mixtos separados con patches aplicados sólo al INDEX:

- `bot/fact_reader.py`: sólo deadline/cancelación post-OCR; el override de observer
  del fix independiente MW readiness permanece en el worktree.
- `CONTEXT.md`: sólo sección Arena/VP; las notas MW readiness, Ads y Sell quedan fuera.

Excluidos Ads inset, Equipment payment wrap, MW readiness scope y wiring,
Summon Pet, portal tests, herramientas Gold, helpers locales, la eliminación del
plan histórico y el probe de adquisición local. Raw/capturas, runtime SQLite,
logs y caches no se publican. Assets runtime VP pequeños y manifest curado sí.
El evaluator VP requiere los raw locales descritos/hashados en su manifest;
su ausencia en una copia nueva no implica ausencia de capacidad productiva.

Snapshot del INDEX exportado en artifacts, sin residuales de Python ni cambios
de configuración local. Se ejecutan regresiones dirigidas allí con el Python
documentado en AGENT_LOCAL; fixtures/raw existentes se copian sólo para replay
local, no al commit. Resultado del snapshot aislado: **713passed**, sin failed ni skipped (27 módulos
dirigidos,62.60s). Replays/evaluators Arena Farming9/9 y VP6/6, wrong0; los
hashes de todos los raw presentes coinciden con sus manifests. Validación previa
del cambio puntual de retorno VP:143passed. Sin tests de código adicionales por
las actualizaciones documentales finales.

## Evidencia física reutilizada y límites

Sin acceso nuevo al teléfono. Se reutilizan Inventory directo113/112,
Sell113→107, soporte Activated, representativo2Manual/1MW/HARD104/88 con retorno
y VP focal8badges/0Stamina que guardó Eilla182050, semana2026-10-05.
La última condición acreditada del dispositivo es Eilla Lobby; runtime cerrado
2026-10-10T15:48:34.949708Z. No se altera esa condición durante el checkpoint.

El smoke representativo tenía120Stamina y límite de4operaciones. **No acredita
una nueva sesión continua600Stamina**; esa evidencia queda pendiente del uso
ordinario. No nueva sesión larga ni campaña28/28. Precisión del horario WB≈1min;
se reutiliza su calibración UTC, sin nueva adquisición física del reset del lunes.
OCR síncrono termina su llamada antes de comprobar deadline/cancelación; nunca
se acepta el resultado tardío ni se repite un input consumptivo por ambigüedad.


## Assets y paths publicados

39 paths. PNG backdrop34.006bytes y mask804bytes; geometría51×391,7552pixels
de backdrop usados. Hashes SHA256 verificados contra INDEX/export:

- `vp_backdrop.png`: `6a370b78006c924da2c97162124aaa16b58e1ec51eceef2f295e81926d51a97a`.
- `vp_backdrop_mask.png`: `8311068426d5b4939146036a90df1bdb49ac221c115fc5bb75dd0e9e6f89d5ea`.

- `ARCHITECTURE.md`.
- `CONTEXT.md`.
- `assets/arena/vp_backdrop.png`.
- `assets/arena/vp_backdrop_mask.png`.
- `bot/arena_farming_cycle.py`.
- `bot/arena_farming_report.py`.
- `bot/arena_farming_resources.py`.
- `bot/arena_flow.py`.
- `bot/arena_vp.py`.
- `bot/capture.py`.
- `bot/character_state.py`.
- `bot/fact_reader.py`.
- `bot/gui_model.py`.
- `bot/manual_stages.py`.
- `bot/monster_wave_activity.py`.
- `bot/productive_runtime.py`.
- `bot/stages_actions.py`.
- `bot/stages_reliefs.py`.
- `bot/stages_runtime.py`.
- `datasets/arena_vp_manifest.json`.
- `docs/ARENA_FARMING_CYCLE.md`.
- `docs/ARENA_STABILIZATION_20261010.md`.
- `docs/ARENA_STABILIZATION_CHECKPOINT_20261010.md`.
- `docs/GAMEPLAY_GT.md`.
- `docs/RESOURCE_ROUTING.md`.
- `tests/test_arena_farming_report.py`.
- `tests/test_arena_farming_resources.py`.
- `tests/test_arena_post_claim_refresh.py`.
- `tests/test_arena_vp.py`.
- `tests/test_capture_native_chronology.py`.
- `tests/test_character_state_gui.py`.
- `tests/test_fact_reader.py`.
- `tests/test_manual_stages.py`.
- `tests/test_monster_wave_post_clear_recovery.py`.
- `tests/test_stages_equipment_inventory_route.py`.
- `tests/test_stages_navigation.py`.
- `tools/arena_farming_smoke.py`.
- `tools/arena_vp_evaluation.py`.
- `tools/gui.py`.
