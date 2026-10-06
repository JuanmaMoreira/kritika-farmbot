# Aceptación combinada 28/28 — 2026-10-05

Baseline `656460c4b16526ced5ae46b36764240aa5ec71cb`, rama
`rebuild/stable-baseline`. Cierre posterior autorizado en un único checkpoint
`fix: stabilize full roster farming session`, con commit/push si validación verde.
Este frente preserva el trabajo independiente Summon Pet y scripts locales previos.
Aceptación principal: GUI manual27ae46d4,28/28 técnicos y28 Rotation;
informe final/hash/config/cobertura en [FULL_ROSTER_CHECKPOINT](FULL_ROSTER_CHECKPOINT.md).
Los estados «en curso», «pendiente» y «sin commit/push» de cada sección inferior
describen ese momento histórico; no reetiquetan ningún run rojo.

## Incidente original (permanece FAILED)

Log `logs/20261005T140313.234892Z_session_72bd9da9.jsonl`; run
`783b9af222a14fa59561ccdde928216b`; session
`e2c4b47466c04f0d9b14ba8fab03a6dd`. Session inició 11:03:20.754897 -03 y
falló 11:39:40.046365 -03: 36:19.291 de Session, ~36:26 de runtime GUI.
Halo Mage, Elemental Fairy y Noblia completaron tres scopes y tres Rotation.
Steam Walker falló en el scope 4. USER_GT corrigió el relato inicial de
«13 completados/personaje 14»: el símbolo anterior al 4 en GUI fue confundido con 1;
SessionReport/JSONL mostraban correctamente 3 completados.

Reconstrucción causal:

| Event | Hora -03 | Estado/acción |
| --- | --- | --- |
| 4196 | 11:37:44.741903 | Scope 4 iniciado tras Rotation de Noblia |
| 4273 | 11:38:01.017632 | Black Market COMPLETED, Lobby |
| 4283–4284 | 11:38:03.973881 | Sapphires 10, consensus fresco |
| 4290–4295 | 11:38:07–09 | Hub acreditado; WB elegible; identidad Steam Walker |
| 4302/4307 | 11:38:12–13 | Select Boss y entrada WB verificadas |
| 4314 | 11:38:20 | Start éxito, primer intento; battle acreditada |
| 4318 | 11:38:23.214528 | Auto ON→ON, cero taps, source21204 |
| 4323 | 11:38:23.822855 | Timer 60 s |
| 4330 | 11:39:29.260356 | Current Damage/battle resuelto, source21872 |
| 4331–4334 | 11:39:30.708506 | Raid Complete resuelto, confianza1, source21887; wait COMPLETED |
| 4335 | 11:39:30.710514 | Inicio de ContinueAfterWorldBossRaid, primer intento |
| 4338–4342 | 11:39:37–39 | Sin salida acreditada tras espera6 s + grace2 s; snapshots frescos conservan Raid Complete |
| 4343 | 11:39:39.843868 | Primera divergencia de contrato: retry_guard_rejected desde source21977 resuelto y recuperable |
| 4345/4346 | 11:39:39–40 | flow.failed / session.failed |

FailureEvidence:
`artifacts/failure_evidence/failure_e545ba29cd2d4c75b8b0dac90212e880/failure.json`.
Frames/snapshots21966,21972,21977 muestran battle + Raid Complete. No contradicción
de GT ni regresión Auto; Equipment Full/Combine/Sell/H&H no ejercidos en este WB.

**LIVE_EVIDENCE:** el primer tap no tuvo salida visible acreditada. Su causa física
permanece UNKNOWN; no se atribuye a ADB, geometría o animación sin evidencia.
**IMPLEMENTATION_CONTRACT:** `retryable_from=lambda _:False` impedía recuperar
este cierre sin consumo, incluso con el mismo overlay fresco y resuelto.

Fix mínimo en `WorldBossActivity`: para Continue únicamente, usar `_is_raid_complete`
como retry guard. Conserva precondition exacta, postcondition WB limpio, bounds
6+2 s y máximo2 intentos del driver existente, freshness estricta, contradicciones
y cleanup. UNKNOWN/AMBIGUOUS/stale/BASE ajena no autorizan retry. Start y confirmaciones
consumptivas siguen sus guards originales; no nuevo raid ni segunda confirmación de reward.

## Validación del fix

Una invocación final: **272 passed, 33.44 s**: World Boss flow/equipment Sell/eligibility,
VerifiedTransition, Auto Battle, Session y productive runtime. Replay semántico causal
con el driver real: persistencia del Raid Complete original21887→21966→21972→21977,
retry fresco exitoso, UNKNOWN, AMBIGUOUS con candidatos ajenos, BASE ajena, stale y
persistencia tras dos taps. No cambio perceptivo; no evaluator invalidado.
Una invocación previa tuvo243 passed/29 errores de setup por permisos del temp de pytest;
se repitió con basetemp bajo artifacts. Las cifras no se suman.

Smoke live focal: `logs/20261005T152339.979596Z_wb_raid_exit_focused_5f1aafb4.jsonl`,
run`2407cbf03edb4017bbc106bedeff5ef6`, session`8046422458ff4a5c8f008ae10b6f759b`.
Rotation natural desde Steam Walker→Telumpel, WB con elegibilidad diaria normal;
Auto ON→ON/cero taps(e75), Continue exit primer intento(e96), WB completo(e97),
Rotation(e129), session.completed(e131), runtime.closed(e134,12:25:51.443826 -03).
No se provocó un tap perdido live ni se fabricó trabajo diario.

## Campaña roja 1 — Galaxy Lord / Daily Quests

Nueva GUI recargada desde disco; rutina literal BM→WB→Gold→Mailbox→Quests→Rotation,
28 personajes y debug. Log `logs/20261005T153038.248412Z_session_fcbf2fa7.jsonl`.
El scope1 es Eclair; no cuenta los scopes del run original ni el smoke.

Hash previo de522 archivos Python/assets/config:
`51bd4999ef9c811395d0c56860329e47b4715833f3eed84b65be6cf8a2856aae`.
Manifest local `artifacts/acceptance_28_20261005/campaign1_before_hashes.json`.
`.env` sólo se hashea, nunca se imprime/versiona. La aceptación permanece pendiente
hasta28 scopes,28 identidades,28 Rotation, Session COMPLETED, cero fallos técnicos
y comparación final de hashes. Este run terminó FAILED y queda histórico.

Run`7c27fa66b0fe4b84a2026b09fc865801`, session`70a3b1e4f70c4f2db5369e39c9e06320`.
Start12:30:45.667145; FAILED13:43:19.731245 (-03), **72:34.064**.
4 personajes completados/4 Rotations: Eclair, Wandering Master, Shadow Mage,
Blood Demon. Scope5 Galaxy Lord: BM/WB/Gold/Mailbox completos, Quests FAILED.
10 Ads returned con10 efectos Sapphire frescos,5 raids WB, Auto ON→ON/taps0;
36 entradas MW productivas. Sin Video0 observado. Chaining MW directo en los4
completos, cero Lobby indebido. Hash posterior522 archivos idéntico al previo;
trabajo independiente también idéntico (`campaign1_after_hashes.json`).

Último estado correcto: Gold MW(e7012), Mailbox close→MW(e7038/7044),
QM→Quests(e7057) correcto; Claim All único ejecutado desde Daily fresco43965.
e7059 abortó en43988 a13:43:19.457997: Quests RESOLVED sin MODE_DAILY_QUESTS.
FailureEvidence`artifacts/failure_evidence/failure_2c1319b395ca46d58d485f5d7f75a517`:
43986/43987 conservan Daily;43988 pierde tab activo (confianza.644) mientras
el aviso «MAX limit of Hero Armor Crafting Material» pasa sobre la pestaña.
**LIVE_EVIDENCE:** Daily permanece físicamente visible; no navegación ajena.
**Root cause:** `_has_incompatible_daily_state` confundía ausencia de señal
Daily con contradicción resuelta durante el wait posterior al claim.

Fix local: Quests resuelto sin Daily permite esperar pasivamente, sin input;
settled sigue exigiendo MODE_DAILY_QUESTS fresco/estable. Tiempo8 s sin cambios,
claims únicos, contextos/overlays ajenos y AMBIGUOUS conservan fail-closed.
Replay de los3 snapshots: sólo43988 habría abortado con el guard anterior;
con el nuevo no aborta y tampoco acredita settled. Tests de recuperación,
persistencia/timeout, Claim All y progress reward, contradicciones y contratos.

Una invocación final afectada: **92 passed,15.87 s** (DailyQuests, QuickMenu,
handoff, RuntimeObserver, registry). Los272 anteriores WB conservan validez;
no se suman invocaciones. No cambio perceptivo/global ni evaluator invalidado.
Smoke focal`logs/20261005T165134.801789Z_daily_max_toast_focused_87aefd6b.jsonl`,
run`92acee835f4b4f00b558448903f383d4`, session`2681c5817f7f420d9ba4230f365809c4`:
Galaxy Lord Quests fresco→Close→MW exacto, nueva entrada Daily→noop→MW→Rotation,
Session COMPLETED13:52:04.018128 (-03). No nueva aparición MAX forzada;
la divergencia MAX queda cubierta por replay/regresión, no por este smoke noop.

## Campaña roja 2 — Ice Warlock / WB Equipment Sell

GUI real recargada,28 personajes, debug y misma rutina literal. Inicio nuevo
scope1 desde el Lobby dejado por Rotation focal, no acumula scopes anteriores.
Log`logs/20261005T165358.677970Z_session_166fdcaa.jsonl`.
Hash522 archivos previo`331fccced40de24e0074c72cee5b3a0581b12ea563e705ff6bcdcedd2de627e2`
(`campaign2_before_hashes.json`). Código/assets/config congelados durante el run.

Run`e950b7ba8dd34a8f994f4fc84051df30`, session`ce3e43c1de69406aa2694bf4a3c558d5`.
Inicio13:54:06.742099, FAILED14:45:02.221437 (-03), **50:55.479**.
4 completos/4 Rotation: Rang, Strike Archer, Hastati, Dark Valkyrie.
Scope5 Ice Warlock: BM completo; WB FAILED antes de battle/Auto.
8 Ads con efecto Sapphire,4 raids WB,30 entradas MW productivas;4 chaining MW
directos, cero Lobby indebido. BM1 retry recuperado. Hash522 archivos previo/post
idéntico, trabajo independiente intacto (`campaign2_after_hashes.json`).

Último estado correcto: Start→Full(e4855), Combine no_relief_available→WB(e4881),
nuevo Start→Full fresco30371(e4886), dismiss→WB30397, QM Inventory→Sell(e4900).
Tail accesible page8/slot15, Item Count128/128. Detail fuerte30528/30530 coincide
en Pants (Enhance), Epic, pants, Enhance=true, visualEpic, Sell=true(e4954).
Primera divergencia(e4955,14:45:01.691724): continuidad CV de title rechazada,
score.9989751577 < threshold.999. No Open Sell, ningún confirm, ningún efecto.
Bulk denied→relief failed→WB/session FAILED(e4962/4963).
FailureEvidence`failure_153faddcf03b440bbe90f3f646310d61`: el ring de snapshots
principal llega hasta30463/QM WB, porque Sell samplea el source fuera del observer.
No se presenta ese ring como evidencia del detail30530.

Adquisición read-only posterior sin input (`ice_warlock_panel`): cinco lecturas
fuertes y capturas aún muestran exactamente Epic Pants Enhance/Sell disponible;
una lectura OCR inconclusa se conserva como tal. El frame original comparado por
CV no está guardado; su desviación de píxeles queda registrada, sin atribuirla
específicamente a codec/glow. **Root cause técnico:** un miss de continuidad CV
era terminal aunque no había contradicción semántica demostrada y todavía podía
adquirirse evidencia fuerte fresca sin input.

Fix local `EquipmentSellRuntime`: mantener fast path y thresholds; sólo tras
miss de píxeles ejecutar una lectura de consenso fuerte bounded, sin input.
Debe coincidir el mismo item/familia/tipo/tier, Sell disponible y visual guard;
secuencias/tiempo/input lineage/cancelación verificadas. Si falla, deny. Popup
Bulk, policy, confirm único y fresh Item Count siguen siendo los guards finales.
No retry de acción económica, nuevo scan ni cambio de threshold. Tests directos
23 passed/1.73 s: recovery.998975, UNKNOWN, changed/protected, stale,
unconfirmed, Sell disabled, visual contradiction, input lineage y cancelación.

Una invocación proporcional final: **815 passed/62.20 s**, cubre Sell directo,
scan/Inventory, WB, MW, Craft, Socket, DailyQuests, handoff/registry, transitions,
Auto/Session/runtime. El replay ajustado a Epic Pants Enhance pasó23 tests/2.54 s
en una invocación aparte; no se suman. No evaluator invalidado.

Smoke live focal`logs/20261005T175419.781009Z_wb_sell_continuity_focused_ecc19623.jsonl`,
run`ebba126de6704182ab10603c95dbcd43`, session`2c4cc5b7fa94412c8df4469b3b6b18dc`.
Ice Warlock restaurado desde detail→Inventory fact→WB exacto; Full→Combine sin
relief→nuevo Full→Sell. **Reproducción natural post-fix** e180: score.998960<.999,
revalidación fuerte fresca sources714/717 del mismo Epic Pants Enhance, sin input.
e194 Bulk success, **confirm1, count128→127**; e198 WB relief success; Start battle,
Auto ON→ON/taps0(e211); WB completado y Rotation(e278); Session COMPLETED
14:57:19.680834, runtime.closed14:57:19.733919 (-03). Ningún fallo técnico.

Sonda auxiliar fallida de adquisición (no campaña, sin sesión ni inputs):
`logs/20261005T174812.014831Z_sell_panel_readonly_35981901.jsonl`,
run`4d704da48e7040148b6956bbd6719e32`, runtime.failed14:48:17.912273 (-03),
por constructor de script con keyword `ocr_engine` inexistente. Se corrigió
el script local a argumento posicional. Repetición read-only
`20261005T174848.094115Z_sell_panel_readonly_e4e979fb.jsonl` completó y preservó
las seis capturas/lecturas sin input. El runtime.failed auxiliar permanece rojo.
Los errores de imports/assertions previos a abrir runtime no crearon sesiones.

## Campaña de aceptación 3 — roja histórica

Código/assets/config nuevamente congelados. Manifest522 archivos
`campaign3_before_hashes.json`, hash
`0da455a794bcb8b93c1091e59540a827b894be7049a6511078daeffadcce13ee`.
Nueva GUI recargada, rutina exacta y28 personajes desde scope1 nuevo.
Log`logs/20261005T175845.466159Z_session_4ff09003.jsonl`.

Run`9e98aa1fc019434f8749aaa3c4e55586`, session`edadabb62e104cbdac322bd0e5b349cf`.
14:58:52.991269→15:20:23.292554 (-03), **21:30.301**, un personaje Eilla
completado/una Rotation. Scope2 Lina: BM/WB completos, Gold falla en Keys→Gold
capacity relief→Treasure drain. Dos raids Auto ON→ON/taps0; tres ads y efectos
Sapphire;11 MW entries. Hash antes/después idéntico,522 archivos; cero cambios
productivos durante el run y trabajo independiente preservado.

Último estado correcto: Silver→Gold encuentra output_full e1787, ACK e1804,
entrada Treasure/OPEN_ONCE verificado y100 inputs RIGHT respaldados por Gold.
Último input e2327→2329, source12223,15:20:16.587986→16.724200 (-03).
Después llega la frontera local Karat: el botón económico se bloquea, pero la
rama del loop espera global/title en vez de cerrar el reward que lo tapa.
Primera divergencia causal: `local_karat` sólo espera y no compone el finalizer
existente; e2346 15:20:22.918727 `local_karat_timeout`, dismiss_inputs0,
karat_boundary_seen=false; flow.failed2363/session.failed2364. No premium tap.

FailureEvidence`failure_9bfdf6e4f07041dfbbb1ca75226e5a90`: frames12278/12284/12290
UNKNOWN/observations vacías. Replay restaura geometry2712×1224 desde los PNGs
downscaled960×433; en los tres Karat bar1.0, reward1.0, Gold0, title0. Este replay
no pretende recuperar el PNG nativo original. Mismo reading causal en el harness
real del drain confirma cierre lateral y fresh clean Treasure, cero económicos.

Fix local `treasure_fast_drain`: local Karat sin Gold + reward positivo utiliza
el mismo `_finalize_exhausted` existente de Karat-entry. Sin reward mantiene
espera sin input bounded. Latch/guards/postcondition/ROIs/thresholds intactos.
Tests directos71 passed/1.60s; invocación afectada338 passed/39.61s (Treasure,
Keys, Gold, MW routing, TapThrough, registry). No sumar invocaciones; anteriores
815 tests siguen válidos en el código no invalidado. No evaluator invalidado.

Smoke`20261005T183016.935802Z_treasure_karat_focused_f43215c0.jsonl`,
run`23080d35dc5c4ba6b4e72d3bdedc596b`: boundary nativo actual confirmado,
finalizer GOLD_KEYS_EXHAUSTED, **un dismiss, cero económicos**,1.547s.
Smoke ejerce el finalizer/entry; la rama nueva del loop se prueba por replay.
Cleanup auxiliar incorrecto intentó el owner Treasure→Lobby de entrada Lobby:
Back volvió físicamente a MW con New Ranking (entrada real QM desde MW),
timeout y runtime.failed18 15:30:33.856246. No sesión de aceptación ni fallo del
finalizer. Primera sonda cleanup siguiente también falla por BASE no limpia:
`20261005T183138.262527Z_treasure_post_finalizer_cleanup_62dc2521.jsonl`.
Ambos rojos auxiliares permanecen registrados. Cleanup corregido
`20261005T183234.527806Z_treasure_post_finalizer_cleanup_80e3b68e.jsonl`
usa ranking confirmado→ACK existente→fresh MW→QM Lobby verificado, completado.

## Campaña de aceptación 4 — roja histórica

Manifest `campaign4_before_hashes.json`,522 archivos, hash
`d7601d87058886cfdffacce862e061989314040eb497ca9d01e2f1ef96696269`.
GUI recargada después del último fix;28 scopes nuevos desde Lina Lobby.
Log`logs/20261005T183419.396311Z_session_6aa08c50.jsonl`,
run`404e5d31e5974f7da80208c739ab8739`, session`d291501d507b4c81af681ea45a519645`.
Session.started15:34:26.290212 (-03). Sólo observación y derivados mientras
corre; sin cambios de código/assets/config productivos.

Fin15:38:26.259479 (-03), **3:59.969**,0 personajes completos/0 Rotation.
Lina BM completo, WB no elegible→hub reutilizado. Gold Stages prerequisite MW
resuelve Equipment/Sell y Socket Full; CLEAR1 efecto203→103 source2201 confirmado,
CLEAR2/ACK e681 éxito source2379; el HUD posterior tiene3, limpio y MW resuelto.
Primera divergencia perceptiva e684 source2409 15:38:22.827713: Sapphire
UNREADABLE; e687/690 sources2424/2439 repiten confidence.59926 sin valor parseado.
e714 flow.failed/e715 session.failed`mw_fresh_sapphire_effect_unavailable`.
FailureEvidence`failure_1ef2779d77054f5f978ff76efa49c749`, frames2409/2424/2439.
Hashes antes/después iguales y trabajo independiente intacto. Run permanece rojo.

Adquisición nativa read-only posterior reproduce3→OCR`③` (confidence.65069)
rechazado correctamente por el parser. Primera sonda
`20261005T184016.504045Z_mw_sapphire_three_readonly_fcf9c5e6.jsonl`,
run`8d37358e94ed4617ad0bc46cedd2ea81`, runtime.failed15:40:27.722246 por output
Unicode cp1252 del script (sin input); repetición JSON ASCII
`20261005T184123.455020Z_mw_sapphire_three_readonly_34642d16.jsonl` completa.

Fix mínimo `build_monster_wave_sapphires_extractor`: grayscale local, scale2
vigente, mismo ROI/parser/min confidence.50/consenso2/max observations3/freshness.
Hub conserva explícitamente preprocessing previo; Lobby intacto. Replay30 crops
(3 nuevas nativas +27 positivas del corpus) verde con grayscale; confidencias
3=.85283/.83058/.83058. Tests77 passed/18.06s incluyen corpus contextual negativo
y consenso real de crops curados pequeños; validación afectada final en una
invocación **530 passed/30.02s** (OCR/facts/MW/Gold/Stages/WB/Treasure/Keys).
815 tests previos no invalidados se conservan; invocaciones no se suman.

Smoke`20261005T184401.122699Z_mw_sapphire_three_focused_54838c94.jsonl`,
run`4a6616a561794953872c3ce13ee1cbc4`, auxiliar rojo: OCR confirma3 sources23/48,
pero efecto rechaza edad2s tras backend cold. No inputs ni relajación de edad.
Script corregido aplica el warm-up ya presente en builder MW antes de acquire.
Smoke`20261005T184531.249962Z_mw_sapphire_three_focused_dc9d5e1d.jsonl`:
owner `read_sapphires_after_clear` confirma3/consenso sources64/79/confidence.83416,
cero consumo, luego QM Lobby fresco. Runtime COMPLETED; este smoke valida
directamente el consumidor del fallo, sin provocar otro CLEAR.

## Campaña de aceptación 5 — roja histórica

Manifest`campaign5_before_hashes.json`,522 archivos, hash
`34e91030df42122526616805cce8b5fc3e6460fd65894b2dc61d463ed4269779`.
GUI real recargada tras el último fix, rutina exacta/28 personajes.
Log`logs/20261005T184728.628013Z_session_fa1e054f.jsonl`,
run`d5604ea5ec5a4228b2b8d68c166265c5`, session`1209487bb32e40ebae3aaee6bda2424b`.
Inicio15:47:35 (-03), scope1 nuevo Lina. Sin cambios productivos durante el run.

Fin16:31:03.313256 (-03), **43:28.130**,3 scopes completos/3 Rotation;
scope4 **Blade Dancer**, Gold→MW Equipment Full→Combine→nuevo Full→Sell.
No Stop Safely fue ejecutado durante la interrupción de herramientas por usage:
la campaña siguió hasta su fallo real. Hash terminal522 archivos coincide con
`campaign5_before_hashes.json`; trabajo independiente intacto. El usuario volvió
este personaje a Lobby después del fallo; ese estado no se presenta como el
popup original.

Antes de la divergencia, cuatro Bulk verificadas redujeron176→149, capacidad132.
Último estado correcto e5460/5461 sources24791/24792: consenso fuerte
`Laoku's Destructive Phantom Sword`, Legendary Weapon, Sell y grade visual.
Continuidad válida e5463 source24793; OpenEquipmentSell e5464..5466
16:30:56.837672..56.913417. Primera divergencia e5468 source24798
16:30:57.663431: identidad OCR `Selling [Laoku's Destructive Phantom`, sin `]`;
15 muestras frescas incompletas hasta24849. **Cero confirmaciones de esta venta**,
CancelEquipmentSale e5485, bulk FAILED e5486 y relief FAILED e5487.
Gold failed e5502/session failed e5503
`mw_equipment_relief:sell_failed:bulk_not_started:confirmation_unreadable_or_stale`.
FailureEvidence`failure_db8e480ab13b4336814c842976f427e4` conserva la ring global
24503/24510/24515, anterior al reader raw: no se atribuye el popup a esos frames.

Adquisición focal nativa del mismo page9/slot3, sin venta:
`20261005T205632.905742Z_sell_long_name_readonly_4eb18317.jsonl`,
confirma popup con nombre en dos líneas: primera `Selling [Laoku's Destructive
Phantom`, segunda `Sword] for 15 K Coins.`. Reader anterior corta identidad y
elige ROIs Bulk de una línea. Cancel fresco, mismo detail/Item Count y Lobby
restaurados. Causa demostrada local de lectura, no cambio de policy.

Fix `equipment_sell_reader.py`: sólo si identidad fuerte empieza Selling `[`
y carece de `]`, leer la continuación física independiente; confidence mínima
de ambas líneas. Parser admite el sufijo exacto `K Coins`; exige nombre cerrado
y Bulk scope independiente exacto. La identidad completa selecciona ROIs K Coin
existentes. No ajustes globales/confidence/consenso/freshness ni input/retry.
Replay curado pequeño nativo + negativos y corpus anterior: **203 passed/13.08s**.
Validación final proporcional Sell/Equipment owners/WB/MW/Craft en una invocación:
**685 passed/124.17s**. Los530/815 anteriores se conservan donde no invalidados,
sin sumar invocaciones como una sola cifra. `git diff --check` sin errores.

Smoke productivo Inventory Full
`20261005T210004.038306Z_sell_long_name_focused_5b94c32d.jsonl`,
run`23c1e743cd32410f9df8b0f267322340`: mismo Phantom Sword,
popup completo consensuado179/188; confirm único y count149→139; Enhance
Legendary139→137 y Epic137→131, Full resuelto131/132, cero expansiones.
El script auxiliar esperaba outcome `relieved` en vez del contrato `success`:
AssertionError posterior al éxito real, **runtime.failed auxiliar preservado**.
Cleanup separado `20261005T210204.974438Z_sell_long_name_cleanup_e3cacaec.jsonl`
verifica Item Count131/132→Back conocido→Lobby fresco67; Runtime COMPLETED.
Dos sondas auxiliares previas fallaron por missing argument `after_sequence`
(cero inputs) y por exigir BASE resuelta bajo QM (OpenQM único); ambos logs
rojos preservados, no cambios runtime por errores del harness.

Identidad por scope en la siguiente campaña: evidencia ADB externa de sólo
lectura disparada por `session.character.started`, antes de BM, con PNG nativo
y timestamp propio. Sin OCR concurrente ni cambios de guards/Rotation. Identidad
runtime opcional None permanece sin reinterpretación; el informe podrá aportar
nombre físico explícito cuando el crop sea legible contra el mapping USER_GT.

Reportes derivados locales (sin cambios runtime):
`artifacts/acceptance_28_20261005/20261005T153038.248412Z_session_fcbf2fa7.summary.json`
y `.table.md`. Routing se verifica contra la BASE publicada por Gold y las
restauraciones exactas Mailbox/Quests, detectando Lobby indebido tras MW.

## Campaña de aceptación 6 — roja, versión congelada

InicioGUI18:08:54.409 (-03); Session.started18:09:01.579409.
Log`logs/20261005T210854.344069Z_session_0db54e8e.jsonl`,
run`810a66e4bfba4ddb859c64fe7c2a0a72`,
session`719b4e4edcad45c8816e52ba5d84322c`.
Manifest`campaign6_before_hashes.json`,522 archivos,
SHA256`ba89604adb4556836ca57e59015bdfcd58d8f8c7cfc23628d04f5b30132eef13`.
RutinaGUI exacta,28 nuevos scopes desde Blade Dancer Lobby.
Captura externa de sólo lectura armada antes de Run Session:
`artifacts/acceptance_28_20261005/campaign6_identities/captures.json` y PNG nativos.
Sin OCR concurrente/inputs adicionales ni cambios productivos durante campaña.

USER_GT posterior durante campaña: existen ads de ~5 s; usuario prohíbe
interrumpir/reiniciar este intento y preserva su aceptación aunque un ajuste
posterior no causal de FAILED se prepare para futuros runtimes.
Auditoría `ads_manager.py`, `AndroidAdsObserver`, `stages_wiring.py` y caller:
**no existe gate elapsed>=30, mínimo de edad ni espera antes de evaluar chrome
terminal acreditado**. Back/close normales actúan en la observación autorizante;
return_grace4 sólo aplica después de main sin results, no ante reward-ready.
No se fabrica un cambio productivo: contrato explícito en ARCHITECTURE y GT,
regresiones nuevas `tests/test_ads_short_terminal.py` prueban5/8/12 s con Reward
granted y close fuerte,5 s sin terminal, X no acreditada, transición multipart
temprana y progreso>60 s. **69 passed/5.00s** en una invocación con Stages/Ads,
incluidos bounds absolutos/external returns/native freshness existentes.
Sin cambios de bot/tools/assets/config ni nuevos inputs de teléfono/GUI.
No se afirma adquisición live de un ad de5 s ni cierre de la deuda X sola.

### Mejora posterior de X circular SDK — aislada durante campaña6

USER_GT posterior: último ad tenía X lista unos20 s antes de que AdsManager
cerrara. El usuario confirma explícitamente la variante física X negra dentro
de círculo blanco en la esquina superior derecha, igual a la captura nativa
histórica `ad_campaign6_char2_terminal.png`. Esto acredita esa variante concreta,
sin ampliar a cualquier X de contenido o SDK desconocido.

Scope6, segundo ad: launch e7124, progress .956 a64.297 s e7148; reset a.279
a104.172 s e7150; external_return e7151 a116.172 s y returned e7153 a119.281 s.
Cero `sdk_back`/`visual_close`: el observer sólo admite chrome reward-granted.
El bloqueo es la variante perceptiva ausente, no minimum elapsed.

Adquisición externa de sólo lectura de UN ad natural siguiente, scope7 Cat Acrobat:
launch e7946,19 PNG nativos, resumed/focus por captura, sin inputs ni ad solicitado.
`artifacts/acceptance_28_20261005/natural_ad_x_review/{captures,launch,terminal,replay}.json`.
Partes iniciales explícitas, incluida Ad2of3 en07.png, sin terminal; X circular
visible desde13.png a72.236991 s con Google AdActivity concordante. Runtime
original no publica cierre en ninguna muestra; retorno e7969 a109.609 s,
**37.371989 s extra** desde la primera captura X, Sapphire fresco e7994.
No se interpreta un cambio de contenido como fin de parte/fin de ad.

Patch futuro en `artifacts/acceptance_28_20261005/short_ads_patch/`, completamente
aislado de bot/tools/assets/config activos. Dos crops de chrome fijo (círculo X
y sonido) y búsquedas restringidas con threshold existente. Sólo Google
AdActivity bajo package juego/focus concordantes publica `sdk_round_close` y
hitbox normalizado(.922,.059); Reward granted conserva Back vigente. El owner
existente despacha ese close inmediatamente a5 s, una vez por key, y observa
efecto fresco. Progress/reset/stall15/60/absolute180/external bounds intactos.

Validación aislada final: **80 passed/5.79s**, una invocación Ads/Stages/native
freshness/progress, replay de chrome adquirido, X de contenido/posición ajena,
chrome incompleto, main/external/focus desconocido y otro AdActivity negativos,
partes anteriores y close real a5 s con tiempo falso. Invocación inicial79
passed/7.18s queda separada; no se suman. Replay19: anteriores01..12 sin close,
13..18 close acreditado,19 main sin hitbox. No se ejecutó un close nuevo live.
Fixtures portables finales (sólo chrome, contenido ajeno en cero) y owner aislado:
**80 passed/4.42s** en una invocación separada. Patch revisable
`short_ads_patch/review.patch` e `install_manifest.json` con hash original y futuro
de cada destino;9 archivos preparados, cero escrituras productivas.

Manifest `campaign6_mid_sdk_round_isolated_hashes.json`:522 archivos,
SHA256 idéntico a inicio `ba89604adb4556836ca57e59015bdfcd58d8f8c7cfc23628d04f5b30132eef13`,
changed[] e independent_changed[]. NO Stop/reload/restart ni escritura de
assets/config productivos. Si esta sesión termina28/28 limpio, su aceptación
permanece válida por instrucción explícita del usuario; esta mejora posterior
no causal de FAILED se incorpora sólo al próximo runtime.

### Cierre rojo de campaña6 y corrección causal

Session.failed e10072,19:48:00.906075 (-03); runtime.closed e10074,
19:48:01.302644. **7 completos,7 Rotations; scope8 Crimson Assassin,
Drakenn09 observado nativamente**. DuraciónSession98:59.327. El manifest final
`campaign6_terminal_hashes.json` conserva exactamente los522 hashes anteriores
y los archivos independientes. Su FAILED permanece histórico.

Gold final investment→keys_promotion: e9985 facts Keys frescos; e10007,
19:47:36.876715, Silver→Gold output_full después de una sola Confirm.
ACK verificado e10024,19:47:40.379773; retorno MW→Treasure e10040,
19:47:51.960144; selector e10046,19:47:55.717310; OPEN_ONCE verificado.
**Primera divergencia:** la captura inicial del drain59763 era destello blanco
de reward, globalUNKNOWN y sin pairGold local. El entry fallback sólo medía
ese frame y devolvióunknown_state inmediatamente: e10050,19:47:59.942471,
0 inputs,0 dismisses,0 Karat; preparación failed e10051, Gold failed e10071.
Evidencia `failure_d9049eb14d1a4ff791f661944f748681` y captura nativa posterior
`campaign6_failed_current.png`: reward Platinum Key, pairGold bar positivo.

Fix local en `treasure_fast_drain.py`: tras first-open verificado, esperar
pasivamente hasta5 s usando nuevas secuencias/timestamps; misma autoridad
Gold/Karat existente, cero input sobre flash/UNKNOWN/stale. Foreign resuelto
y contradicción abortan. Sin segunda OPEN_ONCE, cambio de threshold ni waits
globales. Directos **77 passed/1.92s**; replay causal en
`treasure_entry_replay.json` usa flash archivado downsampled redimensionado
(no acredita scores nativos), reward nativo y secuencias/frontera sintéticas.

Smoke `20261005T230402.696557Z_treasure_entry_focused_9e092811`,
run`372a9e626cf34073b2a78ae1c617b2f7`: lineage roja conservada, fresh Gold reward;
drain120.344 s,95 inputs Gold autorizados (no equivalen a95 batches),1 dismiss,
Karat latch y GOLD_KEYS_EXHAUSTED, retorno QM Lobby verificado; runtime.closed
20:06:15.995686 (-03), sin runtime.failed. No cuenta para aceptación.

### AdsManager incorporado después del FAILED, para campaña7

USER_GT actualizado: nunca cerrar antes de recompensa lista, cerrar cuanto
antes al acreditarse, distinguir pasos intermedios de completion. Se instala
la X circular SDK adquirida con los dos crops de chrome y Android/focus.
No hay gate mínimo temporal. Se elimina autoridad de Back por timeout para
SDK/embedded desconocido: stall/absolute pueden fallar sin abortar la recompensa.
Fallback sólo despacha chrome terminal fresco o retorno externo acotado;
conserva dos retornos por visita y presupuesto total, con hasta dos Back SDK
acreditados en total. Next ad no se considera terminal por nombre; su hitbox
explícito sigue sin adquisición, progreso/reset multipart conocido se observa.

Directos finales Ads **82 passed/3.55s**. Una invocación final afectada de
Treasure/Keys/Gold/wiring/composición/Ads/Stages/replays: **451 passed/48.47s**.
Resultados anteriores permanecen como invocaciones separadas. No short ad
forzado, no efecto Sapphire inventado; validación física de cierre nuevo queda
para un ad que aparezca naturalmente en el próximo runtime. Sin commit/push.

## Campaña de aceptación7 — FAILED histórico, congelada

RunSessionGUI20:08:58 (-03), Session.started20:09:04.417799;
log`logs/20261005T230857.999888Z_session_0cb75379.jsonl`,
run`5ba8bdaa202b4a87a67355ffa50ae19e`,
session`f68e12b17c544b2bbbc22e5ac372d069`.
Nueva sesión desde scope1 Crimson Assassin/Drakenn09, Lobby nativo.
Rutina exacta BM→WB→Gold→Mailbox→DailyQuests→Rotation,28 scopes GUI.
Freeze `campaign7_before_hashes.json` y comprobación GUI-ready:524 archivos,
SHA256`064cffb6663979e8e608f48db18edcdc90eb31ec4027e00cfb987139bad48453`,
changed[] e independent_changed[]. Ads/crops nuevos y fix Treasure cargados;
sin modificar código/assets/config durante la campaña. Capturas de identidad
externas sólo lectura en`campaign7_identities/`; un ad natural observado
sin input ni solicitud adicional en`campaign7_natural_ad/` si aparece.

Session FAILED20:24:00.813563; runtime.closed20:24:00.941532. Duración de
Session896.395764 s (14:56);1 personaje completo/1 Rotation. Scope2 Flame
Striker, identidad física DRAKEN六FS. Hash terminal idéntico al inicial:524
archivos, mismo aggregate, changed[] e independent_changed[]. No se reetiqueta.

Primer ad del scope2: launch e1458 20:18:17.412712, transición natural Ad1of2→
Ad2of2; las capturas nativas12–15 muestran X circular SDK sobre fondo blanco.
El detector anterior comparaba también el fondo: X score.073824, aunque el
control era el adquirido. No publicó cierre. Retorno final tras visita externa
bounded, Ads RETURNED93.625 s; efecto Sapphire fresco68→386 e1503. La X ya
estaba visible en la captura a67.732 s: retraso observado de aproximadamente26 s
hasta RETURNED, sin atribuir un instante de aparición anterior no capturado.

Segundo ad: Sapphire inicial86; e1848 ad activo y e1849 waiting sin close_key.
Los snapshots8677–8679 conservan `Reward granted X`; el frame nativo posterior
confirma el mismo chrome, con X blanca en círculo gris. Primera divergencia
documentable: terminal físicamente acreditado no reconocido por el template
completo (`ad_reward_close` score.466544). No hay evidencia para fechar el inicio
exacto del terminal. e1851 20:23:59.144548 stall61.796 s; e1854
20:24:00.585906 AD_RECOVERY_FAILED63.25 s, close_steps0; Gold flow.failed e1869,
Session.failed e1870. El timeout no convierte falta de autoridad perceptiva en
permiso de Back ni en NO_WORK. FailureEvidence:
`artifacts/failure_evidence/failure_83b7cdde3ef04cabb6cc99fc51ce512a/`.

### Ajuste general posterior y entrega para inicio manual

La propuesta aislada `ads_light_patch/` con variantes de anuncios se descarta;
no se instaló. USER_GT exige independencia del creative. En su lugar, el mismo
owner compara las dos primitivas SDK ya adquiridas con máscaras que excluyen
el fondo. Conserva threshold.94 y exige círculo/posición/ownership. Para el
chrome Reward granted sólo lee su campo SDK fijo mediante el OCR compartido:
texto exacto confidence≥.85 más X circular; no lee contenido publicitario.
`Next ad` se publica como intermedio, sin cierre ni hitbox inventado. La
frescura se comprueba también después de OCR/Android (≤2 s). Sin edad mínima,
sin Back por timer, sin bajar thresholds globales ni añadir assets de creative.

Validación final afectada, una invocación: **196 passed/10.77 s** (Ads,
Stages/replays, navegación, Gold y wiring/composición). Casos5/8/12 s,
Reward granted real, chrome circular negro/blanco, ausencia de terminal,
X de contenido/no circular, Next intermedio, multipart temprano, progreso>60 s,
stall/absolute180 s sin cierre prematuro, ownership contradictorio y OCR lento.
Replay causal `ads_general_replay.json`:17 frames nativos,12 no terminales,
4 terminales circulares y1 Reward granted del rojo; todas las expectativas
verificadas usando el observer productivo. No se fuerza un anuncio nuevo live.

Último steering del usuario: inicia él la nueva sesión28 después de confirmar
este ajuste. No se inicia campaña8 autónomamente;28/28 sigue pendiente. La GUI
anterior debe cerrarse y abrirse de nuevo para cargar este runtime. No commit/push.

### Resultado manual posterior — aceptación principal cerrada

El usuario inició la nueva GUI final27ae46d4: session
`6c2c6ad1abff47ffb4648262e26368bb`, run
`e4d8ec7e6aaf403ca5f919685b22cd81`,20:48:32.979131→21:49:50.587134 -03.
28/28 scopes consecutivos,28 Rotation, Session COMPLETED,0 fallos técnicos,
61:17.608.25 personajes ads_exhausted;6 Ads/Sapphire verificados. No cambia
el resultado de ninguna campaña roja anterior. Código/assets iguales a la
preparación manual; diferencia local routines.json explicada sin inventar
hash de inicio de config.26 nombres registrados y2 UNKNOWN sin inferencia.

Cierre:1860 passed/4 skips históricos (349.23 s), INDEX portátil533 passed/
1 skip de corpus/3 deselected por capturas locales históricas (26.29 s).
Primer diagnóstico INDEX de esas3 capturas ausentes se conserva en informe.
Usuario autorizó único commit/push sobre656460c4;8 paths independientes excluidos.
Scope, tabla28, hashes, historia roja, límites Ads y deuda vigente en
[FULL_ROSTER_CHECKPOINT](FULL_ROSTER_CHECKPOINT.md).
