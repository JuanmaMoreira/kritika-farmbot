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

**USER_GT 2026-10-02, retorno Trading:** Trading Center es MODAL sobre la superficie caller. Desde MW, X normalmente restaura MW; close → snapshot fresco → reclasificar. MW confirmado continúa el mismo flow sin Back ni re-entry. Sólo Lobby confirmado habilita recovery/re-entry bounded; otro contexto lo resuelve su owner. UNKNOWN/AMBIGUOUS espera/reclasifica o usa recovery seguro existente, nunca Back preventivo.

- Back recuerda la BASE inmediatamente anterior. Encadenar BASE→Quick Menu→otra BASE cambia el retorno. Un relief productivo restaura su caller BASE antes de navegar a otra; no encadenar BASEs extra si importa ese retorno.
- MODAL/OVERLAY no crean caller BASE. Close/Cancel vuelve al parent subyacente donde esté establecido; no generalizar gestos de cierre no verificados.
- Craft bloqueado: `Craft → Equipment Full → acceso directo a Combine desde el blocker → relief → Back → Craft`. No existe motivo productivo para Craft limpio→Combine en este relief; no inventar ruta Quick Menu.
- Socket todavía lleno tras Combine/Sell es el blocker **post-relief**, distinto del popup inicial. Elegir No deja la tarea incompleta y se continúa con el siguiente personaje; fuera del scope positivo de relief.
- Equipment detail: no hay X; cerrar tocando afuera, preferentemente la región superior no interactuable entre Karats y `?` junto a Back. **No Back**: regresaría desde Equipment Inventory a su caller. No hay coordenada exacta canónica en este contrato.
- Craft recipe/quantity: Cancel vuelve a la misma Craft BASE.
- **USER_GT (2026-10-01):** `Craft → Inventory → Back → Craft → Back → Lobby` es una secuencia determinista. Lobby es su postcondition normal, no failure ni recovery inesperado. Craft conserva su entrada directa; no agregar `MW → Inventory → MW` preventivo. Desde ese Lobby se continúa por navegación normal a Battle Mode Select y MW.
- **LIVE_EVIDENCE (2026-10-02):** `MW → Inventory → Back → MW → Back → Lobby` conserva esa historia de BASE. Lobby limpio es un destino normal conocido; la activity reusable restablece Battle Mode Select mediante navegación normal sólo en esta rama, sin otro Back ni consumo.
- **LIVE_EVIDENCE (2026-10-05):** en Cat Acrobat, `WB → QM Inventory → Back → WB` restaura WB (secuencias134→194→229, adquisición `4d203684`). El siguiente Back devuelve Lobby, confirmado físicamente; restaurar hub sólo desde ese destino fresco. No demuestra una salida directa hub tras Inventory.
- **USER_GT (2026-10-05):** WB también debe intentar Sell Equipment cuando un nuevo Start confirma Full después de Combine. El contrato Combine-only era anterior a la implementación productiva de Sell; no debe trasladar ese blocker sin resolver a MW.
- Pets Combine All y Mass Evolve Normal/Rare: No devuelve exactamente el parent/estado subyacente Pet Combine o Pet Summon, o Pets Manage si allí aplica esa confirmación; no inferir otras rutas.
- **USER_GT (2026-10-03):** desde Select Battle Mode limpio un Back vuelve directamente a Lobby. En la secuencia `MW → Back → Select Battle Mode → Back → Lobby` es el segundo Back; no se autoriza Back sobre UNKNOWN/modal.
- Trading abierto desde Quick Menu conserva el parent; X restaura ese parent (Craft y Treasure establecidos). Treasure sí cambia de BASE.
- MW tooltip (`overlay.monster_wave_usage_tooltip`): un tap en Sapphires abre; segundo tap sobre el tooltip cierra. Estrategia aceptada: double tap, ignorar normalmente el transitorio; si el segundo se pierde, puede reconocerse y manejarse. No requiere state machine nueva.

## Entradas entre flows — USER_GT corregido 2026-10-04

- Mailbox y Daily Quests son destinos Quick Menu; cerrar cualquiera restaura la BASE que
  estaba debajo. No requieren Lobby: MW→QM→Quests→close→MW→QM→Mailbox→close→MW es válido.
- Rotation/Character Select puede iniciarse por QM desde una BASE verificada que lo permita.
  Lobby sigue válido sin ser obligatorio ni preferido. La entrada a Character Select no requiere Lobby previo.
- Battle Mode Select tiene Quick Menu. Para Lobby gana Back directo (un tap); para
  Pets/Quests/Mailbox/Character Select el destino QM directo evita Lobby.
- Availability depende de la BASE/contexto, no es universal. Catálogo acreditado:
  Lobby, Guild, Pet Summon, Pets Manage, Treasure, World Boss BASE, Monster Wave BASE,
  Battle Mode Select. MODAL superior, UNKNOWN/AMBIGUOUS y batalla/gameplay activo no autorizan QM.
- Las coordenadas shifted de Quests (.395, .205) y Mailbox (.267, .205) están visibles en
  la captura existente `artifacts/hil_j_navigation/20260922/01_mw_quick_menu.png`. Evidencia adquirida previamente; USER_GT confirma la ruta y el retorno al origen.
- World Boss, Monster Wave y Tower of Tribulation comparten Battle Mode Select como parent.
- MW limpio admite Quick Menu→Pets y Quick Menu→Lobby directos. Quick Menu es un router de
  destinos, no implica pasar por Lobby. Tile Pets shifted visible en evidencia existente
  `artifacts/hil_j_navigation/20260922/01_mw_quick_menu.png`; target normalizado (.395, .350)
  medido offline. La ruta fue aportada por USER_GT; nuevo tap no se readquirió live.
- La historia BASE/Back se conserva: entrar a Pets por Quick Menu no demuestra parent Lobby.
- Composición económica futura aportada: WB→MW→ToT; WB no se supone elegible después de MW.
  MW productivo alivia hasta <102; ToT daily requiere su propio ≥1, incluso si MW fue NO_WORK.
  Estas relaciones no agregan ToT daily ni reordenan rutinas.

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

**USER_GT (2026-10-04):** Sapphires también es legible por OCR desde Select Battle Mode.
No hace falta salir a Lobby para decidir la entrada MW desde ese hub acreditado.

Evidencia física previa curada (procedencia en [contrato SKIP archivado](legacy/DOC_RESET_20260925.md) y [reconstrucción](POST_V1_RESOURCE_ROUTING_RECONSTRUCTION.md), no inferencia del detector): SKIP se activa con tickets completos (30/30 en el caso adquirido; VIP puede reducir el requisito). Fill All compra faltantes a 140.000 Gold por ticket; completar tickets no activa SKIP automáticamente. El estado/timer es account-wide y se debe observar fresco, sin fijar duración a partir de un ejemplo. La misión Daily MW requiere x4; eso no limita MW productivo ni autoriza un gate Daily. **USER_GT / product policy:** MW no tiene Eligibility; su objetivo es gastar Sapphires, liberar capacidad y obtener rewards incluso con Daily completada. USER_GT actualizado (2026-10-03): capacidad/base relevante102; Stages sólo necesita saldo <102. MW productivo aplica el mínimo número de entradas para salir de pressure, no vacía por objetivo. Saldo fresco <102 omite navegación; saldo >=102 autoriza inversión. Ejemplos aceptados sin nuevos ingresos: 101→0 entradas; 102→1; 201→1→101; 299→2→99; 300→2→100. Cada CLEAR requiere saldo fresco: no acreditar el efecto aritméticamente.

El board MW muestra balances/límites, no rewards entrantes exactos ni recetas; drops no deterministas no autorizan predicción de saldo. Capacidad Gold Keys no observable por board/Trading; el alert Silver→Gold lleno aporta el bloqueo causal. Conversiones adquiridas: 40 Weapon→10 Hero, receta Hero Weapon de 49 materiales y 10 Bronze→2 Silver. Los facts frescos siguen autorizando cada operación económica, no un saldo calculado persistente. Procedencia histórica: [reconstrucción](POST_V1_RESOURCE_ROUTING_RECONSTRUCTION.md); policy y wiring: [RESOURCE_ROUTING](RESOURCE_ROUTING.md).

**LIVE_EVIDENCE (2026-10-04, Demon Blade):** Hero Armor → Helmet con 114/999 materiales,
costo 49 por unidad; MAX mostró 2/10. Una confirmación produjo `Laoku's Destructive Helmet`;
tras cerrar el resultado, Craft mostró 16/999. Selector/MAX/resultado/decremento adquiridos
en [manifest de replay](../tests/fixtures/craft_armor/manifest.json). No acredita resultados
de Accessories ni otros tiers/recetas por analogía.

**USER_GT:** tras confirmar `Mass Combine` una sola vez en `[Ethereal] Random Part` aparece una animación de resultado cuyo item concreto es irrelevante y puede variar; no se modela por resultado y no requiere el landmark de espada. Se atraviesa con taps fuera del item/botón visible hasta recuperar de forma fresca y estable `Combine → Transmute → [Ethereal] Random Part`. Es la misma clase de mecánica que las demás animaciones cancelables: el contrato es recuperar el BASE, no reconocer el resultado.

## Equipment Inventory / Sell — USER_GT definitivo 2026-10-02

- La lista total se ordena por poder que otorgaría al equipar; su tail es el menor poder. La capacidad comprada limita cuáles slots son seleccionables: puede haber items de menor tier existentes pero inaccesibles debajo del tail adquirido. No buscar arbitrariamente el tier mínimo en la lista total.
- **USER_GT (2026-10-02, bloques visuales):** items del mismo tier y mismo tipo ofrecen los mismos stats relevantes y, por tanto, el mismo combat power potencial; aparecen agrupados contiguamente en el orden del inventario. El item tiene un glow animado: una banda blanca semitransparente diagonal lo atraviesa aproximadamente cada 1.5 s. Estos hechos físicos no autorizan Sell por similitud visual; la implementación y calibración del salto de bloque están en [ROADMAP](../ROADMAP.md#protected-block-scan-acceleration).
- `Item Count: HAVE / NEED` es la autoridad de cantidad y capacidad. Full cuando `HAVE >= NEED`; terminar inmediatamente cuando `HAVE < NEED`. Grid de 4 columnas, 4 filas por página: 16 slots/página, 4 slots/fila. Último slot accesible (índice cero): `min(HAVE, NEED)-1`; página `index//16+1`, posición `index%16`. Próxima fila comprable comienza en índice `NEED`, página `NEED//16+1`, fila `(NEED%16)//4`.
- Cada compra con Karats agrega exactamente una fila (+4 slots). Sólo se compra la fila siguiente, secuencialmente; no se saltan filas ni se compran varias preventivamente. Leer coste/acción y confirmar una vez; verificar `capacity_new == capacity_old+4` con Item Count fresco. Efecto inconcluso no autoriza repetir.
- Legendary, Epic, Rare, Normal y Poor son descartables sin policy por level, enhancement, duplicados, identidad o transcendence. Bulk separa las familias `equipment` y `enhance`. Un Normal lvl 5 sigue siendo descartable.
- Ethereal equipment es configurable por tipo exacto, en ambas direcciones. Weapon: Weapon. Armor: Helmet, Chest, Pants, Gloves, Boots. Accessories: Earrings, Necklace, Ring. Default: Weapon/Earrings/Necklace/Ring protegidos; cinco Armor vendibles. Ethereal Enhance es una opción independiente; no se mezcla con la opción del tipo equipment. Su default conservador de implementación es protegido (USER_GT no fijó default).
- Todo Ethereal+ equipment y Ethereal+ Enhance están permanentemente protegidos, sin excepción configurable. Ethereal+ constituye el límite superior del scan hacia atrás. Locked no puede venderse; Equipped no es candidato efectivo.
- Sólo Bulk es venta productiva autorizada, nunca individual. Antes de confirmar: tier, tipo/grupo cuando corresponda y policy, con panel y popup como guards redundantes; frame/tier, nombre/color y disponibilidad Bulk aportan evidencia. Ethereal+ no permite Bulk, defensa adicional que no sustituye clasificación. UNKNOWN/contradicción/ambigüedad nunca autorizan venta.
- **USER_GT corregido (2026-10-02): Bulk elimina exactamente el bloque vendido y preserva el orden relativo del resto.** Item Count antes/después permite conocer la cantidad eliminada; los items posteriores se desplazan esa cantidad y, si sigue Full, entran nuevos items al prefix accesible. Expansión +4 cambia ese prefix. El contrato de invalidación/transformación del scan está en RESOURCE_ROUTING y ARCHITECTURE.

## Ordered lists — USER_GT y LIVE_EVIDENCE 2026-10-04

- **USER_GT corregido:** Character Select cambia el orden según el orden de entrada
  de personajes. No existe correspondencia persistente identidad↔índice absoluto.
- **LIVE_EVIDENCE Trading General:** el top actual incluye seis ofertas Rune y Epic
  Ticket temporales antes de Lapiz 400; ese prefix difiere del catálogo histórico.
  Dentro de esta adquisición, el suffix conserva este orden: Lapiz 400 → Stamina 100
  → 10M Gold Pouch → Gold 10M → Sapphire 5 → Brawler's Badge → Lapiz 5 → Ring Enhance
  → Melee Badge → Accessory Material → Weapon Material → Hero Weapon Material
  → Hero Armor Material → Hero Accessory Material → R Ticket → K Coin → Guild Commodity.
  La longitud/identidad futura del prefix temporal no está acreditada.
- **LIVE_EVIDENCE Trading:** lista vertical; swipe hacia arriba expone filas posteriores.
  Frame nativo 2712×1220, pitch normalizado .1418, viewport Y .35–.95 y aproximadamente
  cuatro filas completas. No snap-to-row observado; desplazamiento depende de travel,
  duración/inercia y clipping. .90→.40 a 900 ms desplazó aproximadamente .54–.55 del
  viewport; .94→.40 a 650 ms mostró variación registrada en el benchmark curado.
- **LIVE_EVIDENCE bounds:** General retorna al top de ofertas al reseleccionar su tab;
  Guild Commodity es el último row del suffix. Gestos extra al bottom no desplazan
  sostenidamente la lista; el gesto que alcanza el límite se clippea.
- **LIVE_EVIDENCE calibración coarse estabilizada:** lane X .33, inicio Y .94. Inicios
  .945 y más bajos entran fuera del área fiable y pueden registrar sólo ≈3 filas.
  Terminar arriba del viewport aumenta el travel útil: perfil .94→.02 a 250 ms,
  seis muestras, desplazamiento min/med/max 8.62/8.95/9.51 filas. Extender hasta Y=0
  a 250 ms dio 8.30/9.14/9.63 en seis muestras: mayor travel no mejoró el mínimo.
  .94→.02 a 180 ms (33 muestras) dio 8.09/9.06/10.21; a 120 ms (3) 7.96/9.75/9.94.
  40 ms con travel .59 fue inconsistente: 3.01–6.07 filas. No se observó que un
  único gesto desde el top actual alcanzara Hero Weapon Materials.
- **LIVE_EVIDENCE física dirigida:** desde anchor estabilizado, 250 ms forward con
  travel .14/.34/.59/.84/.92 desplazó medianas 1.23/3.21/5.93/7.95/8.67 filas
  (tres muestras por distancia); reverse desde Y=.36 con travel .14/.34/.58,
  medianas 1.28/3.27/5.64 filas hacia top. No hay igualdad nominal travel↔desplazamiento.
  Safe window conservadora de centro de fila completa: Y .43–.87; centro .65.
  [Distribuciones y protocolo](../datasets/trading_swipe_calibration.json).
  Los PNG nativos se fechan antes de adquirir pixels: fechar al final de transferencia
  había admitido frames transitorios y queda descartado como medición estabilizada.
- **LIVE_EVIDENCE títulos:** los nueve assets focalizados y strips de replay conservan
  identidad, posición y procedencia. [Manifest anchors](../datasets/trading_ordered_anchors_manifest.json),
  [replay](../datasets/ordered_navigation_replay.json), [movimiento medido](../datasets/trading_targeted_benchmark.json).
  Currency/Stamina 50 y las dos primeras filas Avatars & Keys conservan su GT propio.

## Point Reward — USER_GT establecido

`Point Reward` MW: MODAL establecido por USER_GT que puede aparecer por encima de CLEAR al cruzar ciertos conquest points (adquirido 2026-09-29: `+2 Gem` por `20000 Conquest Points`). Se cierra sólo con su botón OK; inmediatamente debajo queda CLEAR; tocar fuera o sobre otras zonas no lo cierra; no es overlay ni tap-through. Identidad productiva: rasgos estables del MODAL (título); la línea de recompensa variable queda fuera de identidad.

## UNKNOWN deliberados

- Fill All con Gold insuficiente: comportamiento no confirmado, baja prioridad; expectativa del usuario de compra parcial y aviso posterior **no es GT**. No adquirir ahora ni bloquear MW.
- Extremo animado no muestreado de Heaven & Hell: límite geométrico residual descrito arriba, no duda sobre dónde puede aparecer.

Ante una nueva superficie real: describirla aquí como UNKNOWN, sin asignar clase, y pedir USER_GT antes de implementarla. Badges, botones y modos técnicos no crean contextos.

## Stages Daily ads-only — USER_GT y adquisición 2026-10-02

- **USER_GT:** Stages se accede sólo desde Lobby → Stage, encima de Survival; no existe Quick Menu → Stages. Entrada productiva con Stamina ≥300 y Sapphires <102 (espacio/no rojo). Después de un ad exitoso: Results/config close/Back permiten volver a Lobby; combate/manual no forman parte del GT adquirido de este flow.
- **USER_GT / LIVE_EVIDENCE:** Trading Center → Currency → primera fila Stamina: 50 por trade, coste 200 K Coins. Selector inicial 1/20; cada `>` incrementa un trade. Pool K Coins intencionalmente amplio. Una cantidad N confirmada entrega N×50 Stamina; cap/currency/efecto deben corresponder al panel adquirido. La fórmula/bounds del batch pertenecen a RESOURCE_ROUTING.
- Normal/Elite tiene memoria por personaje. Panel inferior izquierdo `Stamina Use Event (Normal/Elite)`; portal rojo dice Normal cuando se está en Elite. Claim cyan activo entrega reward; puede aparecer popup de reward. **USER_GT 2026-10-02:** tocar Claim inactivo es harmless y Claims no cambia el episodio. Los bounds/percepción del loop pertenecen a ARCHITECTURE/RESOURCE_ROUTING.
- Objetivo único Abyssal Rion; título centrado arriba debajo de Karats. **USER_GT:** verificar primero el episodio con template CV fresco en Normal (también tras Elite→Normal). **LIVE_EVIDENCE 2026-10-02:** el broadcast global cubre la mitad superior del título, causando PRE NCC0.783/score0 vs POST0.9997. El template conserva el ancho de la frase completa y usa su franja inferior libre (y0.169–0.184), threshold0.94 y guard de brillo sin cambios: PRE0.9882, POST1.0; episodio ajeno0.1148 y dropdown0.2335 raw, ambos negativos. Si Abyssal Rion está confirmado, ir directamente a Stage8 sin World Map. Identidad desconocida usa la resolución bounded vigente y exige confirmación fresca posterior. World Map a la izquierda del portal abre dropdown; objetivo en tail con tres estrellas. Seleccionar y cerrar dropdown con World Map si sigue tapando título. Stage 8, anteúltimo, abre MODAL de configuración.
- Mao tiene 30 tickets. `Support Activated` = ACTIVE. NEEDS_TICKETS → Get Support → MODAL superior → Fill All → tickets30/30 READY → cerrar → Get Support verde → ACTIVE. Comprar tickets no activa buff. Adquirido20→30 por300000 Gold (30000/ticket).
- Penance es la dificultad máxima requerida. Start abre MODAL Select Striker; Auto Repeat/Continue abre MODAL SKIP. `300(MAX)` y `Video(2)/(1)/(0)` son visibles. x4 manual equivale a60 Stamina: primer tap abre overlay, segundo selecciona/cierra. Esa interacción no se usa en ads-only.
- Optional Video Pass Ticket: siempre No; No inicia el ad automáticamente. Adquirido popup con cinco tickets, nunca Yes. Tras ad: breve carga → Results → OK → configuración → X → Normal Abyssal → Back → Lobby. Saldo Sapphire after > before prueba producción, sin delta fijo adquirido.
- **LIVE_EVIDENCE:** Video(0) mostró `You have used up all daily video watch attempts for this mode. Please come back tomorrow or try again with a different character.` Agotamiento diario explícito, distinto de No Ads Available temporal.

### Ads — evidencia física conocida

- Google `com.google.android.gms.ads.AdActivity` corre bajo el mismo package de Kritika; main adquirido es `com.hive.HiveUnityPlayerActivity`. En este Samsung, `dumpsys window` completo aporta foco y `windows` no. UIAutomator adquirido sólo expone root/WebView, sin Close/Continue accesibles.
- Back temprano live abortó y devolvió main sin results. Back con chrome SDK `Reward granted` cerró y produjo results. Una variante abrió Finsky/Play Store automáticamente; Back permitió recuperar superficie ad, sin tocar CTA. Package/activity no prueban reward ni que ya se pueda cerrar.
- **USER_GT posterior:** un ad triple aún avanzaba al cierre prematuro de60 s y tenía barra de progreso visible. **LIVE_EVIDENCE:** barra amarilla superior SDK avanzó .264→.918 en cinco capturas; después desapareció y apareció Reward granted. Una barra puede resetear entre etapas. Progreso visible prueba actividad, no finalización; desaparecida/estática/fragmentada no prueba reward. El antiguo supuesto60s=terminado queda stale. Bounds y policy son contrato de software en ARCHITECTURE.
- **USER_GT:** No Ads Available normalmente admite retry temporal (~5 s) o salir a Character Select y reentrar al MISMO personaje; no es automáticamente daily exhaustion. **LIVE_EVIDENCE:** reset aislado conservó identidad antes/selección/Lobby. No apareció No Ads temporal nativo ni se ejercitó su cadena completa; límites de retry y fallback provisional constan en RESOURCE_ROUTING.

USER_GT (2026-10-02/03), Combine result animations: after the one effective confirmation, use bounded lateral taps on the existing noninteractive safe point (0.15, 0.50) under the result overlay until the known panel/menu is recovered. No animation stability requirement before starting TapThroughAnimation; a popup-close frame before animation onset is not completion. Never repeat confirmation because an effect/animation wait is inconclusive.

### No Ads Available: recovery confirmado 2026-10-03

- **USER_GT:** al aparecer indisponibilidad temporal, hacer al menos dos retries separados por 5–6 segundos. Si persiste, salir a Character Select y reentrar al mismo personaje; un intento final. Esta transición no es Rotation. Si persiste después del recovery, registrar indisponibilidad y continuar al siguiente personaje; no hacer entrada manual sin ads.
- **LIVE_EVIDENCE:** el alert adquirido muestra `Loading... (If the video does not load, please visit the [Select Character] screen and try again.)` sobre Auto con botón OK. Es el caso de indisponibilidad observado por el usuario; no contiene Video0 ni el alert diario. No se adquirió aún un frame nativo con texto literal `No Ads Available`.
