# GUI/config — contrato vigente

Refactor Reliefs 2026-10-06 sobre `d97e899b9fac3fbc26583d595b21abd4267b0ce9`.
Implementación en `tools/gui.py`; proyección en `bot/gui_model.py`. Tk/ttk sigue vigente.

## Owners y persistencia

Relief configuration belongs to routine-level transversal relief policy, not to current consumer flows.
Consumers are not part of the policy contract.
`RoutineSpec.relief_policy` / JSON v2 posee decisiones de Socket, Equipment Sell,
Crafting Material y Treasure. La UI no enumera consumidores ni deriva ownership del call graph.

| Setting | Owner | Persistencia / semántica | Default migrado sin overrides |
| --- | --- | --- | --- |
| Enhance All | Socket Relief de rutina | `relief_policy.socket.enhance_all` | true |
| Sell incompatible opals | Socket Relief de rutina | `relief_policy.socket.sell_incompatible` | true |
| Sell Ethereal Boots/Chest/Gloves/Helmet/Pants | Equipment Relief de rutina | `equipment_sell.ethereal_types`: checked **autoriza venta** | checked |
| Sell Ethereal Earrings/Necklace/Ring/Weapon | Equipment Relief de rutina | mismo allowlist de venta | unchecked |
| Sell Ethereal Enhance | Equipment Relief de rutina | `equipment_sell.ethereal_enhance`: checked autoriza su familia independiente | false |
| Weapon / Armor / Accessories | Crafting Material Relief de rutina | `crafting_material.categories` | las tres habilitadas, preservando el drain existente |
| Open Gold Keys for safe capacity relief | Treasure Relief de rutina | `treasure.gold_keys` | true |
| WB eligibility | occurrence WB | `config.world_boss.eligibility` | DAILY_QUEST |
| Resource snapshot | rutina | `resource_snapshot_mode` | BEFORE_CHARACTER_ROTATION |
| Appearance | Application | `runtime/gui_preferences.json` | Light si falta/es inválida |
| Enabled / continuation | occurrence | `enabled` / `continue_on_unavailable` | true |
| Characters / Debug | request | sólo memoria | 28 / false |

Combine sigue encapsulado antes de Sell, sin configuración ni panel vacío. Ethereal+
sigue protegido permanentemente. Los labels dicen **Sell Ethereal**, sin invertir
el allowlist antiguo. No hay switch general Socket: ambas opciones false impiden sus
suboperaciones productivas; el owner conserva su retorno y resultado sin relief.

`treasure.gold_keys` gobierna el OPEN_ONCE + drain seguro existente. Platinum no tiene
campo ni control hoy. El objeto `treasure` es el slot de schema donde se añadirá
`open_platinum_keys` junto con operación, GT y guards; un campo no implementado se
rechaza de forma segura, nunca aparenta funcionar.

## Layout y comportamiento de edición

```text
Routine Editor
├── Steps (ordered occurrences)
├── Step Settings
├── Routine Settings
├── Reliefs
└── Application
```

Step Settings sólo expone eligibility WB. Los dos campos legacy MonsterWaveConfig
se conservan en configs guardadas y APIs standalone, pero no se muestran: en el path
productivo actual la preparación resuelve tickets por SKIP físico y el planner decide
YES/NO. No presentar switches sin efecto en la rutina. Otros steps sin decisiones
configurables muestran una nota y Apply deshabilitado.

Routine Settings contiene Resource snapshot. Reliefs contiene los cuatro grupos de
la tabla. Application contiene Light/Dark. Estos tres panels y Step Settings usan el
viewport Canvas/scrollbar existente, wheel local, Page Up/Down y tokens del theme.
Notas ajustan su ancho; Apply WB queda fuera del scroll. No requiere maximizar.

Apply WB modifica sólo la occurrence y descarta ediciones no aplicadas al cambiar
selección. Checkboxes Reliefs actualizan directamente el borrador de **rutina**;
Save Routine persiste. Seleccionar steps no vuelve a cargar ni modifica relief policy.
Reorder conserva occurrences; Duplicate copia policy y archivo legacy de forma independiente.

## Migración v1 → v2

Load no escribe. Save hace backup único del original v1 y replace atómico desde un
temporal. `config.equipment_sell` se mueve a la policy; cada valor explícito se conserva
por índice original en `legacy_relief_configs`. La reconciliación incluye los defaults
implícitos de consumidores v1. Valores distintos intersectan tipos vendibles y sólo
habilitan Ethereal Enhance si todos autorizaban: warning explícito, sin elegir una
occurrence. Config corrupta se conserva y deniega permisos; policy v2 inválida/faltante
usa opciones productivas desactivadas, allowlist Ethereal vacío y warning. Low-tier
Bulk/Combine mantienen su contrato seguro no configurable.

El archivo local inspeccionado tiene dos rutinas. En Basic Gold, WB y Gold guardaban
el mismo allowlist de cinco Armor y Enhance false; migran sin conflicto. Custom usa
defaults. Resource snapshot, selected ID, ordering, flags, WB eligibility y legacy MW
se conservan. No se modifican .env ni datos de Character State.

## Sorting de Character State

Click en cualquier header: primera vez ascending; segundo click descending.
Una flecha discreta indica columna/dirección. El refresh automático mantiene la
selección y reordena los IDs existentes mediante `Treeview.move`.

- Character: display canónico, `casefold()`; ID permanente desempata.
- Ads y cinco recursos: enteros reales, no texto formateado.
- WB asc: **NO → YES → UNKNOWN**; desc: **YES → NO → UNKNOWN**.
- Snapshot time: timestamp numérico; Ads status / updated: timestamp del último
  intento visible, o actualización operacional si no hubo intento; WB cycle: entero.
- UNKNOWN/None permanece **al final en ambos sentidos**. Empates conservan orden
  de display canónico + ID independientemente de la dirección.

Sorting sólo usa la última lectura en memoria y mueve filas. No llama al store,
no escribe DB ni cambia IDs, Rotation o Character Select. El refresh conserva su
catch-up/timer ya existente; no se introduce polling adicional. La preferencia de
sort dura durante esa GUI, no se añade persistencia a la DB ni a una routine.

## Theme

`tools/gui_theme.py` centraliza Light/Dark: background, surface, surface_alt,
foreground, muted, accent, selection, selected_text y border. Base ttk `clam`
para que Windows respete colores; maps para active/selection/disabled y controles
readonly. También cubre widgets clásicos Text/Listbox/Canvas y popdowns de combobox
ya creados. Report/Console reemplazan su scrollbar nativo por ttk para evitar la
franja clara que Windows no tematiza.

New/Rename, confirmación Delete, unsaved draft y cierre de tarea activa usan
diálogos propios con la misma paleta. Decoración de ventanas sigue siendo del OS.
Switch Light/Dark conserva los widgets/datos y no llama al controller/runtime.
`bot/gui_preferences.py` posee JSON global independiente de Routine JSON y SQLite,
escritura temporal + replace, sin migración; está ignorado mediante `/runtime/`.

## Validación reproducible

Tests directos en `tests/test_gui_cleanup.py`, además de regresiones de routines,
model/controller/entrypoint/launcher, Character State GUI, collector, Sweep,
Session y Rotation. Tk tests usan stores/routines/preferences temporales y no
inician hardware. El smoke visible `python -m tools.gui_cleanup_smoke` usa backup
privado de los 28 estados reales y copia privada de routines; las capturas van a
`artifacts/gui_cleanup_*`, ignoradas. Persiste la elección global final Dark.
Su captura de progreso Sweep es una proyección sintética, no ejecución física.

Auditoría: 1100×760 y 760×560, escala Tk actual ~1.33465 (decoración/DPI Windows
capturada en coordenadas físicas DWM). BM, MW, WB repetido, settings de rutina,
stress de 30 filas de settings, tabla/resources/times, report, console, Application,
diálogo y Light↔Dark. Reopen confirma 28 filas idénticas y Dark persistido.
La pasada visual no necesitó teléfono, sweep completo, Ads/resources ni evaluator.
El cierre conjunto se documenta en [CHARACTER_STATE_CHECKPOINT](CHARACTER_STATE_CHECKPOINT.md).

Validación de Reliefs (2026-10-06): `python -m tools.reliefs_gui_smoke` abre Tk real
con copias privadas, comprueba las cuatro pestañas, Light/Dark, scroll en ventana
reducida, aislamiento de Step Settings y Save/reopen idéntico. Capturas y auditoría
local en `artifacts/reliefs_gui_b810a723/`; cero Session/inputs de teléfono.
El `routines.json` local se migró a v2 después de conservar un backup exacto v1;
las dos rutinas y la selección Basic Gold Farming se conservan sin warnings.
