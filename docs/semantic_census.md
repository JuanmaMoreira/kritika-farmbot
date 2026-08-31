# Semantic census legacy — Fase 3H.2

Este artefacto preserva conocimiento de dominio; **no es configuración runtime** ni
autoriza promoción automática. La fuente auditada es `CONTEXTOS_DEFINIDOS` de
`bot/constants.py` en `b3b11e2`, contrastada con `legacy-pre-hybrid` (sin diferencias
en `constants.py`, `context.py`, `actions.py` o `flows.py`).

## Convenciones

- Tipo: `base`, `overlay`, `global-menu`, `subcontext`, `internal` o `unclear`.
- UI: `current` = vista/revisada en evidencia current-season; `legacy` = sólo código,
  asset o screencap histórico; `unknown` = no alcanza la evidencia disponible.
- Estado 0.2: `production`, `candidate`, `legacy-only` o `unresolved`.
- Necesidad: `BLACK_MARKET_FLOW`, `ROTATION`, `RECOVERY_COMMON`, `FUTURE` o `UNKNOWN`.
- Los nombres 0.2 de filas no productivas son propuestas de búsqueda, no contratos.

## Inventario estructural

- 75 entradas top-level legacy auditadas.
- 18 declaran Quick Menu disponible, con tipos de offset `lobby` o `default`.
- 30 contienen grupos de subcontexto y 3 contienen menús locales detectables.
- Ningún botón legacy tiene `outcomes` configurados: las conexiones son sólo intención
  deducible por nombres, no un grafo ejecutable.
- Faltan los cuatro assets TOT principales (`tot` y sus tres estados auto-repeat).
- Muchas entradas top-level son diálogos o microestados de otra pantalla; no deben
  convertirse mecánicamente en contextos base 0.2.

## Census de las 75 entradas

| # | Legacy | Posible nombre 0.2 | Tipo | Asset legacy | UI / estado 0.2 | Necesidad | Relaciones y ambigüedades |
|---:|---|---|---|---|---|---|---|
| 1 | `lobby` | `screen.lobby` | base | `lobby-id.png` | current / production | BLACK_MARKET_FLOW / ROTATION | Base confirmada; acceso directo a Black Market y disponibilidad separada de Quick Menu. |
| 2 | `select-character` | `screen.character_select` | base | `select-character-id.png` | current / production | ROTATION | Cambio de personaje; no pertenece a la lógica interna de `BlackMarketFlow`. |
| 3 | `stage_normal` | `screen.stage_select` | base | `stage-normal-id.png` | legacy / legacy-only | FUTURE | Contiene episodio `ep-14` y menú local `world-map`; Quick Menu disponible. |
| 4 | `stage-normal-selected` | `state.stage.selected` | internal | `stage-normal-selected-id.png` | legacy / legacy-only | FUTURE | Microestado de selección; variantes MAO support. |
| 5 | `stage-normal-selected-start` | `popup.stage_start` | overlay | `stage-normal-selected-start-id.png` | legacy / legacy-only | FUTURE | Diálogo de inicio sobre selección de stage. |
| 6 | `stage-normal-selected-start-auto` | `popup.stage_auto_config` | overlay | `stage-normal-selected-start-auto-id.png` | legacy / legacy-only | FUTURE | Configuración auto/max; typo legacy `auro-repeat`. |
| 7 | `stage-normal-selected-mao-support` | `popup.mao_support` | overlay | `stage-normal-selected-mao-support-id.png` | legacy / legacy-only | FUTURE | Diálogo/support state, no base. |
| 8 | `stage-normal-skip-completed` | `popup.stage_skip_completed` | overlay | `stage-normal-skip-completed-id.png` | legacy / legacy-only | FUTURE | Resultado transitorio con `ok`. |
| 9 | `stage-normal-daily-dungeon` | `state.daily_dungeon.selected` | internal | `stage-normal-daily-dungeon-id.png` | legacy / legacy-only | FUTURE | Variante de selección con dificultad `penance`. |
| 10 | `stage-elite-chaos` | `screen.elite_chaos` | base | `stage-elite-chaos-id.png` | legacy / legacy-only | FUTURE | Quick Menu; estados de chest anidados. |
| 11 | `stage-elite-chaos-selected` | `state.elite_chaos.selected` | internal | `stage-elite-chaos-selected-id.png` | legacy / legacy-only | FUTURE | Selección/dificultad y MAO support. |
| 12 | `stage-elite-chaos-selected-start` | `popup.elite_chaos_start` | overlay | `stage-elite-chaos-selected-start-id.png` | legacy / legacy-only | FUTURE | Diálogo de inicio/auto-repeat. |
| 13 | `stage-elite-chaos-in-progress` | `state.elite_chaos.in_progress` | internal | `stage-elite-chaos-in-progress-id.png` | legacy / legacy-only | FUTURE | Estado de batalla con toggles. |
| 14 | `stage-elite-chaos-battle-ended` | `state.elite_chaos.ended` | internal | `stage-elite-chaos-battle-ended-id.png` | legacy / legacy-only | FUTURE | Resultado que espera tap. |
| 15 | `stage-elite-chaos-auto-ended` | `popup.elite_chaos_auto_ended` | overlay | `stage-elite-chaos-auto-ended-id.png` | legacy / legacy-only | FUTURE | Fin de repetición. |
| 16 | `stage-elite-chaos-slot-full` | `popup.elite_slot_full` | overlay | `stage-elite-chaos-slot-full-id.png` | legacy / legacy-only | RECOVERY_COMMON | Bloqueo de inventario específico; relación exacta con `bag-full-alert` dudosa. |
| 17 | `stage-elite-chest-rush` | `popup.elite_chest_rush` | overlay | `stage-elite-chest-rush-id.png` | legacy / legacy-only | FUTURE | Confirmación por gold/karats. |
| 18 | `stage-paused` | `menu.pause` | overlay | `paused-id.png` | legacy / legacy-only | FUTURE | Menú de pausa, no pantalla base. |
| 19 | `buffs` | `screen.buffs` | base | `buffs-id.png` | legacy / legacy-only | FUTURE | Tabs astrologer/alchemist; apariencia actual no revisada. |
| 20 | `survival` | `screen.battle_mode_select` | base | `survival-id.png` | current / production | FUTURE | Landmark current-season promovido con evidencia World Boss; es el selector Survival, no el selector PvP observado por separado. |
| 21 | `monster-wave` | `screen.monster_wave` | base | `monster-wave-id.png` | legacy / legacy-only | FUTURE | Quick Menu; dificultad `penance`. |
| 22 | `monster-wave-results` | `screen.monster_wave_results` | internal | `monster-wave-results-id.png` | legacy / legacy-only | FUTURE | Resultado modal/full-screen; evidencia insuficiente para elegir overlay/base. |
| 23 | `monster-wave-skip-confirmation` | `popup.monster_wave_skip` | overlay | `monster-wave-skip-confirmation-id.png` | legacy / legacy-only | FUTURE | Incluye alertas de slots llenos como subcontextos. |
| 24 | `monster-wave-points-reward` | `popup.monster_wave_points_reward` | overlay | `monster-wave-points-reward-id.png` | legacy / legacy-only | FUTURE | Reward transitorio. |
| 25 | `monster-wave-skip-completed` | `popup.monster_wave_skip_completed` | overlay | `monster-wave-skip-completed-id.png` | legacy / legacy-only | FUTURE | Resultado transitorio. |
| 26 | `select-boss` | `overlay.world_boss_select_boss` | overlay | `select-boss-id.png` | current / production | FUTURE | Live confirmó que preserva la base atenuada y Close la restaura; el landmark productivo es current-season. |
| 27 | `world-boss` | `screen.world_boss` | base | `world-boss-id.png` | current / production | FUTURE | Base human-confirmed; Quick Menu abierto/cerrado live con restauración de la base. |
| 28 | `world-boss-auto-repeat` | `popup.world_boss_auto_repeat` | overlay | `world-boss-auto-repeat-id.png` | legacy / legacy-only | FUTURE | Configuración/estado auto-repeat. |
| 29 | `expedition` | `screen.expedition` | base | `expedition-id.png` | legacy / legacy-only | FUTURE | Quick Menu. |
| 30 | `black-market` | `screen.black_market` | base | `black-market-id.png` | current / production | BLACK_MARKET_FLOW | Detector current-season validado; slots legacy son targets, no contextos. |
| 31 | `black-market-purchase-confirmation` | `popup.purchase_confirmation` | overlay | `black-market-purchase-confirmation-id.png` | current / production | BLACK_MARKET_FLOW | Overlay genérico también observado sobre Guild Shop. |
| 32 | `season-pass` | `screen.season_pass` | base | `season-pass-id.png` | legacy / legacy-only | FUTURE | Quick Menu; tab race. |
| 33 | `season-pass-claim-all` | `popup.season_pass_claim_all` | overlay | `season-pass-claim-all-id.png` | legacy / legacy-only | FUTURE | Confirmación yes/no. |
| 34 | `time-rewards` | `screen.time_rewards` | unclear | `time-rewards-id.png` | legacy / unresolved | FUTURE | Close + reward slots; puede ser panel sobre Lobby. |
| 35 | `battle` | `screen.battle_select` | base | `battle-id.png` | legacy / legacy-only | FUTURE | Quick Menu; entrada a Arena y otros modos. |
| 36 | `arena` | `screen.arena` | base | `arena-id.png` | legacy / legacy-only | FUTURE | Quick Menu; el mismo asset se reutiliza en `arena-selected`. |
| 37 | `arena-selected` | `state.arena.selected` | internal | `arena-id.png` | legacy / legacy-only | FUTURE | No tiene señal base propia; selección representada por subcontexto. |
| 38 | `arena-selected-auto` | `popup.arena_auto_config` | overlay | `arena-selected-auto-id.png` | legacy / legacy-only | FUTURE | Configuración auto/upon-defeat. |
| 39 | `arena-battle-ended` | `state.arena.ended` | internal | `arena-battle-ended-id.png` | legacy / legacy-only | FUTURE | Resultado transitorio. |
| 40 | `arena-auto-repeat-defeated` | `popup.arena_auto_defeated` | overlay | `arena-auto-repeat-defeated-id.png` | legacy / legacy-only | FUTURE | Recovery de auto-repeat. |
| 41 | `arena-battle-in-progress` | `state.arena.in_progress` | internal | `arena-battle-in-progress-id.png` | legacy / legacy-only | FUTURE | Toggle auto-repeat. |
| 42 | `arena-tryouts-complete` | `popup.arena_tryouts_complete` | overlay | `arena-tryouts-complete-id.png` | legacy / legacy-only | FUTURE | Resultado `ok`. |
| 43 | `arena-points-reward` | `popup.arena_points_reward` | overlay | `arena-points-reward-id.png` | legacy / legacy-only | FUTURE | Reward `ok`. |
| 44 | `mailbox` | `screen.mailbox` | base | `mailbox-id.png` | legacy / legacy-only | FUTURE | Estado `no-mail`; no Quick Menu en esta definición. |
| 45 | `friends` | `screen.friends` | base | `friends-title-current.png` + `friends-all-button-current.png` | current / production | SEND_STAMINA_FUTURE | Shell y All promovidos con evidencia HIL; accept/delete siguen fuera de alcance. |
| 46 | `friends-delete` | `popup.friends_delete` | overlay | `friends-delete-id.png` | legacy / legacy-only | FUTURE | Confirmación yes/no. |
| 47 | `friends-pending-max-amount` | `popup.friends_pending_max` | overlay | `friends-pending-max-amount-id.png` | legacy / legacy-only | FUTURE | Límite alcanzado. |
| 48 | `friends-recommended-request-sent` | `popup.friend_request_sent` | overlay | `friends-recommended-request-sent-id.png` | legacy / legacy-only | FUTURE | Acknowledgement. |
| 49 | `quests` | `screen.quests` | unclear | `quests-id.png` | legacy / unresolved | FUTURE | Close + tab daily; puede ser panel sobre Lobby. |
| 50 | `bag-full-alert` | `popup.inventory_full` | overlay | `bag-full-alert-id.png` (legacy text), `landmarks/inventory-full-ok-button-current.png` (current) | current / production en Black Market | BLACK_MARKET_FLOW | El nombre legacy queda como historia fría; producción normaliza todas las variantes al mismo evento, sin clasificar inventory kind. |
| 51 | `tot` | `screen.tower_of_tribulations` | base | `tot-id.png` (missing) | unknown / unresolved | FUTURE | Quick Menu; asset principal ausente, intención preservada por flow legacy. |
| 52 | `tot-auto-repeat` | `popup.tot_auto_repeat` | overlay | `tot-auto-repeat-id.png` (missing) | unknown / unresolved | FUTURE | Configuración auto-repeat. |
| 53 | `tot-auto-repeat-defeated` | `popup.tot_defeated` | overlay | `tot-auto-repeat-defeated-id.png` (missing) | unknown / unresolved | FUTURE | Recovery. |
| 54 | `tot-auto-repeat-end` | `popup.tot_auto_end` | overlay | `tot-auto-repeat-end-id.png` (missing) | unknown / unresolved | FUTURE | Fin de repetición. |
| 55 | `socket` | `screen.socket` | base | `socket-id.png` | legacy / legacy-only | FUTURE | Quick Menu; tabs socket/equipment. |
| 56 | `socket-enhance-all` | `popup.socket_enhance_all` | overlay | `socket-enhance-all-id.png` | legacy / legacy-only | FUTURE | Confirmación de enhancement. |
| 57 | `socket-enhance-all-no-material` | `popup.socket_no_material` | overlay | `socket-enhance-all-no-material-id.png` | legacy / legacy-only | FUTURE | Bloqueo por material. |
| 58 | `socket-sell-opal` | `popup.socket_sell_opal` | overlay | `socket-sell-opal-id.png` | legacy / legacy-only | FUTURE | Venta/cantidad. |
| 59 | `trading-center` | `screen.trading_center` | base | `trading-center-id.png` | legacy / legacy-only | FUTURE | Presente como negativo del corpus; tabs general/avatar/currency. |
| 60 | `trading-center-max-gold-pouch` | `popup.max_gold_pouch` | overlay | `trading-center-max-gold-pouch-id.png` | legacy / legacy-only | FUTURE | Límite de pouch. |
| 61 | `trading-center-item-trade` | `popup.item_trade` | overlay | `trading-center-item-trade-id.png` | legacy / legacy-only | FUTURE | Presente como negativo del corpus; diálogo de cantidad/trade. |
| 62 | `trading-center-item-trade-exception` | `popup.item_trade_error` | overlay | `trading-center-item-trade-exception-id.png` | legacy / legacy-only | FUTURE | Error genérico. |
| 63 | `trading-center-insufficient-items` | `popup.insufficient_items` | overlay | `trading-center-insufficient-items-id.png` | legacy / legacy-only | FUTURE | Falta de items. |
| 64 | `craft` | `screen.craft` | base | `craft-id.png` | legacy / legacy-only | FUTURE | Quick Menu. |
| 65 | `craft-amount` | `popup.craft_amount` | overlay | `craft-amount-id.png` | legacy / legacy-only | FUTURE | Cantidad/slots; no base. |
| 66 | `craft-amount-exception` | `popup.craft_error` | overlay | `craft-amount-exception-id.png` | legacy / legacy-only | FUTURE | Error `ok`. |
| 67 | `meteorites` | `screen.meteorites` | base | `meteorites-id.png` | legacy / legacy-only | FUTURE | Quick Menu; state slot/flare y menú local `current-meteorite`. |
| 68 | `combine` | `screen.combine` | base | `combine-id.png` | legacy / legacy-only | FUTURE | Quick Menu; tabs fuse/transmute. |
| 69 | `combine-all-higher` | `popup.combine_all_higher` | overlay | `combine-all-higher-id.png` | legacy / legacy-only | FUTURE | Confirmación. |
| 70 | `combine-all-identical` | `popup.combine_all_identical` | overlay | `combine-all-identical-id.png` | legacy / legacy-only | FUTURE | Confirmación. |
| 71 | `inventory` | `screen.inventory` | base | `inventory-id.png` | legacy / candidate | FUTURE | Candidate 3H.1; Quick Menu; subestado item-lock. |
| 72 | `awakening` | `screen.awakening` | unclear | `awakening-id.png` | legacy / unresolved | FUTURE | Close en vez de back; puede ser panel. Estados done/not-ready. |
| 73 | `awakening-receive-rewards-alert` | `popup.awakening_rewards` | overlay | `awakening-receive-rewards-alert-id.png` | legacy / legacy-only | FUTURE | Confirmación yes/no. |
| 74 | `treasure` | `screen.treasure` | base | `treasure-id.png` | legacy / legacy-only | FUTURE | Quick Menu; menús locales gold/platinum comparten un mismo asset typo `trasure`. |
| 75 | `opening-chest-animation` | `state.treasure.opening` | internal | `opening-chest-animation-id.png` | legacy / legacy-only | FUTURE | Animación/microestado con currency gold-key/karats. |

## Quick Menu legacy y decisión 0.2

Quick Menu no es una de las 75 entradas. Legacy lo representaba mediante
`MENU_RAPIDO`, una estructura global detectada con `assets/ui/menu-rapido-id.png` en
una región fija. Dieciocho contextos declaraban disponibilidad; los botones se
compartían y `MENU_RAPIDO_OFFSET` sí contemplaba el desplazamiento entre `default`
y `lobby`. El problema no era ausencia de esa dimensión, sino que quedaba distribuida
entre contexto, coordenadas y offsets; además, un comentario legacy indica que el
signo estaba invertido y que las coordenadas debían recapturarse.

Conocimiento preservable:

- el menú tiene identidad visual propia y se detectaba, no sólo se asumía;
- puede abrirse desde múltiples bases;
- su contenido ofrece destinos comunes, incluido cambio/selección de personaje;
- el contexto inferior sigue siendo una dimensión separada.

Conocimiento no promovible:

- valores concretos de coordenadas, offsets y targets (el concepto de desplazamiento
  sí se preserva);
- causalidad entre un tap y un destino;
- el asset histórico sin reevaluarlo contra current-season;
- disponibilidad declarada por contexto sin confirmación live.

La semántica elegida es `menu.quick`, usando el slot de overlays de
`ResolvedState`: el namespace expresa que es un menú global y no un popup, mientras
la composición base + overlays ya representa correctamente coexistencia sin ampliar
el contrato.

La sesión human-confirmed `20260825T193046_517947Z-76b5e238` comprobó apertura
instantánea, cierre y reapertura sobre Lobby, y apertura/cierre sobre Inventory. La
posición horizontal cambia con la base, confirmando la observación legacy sin copiar
sus offsets. La curación conservó 18 positivos y 15 negativos estables; excluyó frames
de borde de interacción, GT transicional/atrasado y corrigió `9485/9546` a negativos
porque visualmente el menú ya estaba cerrado. El manifest versionado
`datasets/quick_menu_evidence_manifest.json` registra selección y exclusiones.

Se promovió el crop current-season de 126×140 del tile literal “Lobby” dentro del
menú. Una única región `(0.02, 0.10, 0.25, 0.32)` admite las posiciones confirmadas
sobre Lobby e Inventory sin conocer la base ni aplicar offsets por contexto. El path
productivo grayscale obtuvo 18/18 TP, 0 FP y 0 FN contra 77 negativos, con raw
`0.2981472909450531 → 0.9826233983039856` y gap `0.6844761073589325`.
El menú tapa el landmark inferior de Lobby, por lo que esos frames resuelven
correctamente `UNKNOWN + menu.quick`; esto no convierte el menú en base ni inventa
la pantalla oculta. No hubo un segundo smoke streaming post-promoción porque el
dispositivo ya no figuraba en ADB; la evaluación productiva se hizo sobre los PNG
intactos adquiridos live en esa sesión. La adquisición World Boss del 2026-08-27
validó además `screen.world_boss`: el target común `(0.1940, 0.0564)` abrió y cerró
el mismo overlay, restauró la base, y también fue revalidado sobre Lobby. Su evidencia
permanece en un manifest separado con base `unknown` mientras el panel la oculta.

## Cobertura semántica disponible para Black Market y Rotation

| Estado disponible | Consumidor futuro | Estado 0.2 | Validación / límite |
|---|---|---|---|
| `screen.character_select` | `rotation.standard` | production | Offline 12/12 y live current-season. |
| `screen.lobby` | `BlackMarketFlow` y Rotation | production | Offline 12/12 visibles y live current-season; bajo Quick Menu queda oculta y resuelve `UNKNOWN`. |
| `menu.quick` | `rotation.standard` | production overlay/menu | 18/18 TP, 0 FP/FN sobre 95 labels totales; live sobre Lobby e Inventory. No es prerequisite de `BlackMarketFlow`. |
| `screen.black_market` | `BlackMarketFlow` | production | Offline 11/11 y live current-season después de repair 3F. |
| `popup.purchase_confirmation` | `BlackMarketFlow` | production | Offline 6/6 y live sobre base conocida/UNKNOWN. |
| `popup.insufficient_gold` | `BlackMarketFlow` | production | Human-confirmed live; 1 TP y 0 FP/FN frente a 95 negativos. |
| `popup.inventory_full` | `BlackMarketFlow` | production con gating Black Market | 6/6 TP, 0 FP/FN; cero conflictos para `OK + screen.black_market` en 252 capturas locales. |

Black Market se abre exclusivamente desde Lobby. Quick Menu se reserva para el cambio
de personaje transversal de Rotation. Dentro de `screen.black_market`, 3H.3 promovió
`currency.black_market.gold` con índice row-major para el grid 5×2. El futuro flow no
necesita identidad/tipo de item, precio, balance, OCR ni VLM: compra únicamente slots
GOLD. Ningún item/slot se convierte en contexto.

## Cobertura semántica disponible para World Boss

| Estado disponible | Estado 0.2 | Validación / límite |
|---|---|---|
| `screen.battle_mode_select` | production | 6 frames nuevos más corpus previo; distinguido explícitamente del selector PvP. |
| `overlay.world_boss_select_boss` | production overlay | 4 frames; la base queda deliberadamente `unknown` mientras el modal la tapa. |
| `popup.world_boss_previous_rewards` | production popup | 5 frames de la recompensa opcional del boss anterior; no implica participación actual. |
| `screen.world_boss` | production | 8 frames; el landmark excluye boss, rank, daño y valores variables. |
| `screen.world_boss_battle` | production | 21 frames, incluidos 8 con Raid Complete; landmark estructural de daño sin números. |
| `overlay.world_boss_raid_complete` | production overlay | 8 frames sobre la base de batalla todavía visible. |
| `status.world_boss_daily_active` | production semantic, sin consumidor | Badge Daily posicional en la tarjeta World Boss; positivos/negativos actuales e históricos, incluidos negativos con badges de otras tarjetas aún visibles. |

La curación conserva ROIs normalizados candidates para sapphires, costo, rank,
Start, Auto Repeat, Auto Battle, timer y taps seguros. Una segunda evidencia registra
Auto OFF/ON y sus métricas temporales, pero no promueve OCR, facts, parsers, acciones,
detector temporal ni flow.

## Señales Daily adquiridas y consumidores

Un único asset current-season del badge verde alimenta tres observaciones con ROIs
independientes: Friends All, Guild Attendance y World Boss en Battle Mode Select.
Friends también promueve `screen.friends` y `landmark.friends_all_button`; la transición
live confirma que All elimina el badge de forma estable y Close restaura Lobby.
`SendStaminaFlow` consume esa señal con tap único, espera fresca y retorno verificado.
Guild
conserva por separado el estado active/completed del botón y el badge Daily. Falta el
negativo live `Attendance activo + Daily ausente`, por lo que ningún guard de Guild fue
implementado. World Boss expone sólo elegibilidad externa futura; su flow general-purpose
permanece sin esa precondición.

## Ciclo de incorporación 0.2

El ciclo queda: descubrir → agregar un label único al acquisition vocabulary → adquirir
GT humano → revisar raw → evaluar señal contra negativos → promoción explícita →
regresión productiva. Un candidate requiere una sola entrada y tests; catálogo, specs y
assets sólo cambian al promover. Esto evita duplicar los 75 registros y reconstruir el
monolito legacy.
