# Review OpenCode/Muse — checkpoint de estabilización

Fecha: 2026-09-07. Review arquitectónico y de correctness terminado, fixes integrados y validación hardware-free verde. **Checkpoint propuesto, todavía sin commit ni push; requiere autorización del usuario.** Structured Observability no comenzó.

## Unidad de review y preservación

Base verificada: `45f6edee20db8fc05831ca8c27ca22049936d42a`, branch `maintenance/opencode`. `main`, `maintenance/opencode` y `origin/main` local conocido apuntaban al mismo hash. Se revisaron `git diff HEAD` y los untracked directamente: al entrar, 36 tracked modificados + 22 archivos untracked, staged vacío y sin conflictos. No se hizo fetch; la referencia remota conocida no prueba el estado remoto actual.

Se preservaron el lote ajeno, `wip/session-report-codex`, la adquisición portal y la adquisición de identidad. No hubo checkout, reset, restore, clean, stash, merge, rebase, commit, push ni input físico. Los cuatro scripts auxiliares raíz permanecen intactos y fuera de la propuesta de commit.

Estado posterior: el checkpoint revisado quedó consolidado en `fc66d60` y Structured Observability v1 en `95c6bd6`. Las propuestas de commit y referencias a trabajo pendiente que siguen son el registro histórico de esta revisión; la fase actual está en `docs/FAILURE_EVIDENCE_V1.md` y `ROADMAP.md`.

## Clasificación del lote

| Bloque | Contenido revisado | Resultado |
| --- | --- | --- |
| Rotation | Sentinel `+`, geometría 3 columnas, predecessor, selección dinámica y límites de búsqueda | ACCEPTED. Coarse→fine sí está implementado: 2 swipes fuertes y hasta 4 finos. La autoridad terminal sigue siendo el sentinel. |
| Portal | Probe on-demand Heaven/Hell/Guild, assets y X calibrada, settle, hook y composición | MUST FIX cerrado: frescura, fallos después del input y cancelación. Se conserva la separación percepción/policy/ejecución. |
| VerifiedTransition | Precondition, waits, grace, guard de retry y recovery | MUST FIX cerrado: estabilidad de resultados tardíos y frescura respecto de la última espera; ningún error del hook habilita input con evidencia previa. |
| World Boss / Auto Battle | Harvest crudo, secuencias y spacing, clasificación temporal, visibilidad, timer y Raid Complete | MUST FIX cerrado: guard fresco/visible, UNKNOWN post-tap no fatal, precedencia de Raid Complete y cancelación. No se cambió la policy de participación. |
| Daily Quests | Contrato Lobby, selección de tab, Claim All y progress reward | MUST FIX cerrado: un frame repetido/regresivo no permite otro tap ni confirma Daily. Retry limitado por `navigation_timeout`, **6 s default**, no los ~15 s del brief. |
| Summon Pet Daily | Manage, Epic/Premium, doble tap HIL, outcomes, relief y reentrada | MUST FIX cerrado: predicados completos en navegación/cierres y espera de selector residual; se preserva el doble tap intencional. |
| Equipment relief | Separación retorno a Transmute / espera por desaparición Ethereal | ACCEPTED. La espera exige Transmute correcto y guard ausente, es pasiva y bounded por 15 s; ningún input nace de un contexto incompatible. |
| Meteor Full | Catálogo, detector global, asset, acción No, outcome no fatal y evaluator | ACCEPTED. Sólo caller World Boss y rama negativa; no existe relief positivo ni farming nuevo. |
| Percepción Pet | ROI superior estable sin contador y manifest | ACCEPTED. El cambio semántico del manifest es exactamente dos positivos `8(Open)` añadidos: 48→50, sin quitar ni relabelar los anteriores. El resto del diff JSON es formato. |
| Integración | Registry, normalización, contratos de sesión y acciones | ACCEPTED. Guild directo desde Lobby está verificado; ensurer y Rotation comparten `DEFAULT_QUICK_MENU_POLICY` y el allow-list vigente de cinco contextos. |
| Docs y tests | Contratos/documentación stale, pruebas añadidas o reescritas | SHOULD CLEAN AT CHECKPOINT cerrado en el alcance descrito abajo. |

## MUST FIX — corregidos

1. **Daily podía repetir con la captura detenida.** `_wait_for_daily_tab()` llamaba `observe()` sin validar secuencia. Se reprodujeron múltiples taps desde el mismo frame y aceptación de un Daily más viejo que el baseline. Ahora cada secuencia autoriza como máximo una evaluación; duplicados/regresiones consumen espera sin input. UNKNOWN/AMBIGUOUS permanecen pasivos; otro contexto resuelto aborta. Claim All y reward siguen single-attempt.

2. **Portal podía hacer un segundo dismiss usando un CONFIRMED viejo.** `_settle()` conservaba ese resultado cuando la fuente repetía frames o fallaba. Ahora invalida el permiso; sólo una confirmación fresca al cierre del settle autoriza otro dismiss. Si falla el input o la primera observación posterior, el error ya no se presenta como “no hubo recovery”. El hook propaga errores y cancelación; un retry productivo posterior exige otra observación fresca. Black Market y World Boss conservan `CANCELLED` cuando la transición interrumpe por cancelación.

3. **VerifiedTransition podía saltarse `stable_for`.** Un match aislado post-grace, al salir del retry guard o después de recovery podía producir éxito inmediato. Ahora esos caminos revalidan estabilidad mediante espera pasiva bounded por el timeout nominal; perder la condición termina conservadoramente sin repetir input. La frescura post-grace se compara con la última observación de las esperas, no sólo con el frame anterior al tap. La normalización de contexto también conserva su espera estable después de recovery.

4. **Auto Battle podía provocar un fallo auxiliar o un tap sin control visible actual.** El baseline inmediatamente post-tap se clasificaba como `CONTEXT_MISMATCH` por base ausente, incluso con Raid Complete presente. Ahora UNKNOWN/AMBIGUOUS es inconcluso no fatal y el overlay tiene prioridad; sólo un contexto resuelto incompatible conserva mismatch. El guard debe superar la última secuencia del harvest y el detector confirma otra vez la visibilidad del control antes del input. La cancelación del re-harvest conserva `CANCELLED`. No se modificaron ventanas, mediana ni thresholds OFF/ON; la clasificación sigue siendo auxiliar y hay como máximo un tap productivo por batalla.

5. **Summon aceptaba una base correcta bajo popup como postcondición.** El helper basado en strings podía completar el cierre de Insufficient Gold mientras el popup seguía presente, o invocar relief bajo otro popup de Combine. Se reemplazó por intents y predicados semánticos completos, con guard antes de input y desaparición real de obstrucciones. La evidencia parcial del shell de Summon espera pasivamente hasta disponibilidad confirmada. Después del segundo tap, un selector residual de la ruta elegida sólo consume espera, nunca habilita más aperturas.

Los tests negativos nuevos reprodujeron los fallos principales antes de los fixes. El test de integración HIL de Summon usa el `RuntimeObserver.wait_until` real sobre frames simulados y verifica explícitamente que no exista observación entre selector, settle 0.25 s y `1(Open)`.

## SHOULD CLEAN AT CHECKPOINT — realizado

- Eliminados métodos privados duplicados/sombreados de Summon y Daily, el protocolo Pet copiado sin uso en Daily, imports repetidos y el traceback de debug directo de Summon. Se reutilizan las constantes de catálogo y se corrigió el nombre del predicado Lobby de Daily.
- La regresión de sesión Daily ahora consume `DailyQuestsFlow.contract`, en lugar de escribir a mano el contrato que pretendía verificar. El caso incompatible de tab usa el frame contradictorio real del fixture; el caso de desaparición estable de claims vuelve a tener su propio test.
- Los dobles Ethereal verifican condición y secuencia estrictamente posterior a la navegación. El test de persistencia portal aporta frames durante todo el settle, en lugar de obtener permiso de retry por agotar el fixture. El chequeo de capas distingue la palabra `Hell` del término genérico `shell`.
- Corregidos registry de siete flows, retry Daily, completion Summon, estado de calibración portal, cifras de validación y orden posterior en hot context/arquitectura/roadmap. El plan pre-Astra se preserva como documento operativo histórico; sus cifras no sustituyen esta revisión.
- `git diff --check` sin errores; whitespace de `tests/test_session.py` corregido. No hubo refactor preventivo general ni cambios de estilo masivos.

## ACCEPTED / INTENTIONAL DESIGN

- **Summon selector → 0.25 s → `1(Open)` directo**, sin observación intermedia, tanto inicialmente como tras relief. Daily se decide en Manage; no se vuelve a exigir su persistencia ni desaparición en Summon. Completion usa resultado real + cierre + Summon limpio estable. Las docs anteriores exigían una desaparición que el diseño HIL vigente ya no consumía.
- Raid Complete es autoridad por overlay, incluida base UNKNOWN. World Boss no depende internamente de Daily; Auto Battle y timer son auxiliares. Un timer inconcluso conserva fallback bounded de 90 s y después exige Raid Complete, sin éxito supuesto.
- Rotation no identifica personajes ni cuenta tarjetas. El `+` confirmado define el predecessor; la selección se verifica en esa tarjeta. No se reintrodujo `ObservedScroll` como prueba de bottom. Sus cambios de perfil quedan preservados como tooling/general primitive sin consumidor terminal de Rotation.
- Equipment separa navegación de guard Ethereal; Meteor conserva únicamente rechazo No verificado, sin reintentar Start después del outcome de negocio. El retry físico de un No ignorado sigue bajo el guard fresco de `VerifiedTransition`.
- Los cambios de `ActionExecutor` sólo proyectan intents a geometría; flows no hacen CV ni ADB. El probe portal no entra a Perception/ContextResolver. No se modificó la policy de SessionRunner ni el orden de los siete flows.

## FOLLOW-UP LATER

- Positivo live del sentinel en columna 3 todavía ausente; geometría cubierta por tests. El fix coarse→fine existente se conserva, sin tuning adicional ni inferir robustez absoluta de un solo recorrido.
- Recovery portal tiene cobertura parcial: `VerifiedTransition` y normalización de contexto. No se migraron los `wait_until` crudos de otros flows sin un failure concreto. La creación repetida de helpers/probes y la compatibilidad con dobles antiguos no justifican un refactor ahora.
- La señal de control visible/oculto de Auto Battle tiene evidencia acotada; no se amplía su generalización sin adquisición. No se modificó el motor temporal ni se redujeron negativos.
- Curación futura de raws portal/identidad. El manifest portal aún referencia `artifacts/portal_notification_acquisition/`; **no purgar** esos raws. Identidad conserva los 84 frames y GT externo; no se implementó reconocimiento.
- Structured Observability v1 → Failure Evidence v1 → SessionReport → GUI funcional mínima → Character Identity mínima → Eligibility mínima → reevaluar milestone. Arena fuera de alcance.

## Evidencia de validación

| Validación | Resultado |
| --- | --- |
| Colección del árbol inicial, antes de agregar regresiones | 1444 tests; la cifra reportada 1439 y la cifra 1430 de CONTEXT estaban atrasadas |
| Suite hardware-free final, una ejecución completa | **1464 passed**, 257.47 s; sin skipped ni hardware |
| Evaluación productiva incremental | **404 × 77 = 31.108 pares**, todos cache hits válidos; 404/404 bases y overlays correctos, wrong=0, ambiguous=0 |
| Portal, adquisición | **17/17**: 11 positivos y 6 negativos; los 17 también resuelven sus bases/overlays compatibles en la percepción productiva |
| Portal, corpus completo preservado | **603/603 ABSENT**; máximo negativo `0.489071965`, bajo absent `0.65` y confirm `0.80` |
| Sentinel | **15/15**: 5 positivos y 10 negativos con los márgenes existentes |
| Meteor / Pet Epic / Auto Battle | Regresiones perceptivas y de runtime incluidas en suite; sin recalibración durante este review |
| Hygiene | AST sin definiciones duplicadas en el lote Python revisado; `git diff --check` limpio |

Los contadores individuales del evaluator incluyen landmarks compartidos/observaciones subthreshold y un landmark Fuse ausente durante animación. Eso no equivale a fallo del estado compuesto: los 404 estados y overlays son correctos. No se declara “cero falsos positivos individuales”.

Comandos reproducibles desde la raíz:

```powershell
./tools/agent_run.ps1 pytest -q
./tools/agent_run.ps1 tools.production_perception_evaluation --output artifacts/checkpoint_review/production-perception.json
./tools/agent_run.ps1 artifacts.checkpoint_review.offline_audit
git diff --check
```

El último comando Python es auditoría local temporal, preservada bajo `artifacts/checkpoint_review/`, no tooling productivo versionable. Allí quedan `production-perception.json`, `on-demand-perception.json` y `validation.json` con hashes del código validado.

### Recorrido live reportado: 28 personajes con corte único por sentinel

Confirmación humana del usuario durante este review: **“fue un 28/28 cortado unicamente por el sentinel”**. Esto corrige la descripción previa de “28/28 sin interrupciones”.

Los logs disponibles son compatibles con ese recorrido retomado:

- `logs/20260906T202031.522019Z_session_ab005956.log`: sesión configurada en 28, **63 flow.completed** (9 × 7 flows), 8 advances completados; Rotation falla en índice 9 con `sentinel_not_found_after_max_swipes`.
- `logs/20260906T213449.182850Z_session_fb6320f8.log`: continuación configurada en 19, **133 flow.completed** (19 × 7 flows), 19 advances y `session.completed`.
- Hay un 28/28 ininterrumpido anterior, en `logs/20260905T032040.706120Z_session_1f9b6259.log`, de ~1 h 25 min; antecede al cierre de este lote.

No se infiere identidad, destino de navegación humana ni cierre del ciclo desde estos contadores. El código no está fingerprinted en esos logs, por lo que el recorrido previo no valida automáticamente los fixes de este review. No se ejecutó smoke físico durante esta sesión.

## Untracked raíz: clasificación y destino propuesto

| Archivo | Clasificación | Propuesta |
| --- | --- | --- |
| `check_eval.py` | Inspección ad hoc de un JSON local; path absoluto y esquema de evaluación específico | Preservar local; excluir del commit |
| `fix_tests.py` | Rewriter puntual de tests, ejecuta escrituras al importarlo; no es herramienta general | Preservar local; excluir del commit |
| `test_live.py` | Probe físico antiguo con rutas/identificador de dispositivo y imports privados ya obsoletos; lifecycle sin finally | No ejecutar ni versionar; preservar local |
| `test_wait.py` | Variante diagnóstica física con los mismos problemas de portabilidad/lifecycle | No ejecutar ni versionar; preservar local |
| `Kritika_FarmBot_Plan_Preparacion_Codex_Astra.md` | Checklist operativo histórico solicitado como contexto | Incluir intacto, sin tratar sus cifras como estado actual |

No se encontraron consumidores de los cuatro scripts raíz en código/tools/tests. `pytest.ini` limita la colección normal a `tests/`; los scripts físicos no se importaron ni ejecutaron. Excluirlos implica que seguirán visibles como untracked después de un eventual commit salvo una decisión posterior de archivo local. No se promete tree limpio mientras se preserven en la raíz.

## Contenido exacto del checkpoint propuesto

Un commit local: **`fix: stabilize rotation, obstruction recovery and daily flows`**.

Incluir el lote completo revisado más los fixes y docs del review: **59 archivos**. No incluir los cuatro scripts auxiliares, `.env`, `AGENT_LOCAL.md`, logs, caches, `screencaps/`, `artifacts/` ni identidad. Los assets runtime y manifests curados sí forman parte del checkpoint.

```text
ARCHITECTURE.md
CONTEXT.md
Kritika_FarmBot_Plan_Preparacion_Codex_Astra.md
ROADMAP.md
assets/ui/character-select-create-plus-template.png
assets/ui/landmarks/meteor-inventory-full-prompt-current.png
assets/ui/portal/portal-dismiss-x-wide-current.png
assets/ui/portal/portal-dismiss-x-wide-guild.png
assets/ui/portal/portal-dismiss-x-wide-hell.png
bot/action_executor.py
bot/auto_battle.py
bot/black_market_flow.py
bot/catalog.py
bot/character_select_layout.py
bot/character_select_scroll.py
bot/create_character_sentinel.py
bot/daily_quests_flow.py
bot/equipment_combine_relief.py
bot/flow_registry.py
bot/obstruction_recovery.py
bot/perception/__init__.py
bot/perception/pet_summon.py
bot/perception/specs.py
bot/portal_notification.py
bot/productive_runtime.py
bot/rotation.py
bot/semantic_actions.py
bot/summon_pet_daily_flow.py
bot/temporal_observation.py
bot/verified_transition.py
bot/world_boss_flow.py
datasets/character_select_sentinel_manifest.json
datasets/meteor_inventory_full_evidence_manifest.json
datasets/pet_summon_semantic_manifest.json
datasets/portal_notification_evidence_manifest.json
docs/OPENCODE_MUSE_REVIEW.md
tests/test_action_executor.py
tests/test_auto_battle.py
tests/test_black_market_flow.py
tests/test_catalog.py
tests/test_character_select_layout.py
tests/test_character_select_scroll.py
tests/test_create_character_sentinel.py
tests/test_daily_quests_flow.py
tests/test_equipment_combine_relief.py
tests/test_local_cv_perception.py
tests/test_meteor_inventory_full_perception.py
tests/test_perception_specs.py
tests/test_pet_summon_perception.py
tests/test_portal_notification_probe.py
tests/test_portal_obstruction_recovery.py
tests/test_rotation.py
tests/test_session.py
tests/test_summon_pet_daily_flow.py
tests/test_temporal_observation.py
tests/test_verified_transition.py
tests/test_world_boss_flow.py
tools/production_perception_evaluation.py
tools/semantic_slice_evaluation.py
```

No quedan MUST FIX abiertos de este review. La propuesta está lista para autorización; no incluye merge, push ni inicio de la siguiente fase.
