# Quick Menu: decisión de arquitectura para el normal path

Baseline `rebuild/stable-baseline @ 4606bf3`; checkpoint recibido `2202/2202` hardware-free. **Decisión de modelo: B para el normal path; A queda como observación/cross-check en discovery y recovery. Al momento de esta decisión, la implementación estaba diferida por lineage de retry/recovery no expuesto todavía.** La decisión documental original no cambió el runtime ni alteró `ContextResolver`; la implementación posterior conserva ese límite.

## Comparación

| Criterio | A: base + menú en mismo frame | B: verified-origin handoff | Decisión |
| --- | --- | --- | --- |
| Correctness normal path | Exige base visible bajo panel; los curados de Lobby, World Boss y Battle Mode Select son `UNKNOWN + menu.quick`. | Origen `RESOLVED` antes de `OpenQuickMenu`; overlay fresco después; autorización proviene de la transición, no de UNKNOWN. | B representa las rutas observadas sin convertir overlay en base. |
| Freshness | Una sola observación actual, directa. | Requiere snapshot fuente que autorizó el **input efectivo**, menú con secuencia posterior y uso inmediato en la misma rama. | B precisa lineage explícito; `operation_id`/snapshot inicial solos no bastan. |
| Retry `OpenQuickMenu` | Requiere base resuelta de nuevo. | Retry sólo desde fuente limpia resuelta y permitida, con snapshot fresco; debe transportarse la fuente del último intento efectivo. | B posible, pero `VerifiedTransitionResult` no entrega esa fuente. |
| Retry de tile | Base+overlay actuales podrían reautorizar. | Mismo handoff aún activo + overlay fresco sin pérdida observada + estado no contradictorio; retry bounded de la misma acción. | UNKNOWN aislado nunca basta. Recovery invalida el handoff anterior. |
| Abort/foreign | Global detecta bases contradictorias si existen landmarks. | `RESOLVED` distinto del origen bajo menú o AMBIGUOUS aborta; scope debe conservar detectores que puedan revelar esa contradicción. | B no justifica un scope de sólo tile+destino. |
| Geometría | Base actual determina layout si se resuelve. | Layout deriva de fuente verificada; geometría física del tap usa `final_snapshot.geometry`; visibility no valida target. | B explica Lobby/shifted sin inferir layout desde UNKNOWN. |
| Recovery | Puede redescubrir base tras cleanup. | Toda limpieza/intervening input invalida provenance; un nuevo source verificado puede iniciar otro handoff. | B necesita señal de recovery **antes** de un retry productivo. |
| Complejidad | Nuevos landmarks/calibración debajo de cada panel y evaluaciones físicas. | Token local pequeño o argumentos explícitos; el verifier debe exponer action anchor e intervención de recovery. | B reduce trabajo perceptivo, pero no debe crear lifecycle global. |
| Scoping | Debe incluir base, overlay, destino y contradicciones. | Puede omitir el landmark del origen oculto; mantiene overlay, destino y vocabulario de abort/cross-check. | Candidato posterior a correctness; subset de 2 no queda probado. |
| Seasonality | Nuevos landmarks bajo panel y el tile current-season. | Mantiene detector current-season del menú y base limpia preacción; no añade dependency de clean Lobby bajo panel. | B evita deuda seasonal nueva, sin eliminar la del tile. |
| Menú ya abierto al entrar | Si base+overlay resueltos, podría reconocerlo. | Sin apertura verificada en esta rama, no hay token. | Discovery/reorientation; ningún tile input/retry. |

Same-frame landmarks no son requisito del normal path de B. Sirven como cross-check opcional de un handoff, y como evidencia de discovery, recovery, debugging o telemetry; incluso `RESOLVED base + menu.quick` descubierto sin apertura de esta rama no crea automáticamente provenance ni autoriza un tile. La reorientación puede iniciar después una operación nueva desde un estado verificado.

## Invariantes de B

La cadena autorizante es `source RESOLVED permitido y limpio → OpenQuickMenu ejecutado desde ese source → menú observado después de la acción → handoff local explícito → tile elegido con layout derivado del source`. El handoff transporta `source base`, `source sequence/action anchor`, `menu sequence` y `layout`; `final_snapshot` ya transporta frame y geometry. No necesita un base sintético ni memoria del resolver. La causalidad presupone un solo emisor de input durante la operación; una intervención humana/externa invalida la rama y exige reobservación, porque una secuencia fresca sola no detecta input no registrado. El precedente `run_with_initial` muestra que un snapshot verificado puede entregarse explícitamente a un consumer; no prueba por sí mismo la causalidad de un retry.

La observación del menú puede ser `UNKNOWN + menu.quick` sólo **dentro de esa cadena**. UNKNOWN acredita únicamente que ningún base rule matcheó ese frame; no es la razón del input. Sin handoff, `UNKNOWN + menu.quick` o `AMBIGUOUS + menu.quick` sólo permiten discovery, recovery o reorientation pasiva, nunca tile input ni retry. Tampoco se debe usar un `RESOLVED` foreign bajo menú como nuevo origen: `Pets → Guild + menu.quick` invalida y aborta aunque Guild sea globalmente capaz.

El handoff vive en una rama local y se consume al seleccionar destino. Se invalida en cierre/ausencia observada del menú, overlay contradictorio, base foreign/AMBIGUOUS, input distinto de la selección autorizada, recovery, fallo, salida de rama o transferencia a otro consumer sin argumento explícito. Si el destino queda resuelto después del tap, se verifica la postcondición y se descarta el token; un retry posterior requiere overlay fresco, continuidad observada y presupuesto bounded. La ausencia del menú durante un wait puede dejar continuar la espera pasiva por el destino, pero prohíbe reabrir/reintentar usando el token antiguo.

Para `OpenQuickMenu`, cada intento usa una fuente limpia resuelta y fresca. La policy de retry no puede cambiar silenciosamente de Lobby a Guild: si cambia el origen, se aborta o se crea una transición nueva con su propia fuente/layout. `VerifiedTransitionResult` hoy sólo publica `final_snapshot`, outcome y attempt_count; no publica el snapshot que autorizó el último input. También puede devolver `SUCCESS_FIRST_ATTEMPT` tras recovery de precondition, donde el source inicial no fue el que autorizó el tap. Por ello, capturar sólo `initial` + `opened.final_snapshot` no demuestra el handoff en todos los paths.

En selección, `VerifiedTransition` puede llamar al recovery compartido entre intentos y luego consultar `retryable_from`. Un closure que mira sólo `menu.quick` y secuencia volvería a autorizar el tile tras cleanup. La implementación mínima debe dar al guard una invalidación local cuando recovery actúa, antes de cualquier retry; la alternativa conservadora es terminar esa selección y reorientar, sin reutilizar el token. No se requiere un coordinador de lifecycle. El API exacto (action anchor en result y adaptador local de recovery, o equivalente pequeño) se decide al implementar con tests del verifier.

## Consumers

| Consumer | Provenance que puede recibir | Layout | Problema vigente | Modo posterior / blocker |
| --- | --- | --- | --- | --- |
| Rotation `open_quick_menu` | Fuente inicial de policy; actualizar al source del intento efectivo | Opener fijo | Retry desde `capable` puede cambiar base | Global hasta publicar action anchor y restringir retry al mismo origen. |
| Rotation `OpenCharacterSelect` / R2-C | Resultado verificado de apertura en la misma rama | Lobby o shifted desde source | `_has_quick_menu` autoriza UNKNOWN aislado | Handoff antes de scoping; `stable_for=1.0`, timeout 6 s, after_sequence y sentinel siguen. Scope necesita cross-check/abort completo. |
| ProductiveRuntime `open_quick_menu` | Fuente local fija y limpia | Opener fijo | Expected acepta overlay aislado | Global de momento; familia/base scope evaluable luego. |
| `select_lobby` | Handoff de normalización | Tile fijo | Precondition/retry usan overlay aislado | Correctness migrable; wait a clean Lobby permanece global por B2. |
| `select_guild` | Handoff de normalización | Shifted desde source | Overlay aislado autoriza layout previo | Correctness migrable; scope sólo con destino Guild, fuente/cross-check y aborts. |
| `BattleModeZone.leave` | Fuente Battle Mode Select con Daily compatible, fuera de allow-list general | Opener/tile Lobby fijos | `_quick_menu` autoriza UNKNOWN aislado, sin abort explícito | Handoff local de zona; mantener global hasta equivalencia de abort/geometry. |
| Pets normalization | Handoff de `_navigate_to_lobby`/`_navigate_to_guild` | Shifted para destino Guild | Hereda selección insegura | Se beneficia de la migración del normalizador, sin nuevo flow policy. |
| Friends/Mailbox/OpenGuild directo, scopes blocker, portal recovery | Ninguno para tiles | Targets propios | No son selección Quick Menu; recovery puede interrumpir cadena | Sin migración de tile. Los scopes actuales conservan el tile sólo como blocker. |

## Validación y límite

Antes de code patch: tests de verifier deben demostrar fuente efectiva tras retry/precondition recovery y señal de cleanup antes de retry; tests de handoff deben usar los curados reales para `UNKNOWN + menu.quick` de Lobby/WB/Battle Mode y `RESOLVED Guild + menu.quick`, más contradicción/foreign/AMBIGUOUS sintéticos sólo como invariantes de seguridad, sin declararlos GT físico. Los taps/layout no cambian. HIL corto sólo si se modifica la secuencia física o si falta evidencia de un target en un origen; el manifest Battle Mode valida controles visuales con operación humana, no replay automático.

Esta ventana no implementa Q1 separado de Q2: cerrar sólo los predicates `UNKNOWN` cortaría rutas reales. No se scopea R2-C ni otros consumers antes de resolver action anchor/recovery lineage y preservar el vocabulario de contradicción. Clean Lobby/B2 sigue separado. Ningún detector, ROI, asset o calibración cambió; evaluator/corpus y suite hardware-free vigente no se invalidan por esta decisión documental.


## Estado posterior de implementación

El runtime ahora publica `action_source_snapshot` en cada resultado de `VerifiedTransition`, correspondiente al último input cuyo executor terminó normalmente. `recovery_after_action` marca cleanup posterior al opener y bloquea la creación del handoff aun si después aparece el menú. `on_recovery` invalida un handoff local antes de consultar el retry guard. Rotation, ProductiveRuntime y BattleModeZone crean un `QuickMenuHandoff` desde el resultado de apertura y pasan sus guards explícitamente a la selección. Los retries de apertura conservan el mismo origin contractual; un base resuelto contradictorio aborta.

R2-C conserva percepción global. Su ScopeSpec de dos detectores (`Character Select header` y tile Lobby del menú) oculta landmarks de bases foreign: `Guild + menu.quick` podría degradarse a `UNKNOWN + menu.quick` y, con lineage, autorizar erróneamente un retry. `select_lobby` conserva la verificación global de clean Lobby/B2. `select_guild`, BattleModeZone y openers permanecen globales hasta demostrar un subset con vocabulario de contradicción equivalente. No se tocaron hitboxes, detectores, ROI, assets, calibración ni `ContextResolver`.
