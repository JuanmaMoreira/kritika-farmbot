# Gameplay / UI — GT canónico

Fuente durable de estructura física y mecánicas que condicionan el diseño. `USER_GT` es la declaración explícita del usuario consolidada aquí; sólo nueva `LIVE_EVIDENCE` físicamente contradictoria la reabre. Replay, OCR, detector, resolver y heurísticas no la sustituyen. Implementación actual: [CONTEXT](../CONTEXT.md); software: [ARCHITECTURE](../ARCHITECTURE.md).

## Clases físicas — USER_GT

Sólo `BASE | MODAL | OVERLAY | EXEMPT`. Cada BASE declara `battle_surface`. Nombres `screen.*`, `popup.*`, reglas del resolver y ownership de código no clasifican la UI. Una tabla agrupada aplica la clase a cada superficie enumerada.

| class | Superficies físicas | battle_surface |
| --- | --- | --- |
| BASE | Lobby; Battle Mode Select; Monster Wave; Craft; Equipment Inventory; Socket; Treasure; Combine; Guild; Pets Manage; Pet Summon; Pet Combine; World Boss | false |
| BASE | World Boss Battle | true |
| MODAL | Trading; Mailbox; Quests; Friends; Black Market; Previous Rewards | — |
| MODAL | MW: purchase tickets; insufficient sapphires; resource board; CLEAR; Point Reward (por encima de CLEAR al cruzar ciertos conquest points; OK lo cierra y debajo queda CLEAR; tocar fuera no lo cierra); New Ranking; Weekly Results | — |
| MODAL | Black Market: purchase dialog; insufficient Gold; inventory full | — |
| MODAL | Equipment Full; Socket Inventory Full inicial; blocker Socket todavía lleno **después** del relief (distinto del inicial); Meteor blocker | — |
| MODAL | Socket: Enhance All, No Material, Sell; Combine: confirmaciones | — |
| MODAL | Pets: Combine All; Mass Evolve Normal; Mass Evolve Rare; full/no-material/no-fragments cuando se presentan como diálogos | — |
| MODAL | Craft: quantity/recipe selector y warning premium/Karats; Equipment: Sell dialog/confirmation; Trading: Item Trade y alerts | — |
| MODAL | Ethereal Mass Combine insufficient-material warning (`popup.ethereal_no_material`), distinto de su confirmación; Pet Summon Premium insufficient-Gold warning (`popup.insufficient_gold`) | — |
| OVERLAY | Quick Menu; Pet Summon Result; Pet Combine Result; Select Boss; Raid Complete; Pets Epic/Premium selectors | — |
| OVERLAY | Craft result; Treasure selector y result/reward; MW Sapphires/MAX tooltip; Equipment detail; Combine animation/result | — |
| EXEMPT | Character Select | — |

Combine animation/result sigue siendo OVERLAY aunque casi opaque el fondo. EXEMPT excluye las reglas globales de oclusión de BASE y se usa con moderación. Nuevas batallas deberán declarar `battle_surface=true`; no se deduce del nombre.

Combine es **una BASE**: Transmute, Fuse, [Awakened] Transmute y [Ethereal] Random Part son vistas/estados internos. Awakened pertenece a Transmute; Random Part se alcanza desde Transmute y sólo se modela Random Part. Cambiarlos no cambia la BASE ni su historial Back. Lo mismo vale para tabs/paneles/modos salvo USER_GT explícito distinto.

## Caller, Back y cierres — USER_GT

- Back recuerda la BASE inmediatamente anterior. Encadenar BASE→Quick Menu→otra BASE cambia el retorno. Un relief productivo restaura su caller BASE antes de navegar a otra; no encadenar BASEs extra si importa ese retorno.
- MODAL/OVERLAY no crean caller BASE. Close/Cancel vuelve al parent subyacente donde esté establecido; no generalizar gestos de cierre no verificados.
- Craft bloqueado: `Craft → Equipment Full → acceso directo a Combine desde el blocker → relief → Back → Craft`. No existe motivo productivo para Craft limpio→Combine en este relief; no inventar ruta Quick Menu.
- Socket todavía lleno tras Combine/Sell es el blocker **post-relief**, distinto del popup inicial. Elegir No deja la tarea incompleta y se continúa con el siguiente personaje; fuera del scope positivo de relief.
- Equipment detail: no hay X; cerrar tocando afuera, preferentemente la región superior no interactuable entre Karats y `?` junto a Back. **No Back**: regresaría desde Equipment Inventory a su caller. No hay coordenada exacta canónica en este contrato.
- Craft recipe/quantity: Cancel vuelve a la misma Craft BASE.
- **USER_GT (2026-10-01):** `Craft → Inventory → Back → Craft → Back → Lobby` es una secuencia determinista. Lobby es su postcondition normal, no failure ni recovery inesperado. Craft conserva su entrada directa; no agregar `MW → Inventory → MW` preventivo. Desde ese Lobby se continúa por navegación normal a Battle Mode Select y MW.
- **LIVE_EVIDENCE (2026-10-02):** `MW → Inventory → Back → MW → Back → Lobby` conserva esa historia de BASE. Lobby limpio es un destino normal conocido; la activity reusable restablece Battle Mode Select mediante navegación normal sólo en esta rama, sin otro Back ni consumo.
- Pets Combine All y Mass Evolve Normal/Rare: No devuelve exactamente el parent/estado subyacente Pet Combine o Pet Summon, o Pets Manage si allí aplica esa confirmación; no inferir otras rutas.
- Trading abierto desde Quick Menu conserva el parent; X restaura ese parent (Craft y Treasure establecidos). Treasure sí cambia de BASE.
- MW tooltip (`overlay.monster_wave_usage_tooltip`): un tap en Sapphires abre; segundo tap sobre el tooltip cierra. Estrategia aceptada: double tap, ignorar normalmente el transitorio; si el segundo se pierde, puede reconocerse y manejarse. No requiere state machine nueva.

## Oclusión y layering

**USER_GT:** CHAT puede aparecer en toda BASE, incluso batalla. Heaven & Hell puede aparecer en toda BASE no-battle (incluido Lobby), nunca en una BASE battle. Son oclusores transversales; no crean una nueva BASE. MODAL/OVERLAY/EXEMPT no heredan estas reglas por intersección geométrica: manda su layering físico. Un popup establecido encima de chat no pierde esa propiedad por un detector fallido.

Coordenadas normalizadas `(left, top, right, bottom)`:

| Oclusor | Envelope de diseño | Procedencia |
| --- | --- | --- |
| CHAT | `(0.44, 0.12, 0.85, 0.21)` aproximado | Evidencia curada ya documentada en [manifest Socket](../datasets/socket_inventory_relief_semantic_manifest.json) y [manifest WB](../datasets/world_boss_semantic_manifest.json); sin readquisición |
| Heaven & Hell | **`(0.165, 0.105, 0.360, 0.260)`** | HEURISTIC de diseño derivada por inspección de capturas existentes; detalle debajo |

### Heaven & Hell: procedencia y límite

Revisados todos los 11 positivos del [manifest portal](../datasets/portal_notification_evidence_manifest.json) (adquisición `live_scrcpy`, 2026-09-06) en `artifacts/portal_notification_acquisition/`: `positive_battle_select_{1_seq1,2_seq29,3_seq54}`, `positive_guild_{1_seq1,2_seq28,3_seq52}`, `positive_hell_battle_select_{1_seq1,2_seq28,3_seq58}`, `guild_variant_{seq1,seq30}` (todos `.png`). Además `target_calib_fresh_seq1.png` muestra Hell en Pets; `smoke_after_tap_seq1.png` muestra su ausencia. Búsqueda por nombres/referencias en manifests, screencaps, artifacts/adquisiciones e historia; no se generó evidencia nueva. Directorios de resultados pytest con acceso denegado no se inspeccionaron.

En los frames de 2712×1224, el panel/cromo, la X saliente y los efectos visibles del portal ocupan aproximadamente x=460–970, y=130–315. La envolvente anterior redondea hacia afuera a pasos de 0.005 (aprox. x=447–976, y=129–318): el menor rectángulo conservador a esa precisión de revisión que contiene las variantes observadas, incluida su animación visible y borde difuso. No extrapola fases no capturadas ni añade margen por temporadas hipotéticas. La estimación anterior `(0.16,0.10,0.36,0.27)` no era canónica y se sustituye por ésta.

No es una segmentación exacta ni prueba de todo el ciclo animado. Queda incertidumbre residual en los bordes difusos/fases no muestreadas; sólo justificaría adquisición futura si un nuevo hard landmark dependiera de ese borde. La frase histórica «absent on Lobby» del manifest es **LEGACY_STALE**, supersedida por USER_GT; el manifest se conserva como evidencia, sin alterarlo.

**Oclusión ≠ detección:** el probe usa sólo X+cromo en `(0.270,0.085,0.360,0.175)`; ese recorte no delimita el área que tapa la notificación. El target X establecido `(0.3434,0.1397)` tampoco define el envelope.

### Hard landmarks — DESIGN POLICY

- Identidad/postcondición dura de BASE: evitar CHAT; además evitar el envelope Heaven & Hell si `battle_surface=false`. Señales expuestas pueden ser auxiliares/diagnósticas.
- MODAL/OVERLAY/EXEMPT: no blacklist geométrica automática; comprobar layering establecido.
- Identidad estable: preferir landmark visual/template estable cuando sea práctico. Valor variable necesario para decidir/actuar: OCR/parser. Títulos decorativos constantes no deben ser gates obligatorios si existe evidencia funcional/contextual más fuerte.
- Reemplazar OCR por un template en la misma ROI ocluida no resuelve el problema: elegir landmark seguro.

## Mecánicas establecidas que afectan composición

Evidencia física previa curada (procedencia en [contrato SKIP archivado](legacy/DOC_RESET_20260925.md) y [reconstrucción](POST_V1_RESOURCE_ROUTING_RECONSTRUCTION.md), no inferencia del detector): SKIP se activa con tickets completos (30/30 en el caso adquirido; VIP puede reducir el requisito). Fill All compra faltantes a 140.000 Gold por ticket; completar tickets no activa SKIP automáticamente. El estado/timer es account-wide y se debe observar fresco, sin fijar duración a partir de un ejemplo. La misión Daily MW requiere x4; eso no limita MW productivo ni autoriza un gate Daily. **USER_GT / product policy:** MW no tiene Eligibility; su objetivo es gastar Sapphires, liberar capacidad y obtener rewards incluso con Daily completada. Sapphires se observan antes de entrar, desde Battle Mode Select: 0 permite omitir MW y >0 permite entrar y ejecutar el loop MAX. El saldo inicial determina `ceil(sapphires_iniciales / 100)` y sólo CLEAR confirmado avanza el gasto.

El board MW muestra balances/límites, no rewards entrantes exactos ni recetas; drops no deterministas no autorizan predicción de saldo. Capacidad Gold Keys no observable por board/Trading; el alert Silver→Gold lleno aporta el bloqueo causal. Conversiones adquiridas: 40 Weapon→10 Hero, receta Hero Weapon de 49 materiales y 10 Bronze→2 Silver. Los facts frescos siguen autorizando cada operación económica, no un saldo calculado persistente. Procedencia histórica: [reconstrucción](POST_V1_RESOURCE_ROUTING_RECONSTRUCTION.md); policy y wiring: [RESOURCE_ROUTING](RESOURCE_ROUTING.md).

**USER_GT:** tras confirmar `Mass Combine` una sola vez en `[Ethereal] Random Part` aparece una animación de resultado cuyo item concreto es irrelevante y puede variar; no se modela por resultado y no requiere el landmark de espada. Se atraviesa con taps fuera del item/botón visible hasta recuperar de forma fresca y estable `Combine → Transmute → [Ethereal] Random Part`. Es la misma clase de mecánica que las demás animaciones cancelables: el contrato es recuperar el BASE, no reconocer el resultado.

## Equipment Inventory / Sell — USER_GT definitivo 2026-10-02

- La lista total se ordena por poder que otorgaría al equipar; su tail es el menor poder. La capacidad comprada limita cuáles slots son seleccionables: puede haber items de menor tier existentes pero inaccesibles debajo del tail adquirido. No buscar arbitrariamente el tier mínimo en la lista total.
- `Item Count: HAVE / NEED` es la autoridad de cantidad y capacidad. Full cuando `HAVE >= NEED`; terminar inmediatamente cuando `HAVE < NEED`. Grid de 4 columnas, 4 filas por página: 16 slots/página, 4 slots/fila. Último slot accesible (índice cero): `min(HAVE, NEED)-1`; página `index//16+1`, posición `index%16`. Próxima fila comprable comienza en índice `NEED`, página `NEED//16+1`, fila `(NEED%16)//4`.
- Cada compra con Karats agrega exactamente una fila (+4 slots). Sólo se compra la fila siguiente, secuencialmente; no se saltan filas ni se compran varias preventivamente. Leer coste/acción y confirmar una vez; verificar `capacity_new == capacity_old+4` con Item Count fresco. Efecto inconcluso no autoriza repetir.
- Legendary, Epic, Rare, Normal y Poor son descartables sin policy por level, enhancement, duplicados, identidad o transcendence. Bulk separa las familias `equipment` y `enhance`. Un Normal lvl 5 sigue siendo descartable.
- Ethereal equipment es configurable por tipo exacto, en ambas direcciones. Weapon: Weapon. Armor: Helmet, Chest, Pants, Gloves, Boots. Accessories: Earrings, Necklace, Ring. Default: Weapon/Earrings/Necklace/Ring protegidos; cinco Armor vendibles. Ethereal Enhance es una opción independiente; no se mezcla con la opción del tipo equipment. Su default conservador de implementación es protegido (USER_GT no fijó default).
- Todo Ethereal+ equipment y Ethereal+ Enhance están permanentemente protegidos, sin excepción configurable. Ethereal+ constituye el límite superior del scan hacia atrás. Locked no puede venderse; Equipped no es candidato efectivo.
- Sólo Bulk es venta productiva autorizada, nunca individual. Antes de confirmar: tier, tipo/grupo cuando corresponda y policy, con panel y popup como guards redundantes; frame/tier, nombre/color y disponibilidad Bulk aportan evidencia. Ethereal+ no permite Bulk, defensa adicional que no sustituye clasificación. UNKNOWN/contradicción/ambigüedad nunca autorizan venta.
- Después de Combine, venta o compra no se reutiliza índice/scan. Cada nueva evaluación empieza con Item Count/capacidad frescos, tail accesible calculado y primer candidato vendible hacia atrás; detener al alcanzar cualquier Ethereal+ sin candidato. La salida y su routing se definen en RESOURCE_ROUTING.

## Point Reward — USER_GT establecido

`Point Reward` MW: MODAL establecido por USER_GT que puede aparecer por encima de CLEAR al cruzar ciertos conquest points (adquirido 2026-09-29: `+2 Gem` por `20000 Conquest Points`). Se cierra sólo con su botón OK; inmediatamente debajo queda CLEAR; tocar fuera o sobre otras zonas no lo cierra; no es overlay ni tap-through. Identidad productiva: rasgos estables del MODAL (título); la línea de recompensa variable queda fuera de identidad.

## UNKNOWN deliberados

- Fill All con Gold insuficiente: comportamiento no confirmado, baja prioridad; expectativa del usuario de compra parcial y aviso posterior **no es GT**. No adquirir ahora ni bloquear MW.
- Extremo animado no muestreado de Heaven & Hell: límite geométrico residual descrito arriba, no duda sobre dónde puede aparecer.

Ante una nueva superficie real: describirla aquí como UNKNOWN, sin asignar clase, y pedir USER_GT antes de implementarla. Badges, botones y modos técnicos no crean contextos.
