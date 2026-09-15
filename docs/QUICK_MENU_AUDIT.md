# Auditoría transversal de Quick Menu (baseline `0cca707`)

Estado: **contrato pendiente; implementación detenida**. Esta auditoría distingue la base física conocida por la adquisición de la base que resuelve el runtime en un frame. No cambia código ni aceptación perceptiva. Checkpoint recibido: `2202/2202` hardware-free.

## Contrato observado

`menu.quick` es un overlay independiente que el resolver obtiene del tile literal Lobby. El resolver decide la base únicamente por las reglas de base del mismo batch; no conserva origen temporal. Por tanto `menu.quick` puede coexistir con una base resuelta, pero el overlay por sí solo no acredita cuál es la base. La policy productiva general para abrirlo permite Lobby, Guild, Pets Manage, Pet Summon y World Boss. Battle Mode Select tiene una ruta especial de retorno a Lobby, fuera de esa allow-list. Inventory fue adquirido como origen físico, pero continúa acquisition-only y se resuelve `UNKNOWN` en producción.

La divergencia es concreta: `rotation._has_quick_menu`, `productive_runtime._has_quick_menu` y `battle_mode_zone._quick_menu` aceptan `UNKNOWN + menu.quick`. Esos predicates son `expected` de apertura, `precondition` y `retryable_from` de selección. `VerifiedTransition` usa la precondition antes del primer input y un snapshot fresco para retry; así un menú abierto sobre base desconocida puede autorizar el tap y el retry. Los abort predicates de Rotation y ProductiveRuntime excusan ese mismo estado. Esto contradice la regla de `AGENTS.md` de que UNKNOWN/AMBIGUOUS nunca autorizan input ni retry. `docs/ELIGIBILITY_V1.md` declara expresamente la autorización overlay-only; representa el contrato histórico, no prueba la identidad de base.

## Matriz base × visibilidad

| Base física / semántica | Menú cerrado | Menú abierto: resultado documentado | Clasificación / input hoy |
| --- | --- | --- | --- |
| Lobby | `RESOLVED screen.lobby` limpio | `UNKNOWN + menu.quick` en curados Lobby | Válido y productivo; selección autorizada hoy por overlay, incompatible con la regla UNKNOWN. |
| Guild | `RESOLVED screen.guild` con estado Attendance compatible | `RESOLVED screen.guild + menu.quick` en 3 curados | Válido y productivo; base observable, aunque la geometría debe corresponder al origen. |
| World Boss | `RESOLVED screen.world_boss` limpio | `UNKNOWN + menu.quick` en 4 curados | Válido y productivo; misma infracción de autorización. |
| Pets Manage / Pet Summon | Bases resueltas con sus estados compatibles | Menú abierto reportado live por la policy, sin manifest de base resuelta bajo el panel en esta auditoría | Válido según policy; resolución y geometría bajo menú requieren evidencia dirigida. Tests de rutas usan `UNKNOWN + menu.quick`. |
| Battle Mode Select | `RESOLVED screen.battle_mode_select` con Daily compatible | `UNKNOWN + menu.quick` en 3 curados de retorno | Válido en ruta especial BattleModeZone/Eligibility; fuera de la policy general; selección de Lobby hoy autorizada por overlay. |
| Inventory | Base acquisition-only, runtime `UNKNOWN` | `UNKNOWN + menu.quick` en adquisición 3H.2 | Físicamente válido, no habilitado como origen productivo. |
| Friends / Mailbox | Bases productivas propias | Sin evidencia de menú abierto ni allow-list | Combinación no soportada; no afirmar imposibilidad física. Las entradas productivas son directas desde Lobby. |
| Character Select | `RESOLVED screen.character_select` | Sin evidencia de menú abierto ni allow-list | Combinación no soportada; no afirmar imposibilidad física. |
| Base foreign resuelta | `RESOLVED` foreign | `RESOLVED foreign + menu.quick` posible en el modelo, sin GT físico | No autoriza acción Quick Menu bajo policy general. `productive_runtime._has_quick_menu` hoy no comprueba allow-list y la aceptaría. |
| UNKNOWN | `UNKNOWN` | `UNKNOWN + menu.quick` confirmado en varios orígenes físicos | NO debe autorizar input/retry; hoy sí participa en tres consumidores. |
| AMBIGUOUS | `AMBIGUOUS` | Modelo admite overlay; sin GT físico | NO autoriza input/retry; los tres predicates principales lo rechazan. |

No hay evidencia para declarar físicamente imposible ninguna combinación no adquirida. Overlay ausente no satisface los predicates de apertura; sólo la base limpia autorizada permite repetir `OpenQuickMenu`.

## Consumers productivos

| Consumer / transición | Base permitida | Expected; retry; abort | Geometría / supuesto del menú | Percepción; recomendación |
| --- | --- | --- | --- | --- |
| Rotation `open_quick_menu` | 5 bases de policy; Guild admite Attendance activo/completado | `_has_quick_menu`; base limpia capaz; unexpected state | Opener fijo `(0.1940, 0.0564)` adquirido para Lobby/World Boss y declarado para la policy | Global. Mantener hasta cerrar semántica y equivalencia de todos los orígenes; subset común incluiría bases y overlays de varias familias. |
| Rotation `open_character_select` (R2-C) | Origen inicial de las 5 bases | Character Select limpio; `_has_quick_menu`; unexpected Character Select state | Layout Lobby o shifted calculado del origen inicial, pero snapshot del menú puede ser UNKNOWN | Global. No scopear: el scope de header+tile pierde origen y el global tampoco lo resuelve sobre Lobby/WB. |
| ProductiveRuntime `open_quick_menu` | Origen limpio de policy | `_has_quick_menu`; mismo origen limpio; incompatible open state | Opener fijo | Global. Mismo bloqueo de semántica; origen fijo permite estudiar scope por familia después. |
| ProductiveRuntime `select_lobby` | Origen inicial capaz; también Battle Mode Select vía Eligibility | Lobby limpio; `_has_quick_menu`; incompatible destination state | Tile Lobby fijo `(0.2020, 0.2050)` adquirido en retorno Battle Mode; overlay visible no demuestra target para cada origen | Global. Menú/bases primero; la ausencia global de overlays para Lobby limpio sigue siendo blocker B2 independiente. |
| ProductiveRuntime `select_guild` | Origen no-Lobby limpio de policy | Guild limpio; `_has_quick_menu`; incompatible destination state | Shifted calculado del origen inicial | Global. Necesita autorización del origen actual y equivalencia geométrica; navegación a Pets/Summon usa este retorno. |
| BattleModeZone `leave`: `open_quick_menu` → `select_lobby` | Battle Mode Select con Daily compatible | `_quick_menu`; luego Lobby limpio; guard repetido para retry; sin abort explícito | Opener y tile Lobby fijos; controles adquiridos human-operated, sin replay automático | Global. `UNKNOWN + menu.quick` autoriza selección y retry; ruta especial no debe diluirse en allow-list general. |
| `OpenGuild` directo | Lobby limpio | Guild limpio; Lobby limpio; incompatible destination state | Target directo, no tile | Scoped (`GUILD_NAVIGATE_SCOPE`, incluye tile para bloquear overlay). Sin dependency de selección Quick Menu. |
| `OpenFriends` / `OpenMailbox` | Lobby limpio | Friends/Mailbox; flujo sin retry productivo de entrada; abort propio | Targets directos, no tiles | Navegación global; consumers vecinos independientes del contrato Quick Menu. |
| Pets Manage / Summon | Lobby directo o normalización desde base capaz | `open_quick_menu`/`select_lobby` o `select_guild` en normalización; luego base Pets | Targets Quick Menu preceden el flow; scopes Pets incluyen tile como blocker | Entrada Quick Menu global; normal path Pets ya scoped donde procede. |
| Portal obstruction recovery | Cualquier transición verificada que lo tenga conectado | Probe físico confirmado; reobservación; caller reevalúa expected/retry | Dismiss portal, no tile Quick Menu | Global y separado. Puede operar tras fallo de transición Quick Menu; no suministra identidad de base ni autoriza repetir la acción productiva por sí mismo. |

`OpenFriends`, `OpenMailbox` y `OpenGuild` no abren Quick Menu. Los scopes existentes que llevan el tile son Guild navigate, Pets Manage navigate, Pet Summon, Rotation Character Selection y World Boss Eligibility; lo usan para preservar un blocker, no para seleccionar tiles. No se encontró navegación productiva a Pets mediante un tile Pets.

## Geometría y estabilidad

El tile Lobby se detecta en una ROI horizontal amplia `(0.02, 0.10, 0.25, 0.32)` que cubre placements distintos. Detectar su texto no valida una coordenada de acción. `SelectQuickMenuGuild` y `OpenCharacterSelect` codifican dos layouts (`LOBBY`, `SHIFTED`) y derivan el layout del origen **anterior**; no del estado resuelto bajo el menú. `SelectQuickMenuLobby` y `OpenQuickMenu` usan coordenadas fijas. La geometría se escala por `FrameGeometry` del snapshot, pero sus hitboxes son actuales para el layout 2712×1224 y no se cambiaron. Los targets Lobby del retorno Battle Mode están visualmente dentro del control adquirido; el manifest especifica intervención humana y ausencia de replay automático. No generalizar esa evidencia a otros orígenes.

El detector `quick-menu-lobby-tile.png` es **seasonal-risk**: crop literal current-season, calibrado en positivos/negativos curados pero sin dataset multitemporada controlado. El landmark Lobby que el menú tapa también tiene riesgo seasonal documentado; no usarlo como requisito implícito del overlay ni abrir clean Lobby en esta tarea. El landmark Guild Message tab es **likely stable** dentro del corpus actual, incluido Guild+Quick Menu; estabilidad multitemporada desconocida. No hay detector estructural independiente del texto Lobby para el menú en producción.

## Decisión pendiente y validación necesaria

El contrato mínimo demostrable hoy es: `menu.quick` prueba visibilidad; la base del mismo snapshot prueba origen autorizado y layout cuando está resuelta. La policy UNKNOWN/AMBIGUOUS debe prevalecer. Aplicar sólo `status is RESOLVED` a los predicates sería un fix fail-closed, pero rompería rutas productivas confirmadas desde Lobby, World Boss y Battle Mode Select, porque **el global también resuelve UNKNOWN**. Por eso no se implementó ese patch aislado ni se inventó un base sintético/carry temporal en el resolver. La decisión arquitectónica requiere evidencia de identidad observable bajo el overlay para esos orígenes. Una acción overlay-only sólo podría simplificar geometría después de resolver una base autorizada; no convierte UNKNOWN en autorización. Esa decisión precede R2-C y cualquier scope de selección.

Validación siguiente, limitada: evaluar en frames curados si existe landmark de base no ocluido bajo Quick Menu para Lobby, World Boss y Battle Mode Select; adquirir 1–3 condiciones HIL sólo si esa evidencia offline no basta, con confirmación humana de base y target. Cubrir cada base soportado, UNKNOWN, AMBIGUOUS, foreign, overlay ausente, layout mismatch, retry/abort/no-input y resolver preservation antes de performance. Sólo después: `predicate → semantic dependencies → detector subset → geometry → retry/abort vocabulary`, usando `ScopeSpec` y el wiring existente. Ningún detector/ROI/asset cambió aquí: evaluator y corpus global no están invalidados; tampoco el checkpoint hardware-free.
