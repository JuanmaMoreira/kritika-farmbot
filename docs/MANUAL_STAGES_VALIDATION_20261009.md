# Manual Stages — implementación y validación 2026-10-09

Baseline/HEAD `c607b601b9ba79d49ec0261e3dd5d475b94aea46`, rama
`rebuild/stable-baseline`. Sin commit/push. Manual Stages está conectado a la
tercera rama del único paso Arena Farming Cycle. Las correcciones USER_GT de esta
sesión prevalecen: Chaos06 en **Hell**, Support obligatorio, capacidad Sapphire
disponible y buffs1/2 sin lectura de contadores.

## Contrato entregado

1. **Selección:** Burst Breaker/Berserker/Demon Blade/Kaiserin→Abyssal Rion09,
   Penance. Otro personaje→09 sólo con set completo acreditado; de lo contrario
   Chaos06, Hell. Stage08 queda exclusivamente en Ads.
2. **Autoridad de meteoritos:** `MeteoritesCharacterScope.full_set_equipped_verified`
   consume READY, identidad coincidente, phase equipped, once efectos ordenados,
   sin pending/released ni excepción. SharedMeteoritesProcedure acredita cada
   slot por efecto físico del set2; el flag de configuración no es autoridad.
   Session expone el scope durante los pasos y conserva setup/cleanup propios.
3. **Navegación/x4:** navegación Stages existente, World Map/episodio/Claim;
   Chaos adquirido como episodio de una estrella, dos antes de Rion. Un único
   punto de x4 en BASE aprovecha la observación posterior a Claim: ON se conserva,
   OFF usa doble tap adquirido y verifica efecto. UNKNOWN no autoriza input.
   El primer MODAL también muestra x4, pero no se vuelve a comprobar allí.
4. **Preparación:** Penance/Hell y cuatro buffs con estado conocido/effect fresco.
   Buffs1/2 sólo ON, sin OCR de contadores; buff3 exige ticket para activarse.
   Buff4 se activa sólo con un ticket seguro o conserva reserva ON acreditada;
   contador ambiguo/insuficiente→OFF. Nunca Karats. Cada buff observado reservó
   un ticket por entrada x4, no cuatro. MaoSupport reutiliza NEEDS→Fill All→READY→
   activar→ACTIVE del owner Ads; ACTIVE se conserva y se revalida tras relief.
5. **Dos Start:** primer MODAL→Select Striker; su Start→una batalla. No Auto
   Repeat. Guard/effect distintos; Start incierto no se repite. Equipment/Socket
   Full reutilizan reliefs transversales y contratos de retorno. Sólo blocker
   fresco que acredita rechazo permite retomar Start, después de restaurar BASE,
   x4, objetivo, dificultad, Support y buffs.
6. **Auto:** botón rojo en ambos estados; destellos laterales acreditan ON. Se
   usa Pause + Auto adquiridos en esta superficie, con ventana focal de2s.
   OFF→tap único→ON verificado; ON conservado; UNKNOWN corta sin wait normal.
   Se corrigió el falso ON de Monk causado por incluir el bisel metálico fijo.
7. **Wait/terminal:** pausa cancelable30s, polling ligero1.5s y bound adicional120s,
   sólo frames frescos/CV focal, cero OCR/resolver global. Clear Time + Home
   acredita `overlay.manual_stage_clear` sobre la BASE de batalla; Loading y
   combate activo no son terminales. Timeout no declara victoria.
8. **Salida:** Clear Time→Home→Lobby limpio. Home temprano sin efecto admite un
   único retry después de timeout únicamente con un nuevo Clear Time expuesto
   posterior al input. UNKNOWN/Loading no autorizan retry. Muerte Revive/Abandon→
   Abandon→Get stronger→X→Lobby; timeout también puede mostrar Get stronger.
9. **Economía:** Stamina≥60 y Sapphire<capacidad mediante StageBalances fresco,
   sin compra/recarga. Después de Lobby se leen valores frescos y se distingue
   rewarded/no_progress/defeated/stamina_insufficient/sapphire_capacity_full de
   ambigüedad, cancelación y fallo técnico. No recompensa fija ni reinicio incierto.
10. **Coordinación:** defaults40Badges/100Sapphires, thresholds por ocurrencia,
    prioridad Arena→MW→Manual cuando ambos son insuficientes. Cada operación
    completada vuelve a la autoridad nativa de recursos antes de decidir otra.
    Progreso Manual requiere Sapphire, no sólo Badges. Stamina insuficiente,
    capacidad llena, derrota/no progreso terminan funcionalmente sin bucles.
    Session continúa sus pasos; cleanup sólo al final del personaje. Controlador
    adaptativo, Rotation y único paso GUI conservados. Sin REPEAT_CURRENT.

## Evidencia física y costes

| Entrada | Stamina medida | Sapphires | Resultado |
| --- | --- | --- | --- |
| Mystic Wolf Guardian, Chaos06 Penance inicial |61→1|59→59|Derrota; Abandon y segundo MODAL X adquiridos. Configuración inicial sustituida por Hell. |
| Monk, Chaos06 Hell, detector anterior |111→51|21→21|Timeout con AutoOFF confirmado por USER_GT; negativo de regresión. |
| Burst Breaker, primer Rion09 Penance |151 pre-entrada→92 Lobby, con regeneración durante espera|129→129|Clear Time124s, overlay90; capacidad llena impidió ganancia. Ahora esa entrada queda bloqueada por precondición. |
| Burst Breaker, Rion09 productivo |96 Lobby antes de navegación; x4=60 visible|29→71|Clear Time63s, recompensa42. Home posterior guardado cerró resultado; el primer smoke preservó ambigüedad al no verificar Lobby. |
| Blade Dancer sin set, Chaos06 Hell final |89 Lobby→Claim119 pre-Start→59 Lobby|28→68|Coste real60 y recompensa40. Clear Time31s; wait37.750s/6polls/ceroOCR. Socket relief, una entrada y Session COMPLETED. |

El delta neto89→59 incluye **30 Stamina de Claim**: no es coste30. X4 muestra
15/30/45/60 y Start60. Una entrada cuesta60 en las configuraciones adquiridas.
Buff4: stock97→seleccionado96→post-entrada96 en Rion; no débito adicional al
Start. No se extrapola la economía Double Points de Arena ni una recompensa
Sapphire universal. Karats se mantuvo106017 en la entrada final.

Smoke final real:
[resultado](../artifacts/manual_stages/cycle_hell_support_final/result.json),
[eventos](../artifacts/manual_stages/cycle_hell_support_final/events.jsonl),
[preparación Hell/x4/Support](../artifacts/manual_stages/cycle_hell_support_final/manual_prepared.png),
[Clear Time](../artifacts/manual_stages/cycle_hell_support_final/manual_clear.png),
[Lobby final](../artifacts/manual_stages/cycle_hell_support_final/physical_final.png).
El threshold Badge107 del smoke fuerza la rama Manual con saldo106; defaults
productivos40/100 permanecen. El bound2 permitió un owner productivo y luego
`stamina_insufficient` con59, **sin segundo Start**. El paso Lobby siguiente y
Session completaron, operación física activa=false.

La selección de tarjeta Kaiserin se corrigió tras identidad fiable; aquel smoke
se canceló ante blocker antes de la entrada consumptiva. No se reinterpretó como
prueba Hell ni victoria. Smokes anteriores y adquisiciones fallidas están
preservados; no se vuelven success por inferencia.

## Validación dirigida

11. **Tests/evaluator:** selección fuerte/set completo/parcial/ausente/identidad,
    Stamina59/60/capacidad, x4ON/OFF/UNKNOWN/un único punto, Penance/Hell,
    buffs/Support, Start diferenciados/uncertidumbre, relief/readiness,
    Auto/Loading/terminal/Home/derrota/cancelación, routing/bounds/progreso y
    continuación Session/lifecycle cubiertos por tests dirigidos.
    Batches afectados PASS (solapados):253 Arena/Manual/cycle/settings;
    79 Manual/navegación;116 Session/Meteorites/MW/resources/replay;
    83 AdsStages/socket/controller/settings. Fix de fixture Gold y nuevos tests
    Home/Support se reejecutaron sólo en los casos invalidados: todos PASS.
    Regresiones StageAds/retorno/scope anteriores264PASS reutilizadas.
    Evaluator Manual **20/20**, última ampliación18reusados/2nuevos; Arena
    recursos **9/9**. Fixtures portables de Auto/Clear/muerte pasan sin teléfono.
    `.pytest_cache` tiene un warning ambiental de acceso; ejecución posterior
    usó `-p no:cacheprovider` y basetemp local. No suite ni campaña28/28.

    [Manifest curado](../datasets/manual_stages_20261009_manifest.json),
    [fixtures portables](../tests/fixtures/manual_stages_controls/manifest.json),
    [evaluator](../artifacts/manual_stages/evaluation/report.json).
    Raw/corpus grande permanecen ignorados en artifacts/screencaps; sólo assets
    runtime, manifest y fixtures pequeños forman parte del cambio revisable.

## Límites y cierre

12. **Límites:** la cadena continua nueva Manual→MW→Arena no se ejecutó live
    completa: el smoke final terminó correctamente por Stamina59. El routing
    completo está probado offline; MW/Arena mantienen sus smokes previos
    acreditados (MW100→0Sapphires/7→106Badges y Arena Hard112/112 continuo).
    Support inactive reutiliza el owner físico Ads cerrado, con nuevos tests de
    wiring; no se forzó expiración. Set completo se consume del lifecycle B1 y
    se probó con Session, sin otra campaña de reequipamiento. Persisten deudas
    Arena ajenas: derrota Single, modal de umbral, cancelación física y economía
    de agotamiento Gold; no bloquean activación ON autorizada por USER_GT.
13. **Estado final:** Blade Dancer en Lobby limpio; último saldo verificado
    59/440Stamina,68/102Sapphires,106/106Badges, Gold8710437190,
    Karats106017. Runtime/sources/sockets/forwards de la adquisición cerrados;
    ningún combate quedó activo. HEAD y rama originales intactos, sin staging,
    commit/push; Arena no publicado y cambios independientes Ads/MW/Sell/Summon,
    documentación/herramientas y demás worktree preservados. No otro frente.
