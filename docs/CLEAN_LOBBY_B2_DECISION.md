# Clean Lobby / B2 — decisión arquitectónica

Fecha: 2026-09-16. Baseline: `rebuild/stable-baseline @ 56ea071`.

## Decisión

`clean Lobby` conserva su significado fuerte:

```
RESOLVED screen.lobby + overlays vacíos
```

Se distinguen dos usos:

- **discovery/recovery/postcondición de sesión**: observación global. Responde si el
  runtime está realmente en un contexto limpio desde cero.
- **postcondición de una transición conocida a Lobby**: conserva exactamente la
  misma semántica del resolver, pero ejecuta sólo los 77 detectores que producen
  alguna dependencia de `BASE_CONTEXT_RULES` o `OVERLAY_RULES`. El source
  verificado, la acción, `after_sequence`, retry, abort y recovery siguen en el
  caller.

No se adoptó todavía un contrato C reducido por transición. Faltan datos físicos
para declarar irrelevantes o imposibles blockers concretos. El resultado es el
modelo D: contrato fuerte global para discovery/recovery y observación
resolver-complete para transiciones conocidas. La separación reduce trabajo sin
debilitar la propiedad observada.

## Consumers

| consumer | current clean-Lobby contract | blockers relevant | seasonal dependency | proposed contract | decision |
|---|---|---|---|---|---|
| CloseFriends → Lobby | Lobby resuelto, overlays vacíos | Todo el catálogo mientras no exista exclusión física; base Friends y bases foreign preservadas | `Trading Center`, seasonal-risk | Source Friends limpio + CloseFriends + evidencia fresca resolver-complete | **SAFE_TO_SCOPE**, 95→77 |
| Mailbox close → Lobby | Igual | Igual; Mailbox y bases foreign preservadas | Igual | Source Mailbox limpio + CloseMailbox + evidencia fresca resolver-complete | **SAFE_TO_SCOPE**, 95→77 |
| Daily close → Lobby | Igual | Igual; Quests y bases foreign preservadas | Igual | Source Quests limpio + CloseQuests + evidencia fresca resolver-complete | **SAFE_TO_SCOPE**, 95→77 |
| Black Market close → Lobby | Igual | Igual; popups BM, bases foreign y recovery preservados | Igual | VerifiedTransition source BM + CloseBlackMarket + evidencia fresca resolver-complete | **SAFE_TO_SCOPE**, 95→77 |
| ClosePets → Lobby | Igual | Igual; familia Pets y bases foreign preservadas | Igual | VerifiedTransition source Pets + ClosePets + evidencia fresca resolver-complete | **SAFE_TO_SCOPE**, 95→77 |
| `select_lobby` → Lobby | Igual; opener/handoff ya cerrado | Menú, todas las bases/overlays y handoff invalidado por recovery | Igual | QuickMenuHandoff vigente + SelectQuickMenuLobby + evidencia fresca resolver-complete | **SAFE_TO_SCOPE**, sólo el wait final, 95→77 |
| Rotation R2-B Select → Lobby | Igual | Todas las bases/overlays; Character Select preservado para retry/abort | Igual | Source Character Select + ConfirmCharacterSelection + evidencia fresca resolver-complete | **SAFE_TO_SCOPE**, 95→77 |
| BattleModeZone leave → Lobby | Igual | Menú, Battle Mode Select, todas las bases/overlays; handoff vigente | Igual | Handoff vigente + SelectQuickMenuLobby + evidencia fresca resolver-complete | **SAFE_TO_SCOPE**, sólo el wait final, 95→77 |
| Discovery, recovery y postcondición de flow/session | Global | Todo el catálogo y readers/facts necesarios por el consumidor | Igual | Sin cambio | **KEEP_GLOBAL_DISCOVERY / KEEP_GLOBAL_SEASONAL** |

## Contratos operativos por consumer

| consumer | source | action | expected | retryable_from / abort_if | timing | carry / recovery | siguiente input |
|---|---|---|---|---|---|---|---|
| CloseFriends | Friends limpio | CloseFriends | clean Lobby | sin retry de acción; abort incompatibles | timeout 6 s, stable 0.25 s | `after_sequence` del source; sin recovery local; snapshot no sale del FlowResult | ninguno antes de postcondición global del runner |
| Mailbox close | Mailbox limpio | CloseMailbox | clean Lobby | sin retry de acción; abort incompatibles | 6 s, stable 0.25 s | igual | ninguno antes del postcheck global |
| Daily close | Quests limpio | CloseQuests | clean Lobby | sin retry de acción; abort incompatibles | 6 s, stable 0.25 s | igual | ninguno antes del postcheck global |
| BM close | Black Market limpio | CloseBlackMarket | clean Lobby | retry sólo desde BM limpio; abort navegación incompatible | normal 5 s, grace 2 s, 2 attempts, stable 0.25 s | `action_source_snapshot`; shared obstruction recovery | ninguno antes del postcheck global |
| ClosePets | Pets Manage/Summon limpio | ClosePets | clean Lobby | retry sólo desde source; abort destino incompatible | normal 6 s, grace 2 s, 2 attempts, stable 0.25 s | `action_source_snapshot`; shared obstruction recovery | caller reobserva global antes de abrir Pets u otra navegación |
| select_lobby | source limpio + QuickMenuHandoff | SelectQuickMenuLobby | clean Lobby | retry por handoff; base contradictoria/menú perdido aborta; recovery invalida handoff | normal 6 s, grace 2 s, 2 attempts, stable 0.25 s | source/action lineage existente; no handoff nuevo | caller reobserva global antes de otra navegación |
| R2-B | Character Select limpio | ConfirmCharacterSelection | clean Lobby | retry sólo desde Character Select; abort clean screen incompatible | normal 6 s, grace 2 s, 2 attempts, stable 0 | `action_source_snapshot`; shared obstruction recovery | SessionRunner valida postcondición global antes de continuar |
| BattleModeZone leave | Battle Mode Select + QuickMenuHandoff | SelectQuickMenuLobby | clean Lobby | retry por handoff; recovery invalida; estado incompatible aborta | normal 6 s, grace 2 s, 2 attempts, stable 0.25 s | lineage existente | zone/session valida postcondición antes de continuar |

No cambiaron action count, timeouts, grace, `stable_for`, `after_sequence`,
attempts ni recovery boundaries.

## Comparación de modelos

| modelo | evaluación |
|---|---|
| A. Lobby + ausencia global de overlays | Correcto y fuerte, pero ejecuta 95 detectores aun cuando el consumer sólo necesita resolución contextual. Se mantiene para discovery/recovery. |
| B. landmark estructural + blockers relevantes | Preferible a largo plazo, pero no existe landmark estructural probado. No implementable con evidencia actual. |
| C. contrato local por transición | Arquitectónicamente válido sólo con source/action/freshness y lista completa de blockers relevantes. No hay evidencia física suficiente para recortar por consumer. |
| D. fuerte para discovery + local para transiciones | **Elegido.** La primera etapa local es resolver-complete: idéntica semántica de bases/overlays, 77 detectores. Un C más pequeño queda condicionado a evidencia HIL. |

## Blockers y overlays

Regla conservadora vigente: los 57 outputs de `OVERLAY_RULES` son
`MUST_BLOCK` para los siete consumers. Ninguno autoriza input. Salvo los casos
indicados, la coexistencia física con Lobby es **UNKNOWN**: no se declara
`IMPOSSIBLE` por ausencia de ejemplos.

| overlay | coexistencia física con Lobby | consumers | autoriza input | bloquea success | evidencia / clase |
|---|---|---|---|---|---|
| `popup.monster_wave_ticket_purchase` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.monster_wave_insufficient_sapphires` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.monster_wave_inventory_board` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.monster_wave_clear` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `overlay.monster_wave_usage_tooltip` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.monster_wave_new_ranking` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.monster_wave_weekly_results` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.monster_wave_daily_active` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.pet_summon_daily_active` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.pet_epic_available` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.pet_epic_unavailable` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.pet_premium_ticket_available` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.pet_premium_gold` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `overlay.pet_epic_selector` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `overlay.pet_premium_ticket_selector` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `overlay.pet_premium_gold_selector` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.pet_epic_insufficient_fragments` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.pet_inventory_full` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.pet_combine_all` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.pet_combine_no_material` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.pet_epic_runes_full` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.pet_mass_evolve_confirmation` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `mode.pet_mass_evolve_selection` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.friends_send_stamina_daily_active` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.guild_attendance_active` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.guild_attendance_completed` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.guild_attendance_daily_active` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.world_boss_daily_active` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `mode.daily_quests` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.daily_quests_claimable` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.daily_quests_progress_reward_claimable` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `mode.mailbox_character_mail` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.mailbox_claimable` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.mailbox_read_mail_present` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.equipment_inventory_full` | posible; contraejemplo semántico conocido | todos | no | sí | Lobby + popup no es clean Lobby; MUST_BLOCK |
| `mode.combine_fuse` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `mode.combine_transmute` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.combine_transmute_available` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.combine_ethereal_available` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `status.combine_fuse_available` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `panel.combine_awakened_transmute` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `panel.combine_ethereal_random_part` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.combine_all` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.ethereal_mass_combine` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.ethereal_no_material` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `overlay.world_boss_select_boss` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.world_boss_previous_rewards` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.socket_inventory_full` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.meteor_inventory_full` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.socket_enhance_all` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.socket_no_material` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.socket_sell` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `overlay.world_boss_raid_complete` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.inventory_full` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.insufficient_gold` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `popup.purchase_confirmation` | UNKNOWN | todos | no | sí | regla del resolver; MUST_BLOCK |
| `menu.quick` | sí, base subyacente preservada | todos | no por sí solo | sí | frames/contrato QuickMenu; MUST_BLOCK |

El test de cierre sintetiza `Lobby positive + cada overlay` como invariante del
resolver; no lo presenta como ground truth físico. También sintetiza `Lobby
positive + cada una de las 17 bases foreign` y exige `AMBIGUOUS`.

## Robustez seasonal

| señal | clasificación | resultado |
|---|---|---|
| `landmark.lobby_trading_center_label` | **seasonal-risk** | Única señal positiva productiva. Incluye texto y decoración/fondo actuales. |
| icono de oro legacy | shell-persistent, no exclusivo | No distingue Lobby. Rechazado como prueba positiva. |
| `lobby_commerce_pair` legacy/offline | unknown | Candidato no promovido, sin métricas ni contrato productivo suficiente. |
| banners/eventos/fondo | seasonal-risk | No deben definir identidad semántica. |
| landmark estructural pequeño | needs evidence | No existe uno demostrado entre assets/detectores actuales. |

La identidad semántica permanece `screen.lobby`; su implementación visual es
reemplazable. Un cambio de temporada se manifestará como timeout/UNKNOWN y
evidencia de fallo, no como fallback silencioso. Reemplazar o recalibrar el asset
de Lobby requerirá evaluator incremental de positivos, negativos cercanos y
regresiones. Este cambio de routing no modifica detector, ROI, asset ni
calibración, por lo que no invalida evaluator/corpus.

## Falso success y límites

- El scope contiene las 79 observaciones semánticas requeridas por el catálogo:
  71 LocalCv y 8 outputs producidos por 6 detectores especializados.
- Son 77 instancias porque algunos especializados producen más de un output.
- Se conservan todas las bases foreign, todos los overlays, orden e instancias.
- `UNKNOWN` y `AMBIGUOUS` no satisfacen clean Lobby.
- El source/action lineage y freshness vienen de los waits o
  `VerifiedTransition`; ver Trading Center aislado no basta.
- El siguiente input queda además detrás del postcheck global de flow/session o
  de una reobservación global del precondition navigator.
- No hay fallback scoped→global durante el wait. El fallback de construcción ya
  existente sólo se usa si el runtime no soporta scoping o falta un detector.

## D / snapshot reuse

Existe duplicación local: el close demuestra Lobby y el runner vuelve a observar
la misma propiedad; la siguiente precondition puede observarla una tercera vez.
No se reutiliza en B2 porque `FlowResult` y los resultados de zone/rotation no
transportan de forma uniforme un snapshot de postcondición. Resolverlo exigiría
un contrato transversal SessionRunner-wide. Clasificación: **D_REUSE deferred**.

## Evidencia y HIL

No se necesita HIL para la migración 95→77 porque no cambia la semántica ni los
detectores. HIL sí será necesario para reducir por debajo de 77:

1. una condición/source a la vez;
2. confirmar qué overlays pueden coexistir tras ese close;
3. adquirir negativos próximos para un landmark estructural;
4. validar R2-B físicamente sólo si se quiere evidencia temporal del dispositivo.

No se declara robustez multitemporada a partir de frames de una sola temporada.

## Benchmark

Cinco frames reales de Lobby, dos pasadas medidas después de warm-up:

| transición/scope | before | after | ms/frame |
|---|---:|---:|---:|
| global | 95 | 95 | 657.53 |
| Friends → Lobby | 95 | 77 | 419.99 |
| Mailbox → Lobby | 95 | 77 | 420.80 |
| Daily → Lobby | 95 | 77 | 416.32 |
| Black Market → Lobby | 95 | 77 | 412.51 |
| Pets → Lobby | 95 | 77 | 413.59 |
| Quick Menu/BattleMode → Lobby | 95 | 77 | 411.73 |
| R2-B → Lobby | 95 | 77 | 423.54 |

Los frames actuales demuestran equivalencia actual, no estabilidad seasonal.

## Clasificación final

- **SAFE_TO_SCOPE**: CloseFriends, Mailbox, Daily, Black Market, ClosePets,
  `select_lobby`, BattleModeZone leave y R2-B.
- **KEEP_GLOBAL_DISCOVERY**: probes, recovery y postcondiciones de flow/session.
- **KEEP_GLOBAL_SEASONAL**: no se sustituye la única señal positiva actual.
- **NEEDS_NEW_SEMANTICS / NEEDS_EVIDENCE**: scopes menores por consumer y landmark
  estructural de Lobby.
- **D_REUSE**: duplicación local identificada, no implementada.
