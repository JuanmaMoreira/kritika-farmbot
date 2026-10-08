# Meteorites — adquisición HIL 2026-10-08

Se acreditaron accesos directo/QM, cinco tabs, tres sets, reentrada independiente
de tab/página, y **3 Equip + 3 Unequip individuales** sobre `rang`. Ancla 25 estable
en los dos normales probados. Estado restaurado: compartidos usados desequipados,
Set 1 activo con sus 11 originales, Meteorites/página 1. No hay flow, coordinator,
GUI, algoritmo completo, commit ni push. Worktree independiente desde
`ce44fe55ef0490e068f972b59e96c1e9a3c58350`; checkout original preservado.

## 1. BASE/navigation

**USER_GT:** BASE autónoma no-battle; Lobby directo y QM; entrada siempre tab
Meteorites/página 1; set recordado por personaje. Tabs/página/set independientes.
**LIVE_EVIDENCE:** captura `02` entró directamente en Set 1; `03` Set 2 vacío;
`24` Set 3 vacío. `27–30` adquirieron Combine/Evolve/Reforge/Reroll sin modificar
items. `31` dejó Reroll/página 2; `32→33` Back llevó a Lobby; `34→35` QM Meteorites
restableció main/página 1 y conservó Set 3. No demuestra persistencia durante
rotación, que ya queda cerrada por USER_GT. Flechas/paginador adquiridos: 1/40 y
2/40; no equiparar ese denominador con número de páginas llenas.

Geometría normalizada del frame scrcpy, sólo evidencia de hitboxes ejercitados:
Lobby Meteorites (.925,.755); tile QM en layout Lobby (.076,.496); sets
(.215/.268/.320,.282); next/previous (.730/.630,.910); Back (.802,.073).
No promover el tile Lobby a layout shifted sin medir geometría correspondiente.
Cierre detail por fondo vacío (.89,.30) acreditado. Captura nativa 2712×1220;
stream 2712×1224. La discrepancia abortó `01` antes del input: fuentes separadas,
geometría siempre desde frame.shape, nunca reinterpretar bytes con otro tamaño.

## 2. Bag ordering

**USER_GT:** 16/página; equipados en algún set → Flare desequipados → normales
desequipados; tier y nivel dentro del grupo. Precondiciones asumidas, sin cinco
verificadores, en [GAMEPLAY_GT](GAMEPLAY_GT.md#meteorites--user_gt-y-adquisición-2026-10-08).
Excepciones completas: `berserker`, `demon_blade`, `kaiserin`; `burst_breaker` incluido.

**LIVE_EVIDENCE:** originales 1–11; Flare desequipados 12–15; normales desde 16.
Flare compartido Ethereal+ +30 estuvo en 12 y pasó a 1 con Equip. Ancla inicial
**16+9=25**, índice absoluto uno-based, página 2/celda 9. `10/13/16` muestran:
Evasion +20 → Shield +21 → normal negro +21. Los dos primeros Equip mantienen
al siguiente objetivo en 25. La frontera normal avanza 16→17→18: recalcular
frontera+9 durante el loop cambiaría el algoritmo. Conservar ancla inicial.
No se probaron diez Equip ni otros inventarios; sin contradicción posicional
observada. Se registra la muestra, sin universalizarla.

## 3. Overlay y señales visuales

Título focal completo: `Ethereal+ Meteorite Flare (ATK) +30`, `(Evasion) +20`,
`(Shield) +21`. ROI explorada alrededor de (.284,.255,.495,.287).
**Matiz físico respecto a la descripción general del nombre:** en nivel cero no
hay `+0` en el título; la barra inferior sí muestra +0 en Concentration E+ y
Flare Ethereal (`25/36`). Ausencia por OCR degradado no prueba cero. Stats y
nombres de skills no identifican beneficiario ni importan para preparación.

Equip/Unequip se reconoce por el **control lateral superior**, flecha derecha/
izquierda y texto correspondiente. El botón inferior azul con candado también
puede decir Unequip: USER_GT confirma que gestiona lock y debe ignorarse.
`Equipped Item` acompaña los samples equipados en set activo. La línea
`Equipped: DRAKEN四R` también aparece con originales de otro set que ofrecen Equip.
E verde es relativa al set activo; su ausencia no prueba desequipado global.
USER_GT permite el mismo item en múltiples sets; fuera del uso futuro autorizado.

Ethereal y E+ usan título rojo. El marco E+ tiene ornamento dorado adicional;
Ethereal simple, marco rojo sin él. Flare conserva su sprite entre ambos.
Hay 12 tipos por USER_GT; se ven 10 glyphs normales y Flare, sin catálogo completo
nominal de los doce. Sprite sirve para tipo; marco para tier, sin usar color rojo
como clasificación E+ suficiente. Selección: contorno amarillo en Bag.

**Comparación offline, exploratoria:** un template fijo mal alineado produjo
NCC Flare .34–1.00 BGR y .42–1.00 gray; con pequeña búsqueda local, .78–1.00 BGR
/.886–1.00 gray, frente a normales ≤.398 BGR/≤.503 gray en ese frame. Esto favorece
sprite/core alineado y grayscale para discovery, pero no calibra threshold de
producción. Fases del mismo Flare durante `38`: gray NCC .815–1.00. La animación
diagonal de glare cambia correlación; usar core sin frame/badges y referencias
de distintas fases. `+30` alterna con MAX; un guard de celda completa falló .828
por esa fase (`07`, cero input). Nunca requerir igualdad del superíndice.

OCR focal leyó correctamente ambos preprocesamientos en estos ejemplos. Títulos
warm: 31–63 ms, mediana 47 ms (8 llamadas); barras/controles, 15–31 ms. Cold start
2.38/2.80 s en dos procesos: precargar el engine fuera del tramo de acción.
18 OCR offline en total, **cero OCR durante los inputs**. No evidencia para
rechazar OCR ni para convertirlo en gate decorativo de BASE.

## 4. Effects

`09/12/15`: Equip ocupó exactamente centro/slot Evasion/slot Shield, agregó E,
movió item al prefix equipado, cerró overlay y volvió a página 1 tras Loading.
`19/21/23`: Unequip desde primera posición 1 tomó Flare/Shield/Evasion;
respectivo slot vacío, E retirada y Bag reordenado acreditaron cada operación.
En el caso adquirido, los compartidos mejorados precedieron originales de otros
sets. No asumir posición 1 universal sin esas precondiciones y selección verificada.

Loading conserva pantalla anterior, Bag/página/slots anteriores. Cerrar overlay
no es éxito; tampoco tick de set nuevo sin slots ya cargados (`38/frame_017`).
Equip desde página 2 mantuvo 2/40 durante Loading y regresó a 1 sólo con el efecto.
Un slot/E inequívoco puede acreditar efecto; comprobar readiness cuando Loading
siga bloqueando el próximo input. No convertir estados transitorios en no-efecto.

CP no es autoridad: Flare en set vacío no lo cambia (USER_GT, observado); durante
Unequip con otros items el HUD puede actualizar después. Toast CP/glare pueden
persistir con Bag semánticamente listo. En `38/last` se restauraron slots y CP inicial.

## 5. Timings y Equipment Sell

PTS del stream mapeados al reloj monotonic host, tap timestamp antes del comando
ADB. Incluyen transporte/input y posible coste del stream; no aíslan internals
del juego. Intervalos: último sample aún anterior → primero con efecto completo.
Overlay listo fue revisado visualmente; NCC de título sólo localizó ese frame.

| Operación | Selección→overlay s | Tap→efecto completo s | Suma latencias s | Wall HIL selección→efecto s | Capturas selección + acción |
| --- | ---: | --- | ---: | ---: | --- |
| Equip Flare (ATK) +30 | 0.157 | (0.953, 1.047] | 1.204 | 20.063 | 13 + 29 |
| Equip Evasion +20 | 0.218 | (1.125, 1.219] | 1.437 | 21.156 | 12 + 27 |
| Equip Shield +21 | 0.203 | (0.922, 1.031] | 1.234 | 23.250 | 10 + 24 |
| Unequip Flare (ATK) +30 | 0.141 | (0.985, 1.063] | 1.204 | 19.282 | 10 + 26 |
| Unequip Shield +21 | 0.157 | (0.390, 0.453] | 0.610 | 19.110 | 11 + 26 |
| Unequip Evasion +20 | 0.234 | (0.422, 0.500] | 0.734 | 21.687 | 10 + 26 |

En seis muestras: overlay mediana .180 s, rango .141–.234; efecto mediana 1.039 s,
rango .453–1.219. Los primeros efectos completos también mostraron Bag reordenado,
página correcta y Loading ausente: efecto→Bag listo indistinguible de cero al
muestreo, **no prueba 0 ms físico**. Gaps vecinos de efecto, 63–109 ms. Sin p95:
seis operaciones heterogéneas no justifican una cola estadística.

Wall HIL mediana 20.609 s, rango 19.110–23.250: incluye revisión humana/modelo,
guard, arranque/cleanup de cada source y guardado PNG. Suma de latencias activas
.610–1.437 s es una suma de muestras separadas, **no** benchmark productivo continuo.
La captura nativa inicial sola tardó 2.156 s. Guardar PNG inicialmente costaba
.188–.297 s/frame; se movió fuera del muestreo. Stream hasta 30 fps, observación
pasiva con pausa 50 ms y cero OCR en espera; no trasladar este presupuesto de
corpus al loop productivo. Por operación: 2 checks CV de continuidad, revisión
visual de panel/efecto, capturas de la tabla; las muchas percepciones offline no
forman parte de la latencia del juego.

Inspección del baseline y diferencias locales del checkout original: no se adoptó
el reader local modificado ni se cambió código productivo. Equipment Sell reutilizable:
`_SelectedSalePanel`, `_inspect`, `_selected_panel_current`: candidato, selección,
frame e input lineage; fast path de continuidad y relectura semántica si se pierde.
`_tap` pone barrera temporal/secuencia e invalida selección previa. `_read_consensus`
examina sólo frames posteriores/frescos, con cancelación, bounds y reader focal.
`execute_equipment_sell` confirma una vez; decremento fresco de Item Count acredita
Sell. Meteorites necesita slot/E/reordenamiento, sin popup Bulk ni count decrement.
Sell consume dos muestras para sus facts; no copiar esa cuota ni 4 s/50 ms/48 frames
por analogía. **El runtime Sell no hace retry de input**: resultado fallido no
reautoriza confirm. Retries del caller tras relief son otra frontera.

## 6. Recovery

No hubo Equip/Unequip sin efecto explícito ni retry. `01/05/07` son guard aborts
antes de tap; `05` no conserva before.png por una limitación inicial del recorder;
`06` recapturó Bag sin input. La persistencia de Loading no es no-efecto acreditado.
USER_GT describe workaround seleccionar otro y volver al ancla; preservado,
sin ejercicio ni implementación. Ante resultado ambiguo, observar/reconciliar
slot/E/overlay sin input; no repetir una acción potencialmente consumada.
Una futura recuperación tendría que vincular item/set/página frescos, acreditar
no-efecto, reautorizar un único retry seguro, mantener bounds/cancelación y volver
a acreditar el efecto. No crear recovery genérico ni ampliarlo desde timeout.

## 7. Acquisition gaps

Faltan: un sprite entre los doce y nombres de la mayoría de glyphs; tiers inferiores
etiquetados (hay marco azul en Combine/Evolve, sin lectura de tier); estados disabled
de Equip/Unequip; episodio real de no-efecto; otros inventarios para ampliar el
límite experimental del ancla. USER_GT ya cierra persistencia por personaje y
pertenencia múltiple: no requieren campañas nuevas para el futuro flow.

No queda intervención del usuario necesaria para este alcance. Si el diseño
necesita cubrir esos negativos, el usuario podrá preparar un ejemplo del tier/tipo
faltante o avisar un no-efecto natural, **una condición a la vez**. No provocar un
fallo ni equipar los once sólo para cuota. Sin adquisición transversal nueva de
oclusores; respetar GAMEPLAY_GT y el owner causal existente.

## 8. Implementation recommendation

Composición mínima en owners existentes, diseñada después de esta adquisición:
BASE/main landmark estructural de set/centro/slots bajo regiones seguras;
selector activo por check visual y slots cargados; grid/paginador focal;
discovery Flare/core template con margen/fases y tier/frame auxiliares;
reader de título único para tier/tipo/+nivel y barra focal sólo ante cero/ambigüedad;
action icon/text lateral por template; binding al candidato/set/página/input lineage;
una operación Equip o Unequip con efecto específico y espera pasiva bounded.

No depender del título superior bajo CHAT, ni de tab/selector parcialmente bajo
H&H como único landmark duro. Meteorites main tiene once slots y centro Flare
bajo los oclusores; los otros tabs ofrecen negativos cercanos. Detail sigue su
clase/layering, sin blacklist geométrica heredada automáticamente. Calibrar con
estos negativos antes de promover thresholds; ningún detector/reader quedó implementado.
Ancla inicial conservada; página verificada tras cada acción; cleanup individual
y Set 1 final. Precondiciones contractuales, sin auditoría exhaustiva ni nuevo coordinator.

Corpus local: **527 frames raw de adquisición, 63 muestras curadas**, 38 sesiones
scrcpy, 33 inputs separados y 35 checks CV live (incluye guard aborts). Sin venta,
Enhance, Combine, Evolve, Reforge, Reroll económico, Arena ni otros frentes.
[Manifest](../datasets/meteorites_hil_20261008_manifest.json) contiene timestamps,
secuencias por sesión, SHA256, raw→curado, positivos/negativos/transiciones y límites.
Raw en `artifacts/meteorites_hil/20261008`, curado en
`screencaps/semantic/meteorites/20261008`; ambos ignorados por Git, conservados en worktree.
Recorder exploratorio de un input conservado sólo en el worktree de adquisición; su configuración
machine-local se lee de AGENT_LOCAL y nunca se registra serial. Probes/curación
reproducibles en artifacts (`build_manifest.py`, JSON de tiempos/OCR/templates/glare).
Validación: formato/diff, sintaxis del recorder, referencias y hashes de corpus.
Sin suite ni evaluator: no se modificó lógica perceptiva/productiva.
