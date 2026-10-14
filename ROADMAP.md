# Pendientes y estado de capacidades

Baseline productivo: `7f80a184` en `rebuild/stable-baseline`, 2026-10-14.
Entrada breve en [CONTEXT](CONTEXT.md); autoridad física en
[GAMEPLAY_GT](docs/GAMEPLAY_GT.md), contratos en [ARCHITECTURE](ARCHITECTURE.md) y
[RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md). Este documento planifica; los
checkpoints y conteos históricos se consultan desde [HISTORY](docs/HISTORY.md).

## Secuencia prioritaria acordada

1. **Consolidación documental:** cierre de esta fase; contexto compacto, estado
   reconciliado con publicaciones, contratos e historia separados y enlaces revisados.
2. **Auditoría focal y limpieza segura de almacenamiento:** siguiente mantenimiento.
   Revisar consumidores/procedencia antes de proponer borrados; preservar evidencia
   útil, corpus, runtime y trabajo local. No se ejecuta como parte de esta fase.
3. **Open Pets:** siguiente funcionalidad importante, **todavía no iniciada**.
   Preparación e implementación después de la limpieza. No confundir con Summon Pet
   Daily/Pet relief existentes. Consultar GT/contratos pertinentes y resolver sólo
   las preguntas físicas realmente abiertas al comenzar; aquí no se diseña su flow.

## Terminadas para su alcance publicado

| Capacidad | Estado / fuente |
| --- | --- |
| Runtime, GUI/CLI, sesiones/Rotation y rutinas v2 | Productivos; orden literal y config por ocurrencia. [ARCHITECTURE](ARCHITECTURE.md), [GUI_CONFIGURATION](docs/GUI_CONFIGURATION.md) |
| Flows diarios, Black Market y World Boss | Productivos; outcomes de negocio distintos de fallo técnico. [HISTORY](docs/HISTORY.md#flows-diarios) y contratos vigentes |
| Monster Wave SKIP | Loop Sapphire pressure y pasada única para Arena, board/reliefs/efecto conectados. [MONSTER_WAVE_SKIP](docs/MONSTER_WAVE_SKIP.md) |
| Stages Daily / Ads y Gold Farming | Ads-only con inversión MW; Gold 28/28 acreditado en su campaña. [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md#basic-gold-farming--estrategia-seleccionada-no-planner) |
| Arena | Single Battle, Auto Repeat y Farming Cycle publicados; sustituye la nota antigua «Daily Arena no implementado». No policy diaria propia. [ARENA_FARMING_CYCLE](docs/ARENA_FARMING_CYCLE.md) |
| Manual Stages / presupuesto Stamina | Tercera rama del Farming Cycle; una entrada causal x4 por invocación y ledger60/entrada. [Contrato](docs/ARENA_FARMING_CYCLE.md#manual-stages-y-deudas) |
| Shared Meteorites A/B1/B2 | Setup/cleanup por personaje; once efectos y lifecycle Session. [ARCHITECTURE B2](ARCHITECTURE.md#meteorites--integración-b2-de-routinesession-2026-10-08) |
| Character Identity / Persistent State / Data Sweep / Arena VP | 28 IDs, SQLite/epochs, Ads/WB y datos informativos separados; VP sin autoridad económica. [CHARACTER_STATE_CHECKPOINT](docs/CHARACTER_STATE_CHECKPOINT.md), [Arena stabilization](docs/ARENA_STABILIZATION_CHECKPOINT_20261010.md) |
| Reliefs / Equipment / Trading / Craft / Treasure Gold | Wiring y permisos por caller; Sell cromático, bloque protegido y paginación guardada. [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md) |
| Ordered-list navigation / targeted swipe | Primitive y consumidor Trading Materials cerrados; no exige adopción en otra lista. [TARGETED_SWIPE_AUDIT](docs/TARGETED_SWIPE_AUDIT.md) |
| Observabilidad / Failure Evidence / Session Report | MANUAL técnico y frame directo/nativo publicados; reporte Arena analítico. [FAILURE_EVIDENCE_V1](docs/FAILURE_EVIDENCE_V1.md), [SESSION_REPORT_V1](docs/SESSION_REPORT_V1.md) |

Aceptaciones por alcance, no promesa de cobertura física exhaustiva de HEAD:
[full roster](docs/FULL_ROSTER_CHECKPOINT.md),
[Stability+Performance acumulativa](docs/FULL_ROSTER_STABILITY_PERFORMANCE_CHECKPOINT.md),
[Gold 28/28](docs/GOLD_CYCLE_DIAGNOSIS_20261009.md),
[Arena integral](docs/ARENA_FARMING_CHECKPOINT_20261009.md).

## Implementadas con límites conocidos

- Arena retorno `f5d2a828`: causa física/píxeles del corte **UNKNOWN**. No hay
  investigación nueva autorizada aquí; captura posterior positiva no prueba el fix.
  Fallar conservadoramente preservando evidencia sigue siendo el contrato.
- Recuperaciones recientes guardadas tienen cierre offline posterior; publicación
  no implica prueba live posterior de todas sus ramas. Procedencia por intervención
  en [HISTORY](docs/HISTORY.md#consolidación-documental-2026-10-14).
- Arena: derrota Single, modal de umbral (clase conocida, literal/umbral/cierre
  UNKNOWN), Upon Defeat ON y cancelación física conservan deuda focal. La operación
  NORMAL con Socket relief y retorno acreditada el 2026-10-12 cierra esa ruta
  concreta; no acredita todas las variantes de relief/retorno. Buffs1/2 requieren
  ON, sin gates OCR de stock; Double Points conserva cobertura propia y nunca Karats.
- Craft Accessories Hero Earrings: falta MAX/result/effect completo; Weapons y
  Armor/Helmet tienen adquisición propia. No generalizar entre familias.
- Equipment expansión +4 positiva, Ethereal Enhance positivo, Fill All MW sin Gold,
  balance0 natural en QM y chat completamente desplegado conservan límites físicos
  focales; sólo ante necesidad/aparición natural, sin fabricar estados para cubrirlos.
- Corpus: fuentes históricas ausentes/fixtures reducidas limitan reproducción.
  Bundles Failure Evidence son temporales, no assets runtime. No readquirir hechos
  cerrados sólo por ausencia de raw o un miss perceptivo.

Estos límites no bloquean Open Pets ni requieren otra campaña general. Amplitud
Ads quedó cerrada por USER_GT 2026-10-06; las variantes SDK posteriores tienen
replays propios, no una deuda general reabierta. Fallos históricos de tests se
conservan con su fecha y no se declaran actuales sin reproducción vigente.

## Mejoras futuras no bloqueantes

- Arena controller: posible optimización de `adjacent_uncertainty`; evaluar sólo
  en una tarea futura con causa/alcance propios. Sin ajuste durante consolidación.
- Trading confirm p95 histórico1.593s/max1.688s (gate2s): candidato medido, sin patch.
- Medición física final de Socket animation/scoped perception0.2s, otras rutas QM
  no ejercidas y transformaciones Sell bajo Full: conservar adquisición natural
  suficiente para cada ruta; no repetir smokes cerrados por rutina.
- ToT y Melee: futuros, no implementados. ToT necesitará GT de su lista/readiness
  y puede reutilizar primitive de ordered-list; no inferir UI por analogía.
- Open Platinum Keys: futuro, sin control funcional; requiere GT/economía propios.
- REPEAT_CURRENT y planner/scheduler estratégico general: fuera de alcance actual.
  El clock de resets/eligibility ya implementado no es ese scheduler estratégico.

## Deuda técnica y mantenimiento

- Auditoría de almacenamiento: inventario focal, consumidores y retención antes de
  borrar; herramientas históricas fase11 archivadas fuera del checkout no son deps.
- Mantener un owner por contrato y la entrada breve de CONTEXT; actualizar estado
  cuando una intervención posterior cierre un límite concreto, con enlace histórico.
- SessionReport base: MANUAL técnico conserva evidencia en resultados/JSONL, pero
  su proyección como incompletitud no garantiza renderizar la referencia. Revisar
  esa presentación en trabajo posterior; no cambiar status ni policy incidentalmente.
- Portabilidad de evidencia histórica y replay de interrupciones sin SessionResult
  son mejoras futuras. Failure Evidence síncrono conserva límites de IO/memoria;
  las mediciones antiguas del ring reducido no miden el callback directo actual.
- Whitelist `monster_wave.sapphire_effect` de SessionReport **ya implementada**;
  la proyección UNASSESSED de campañas antiguas queda como historia, no tarea abierta.
