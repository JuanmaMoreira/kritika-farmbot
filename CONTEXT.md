# Estado actual — Kritika FarmBot

## Worktree y checkpoint

Inspección documental: 2026-09-25. Rama `rebuild/stable-baseline`, HEAD `22c213a` (`docs: clarify MW skip lifecycle from HIL (30/30, 140k Gold, activation)`). Checkpoint histórico V1 `04640c2`; no representa el wiring post-V1 actual. Código + tests del worktree prevalecen. Autoridad física: [GAMEPLAY_GT](docs/GAMEPLAY_GT.md); contrato/wiring de recursos: [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md).

**Local sin commit, preservar:** `bot/{craft_reader,craft_runtime,flow_registry,monster_wave_productive,monster_wave_resource_route,monster_wave_standalone}.py`, tests de Craft/MW correspondientes y `tests/test_craft_reader_context.py` untracked. Contienen L2 reactivo, relief del CraftStep, handoff directo hacia Craft, diagnóstico OCR y umbral local Weapon cost 0.80. Este reset no los modifica ni declara validación nueva.

También preservar la eliminación local de `Kritika_FarmBot_Plan_Preparacion_Codex_Astra.md` y `check_eval.py`, `fix_tests.py`, `test_live.py`, `test_wait.py` untracked. Los cambios documentales locales anteriores fueron retenidos en el [snapshot histórico](docs/legacy/DOC_RESET_20260925.md); la sección L2 de la reconstrucción se conserva.

## Producto y límites reales

- CLI/GUI comparten runtime: Black Market, World Boss, Monster Wave, Send Stamina, Summon Pet Daily, Daily Quests, Mailbox y Guild Check-In; sesión multicharacter, Rotation, Identity, Eligibility y observabilidad existentes.
- MW ejecuta un proceso SKIP MAX por invocación; sin farming loop, Start manual ni Auto Battle MW. L1 está conectado en `_build_productive_monster_wave`: board fresco → plan único → prerequisites como máximo una vez → resume del mismo request. El builder conserva fallback al flow bare ante AttributeError/TypeError/ValueError.
- **L2 local/in progress:** después del resume trata el blocker Equipment/Socket observado, una vez por tipo, conserva `daily` y no repite board/planner/J. Equipment usa Combine-first sin plan Sell productivo. No está cerrado físicamente de punta a punta.
- Craft/Trading/Keys/Treasure, Equipment Sell y composer tienen capacidades standalone; eso no completa sus adapters productivos. Keys/Materials/Gold recovery aún tienen callbacks de fallo en `flow_registry.py`. Craft→Combine aún es placeholder sin input; detalle exacto en RESOURCE_ROUTING.

## Primera divergencia y pendientes inmediatos

**P0 Craft:** la entrada física fue confirmada por el usuario, pero la postcondición exige título/rate/expert y counts/costs de las tres familias. Logs existentes `logs/20260924T225232.947447Z_selected_flows_a578d341.jsonl` y `logs/20260924T225448.940649Z_selected_flows_7a00acd2.jsonl` registran `craft.entry_postcondition_sample` rechazado y timeout; el segundo conserva título de baja confianza y Weapon count contaminado. El cambio local de confianza de Weapon cost no desacopla identidad de economía. Title/Hero Weapon count están expuestos a CHAT; rate intersecta Heaven & Hell. No reinterpretar esto como fallo del GT de navegación.

Siguiente: identidad Craft con landmark seguro, economía sólo de la operación requerida; validación dirigida y un smoke MW autorizado. Después, corregir la primera divergencia siguiente y completar wiring/L2 siguiendo [ROADMAP](ROADMAP.md), sin reaperturas de GT.

**Bug separado Run Session:** `ProductiveRuntime.run_session` prepara por `isinstance(MonsterWaveFlow)`; `ProductiveMonsterWaveFlow` no hereda ese tipo y queda sin binding `prepared(zone, daily=True)`, aunque se asigna eligibility por nombre. No atribuir este problema a Craft ni afirmar Daily productivo integrado.

## Entorno temporal

Cuatro fixtures Rotation ausentes bajo `artifacts/failure_evidence/` causaron FileNotFoundError en validaciones anteriores. Gap ambiental conocido, ajeno a MW/Craft; no bloquea un smoke ni obliga a repetir suite completa. Paths de Python/ADB/scrcpy en `AGENT_LOCAL.md`. No se ejecutaron tests/evaluator/HIL durante este reset; resultados previos no invalidados siguen siendo reutilizables.
