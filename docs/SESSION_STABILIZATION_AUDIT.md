# Sesión combinada — reconstrucción causal 2026-10-04

Baseline `31ecf4642db02d6a90fce871360f38cc45e92650`, branch
`rebuild/stable-baseline`. Investigación y aceptación realizadas sin commit/push;
cierre autorizado en un único checkpoint local `fix: stabilize combined farming sessions`,
sin push, sin desarrollo ni smokes nuevos durante el cierre. Este informe conserva los
runs rojos; el retry posterior no cambia su resultado histórico.

## Incidentes investigados

Los cinco incidentes quedan cerrados para este frente por sus cambios causales y
validación afectada. Los dos runs originales conservan FAILED; el motivo físico
del primer tap Black Market sin efecto sigue UNKNOWN, sin inventar GT histórico.

| Caso | Primera divergencia | Causa demostrada y límite | Cambio mínimo |
| --- | --- | --- | --- |
| WB Auto OFF → waiting | Run f2f67481, eventos 93–94: UNKNOWN/TIMEOUT, cero taps; `no fresh context after fast harvest`. Después entra al wait | El harvest y `observe()` pueden entregar la misma secuencia. La fase quick descarta el contexto y el caller abandona la comprobación tras una ventana inconclusa. El OFF físico del incidente es USER_GT; las capturas temporales originales no fueron preservadas y no permiten atribuir su UNKNOWN a un glow/cinemática específico | Esperar un contexto estrictamente fresco antes del guard y después del tap; una segunda observación bounded en WB sólo si no se despachó input. OFF habilita, ON no toca, UNKNOWN no autoriza |
| Ads multipart early exit | Run f2f67481: launch e557 22:04:47.540 UTC; progreso .071→.9196 entre 5.45 y 58.84 s; terminal recovery a 78.141 s | Global elapsed ya excedía 60 s cuando expiró la grace de 15 s desde el último progreso. El fin de una parte no probaba fin del ad. Otra adquisición natural mostró Ad 2 of 3 y tres visitas externas: el contador global de dos retornos además dejaba la tercera sin recuperación | Fallback medido desde el último movimiento/reset SDK; absoluto 180 s. Retornos externos bounded por visita, reiniciados sólo tras SDK fresco y sujetos al límite de close steps. Android/focus, no contenido, siguen siendo autoridad |
| MW→Mailbox/Quests vía Lobby | Run f2f67481: e1532 MW→QM→Lobby; Gold termina e1567 en Lobby; Mailbox e1569–1591 y Quests hasta e1606 restauran ese Lobby | La rutina real contenía Gold Farming Cycle. Su inversión MW final normalizaba Lobby incondicionalmente, antes de que Session eligiera el panel siguiente | Gold vuelve a Lobby sólo para reanudar Stages; publica snapshot/postconditions de su MW final. No conocimiento de Mailbox/Quests dentro de MW |
| Black Market FAILED, Berserker | Primer slot comprado e1640–1647; segundo select e1648 22:14:03.621 UTC sin popup; nominal e1650 y grace e1654 terminan en mercado válido. Reobservación repite secuencia 8907; e1655 `retry_state_not_fresh`; FAILED e1658 | El tap no produjo el efecto esperado; por qué se perdió físicamente sigue UNKNOWN. La divergencia recuperable estaba en mercado limpio, pero el guard no esperaba la siguiente secuencia y rechazó el retry. Retry posterior sobre Berserker completó; no borra el rojo | VerifiedTransition espera una nueva observación bounded antes de evaluar el retry ya autorizado. Conserva failure ante timeout/estado incompatible; no sleep global ni conversión a NO_WORK |
| BASE Craft FAILED, Berserker | Run 2728dafd: Weapons 672→182 (10), 182→35 (3), efectos frescos. Hero Armor 547/999, costo49: e369 abre receta seq2248; samples2254–2292 leen `Hero ` .84495 bajo .85. e393 timeout; un cancel e394–396; e397 `recipe_verification_failed` | Crop de tier Armor incluía ruido adyacente y no acreditaba Hero. Familia/Helmet seguían correctos. No hubo confirmación/consumo Armor. Evidencia final archivó un contexto Craft anterior, no los frames del selector; no se atribuye ese snapshot al popup fallido. Sin relación con Trading/targeted swipe | Crop específico Armor conservando Expert y umbral .85. Adquisición natural Hero Helmet/MAX2/resultado/decremento 114→16; replay curado. Accessories no se acredita por inferencia |

## Logs y procedencia

- `logs/20261004T215918.768168Z_session_f2f67481.jsonl`, run
  `94a95275d1894b8f9088344d5dab988f`, session
  `c0ac963c458d484b922cb6c94158c0bf`: Blade Dancer → Rotation → Berserker;
  termina FAILED Black Market. Rutina literal BM, WB, Gold Farming, Mailbox, Daily Quests.
- `logs/20261004T221716.129031Z_session_2728dafd.jsonl`, run
  `fa7d31fbeff54010ad35170bc1094aa5`, session `d19fc74847da4b40a96cc5b480204fcc`: Berserker; BM completa el retry, luego WB y Gold;
  FAILED Craft a 22:21:06 UTC.
- Black Market FailureEvidence local `failure_a983189f24cf4d0bad3b63fab26ef758`:
  frames8905/8906/8907 muestran mercado, slot0 purchased y slot1 Gold50000, sin modal.
- Craft FailureEvidence local `failure_66237a3e03d84f1682b30132e4497f68`: contexto anterior al selector;
  la identidad fallida está demostrada por las muestras/logs, no por esa captura final.
- Los tres primeros harnesses WB (`96aeb1a9`, `36cb1e22`, `3c02ff5f`) quedan rojos:
  OFF no verificado inmediatamente tras toggle, adquisición temporal hambrienta por
  tests OCR concurrentes, y UNKNOWN respectivamente. Sus assertions no son una campaña aceptada.
- Focal WB final `logs/20261005T001528.567000Z_wb_stabilization_focused_0a69673c.jsonl`:
  e60 OFF seq555 → un tap → ON seq623, SUCCESS; e64 ON seq650 → cero taps,
  SUCCESS; raid completo y retorno normal. No tests OCR concurrentes durante esas ventanas.
- Ad triple natural en `36cb1e22`: captura local `ad_focused_progress.png` muestra
  `Ad 2 of 3`; Stages verificó reward Sapphire0→312. Expuso el límite externo que luego
  se corrigió; no se presenta como validación post-fix de ese segundo cambio.

Timestamps JSONL en UTC; fecha local Argentina 2026-10-04. Capturas nativas, logs y
harnesses quedan locales en `artifacts/session_stabilization`, no en Git.

## Archivos y contratos afectados

- `bot/auto_battle.py`, `world_boss_activity.py`: frescura OFF/ON, instrumentación;
  WB Equipment Sell bounded y caller WB. `flow_registry.py`: wiring productivo WB,
  contract Gold propio. Su hunk SummonPet ya existía y se preserva.
- `bot/verified_transition.py`: adquirir siguiente snapshot antes de decidir el
  retry autorizado; no ampliar inputs ni degradar fallos a no-work.
- `bot/ads_manager.py`: stall SDK, counter por visita externa y autoridad registrada.
- `bot/gold_farming_flow.py`, `stages_daily_flow.py`, `stages_wiring.py`: entry
  BASE/hub y MW preparado, publicar surface final para Session literal/Navigation.
- `bot/craft_reader.py`, `monster_wave_board_reader.py`, `trading_key_row_reader.py`,
  `equipment_sell_reader.py`: cuatro defectos perceptivos locales diferentes;
  thresholds, guards de gasto, fresh effects y una confirmación se mantienen.
- `bot/portal_notification.py`, assets Stages y portal: variantes físicas causales;
  assets Equipment Normal/Poor: completar labels del guard ya existente.
- Tests directos/regresiones/replays pequeños con manifests; ARCHITECTURE,
  GAMEPLAY_GT, RESOURCE_ROUTING, CONTEXT, ROADMAP sólo para sus hechos/contratos.
  No cambios en directed_list_scroll/Trading targeted swipe.

El borrado del plan, `summon_pet_daily_flow.py`, el hunk SummonPet de
`flow_registry.py`, los41 inserts de `test_portal_obstruction_recovery.py` y los
cuatro scripts root `check_eval.py`/`fix_tests.py`/`test_live.py`/`test_wait.py` son
trabajo independiente previo, no cambios de estabilización. Se mantienen intactos.

## Divergencias adicionales durante aceptación

El intento GUI `20261005T003403.708932Z_session_8cb8fbbd.jsonl`, Demon Blade,
permanece FAILED (0/3). WB no elegible deja Select Battle Mode, pero e97 fuerza
Lobby antes de Gold. USER_GT confirma Sapphires legibles en ese hub. Stages/Gold
aceptan ahora BASE Quick Menu; desde hub, Stages ejecuta el MW prerequisite
preparado antes de pedir Lobby para su propio gameplay. No cambia el orden de Session.

Ese intento también expuso un failure del board MW: e206–207 y e212–213 reúnen
pares frescos, pero repetir OCR sobre cinco crops byte-idénticos suma 1,187/1,297 s
hasta edades 2,094/2,297 s y viola el límite 2 s. e218 pierde el consenso;
e232–233 fallan flow/session. El reader memoiza sólo el resultado OCR de cada
crop exactamente idéntico (una entrada por fila); cada muestra conserva su propia
secuencia/timestamp y recalcula contexto/red pressure. Cambiar un píxel vuelve a OCR.
No se amplían edades ni se cachea autoridad de saldo.

Focal read-only `20261005T004659.832474Z_board_stabilization_focused_86e663f5.jsonl`:
dos adquisiciones aceptadas con edades 1,125/0,828 s. Cleanup separado cierra el
intent pendiente y vuelve a Lobby sin confirmar SKIP. Tests dirigidos hub/Stages/
Gold/navigation/board: 173 passed en una invocación, 37,60 s.

El siguiente intento GUI `20261005T005454.043508Z_session_4bada9d3.jsonl`
permanece FAILED (1/3, Demon Blade → Kaiserin). Confirmó WB no elegible hub→MW
sin Lobby e61–64; ad de 108,813 s con tres visitas Finsky y recompensa97→499;
WB Kaiserin ON→ON, cero taps, raid completo. La divergencia e1430–1434 fue posterior
a MW: Start abrió Select Striker, pero la X del banner Hell Portal cubría las
primeras letras del title y NCC .9028 no llegaba a .94. Timeout correcto ante
UNKNOWN; no combate/ad despachado. Se recorta sólo ese extremo del template
(.343→.365), conservando threshold y brillo: replay1.000. Focal
`20261005T011033.364577Z_striker_stabilization_focused_b5c76e8d.jsonl` reconoció
el modal real, abrió Auto y cerró hasta Lobby sin Video/combate. 85 tests afectados
passed en una invocación de6,31 s. La aceptación se reinicia sin contar el primer
personaje del rojo.

El intento GUI `20261005T011226.812395Z_session_f2984b61.jsonl` permanece
FAILED (0/3, Kaiserin). Ad normal con Reward granted y Back a33,703 s, reward31→415.
e198–205 abren MW y acreditan un ACK de entrada; después el aviso Hell tapa
MW_SCREEN, dejando UNKNOWN limpio. El recovery causal existente no confirma
el aviso: probe antiguo .593 en captura nativa actual. No se gastaron Sapphires.
Una variante de asset con X completa/borde mantiene thresholds .80/.65,
reconoce los11 positivos previos (.881–.920), rechaza6 negativos mismosROI
(max.263) y690 frames de manifests (max.414, sin ausencias). No se cambian
ownership, guards ni lógica MW. 95 tests afectados passed en2,17 s.
Focal `20261005T012227.376051Z_portal_stabilization_focused_1a4e33c5.jsonl`:
entrada efectiva fresca→missing BASE→CONFIRMED→un dismiss→ABSENT→MW
revalidada→MAX→salida completa sin Start SKIP. El primer back HIL sólo preparó
el source hub; no fabricó un snapshot software. H&H se cierra por obstrucción
causal, no por presencia preventiva. El rojo queda rojo y se reinicia aceptación.

El intento GUI `20261005T012500.517567Z_session_198e41e1.jsonl` permanece
FAILED (1/3, Kaiserin → Dimension Manipulator). Kaiserin termina business-incomplete
por Video0; WB del segundo personaje verifica ON→ON sin input y completa el raid.
Keys confirma dos promociones Bronze→Silver: 210→10 y 10→0, Silver338→340.
La primera divergencia ocurre después del segundo efecto: frames8460/8466/8472
leen el `0/10` rojo con confianza .85923 bajo .90. e1602 agota muestras y e1604
marca `after_fact_unreadable`; no hay confirmación repetida. La máscara roja binaria
perdía el slash fino por compresión. Se conserva la localización HSV y se preserva
el contraste rojo antialiasado; parser, títulos, umbral .90 y consenso fresco siguen
iguales. Tres frames nativos read-only ahora leen exactamente `0/10` ≥.99933;
99 tests afectados passed en44,42 s en una invocación.

El primer harness focal
`20261005T014423.558112Z_keys_zero_stabilization_focused_100f45d6.jsonl` queda rojo
por omitir los detectores especializados de Trading, sin input. El focal corregido
`20261005T014920.215093Z_keys_zero_stabilization_focused_f9edd119.jsonl` acredita
consenso de dos secuencias nuevas para Bronze0/10 y Silver340/10, cierra Trading,
verifica MW y vuelve a Lobby. No repite trade ni infiere un saldo cero.

Durante el intento `8889626a`, USER_GT aclara que el ad de Dimension Manipulator
mostró una X unos10 s antes del cierre del bot, sin texto «Reward granted».
El log muestra SDK progress .0475→.9838, tres visitas Finsky, retorno en94,609 s y
reward Sapphire2→218. Es un cierre tardío con recompensa acreditada, no salida
prematura; tres visitas externas no prueban por sí solas tres partes. El siguiente ad de Mystic Wolf Guardian permitió guardar
`ad_campaign6_char2_terminal.png`: X blanca circular sin reward-granted. El observer
actual sólo reconoce los dos chrome reward-granted, de modo que no acreditó esa X
y esperó la transición externa posterior (103,609 s). No se modifica el código
durante la campaña ni se atribuye ese episodio al detector reward-granted. Queda
deuda local de reconocimiento del chrome X sola; no autoriza Back sobre cualquier X
de contenido ni convierte tres visitas externas en prueba de triple ad.

El intento GUI `20261005T034856.051617Z_session_8889626a.jsonl` queda
CANCELLED por Stop Safely, 2/3 completos, cero technical failures; no se acepta.
USER_GT observó Sell omitiendo Normal/Poor en Mystic Wolf Guardian. La primera
divergencia demostrada e3331 abre Normal Chest sellable pero sin `grade_visual`;
e3346/e3359/e3401/e3415/e3429/e3443 repiten la omisión sobre Normal Weapon/Enhance.
Epic e3368 sí queda acreditado; después vende Legendary e3452–3469. Assets existentes
sólo cubrían Rare/Epic/Legendary/Ethereal. La policy ya autoriza ambos tiers bajos,
pero su guard visual fail-closed no tenía los dos templates. No se retira el guard.
Se adquieren los labels físicos `[Poor]` blanco y `[Normal]` verde en Drakennn15,
slots accesibles, añadiendo únicamente `grade_poor.png` y `grade_normal.png`.
Rare/Epic tienen assets y replays positivos existentes; evaluator14/14, tests313 passed
en15,92 s (una invocación). Replays nuevos cubren Poor Gloves, Normal Enhance y Chest,
y rechazan otros tiers. Focal productivo
`20261005T043203.575042Z_sell_tiers_focused_2b1230b7.jsonl`:
Poor Equipment127→126; Normal Enhance126→125; Normal Equipment125→122, cada uno
con una confirmación, popup propio y count fresco. Cleanup Lobby, sin expansión.

Ese intento CANCELLED acreditó además la cadena completa en Mystic:
e3633 Gold termina MW; e3642 QM Mailbox; e3656 restore MW;
e3671 QM Daily Quests; e3680 restore MW; e3688 QM Character Select;
e3708 Rotation completa. Sin Lobby intermedio. La aceptación se reinicia con assets
finales y no suma esos personajes a versiones posteriores.

## Validación final

El intento GUI `20261005T043527.274126Z_session_52f9b450.jsonl` queda FAILED,
1/3 (Mystic Wolf Guardian→Cat Acrobat),597,6 s. USER_GT detectó redundancia de relief:
el primer Combine fue WB, e551–590 Fuse con efecto y retorno WB; e608 un nuevo
Full termina business-incomplete por el contrato antiguo Combine-only. Gold recibe
hub y MW vuelve a Combine e662–682, sin fase disponible, después Sell134→126 e786.
No fue una reentrada MW gratuita: el primer caller era WB y el segundo MW. USER_GT
confirma que WB debe usar Sell implementado; se conecta el owner Inventory existente
tras Full post-Combine, una visita, mismo policy y retorno WB fresco. Sin memoria
global de Session ni conocimiento de MW dentro de WB.

En ese mismo run, después del ad100,015 s con retorno/reward, una nueva inversión
MW genera Equipment Full y Fuse tiene efecto e1399–1420. El Inventory131/128
abre Legendary Earrings e1483; popup e1489 tiene identidad exacta terminada en
«for», importe15 K Coins en la línea siguiente. El reader elegía layout corto
al exigir importe en la primera línea, dañando el OCR de Equipment en el recorte.
e1505 falla `confirmation_unreadable_or_stale`, confirma0, sin repetir venta;
e1513/1514 mantienen FAILED. Se selecciona layout K Coin al observar «] for»;
nombre y alcance Bulk siguen exactos, no se interpreta timeout como éxito.
Dos replays curados nativo/stream y negativos,174 tests passed9,88 s.

Adquisición de WB Inventory `4d203684` acredita WB134→Inventory194→WB229,
131/128, sin Start ni venta. Su cleanup queda rojo al esperar hub tras el Back:
el destino físico es Lobby, no UNKNOWN. Primer harness `bdc1a4d8` también queda
rojo por usar `zone.enter` desde MW; corregido a `ensure_hub`, sin cambiar runtime.
La nueva rama conserva esa historia y restablece hub sólo desde Lobby fresco.
Tests WB wiring91 passed1,84 s; contracts235 passed2,24 s, invocaciones separadas.

Focal WB final `20261005T050007.963985Z_wb_sell_focused_2190ee23.jsonl`:
Cat Acrobat Full131/128→Combine sin fases disponibles→Full fresco→QM Inventory→
Bulk Legendary Earrings131→122 e152 (una confirmación, sin expansión)→fresh WB→
Start→Auto ON→ON0 taps e169→Raid Complete e193→retorno normal. COMPLETED e219.
Prueba físicamente el reader K Coin corregido y el wiring WB, sin volver a Combine
ni delegar ese Full a MW. La salida observada Lobby se restablece a hub e209–212.
Regresión dirigida de esa historia BASE y bounds:7 passed1,56 s.

### Campaña GUI de aceptación con código final

`logs/20261005T050411.404714Z_session_2808930b.jsonl`, run
`e8e1bbd8f8c34edcaafb3521bbd8bd7e`, session
`2a959d94538c4dff9123643dd02d576b`. Una única sesión real Basic Gold Farming,
configurada desde GUI con tres personajes y debug, atraviesa Rotation; no suma smokes
ni personajes de las versiones anteriores. Orden BM→WB→Gold Farming→Mailbox→Daily
Quests→Rotation. Gold ejerce Stages Ads/MW y reliefs naturalmente.

Inicio Session e20 05:04:17.232623 UTC; COMPLETED e3623 05:37:36.554898 UTC;
runtime.closed e3624 05:37:36.735101. Tres personajes procesados y tres avances,
14 flows.completed, cero flow.failed/session.failed/runtime.failed. Duración Session
1999,322 s (33:19); GUI runtime completo 2005,2 s (33:25, incluye preparación).
Hashes de los 151 archivos Python y 47 assets registrados antes de iniciar siguen
idénticos al cierre. Los cambios posteriores son documentación, no código productivo.

| Personaje | Business / técnico | WB Auto y resultado | Ads / recompensa Sapphire | Ruta final / Rotation | Relief natural / Craft | Duración incluyendo Rotation |
| --- | --- | --- | --- | --- | --- | --- |
| Cat Acrobat | Video0 legítimo; técnico COMPLETED | WB no elegible, daily indicator absent; no batalla/Auto aplicable. Hub→MW directo, sin Lobby para OCR | 98,953 s, tres visitas Finsky; 68→428 | Gold final Lobby tras MW no-work por pressure bajo; Mailbox/Quests restauran ese origen. Rotation completa e1035 | Equipment Combine→Full fresco→Sell129→122/128, una confirmación, cero expansión. Craft no requerido | 475,020 s (7:55) |
| Crimson Assassin | Mailbox claims_leftover; técnico COMPLETED. Gold UNASSESSED en proyección GUI | ON→ON, cero taps e1135; Raid Complete, WB termina hub e1165 | 94,563 s:74→506; 111,750 s:6→270 | MW e2379→QM Mailbox→MW fresco e2402→QM Quests→MW fresco e2426→QM Character Select; Rotation e2454 | Socket Enhance All; Equipment Combine→Inventory122/136 disponible, cero venta/expansión. Craft no requerido | 807,732 s (13:27,732) |
| Flame Striker | Sin evento business-incomplete; UNASSESSED en proyección GUI de Gold; técnico COMPLETED | Full→Combine con efecto, no Sell necesario; ON→ON cero taps e2579; Raid Complete, WB hub e2609 | 96,328 s:0→324; 109,250 s:24→258 | MW e3542→QM Mailbox→MW fresco e3569→QM Quests→MW fresco e3593→QM Character Select; Rotation e3621 | Keys cuatro trades con efectos frescos; Equipment Combine→Inventory121/132 disponible, cero venta/expansión. Craft no requerido | 716,568 s (11:56,568) |

Black Market completa naturalmente en los tres: e36 05:04:24.392, e1090
05:12:24.721 y e2485 05:25:47.281 UTC, sin la divergencia previa. Craft no fue
necesario en esta campaña; la adquisición focal Hero Armor MAX/result/effect y
replays anteriores conservan su procedencia. No se fuerza consumo para fabricar cobertura.

**Handoff explícito:** Crimson QM Mailbox e2388→restore MW e2402 (source12790),
QM Quests e2417→restore MW e2426→QM Character Select e2434. Flame QM Mailbox
e3551→restore MW e3569, QM Quests e3583→restore MW e3593→QM Character Select
e3601. No Lobby intermedio en ambas cadenas. Cat termina legítimamente en Lobby
porque el MW final hizo no-work por pressure; no se acredita una BASE MW inexistente.

**Ads:** cinco retornos normales Kritika tras SDK/Finsky, duraciones94,563–111,750 s,
todos con efecto Sapphire fresco. No terminal fallback/absolute-bound en esos cinco;
el SDK sigue progresando después de60 s y un reset en Crimson no autoriza completion.
Cada visita externa usa Android Back y después exige evidencia SDK nueva. Tres
visitas Finsky no prueban triple: no hubo label físico multipart preservado en esta
campaña. El triple natural anterior y tests/replays cubren la regresión; la política
post-fix queda observada live en cinco ads largos, sin salida prematura/reward perdido.

**Business y límites del reporte:** la GUI conserva COMPLETED con cero technical
failures, dos personajes business-incomplete y uno UNASSESSED. Cat: Video0. Crimson:
Claim All e2395, procesamiento observado/completado e2404–2405, claims_leftover e2406,
Delete Read omitido correctamente; la razón física de esos claims restantes no se
infiere. Mailbox conserva su contrato business incompleto y restore MW verificado.
Gold de Crimson/Flame aparece «assessment unavailable» porque la whitelist
informativa de SessionReport no incluye `monster_wave.sapphire_effect`; los efectos
y resultados productivos sí están registrados. No se reetiqueta la sesión ni se
modifica código tras aceptación para ocultar esa limitación de proyección.

### Offline final y cierre

Una invocación final de90 archivos afectados: **1906 passed,4 skipped en451,65 s**
(7:31), exit0. Incluye WB/Auto, AdsManager/Stages, Navigation/Quick Menu,
Mailbox/Quests, Black Market, Craft, MW, Routine/Session, Rotation y owners afectados
por VerifiedTransition (pet, Keys, Equipment, Socket). Los cuatro skips pertenecen
a fixtures históricos de Rotation no disponibles localmente; no se presentan como
validación física. Lista exacta local `artifacts/session_stabilization/final_offline_files.json`;
stdout `final_combined_offline.txt`. Las cifras dirigidas previas arriba son
invocaciones separadas, no un total acumulado.

Replays curados de Hero Armor, Select Striker, H&H, Keys0/10, Normal/Poor y popup
K Coin están incluidos. Evaluators dirigidos anteriores: Craft13/13, Equipment14/14;
H&H11 positivos/6 negativos más690 frames de corpus. No evaluator global sin
invalidación. `git diff --check` pasa al cierre (exit0; avisos normales LF/CRLF);
evidencia grande/logs/harnesses continúan locales. El checkpoint incluye assets runtime
y fixtures curados de replay (ROIs, o frames Craft reducidos a960 px de ancho), con
sus manifests de procedencia; no incluye capturas originales, logs ni artifacts.

La primera validación amplia dejó8 failed/1396 passed/4 skipped (522,59 s),
conservada en `combined_offline.txt`. Cinco incompatibilidades de harness
Quick Menu/board se reprodujeron cargando módulos baseline en memoria (5 failed,
9,51 s, `baseline_regressions.txt`), sin restaurar archivos. Los otros tres eran
conteos globales decorativos de detectores98 frente99; se mantienen assertions
de scopes/identidad/comportamiento, no esa cifra ajena al contrato local. Los tests
Quick Menu ahora preservan fail-closed ante lineage perdida, y el harness board
scriptado separa el precheck físico del test de spacing. No se ocultan fallos live
ni se retiran guards para obtener verde.

Deuda causal restante: chrome SDK X sola sin reward-granted (cierre tardío/reward
acreditado); whitelist informativa de SessionReport; Accessories MAX/result/effect
físico todavía abierto; triple explícitamente identificado post-fix y No Ads temporal
full recovery natural. No se reabre targeted swipe. Un checkpoint local, sin push.

### Preparación del único checkpoint local

Revisión del índice:65 archivos causales, incluidos assets runtime y21 archivos de
fixtures curados/manifests (aproximadamente5 MB en total; ningún archivo individual
mayor de1 MB). No logs, raw captures, harness outputs ni artifacts. Staging de
`flow_registry.py` por cuatro hunks WB/Gold; su hunk SummonPet queda en worktree.
El diff completo de `test_portal_obstruction_recovery.py` es previo y queda fuera;
los tests/assets/replays nuevos de portal/H&H sí se incluyen desde sus archivos dueños.
El resto del trabajo independiente listado arriba no entra al checkpoint.

Comprobación mínima adicional desde INDEX, con todos los módulos bot cargados del
índice y los assets/fixtures comparados con su versión revisada: **82 passed en2,50 s**
(seis archivos: registry, Gold, WB Sell, VerifiedTransition, portal probe/replay).
Comprueba que excluir SummonPet no deja wiring causal incompleto; no reemplaza ni
se suma a1906/4 de la validación final anterior. Hashes de los archivos independientes
preservados. `git diff --cached --check` verde. Sin suite completa adicional ni live.
