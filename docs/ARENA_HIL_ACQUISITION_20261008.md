# Arena — adquisición HIL 2026-10-08

Continuación B1: [owner standalone, validación y smoke](ARENA_B1_20261008.md).
Los hechos de esta adquisición y el gap de victorias CERRADO se conservan;
aceptación B1 se registra separadamente, sin transformar offline en LIVE_EVIDENCE.

Se observó un Auto Repeat natural EASY x8 completo: **104 Brawler Badges usados,
106→2**, aproximadamente **8 min 12 s**, con retorno verificado a Challenge.
Ambas vistas de Arena y las tres dificultades están adquiridas.

**Gap de victorias CERRADO por USER_GT de Fase A:** `Brawler's Badge Used`
acredita `used_tickets`; `Acquired Karats` acredita `won_tickets`: exactamente
un Karat por badge ganado y cero por badge perdido. No hace falta un campo Wins.
Batch adquirido: EASY x8, used104 / won104 / lost0 / winrate100%.
No usar puntos, saldo, resultados individuales ni dividir por ocho. Double Points
duplica sólo Victory Points, no Karats; no condiciona el reader.

Baseline `dd999288870e1afa02f061b4a9f3b830d89b0b03`, rama
`rebuild/stable-baseline`. Telumpel acreditado por USER_GT y New Ranking visible.
Un solo batch autorizado por steer, EASY x8 hasta 106 Badges, buffs 1/2 ON,
buff 3 OFF, sin Karats. Sin implementación productiva, commit ni push.

## A. Navegación y superficies

LIVE_EVIDENCE: Lobby → **Battle** → **Select Mode** → tarjeta Arena → selección
Beginner / Intermediate / Expert. USER_GT: Beginner=EASY izquierda,
Intermediate=NORMAL centro, Expert=HARD derecha; selección y Challenge son vistas
semánticas de la misma BASE Arena no-battle. Challenge no es MODAL/OVERLAY.
Cada Challenge muestra sólo el oponente y nombre de la dificultad elegida.

Adquiridas las tres vistas Challenge sin combate en NORMAL/HARD. Las tres
columnas ofrecieron Challenge; no apareció dificultad unavailable. Con 2 Badges,
Start y Auto Repeat conservan apariencia activa: color de botón no prueba
readiness económica. Back de Challenge devuelve selección, con Loading posible.
Al retornar tras el batch apareció New Ranking / OK, cerrado y selección limpia
verificada. El resultado no reapareció al entrar NORMAL/HARD; no prueba una
capacidad de reabrir historial ni persistencia fuera de esta ruta.

Quick Menu / retorno al caller externo todavía no acreditados. El intento QM
desde Challenge HARD falló **antes del primer input**, al perder ADB el teléfono.
Última pantalla acreditada: Challenge HARD limpio, no Lobby. No inferir que
Select Mode de Arena es el hub Survival ni su clase a partir del nombre técnico.

## B. Buffs y economía de selección

LIVE_EVIDENCE, antes del batch:

| Buff | Saldo inicial OFF | Al seleccionar ON | Coste mostrado |
| --- | ---: | ---: | --- |
| ATK Increase, +20% ATK | 923 | 915 | 3000 Gold |
| Thorns Aura, devuelve 20% daño | 999 | 991 | 5000 Gold |
| Double Points | 999 | sin seleccionar | 8 Karats |

Selected: check dorado grande superior izquierdo + borde iluminado; OFF sin
check y borde tenue. La reserva visible es de 8 unidades con x8 **antes de
combate**; selección no consume Badges. Buffs 1/2 permanecieron ON durante el
batch, relief manual y visitas posteriores a NORMAL/HARD.

Después del batch: 811/887 ON. Cleanup OFF devolvió 8 a cada contador:
**811→819**, **887→895**. Consumo neto desde OFF inicial: 104 unidades de cada
buff, concordante con Badges usados. Leer contador selected como disponible libre
sin considerar reserva perdería 8 unidades. La devolución está demostrada para
buffs 1/2; no extrapolarla automáticamente a Double Points.

USER_GT: buffs 1/2 siempre ON antes de ejecutar; compra Gold permitida con coste
fresco y confirmación acreditada. No hubo agotamiento ni compra en esta muestra;
confirmación de compra sigue sin adquirir y no se fabricó stock cero.

USER_GT Double Points: una unidad por Badge, no por combate x8. Activar sólo con
saldo conocido >= consumo previsto conocido. UNKNOWN mantiene OFF. Auto Repeat
puede comprarlo automáticamente con Karats al agotarse, y no se detiene por ese
agotamiento. Karats prohibidos. No se abrió ni confirmó compra del buff 3.
Mantener ON nunca basándose sólo en la presencia del icono o coste.

## C. x8 y previsión

x8 ya estaba ON (check dorado sobre x8 + iluminación) en la primera Challenge;
no se tocó conforme a USER_GT. Se mantuvo entre combates y al cambiar dificultad.
Memoria por personaje/cuenta no investigada. x2/x3/x5/x8 visibles.

USER_GT: cuando x8 no está seleccionado usar doble tap específico; tap aislado
abre pequeño overlay. Esa transición no se provocó porque x8 ya estaba ON.
El futuro flow observa selección actual y barrera de freshness después de cambio;
no trata doble tap como permiso para retries desde UNKNOWN.

Batch natural demostró **13 entradas x8 = 104 Badges**, saldo inicial 106,
residuo 2 sin entrada x2 automática. No selector de límite/entradas visible en
configuración. Para este caso se predijo sólo bound <=106; buff 3 quedó OFF.

Propuesta basada en este caso: con saldo fresco B, x8 verificado, repetición hasta
insuficiencia y sin otros consumos, prever `floor(B/8)*8`, no 80 constante. El
valor es previsión de batch máximo, no consumo real ni garantía de término normal
si aparece blocker/interrupción. Debe aceptarse este contrato antes de wiring.
Readiness x8 mínimo 8; un saldo 2 no autoriza entrada ni compra.

## D. Configuración, inicio y ejecución

Ruta física acreditada:

`Challenge → Auto Repeat → MODAL configuración → Auto Repeat verde interno → Loading → combate`

Upon Defeat ya vacío: no se tocó. Config muestra texto de repetición de dificultad
actual, término al agotar Badges y compra automática de items con Gold/Karats.
Hay X y un botón verde interno; sin número configurable de entradas visible.

**Corrección de USER_GT de ruta:** X devuelve Challenge, pero tocar su botón
Auto Repeat vuelve a abrir configuración. No inicia el batch. Se preservó la
primera divergencia y el usuario autorizó usar el botón verde **del modal**.

Primer inicio autorizado: bag full sobre configuración, Yes/No, saldo 106,
sin batalla. Literal “The bag is full. Would you like to organize your bag?”
coincide con el Socket blocker curado existente (`SOCKET_INVENTORY_FULL_PROMPT_SPEC`),
pero inventario intervenido manualmente no fue identificado por el usuario.
No prueba Equipment Full ni implementa relief nuevo. Usuario liberó espacio y
restauró Challenge; captura fresca verificó misma configuración y saldo.

Inicio efectivo acotado por before 20:32:43.978502 UTC y after Loading
20:32:44.431763 UTC. Sin segundo batch ni inputs mientras ejecutaba.
Secuencia natural repetida: Loading → Arena Battle con HUD versus, HP, timer,
pausa y banda `..Auto Repeat..` → WIN / Tap the screen → Challenge con próximo
oponente → nueva batalla. WIN observado desde preview; no se retuvo un PNG raw
limpio de ese transitorio. No tocar Tap the screen durante batch automático.

Challenge transitorio no es terminal. Oponentes cambiaron, Badges en pasos de 8,
buffs 1/2 continuaron ON. No contador fiable de entradas/remaining visible durante
batalla. Control de pausa visible: comportamiento de cancelación no probado;
no confundir pausa con cancelación segura. No derrota/desconexión de juego
observadas. No se forzó derrota ni se gastó para un Start standalone; su control
visible y semántica de una entrada provienen de USER_GT, transición independiente
no adquirida. Detector AutoBattle WB no acredita Auto Battle Arena.

## E. Resultado y consumo real

Resultado causal de este batch sobre Challenge:
**Auto Repeat/Auto Continue/SKIP Results**.

| Literal real | Valor nativo limpio | Interpretación |
| --- | ---: | --- |
| Brawler's Badge Used | 104 | used_tickets, Badges consumidos |
| Acquired Victory Points | 7,280 | no reader productivo de puntos propuesto |
| Acquired Karats | 104 | won_tickets, correspondencia directa USER_GT |
| Rewards | panel vacío | no campo wins/attempted |

104/8=13 entradas observadas, separado del resultado semántico en badges.
USER_GT definitivo: `won_tickets=104`, `used_tickets=104`, `lost_tickets=0`,
`winrate=1`. El result reader no expone wins/attempted ni usa divisibilidad como
autoridad. `Acquired Victory Points` no valida ni reconstruye won_tickets.

OK del resultado reveló MODAL **Insufficient Brawler's Badge / purchase? Yes-No**
sobre Challenge. No elegido: Challenge limpio con saldo 2. No se abrió compra.
Resultado persiste al menos desde primer raw final hasta OK manual, unos 115 s;
no se auto-cerró en esa ventana. No inferir persistencia tras navegación externa.

Gold fresco post-relief 6228489654 y final igual: **cero Gold del batch**.
Karats 100868→100972: **+104 netos**, sin compra. Gold pre-relief 6249097864
cambió durante intervención del usuario y se excluye de contabilidad Arena.
Badges 106→2, buffs OFF finales 819/895/999; consumos netos 104/104/0.

## F. Reader focal y autoridad

Inspección visual nativa es autoridad LIVE_EVIDENCE, OCR sólo prueba de viabilidad
sobre ese GT. Captura nativa 2712×1220; stream 2712×1224. ROIs normalizadas desde
cada shape, no copiar pixels absolutos.

| Señal/valor | ROI normalizada (l,t,r,b) | Resultado de probe offline |
| --- | --- | --- |
| título final | (.315,.195,.690,.242) | NCC positivo ~.956, negativos de batch <=.216 |
| label Badge Used | (.266,.322,.398,.357) | OCR literal, confianza .97928 |
| número used_tickets | (.443,.321,.480,.357) | OCR 104, .99999 |
| número Acquired Karats | (.448,.630,.483,.668) | OCR 104, .99998 |
| banda ejecución | aprox. (.405,.700,.597,.798) | visual; sin calibración productiva |

Título final es compartido con otros modos: combinarlo con label Badge Used y
lineage del batch/dificultad. Template para identidad estable + OCR focal entero
para valores, evitando mezcla de líneas. Fase A incorpora reader offline descrito
al final; esta sección conserva las medidas de adquisición.
ROIs del resultado dependen del panel físico superior: no aplicar blacklist de
CHAT/H&H automáticamente como a BASE; Fase A acredita el final como MODAL.
Config es MODAL por USER_GT; panel final,
insuficiencia y Ranking se observaron como diálogos superiores, parent dimmed,
con su propio cierre. Batalla candidata BASE battle_surface=true pendiente de
USER_GT específico si se necesita declararla en catálogo.

Probe OCR: primer número 2.741 s incluye carga lazy del engine; número siguiente
19 ms, label 25 ms. Una muestra limpia no valida variantes numéricas ni todos
los rangos. No usar cifras plausibles en frames corruptos como válidas. Guardar
`won_tickets` usa la relación física ahora cerrada por USER_GT, sin campo wins.

## G. Performance y estrategia de espera

553 observaciones de 1 s nominal, un source a 10 fps/2 Mb/s; 32 PNG raw
representativos (20 s o onset de ventana estática), preview mutable cada 5 s.
No OCR, ContextResolver ni input durante la observación. Stopfile y bound 1200 s;
cleanup final verificado a 556.485 s de lifetime del instrumento.

- Último raw de batalla: 20:40:39.699374 UTC, seq4821.
- Primer raw final: 20:40:58.750833 UTC, seq5019.
- Duración verificable desde input hasta final: aproximadamente **475–495 s**.
- HEURISTIC temporal: salto de thumbnail a pantalla estable a 20:40:55.751203
  UTC, seq4989; luego diferencias ~.00002. Estimación **8 min 12 s**; los frames
  del salto no se conservaron y diferencia sola no identifica contexto. No afirmar
  instante exacto. La adquisición deja explícita esa incertidumbre.
- Intervalos entre próximas Challenge conservadas sugieren ~35–40 s por entrada;
  promedio de batch ~38 s/entrada incluye loading/result/retorno, no sólo combate.

| Coste/señal medido | p50 | p95 | máximo |
| --- | ---: | ---: | ---: |
| get_frame copia | 0 ms cuantizado | 16 ms | 16 ms |
| thumbnail grayscale | 0 ms cuantizado | 16 ms | 16 ms |
| escritura/hash PNG retenido | 125 ms | 141 ms | 156 ms |
| age de frame | 75 ms | 125 ms | 265 ms |

Clock monotonic local tiene resolución **15.625 ms**: cero no significa coste
cero y no permite ranking sub-ms. Captura nativa final medida con perf_counter:
1.305 s. Medidas de copia no incluyen coste permanente de decode/ADB ni uso CPU;
no comparar 0 ms de copia con 1.305 s de captura como coste total de sources.

Recomendación futura: `ControlledWait` cancelable con sondeo focal del **resultado
final** cada 2–5 s como punto de partida (latencia acotada), plazo de seguridad
configurable y freshness real. No dormir ocho minutos ni resolver pantalla
completa cada segundo. Banda Auto Repeat sirve como evidencia positiva en combate,
pero su ausencia durante Challenge/WIN no demuestra fin. Identidad final positiva
habilita snapshot fresco y OCR de campos una vez; si stream presenta artefactos,
refresh nativo antes de aceptar cifras. Resultado permaneció hasta ACK manual,
por lo que no requiere capturarlo a frecuencia de combate.

2–5 s es propuesta basada en ciclo ~38 s y persistencia terminal, no benchmark
comparativo ni garantía para todos los personajes. Cancelación del wait no equivale
a cancelar físicamente el juego: usuario/owner debe gestionar batch activo.

## H. Corpus

[Manifest](../datasets/arena_hil_20261008_manifest.json). Raw local
`artifacts/arena-hil/20261008/`; curado `screencaps/arena_hil/20261008/`.
Mantiene adquisición parcial original y añade antes/después, configuración,
blocker, batch, resultado nativo, cierres, NORMAL/HARD y devolución de reservas.
Timestamp UTC, source, shape, sequence por lifetime, hashes raw/curados,
configuración/GT y positivos/negativos explícitos. Telemetría en JSONL, resumen
offline y OCR probe separados; preview mutable/contact sheets no son raw GT.

Frame con WhatsApp descartado a pedido: PNG y registro eliminados, sin curado.
Artefactos H264 posteriores guardados como ambiguos relevantes, no números GT.
Resultado nativo y fresh stream reiniciado sirven como positivos limpios; finales
parciales/corruptos como ejemplos que no deben autorizar lectura. Positivos
numéricos sólo 104; sin fabricar derrota/0 ni otros tamaños.

## I. Owners mínimos futuros

IMPLEMENTATION_CONTRACT revisado: `BattleModeZone/OpenBattleModeSelect` abre
**Survival**, parent WB/MW; Arena entra por **Battle** a otro Select Mode.
Reutilizar executor/VerifiedTransition/QuickMenu sólo donde ruta, guards y targets
estén acreditados; no forzar el hub existente ni una arquitectura nueva.

- ArenaFlow(SINGLE_BATTLE): navegación caller-owned, vista Challenge+dificultad,
  buffs 1/2, policy buff3 y x8, una entrada autorizada, resultado y retorno.
  Transición Start standalone sigue pendiente; no trasladar WB automáticamente.
- ArenaFlow(AUTO_REPEAT): misma preparación, configuración Upon Defeat OFF,
  inicio interno modal, **un batch por invocación**, wait focal, terminal fresco,
  cierre resultado y No de insuficiencia cuando corresponda. Challenge no terminal.
- Reader final local implementado en Fase A: used_tickets entero >0,
  won_tickets entero en0..used, dificultad/x8 conocidos por ejecución, lineage,
  integridad/freshness y valores del mismo frame. No attempted/wins ni puntos.
- Controller futuro consume resultados acreditados recientes, dificultad,
  used_tickets/won_tickets y recursos; no puntos ni winrates históricos estacionarios.
  Excepciones Hard/Easy 0% requieren used>=80 y batch válido; Easy corta ciclo
  funcional, no FAILED técnico ni otros flows/lifecycle Meteorites.
- ReliefCoordinator en `bot/relief_policy.py` delega permisos, no deduce presión
  ni navegación/retries. Arena caller conserva evidencia y return plan local;
  `EquipmentReliefRequest`/Socket owners se componen si blocker propio acreditado.
- Session/Arena Farming Cycle posterior posee repetición resource-driven y
  integración MW/Manual Stage. Arena no se acopla a Rotation ni Meteorites.

## J. Gaps y cierre físico

Gap Karats→won_tickets CERRADO. Pendientes: derrota y su consumo observado;
Start standalone y Auto Battle independiente; cancelación/pausa; compra buffs
Gold agotados; selección doble tap x8 desde OFF (USER_GT suficiente para ruta,
sin muestra propia); Quick Menu, Back externo/return-to-origin y declaración
física de Select Mode/Arena Battle. Modal informativo de umbral de puntos:
existencia/clase MODAL por USER_GT adicional; título, umbral y cierre UNKNOWN.
Adquirir naturalmente, sin detector inventado ni taps ciegos. No necesitan otro batch
para cerrar lo ya acreditado. No inventar disabled, límites o interrupciones.

Último estado acreditado 20:48:36 UTC: **Challenge HARD, sin modal ni batalla,
Badges 2, x8 ON, tres buffs OFF, 819/895/999**, Gold 6228489654, Karats100972.
Teléfono luego no encontrado por ADB; último intento QM no envió input.
Captura/source/proceso/socket/forward propios cerrados; ADB compartido no matado.

Cambios propios de adquisición: GAMEPLAY_GT, este informe, manifest, tooling aislado
`tools/arena_hil_observe.py`, raw/curados locales. Runtime/GUI sin cambios propios.
Trabajo independiente inicial en CONTEXT/runtime/tests/scripts preservado.
Validación de adquisición (previa a Fase A): diff/formato, integridad de manifest/hashes y probe OCR
focal offline; sin pytest ni evaluator productivo por no invalidación de código.

## K. Fase A — semántica, percepción y result reader

Implementados `bot/arena_semantics.py` (facts/contratos), `bot/arena_reader.py`
(ArenaVisuals/Detector/ResultReader) y catálogo/default/scopes preservadores de
contexto. Selección y Challenge comparten BASE Arena; configuración, resultado,
Insufficient Badge y New Ranking conservan MODAL. No hay navegación productiva
Arena ni wiring dentro del hub Survival. El botón verde adquirido de inicio está
dentro de configuración; X cierra sin iniciar. Upon Defeat OFF está acreditado;
un estado no adquirido devuelve UNKNOWN. Batalla sólo emite actividad positiva
con versus+banda, sin inventar clase BASE ni usar ausencia como término.

Autoridad terminal: título compartido + labels específicos **Brawler's Badge Used**
y **Acquired Karats** + estructura/OK. New Ranking requiere además label Arena
completo, evitando los tres falsos positivos iniciales sobre ranking MW. Los
ROIs del corpus tienen variantes de shape nativo/stream; matching local con margen
de posición conserva su geometría relativa. Banda activa usa glyphs amarillos
focales; el background transparente y borde animado no son autoridad.

`ArenaBatchResult` contiene difficulty, multiplier, used_tickets, won_tickets,
observed_at y provenance (run/source lifetime, secuencia, hash pixels, confianzas,
relación USER_GT). Enteros used>0 y0≤won≤used; winrate/lost derivados. No wins,
attempted, Victory Points, saldo Karats ni dependencia de Double Points.
El caller aporta `ArenaBatchExecution` de un único inicio verde efectivo con
post-start positivo, configuración conocida y barreras de tiempo/secuencia. La
percepción del final no fabrica ese receipt. Source/run ajenos, inicio no
verificado, configuración desconocida y frame stale/futuro no producen resultado.
Futuro owner debe invalidar receipt ante otro batch, cancelación o discontinuidad;
ese owner productivo no se implementa en esta fase.

Lectura de los dos valores desde una sola copia de pixels. OCR focal color/gris
concordante, una línea, confianza≥.95 y gramática estricta; cero explícito válido,
missing/garbled nunca cero. Sin acumulación de campos entre frames. Integridad de
padding numérico en color absoluto: un recorte negro podía dejar `10` con OCR
alto; se rechaza antes de OCR, sin aceptar plausibilidad. H264 finales parciales
fallan label Karats y tampoco llegan a OCR. Freshness se comprueba de nuevo al
terminar; lazy load no extiende el budget2s. UNKNOWN permite nueva observación
fresca o refresh nativo existente, sin input económico ni rescate de cifras.

`wait_terminal` es interfaz pasiva basada en ControlledWait: bound obligatorio,
cancelación y sondeo focal3s inicial, sin OCR ni resolver global continuo; devuelve
snapshot terminal positivo. No espera fija8min ni ejecución productiva. Cancelar
observación no prueba cancelación física. Challenge/WIN/banda ausente no terminan
el wait. No se ejecutó un batch para probarlo.

Economía sólo preparada: previsión candidata `(Badges//8)*8` (106→104+2), no
garantía ante blockers/interrupciones. Buffs1/2 siempre ON por USER_GT, Gold sólo
bajo verificación económica futura. Buff3 necesita cobertura conocida del consumo
previsto, distinguiendo saldo libre y reserva acreditada; nunca Karats. No se
extrapola su refund desde buffs1/2. x8 ya activo no se toca; doble tap específico
conserva USER_GT para futura selección. No inputs ni policy productiva aquí.

32 assets hash-verificables (~409KB) y24 fixtures portables (~5.1MB):21 derivados
del corpus,3 numéricos **SYNTHETIC**. Canvas de ROIs y márgenes a media escala;
pixels fuera del contrato se omiten. No raw/artifacts ignorados requeridos por
pytest o evaluator por defecto. Manifest conserva fuente y hash original,
transformación y ausencia de autoridad física de los sintéticos. Buff3 ON reutiliza
check adquirido de buff1; x8 OFF reutiliza marcador unchecked de x5: composición
visual/synthetic testing, sin adquirir activación buff3 ni transición x8 OFF.

Validación: **376 tests afectados verdes**, incluidos57 Arena; después de compactar
fixtures sólo se repitieron los57 invalidados. OCR real:104/104 nativo y dos streams,
104/72 y104/0 sintéticos;104/105 rechazado. Contratos cubren missing, confusión,
multilínea, daños parciales, mezcla entre frames/preprocessing, configuración
desconocida, stale/futuro/barreras, cancelación y agotamiento de freshness en OCR.
Evaluator incremental: **104/104** (24portables +80adquiridos) y **513/513**
negativos existentes, incluidos otros modos. Última pasada:80+513 cache hits,
24 pares recalculados por compactación; cero errores. Un frame de batalla marcado
clean tenía banda H264 corrupta (frame2878); se corrigió esa anotación de integridad,
conservando contexto físico. Frames corruptos no tienen obligación de emitir
actividad positiva ni autorizan lectura numérica.

Comandos desde raíz: `./tools/agent_run.ps1 tools.arena_evaluation` usa fixtures
portables; `--acquired --existing-negatives` añade corpus curado local y negativos
confirmados. `tools.arena_phase_a_assets` reproduce assets/fixtures desde curado,
sin teléfono y fallando si falta fuente/hash. Reports de validación/coste locales
en `artifacts/arena_phase_a/`; no se versionan.

Coste offline medido con perf_counter (última pasada, carga de tests concurrente,
no garantía live): probe CV terminal104samples p50 **2.12ms**, p95 **4.37ms**,
máximo8.23ms (incluye negativos con short-circuit). Reader caliente9lecturas de
cuatro OCR: p50 **129.64ms**, p95 **352.30ms**, máximo430.43ms. OCR caliente39calls:
p50 **29.37ms**, p95 **55.37ms**, máximo178.22ms. Primer OCR lazy3.219s y reader
frío3.431s; corridas anteriores observaron reader frío2.33–2.65s. Esto puede
agotar freshness2s: rechazar y readquirir, sin extender edad. Detector semántico
completo,5probes por superficie adquirida: Challenge59.7–76.9ms, configuración
51.3–73.5ms, final27.7–69.4ms; el wait no ejecuta ese detector completo. No se
incluyen costes permanentes de decode/ADB, captura nativa ni uso CPU de sources.

No smoke/hardware/ADB en Fase A. Estado físico sólo el último adquirido descrito
en J, sin asumir reconexión: HARD limpio,2Badges, x8ON, buffsOFF. Worktree principal
`D:/PROYECTOS/kritika-farmbot`, rama `rebuild/stable-baseline`, HEAD baseline
dd999288870e1afa02f061b4a9f3b830d89b0b03. Trabajo independiente preservado;
sin commit/push. Cancelación, Quick Menu, Start standalone y modal de umbral de
puntos siguen abiertos. No ArenaFlow productivo, Farming Cycle, adaptive controller,
Manual Stages ni REPEAT_CURRENT; no siguiente frente automático.
