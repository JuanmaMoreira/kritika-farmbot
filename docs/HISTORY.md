# Historia — Kritika FarmBot 0.2

Este documento conserva decisiones, evidencia y líneas reemplazadas. No define el estado productivo: para eso ver [`../CONTEXT.md`](../CONTEXT.md). Los contratos vigentes están en [`../ARCHITECTURE.md`](../ARCHITECTURE.md).

## Origen y vertical slice

El runtime 0.2 reemplazó el diseño legacy monolítico por límites explícitos: captura, percepción semántica, resolución de contexto, flows, ejecución física y ADB. El tag `legacy-pre-hybrid` preserva el runtime anterior.

La primera línea productiva cerró Black Market, World Boss, `StandardRotation`, sesiones multi-flow, CLI y GUI. La validación live incluyó Rotation aislada 28/28 y una sesión combinada `Black Market → World Boss → Rotation` 28/28 sin fallos técnicos.

## Percepción, evaluación y operaciones verificadas

La percepción evolucionó desde landmarks aislados hacia observaciones semánticas, overlays y facts OCR/temporales. `ContextResolver` quedó puro; `RuntimeObserver` pasó a entregar snapshots coherentes y frames frescos.

La evaluación offline se volvió incremental por detector×frame, con fingerprint e invalidación conservadora. Los full audits quedaron reservados para cambios compartidos, recalibraciones amplias o sospecha de cache inválida.

`VerifiedTransition` consolidó precondición, acción y postcondición. El criterio operativo resultante fue: la desaparición visual o el paso del tiempo no prueban éxito; un retry necesita un estado fresco que lo autorice.

## Reliefs productivos acotados

### Socket Inventory Relief

Se adquirió y promovió una operación de soporte para el blocker confirmado de World Boss. Intenta Enhance All sólo con GOLD, usa Bulk únicamente para el caso adquirido de ópalo incompatible level 0 y vuelve al caller exacto. Una segunda aparición en el mismo run usa la salida negativa.

Durante HIL, el chat dinámico demostró que una ROI superior derecha era frágil. El landmark base se movió al tab izquierdo persistente y se validó contra positivos, negativos y una captura con chat visible. El smoke de No Material confirmó OCR de `Opal (Skill)+0`, venta explícitamente autorizada y reducción de inventario. Un frame transitorio enseñó que «popup ausente» no equivale por sí solo a retorno exitoso.

### Equipment Combine Relief

Para World Boss se incorporó una operación independiente con orden fijo Transmute → Ethereal condicional → Fuse, acumulación sin short-circuit y retorno verificado. Conserva un único intento positivo por run; la repetición del blocker se cierra de forma no fatal.

Estos reliefs no son flows del registry ni una solución general de inventario.

## Flows diarios

La línea estable agregó Send Stamina, Summon Pet Daily, Daily Quests, Mailbox y Guild Check-In como flows `PER_CHARACTER` con contratos explícitos.

- Send Stamina autoriza un único All desde Daily visible.
- Summon Pet Daily conserva una apertura acotada y un Pet relief incidental de un solo Combine All.
- Daily Quests trata Claim All y el reward independiente de forma single-attempt.
- Mailbox preserva leftovers como outcome de negocio y no libera espacio.
- Guild Check-In usa acceso directo desde Lobby y Quick Menu desde contextos permitidos; completion requiere estado fresco estable.

La adquisición live de Guild separó el badge de la señal de completion y evitó convertir el trabajo en categories, routines o un grafo general de navegación.

## Consolidación del baseline estable

Después de los flows se consolidaron, en orden:

- `fc66d60`: Rotation, obstruction recovery y daily flows.
- `95c6bd6`: Structured Observability v1.
- `16f2d41`: Failure Evidence v1.
- `7865c55`: SessionReport v1.
- `454d111`: GUI funcional mínima.
- `a5c2648`: Character Identity mínima.
- `9e1e258`: Eligibility mínima.
- `e3db3c1`: compactación de SessionReport.
- `9a4c034`: `BattleModeZone` compartida.
- `71340f58`: Monster Wave SKIP-only.

Monster Wave quedó integrado en el registry y en la visita compartida a Battle Mode. Su alcance estable es una sola operación MAX SKIP por llamada, compra opcional de tickets, board configurable y eligibility diaria; Start manual, Auto Battle y farming loop quedaron fuera.

La validación de ese checkpoint cerró **1925/1925 tests hardware-free** y **510 frames** sin wrong/ambiguous. La evidencia live confirmó ACTIVE, MAX, Start y board negativo. Por eso las antiguas frases «sin commit» y «sin push» eran estado documental pre-commit, no evidencia de un checkpoint posterior.

## Línea experimental Inventory Relief

La etapa experimental comenzó inequívocamente en `4612fd8` y terminó en `024ff8e15f981930e3bab962ed116f1e9f3946fe`. Se preserva completa en la branch `archive/inventory-relief-experimental`.

Su secuencia fue:

- `4612fd8`: chain de Inventory Relief con Trading, Craft, Treasure y Equipment Sell;
- `9e5e9fc`: fixes de Trading;
- `f568c25`: percepción runtime acotada;
- `eb0a843`: retry y swipe de Trading;
- `3c8c0a7`: input lifecycle/readiness;
- `024ff8e`: readiness de Trading y separación Keys/Materials.

La evidencia raw permanece en `artifacts/acquisition-inventory-relief-chain` y los curados en `screencaps/semantic/inventory-relief`. La branch archival conserva manifest, assets runtime, documentos y commits experimentales. Nada de eso se copió al baseline reconstruido.

### Conocimiento de dominio preservado

- Keys: conversiones Bronze → Silver → Gold; el orden debe adaptarse a capacidad.
- Materials: categorías Weapon, Armor y Accessory con conversiones verificables.
- Trading: monto bounded, lectura de input y verificación de disminución real.
- Listas: sólo filas completas son accionables; cada gesto exige reobservación y corrección bounded.
- Craft: distinguir costo GOLD de ofertas KARATS.
- Treasure: una apertura GOLD y repeat condicionado a currency GOLD fresca.
- Equipment Sell: Item Count es autoridad; Ethereal+ y accesorios se protegen; rareza/tipo/costo desconocidos fallan cerrados.
- Recovery causal: resolver blocker, volver al caller y reintentar sólo si un blocker fresco autoriza exactamente esa repetición.

Los thresholds ensayados para presión de recursos fueron propuestas experimentales, no policy aceptada.

## Percepción acotada: resultado del experimento

El experimento demostró que evaluar sólo detectores relevantes reduce marcadamente la latencia frente a percepción global. También mostró que su implementación estaba entrelazada con Inventory Relief y con planes específicos de navegación.

Se conserva el principio, no la API: limitar hot paths de a uno, reservar percepción amplia para discovery/recovery/evaluación, medir antes y después y exigir smoke breve antes de extender.

## Input lifecycle: regresión y descarte

La motivación era válida: una pantalla visible puede no estar aún interactiva, un tap puede perderse y una percepción global lenta puede ocultar ese problema. El framework experimental añadió perfiles de readiness, retry y no-effect.

Hardware reveló tres regresiones en Trading:

1. rechazo de precondición antes de readiness real;
2. routing incorrecto de scroll en Keys;
3. confusión entre selección visible y contenido listo.

La conclusión no fue conservar el framework. El baseline retiene sólo las reglas: visible no implica interactivo; la corrección no puede depender de lentitud accidental; un tap perdido requiere tratamiento bounded y verificable. No hay input lifecycle general en la arquitectura ni en el roadmap.

## Rollback y reconstrucción

Git estableció el límite causal:

- `main == origin/main == 71340f58d3a4515facc346ad22addfc0d814a6ec`;
- no existe otro commit general estable entre ese checkpoint y Inventory Relief;
- `4612fd8` abre la etapa experimental;
- `024ff8e` es su HEAD preservado.

Se creó `archive/inventory-relief-experimental` sin sobrescribir referencias y `rebuild/stable-baseline` desde `71340f58`. No se movió `main`, no se borró la feature branch, no hubo rebase/reset destructivo ni push. Los cambios locales ajenos y los raws/curados quedaron intactos.

La reconstrucción eligió no cherry-pickear código experimental. Primero endureció instrucciones y skills; después reconstruyó contexto, arquitectura, roadmap e historia. El trabajo futuro reintroducirá una capacidad por vez desde evidencia y primera divergencia causal.

## Decisiones reemplazadas

- El icono de oro de Lobby describe un shell persistente, no una pantalla base exclusiva.
- `landmark.lobby_commerce_pair` quedó como alternativa offline; producción usa Trading Center.
- El candidate temprano de Monster Wave no bastaba para Battle Mode Select y fue reemplazado por evidencia current-season.
- La calibración empírica expresa posición dentro del gap observado, no probabilidad.
- Las sesiones raw o diagnósticas nunca se promueven automáticamente.
- La policy temprana de abortar todo error técnico no define por sí sola la futura policy unattended.
- El chain experimental y su lifecycle no son la arquitectura runtime objetivo.

## Registros relacionados

- [`semantic_census.md`](semantic_census.md): taxonomía legacy y Quick Menu.
- [`legacy/`](legacy/): documentación 0.1 preservada.
- `datasets/*manifest.json`: ground truth curado y provenance reproducible.
- [`../CHANGELOG.md`](../CHANGELOG.md): milestones de alto nivel.
- Git `4a14eee`: documentos hot completos previos a su compactación.
- Branch `archive/inventory-relief-experimental`: manifest, assets y docs de la etapa experimental.
