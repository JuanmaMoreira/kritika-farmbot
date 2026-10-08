# Shared Meteorites — checkpoint A+B1+B2 (2026-10-08)

Parent publicado de origen: `ce44fe55ef0490e068f972b59e96c1e9a3c58350`.
Branch destino: `rebuild/stable-baseline`. Un único commit de feature, sin commit
auxiliar ni ref move manual. Hash publicado: consultar HEAD/tracking/remote del
branch después de cierre; el commit no se autorreferencia.

## Alcance y procedencia

Worktree `meteorites-hil` parte de ese parent y posee el diff causal Meteorites.
BASE/catalog/acciones/scopes, 31 assets, readers/detector, primitivas frescas,
procedimiento posicional de once, Routine Settings/schema/GUI y lifecycle Session,
fixtures portables/tests/documentación. Los hunks de wiring de owners compartidos
son exclusivamente Meteorites; Ads/MW/Equipment/fact_reader/flow_registry/summon_pet
independientes del principal no entran en el INDEX.

Integración: snapshot SHA256 de todos los archivos dirty/untracked del principal;
INDEX exclusivo validado y exportado sin .env/AGENT_LOCAL/DB/corpus ignorado.
Fusión three-way por archivo del working tree en copias revisables, conservando EOL
y hunks independientes; resolver sólo superposición de la misma evolución A→B2.
Stage del principal mediante patch cached del INDEX aprobado sobre el parent,
verificar árbol idéntico y commit normal en su branch. Ningún reset/clean/restore,
stash, force-push ni actualización externa de la ref estable.

## Acceptance conservada

| Fase | Cadena y límite |
| --- | --- |
| A | 3 Equip +3 Unequip, slots directos, transición fresca EMPTY↔OCCUPIED; retry único opt-in sólo no-efecto explícito |
| B1 |11+11, Flare primero, ancla15 única/reutilizada, cleanup10..1/centro y Set 1 |
| B2 |Telumpel11→Send Stamina COMPLETED→11→Set 1; Flare1/ancla14;0 retries/Ads/Rotation/compras |

B2 final Set 2 vacío/compartidos desequipados, Set 1 activo/originales preservados,
sin overlay/Loading. Setup26.411s, cleanup27.155s, coordinator9.606ms;
primitivas20.296s e I/O evidencia23.830s separados. Exportador corregido después de
Session COMPLETED desde evidencia existente, sin repetir inputs. Informes dueños:
[adquisición](METEORITES_HIL_ACQUISITION_20261008.md), [A](METEORITES_PHASE_A_20261008.md),
[B1](METEORITES_B1_20261008.md), [B2](METEORITES_B2_20261008.md).

## Contratos auditados

OFF no crea scope ni modifica secuencia. ON exige stable ID acreditado y setup
antes de pasos; cleanup después de todos los pasos normales antes de Rotation o
completion sin Rotation. Flow COMPLETED/no-work no libera entre pasos. Excepciones
berserker/demon_blade/kaiserin; burst_breaker participa; UNKNOWN no opera.
Stop Safely desde READY requiere contexto fresco seguro; segundo Stop aborta.
FAILED/UNKNOWN no autorizan cleanup ciego ni Rotation; cada nueva ejecución crea
scope/progreso nuevos y requiere preparación manual tras incertidumbre.
Las cinco precondiciones USER_GT se asumen; ningún auditor extra de inventario.
No acoplamiento a Send Stamina: sólo es el consumidor usado en el smoke.

## Corpus y validación

31 PNG runtime:128526 bytes. 28 fixtures focales +manifest:12804814 bytes;
hashes, ROIs y fuente registrados. Curados completos63 (260593985 bytes), raw527,
artifacts/logs/configs/DB/seriales/rutas personales y recorder exploratorio excluidos.
Manifests con referencias externas son procedencia/acceptance, no dependencias de
pytest. Evaluator63/63 y negativos513/513 de A se conservan; reproducirlos exige
corpus externo explícito y falla si falta, nunca se presenta como evaluación portable.

Consolidado worktree:1254passed/0failed/4skipped/41deselected,27.44s.
Auditoría sin exclusiones:1254passed/41failed/4skipped;37fallos por raw históricos
faltantes (35Lobby return/2Rotation),4harness llaman API _initial_lobby retirada antes
de Meteorites. Los4skips son QM Battle Mode/Guild de corpus local ausente.
Ninguna prueba Meteorites excluida. INDEX portable:1254passed/0failed/4skipped/41deselected,53.97s.
Primer arranque aislado:1166passed/88setup-errors por parent basetemp inexistente;
crear artifacts resolvió el entorno, sin cambio de código. El INDEX se revalidó verde.
Nodos exactos/selección en [manifest de validación](../datasets/shared_meteorites_checkpoint_validation.json).
`git diff --cached --check`, stat/name-status y staged diff completo son gates de publicación.

## Límites

No-efecto real todavía sin episodio live; recovery acotado probado offline.
QM shifted no habilitado por geometría Lobby; sprite/tier inferior/acción disabled
no adquiridos conservan UNKNOWN. Roster y Stop Safely validados offline, no nuevos
smokes físicos. REPEAT_CURRENT no implementado: scope del personaje podrá abarcar
varios ciclos; Arena/ToT/Stages Elite pendientes. Nueva baseline apta para iniciar
Arena como tarea posterior explícita, sin iniciar ese frente en este checkpoint.
