# Meteorites — Fase A, implementación 2026-10-08

Baseline `ce44fe55ef0490e068f972b59e96c1e9a3c58350`. Sin commit/push.
Trabajo local previo preservado. Adquisición y worktree `meteorites-hil`
preservados: sólo se copiaron informe, manifest y 63 curados hash-verificados;
raw y recorder permanecen en el worktree de adquisición.

## Arquitectura y autoridad

Owners: `meteorites_semantics`, `meteorites_actions`, `meteorites_reader`,
`meteorites_runtime`; integración pequeña en catalog, default perception,
scopes resolver-complete, semantic actions, ActionExecutor y ProductiveRuntime.
Contrato durable en [ARCHITECTURE](../ARCHITECTURE.md#meteorites--primitivas-fase-a-2026-10-08).
No hay nuevo coordinator, routine, excepciones de personaje ni wiring Fase B.
Se reutilizan el parser de página y los contratos de Equipment Sell para binding
causal, lineage, barriers posteriores al tap, readers focales y continuidad segura;
popup Bulk y verificación Item Count quedan en su owner y no se copian.

- **USER_GT:** BASE autónoma no-battle, tabs/página/set independientes,
  16 posiciones de Bag, Flare central y orden 1..10, E relativa al set activo,
  lock distinto de acción lateral, reglas de retorno y selección de set.
- **LIVE_EVIDENCE curada:** acceso Lobby/QM Lobby, selector 1/2/3, tiers
  Ethereal/Ethereal+, niveles positivos/cero, MAX/glare, seis efectos individuales
  desde Bag y cierre por fondo. Procedencia completa en
  [informe de adquisición](METEORITES_HIL_ACQUISITION_20261008.md).
- **IMPLEMENTATION_CONTRACT:** lineage de selección/input, observations frescas,
  un input lateral, efecto de slot, retorno a página 1 preparada y retry acotado.
- **HEURISTIC calibrada:** thresholds CV/HSV y OCR focal. Fallo perceptivo no
  reabre GT ni autoriza input. No se identifica el beneficiario desde stats.
- **LIVE_EVIDENCE del smoke productivo:** tres Equip por cambios de slots 0/1/2
  y tres Unequip con selección directa desde slots 0/2/1, overlay propio y
  cambios del mismo slot. Estado final y timings medidos, no extrapolados.
- **UNKNOWN físico pendiente:** episodio live de no-efecto; recovery probado offline.

## Percepción y corpus

63/63 curados pasan con RapidOCR real. El nuevo detector principal pasa 513/513
negativos existentes; evaluación incremental sólo de ese detector, sin repetir
otros pares válidos. Informe derivado local:
`artifacts/meteorites_phase_a/evaluation.json` y `negative_evaluation.json`.
El manifest de adquisición tiene paths relativos y hashes; corpus root es
explícito y falta de corpus es error, nunca skip exitoso.

Assets runtime pequeños reproducibles mediante `tools.meteorites_assets`;
su [manifest de procedencia](../datasets/meteorites_visual_assets_manifest.json)
registra crop y SHA fuente/asset. No hay templates por nombre o catálogo de tipos.
Fixtures portables en `tests/fixtures/meteorites_phase_a`: 28 vistas focales
lossless derivadas de curados, manifest y hashes; no dependen de raw/ignorados.
Se preservan todas las ROIs ejercitadas y su padding; resto de pixels negro.

BASE principal bajo overlay, cuatro tabs negativos, check de set independiente,
pager, once slots, Flare/core con búsqueda local, marco Ethereal/Ethereal+
incluyendo E equipada, título y barra cero/MAX, acción lateral y spinner cyan.
Geometría desde frame.shape; fuentes 2712×1220/1224 cubiertas por replay.
La selección no usa igualdad del superíndice animado MAX/+30.

## Equip, Unequip y recovery

Equip individual: Bag preparado → candidato visual → selección → overlay
fresco ligado por sprite/set/página/lineage → tier/Flare/nivel/acción lateral
completos → continuidad fresca → un tap → slot esperado EMPTY→OCCUPIED →
readiness/página 1. Normales usan el primer slot vacío según orden USER_GT;
no hay recorrido de diez ni algoritmo de ancla.

Unequip individual: slot ocupado acreditado → selección → overlay fresco
ligado → acción Unequip lateral → un tap → mismo slot OCCUPIED→EMPTY →
readiness/página 1. Bag fallback exige E positiva y slot único cuyo core coincide.
Replay protege ambos contratos; el smoke productivo acredita la ruta física
desde slots, independientemente del replay adquirido desde Bag.

Positivo y readiness se distinguen. Loading persistente es `in_progress`;
pixel unknown/overlay perdido/dispatch incierto son ambiguos. Para no-efecto,
overlay original retenido y fresco se revalida, se cierra por fondo acreditado,
y Bag/set/página/item/slots deben seguir iguales y estables. Sólo opt-in explícito
permite un retry con nueva selección/overlay/acción/set acreditados. Un efecto tardío observado durante la reconciliación cancela el retry y queda
acreditado como positivo. Máximo dos
taps laterales por operación, y ninguno adicional ante ambigüedad. Sin workaround
de otro meteorito ni recovery transversal. El no-efecto está probado offline;
no se provocó un fallo físico para obtenerlo.

## Validación y smoke

70 pruebas directas/temporales nuevas pasan, incluyendo navegación Lobby/QM,
input lineage, transport uncertainty, cancel race, stale/duplicate samples,
efecto tardío, efecto con readiness pendiente, retry acotado y doble input.
545 regresiones compartidas afectadas verificadas, reutilizando las 535 que
seguían válidas y repitiendo sólo los asserts invalidados por el nuevo catálogo.
No se ejecutó suite completa ni evaluator global.

Smoke preparado en `tools.smoke_meteorites_phase_a`: entry → Set 2 → Flare +30 →
Evasion +20 → Shield +21 → Unequip desde slots 0/2/1 → Set 2 vacío → Set 1
con sus once originales/página 1. Sin retry durante el smoke; primera divergencia
detiene cadena, guarda frames/lineage/metrics y exige coordinar restauración.
Source/process/socket/forward conservan cleanup del runtime existente.

**Smoke físico completado**, preparación explícita por chat/steer. Entrada Lobby,
Set 2 vacío, Equip Flare +30/normal +20/normal +21 y Unequip desde sus slots
0/2/1, cada uno con un único input lateral y efecto independiente. Final observado:
Set 2 vacío; Set 1 activo con los once originales; página 1, sin overlay/Loading.
No se ejecutaron los once Equip. Quick Menu tiene replay y adquisición previa;
este smoke usó Lobby directo.

Primera ejecución `20261008_131227` detenida antes de Equip: el reader acreditó
el overlay en 0.282 s y la captura inmediata de continuidad repitió sequence 60.
La barrera lo rechazó; cero inputs laterales. Usuario cerró el panel, restauró
Set 1 y Lobby por chat. Fix local: esperar pasivamente un nuevo tick con los bounds
y cancelación existentes. Cuatro regresiones nuevas cubren duplicados transitorios,
persistentes y cancelación. No cambio perceptivo: evaluator previo sigue válido.

Segunda ejecución `20261008_131349` completó la cadena. Evidencia local antes,
overlay, acción, efecto y final; procedencia SHA y lineage sanitizado durable en
[manifest del smoke](../datasets/meteorites_phase_a_smoke_20261008_manifest.json).
Raw/logs siguen ignorados y no son dependencias de los tests. La conexión se cerró
por el owner productivo; no quedó restauración manual pendiente.

## Latencia productiva

Segundos de operaciones reales a 10 fps. Wall incluye navegación/readiness inicial;
excluye calentamiento OCR y escritura posterior de capturas. Son seis operaciones
en un dispositivo, sin retries; no un objetivo de duración ni un benchmark general.

| Operación | Slot | Selección→overlay | Tap→efecto | Efecto→readiness | Wall | Capturas/OCR/consultas detector/matches CV | Freshness rejects |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Equip Flare +30 | 0 | .328 | .422 | .031 | .860 | 19/3/42/117 | 12 |
| Equip normal +20 | 1 | .281 | .516 | .031 | 1.234 | 26/4/52/148 | 17 |
| Equip normal +21 | 2 | .531 | .734 | .125 | 1.812 | 21/4/47/124 | 13 |
| Unequip Flare desde slot | 0 | .391 | .500 | .063 | .985 | 21/3/42/114 | 13 |
| Unequip normal +21 desde slot | 2 | .375 | .531 | .047 | 1.000 | 22/3/41/111 | 14 |
| Unequip normal +20 desde slot | 1 | .500 | .485 | .031 | 1.188 | 16/3/35/106 | 10 |

Medianas: selección→overlay .383 s, tap→efecto .508 s, efecto→readiness .039 s,
wall 1.094 s. Wall acumulado seis operaciones 7.079 s. Capture cost total .575 s
(por operación .032/.078/.297/.046/.031/.091); perception total 1.451 s
(.157/.124/.451/.203/.156/.360). 125 llamadas capture, 20 OCR, 259 consultas
de categorías detector y 720 matches CV; 79 freshness rejects de ticks repetidos
o anteriores a barrier, cero retries. Captures cuenta consultas al source,
no 125 frames nuevos ni screencaps ADB. Resolver/percepción general de entrada,
startup y escritura de evidencia quedan fuera de estas métricas de primitivas.

## Límites para Fase B

No once Equip, cleanup automatizado, SharedMeteoritePreparation,
Routine Settings/Change Meteorites, excepciones por personaje, Arena, ToT ni Elite.
Ancla probada sólo en dos normales adquiridos; no universalizada. No tier inferior
autorizable, ni tipo faltante inferido. Layout Quick Menu shifted de Meteorites
sin hitbox adquirido. No episodio live de no-efecto para afirmar cobertura física.
Thresholds corresponden al corpus/theme disponible. Un UNKNOWN corta inputs.
