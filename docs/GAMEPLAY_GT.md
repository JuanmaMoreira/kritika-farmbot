# Gameplay / UI — GT canónico

Fuente durable de estructura física y mecánicas que condicionan el diseño. `USER_GT` es la declaración explícita del usuario consolidada aquí; sólo nueva `LIVE_EVIDENCE` físicamente contradictoria la reabre. Replay, OCR, detector, resolver y heurísticas no la sustituyen. Implementación actual: [CONTEXT](../CONTEXT.md); software: [ARCHITECTURE](../ARCHITECTURE.md).

## Clases físicas — USER_GT

Sólo `BASE | MODAL | OVERLAY | EXEMPT`. Cada BASE declara `battle_surface`. Nombres `screen.*`, `popup.*`, reglas del resolver y ownership de código no clasifican la UI. Una tabla agrupada aplica la clase a cada superficie enumerada.

| class | Superficies físicas | battle_surface |
| --- | --- | --- |
| BASE | Lobby; Battle Mode Select; Monster Wave; Craft; Equipment Inventory; Meteorites; Socket; Treasure; Combine; Guild; Pets Manage; Pet Summon; Pet Combine; World Boss | false |
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
| OVERLAY | Craft result; Treasure selector y result/reward; MW Sapphires/MAX tooltip; Equipment detail; Meteorite detail; Combine animation/result | — |
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

**USER_GT (2026-10-06, MW):** MAX se selecciona una sola vez por personaje y
permanece seleccionado durante los passes y preparaciones siguientes. La operación
inicial conserva los dos taps consecutivos del control; persistencia no autoriza retap.

**USER_GT / LIVE_EVIDENCE (2026-10-06, Trading Keys):** la fila `Silver Key 2`
consume Bronze y la fila `Gold Key 2` consume Silver; el par debajo del icono
de entrada es inventario disponible / coste por trade. Bronze `6/10` no permite
un trade; Silver `15/10` permite uno. El Item Trade de Gold Key muestra Silver
`(15/10)` y cantidad inicial `1/20`: numerador = trades seleccionados,
denominador = límite del batch, distinto de la cantidad de Silver disponible.
La oferta produce dos Gold Keys por trade. No revela capacidad Gold libre.
Captura preservada y apertura única sin confirm en
[informe Trading](TRADING_FAILED_SESSION_A94AC2E7.md).

**LIVE_EVIDENCE (2026-10-04, Demon Blade):** Hero Armor → Helmet con 114/999 materiales,
costo 49 por unidad; MAX mostró 2/10. Una confirmación produjo `Laoku's Destructive Helmet`;
tras cerrar el resultado, Craft mostró 16/999. Selector/MAX/resultado/decremento adquiridos
en [manifest de replay](../tests/fixtures/craft_armor/manifest.json). No acredita resultados
de Accessories ni otros tiers/recetas por analogía.

**USER_GT:** tras confirmar `Mass Combine` una sola vez en `[Ethereal] Random Part` aparece una animación de resultado cuyo item concreto es irrelevante y puede variar; no se modela por resultado y no requiere el landmark de espada. Se atraviesa con taps fuera del item/botón visible hasta recuperar de forma fresca y estable `Combine → Transmute → [Ethereal] Random Part`. Es la misma clase de mecánica que las demás animaciones cancelables: el contrato es recuperar el BASE, no reconocer el resultado.

## Meteorites — USER_GT y adquisición 2026-10-08

**USER_GT:** Meteorites es una BASE autónoma, `battle_surface=false`, accesible
por Lobby directo y Quick Menu. Siempre entra en tab **Meteorites**, Bag página 1;
el set activo 1/2/3 se recuerda por personaje. Tab, página y set son dimensiones
independientes. Después de usar el set compartido se restaura **Set 1**.
Los otros tabs son vistas internas: Combine, Evolve, Reforge y Reroll.

**USER_GT, orden y contrato:** 16 meteoritos por página. Primero los equipados
en algún set del personaje (incluidos Flare), luego Flare desequipados y luego
normales desequipados; dentro de cada grupo, tier y nivel. El conjunto compartido
contiene 10 normales y 1 Flare, todos Ethereal+ y nivel >0. Bajo las precondiciones,
el Flare compartido está en las posiciones absolutas 1–12, página 1.

Precondiciones **USER_GT**, asumidas por el algoritmo sin auditoría exhaustiva:

1. El beneficiario no tiene Ethereal+ mejorados que alteren el orden esperado.
2. Sus meteoritos originales, si existen, están en Set 1.
3. Set 2 y Set 3 comienzan vacíos.
4. Existe el conjunto compartido completo, desequipado: 10 normales + 1 Flare,
   Ethereal+, nivel positivo.
5. No hay otro conjunto desequipado con esas características que interfiera.

**USER_GT aclarado en chat:** `berserker`, `demon_blade` y `kaiserin` omiten la
preparación compartida completa. `burst_breaker` **no** es excepción. Son stable IDs,
no inferencias desde el texto de stats. No son cinco verificadores nuevos.

**USER_GT B2, lifecycle:** Change Meteorites pertenece a la rutina completa.
Activarlo declara que el usuario preparó el set desequipado bajo los cinco supuestos;
no hay confirmación por personaje ni auditoría completa. Setup precede al primer
paso y cleanup sigue al último antes de Rotation o completion sin Rotation.
Un flow que termina normalmente no finaliza el scope. Sólo stable ID acreditado
permite operaciones; los tres exceptuados anteriores omiten ambos procedimientos.
Stop Safely intenta liberación verificada únicamente desde contexto conocido;
FAILED/estado incierto no autoriza cleanup ciego ni Rotation. Tras interrupción
incierta se requiere restablecer manualmente el set desequipado antes de reanudar.

**LIVE_EVIDENCE B2 2026-10-08:** rutina real Change Meteorites ON, stable ID
`telumpel` acreditado:11 Equip → Send Stamina COMPLETED/Lobby →11 Unequip → Set 1
→ Session COMPLETED sin Rotation. Flare+30pos1, frontera5/ancla14 estable. Set 2
vacío por efectos individuales, Set 1 activo/página1/vacío, sin overlay/Loading;
0 retries. Confirma ownership Session en finalización sin Rotation; no campaña roster
ni prueba live de Stop Safely. [Informe B2](METEORITES_B2_20261008.md).

**USER_GT, semántica:** hay 12 tipos contando Flare. Cada tipo conserva su sprite
entre tiers; el marco expresa tier. Un mismo meteorito puede pertenecer a varios
sets dentro del mismo personaje; el flow futuro no usará esa capacidad. Flare
potencia los demás meteoritos: con los otros slots vacíos, equiparlo no cambia CP.
El control lateral superior Equip/Unequip realiza la acción sobre el set activo;
el botón inferior con candado y texto Unequip gestiona el lock, y se ignora.

**USER_GT 2026-10-09:** mantener un tap sobre un item/meteorito abre un OVERLAY
informativo, distinto del detalle accionable con Equip/Unequip lateral. Se cierra
con un tap en un costado no disruptivo. El panel Fury+30 desplazado de la aceptación
Arena corresponde a ese long press; su botón inferior de lock no autoriza Equip.
El log emitió `input tap`, sin medir DOWN→UP físico; no demuestra por qué Android
lo interpretó como long press.

**LIVE_EVIDENCE**, personaje `rang`, corpus y límites en
[manifest](../datasets/meteorites_hil_20261008_manifest.json) e
[informe](METEORITES_HIL_ACQUISITION_20261008.md):

- Lobby directo abrió Meteorites/página 1/Set 1. Sets 2 y 3 vacíos adquiridos.
  Check amarillo encima del botón identifica set activo. Reroll/página 2 → Back
  → Lobby → QM Meteorites volvió a Meteorites/página 1 y conservó Set 3.
- Bag 4×4; la muestra mostró 1/40 y 2/40 con flechas adelante/atrás; página 1
  no mostró flecha atrás. Esto no demuestra que todas las páginas estén llenas.
- Inicialmente: posiciones 1–11 originales equipadas en Set 1; 12–15 Flare
  desequipados; primer normal desequipado 16. Flare E+ +30 pasó de 12 a 1 al
  equiparlo en Set 2, ocupó el centro y obtuvo E verde. CP permaneció igual.
- Hipótesis posicional parcialmente acreditada: `anchor = 16 + 9 = 25`
  (índices absolutos **uno-based**, página 2/celda 9). Equip desde ese índice tomó
  Evasion +20, luego Shield +21; tras cada acción el siguiente normal quedó en 25.
  La frontera normal avanzó 16→17→18: conservar el ancla inicial, no recalcularla
  desde la frontera móvil. Dos normales prueban esos pasos; no un recorrido de diez
  ni todas las configuraciones de inventario.
- Los tres Equip cerraron detail, atravesaron Loading y retornaron a página 1,
  con slot nuevo y marca E frescos. Los tres Unequip se adquirieron individualmente
  desde posición 1, con identidad/acción lateral verificadas: Flare, Shield, Evasion.
  Cada acción vació su slot, retiró E y reordenó Bag. No se repitió una acción incierta.
- La E verde y la acción lateral reflejan el **set activo**. Al activar Set 2/3
  vacío, desaparecieron las E de originales que seguían equipados en Set 1;
  su overlay conservó `Equipped: DRAKEN四R` y ofreció Equip. Ausencia de E no
  demuestra que el item esté globalmente desequipado.
- Detail muestra tier/tipo/nivel positivo en el título: `Ethereal+ Meteorite
  Flare (ATK) +30`, `(Evasion) +20`, `(Shield) +21`. En cero, el título omite el
  sufijo; la barra inferior muestra `+0`. Concentration E+ y Flare Ethereal cero
  adquiridos: no convertir un sufijo ilegible/ausente por fallo OCR en cero.
- Ethereal y Ethereal+ tienen título rojo. Ethereal+ agrega ornamento dorado al
  marco rojo; Ethereal simple carece de éste. Sprite Flare conservado entre ambos.
  `+30`/`MAX` alternan en el mismo E+; glare diagonal cambia pixels sin cambiar item.
- Selección tiene contorno amarillo en Bag. Tocar fondo vacío (.89,.30), geometría
  normalizada del frame adquirido, cerró detail sin Back ni cambio de set/página.
- Loading puede conservar Bag/slots anteriores y desaparecer después del cierre
  del overlay. Check de set nuevo tampoco acredita por sí solo slots ya cargados.
  CP/toast puede llegar después del efecto o persistir: no es gate único.
- Cleanup físico acreditado: tres items de prueba desequipados, Set 2 vacío;
  Set 1 activo, sus 11 slots originales y CP inicial restaurados, tab Meteorites/página 1.

**USER_GT, no-efecto conocido:** ocasionalmente Equip no responde para un item;
manualmente se resuelve seleccionando otro y regresando al ancla. No ocurrió en
esta adquisición y no se ejercitó retry live. El recovery productivo acotado de
Fase A/B1 está probado offline; el workaround manual no está implementado.
Loading, timeout, OCR miss o UNKNOWN no acreditan no-efecto ni autorizan repetir.

**USER_GT adicional 2026-10-08, Fase A:** Flare ocupa siempre el centro.
Los diez normales se asignan secuencialmente en el orden físico:

```text
10   1   2   3
 9   FLARE  4
 8   7   6   5
```

E verde en Bag significa equipado en el set activo. Equip se acredita por
centro/slot esperado EMPTY → OCCUPIED; Unequip por el mismo slot OCCUPIED → EMPTY.
**LIVE_EVIDENCE 2026-10-08, smoke productivo Fase A:** selección directa desde
los slots 0 (Flare +30), 2 (Shield +21) y 1 (Evasion +20) del Set 2 abrió su overlay
con acción lateral Unequip. Un único tap por item cambió el mismo slot
OCCUPIED → EMPTY, preservando los otros diez. La ruta desde slots queda acreditada;
no se necesitó fallback Bag. Antes se acreditaron tres Equip EMPTY → OCCUPIED
en centro/1/2. Final: Set 2 vacío, Set 1 activo con once originales, página 1.
Procedencia/hash/lineage en `datasets/meteorites_phase_a_smoke_20261008_manifest.json`;
capturas locales en `artifacts/meteorites_phase_a/20261008_131349/`.
Cierre, Loading, CP y tap no prueban efecto.

**LIVE_EVIDENCE 2026-10-08, aceptación B1:** cadena completa sobre personaje visible
`Drakenn19` preparado por el usuario (stable ID no inferido), bajo precondiciones
USER_GT: Flare E+ +30 posición2; Flare suffix hasta primer normal6; ancla inicial
15 = 6 + 9, reutilizada en los diez Equip normales sin recalcular. Centro y slots
1..10 acreditaron EMPTY→OCCUPIED individualmente. Cleanup directo10..1, centro al
final: once OCCUPIED→EMPTY individuales; Set 1 activo/página1, originalslot10
preservado, sin overlay/Loading. 22 inputs laterales, cero retries/reconciliación.
Esta configuración acredita el recorrido completo; no prueba todas las cantidades
posibles de inventario. Loading/CP/E no sustituyeron los cambios de slot.
[Manifest B1](../datasets/meteorites_b1_smoke_20261008_manifest.json) y
[informe](METEORITES_B1_20261008.md); raw ignorados. No-efecto sigue sin episodio live.

## Equipment Inventory / Sell — USER_GT definitivo 2026-10-02

- La lista total se ordena por poder que otorgaría al equipar; su tail es el menor poder. La capacidad comprada limita cuáles slots son seleccionables: puede haber items de menor tier existentes pero inaccesibles debajo del tail adquirido. No buscar arbitrariamente el tier mínimo en la lista total.
- **USER_GT (2026-10-02, bloques visuales):** items del mismo tier y mismo tipo ofrecen los mismos stats relevantes y, por tanto, el mismo combat power potencial; aparecen agrupados contiguamente en el orden del inventario. El item tiene un glow animado: una banda blanca semitransparente diagonal lo atraviesa aproximadamente cada 1.5 s. Estos hechos físicos no autorizan Sell por similitud visual; la implementación y calibración del salto de bloque están en [ROADMAP](../ROADMAP.md#protected-block-scan-acceleration).
- `Item Count: HAVE / NEED` es la autoridad de cantidad y capacidad. Full cuando `HAVE >= NEED`; terminar inmediatamente cuando `HAVE < NEED`. Grid de 4 columnas, 4 filas por página: 16 slots/página, 4 slots/fila. Último slot accesible (índice cero): `min(HAVE, NEED)-1`; página `index//16+1`, posición `index%16`. Próxima fila comprable comienza en índice `NEED`, página `NEED//16+1`, fila `(NEED%16)//4`.
- Cada compra con Karats agrega exactamente una fila (+4 slots). Sólo se compra la fila siguiente, secuencialmente; no se saltan filas ni se compran varias preventivamente. Leer coste/acción y confirmar una vez; verificar `capacity_new == capacity_old+4` con Item Count fresco. Efecto inconcluso no autoriza repetir.
- Legendary, Epic, Rare, Normal y Poor son descartables sin policy por level, enhancement, duplicados, identidad o transcendence. Bulk separa las familias `equipment` y `enhance`. Un Normal lvl 5 sigue siendo descartable.
- Ethereal equipment es configurable por tipo exacto, en ambas direcciones. Weapon: Weapon. Armor: Helmet, Chest, Pants, Gloves, Boots. Accessories: Earrings, Necklace, Ring. Default: Weapon/Earrings/Necklace/Ring protegidos; cinco Armor vendibles. Ethereal Enhance es una opción independiente; no se mezcla con la opción del tipo equipment. Su default conservador de implementación es protegido (USER_GT no fijó default).
- Todo Ethereal+ equipment y Ethereal+ Enhance están permanentemente protegidos, sin excepción configurable. Ethereal+ constituye el límite superior del scan hacia atrás. Locked no puede venderse; Equipped no es candidato efectivo.
- **USER_GT 2026-10-07:** el nombre seleccionado Legendary tiene tinta naranja, independientemente del nombre/tipo. **Evidencia física curada:** el título seleccionado usa Poor blanco, Normal verde, Rare azul, Epic violeta/magenta, Legendary naranja y Ethereal rojo. Ethereal+ también usa rojo: el color acredita la familia roja, pero no distingue Ethereal de Ethereal+; el marcador visible `[Ethereal+]` conserva esa distinción. Fuentes y recortes nativos en [corpus focal](../tests/fixtures/equipment_title_color/manifest.json); incluye equipment y Enhance. No hay wrapping acreditado del título seleccionado: el nombre largo Phantom Sword observado reduce su fuente; el wrapping acreditado pertenece al popup.
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

## Identidad, recursos y resets — USER_GT / LIVE_EVIDENCE 2026-10-05/06

- Los28 personajes conocidos tienen identidad por su nombre personal. Character
  Select cambia su orden según entradas; posición no identifica un personaje.
  DRAKEN一BK=Berserker, DRAKEN二DB=Demon Blade, DRAKEN三BB=Burst Breaker;
  OCR puede confundir 一 con `-`, 二 con `-`/omitido y 三 con `=`.
- Quick Menu inferior muestra Lapiz, Dark Essence, Light Essence, Nature Essence
  y K Coins. La fila superior también muestra Mao Coins, distinto de K Coins.
  Evidencia live: Demon Blade3766/455/50/24/121918 y cinco personajes adicionales,
  sin gastar recursos para crear magnitudes. El resumen se desplaza horizontalmente
  según el caller del Quick Menu; los campos son los mismos.
- Cada reset diario sincronizado entrega2 Stage Ads por personaje. Un efecto rewarded
  consume una oportunidad; Video0 indica agotamiento diario. No Ads temporal no acredita0.
- WB cierra30min antes del reset sincronizado. Countdown observado +30min define
  ese reset; Stage Ads resetea en él diariamente. WB nuevo sucede aproximadamente
  cada3 días. Hora actual04:00 local -03, cierre03:30; puede desplazarse por horario
  estacional. Live2026-10-06T02:15:52Z mostró1d4h14m: cierre aproximado
  2026-10-07T06:30Z y reset07:00Z. Display de precisión1min; no acredita segundos.
- Reward del WB anterior disponible significa recompensa anterior YES y participación
  del WB actual NO. Ranking+Damage numéricos significa participación actual YES;
  ambos guiones significa participación actual NO, sin recompensa anterior disponible.
  La pareja adquirida está en el header World Boss main (Most Damage/Overall Rank);
  Select Battle Mode muestra el card/ranking, sin ambos campos completos. Numeric
  fue adquirido live; guiones y previous reward conservan evidencia histórica.
- Tras Raid Complete el panel puede tardar en actualizar rank/damage. Guiones stale
  no contradicen una participación recién acreditada dentro del mismo ciclo.

## Arena — USER_GT y adquisición 2026-10-08

Un batch EASY x8 completo observado; [informe y gaps](ARENA_HIL_ACQUISITION_20261008.md).
B1 añadió un único batch EASY x8 autorizado y retorno verificado; hubo pausas del
observer y recuperación explícita, detalladas en [informe B1](ARENA_B1_20261008.md).

- **USER_GT:** Beginner=EASY izquierda, Intermediate=NORMAL centro, Expert=HARD derecha. Victoria x1:
  70/120/180 puntos respectivamente; x8 multiplica por ocho; derrota cero.
  El juego calcula los puntos; no se necesita leerlos/acumularlos para esa policy.
- **USER_GT:** matchmaking depende de puntos acumulados. Winrate por personaje y
  dificultad no es estacionario; controller futuro usa resultados recientes,
  exploración e histéresis, sin implementar en esta adquisición.
- **USER_GT:** un Auto Repeat completo suele durar unos ocho minutos, variable
  por personaje. No es una espera fija. El modal final no requiere un campo Wins.
- **USER_GT definitivo, Fase A:** cada Brawler Badge con el que se ganó entrega
  exactamente un Karat; los badges con los que se perdió entregan cero.
  `Brawler's Badge Used` → `used_tickets`; `Acquired Karats` → `won_tickets`.
  `winrate = won_tickets / used_tickets`; no hay un campo `wins` separado.
  No deducir victorias de puntos, saldo de Karats, resultados individuales ni
  divisiones por ocho. Un cero explícito acreditado es válido; ilegible no es cero.
- **USER_GT adicional:** Double Points (buff 3) duplica únicamente Victory Points,
  **no Karats**. La correspondencia Acquired Karats → won_tickets es independiente
  del estado de ese buff; el result reader no necesita consultarlo.
- **USER_GT, policy futura:** sólo batch válido con ≥80 Brawler Badges consumidos
  (diez entradas x8) permite Hard 0%→Easy o Easy 0%→terminación funcional de
  Arena Farming Cycle. Batch menor no habilita ninguna excepción; esa terminación
  no es FAILED técnico ni necesariamente termina toda la rutina.
- **USER_GT, comparación futura:** Hard supera Normal si pHard > (2/3)pNormal;
  Normal supera Easy si pNormal > (7/12)pEasy; Hard supera Easy si
  pHard > (7/18)pEasy. No vuelve estacionario el matchmaking ni implementa policy.
- **USER_GT, composición:** Badges suficientes→Arena; insuficientes con
  Sapphires suficientes→MW→Arena; ambos insuficientes→Manual Stage→MW→Arena.
  Defaults de decisión por ocurrencia:40Badges para Arena,100Sapphires para MW,
  80Badges usados en un batch para excepciones cero victorias. No son costes;
  entrada técnica x8 requiere8, no40. Manual Stages usa el contrato adquirido
  abajo, independiente de Stages Daily Ads. Conservar lifecycle Shared Meteorites.
- **LIVE_EVIDENCE:** Telumpel en Lobby (identidad USER_GT)→botón Battle→Select Mode
  con tarjeta Arena→Arena con columnas Beginner/Intermediate/Expert y Challenge.
  Ticket amarillo 106 visible en Lobby y ambas pantallas: Brawler Badges por
  USER_GT confirmado al retomar. La moneda plateada 422 sigue sin identificar.
  Capturas scrcpy 2712×1224, secuencias por lifetime, en manifest del informe.
- **USER_GT:** Arena selección y Challenge son vistas de una misma BASE no-battle;
  Challenge no es modal/overlay. Auto Repeat abre un MODAL de configuración.
  Upon Defeat siempre desmarcado. X cierra configuración; inicio físico interno
  corregido por LIVE_EVIDENCE y steer posterior, descrito debajo.
- **USER_GT actualizado 2026-10-09:** buffs1/2 se activan y se verifica ON;
  no leer sus contadores ni exigir cobertura de tickets. Su fallback Gold está
  permitido; nunca Karats. Buff 3 Double Points consume una unidad
  por Badge, no por combate x8; activar sólo con saldo conocido ≥consumo previsto
  conocido. UNKNOWN mantiene buff 3 OFF. Auto Repeat no se detiene al agotarlo y
  puede comprarlo con Karats: compra premium prohibida.
- **USER_GT:** x2/x3/x5/x8 existen; usar sólo x8. Observar selección actual,
  no tocar si ya activo; de lo contrario doble tap específico como MAX MW.
  Tap aislado abre overlay; memoria personaje/cuenta no resuelta ni requerida.
- **USER_GT:** Socket Inventory Full puede aparecer en Arena; Equipment Full
  posible no confirmado. Reusar ReliefCoordinator, sin forzar blockers.
  ArenaFlow ejecuta un batch por invocación; ciclos pertenecen al caller.
- **LIVE_EVIDENCE:** EASY Challenge muestra x8 con check dorado ya seleccionado;
  buffs 1/2 inicialmente 923/999 sin check, selección los deja 915/991 con check
  y borde iluminado, Badges aún 106. Costes visibles Gold 3000/5000 y buff 3
  8 Karats, saldo 999 sin check. No compra. Una captura con notificación externa
  se descartó por instrucción; el estado posterior limpio conserva los checks.
- **LIVE_EVIDENCE:** Auto Repeat abrió configuración con Upon Defeat vacío;
  X devolvió Challenge con buffs 1/2 y x8 activos, buff 3 OFF. Texto del modal:
  termina al agotar Badges y compra items automáticamente con Gold/Karats.
  No hay selector de número de entradas en el modal observado.
- **LIVE_EVIDENCE, corrección causal:** tras X, Auto Repeat de Challenge vuelve
  a abrir configuración; el botón verde interno es el inicio autorizado por
  steer posterior. Primer inicio produjo “The bag is full. Would you like to
  organize your bag?” con Yes/No sobre configuración, Badges 106 sin consumo.
  Usuario preparó espacio y restauró Challenge; inventario intervenido no nombrado.
  Literal coincide con Socket blocker curado existente; no prueba Equipment Full.
- **LIVE_EVIDENCE:** ejecución efectiva EASY x8, Upon Defeat OFF y buff3 OFF:
  Loading→batalla (HUD versus, timer, pausa, banda Auto Repeat)→WIN transitorio
  sin input→Challenge con próximo oponente→batalla. Challenge no prueba término.
  NORMAL/HARD Challenge también adquiridas sin combatir; x8 y buffs1/2 persisten.
  Start/Auto Repeat conservan apariencia activa con saldo2: no es readiness.
- **LIVE_EVIDENCE:** batch consumió **104 Badges (13 entradas x8), 106→2**;
  x8 no ejecutó entrada residual x2. Final “Auto Repeat/Auto Continue/SKIP
  Results”: Brawler's Badge Used104, Acquired Victory Points7280,
  Acquired Karats104, Rewards vacío. **Sin campo wins ni attempted**.
  USER_GT cierra la correspondencia: used_tickets104 / won_tickets104,
  lost_tickets0, winrate100%. Cifra nativa limpia y OCR concordantes; OCR no es GT.
- **LIVE_EVIDENCE:** OK final descubre insufficient Brawler's Badge / purchase
  Yes-No; No devuelve Challenge limpio. Back→selección puede mostrar Loading y
  New Ranking/OK antes de quedar limpia. Resultado no reapareció en NORMAL/HARD.
- **LIVE_EVIDENCE:** buffs1/2 seleccionados reservan8 unidades con x8. Después
  de batch 811/887 ON; deselección devuelve8, OFF819/895. Neto104 unidades de
  cada buff (inicial923/999). Buff3 OFF999 sin consumo. Gold post-relief manual
  6228489654 igual al final; Karats100868→100972, +104 sin compra.
- **LIVE_EVIDENCE / límite temporal:** inicio 20:32:44 UTC aprox.; último raw
  de batalla20:40:39.699, primer raw final20:40:58.751. Duración verificable
  ~475–495s, estimación por telemetría8min12s; no instante exacto. Final permanece
  hasta ACK manual. Stream con artefactos no autoriza cifras; native fresco limpio.
- **HEURISTIC de previsión, no contabilidad real:** para saldo B y x8 constante,
  batch natural hasta insuficiencia, `floor(B/8)*8` explica106→104+2. No80 fijo,
  no garantía si blocker/interrupción. Mantener buff3 OFF ante consumo desconocido.
- **LIVE_EVIDENCE B1:** New Ranking apareció también al entrar desde Select Mode;
  un OK acreditado devolvió selección sin iniciar batalla. Captura portable curada.
  Recuperación pre-start autorizada: X configuración→Challenge; Back→selección;
  Back→Select Mode; Back→Lobby. Son transiciones adquiridas, no wiring QM.
- **LIVE_EVIDENCE B1, único consumo autorizado:** Telumpel EASY x8,50Badges,
  tres buffs ON con stock libre755/844/935 y reserva inicial8 verificada al seleccionar.
  Upon Defeat OFF; único botón verde interno→Loading→batalla activa. Resultado
  nativo Brawler's Badge Used48 y Acquired Karats48: used48/won48,100%.
  OK único→Insufficient Brawler's Badge; No único→Challenge limpio BASE Arena
  acreditado. Final nativo:2Badges, x8ON, buffsON707/796/887, Gold6436020953
  sin cambio, Karats101020→101068. Buff3 ON no modifica correspondencia Karats.
  Detener/reabrir el observer no detuvo el juego. Hubo handoff explícito;
  no se midió instante de final ni duración precisa del batch. Capturas/procedencia
  en manifest portable B1 e informe. No compra, segundo batch ni generadores.
- **USER_GT / deuda de adquisición:** al alcanzar determinados puntos puede
  aparecer otro **MODAL informativo** de Arena, similar al de Monster Wave.
  Título/literal (podría ser «Points Reward»), umbral y cierre **UNKNOWN**.
  Capturar cuando aparezca naturalmente; no provocar el evento, inventar detector
  ni bloquear A/B1. ArenaFlow debe distinguirlo del final; estado
  no reconocido conserva evidencia y nunca autoriza taps ciegos de cierre.
- **UNKNOWN residual B1:** derrota; pausa/cancelación física; compras Gold no
  cubiertas por la adquisición B2 debajo; retorno tras relief. Configuración,
  resultado Auto Repeat, insuficiencia y New Ranking son MODAL; Challenge es
  otra vista de la BASE Arena. Single tiene un resultado distinto, descrito debajo.
  No se readquiere x8 desde OFF porque estaba ON; doble tap sigue USER_GT.
  Estado histórico al cerrar la adquisición inicial: Challenge HARD limpio, Badges2 y tres buffsOFF;
  ADB perdió dispositivo antes del intento QM, sin input. Los nombres legacy
  del censo semántico no clasifican estas superficies.

### Arena B2 — Single y salida externa (2026-10-08)

- **USER_GT:** resultado individual es OVERLAY sobre Arena Battle; Arena Battle
  es BASE battle; Select Mode de Arena es BASE distinta de la de Survival.
- **LIVE_EVIDENCE:** Challenge limpio permite Quick Menu mediante el control
  compartido; su tile Lobby retorna a Lobby. Ruta Back adquirida sin combate:
  Challenge→selección (puede aparecer New Ranking→OK)→Select Mode Arena→Lobby.
  No se habilita una regla global de QM por conveniencia del flow.
- **USER_GT:** Start ejecuta una entrada; seleccionar buff 1 insuficiente compra
  directamente con Gold, gasto pequeño. **LIVE_EVIDENCE:** x8 con stock6 compra2
  unidades a3000Gold: debit6000, muestra reserva roja `-2`, sin cambiar Karats
  ni badges. Stock0 muestra `+` con buffOFF; selección x8 compra8, debit24000 y
  reserva `-8`. El signo negativo es reserva pagada, nunca inventario libre.
- **LIVE_EVIDENCE:** un Start individual EASY x8→batalla automática, sin activar
  Auto Battle ni enviar otro input de combate→WIN con estadísticas, Reward
  Karat1×8/puntos70×16 y «Tap the screen». No campos Used Tickets/Acquired Karats;
  el reader de Auto Repeat no posee autoridad sobre este resultado.
- **LIVE_EVIDENCE:** un tap al prompt devuelve selección de dificultad, no
  Challenge. Primera entrada106→98badges y101068→101076Karats. Reentrada a
  Challenge muestra buffsOFF, stock0/309/706 y x8ON. Segunda entrada registrada
  una sola vez98→90badges y101076→101084Karats; cierre y Back externos verificados.
- **LIVE_EVIDENCE:** New Ranking reapareció naturalmente después de Back desde
  Challenge; OK adquirido restituyó selección. Es distinto de la deuda informativa
  por umbral de puntos, que no apareció. Derrota individual sigue UNKNOWN y no
  se deduce de ausencia de WIN. No se provocaron derrotas ni cancelación física.
- **LIVE_EVIDENCE:** repetición causal productiva tras corregir CV pausa/prompt:
  EASY x8 único Start90→82badges/101084→101092Karats, buff1Gold24000;
  resultado/cierre/Back/Lobby y paso posterior Session completados continuamente.
  Total B2: tres entradas,24badges,24Karats,54000Gold; cero gasto Karats.

Manifests curados: `datasets/arena_b2_acquisition_manifest.json`,
`datasets/arena_b2_assets_manifest.json`, `tests/fixtures/arena_b2/manifest.json`.
Evidencia nativa/stream y consumos: [informe B2](ARENA_B2_20261008.md).

### Arena Farming — adquisición focal 2026-10-09

- **LIVE_EVIDENCE:** Dimension Manipulator identificado por owner canónico de
  identidad, ciclo desde Lobby119Badges/95Sapphires. Un único Auto Repeat HARD x8,
  Upon DefeatOFF, buffs1/2/3 seleccionados desde stock999 y reserva8 verificada.
  Modal nativo Used112 / Acquired Karats112;119→7Badges y103165→103277Karats.
  Gold6930610473 intacto durante Arena. Cierres Insufficient/No y New Ranking/OK,
  retorno Lobby y paso posterior Session completados sin reiniciar source/owner.
- **LIVE_EVIDENCE / telemetría:** ControlledWait continuo526.906s,
  175observaciones, intervalo medio3.028s/máximo3.172s, cero OCR. Autonomía
  acreditada para este batch; no acredita una campaña de múltiples ciclos.
- **LIVE_EVIDENCE:** refresh posterior100Sapphires/7Badges. El MW de presión
  devolvió no_work sin input. La operación de generación única posterior acreditó
  CLEAR, consumo fresco100Sapphires y saldos Lobby0Sapphires/106Badges, sin otro
  Arena. Final Gold7127809094 yKarats103277; no compra de badges/Double Points con
  Karats. El delta de Badges99 es esta observación, no recompensa fija contractual.
- **IMPLEMENTATION_CONTRACT:** generar un pase MW no aplica la meta de presión102
  de Gold Farming; reutiliza los mismos owners/guards físicos. Manual Stages
  conserva operación y economía independientes de Stages Daily Ads.

Fuentes crudas locales y límites: [informe Farming](ARENA_FARMING_VALIDATION_20261009.md).

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

### Manual Stages — USER_GT y adquisición 2026-10-09

- **USER_GT:** Burst Breaker, Berserker, Demon Blade y Kaiserin pueden hacer
  Abyssal Rion **09** directamente. Otro personaje sólo puede ir a09 con los11
  meteoritos compartidos equipados y verificados para esa identidad; sin esa
  garantía usa **Chaos06**. El flag de configuración no acredita equipamiento.
  Chaos es el episodio de una estrella, dos antes de Rion. Stage08 sigue siendo Ads.
- **USER_GT:** entrada manual requiere Stamina≥60 y Sapphires por debajo de su
  capacidad fresca. **USER_GT posterior (presupuesto/abastecimiento):** se permite
  comprar Stamina con la oferta K Coins acreditada cuando corresponda Manual;
  supersede la prohibición inicial de abastecimiento, no autoriza recarga premium.
  x4 puede seleccionarse en BASE o primer MODAL. **LIVE_EVIDENCE:** en BASE
  el doble tap en x4 abre/cierra la selección y deja el check amarillo; yaON
  se conserva. El primer MODAL muestra x1=15/x2=30/x3=45/**x4=60**.
- **USER_GT actualizado:** Rion09 requiere Penance; Chaos06 requiere **Hell**,
  segunda dificultad. **LIVE_EVIDENCE:** Chaos06 abre «Chamber of Reflections»;
  Rion09, «Corrupted Hall of Dimensions». Ambos comparten controles de dificultad,
  cuatro buffs y los dos MODAL. Primer Start abre Select Striker sin consumo
  de Stamina; su Start inicia una sola entrada. No usar Auto Repeat.
- **USER_GT:** buffs1–3ON; buff4 sólo con tickets suficientes, **nunca Karats**.
  **USER_GT actualizado:** buffs1/2/3 requieren sólo selección y efecto ON,
  sin leer contadores. El cuarto conserva cobertura de tickets; insuficiente
  o ambiguo OFF, sin compra Karats, como el último buff de Arena.
  **USER_GT:** Get Support debe estar activo igual que en Stage Ads: conservar
  ACTIVE; NEEDS_TICKETS→Fill All→READY→activar→ACTIVE mediante el owner existente.
  Revalidar Support después del relief.
  **LIVE_EVIDENCE:** cada activación adquirida99→98 en x4; buff4 muestra precio
  premium20 si faltan tickets. Al abandonar configuración por relief, la
  selección puede resetearse y sus tickets reservados recuperarse. Rion09:
  buff4 stock97→seleccionado96→post-entrada96; buffs1–3,98→97→97.
  Cada buff consume **un ticket por entrada x4**, sin débito extra al Start.
  Una selección ON ya reservó ese ticket; no exige otro ticket restante.
  No trasladar el consumo Double Points de Arena a este control.
  **LIVE_EVIDENCE 2026-10-09:** retorno de Equipment relief a Rion09 conserva
  Penance seleccionado con variante del botón (posición/render de estrella y
  borde). Template único previo produjo UNKNOWN: NCC0.9385 stream/0.8170 nativo.
  Variante curada local con margen propio acredita ON al mismo threshold0.94;
  conserva OFF y rechazo de controles dimmed. No autoriza otro Start por el miss.
- **USER_GT:** el botón Auto permanece rojo en ambos estados; ON tiene destellos
  intermitentes laterales, OFF carece de ellos. **LIVE_EVIDENCE / regresión:**
  Monk perdió Chaos06 Hell por timeout con AutoOFF (confirmado por el usuario).
  El bisel metálico brillante no prueba ON. El símbolo Pause y la palabra Auto
  identifican esta superficie; fondos y animaciones de combate no prueban estado.
- **USER_GT:** Clear Time con botones inferiores es **OVERLAY sobre batalla**;
  Home lleva directamente a Lobby. La derrota con Revive/Abandon es MODAL:
  usar Abandon, nunca Revive premium. El segundo MODAL «Get stronger» se cierra
  con X. **LIVE_EVIDENCE:** Abandon→Get stronger→X→Lobby; timeout también mostró
  Get stronger. Mystic61→1 y Monk111→51, sin incremento Sapphire en ambas derrotas;
  los60 son el coste observado de una entrada x4, sin gasto adicional acreditado.
- **LIVE_EVIDENCE:** Burst Breaker ganó Rion09 Penance tras activar AutoOFF→ON,
  con Clear Time124s (incluye el retraso de recuperación inicial). Home→Lobby
  limpio. Overlay mostró90Sapphires, pero saldo129→129 sin progreso porque ya
  estaba sobre capacidad; esta prueba no acredita producción de saldo.
- **LIVE_EVIDENCE:** segundo Rion09 Penance con AutoON conservado: Clear Time63s,
  recompensa visible42 y saldo29→71 tras Home→Lobby. Primera salida Home no tuvo
  efecto; un nuevo Home con Clear Time aún fresco cerró a Lobby, sin otro Start.
- **LIVE_EVIDENCE:** Blade Dancer sin Shared Meteorites→Chaos06 Hell;
  Support Activated conservado antes/después de Socket relief; cuatro buffsON,
  AutoON conservado (20samples/2s, peak.158). Clear Time31s; overlay40Sapphires,
  saldo28→68. Stamina Lobby89→Claim/pre-Start119→Lobby59: coste físico60,
  no confundir delta neto30 con el coste. Un único Start en Select Striker;
  Home sin efecto→Clear fresco→un retry Home→Lobby limpio.
  Nueva invocación con59Stamina no inició y Session continuó/completó.

Procedencia curada: [manifest Manual](../datasets/manual_stages_20261009_manifest.json).

### Ads — evidencia física conocida

- **USER_GT 2026-10-09:** el end card Google Play de
  `artifacts/failure_evidence/failure_457cdceba7744755a472452078ce6352/frame_1581.png`
  (Binance en esa captura) ya tenía la recompensa del anuncio completo lista;
  la X negra circular superior derecha podía cerrarlo. No tenía el icono de
  sonido del chrome de vídeo anterior. Se acredita ese layout fijo con X y
  pie Google Play, bajo Google AdActivity/focus concordantes; la marca del
  anuncio, una X genérica y un fin de parte no aportan autoridad.

- **USER_GT (2026-10-05):** existen anuncios de aproximadamente5 s. Una duración corta no contradice una terminal authority fuerte ya acreditada (Reward granted/chrome SDK adquirido). Una X de contenido o sin estructura/posición SDK acreditada no prueba completion; acabar una parte tampoco prueba fin del anuncio completo. El contrato temporal pertenece a ARCHITECTURE.
- **USER_GT actualizado (2026-10-05):** nunca cerrar antes de recompensa lista; al acreditarse, cerrar cuanto antes. Pasos intermedios como Next ad no acreditan por sí mismos recompensa del anuncio completo. Esto no establece un hitbox de Next ad ni autoriza tocar contenido: el control explícito necesita evidencia física de su chrome; el progreso/reset multipart adquirido ya se observa sin input.
- **USER_GT posterior (2026-10-05):** el usuario confirma que la X negra dentro del círculo blanco de la esquina superior derecha del chrome Google SDK, igual a `ad_campaign6_char2_terminal.png`, estaba lista para cerrar el anuncio completo; quedó visible unos20 s extra antes del cierre. **LIVE_EVIDENCE de sólo lectura:** campaña719b4e4e, scope7,19 capturas del siguiente ad natural; partes explícitas previas sin esa X, después X circular y chrome de sonido con resumed/focus Google AdActivity concordantes. Primera captura acreditada a72.237 s, retorno runtime a109.609 s y Sapphire fresco. El movimiento del contenido después de esa X no es autoridad de espera. No se generaliza a otras X/SDKs ni a fin de una parte.
- Google `com.google.android.gms.ads.AdActivity` corre bajo el mismo package de Kritika; main adquirido es `com.hive.HiveUnityPlayerActivity`. En este Samsung, `dumpsys window` completo aporta foco y `windows` no. UIAutomator adquirido sólo expone root/WebView, sin Close/Continue accesibles.
- Back temprano live abortó y devolvió main sin results. Back con chrome SDK `Reward granted` cerró y produjo results. Una variante abrió Finsky/Play Store automáticamente; Back permitió recuperar superficie ad, sin tocar CTA. Package/activity no prueban reward ni que ya se pueda cerrar.
- **USER_GT posterior:** un ad triple aún avanzaba al cierre prematuro de60 s y tenía barra de progreso visible. **LIVE_EVIDENCE:** barra amarilla superior SDK avanzó .264→.918 en cinco capturas; después desapareció y apareció Reward granted. Una barra puede resetear entre etapas. Progreso visible prueba actividad, no finalización; desaparecida/estática/fragmentada no prueba reward. El antiguo supuesto60s=terminado queda stale. Bounds y policy son contrato de software en ARCHITECTURE.
- **USER_GT:** No Ads Available normalmente admite retry temporal (~5 s) o salir a Character Select y reentrar al MISMO personaje; no es automáticamente daily exhaustion. **LIVE_EVIDENCE:** reset aislado conservó identidad antes/selección/Lobby. No apareció No Ads temporal nativo ni se ejercitó su cadena completa; límites de retry y fallback provisional constan en RESOURCE_ROUTING.

USER_GT (2026-10-02/03), Combine result animations: after the one effective confirmation, use bounded lateral taps on the existing noninteractive safe point (0.15, 0.50) under the result overlay until the known panel/menu is recovered. No animation stability requirement before starting TapThroughAnimation; a popup-close frame before animation onset is not completion. Never repeat confirmation because an effect/animation wait is inconclusive.

### No Ads Available: recovery confirmado 2026-10-03

- **USER_GT:** al aparecer indisponibilidad temporal, hacer al menos dos retries separados por 5–6 segundos. Si persiste, salir a Character Select y reentrar al mismo personaje; un intento final. Esta transición no es Rotation. Si persiste después del recovery, registrar indisponibilidad y continuar al siguiente personaje; no hacer entrada manual sin ads.
- **LIVE_EVIDENCE:** el alert adquirido muestra `Loading... (If the video does not load, please visit the [Select Character] screen and try again.)` sobre Auto con botón OK. Es el caso de indisponibilidad observado por el usuario; no contiene Video0 ni el alert diario. No se adquirió aún un frame nativo con texto literal `No Ads Available`.
