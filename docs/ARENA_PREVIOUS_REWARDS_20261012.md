# Arena Previous Season Rewards — adquisición focal 2026-10-12

Los apartados de adquisición conservan el estado histórico de esa campaña.
El contrato productivo incorporado posteriormente se describe al final.

## Autoridad y alcance

**USER_GT:** MODAL sobre Arena BASE, por personaje que participó en la temporada
anterior. Varios personajes pueden tenerlo pendiente; no aparece obligatoriamente
en cada visita ni para todos. No modelar disponibilidad global ni inferir presencia
desde participación. Otros personajes reservados para validación del manejo futuro.

**LIVE_EVIDENCE:** personaje visible `Drakenn26`, nivel70, bloque de ranking
Telumpel. Ruta Lobby → Battle → Select Mode con tarjeta Arena → Arena + MODAL.
Sólo inputs `ArenaControl.BATTLE` y `ArenaControl.ARENA`, una vez cada uno,
desde guards positivos y frescos mediante `tools.arena_b2_acquire`/ActionExecutor.
En la adquisición inicial no se ejecutó ArenaFlow, combates, compras, claim,
OK, Back ni cambio de personaje; el follow-up OK autorizado se documenta abajo.

## Evidencia preservada

Captura nativa `ADB exec-out screencap -p` preparada antes de cada input. PNG
originales completos2712×1220, sin recomprimir, en
`artifacts/arena_previous_rewards_20261012/{lobby_route_live,arena_entry}`.
`frames.jsonl` registra UTC, timestamp monotónico, secuencia local al lifetime,
shape y SHA256; `action.json` identifica guard/input y secuencia previa.
ADB inicialmente no pudo iniciar daemon dentro del sandbox: sin captura/input;
ejecución autorizada fuera del sandbox completó la adquisición.

Arena input23:10:11.420608Z (20:10:11 -03). Primer frame post-tap002 es Select Mode
con Loading (negativo relevante). Frames003/004 muestran el modal completo;
son dos observaciones pasivas del mismo evento, no dos participaciones.
No se intentó consumir/cerrar para obtener más muestras.

Raw→curado trazable en
`datasets/arena_previous_rewards_semantic_manifest.json`; copias nativas locales
en `screencaps/semantic/arena-previous-rewards/20261012`. La anotación del parent
físico Arena procede de ruta/título visible, no de forzar el resolver.
Crops nativos legibles del panel, resultados y controles y sus geometrías/hashes
en `artifacts/arena_previous_rewards_20261012/crops.json`.
Fixtures portables reducidas al50% con hashes/parent en
`tests/fixtures/arena_previous_rewards/manifest.json`.
Raw y corpus locales no se versionan; crops runtime pequeños y fixtures portables
siguen las convenciones existentes. Reproducción offline:
`./tools/agent_run.ps1 tools.curate_arena_previous_rewards`.

## Contenido y controles observados

| Zona | Texto visible |
| --- | --- |
| Anuncio | Arena 642 Season Arena has begun. |
| Resultados | Arena 641: Past Season Results |
| Ranking de clase | Telumpel Ranking : Rank 22 (44.00%) |
| Recompensa clase | Ranking Reward; 30 Karats |
| Ranking general | Overall Rank: Rank 819 (35.29%) |
| Recompensa general | Ranking Reward; 5 Accessory Material; 70 Karats |
| Footer | Ranking rewards will be sent to mailbox. |
| Control | Único botón rojo OK; sin X visible |

Panel oscuro central con borde dorado, emblema de dos cascos arriba, bloques
de clase/general separados por línea vertical; Arena subyacente oscurecida.
Hitbox visible candidata OK(.436,.777,.564,.866), centro(.500,.8215), normalizada
desde frame.shape. Inicialmente **HEURISTIC geométrica**; el follow-up autorizado
acreditó físicamente ese centro y el cierre a selección Arena. No se añadió acción
productiva ni manejo automático.

## Percepción e integración

Identidad `popup.arena_previous_rewards`, observación
`landmark.arena_previous_rewards`. `ArenaDetector`/`ArenaFlowVisuals` existentes,
catálogo vía `ARENA_MODAL_PAIRS` y `ARENA_OBSERVATIONS`, sin nuevo coordinator.
El manifest `datasets/arena_previous_rewards_assets_manifest.json` declara cuatro
ROIs de wording fijo Season Arena has begun/Past Season Results/footer/OK,
assets `assets/arena/previous_rewards/*.png`, threshold0.92 y shape de referencia.
CV con brillo acreditado; cero OCR para identidad. Clase, números de temporada,
ranking e importes excluidos. El texto compartido mailbox/OK por sí solo no basta.
Sin observación de BASE desde el MODAL; replay positivo devuelve overlay correcto
con BASE UNKNOWN, conservando separación física/semántica.

Default y scope focal Arena ya incluyen el detector. Sin flags de cuenta,
persistencia de elegibilidad, acciones nuevas ni cambio de routing Farming Cycle.

## Validación y límite residual

Evaluator focal `tools.arena_previous_rewards_evaluation`:73 frames,4 positivos
(2nativos+2replays reducidos),69negativos,0wrong,0OCR. Incluye entrada Loading,
Lobby/Select Mode, estados de Arena A/B1/B2, WB Previous Rewards y WM Weekly
Results confirmados. Cache incremental con fingerprints de los assets/manifests.
Tests propios verifican identidad/layering, geometría, procedencia y máscaras
sintéticas de campos variables; no afirman nuevas propiedades físicas.

Validación:13 tests focales PASS, incluidos wiring default/scope Arena y ausencia
de confusión WB/WM/batch.156 regresiones existentes de `test_arena_phase_a`,
`test_arena_b2_replay` y `test_arena_flow` PASS; sus señales anteriores no fueron
modificadas. Default legacy CV requiere regiones al tamaño nativo; la prueba de
wiring restaura dimensiones desde fixture reducida, sin cambiar infraestructura.
`git diff --check` PASS. Warning inicial de cache pytest sin permisos separado;
corrida focal final sin cache. No evaluator global ni suite completa por este ROI local.

**USER_GT adicional:** escudo League Match dinámico según ranking; nunca es asset
fijo de esta identidad. El guard de navegación existente usa texto Select Mode y
label Arena en su tarjeta; no depende del escudo League Match. El primer crop
generado desde el transitorio se corrigió al revisar todos los frames, antes del
resultado final; ahora ese frame es negativo y los cuatro assets pertenecen al modal.

**USER_GT posterior:** este modal no tiene función Claim; las recompensas aparecen
en Mailbox y su claim corresponde al flow Mailbox. OK es reconocimiento/cierre.
No se necesita una policy de claim de rewards dentro de ArenaFlow.

**LIVE_EVIDENCE posterior, cierre autorizado:** un único tap OK(.500,.8215),
desde detección visual positiva fresca y geometría nativa, produjo selección
limpia Arena BASE (Beginner/Intermediate/Expert). No hubo New Ranking en los
dos frames posteriores. Capturas nativas completas antes→acción→después en
`artifacts/arena_previous_rewards_20261012/ok_close`, metadata/hashes en
`frames.jsonl`, target y autorización en `action.json`, resultado en `result.json`.
Antes23:18:46.075480Z; después23:18:47.199728Z y settled23:18:48.928326Z
(20:18 -03). Sin inputs posteriores, Mailbox no abierto ni recompensas reclamadas.
Script local de adquisición preservado en `close_acquire.py`; no acción runtime nueva.
Validación incremental del corpus ampliado:16 tests focales PASS; evaluator79
frames,6positivos (3nativos+3replays reducidos),73negativos,0wrong,0OCR;
73pares reutilizados desde cache y sólo6nuevos evaluados. Sin cambio de detector,
se mantienen las156regresiones previas válidas.
Curador incorpora un positivo antes de OK y dos negativos Arena limpia; assets
del detector intactos. No se prueba reapertura ni ausencia de New Ranking en
otras visitas/personajes. El siguiente trabajo podrá manejar presencia visual
opcional en ArenaFlow y verificar selección fresca, sin cambiar Farming Cycle.

Estado físico al terminar adquisición inicial: mismo personaje, modal abierto sobre
Arena, recompensas preservadas. Estado final tras follow-up autorizado: Drakenn26
en selección limpia Arena BASE; OK reconocido, sin claim de Mailbox. Sin manejo
automático, commit ni push.
Captura nativa final pasiva23:15:17.497977Z (20:15:17 -03), guardada con hash en
`artifacts/arena_previous_rewards_20261012/final_state/native.jsonl`, confirma
que sigue abierto e intacto; sin inputs adicionales. Adquisición nativa no abrió
scrcpy/source/sockets/forwards; no quedaron procesos de captura propios activos.

## Contrato productivo — regularización 2026-10-14

**IMPLEMENTATION_CONTRACT:** `ArenaFlow._navigate` admite el modal opcional
después de entrar a Arena. Los cuatro landmarks fijos de su identidad, positivos
y frescos, autorizan un único `PREVIOUS_REWARDS_OK` en (.500,.8215), escalado
desde frame.shape. El owner exige selección Arena limpia y fresca después de OK
antes de elegir dificultad. Un cierre inconcluso agota la espera y termina en
MANUAL_RESOLUTION, sin repetir OK ni iniciar combate; una identidad desconocida
o parcial no autoriza reconocimiento. Los guards existentes de freshness,
secuencia, source lifetime y cancelación permanecen activos.

Sin modal se conserva la entrada habitual a selección/New Ranking. Single Battle
y Auto Repeat comparten esta navegación; Farming Cycle usa el mismo ArenaFlow.
OK sólo reconoce/cierra: no ejecuta claims, no entra a Mailbox ni altera recursos,
routing o elegibilidad. El combate posterior pertenece a la operación Arena
solicitada y conserva su preparación/Start verificados.

Runtime necesita conjuntamente semántica/catálogo, `ArenaDetector`,
`ArenaFlowVisuals`, manifest de assets y cuatro PNG. Tests portables están en
`test_arena_previous_rewards` y `test_arena_previous_rewards_flow`; el evaluator
focal reutiliza fixtures versionadas y el corpus nativo curado local declarado
por los manifests. Los raws/corpus locales son evidencia conservada, no assets
runtime ni requisitos para ejecutar los tests portables. No se realizó una nueva
adquisición ni se incorporaron los cambios independientes de estabilización.
