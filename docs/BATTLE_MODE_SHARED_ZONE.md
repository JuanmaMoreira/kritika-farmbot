# Battle Mode como zona preparada

Estado actual: World Boss y Monster Wave SKIP-only son consumidores productivos de
la misma zona; MW implementa Daily/standalone, MAX fijo, compra y board configurables.
Ver [`MONSTER_WAVE_SKIP.md`](MONSTER_WAVE_SKIP.md) para contratos, calibración y gaps
vigentes. El resto de este documento preserva el diseño del checkpoint original
de zona preparada, cuando WB era su único consumidor.

Fase desde `main@e3db3c13076e0ad7baa4cc37184a3a336c418bc9`, en
`feature/battle-mode-shared-zone`. World Boss es el único consumidor productivo.
La adquisición `artifacts/acquisition-battle-mode-monster-wave/` permanece completa,
ignorada y accesible; no se incorporaron sus raws al runtime ni se borraron datos.

## Intención y límites

El usuario es el planner. Selecciona actividades, orden y opciones; el bot ejecuta
navegación, gameplay y manejo operacional. Compartir una visita sólo elimina
navegación entre posiciones consecutivas compatibles. No reordena, agrega
actividades estratégicas ni infiere un plan desde recursos o dependencias.

No se implementaron MonsterWaveFlow, TowerFlow, Stages, Arena, RoutineSpec, loops,
conditions, character scopes nuevos ni nuevos reliefs. `StandardRotation`, Identity,
registry, selección manual y proyección de SessionReport conservan sus funciones.

## Antes y después

Antes: `ProductiveRuntime.run_session → SessionRunner → WorldBossDailyEligibility`
abría Battle Mode, leía el badge y restauraba Lobby. El runner exigía esa
restauración. `WorldBossFlow` volvía a leer sapphires y abrir Battle Mode para jugar;
su contrato terminaba en Lobby o World Boss. Daily eligible requería **dos aperturas**.

Ahora:

```text
Standalone / Run Selected Flows
  WorldBossFlow [Lobby → Lobby]
    precheck OCR → BattleModeZone.enter
    WorldBossActivity [hub → selector → World Boss → gameplay → Back → hub]
    BattleModeZone.leave [Quick Menu → Lobby]

Daily / SessionRunner
  asegurar Lobby + Identity existente
  observar precheck en Lobby y conservarlo pendiente → BattleModeZone.enter
  WorldBossDailyEligibility [observar el hub, sin navegación]
    eligible → consumir precheck; si permite ejecutar, WorldBossActivity → hub
    not eligible → skip estructurado, descartar precheck, sin activity
    unknown / ambiguous / error → fallo técnico, sin cleanup a ciegas
  al terminar el tramo seleccionado: BattleModeZone.leave
  siguiente flow o Rotation
```

| Caso | Aperturas antes | Aperturas ahora |
| --- | ---: | ---: |
| Daily eligible con recursos | 2 | 1 |
| Daily not eligible, incluidos sapphires < 5 | 1 | 1 |
| Daily eligible con sapphires < 5 | 1 | 1 |
| Standalone con recursos | 1 | 1 |
| Standalone con sapphires < 5 | 0 | 0 |

En Daily, la lectura de sapphires ocurre en Lobby, pero no tiene autoridad terminal
antes de Eligibility. Badge ausente produce `SKIPPED_NOT_ELIGIBLE` aunque los
sapphires sean insuficientes; no publica `world_boss.insufficient_sapphires` ni
business incomplete. Sólo con badge activo se consume el precheck: insuficientes
produce ese outcome sin ejecutar la activity; suficientes permite continuar desde
el hub. UNKNOWN/AMBIGUOUS/failure de Eligibility siempre conserva precedencia técnica.
Hay una sola apertura y ningún retorno intermedio a Lobby.

Standalone conserva el terminal inmediato por recursos insuficientes, sin abrir
Battle Mode. Run Selected Flows y Run Flow Once jamás aplican el check Daily.

## Ownership y contrato preparado

- `BattleModeZone` contiene exclusivamente entrada Lobby → hub y salida
  hub → Quick Menu → Lobby. Comprueba estados estables y postcondiciones; retries
  bounded de dos intentos requieren exactamente el origen fresco de cada acción.
  Reconocer el status Daily como overlay compatible no constituye policy Daily.
- `PreparedActivity` vincula una posición a una instancia de zona, un callable de
  ejecución hub → hub y un precheck opcional. No es un flow en el registry ni un
  framework de routines. El precheck devuelve `None` o un resultado candidato,
  sin publicar eventos. El runner lo conserva localmente para esa posición y sólo
  lo consume después de Eligibility (o si no hay check). NOT_ELIGIBLE lo descarta;
  un resultado técnico de Eligibility prevalece. Cancelación detiene inmediatamente.
  Nunca produce un skip ni decide si se abre `BattleModeZone`.
- `SessionRunner` comparte únicamente la misma instancia de zona entre posiciones
  consecutivas. Asegura Lobby antes de una visita, preserva Identity en la primera
  observación de precondición y verifica hub antes de Eligibility/activity. Verifica
  la postcondición de cada posición y Lobby después del cierre final. Un flow ajeno
  intermedio termina la visita; nunca se mueve para optimizarla.
- `WorldBossActivity` conserva selector, Previous Rewards, Start, límites locales
  de Socket/Equipment relief, negativas repetidas, bag/meteor full, Auto Battle,
  timer, Raid Complete y Continue. En toda completion de gameplay verifica World
  Boss limpio y solicita `ExitWorldBoss`; sólo completa tras verificar el hub.
- `WorldBossFlow` compone la misma activity con precheck y apertura/cierre propios.
  Declara Lobby → Lobby y mantiene `world_boss` seleccionable individualmente.

Failure/cancelación no activan un `finally` que navegue desde estados desconocidos.
Un fallo del cierre final impide completar la posición o publicar un skip exitoso.
Las causas técnicas y los outcomes de gameplay ya producidos se conservan.
Rotation conserva su allow-list; reconocer Battle Mode para las precondiciones de
activities no lo convierte en origen autorizado de Rotation.

El retorno `World Boss screen → Back → Battle Mode Select` fue confirmado por el
usuario en esta tarea. El target relativo del botón Back se obtuvo de la captura
curada `screencaps/semantic/world_boss/main/20260827T231011_209632Z_01.png`; el executor
lo escala con la geometría del frame. El retorno final por Quick Menu conserva las
acciones y estados adquiridos en
[`world_boss_eligibility_return_manifest.json`](../datasets/world_boss_eligibility_return_manifest.json).
No hubo replay físico en esta fase.

## Eligibility y recursos durante una visita

`WorldBossDailyEligibility` sólo observa. Exige presencia/ausencia consistente por
0,75 s, secuencias frescas y budget de 6 s. UNKNOWN, AMBIGUOUS, overlays incompatibles
o badge fluctuante no autorizan ejecución. El check conserva el hub como precondición.
No almacena decisiones entre visitas o personajes.

El contrato permite leer otros badges seleccionados en la misma visita y conservar
decisiones dentro de ella: no obliga a restaurar Lobby por check. En esta fase sólo
se evalúa el badge WB en su posición; no hay snapshot conjunto ni Eligibility
productiva MW/Tower. Agregar esa lectura conjunta no exige cambiar WorldBossActivity.

El precheck de sapphires se observa opcionalmente antes de abrir visita desde Lobby.
En Daily se conserva y consume después de Eligibility: evita ejecutar una activity
elegible sin recursos, sin necesitar volver a Lobby para leer. En standalone además
evita abrir la zona. Se omite cuando una activity se encadena desde el hub. Su valor
confirmado puede acompañar el resultado WB como diagnóstico consumido una vez;
no se suma, resta ni predice disponibilidad con un saldo interno.

El precheck es evidencia de una posición, no un gate global de la zona. Una segunda
activity preparada seleccionada comparte la misma visita tanto si WB fue omitido
por Daily ausente como si terminó por recursos insuficientes después de confirmar
Daily activo. No se insertan actividades ni se modifica su orden.

Los popups del juego son boundaries autoritativos. **El runtime WB actual sólo tiene
el precheck OCR de sapphires; no tiene semántica productiva del popup de sapphires
insuficientes.** Si aparece un estado no reconocido durante la ejecución, falla
conservadoramente. Este refactor no introduce ese detector ni convierte el OCR en
garantía de disponibilidad futura. Loops futuros deberán usar outcomes/popups
adquiridos, sin contabilidad simulada.

## Extensión futura y reliefs

Una segunda activity se puede vincular a la misma zona con su propio callable
hub → hub, opciones y check. Las pruebas usan una activity ficticia sin referencias
a WB y verifican ambos órdenes, skips y cortes por un flow ajeno. La secuencia futura
`WB → MW → Tower` podrá conservar una visita sólo cuando sea el orden seleccionado.
Enable/disable, selected characters y loops/conditions explícitos permanecen asuntos
de composición futura; el seam no los decide ni los impide.
La composición default All Characters + Standard Rotation se conserva.

Cada activity conserva la intención ante un blocker y delega a support operations
independientes con un return plan adquirido. El hub no conoce Socket, Equipment,
SKIP ni inventarios. Así, `activity → blocker → relief → resume activity → hub`
no necesita acoplar reliefs a MW. Los returns productivos actuales de Socket y
Equipment siguen siendo exclusivamente a WB; otros callers necesitan evidencia.

Reliefs futuros pendientes, sin implementación: Keys mediante Trading Center/tab
Keys y Treasure; Crafting Materials mediante Trading Center/materials y Craft.
La relación MW → Arena Tickets → Arena no genera planning automático.

## Ground truth preservado para Monster Wave y Tower

Los tres badges Daily (WB, MW, Tower) conviven en Battle Mode Select, reutilizan el
mismo asset y pertenecen a sus cards respectivas. Hub → MW → Back → hub se confirmó
dos veces; hub → Tower → Back → hub también está confirmado. MW sigue operable sin
su badge: Daily no equivale a disponibilidad general.

**Monster Wave será SKIP-only por decisión explícita de producto. Nunca se usará
Start manual ni se diseñará batalla manual/Auto salvo cambio explícito de decisión.**
El futuro activity contempla SKIP Ticket, Activate SKIP, Start SKIP process,
Sapphires Used, inventory board, blockers, CLEAR y retorno a MW/hub.

Hechos adquiridos: activación requiere 30 SKIP Tickets; Purchase SKIP Ticket permite
comprarlos; Fill All desde 20/30 mostró 1.400.000 GOLD; activación produce timer
account-wide; MAX puede consumir hasta 100 sapphires por intento según disponibilidad
y timer. Deben contemplarse SKIP activo, tickets insuficientes, compra posible,
**GOLD insuficiente para comprar tickets**, timer/expiración y sapphires insuficientes.
Esta fase no implementa su state machine.

El inventory board enumera inventarios no bloqueantes que pueden llenarse durante
MW: Brawler's Badges (**Arena Tickets**), Weapon Material, Hero Weapon Material,
Bronze Key y Silver Key. Advierte que rewards que excedan capacidad no se obtendrán
y permite decidir continuar. Socket y Equipment son blockers duros con sus popups,
aunque no aparezcan en ese tablero. El popup “The bag is full. Would you like to
organize your bag?” es el boundary ya conocido en WB (`popup.socket_inventory_full`);
no se duplicará semántica MW-specific.

Tower: card, entry, Back → hub, Sapphires Used 1, Physical/Magical, floor selection
y Start están confirmados. No hay TowerFlow productivo.

## Follow-ups exactos antes de MonsterWaveFlow

1. Adquirir badge ausente de Tower; revisar necesidad de negativo reciente WB
   (ya existen negativos curados WB, no se afirma que falten por completo).
2. Popup de sapphires insuficientes de MW.
3. GOLD insuficiente para comprar SKIP tickets.
4. Rama No del inventory board.
5. Rama No del bag-full popup si hace falta confirmar su comportamiento.
6. Posibles estados de SKIP expirado/no activable.
7. Completar positivos/negativos discriminantes antes de promover Eligibility MW/Tower,
   y returns específicos antes de integrar reliefs con nuevos callers.

Start manual MW no es un gap: está expresamente excluido.

## Validación

La comparación AST contra la baseline confirma que el cuerpo de gameplay desde
`open_selector` hasta su resultado y sus siete helpers se trasladaron sin cambios.
Pruebas dirigidas: standalone completo; Daily real eligible/ineligible; UNKNOWN y
AMBIGUOUS; hub fresco; retornos fallidos/cancelados; precheck; actividad ficticia
en ambos órdenes y separada por un flow; skips; report, Identity y Rotation.
No se cambiaron detectores, resolver, assets, ROIs ni thresholds.

Validación final tras corregir precedencia Daily: **183 tests dirigidos** y
**1797/1797 hardware-free** en 268,39 s. Incluye badge ausente/activo con recursos
insuficientes/suficientes, UNKNOWN/AMBIGUOUS/failure de Eligibility después de entrar,
clasificación SessionReport, standalone sin apertura y segunda activity compartida.
`git diff --check` limpio; enlaces locales, UTF-8 y whitespace verificados.
Los 64 frames del manifest de adquisición siguen accesibles. Sin hardware, commit
ni push; cambios ajenos preservados y trabajo listo para revisión.
