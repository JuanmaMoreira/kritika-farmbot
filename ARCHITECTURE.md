# Arquitectura — contratos estables

`IMPLEMENTATION_CONTRACT`. [GAMEPLAY_GT](docs/GAMEPLAY_GT.md) define la UI física; [CONTEXT](CONTEXT.md) declara wiring y divergencias actuales; [RESOURCE_ROUTING](docs/RESOURCE_ROUTING.md) concentra composición económica. Los nombres técnicos base/overlay del resolver no son la clasificación física canónica.

## Flujo y ownership

```text
Capture → Perception / Runtime Facts → ContextResolver
        → RuntimeObserver snapshot → Flow / support operation / SessionRunner
        → operación semántica verificada → ActionExecutor → AdbClient
```

| Owner | Responsabilidad y límite |
| --- | --- |
| ScrcpyFrameSource | Captura y cleanup de sus recursos |
| PerceptionEngine y readers | Observaciones/facts semánticos; nunca navegación o negocio. OCR demand-driven para datos necesarios |
| ContextResolver | Resolución pura y determinista: RESOLVED / UNKNOWN / AMBIGUOUS; no captura, input ni policy temporal |
| RuntimeObserver / TemporalObserver | Snapshot coherente de frame, secuencia, tiempo, observaciones, facts y geometría; evidencia multiframe sólo donde hace falta |
| Flow / activity | Intención de negocio, gates, outcomes y composición de operaciones; sin CV/ADB directos |
| AdsManager / AndroidAdsObserver | Lifecycle transversal de publicidad; ownership Android, progreso/cierre seguro y retorno. El caller prueba reward y decide retry |
| Support operation | Relief concreto y retorno caller-specific; no planner ni recovery general |
| BattleModeZone / PreparedActivity | Entrada/salida del hub y binding de actividad; sin gameplay o policy de inventario |
| SessionRunner / Rotation | Orden explícito y policy de sesión / cambio transversal de personaje |
| Eligibility / Identity | Contexto y skips en flows que lo requieren; MW no usa Eligibility. Sin estrategia automática |
| VerifiedTransition | Precondición, acción, efecto esperado; retry bounded y guardado con evidencia fresca |
| ActionExecutor / AdbClient | Intent validado → input según frame.shape / único límite activo ADB |
| CLI / GUI / observabilidad | Configuración, ejecución, cancelación y reporte; no policy de negocio |

El usuario selecciona objetivos/orden. La sesión comparte zona sólo entre actividades preparadas consecutivas compatibles, sin reordenar. Failure/cancelación no dispara navegación ciega en un finally. AdsManager permanece separado de percepción normal.

## Observación y autorización

Hot paths consultan evidencia relevante; discovery/recovery pueden observar ampliamente. Scopes deben conservar contradicciones/blockers relevantes al contrato, no sólo el destino esperado. Clean Lobby significa `RESOLVED screen.lobby` sin overlays; su implementación resolver-complete no prescribe clasificar físicamente todo el catálogo como BASE.

Estado UNKNOWN/AMBIGUOUS aislado nunca autoriza input. Un handoff local puede conservar el source verificado de una acción efectiva y autorizar sólo el siguiente control conocido bajo overlay fresco compatible. Quick Menu y entradas WB emplean ese contrato; no crean bases sintéticas ni estado global en el resolver. Base foreign, contradicción, pérdida observada o recovery invalidan el permiso de retry. Una espera pasiva posterior a input efectivo no equivale a nueva autorización.

`VerifiedTransitionResult.action_source_snapshot` identifica el último source cuyo executor terminó normalmente; `recovery_after_action` impide fabricar un handoff desde cleanup. Geometría siempre del frame fresco. Retry específico, bounded, cancelable y autorizado para **esa** acción; no por sleeps, timeout o baja velocidad de percepción.

Verificar el efecto con señal fiable suficiente. Identidad de contexto se separa de datos económicos; postcondiciones no se convierten en revalidación de cada hecho GT. Landmarks y oclusión siguen GAMEPLAY_GT. Ausencia ambigua de popup no prueba por sí sola éxito o retorno limpio.

H&H se recupera sólo cuando bloquea una observación o un input; su mera presencia no provoca trabajo. `VerifiedTransition` entrega las ROIs de la señal necesaria fallida (también ante abort) o consulta el target real del executor. `PortalObstructionRecovery` sólo prueba si esa geometría intersecta el envelope de GAMEPLAY_GT y el contexto es compatible; nunca por timeout/UNKNOWN aislado. Un único dismiss requiere CONFIRMED fresco y una espera pasiva bounded/cancelable debe confirmar ABSENT; persistencia, evidencia inconclusa o frame stale propagan fallo técnico. El caller revalida su condición original con el snapshot fresco, conservando intención/caller. Inputs directos afectados pueden usar `VerifiedTransition.recover_input` y conservar su espera y cancelación; los no afectados no adquieren probes ni capturas adicionales.

H&H no es observación permanente: primero se decide el conflicto causal sin probe; una condición satisfecha no habilita probe por ROI. En entrada MW, los MODAL conocidos se normalizan antes de evaluar la BASE oculta o intentar H&H. El handoff local de entrada efectiva permite sólo el ACK establecido bajo UNKNOWN y, una vez sin MODAL, recovery causal del landmark MW ausente; véase [contrato MW](docs/MONSTER_WAVE_SKIP.md). CONFIRMED siempre conduce a dismiss; después se reevalúa la entrada desde el principio con evidencia fresca, sin repetir la entrada ni cambiar caller.

## Navegación y economía

Rutas concretas respetan caller/Back de GAMEPLAY_GT. El caller posee su retorno y la intención que reanuda; no hay navigation graph general. Quick Menu usa origen verificado; Lobby no es un hub obligatorio. Relieves vuelven al caller antes de otro cambio de BASE.

- El planner de recursos es puro; el board describe, cada capacidad decide/ejecuta dentro de su operación con facts frescos. El executor de ruta consume un plan, no replantea por su cuenta.
- Economic owners verifican identidad, cantidad, moneda, límites y efecto. No imputar saldos desde acciones previas. Karats no se gastan mediante fallback implícito; USER_GT Equipment autoriza explícitamente la siguiente fila +4 tras Combine y scan Sell sin candidato accesible.
- Equipment conserva request causal y Combine primero. Sell productivo aplica policy USER_GT y scan desde tail accesible fresco; cada Bulk confirma una vez y prueba Item Count decreciente. Sin candidato, expansión secuencial +4 con coste y efecto verificados. CV de bloques sólo descubre candidatos; panel/policy/popup siguen autorizando cada Bulk. Tras Bulk compatible se invalidan pixels/crops/templates/geometría y se transforman rangos lógicos protegidos por delta fresco; navegar a la región nueva sin reinspección innecesaria. Expansión, contexto/resort o delta contradictorio invalidan también ese modelo y restauran scan secuencial. Nunca retry destructivo inconcluso. Su existencia standalone no prueba wiring de un caller.
- Recovery vuelve a estado conocido; la sesión decide cómo continuar con el resultado. Los límites concretos de MW/Craft/Keys están en RESOURCE_ROUTING.

Configuración import-safe y explícita; paths/seriales locales fuera de código portable. Cleanup de source/proceso/socket/forward pertenece a su owner. No incorporar lifecycle frameworks, planners generales o abstracciones preventivas sin necesidad real conforme a AGENTS.

## AdsManager transversal

AdsManager no pertenece a Stages ni selecciona contenido publicitario. `AndroidAdsObserver` reúne pixels frescos y activity/window; el adapter despacha acciones Android/semánticas y el manager mantiene el lifecycle bounded. Stages es un caller: navegación/configuración/Mao permanecen concretos, y su success exige Results y Sapphire after > before. No se crea un framework general de stages.

- Activity/focus deben concordar. Package/activity son contexto, no prueba de reward ni de fase closable. Usar `dumpsys window` completo donde `windows` no aporta foco. Cada input fuerza screencap nativa fresca; no reinterpretar pixels SDK stale sobre main como permiso para otro Back. UI hierarchy actual sin affordances útiles es diagnóstico, no dependencia de cleanup.
- Chrome fijo SDK reward-ready permite cierre normal; CV de la barra SDK sólo prueba progreso, nunca autoriza un input. Movimiento ≥.01/reset conserva observación, con grace 15 s y límite absoluto 180 s multipart. No OCR ni reconocimiento de marca/contenido del anuncio.
- ~60 s es fallback sólo para estado desconocido/estancado sin progreso conocido. Back 1 → pixels/Android frescos → Back 2 únicamente si sigue ownership positivo ad/external. Main + superficie conocida detiene inputs inmediatamente; results tienen grace bounded 4 s. Nunca Back→Back a ciegas ni segundo Back dentro del juego. External package se recupera con Back bounded, sin CTA/install/permisos/compras.
- `AdsOutcome.RETURNED` señala retorno con results; **AD_COMPLETED** funcional sólo después de que el caller pruebe reward. `AD_ABORTED_RECOVERED` no es success ni supone reward/debit; el caller restaura estado y puede reintentar bounded. `UNAVAILABLE` por intento puede terminar en ADS_UNAVAILABLE/MANUAL_ENTRY_REQUIRED según policy del caller. `EXHAUSTED` corresponde a agotamiento explícito. `AD_RECOVERY_FAILED` sólo si no puede verificarse recuperación segura.
- Freshness y resultado inconcluso conservan los guards consumptivos. Policy concreta No Ads/same-character reset y prerequisites de Stages pertenecen a RESOURCE_ROUTING; límites físicos adquiridos a GAMEPLAY_GT.
