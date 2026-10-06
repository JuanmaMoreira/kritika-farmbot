# GUI/config — contrato vigente

Cleanup 2026-10-06 sobre `fe774abcef3a636c138028717a0d2a0b514c5e6f`, incluido
en el checkpoint de Character State / Character Data Sweep. Implementación en
`tools/gui.py`, proyección en `bot/gui_model.py`. Tk/ttk sigue siendo el framework.

## Owners y persistencia

| Setting | Owner / condición de visibilidad | Persistencia | Default del formulario |
| --- | --- | --- | --- |
| Enabled | Occurrence, fila de la rutina seleccionada | `RoutineStep.enabled`, JSON v1 | true |
| Purchase SKIP tickets | MW occurrence; también prerequisite/investment de Stages Ads y Gold Farming Cycle | `config.monster_wave.purchase_skip_tickets` | false |
| Continue with nonblocking inventory full | Mismos consumidores de MW | `config.monster_wave.continue_when_nonblocking_inventory_full` | false |
| Ethereal Boots, Chest, Gloves, Helmet, Pants | Equipment relief de MW, Stages, Gold y WB | `config.equipment_sell.ethereal_types` | checked |
| Ethereal Earrings, Necklace, Ring, Weapon | Mismo equipment relief | mismo campo | unchecked |
| Ethereal Enhance | Mismo equipment relief | `config.equipment_sell.ethereal_enhance` | false |
| WB eligibility | Sólo World Boss occurrence | `config.world_boss.eligibility` | DAILY_QUEST |
| Resource snapshot | Rutina completa, sin depender de la fila seleccionada | `RoutineSpec.resource_snapshot_mode`, JSON v1 | BEFORE_CHARACTER_ROTATION |
| Routine name / selected library entry | Biblioteca de rutinas | `RoutineSpec.name` / `selected_id`, JSON v1 | Presets existentes |
| Characters | Request de Run Session; Sweep usa su ALL 28 existente | Request en memoria, no rutina | 28 |
| Debug | Visibilidad de eventos del request | Request en memoria | false |
| Appearance | Application, siempre disponible | `runtime/gui_preferences.json` | Light si falta/es inválida |

Los defaults de formulario se conservan de los dataclasses actuales. Una occurrence
sin overrides sigue heredando los defaults del runtime; Apply crea una decisión
explícita para las secciones que consume. La tabla describe controles GUI;
`continue_on_unavailable` sigue siendo un campo v1 existente, sin añadir un control.

## Auditoría causal y layout

El panel anterior mostraba venta, ambos settings MW, WB eligibility y Resource
snapshot simultáneamente. Apply construía MW + equipment_sell para cualquier flow,
incluido Black Market. Sólo agregaba eligibility cuando el flow era WB. La propiedad
de rutina de Resource snapshot ya era correcta en JSON, pero su placement era Step
Settings. No existía scroll en ese panel. No existía preference de appearance.

Ahora Routine Editor agrupa selector/New/Duplicate/Rename/Save Routine/Delete,
lista ordenada y acciones Enable/Disable, Up/Down, Remove, Add flow. A su derecha:

- **Step Settings = selected occurrence**. El título identifica posición y nombre.
  Se reconstruye al cambiar selección. BM, Mailbox y otros flows sin consumers
  configurables muestran `No configurable settings for this step.`; Apply está
  deshabilitado. WB muestra eligibility y su equipment relief, nunca MW. MW muestra
  sus dos decisiones y equipment relief, nunca WB. Stages y Gold mantienen los
  consumers MW/equipment que sus builders componen, identificados como prerequisite
  o investment. No se infiere gameplay nuevo desde los nombres.
- **Routine Settings = whole routine**. Resource snapshot en panel propio.
  Cambiarlo modifica el borrador; Save Routine persiste, como antes.
- **Application Settings = appearance**. Pestaña Application independiente.
  Light/Dark se aplica inmediatamente y se persiste al seleccionar.
- **Character State** independiente del editor, con Sweep — All 28 como acción de
  mantenimiento y el mismo progreso/Stop Safely global.

Los dos panels de settings usan Canvas + scrollbar ttk vertical, rueda local y
Page Up/Down con foco en el viewport. El ancho sigue el viewport y las notas se
ajustan. Apply queda fuera del scroll. La lista de steps y la tabla mantienen
scroll horizontal/vertical. No se depende de maximizar la ventana.

## Apply, v1 y configs repetidas

Apply modifica exclusivamente las secciones configurables de la occurrence que
describe el formulario. No aplica si la selección ya cambió antes del evento del
formulario. Save Routine persiste el borrador. Cambiar de step descarta ediciones
no aplicadas, explicado junto a Apply; no hay autosave silencioso. Reorder y
Duplicate conservan el config de cada occurrence. Los overrides legacy ajenos a un
formulario se retienen sin añadirlos a otros flows ni eliminar datos existentes.
No cambia schema v1 ni su recuperación de configs corruptas/Basic Gold.

**Rutina normal + BEFORE_CHARACTER_ROTATION conserva su mecanismo productivo**:
al final de cada personaje, Rotation abre su Quick Menu; el collector observa
Lapiz/Dark/Light/Nature/K Coins, persiste un snapshot completo y luego Rotation
abre Character Select. No hay una apertura QM adicional. OFF continúa desactivando
el collector. No se modificaron `ProductiveRuntime`, `StandardRotation`, Session,
reader, SQLite ni policy WB en esta pasada.

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
