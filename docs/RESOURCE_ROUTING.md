# Resource routing — contrato actual

`IMPLEMENTATION_CONTRACT`. Fuente única de policy/composición de recursos y sus límites productivos. UI física/caller/Back: [GAMEPLAY_GT](GAMEPLAY_GT.md); estado caliente: [CONTEXT](../CONTEXT.md). La [reconstrucción](POST_V1_RESOURCE_ROUTING_RECONSTRUCTION.md) es procedencia histórica, no plan de ejecución.

## Ownership y policy aceptada

**USER_GT / product policy:** el propósito productivo de MW es gastar Sapphires mediante SKIP para obtener rewards. Todo lo descrito aquí —board/planner/J y reliefs— son fallbacks ante presión/capacidad para restaurar MW y reintentar la intención productiva; no son el objetivo del flow ni flows de limpieza standalone. Un futuro flow cuyo propósito sea limpiar recursos deberá declararse explícitamente como tal.

- Board reader/snapshot describen cinco balances/límites por identidad: Brawler's Badges, Weapon Material, Hero Weapon Material, Bronze y Silver Keys. Consenso fresco después de la barrera del caller. El rojo local puede probar presión sin OCR cuando no hace falta aritmética; ausencia/inconclusión conserva OCR, y Weapon exacto se conserva si hace falta proyectar Hero. No predicen rewards ni capacidad Gold.
- `plan_resource_route` es puro: snapshot + facts externos explícitos → pasos simbólicos. Entrada inclusiva Bronze ≥400, Silver ≥450, Weapon ≥800, Hero ≥800; presión dura probada también participa. La conversión determinista 40→10 puede justificar Craft alrededor de Materials. Receta/capacidad Equipment son facts de ejecución, no prerrequisitos ocultos del planner.
- Umbral decide visitar, no cuánto drenar. Craft drena Hero hasta <49, Materials Weapon hasta <40 y Keys hasta NO_MORE_PROMOTIONS, con facts frescos y budgets. Materials paga Keys primero aunque no cruce umbral; Keys solo no paga General. Sin viaje justificado, no se abre Trading para diagnosticar Gold; Gold-full oculto por sí solo no bloquea MW.
- Executor J consume el plan una vez por pasada/request. Cada capacidad conserva sus guards/efectos: Craft receta/moneda/cantidad/decremento, Trading panel/row y efecto, Treasure Gold antes de cada apertura y stop antes de Karats. No hay contabilidad simulada, replan ni compras premium implícitas. No reutilizar snapshot/plan entre pasadas del farming loop: cada nueva pasada obtiene y evalúa su propio board fresco porque rewards de una pasada pueden crear presión para la siguiente.
- Keys es por fases. Si toda Bronze pendiente cabe en Silver (capacidad 499), Bronze* → Silver final*. Si no, Silver pre-drain EXACT1 mínimo → Bronze* → Silver final*. Una vez en Bronze, mantener intención mientras el siguiente MAX batch cabe; sólo presión real permite otra liberación Silver. Fresh facts no resetean fase. Budget, C4 y confirm único no cambian; OUTPUT_FULL conserva pending exacto y fase a través de Gold drain/retry único. Segundo OUTPUT_FULL falla cerrado.
- Craft con Materials: `MW → Craft → Quick Menu → Trading → X → Craft → Back → MW`, con Craft antes/después según plan. Craft+Keys sin Materials restaura MW antes de Trading. Gold-full diferido espera restaurar MW y usa `MW → Quick Menu → Treasure → Back → MW → Quick Menu → Trading` para reintentar una sola vez la misma operación pendiente. La entrada conserva el caller directo. Si la rama Craft consultó Inventory, su segundo Back termina normalmente en Lobby y se continúa por `Lobby → Battle Mode Select → MW` con reenter, sin reprepare ni repetir consumos.
- Capacidad Equipment se consulta dentro de Craft sólo si la rama tiene material para producir equipos; no existe preflight Inventory desde MW. `Craft → Quick Menu → Inventory → lectura fresca → Back → Craft → Back → Lobby` tiene Lobby como salida normal conocida. Cero slots prueba la necesidad de espacio: se abre Hero Craft sin confirmación, se exige el popup Equipment Full fresco y se toma Combine directo desde él. Combine vuelve a Craft mediante su reader local; si sigue Full se aplica el contrato Equipment siguiente y se reintenta sólo ese CraftStep dentro del mismo J, sin board nuevo ni replan.
- Equipment Full siempre: **Combine → fresh Item Count/capacity → Sell tail-first → Karats +4 slots → reevaluación**. Combine tiene prioridad; no vender antes equipos que aún podría resolver. Este USER_GT autoriza explícitamente expansión Equipment con Karats; las prohibiciones antiguas quedan LEGACY_STALE y Treasure conserva su stop antes de Karats.
- Si HAVE < NEED tras cualquier check, terminar inmediatamente. Mientras siga Full, calcular tail accesible fresco y escanear hacia atrás: primer candidato permitido → Bulk único con guards de panel/popup; cualquier Ethereal+ antes de candidato → detener scan. Sin candidato accesible, calcular matemáticamente la siguiente fila comprable y comprar exactamente +4, confirmar una vez y verificar `capacity_new == capacity_old + 4` con Item Count/capacity fresco antes de reiniciar Sell.
- **Tras Bulk verificado: invalidar evidencia visual, conservar sólo rangos lógicos protegidos compatibles con eliminación contigua y orden relativo preservado.** Delta fresco transforma índices y define región nueva expuesta; ir directamente al siguiente índice no inspeccionado. HAVE<NEED termina inmediatamente. Delta/modelo contradictorio descarta el modelo y usa scan secuencial seguro. Expansión +4, Combine y contexto con posible resort invalidan todo estado; fresh capacity/tail. Nunca varias filas preventivas.
- El caller conserva entrada directa Craft sin Inventory preflight. Consultar Inventory sólo en una necesidad real; `Craft → Inventory → Back → Craft → Back → Lobby` es salida normal determinística. Desde Lobby, navegación normal restaura MW y continúa el mismo pass. Socket conserva sus guards propios.

## Estado implementado frente a wiring productivo

Estado reconciliado para el checkpoint MW del 2026-10-02 en `rebuild/stable-baseline`; implementación vigente y evidencia final descritas en CONTEXT. Etapa de estabilización cerrada.

| Parte | Estado real y límite |
| --- | --- |
| Board / planner / J / runner standalone K | Componentes existentes. K ofrece acquire/plan/prerequisites/full-one-shot; su composición inyectada no prueba callbacks productivos completos |
| L1 productivo | Builder conecta ProductiveMonsterWaveFlow, A1, planner y J. PreparaciÃ³n Ãºnica y loop de Sapphire pressure `max(0, ceil((Sapphires-101)/100))` implementados: cada pasada adquiere su propio board y plan; dentro de su relief no repite board/planner/J. YES sin presiÃ³n, NO con presiÃ³n, resume del mismo pass y accounting sólo después de CLEAR y consenso fresco Sapphire. Loop de pressure validado offline; smokes históricos previos conservados bajo su policy original. Un fallo de construcciÃ³n todavÃ­a puede caer al flow bare; los smokes comprueban el tipo productivo real |
| Plan no ejecutable | NO_PREREQUISITES permite SKIP por YES; INSUFFICIENT_OBSERVABILITY y CONTRADICTORY fallan cerrado. K acquire/plan-only conserva el popup para su caller |
| L2 productivo | Equipment y Socket responden al blocker físico del mismo pass. Equipment hace Combine primero y después fresh Item Count mediante el plan de policy del inventory owner. Si queda Full, Sell Bulk tail-first y expansión secuencial verificada; Socket conserva su relief propio. Caller Equipment probado live: Combine-first, cinco Bulk tail-first 162/128→127/128, retorno al mismo pass y CLEAR |
| Craft local | Handoff Quick Menu usa source/snapshot verificado; reader agrega diagnóstico y umbral local Weapon cost 0.80. P0 Craft corregido y validado localmente; ya no es la primera divergencia |
| CraftStep full | Entrada directa por handoff; Inventory sólo por necesidad real de capacidad. Full abre Combine directo; retorno local a Craft y fresh Item Count antes de Sell. Plan EquipmentSellPolicy conectado al mismo CraftStep. Inventory consultado implica segundo Back a Lobby como salida normal. Live Combine `135/128→124/128`, Craft `318→24`, Lobby esperado; caller Sell validado live en MW: Full → Combine → count 162/128 → cinco Bulk → 127/128 → retorno al mismo pass y CLEAR |
| Keys productivo | Promoción normal verificada live en varias pasadas. Scope conserva dependencias del resolver, caller MW y tabs/rows; excluye readers ajenos. Identidades de las dos filas mediante templates frescos; sólo los pares causales usan OCR (2 llamadas/sample, 2 samples concordantes, máximo 3 ante un transitorio). C4 conserva panel/cantidad/cost kind/MAX post-dispatch/confirm único/efecto. Después del confirm, ni Item Trade persistente ni filas transitorias con el saldo previo cierran la espera: requiere decremento fresco o boundary reconocido, preservando el mismo consenso del efecto sin OCR duplicado. El siguiente paso reutiliza únicamente el consenso exacto que probó SUCCESS si sigue fresco (0..2 s), o readquiere después de su barrera. J cierra por X, reclasifica fresco y verifica MW; L1 reanuda directamente el mismo pass con `resume_after_relief=True`, cero Back/re-entry. Sólo un Lobby físicamente confirmado permite el recovery bounded existente; UNKNOWN/AMBIGUOUS no autoriza Back preventivo |
| Gold relief productivo | ACK y drain conectados a los owners existentes. ACK exige alert Gold-full fresco y dos filas Keys completas después del dispatch; probado live. Treasure usa scope con todas las dependencias del resolver + detector Gold/Karats también en la primera apertura. OPEN_ONCE y drain verificados live: 499 Gold agotados, límite Karats y un dismiss final; cinco promociones causales posteriores completadas. Conserva latch premium, finalizer y retry causal único |
| Materials productivo | Weapon→Hero conectado y verificado live: `852→52→12`, C3 fresco concordante y C4 verificado con una confirmación por intent. General incluye ofertas temporales fuera del catálogo histórico: búsqueda visual del título adquirido, sin índice inferido ni OCR de ofertas ajenas. Máximo 12 swipes conocidos, lane `.33`, delta del profile, settle post-dispatch y una inversión ante no progreso; fila completa y posición concordante antes de retornar READY. Target parcial/ausente/agotar bound falla cerrado. No implementa otros materiales |
| Sell | USER_GT definitivo implementado: nueve tipos Ethereal + Enhance configurables en GUI; E+ protegido; Bulk único por intent; count fresco, transformación lógica compatible tras Bulk e invalidación completa tras expansión. Adapter live Inventory `131/128→128/128→127/128` mediante dos Bulk verificadas (equipment y enhance), reevaluando el nuevo tail. Expansión: fila +4/popup/coste adquiridos nativamente, compra positiva aún no ejercitada live porque Bulk resolvió Full. Boots/Gloves/Pants/Chest/Helmet Ethereal y reinicios tail verificadas live: `172→167→162→157→146→135→129→128→123`, ocho Bulk y cero compras; Legendary/Epic/Rare/Ethereal tienen guards visuales nativos; Poor/Normal pendientes de adquisición si aparecen |

Referencias de implementación: [flow_registry](../bot/flow_registry.py), [ProductiveMonsterWaveFlow](../bot/monster_wave_productive.py), [J/navigation](../bot/monster_wave_resource_route.py), [K](../bot/monster_wave_standalone.py), [planner](../bot/resource_route_planner.py), [Craft reader](../bot/craft_reader.py). Los tests de [MW productivo](../tests/test_monster_wave_productive.py) y [ruta](../tests/test_monster_wave_resource_route.py) describen composición con dobles; no convertirlos en prueba de integración física/callback real.

## Sell acceleration — implementada

[Protected-block scan acceleration](../ROADMAP.md#protected-block-scan-acceleration) implementado en el Sell owner global: dos crops alrededor del panel fuerte protegido, NCC BGR con margen 2 px y threshold .90; sólo discovery. Sin perfil/crop/matching concluyente usa scan secuencial. Panel/policy/popup siguen autorizando cada Bulk. Rangos lógicos sobreviven sólo al Bulk compatible; expansión/contexto distinto invalidan. Combine-first, Ethereal+ y prefix accesible no cambian.

## Checkpoint aceptado y límites

MW estable para esta versión; loop autónomo live terminado. Camino productivo estabilizado live: smokes completos sin instrumentación `214/214` y `253/253`, tres CLEAR cada uno y Lobby, sin flow.failed. Caller Equipment ejercitado en 4 CLEAR `396/396` tras cinco Bulk; su salida final Lobby fue el último fallo y quedó corregida/validada nativamente sin repetir consumos. Gold Full post-confirm, ACK/drain y retry causal único validados live. Validación proporcional final registrada en CONTEXT. USER_GT de Sell ya está cerrado y autoriza explícitamente Karats para Equipment; no existe un bloqueo pendiente por falta de autorización. MW productivo omite con precheck fresco de Sapphires <102, independientemente del badge Daily. Fill All con Gold insuficiente no bloquea esta integración.

## Evidencia live adquirida 2026-10-01/02

Smoke `20261001T195406.677299Z_mw_stabilization_43eaf70d`: 2 CLEAR, 5 trades Keys verificados y `138/138` Sapphires. Smoke `20261001T202142.178012Z_mw_stabilization_84b71faf`: 2 CLEAR, Materials `852→52→12`, Craft y Socket relief, retorno al mismo pass y `138/138`. Estos smokes no prueban Gold-full ni el caller nuevo de Sell; la tabla registra su validación posterior. Capturas nativas/failure evidence quedan locales, fuera de assets runtime y sin versionar.

Validación final 2026-10-02: `mw_final_native_d1e5d83e` COMPLETED, tres CLEAR y 253/253, Lobby, sin flow.failed. `mw_exit_inventory_native_3bf4119d` prueba la rama Inventory → MW → Lobby → hub sin consumos; conserva la salida contractual de la activity. Equipment expansión +4 positiva y Poor/Normal visuales siguen pendientes de adquisición cuando sean necesarios, sin alterar el fail-closed ni comprar preventivamente.


Deuda posterior no bloqueante: expansión +4 positiva live (mecánica adquirida/tests verdes, no compra innecesaria), Poor/Normal visual positivo y Ethereal Enhance positivo (sin evidencia suficiente, fail-closed), lifecycle SKIP tras pausas largas, portabilidad/publicación del corpus local y Fill All con Gold insuficiente UNKNOWN. No adquirir ni implementar estas ramas durante el cierre. No repetir smokes aceptados.

## Stages Daily — caller productivo cerrado 2026-10-02

```text
Stages → generar Sapphires → Monster Wave → consumir Sapphires / obtener recursos
```

Flow Registry/CLI/GUI componen Stages Daily ads-only, navegación/configuración/Mao concretos, compra Stamina, same-character reentry y AdsManager transversal. Gate fresco Lobby: Stamina ≥300 y Sapphires <102. Saldo Sapphire alto delega a MW existente y reevalúa después; no duplica MW. Stamina faltante compra la oferta Currency/Stamina con K Coins (disponibles por USER_GT), un único batch de `ceil(max(0,300-HAVE)/50)` trades desde HAVE fresco: abrir oferta una vez, seleccionar mediante `>`, verificar cantidad/cap, confirmar una vez y exigir Stamina fresca≥300; sin OCR K Coins ni Trading genérico. Cap insuficiente o efecto inconcluso detiene sin segundo consumo. Baseline Sapphire se readquiere tras prerequisites.

Un ad exitoso por ejecución. Sólo Normal/Abyssal Rion/Stage8: CV fresco confirma episodio antes de World Map; si ya es Abyssal Rion, Stage8 directo. De otro modo, selección tail/cierre y verificación fresca bounded. Mao ACTIVE, Penance,300 MAX; no x4/manual. Success requiere Results y Sapphire after > before, luego Lobby limpio. Equipment/Socket Full delegan a reliefs globales con layering superior; no policy privada. Adapter Inventory Lobby conserva su geometría adquirida distinta del menú desplazado Craft; portal handoff sólo desde entrada verificada al relief conocido.

No Ads temporal: tres lanzamientos iniciales con dos retries separados 5 s; si persiste, Character Select→MISMO personaje→un último lanzamiento. Identidad verificada antes de confirmar y al volver a Lobby; no Rotation. Si persiste, ADS_UNAVAILABLE/MANUAL_RESOLUTION y business incomplete autorizado en Gold Farming→MW final→Rotation. No entrada manual ni combate fallback. Video0/alert diario explícito→ads_exhausted. Abort recuperado no presupone reward/debit: restaurar Lobby y como máximo un retry con balances/count frescos compatibles; manual no autorizado detiene. Sin recuperación segura→AD_RECOVERY_FAILED. Lifecycle/progreso/cierre del AdsManager pertenece a ARCHITECTURE.

El alert Loading/Select Character de No Ads está adquirido como template CV nativo/stream con prioridad de modal. El texto literal No Ads Available conserva fallback provisional exacto sobre el cuerpo de alert Stages conocido, sólo bajo main activity/focus concordantes y nunca sobre contenido del ad. OK compartido requiere chrome Stages: no atribuye modals ajenos. Retry/reset policy y same-character isolation cubiertos por tests; cadena completa post-fix no forzada live.

Smoke aceptado `stages_progress_smoke` / `f1c24b514e4e40128d5875a7c1ed74f4`: COMPLETED, Sapphires5→479, Stamina440→140, Lobby sin flow.failed. Etapa funcional/cerrada, no repetir smokes ni ampliar ramas durante el checkpoint. Deuda futura en ROADMAP.


## Basic Gold Farming — estrategia seleccionada, no planner

USER_GT actualizado durante validación live de Configurable Routines v1:
`Basic Gold Farming` selecciona `Gold Farming Cycle` (`gold_farming`), una capability
Lobby→Lobby con hasta dos oportunidades de Stages Ads y una inversión MW después de
cada oportunidad. La inversión de la última oportunidad es final; si Stages confirma
agotamiento diario en la primera, se omite la segunda oportunidad y se conserva MW final.
No programa actividades ajenas, no cambia el orden de rutinas custom ni controla Rotation.

Decisión con el wiring actual: A (cuatro steps literales) sigue disponible como custom,
pero no expresa la estrategia económica ni el fin anticipado. B exigiría introducir
intents/resource policy en RoutineRunner/Session, hoy owners de secuencia/Eligibility/Rotation.
C reutiliza Registry, StagesDailyFlow y ProductiveMonsterWaveFlow y encapsula sólo el
dominio que requiere coordinación. D (caches/saltos de índices en runner) acoplaría
secuencia genérica a policy económica. Se elige C, sin graph/workflow engine.

Stages conserva el owner de readiness causal (`Sapphires>=102 → MW → lectura fresca`):
también es necesario para Stages standalone y no decide qué farmear. Gold Farming posee
cantidad de oportunidades e inversión posterior/final. El mismo MW binding se reutiliza
secuencialmente y sus prepares/boards/bounds siguen siendo por invocación/pasada.
La observación explícita `Video 0`/alert diario vive como fact de disponibilidad de Stages
en un scope por personaje de Session, compartido entre occurrences. Same-character recovery
no crea un nuevo scope. Rotation separa los scopes; no hay balance económico simulado.
UNAVAILABLE/ABORT/timeout/UNKNOWN/failure nunca crean ese fact. Otra occurrence Stages
con agotamiento conocido devuelve no-work antes de recursos/navegación; la secuencia custom
mantiene sus llamadas literales. La capability registra la oportunidad restante omitida.

MW standalone y preparado tienen readiness fresco en Lobby antes de Select Battle Mode.
Sólo consenso confirmado de saldo <102 devuelve COMPLETED + `monster_wave.no_work` sin entrada.
Saldo en pressure no se almacena: prepare vuelve a verificar fresco en el hub. Failure/UNKNOWN
detiene sin navegación. PreparedActivity distingue este `entry_readiness` terminal del
precheck de Eligibility pendiente de World Boss; no se combinan y no se cambia Daily policy.
Si el hub ya está abierto por una actividad adyacente, MW verifica allí sin reentrarlo.

Reporting conserva events reales de children y status/decision de cada actividad; correlación
`attempt_index/activity_id/activity_role` distingue requested, prerequisite, investment y
final_investment dentro de routine/character/occurrence. Ads unavailable autorizado puede
continuar dentro del ciclo con resultado MANUAL_RESOLUTION registrado y business incompleteness;
FAILED/CANCELLED/manual no declarado corta sin inversión ni Rotation. Stages devuelve Lobby fresco; después de MW la capability solicita su propio retorno
Lobby mediante Navigation, sin imponer esa salida al gameplay owner MW. Overrides MW/equipment de cada occurrence se clonan y aplican
al MW prerequisite/inversiones de esa capability, sin mutar otra occurrence.

Persistencia schema v1: sólo el preset original intacto (`basic-gold`, nombre original,
cuatro steps enabled/default config/default continuation) migra a la capability. Rutinas
editadas y custom permanecen intactas. La GUI guarda/reabre el mismo ID seleccionado.
Arena/ToT podrían tener capabilities propias si su dominio lo requiere; no se implementan.

### Handoff del panel SELLABLE — USER_GT 2026-10-02

El scanner mantiene abierto el mismo panel cuando el consenso fuerte fresco de nombre/tier/type y guards visuales cumple la policy. El handoff local conserva candidate, Inventory previo inmutable y panel/evidence de ese tap; Bulk usa ese panel directamente, sin close/reopen ni otro consenso equivalente. Cualquier input intermedio, cambio de candidate, pérdida de freshness o discontinuidad del título/grade/Sell invalida el handoff sin consumo. Esa continuidad visual sólo invalida: CV nunca autoriza Sell. PROTECTED/inconcluso cierra y conserva el scan vigente.

El popup Bulk, policy Ethereal/Ethereal+, confirmación única y fresh Item Count/delta permanecen en el owner consumptivo existente. Un `before` anterior al panel sólo se acepta con `reuse_selected_panel`, el mismo strong item observado por el scan y secuencias monotónicas; las transformaciones lógicas tras Bulk no cambian. Telemetría: protected/sellable panel opens, same-item reopens, Bulks y elapsed.

Live Sell selected-panel continuity: exact pixel equality was invalidated by H264/background noise on an unchanged strong Boots panel (name NCC 0.999999, grade/type 0.996757; protected Ethereal+ negatives 0.4928/0.6877). Fresh same-candidate/input-lineage guards remain; conservative ROI correlation only rejects continuity and never authorizes sale. Strong classification/policy and the fresh Bulk popup retain destructive ownership. Zero-confirm denials report bulk_not_started plus their real reason rather than effect_inconclusive.


Live Craft count (2026-10-03): Hero Weapon ROI excludes the animated icon at the left of the count. The routine investment physically verified 800−10×49=310/999, while the old crop yielded 1310/999 and correctly failed closed. Native/stream replay reads 310/999 after cropping; confidence and parse_pair bounds remain unchanged. An inconclusive effect still never authorizes a second confirmation.

Live Craft result (2026-10-03): the old name ROI included the item graphic and rejected Laoku’s Destructive Phantom Sword at confidence .55 despite the known black-lateral/fullscreen result. A text-line crop reads the same result at .9985 without changing darkness/context/name confidence guards. The existing 13-frame cross-kind evaluator remains green; verified cleanup closed that same result and freshly read 867→377 without repeating confirmation.

Live Materials effect (2026-10-03): after MAX Weapon→Hero 840→40, glyph segmentation excluded the disconnected left stroke of the first 4. Native and stream replay proved narrow 10/40 versus widened 40/40. Only the initial left glyph margin grows .004→.008; both independent perturbation reads must still agree. Row identity/C4/one-confirm/post-effect guards remain, and the existing Materials/Keys corpus passes. No blind trade retry follows unreadable effect.


Live Stamina final selection (2026-10-03): a frame captured 31 ms after the final
`>` dispatch still showed 4/20, then the same panel reached 5/20 without another
input. As in productive C4 post-MAX, the final verification waits bounded for the
requested quantity. There is no perception between setup taps, no setup retry,
and no confirmation from an intermediate/mismatched/inconclusive selection.

Resolved MW blockers retain their original `manual_resolution` event. Only a
confirmed CLEAR after the productive relief adds `monster_wave.relief_resolved`
with the same boundary ID. Reporting projects that exact intermediate boundary
as resolved; another unresolved manual result and all FAILED/CANCELLED outcomes
remain terminal/incomplete. Timestamp alone is not an identity (Windows clock
granularity can give separate events identical created_at values).


Live Craft partial MAX (2026-10-03): first Craft663→173 completed with one confirm and fresh effect; the next selector physically3/10 failed before consumption because the broad quantity crop yielded confidence .808. Text-only quantity ROI (.438,.735,.495,.783) reads native .99808 and stream .99928 with threshold .85 unchanged. Recipe identity/currency/cost/cap/MAX/post-effect guards remain. Native/stream replay, existing13-frame cross-kind evaluator and243 directed tests pass; live cleanup verified3/10 and cancelled without confirming.

### Trading Item Trade: pair crop 867/40 (live 2026-10-03)

El run cbb2ac64 completó Shadow Mage y Blood Demon (éste con dos ads), pero
falló en el tercer personaje antes de MAX/confirm de Materials. Item Trade estaba
abierto: OCR de la ROI amplia devolvía `(867740)` en vez de `(867/40)`. El parser
fail-closed lo rechazó; no hubo trade. La ROI input_pair conserva ancho .54–.65
y ajusta sólo vertical .343–.38. Native/stream dan .99924/.99926; parser, threshold
.85, identity/cost/quantity/C4 no cambian. Replays Keys/Materials y composición:
255 tests verdes; selección cancelada, Craft parent fresco y Lobby verificado.
Nueva campaña GUI42a5d0f6 desde ese personaje para tres consecutivos.

### Stages post-ad: stale matching stream surface (2026-10-03)

Run1f0f4912 completó Galaxy Lord con dos ads/una Rotation. El siguiente personaje
recuperó un ad abortado (no exhaustion). Close Auto produjo Config correctamente,
pero el frame de stream matching llegó con edad fuera de la guard2s y la espera
terminó FAILED. StagesNavigation.wait conserva guard/failure/cancellation; sólo
si el último snapshot del timeout coincide semánticamente y está stale, adquiere
un snapshot nativo real y hace una verificación adicional bounded2s. Cero retries
de input, ningún timestamp relabelled, ningún consumo repetido. Si native fresco
no coincide, sigue FAILED.229 tests verdes. Evidencia original/local conservada.

### Follow-up: Materials crop is identity-specific, Keys unchanged

Run87de8e91 hizo ambos Stages productivos pero MW final falló antes de confirm
en Bronze MAX: el crop vertical compartido leyó `(240/200)_`. La calibración de
Materials no generaliza al fondo de Keys. Sólo input/output identity fuerte
hero_weapon_crafting_material selecciona el crop Material .54,.343,.65,.38;
Keys conserva .54,.34,.65,.385 (native240/200 .99920). El campo diagnóstico
input_pair y el parser estricto quedan iguales. Replays reales native/stream
para ambas identidades +341 tests verdes; MAX cancelado sin consumo, Lobby
verificado. Nuevo smoke GUI4be589fc desde personaje actual para tres consecutivos.

### Actualización recovery Ads 2026-10-03

Supersede el límite anterior de dos intentos post-reset: son **3 lanzamientos iniciales** (dos retries con espera de 5 s) y **1 lanzamiento final tras same-character reentry**. Sólo indisponibilidad explícita permite esta cadena; UNKNOWN/timeout/abort no equivalen a agotamiento. Stages conserva MANUAL_RESOLUTION `stages_daily.ads_unavailable` al terminar la cadena. Gold Farming, si la policy autoriza continuar, etiqueta business incompleteness, conserva inversión final MW, omite otra oportunidad de Stages por `ads_recovery_exhausted` y deja Rotation a Session. No escribe el hecho diario `stage_ads_exhausted`; rutinas custom mantienen su orden literal.

El replay rojo native/stream reconocía Auto (.999687–1.0) antes del alert OK (.981004–1.0), filtrando autoridad de la capa inferior. Ahora el cuerpo fijo adquirido del alert Loading/Select Character identifica `no_ads` con threshold .94, sin OCR ni bajada de threshold; alert OK desconocido precede Auto y bloquea inputs al parent. Android main activity/focus concordantes siguen siendo necesarios para el outcome UNAVAILABLE. Un alert que llega durante return grace conserva su identidad en lugar de convertirse en AD_ABORTED_RECOVERED.

### Histórico: MW standalone terminal Lobby (2026-10-03; supersedido por handoff)

La reproducción4628c0db repitió el timeout42a5d0f6: CLEAR e inversión ya verificados; `ExitMonsterWave` llegó a Lobby limpio, pero Activity normalizaba a hub (`exit_lobby_to_hub`) para después volver a Lobby por Zone. La reapertura no alcanzó hub y el run quedó FAILED sin Rotation. La causa de composición es exigir un destino intermedio innecesario para un caller standalone; no se atribuye a cierre externo del juego.

`MonsterWaveFlow.run` y el loop productivo standalone solicitan `return_to_lobby=True` sólo al finalizar. Si el exit fresco llega a Lobby, no reabre Battle Mode; `BattleModeZone.leave` reconoce Lobby limpio como su destino terminal sin inputs. Si llega a hub, la salida existente hub→Lobby permanece. PreparedActivity mantiene el default hub, su postcondition y zone sharing; no se generaliza la rutina ni se permite UNKNOWN/modal como Lobby. Failures de SKIP/CLEAR siguen deteniendo antes del cierre. Ningún trade/claim/confirm cambió.


### Socket animation handoff — live 2026-10-03

IMPLEMENTATION_CONTRACT / LIVE_EVIDENCE: run77d1ee48 stopped after its single
Gold Enhance dispatch, while fresh frames2147/2153 already carried the existing
strong animation-tappable observation. Socket's 250ms stability gate could miss
the alternating dark/bright phases and never hand off to TapThroughAnimation.
Only this post-confirm handoff now uses stable_for=0: first fresh positive frame
starts the existing bounded safe-side tap loop. Bright UNKNOWN frames wait without
input; unrelated known contexts stop. Enhance remains one consumptive dispatch;
its inconclusive effect never authorizes another confirmation. Normal entry,
modal and return transitions retain their stability requirement. Live replay
preserves positive dark phases, negative flash and clean native aftermath.

The No Ads modal fix exposed a separate replay regression: shared single-OK
chrome alone could assert a Stages base inside Socket No Material. Generic alert
classification now also requires underlying fixed Stages chrome (dimmed allowed
for identity only); acquired specific No Ads body remains sufficient. Thus an
upper modal still captures input, while its physical owner is preserved.


### MW relief return may expose an existing MW modal

LIVE_EVIDENCE 2026-10-03 runc6ceba8b: Keys Gold capacity recovery drained Treasure
successfully. Its Back returned physically to MW + New Ranking (resolved, landmark
confidence .9961), but leave_treasure demanded clean MW directly and timed out.
The return now reclassifies and accepts MW's existing Ranking/Weekly modal, uses
the owner's acquired acknowledgement action (max two, single dispatch each), and
requires fresh clean skip-state before reacquiring the anchor/continuing Trading.
No extra Back, Lobby or MW reentry; UNKNOWN cannot authorize acknowledgement.
Persistent modal, stale effect, cancellation and foreign contexts remain stops.


### Sapphire pressure y visita Craft — contrato vigente 2026-10-03

USER_GT / IMPLEMENTATION_CONTRACT: objetivo común para readiness de Stages e
inversiones intermedia/final de Gold Farming: aliviar/invertir Sapphire pressure
hasta saldo <102. `bot.sapphire_pressure.sapphire_pressure_passes` implementa
`max(0, ceil((balance-101)/100))`. Cero passes no navega. ProductiveMonsterWaveFlow
prepara una vez y, tras cada CLEAR, exige el consenso existente fresco del HUD MW
y recalcula; no supone un decremento de100. Un efecto inconcluso corta, no consume
otra entrada. Guards de CLEAR y relief no cambian. Los smokes históricos anteriores
registran la policy anterior; la recalibración presente se verifica offline.

CraftStep aprovecha el panel abierto para Weapons, Armor y Accessories Hero
elegibles, en ese orden; costo/material ya visibles permiten decidir sin abrir
tabs por precaución. Cada familia reutiliza selección fuerte, MAX/cantidad
verificada, una confirmación y decremento fresco. Categoría sin trabajo o lectura
inconclusa no bloquea las siguientes; failure real corta. Capacity probe considera
las tres familias y abre la receta de la familia elegible si debe probar Full.
Material/costo compartido no prueba que otro selector tenga cantidad o efecto:
esos guards siempre vuelven a verificarse. Faltan resultados productivos naturales
Armor/Accessories completos, documentados en ROADMAP; no se inventa GT.

Socket Enhance All/Gold: después del primer positivo de inicio, TapThroughAnimation
usa 0.2 s entre taps, cada uno precedido por pixels frescos y animación positiva
tappable. Scope local conserva Socket/upper layers y el detector original; bright
flash/UNKNOWN no autorizan tap. BASE debe persistir0.25 s y verificarse con el
observer completo. Timeout12 s/max20 conservados; cadence real suma captura y
percepción. Sin second confirm ni cambios de threshold.

Select Battle Mode tiene QM, pero hacia Lobby gana Back único por BattleModeZone
(segundo Back en MW→hub→Lobby). Lobby fresco no emite input. La salida MW/entry Rotation
vigentes están descritas en el handoff siguiente; no la normalización histórica de arriba.


### Handoff entre flows — contrato final 2026-10-04

Supersede el destino terminal standalone MW→Lobby de arriba. MW termina gameplay y entrega
MW limpio y evidencia final; Session/Navigation poseen el siguiente handoff, reutilizando
PreparedActivity y ComponentRequirement. Hub o Lobby fresco de no-work/ramas existentes son
postconditions válidas; no se fuerza una superficie intermedia. Contrato de rutas y NO_WORK
puro en ARCHITECTURE. Stages y Gold Farming solicitan explícitamente Lobby a Navigation después
de MW cuando reanudan operaciones que lo requieren. Pressure <102, budgets, reliefs, Ads,
trades y agotamiento conservan su policy. Rotation sigue fuera de Gold Farming y entra desde una BASE verificada con capability Quick Menu,
sin Lobby intermedio. Quests/Mailbox son destinos QM y restauran su origen fresco.
Battle Mode Select tiene QM; Back directo gana exclusivamente cuando el destino solicitado es Lobby.
Desde MW, Quick Menu→Lobby evita dos cambios BASE por Back→hub→Lobby; hacia otra actividad
Battle Mode sólo se solicita hub. Unknown/modal/failure/cancel nunca habilitan cleanup arbitrario.
