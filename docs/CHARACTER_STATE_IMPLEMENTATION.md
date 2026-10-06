# Character Identity + Persistent Character State — informe de implementación

Baseline `fe774abcef3a636c138028717a0d2a0b514c5e6f`, rama
`rebuild/stable-baseline`. Identity, State, Sweep y GUI forman un único checkpoint
causal; cierre y validación del índice en [CHARACTER_STATE_CHECKPOINT](CHARACTER_STATE_CHECKPOINT.md).
Los apartados de adquisición conservan sus resultados y límites originales.
Open Pets no implementado.
Trabajo independiente previo preservado. Fecha live: noche local2026-10-05,
timestamps UTC2026-10-06.

## Identity

Conjunto cerrado de28 nombres personales y28 IDs explícitos permanentes en
`bot/character_identity.py`. Los IDs no derivan de posiciones, índices ni OCR.
Nombre canonical y display/class son metadata.25 identidades ordinarias requieren
match exacto OCR≥0.95. Tres Unicode requieren template de tinta blanca del nombre
y discriminación independiente del sufijo; ambos scores≥0.90 y margen≥0.06.
No hay fuzzy matching ni ML. Alias OCR sólo nomina, nunca acredita.

Se compararon glifo/full-name y margen completo: el prefijo DRAKEN compartido
reducía el margen live sin aportar identidad. El discriminador del sufijo conserva
full-name agreement y separa 一BK/二DB/三BB. Tres máscaras pequeñas se calibraron
con el primer frame por personaje; los otros dos permanecen validation.
Provenance: `datasets/character_identity_templates.json` y corpus original
`datasets/character_identity_manifest.json`.

Resultado: **84/84 frames,28/28 identidades,0 wrong,0 UNKNOWN**.
Calibración28, validation56; acquisition histórica compartida, no sesiones
independientes. Tests cubren variantes corruptas, conflicto OCR/píxeles, fallback,
UNKNOWN y negativos contextuales. Evaluación existente verificó494 contextos
noLobby y18 context negatives, sin false accept;19 Lobby adicionales no están
etiquetados y no cuentan como identity acceptance. Live Demon Blade correcto con
`DRAKEN二DB`, después de confirmar físicamente el título en Character Select.
El primer smoke dejó UNKNOWN explícito y no escribió facts para ese scope.

## DB y provenance

Ruta local: `runtime/character_state.sqlite3`, ignorada junto a WAL/SHM por `/runtime/`.
Schema `PRAGMA user_version=1`, inicialización0→1; versiones futuras/archivo corrupto
se preservan y rechazan. SQLite FK, WAL, synchronous FULL, lock y transacciones
atómicas para actualizaciones concurrentes. No dataset/DB real versionado.

- `characters`: character_id, canonical_name, display_name, identity_source.
- `operational`: Ads count/epoch/status/source/update/attempt; WB cycle,
  participated, previous reward, daily quest y provenance.
- `resource_snapshots`: cinco enteros completos, observed_at/source, historial;
  latest reliable por identidad es lo mostrado.
- `fact_history`: valor/source/observed_at/effective_at/epoch/cycle.
- `reset_clock`: anchor UTC, raw countdown, observación/source, próximos daily/WB,
  ciclo/open y precisión.

DB nueva a mitad de epoch conserva UNKNOWN. Backfill explícito del log publicado
`20261005T234827.311080Z_session_27ae46d4.jsonl` acreditó26 scopes nombrados y
26 Ads0, con fuente SHA256
`be4cf35d6f919b7683bf61f153a9c399d4c2a68383118c694b35a6dfc86d9b89`.
No se rellenaron los dos scopes UNKNOWN por orden. Demon Blade recibió después
Video0 fresco; Burst Breaker permanece UNKNOWN hasta observación/reset.
Backfill rechaza ambiguity, epochs viejos y datos anteriores a un update conocido.

## ResetClock

Live `1d4h14m`, observado2026-10-06T02:15:52Z, cierre estimado
2026-10-07T06:30Z, synchronized reset2026-10-07T07:00Z.
Local -03:03:30/04:00. Siguiente daily reset2026-10-06T07:00Z.
Ultima lectura2026-10-06T02:41:19.864Z: `1d 3h48m`, mismo anchor.
Estado DB previo al Character Data Sweep:27 Ads0/1UNKNOWN (Burst Breaker),6 WBYES/22UNKNOWN,6 snapshots. Evidence:
`artifacts/world-boss-live/state-wb-main-after/20261006T021552_489434Z_03.png`.

El display es de minutos. Se normaliza observed_at+displayed remaining al próximo
límite de minuto y se agrega30min; precisión declarada60s, sin afirmar segundos
físicos. Ninguna hora local permanente. Nuevos countdowns recalibran absolute anchor,
absorbiendo desplazamientos estacionales. Entre ellos se proyecta daily24h y WB
aproximadamente3 días; eventos WB proyectados están marcados como tales.

Startup, GUI y lecturas operativas hacen catch-up. Runtime posee scheduler cancelable,
GUI timer Tk; cambian automáticamente los28 sin visitar personajes. Catch-up salta
múltiples resets al epoch más reciente. Daily entregaAds2; último30min cierra WB;
nuevo ciclo WB poneNO para todos, reabre y conserva historia. Validado con reloj
controlado y scheduler/Tk; no se esperó físicamente al reset nocturno.

Catch-up usa el boundary recalibrado: un adelanto ya cruzado aplica reset. Si una proyeccion prematura asigno2 antes del nuevo limite retrasado, ese valor queda UNKNOWN hasta reset/observacion fresca; las observaciones fisicas se conservan.

## Stage Ads

`stages.ad_selection`: cantidad fresca; Video0→0/source VIDEO0.
`stages.sapphire_effect` con aumento verificado→decremento bounded0..2.
`stages.daily_exhausted`→0; `temporarily_unavailable` y aborted recovery conservan
cantidad, registrando intento separado. UNKNOWN reward sin count previo sigueUNKNOWN.
Scopes no procesados no se modifican por failure/cancelación. Epoch actual0 puede
omitir navegación; reset invalida agotamiento anterior. GUI muestra count/status/time.

Smoke natural Demon Blade conVideo0:0 persistido, sin consumir Ads artificialmente.
Los seis rewarded históricos se reconstruyeron sólo tras count previo y efecto causal.
Decremento2→1→0/reset cubiertos directamente y por consumidor de eventos.

## World Boss

Un solo flow/activity con policy independiente. DAILY_QUEST preserva daily marker;
CURRENT_WB_NOT_PARTICIPATED usa ciclo actual y facts físicos; GENERAL preserva
comportamiento standalone general. Por occurrence, duplicación/save/reopen v1.
DB YES omite; DB NO/UNKNOWN permite intento hacia inspección fresca antes de Start.
UNKNOWN físico no autoriza raid. Guards Start/Auto/reliefs originales conservados.

Previous reward overlay semántico existente→NO actual/YES previous; numeric pair→YES;
dash pair→NO/NO previous. **La pareja completa adquirida está en World Boss main**,
no en Select Battle Mode, donde sólo se observó card/rank. No se inventó un damage
ausente del hub. Numeric live:610,522,681,814 damage yRank104; guiones y Previous
Rewards del corpus histórico están curados/reutilizados. Reader focal exige labels
completos, confianza≥0.95, pareja consistente; misses no significanNO.

`world_boss.raid_complete_verified` escribeYES/source RAID_COMPLETE inmediatamente
antes de Continue; cleanup posterior fallido no elimina el hecho. YES monotónico
dentro del ciclo; panel stale no lo degrada. Sólo nuevo ciclo puede resetearlo.
No se hizo nuevo raid porque los personajes naturales ya estabanparticipados.
La integración ejecuta happy raid hastaRaid Complete y provoca cleanup fallido para
demostrar persistencia causal. Daily Quest y reward anterior son columnas independientes.

## Recursos, trigger y overhead

ROIs normalizadas number-only (`bot/character_data.py`):

| Campo | ROI Lobby (x1,y1,x2,y2) |
| --- | --- |
| Lapiz | .075,.884,.125,.920 |
| K Coins | .150,.884,.211,.920 |
| Dark | .075,.954,.125,.995 |
| Light | .160,.954,.211,.995 |
| Nature | .245,.954,.296,.995 |

Caller noLobby adquirido desplaza x+.130. Geometría desdeframe.shape; Mao Coins
tercero superior está excluido. Parser estricto: enteros0/dígitos/comas agrupadas,
una línea/confianza≥0.95. Partial/unreadable conserva snapshot completo anterior.
Fallo informativo loguea y continúa; DB recursos nunca autoriza gameplay consumptivo.

OFF no ejecuta reader; BEFORE_CHARACTER_ROTATION default usa el frame delQM ya
abierto paraRotation, antes de Character Select. Hook runtime/Session genérico;
Rotation desconoce nombres/balances. No hay captura extra ni scan99 del collector.

| Personaje live | Lapiz | Dark | Light | Nature | K Coins |
| --- | ---: | ---: | ---: | ---: | ---: |
| Elemental Fairy | 50691 | 147 | 6609 | 145 | 193061 |
| Noblia | 27705 | 232 | 64 | 184 | 116892 |
| Steam Walker | 32540 | 12 | 132 | 151 | 67064 |
| Telumpel | 35573 | 93 | 91 | 168 | 119038 |
| Eclair | 8254 | 236 | 169 | 209 | 108029 |
| Demon Blade | 3766 | 455 | 50 | 24 | 121918 |

Smoke corregido3 personajes: focal OCR+persist0.165/0.160/0.186s.
QM-ready→persist telemetry0.379/0.364/0.429s (incluye instrumentación);
QM-ready→Character Select3.682/3.561/3.787s (incluye navegación existente).
Exactamente **una apertura QM por Rotation**. Cold OCR inicial standalone2.728s;
warm reader aislado0.112–0.113s. Productivo comparte engine existente.
Métricas en `artifacts/character_state_metrics.json`.

## GUI y live

Character State:28 filas, Ads count/status/update, WB participated/cycle/open,
cinco recursos y snapshot time. Scrollers, clock visible y actualización automática.
Step Settings: WB eligibility seleccionada por occurrence; Routine Settings:
Resource snapshot por rutina. Configs opcionalesv1 backward compatible; WB corrupto→DAILY_QUEST;
snapshot corrupto→OFF. Save/reopen/duplicate acreditados. RealTk construida/reabierta:
28 filas idénticas en `artifacts/character_state_tk_reopen.json`.

Smokes productivos con summary/reopen_equal y cleanup de source:

- `20261006T022645.130346Z_character-state_2de7b017`:3 chars/3 Rotation COMPLETED;
  primerDemon UNKNOWN preservado sin writes, Fairy/Noblia correctos.
- `20261006T023258.183097Z_character-state_6a60f0cc`:3 chars/3 Rotation COMPLETED;
  Steam/Telumpel/Eclair correctos, WB numeric YES, snapshot mismoQM.
- `20261006T024051.356464Z_character-state_08bf741e`:1 char/1 Rotation COMPLETED;
  Demon canonical correcto, WBYES, naturalVideo0→0, recursos correctos/reopen.
  Print final tuvoUnicode CP1252 después de runtime.closed/summary guardado;
  se corrigió ensure_ascii del reporte, sin repetir inputs ya exitosos.

Logs en `logs/`, capturas/summaries en `artifacts/character-state-live/`, todos
ignorados.16 pequeños crops curados y manifest/hash están en
`tests/fixtures/character_state/`; originales grandes preservados sin versionar.

## Validación anterior al cierre conjunto (procedencia)

- Seleccion final afectada: **629 passed,4 skips historicos**, 68.57s.
  `artifacts/character_state_final_pytest.txt`.
- Store ampliado despues con routing de Ads0/reset y facts WB independientes:
  **19 passed** (incluye los16 ya presentes en la seleccion final).
  Ultimo recheck store/data/WorldBossFlow tras cerrar la ventana global:133 passed.
  Countdown ilegible en DB sin anchor conserva clockUNKNOWN; no inventa cierre.
- Policy/flows WB y nuevos readers/store/GUI:151 passed; configs/routines/GUI72 passed;
  reloj/data/GUI55 passed. Son selecciones solapadas, no sumarlas como tests distintos.
- Corpus closed-set84/84; replay OCR real de16 crops y context negatives existentes,
  sin wrong identity/false accept. Evaluator de identidad existente completo:
  28 calibration+56 validation correctos,494 noLobby,18 extra context negatives.
- RealTk reopen28 filas identicas. Smokes productivos y SQLite reopen verdes.
- Suite amplia deliberada: **4333 passed,4 skips,26 failed**,936.29s.
  Dos fallos afectados corregidos: expectation de CharacterContext incluye stable ID
  y double WB construido sin constructor conserva compatibilidad sin policy.
  Recheck completo de grupos fallidos: **397 passed,24 failed**,146.38s.
  `artifacts/character_state_full_pytest.txt` y `character_state_full_failures_recheck.txt`.
- Los24 restantes son preexistentes:11 GUI funcional (Session forbidden y evidence
  legacy),1 catalog count,7 lobby-return detector counts,1 Pets count y4 seed helpers
  `_initial_lobby` eliminados anteriormente. Se reprodujeron cargando productive_runtime
  directamente de HEAD en memoria; los otros owners de esos contratos no tienen cambios
  del frente. Resultados en `artifacts/character_state_baseline_failures.txt`.
  Ese comparador produjo ademas un falso fallo de inspect.getsource al apuntar
  al archivo actual con offsets de HEAD; corregido usando copia HEAD en artifacts,
  recheck del unico test afectado:1 passed. No es fallo del bot/baseline.
  No se cambia gameplay ni tests ajenos para esconder estos fallos.
- `git diff --check` limpio; DB/logs/artifacts ignorados; staging vacio.

## Deuda física focal

- Balance0 visible de Quick Menu no apareció naturalmente; parser y límites
  probados, sin fabricar gasto. Comas/separadores, valores altos y pocos dígitos
  adquiridos durante Character Data Sweep.

Los tres Unicode y las visuales WB están cerrados por corpus/evidencia disponible;
no se exige otra adquisición para reconfirmarlos. Un timer histórico de baja
confianza conservaUNKNOWN y no calibra; la calibración actual usa lectura live fuerte.

## Character Data Sweep — cierre 2026-10-06

### Auditoría y composición

Antes existía `Resource snapshot: OFF/BEFORE_CHARACTER_ROTATION` dentro de rutinas
normales, pero GUI/Session rechazaban ejecutar una Session sin flows. No había una
acción accesible para refrescar los28 personajes sin gameplay.

Ahora **Character State → Character Data Sweep — All 28** inicia una
`SessionPlan.character_data_only` con ALL28 y lista de flows vacía. El request dedicado
no depende de la rutina seleccionada ni persiste una rutina artificial. Runtime
reutiliza resolver, scopes por stable ID, collector, store, Navigation y StandardRotation.
Fuerza captura sólo durante esa ejecución y restaura la policy normal al terminar.
Cada identidad se obtiene desde el snapshot de entrada de Rotation; el hook del
mismo QM guarda recursos antes de Character Select. No hay consulta Ads/WB ni
flow productivo. ResetClock conserva su ownership habitual.

UNKNOWN, identidad duplicada y snapshot incompleto nunca sobrescriben otra fila.
Las adquisiciones incompletas producen un resumen MANUAL_RESOLUTION y conservan
datos previos; la navegación conserva sus outcomes técnicos. Stop Safely conserva
snapshots completados, no toca personajes pendientes y limpia scope. GUI muestra
personaje/índice, resultado del snapshot y resumen final con counts/elapsed.

### Divergencia causal y reader

Primer intento GUI cancelado con Stop Safely tras la primera divergencia: Galaxy
Light42 se leía correctamente pero con confianza insuficiente;6 snapshots persistidos.
La adquisición posterior recorrió28 identidades/28 Rotations con23 snapshots y5
failures informativos, sin fallos técnicos. Las cinco capturas existentes demostraron
crop ajustado sobre números cortos (172/455/42/127); se curaron25 crops pequeños en
el manifest de replay. No se gastaron recursos para crear variantes.

El cambio local admite un único reintento OCR del mismo crop con margen negro
proporcional a su altura (0.16 por lado), sólo si la lectura original no es fiable.
Debe coincidir exactamente el texto y superar el mismo gate ≥0.95, entero válido
y una línea. No se relaja confianza, no se reemplazan unreadables por0 y no hay
captura ni input adicional. Failures guardan el frame ya disponible en artifacts.
El run final recuperó tres lecturas: Eilla Dark40, Demon Dark455 y Galaxy Light42.

### Aceptación desde GUI real

- Log: `logs/20261006T040349.033742Z_character_data_sweep_a15f2041.jsonl`.
- Run: `2c282440554f480a9d9a59c366650195`.
- Session: `406ad33e80154781a8b426898b1f27d2`.
- COMPLETED: **28 processed,28 unique identities,28 snapshots,28 Rotations,
  0 acquisition failures,0 technical failures**. Los tres Unicode resueltos live.
- Session345.545s; GUI349.2s incluyendo inicialización, equivalente a5:49.
- 28 aperturas útiles QM, cada snapshot antes de su propio Character Select;
  ningún flow productivo ejecutado. Código productivo igual al hash al iniciar el run.
- Mediana por personaje12.101s; reader+persistencia0.159s, total5.266s;
  navegación/Rotation sin reader mediana11.220s. Reader min0.127s/max0.465s.

`tools.audit_character_data_sweep` cotejó los28 stable IDs y nombres contra SQLite,
valores completos contra eventos, source_sequence contra el QM-ready fresco y
observed_at dentro del scope correspondiente. Timestamps UTC desde
2026-10-06T04:04:00.516085Z (Ice Warlock) hasta04:09:29.437445Z (Dark Valkyrie).
La Rotation28 volvió al primer personaje. Sin off-by-one, identidades stale,
contaminación cruzada ni fingerprints de cinco valores repetidos.

Después se cerró y abrió la GUI como proceso normal: Idle, sin memoria de Session,
tabla completa verificada visualmente de arriba abajo. Reopen SQLite independiente
conservó exactamente las28 filas/valores/timestamps. GUI queda abierta en Character State.

Artifacts locales ignorados: `artifacts/character-data-sweep/audit.json`,
`resources.csv`, `resources.md` (28 filas, cinco valores, canonical ID y timestamp),
`operational.csv`, `gui-reopen.json`, `pytest-final.txt`, `worktree-status.txt`.
La DB sigue en `runtime/character_state.sqlite3`, schema1; no se versionan datos reales.

### Sanity operativo, sin reparación forzada

Comparación exacta con `operational-before.json`: todos los facts Ads/WB, fuentes y
timestamps permanecen iguales. Epoch Ads2026-10-05T07:00Z, WB cycle1; no cruzó reset
durante la aceptación. **Ads0 en27, Burst BreakerUNKNOWN** sin historia causal segura.
Los26 del backfill tienen fuente LOG_BACKFILL del log histórico acreditado; Demon
Blade tiene VIDEO0. **WBYES en6**: Demon Blade, Eclair, Elemental Fairy, Noblia,
Steam Walker y Telumpel, fuente WB_PANEL. **Los otros22 permanecen UNKNOWN** sin
source/updated_at, no NO. El sweep no infiere participación desde Daily Quest ni
fuerza los28 YES esperados por el usuario. Dump operational conserva provenance por fila.

### Validación afectada y separación del trabajo

**241 passed en12.01s**, sin teléfono: Sweep, Session, runtime, Rotation, GUI
model/controller/entrypoint, collector/replay, store y routines. Incluye10 tests
directos Sweep y los gates del reintento focal. Cubre ALL28, no gameplay, una apertura
QM, orden snapshot→Select, atribución estable, UNKNOWN/unreadable/duplicado, cancelación,
preservación Ads/WB, summary y reopen. Replay real expandido a41 crops; no cambió el
resolver de identidad, por lo que se conserva el corpus84/84 acreditado.
`git diff --check` limpio; staging vacío. No se repitió la suite global cuyos24
fallos preexistentes se documentan arriba; no se alteró ese trabajo para ocultarlos.

Sweep añade `tests/test_character_data_sweep.py`, `tools/audit_character_data_sweep.py`
y25 crops al manifest existente. Extiende los owners actuales `bot/session.py`,
`bot/productive_runtime.py`, `bot/character_data.py`, `bot/gui_model.py`,
`bot/gui_controller.py`, `tools/gui.py`, `tests/test_character_data.py` y documentación.
Identity/store/Ads/WB y su wiring previo permanecen como trabajo Character State
sin commit; los ocho paths independientes listados abajo permanecen preservados.
No Open Pets, commit ni push. No deuda de adquisición bloqueante para Sweep; balance0
natural sigue como variante física pendiente del reader, con parser probado.

## GUI cleanup — 2026-10-06

Contrato/auditoría de todos los settings: [GUI/config vigente](GUI_CONFIGURATION.md).
El panel previo mezclaba venta, MW, WB y Resource snapshot, y Apply inyectaba
MW/venta en flows ajenos. Ahora Step Settings describe sólo la occurrence y sus
consumers reales; BM/sin config tienen empty-state, WB sólo eligibility/relief,
MW sólo sus decisiones/relief. Stages/Gold conservan sus prerequisites MW.
Routine Settings separa snapshot; Application contiene Appearance global.
Apply→draft/Save Routine→JSON sigue explícito, sin autosave. Scroll vertical local
en ambos panels y Apply fijo; editor y toolbar compactos para ventana reducida.

Character State conserva28 filas/valores/timestamps y acción Sweep. Headers
ordenan asc/desc con indicador, números/timestamps tipados, Character casefold,
WB NO/YES (asc) o YES/NO (desc), UNKNOWN al final en ambos sentidos y empates
por display/ID. Refresh mantiene sort; sólo mueve filas, sin writes ni cambio de
Rotation. Theme central Light/Dark con ttk clam y widgets clásicos, popdowns,
scrollbars ttk y diálogos propios. Preference en `runtime/gui_preferences.json`,
independiente de routines/SQLite; toggle inmediato y reopen persistente.

Rutina normal + BEFORE_CHARACTER_ROTATION sigue capturando los cinco balances al
final de cada personaje desde el mismo QM de Rotation, antes de Character Select.
Regresión nueva GUI request→run_routine→collector productivo→SQLite acredita modo
OFF/BEFORE, dos personajes y orden QM→snapshot→Select. Ningún owner productivo
fue modificado durante cleanup; se reutiliza la aceptación física previa.

Validación directa:25 tests nuevos verdes. Smoke Tk visible/reopen, 1100×760 y
760×560, escala actual~1.33465;19 capturas locales de editor/BM/MW/WB repetido,
rutina/scroll stress, State asc/desc/resources, refresh, progreso Sweep sintético,
Light/Dark, Application, Console/Report y diálogo. Reopen:28 filas idénticas,
Dark conservado, cero errores de callbacks. Selección completa: **231 passed en
20.02s** (25 nuevos incluidos, no sumar ambos conteos). Evidencia final:
`artifacts/gui_cleanup_df0f5e5c/audit.json` y19 PNG en esa carpeta; ejemplos
`dark_reduced_mw_top.png`, `dark_reduced_mw_bottom.png`,
`dark_repeated_world_boss.png`, `dark_character_state_numeric_asc.png`,
`dark_reopened.png`. `git diff --check` verde y staging vacío. No adquisición física
ni nuevo sweep; screenshots/DB backup/routines privadas bajo artifacts ignorados.

Separación del diff: Character State (identity/store/Ads/WB/readers/reset/collector)
y Data Sweep (Session/runtime/controller, audit/replay/stop) permanecen locales.
Cleanup añade `bot/gui_preferences.py`, `tools/gui_theme.py`,
`tests/test_gui_cleanup.py`, `tools/gui_cleanup_smoke.py`, `docs/GUI_CONFIGURATION.md`;
extiende `tools/gui.py` y `bot/gui_model.py` compartidos, adapta el seam de diálogos
de `tests/test_routines.py` y actualiza este informe/README. Los ocho paths
históricos independientes del apartado siguiente siguen preservados. Sin commit,
push, gameplay nuevo, Open Pets o cambios a GAMEPLAY_GT.

## Worktree anterior al checkpoint (procedencia)

Preexistente, preservado sin cambios del frente:

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

No se modificó flow_registry; su único hunk sigue siendo Summon Pet independiente.
Estado del frente antes de añadir Character Data Sweep, `git status --short`:

```text
 M .gitignore
 M ARCHITECTURE.md
 M CONTEXT.md
 M ROADMAP.md
 M bot/character_identity.py
 M bot/character_resources.py
 M bot/productive_runtime.py
 M bot/rotation.py
 M bot/routines.py
 M bot/session.py
 M bot/stages_daily_flow.py
 M bot/world_boss_activity.py
 M bot/world_boss_eligibility.py
 M bot/world_boss_flow.py
 M datasets/character_identity_manifest.json
 M docs/GAMEPLAY_GT.md
 M docs/RESOURCE_ROUTING.md
 M tests/test_character_identity.py
 M tests/test_ocr_extractors.py
 M tests/test_productive_runtime.py
 M tools/gui.py
?? assets/character_identity/
?? bot/character_data.py
?? bot/character_state.py
?? bot/world_boss_state.py
?? datasets/character_identity_templates.json
?? docs/CHARACTER_STATE_IMPLEMENTATION.md
?? tests/fixtures/character_state/
?? tests/test_character_data.py
?? tests/test_character_state.py
?? tests/test_character_state_gui.py
?? tools/backfill_character_ads.py
?? tools/character_identity_benchmark.py
?? tools/character_state_evaluation.py
?? tools/character_state_gui_smoke.py
?? tools/curate_character_state.py
?? tools/smoke_character_state.py
```

Este inventario corresponde al frente previo al checkpoint; la baseline indicada
es su parent. El cierre conserva fuera del commit los ocho paths independientes.
