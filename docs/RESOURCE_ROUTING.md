# Resource routing — contrato actual

`IMPLEMENTATION_CONTRACT`. Fuente única de policy/composición de recursos y sus límites productivos. UI física/caller/Back: [GAMEPLAY_GT](GAMEPLAY_GT.md); estado caliente: [CONTEXT](../CONTEXT.md). La [reconstrucción](POST_V1_RESOURCE_ROUTING_RECONSTRUCTION.md) es procedencia histórica, no plan de ejecución.

## Ownership y policy aceptada

- Board reader/snapshot describen cinco balances/límites por identidad: Brawler's Badges, Weapon Material, Hero Weapon Material, Bronze y Silver Keys. Consenso fresco después de la barrera del caller. El rojo local puede probar presión sin OCR cuando no hace falta aritmética; ausencia/inconclusión conserva OCR, y Weapon exacto se conserva si hace falta proyectar Hero. No predicen rewards ni capacidad Gold.
- `plan_resource_route` es puro: snapshot + facts externos explícitos → pasos simbólicos. Entrada inclusiva Bronze ≥400, Silver ≥450, Weapon ≥800, Hero ≥800; presión dura probada también participa. La conversión determinista 40→10 puede justificar Craft alrededor de Materials. Receta/capacidad Equipment son facts de ejecución, no prerrequisitos ocultos del planner.
- Umbral decide visitar, no cuánto drenar. Craft drena Hero hasta <49, Materials Weapon hasta <40 y Keys hasta NO_MORE_PROMOTIONS, con facts frescos y budgets. Materials paga Keys primero aunque no cruce umbral; Keys solo no paga General. Sin viaje justificado, no se abre Trading para diagnosticar Gold; Gold-full oculto por sí solo no bloquea MW.
- Executor J consume el plan una vez. Cada capacidad conserva sus guards/efectos: Craft receta/moneda/cantidad/decremento, Trading panel/row y efecto, Treasure Gold antes de cada apertura y stop antes de Karats. No hay contabilidad simulada, replan ni compras premium implícitas.
- Keys prefiere Silver→Gold cuando tradeable y luego Bronze→Silver. Budget deriva de facts frescos; Silver→Gold OUTPUT_FULL conserva el pending exacto. ACK requiere alert fresco y Trading/Keys limpio; Treasure drena Gold y permite un solo retry del pending. Segundo OUTPUT_FULL falla cerrado.
- Craft con Materials: `MW → Craft → Quick Menu → Trading → X → Craft → Back → MW`, con Craft antes/después según plan. Craft+Keys sin Materials restaura MW antes de Trading. Gold-full diferido espera restaurar MW y usa `MW → Quick Menu → Treasure → Back → MW → Quick Menu → Trading` para reintentar una sola vez la misma operación pendiente. No encadenar otra BASE desde Craft perdiendo el caller.
- Capacidad Equipment se observa una vez por visita Craft antes del primer craft (`Craft → Quick Menu → Equipment Inventory → lectura fresca de capacidad → Back → Craft`); cero slots produce EQUIPMENT_CAPACITY_BLOCKED. Relief de ese CraftStep debe usar el blocker directo conforme a GT, conservar request y volver a Craft; no repetir board/planner/J. No es autorización para ir de Craft limpio a Combine.
- Equipment composer: Combine una vez; retry del request con contexto fresco; si sigue full, Sell sólo con autorización+candidato explícitos; último retry sólo tras venta probada. Sin Sell plan productivo MW, se detiene sin vender. Socket conserva su operación/guards propios. El caller aporta ruta/retorno; relief no absorbe policy del juego.

## Estado implementado frente a wiring productivo

Inspeccionado sobre HEAD `22c213a` + cambios locales MW/L2 (sin declararlos checkpoint).

| Parte | Estado real y límite |
| --- | --- |
| Board / planner / J / runner standalone K | Componentes existentes. K ofrece acquire/plan/prerequisites/full-one-shot; su composición inyectada no prueba callbacks productivos completos |
| L1 productivo | `_build_productive_monster_wave` conecta ProductiveMonsterWaveFlow, A1, planner, J, Craft y wrappers Keys/Materials/Treasure. Handoff RESOURCE_BOARD_PENDING fresco → adquisición/plan una vez → cierre board → J como máximo una vez → hub → resume del mismo request. Plan vacío no fabrica trabajo. Builder puede caer al flow bare ante error de wiring |
| Plan no ejecutable | K standalone detiene unresolved sin cerrar board. L1 actual, tras adquirir/cerrar board válidos, omite J para NO_PREREQUISITES, INSUFFICIENT_OBSERVABILITY o CONTRADICTORY y continúa salida/resume. No describir ambos callers como fail-closed idénticos ni confundir estos estados del planner con UNKNOWN del resolver |
| L2 local | Resume reacciona al popup Equipment/Socket, como máximo una vez por tipo, sin orden fijo ni segunda preparación; cada retry conserva daily. Hay pruebas dirigidas escritas, pero este reset no las ejecuta y la integración física no está cerrada |
| Craft local | Handoff Quick Menu usa source/snapshot verificado; reader agrega diagnóstico y baja a 0.80 la confianza de Weapon cost. Identidad sigue acoplada a OCR de título/rate/expert y datos de tres familias: primera divergencia actual |
| CraftStep full | Composer conectado localmente, `sell_plan=None`, retry sólo de ese paso. **Entrada no implementada**: `enter_combine` lanza `craft_combine_entry_not_established`. El return plan inerte aún apunta a MW; contrato requerido es volver a Craft antes de continuar. No se considera ruta productiva lista |
| Keys productivo | `_read_key_facts` falla `fresh_key_facts_unavailable`; `_execute_key_trade` devuelve `keys_adapter_not_established` |
| Gold recovery productivo | `_drain_gold_keys` devuelve `drain_not_established`; `_acknowledge_gold_full` devuelve `ack_not_established`. Standalone disponible no elimina estos huecos |
| Materials productivo | `_locate_material` devuelve TARGET_UNKNOWN / `materials_adapter_not_established`; `_read_material_fact` falla `fresh_material_fact_unavailable`; `_execute_material_trade` devuelve `materials_adapter_not_established` |
| Sell | Runtime/composer disponibles; MW no suministra candidato/plan autorizado, por lo que no vende |

Referencias de implementación: [flow_registry](../bot/flow_registry.py), [ProductiveMonsterWaveFlow](../bot/monster_wave_productive.py), [J/navigation](../bot/monster_wave_resource_route.py), [K](../bot/monster_wave_standalone.py), [planner](../bot/resource_route_planner.py), [Craft reader](../bot/craft_reader.py). Los tests de [MW productivo](../tests/test_monster_wave_productive.py) y [ruta](../tests/test_monster_wave_resource_route.py) describen composición con dobles; no convertirlos en prueba de integración física/callback real.

## Trabajo inmediato

P0 identidad Craft segura y economía específica de operación → validación afectada → un smoke MW autorizado → primera divergencia siguiente. Completar los adapters anteriores y caller Craft conforme a GT dentro de ese ciclo, sin framework nuevo. L2 no está cerrado por existir el composer. Run Session Daily/eligibility es un bug de binding separado, descrito en CONTEXT. Fill All con Gold insuficiente no bloquea esta integración.
