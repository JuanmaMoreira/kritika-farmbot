# Profiling focal de PerceptionEngine — 2026-10-16

Diagnóstico offline, `kritika-dev-workflow / diagnose-only`, sobre
`rebuild/stable-baseline @ 8ab0ff6ce78d2bf0e5a6d30641a60f11e5bc05ad`.
No se modifica producción, tests, contratos, vocabulario, resolver, guards ni
decisiones. Sin Session, hardware, nuevas capturas, commit o push.

**Resultado:** domina `matchTemplate`, no la conversión del frame completo.
En el subconjunto focal, el análisis global tarda **649,5 ms de mediana**;
602,7 de sus 701,2 ms medios corresponden a matching. Hay **26 medidas LocalCv
idénticas repetidas por análisis**, 183,4 ms medios de trabajo duplicado.
La primera optimización propuesta es cortocircuitar los gates existentes de
`PetLowTierCandidateDetector.detect` y `PetEpicAvailabilityDetector.detect`:
unos **135,7 ms/análisis global de trabajo actualmente ejecutado** quedan
después de un gate ya insuficiente en estos frames. Esto es potencial teórico
medido sobre el original; todavía no hay una implementación optimizada medida.

## Alcance y reproducción

Desde la raíz, con el Python de `AGENT_LOCAL.md`:

```powershell
.\.venv\Scripts\python.exe -m artifacts.perception_profile_20261016.study
.\.venv\Scripts\python.exe -m artifacts.perception_profile_20261016.detail_ops
.\.venv\Scripts\python.exe -m artifacts.perception_profile_20261016.full_frame
.\.venv\Scripts\python.exe -m artifacts.perception_profile_20261016.summarize
.\.venv\Scripts\python.exe -m artifacts.perception_profile_20261016.opportunities
```

Los scripts y datos derivados son artifacts locales ignorados por Git. La
reproducción no abre transporte ni inicializa backend OCR. Entradas, hashes,
configuración, inventario y logs exactos:
[metadata.json](../artifacts/perception_profile_20261016/metadata.json).
Muestras crudas:
[samples.jsonl](../artifacts/perception_profile_20261016/samples.jsonl).
Resultados por motor, detector y primitiva:
[summary.json](../artifacts/perception_profile_20261016/summary.json).
El [apéndice completo](../artifacts/perception_profile_20261016/MEASUREMENTS.md)
incluye los 101 detectores, familias, controles extranjeros y los 22 frames.

### Metodología

- 22 frames BGR existentes: 16 focales y 6 controles de seguridad. Incluye dos
  hubs, MW limpio, ranking, tres boards del corpus, CLEAR, Full, tooltip,
  cuatro capturas completas de campaña y Normal de Stages. Controles: Socket,
  animación oscura, Pet Combine, Mailbox, Black Market y Quick Menu.
- Se conservan los píxeles y dimensiones originales: 2712×1224 o 2712×1220.
  Las evidencias de fallos preservadas a 960×433 se excluyen del matching nativo;
  no se amplían para fingir calibración. `metadata.json` tiene SHA256 de cada PNG.
- Global: `build_default_perception`. A1: selección productiva
  `MONSTER_WAVE_BOARD_ACQUISITION_SCOPE` + `MonsterWaveBoardPerception` existente.
  No se ensaya un nuevo scope ni una optimización propuesta.
- Por motor: 3 recorridos sin instrumentación; 8 recorridos instrumentados con
  orden pseudoaleatorio reproducible (seed 716 + repetición); 8 llamadas por
  frame con píxeles repetidos tras precalentarlo; 2 llamadas con motor recién
  construido por frame. Hay además 88 parejas globales alternadas con/sin
  registro para estimar overhead. En total, 1.100 análisis en el estudio principal.
- “Nuevo/alternado” significa otro frame archivado, frecuentemente otro contexto;
  no una nueva adquisición física. Incluso al repetir píxeles se copia el array
  y se renuevan sequence/timestamp. PNG decode, copias del harness, construcción
  del motor, firmas y escritura de resultados quedan fuera de `analyze`.
- “Frío” vacía el estado del motor/memo y vuelve a cargar assets; el proceso,
  OpenCV y filesystem ya están calientes. No mide arranque de Windows ni cold
  page cache. La construcción se conserva aparte en las muestras crudas.
- Se cronometra `analyze` real con `perf_counter` y cada `detect` superior hasta
  materializar su iterable. Wrappers exclusivamente en el proceso de medición
  registran `LocalCvDetector.measure`, `matchTemplate`, `cvtColor`, `resize`,
  `minMaxLoc`, `inRange` y `split`. Los wrappers reenvían argumentos y kwargs.
- Los 101 tiempos de detector son aditivos; las primitivas y medidas internas
  están incluidas en ellos. Se reconcilian sumas y medias, nunca la suma de p95
  o medianas. El resto de `analyze` incluye validación/concatenación, emisión de
  batch y registro del harness. En A1 incluye su comparación/copia de crops.
- Se exige la misma firma exacta de observaciones, orden y valores por
  motor/frame entre ejecución original, instrumentada, repetida y motor frío.
  Esta comprobación no compara global contra A1 como si tuvieran igual cobertura.
  No demuestra equivalencia de ninguna optimización futura.

Entorno: Python 3.12.14, NumPy 2.5.2, OpenCV 5.0.0, Windows 11, CPU AMD64,
6 procesadores lógicos; OpenCV conserva sus 6 threads y optimizaciones/OpenCL
habilitados. Usar arrays NumPy no acredita ejecución GPU. Configuración completa:
[opencv_build.txt](../artifacts/perception_profile_20261016/opencv_build.txt).
Tiempos de pared síncrona, sin aislamiento del sistema: no son CPU pura.

La primera corrida etiquetó incorrectamente todas las entradas como ROI por
comparar `tuple` contra `list`; sus **tiempos** y el resto de la instrumentación
siguen válidos. Se corrigió el harness y se repitió sólo la atribución afectada:
4 especializados × 22 frames × 8 repeticiones. La fuente de esa clasificación es
[full_frame.json](../artifacts/perception_profile_20261016/full_frame.json),
no el sufijo `roi/full` de las muestras originales. Las tablas del apéndice
usan ese suplemento. Una reproducción nueva del script principal ya tiene el
comparador corregido.

## Mediciones y reconciliación

Los cuatro logs de la campaña reconstruyen **20.044 análisis, 7.476,421771 s**,
máximo registrado 2,241046 s. MW: 8.708 llamadas / 5.548,799560 s; Stages:
6.095 / 1.217,887906 s. Son mezclas de scopes y owners, no tiempos del mismo
engine completo. Las restantes 5.241 llamadas suman 709,734305 s.
El timer histórico de `RuntimeObserver` incluye `analyze` y `check_operation`,
pero termina antes de resolver y construir facts; el benchmark cronometra sólo
`analyze`. Captura, OCR del reader, resolver y esperas no están en este timer.

### Total por condición

Esta tabla usa los 22 frames; ms de pared. El análisis focal posterior usa sólo
los 16 pertinentes al recorrido, y por eso tiene percentiles ligeramente distintos.

| Motor / condición | n | Mediana | p95 | Máximo |
| --- | ---: | ---: | ---: | ---: |
| Global original, alternados | 66 | 655,3 | 841,4 | 922,4 |
| Global instrumentado, alternados | 176 | 650,2 | 992,8 | 1.506,8 |
| Global instrumentado, repetidos | 176 | 706,4 | 1.203,7 | 2.183,3 |
| Global instrumentado, motor frío | 44 | 833,6 | 1.238,9 | 1.410,4 |
| A1 original, alternados | 66 | 474,6 | 836,7 | 1.119,8 |
| A1 instrumentado, alternados | 176 | 526,5 | 849,2 | 1.331,1 |
| A1 instrumentado, repetidos | 176 | 204,8 | 259,4 | 363,5 |
| A1 instrumentado, motor frío | 44 | 528,5 | 767,4 | 1.345,6 |

Global no tiene memo de frames: repetir píxeles no elimina una sola llamada.
No atribuir sus diferencias entre fases a un gate/caché inexistente. Hay ruido,
deriva entre fases, asignaciones y cachés internas de bibliotecas/CPU no controladas.
A1 sí tiene una diferencia algorítmica acreditada: **81 hits de 81 posibles**
en repetidos; **0** en frío; **0,36 hits/análisis** de media en alternados.
La colección alternada cambia mucho más de contexto que un wait físico estable.

En A1 caliente, los 8 especializados todavía consumen **197,5 ms medios** y el
resto del análisis 11,5 ms: total 209,0 ms. No se acelera el reader OCR ni la
reacreditación Yes/No por el hecho de tener esos hits.

Overhead: las 88 parejas alternadas dan delta traced−plain medio **26,43 ms**
(3,46% del plain pareado), mediana **9,71 ms**, p95 **321,64 ms**, máximo
878,56 ms; **36/88 deltas negativos**. La cola está fuertemente contaminada por
ruido de scheduling: no es un coste fijo de instrumentación ni se resta a cada
detector. Mejoras pequeñas requieren una comparación pareada propia más estable;
estos datos permiten identificar trabajo dominante, no certificar diferencias de 1 ms.

### Descomposición aditiva focal

128 análisis globales = 16 frames × 8. Media por análisis:

| Componente | Media ms | Parte del total |
| --- | ---: | ---: |
| 84 LocalCv superiores | 340,522 | 48,56% |
| 17 especializados, inclusivos | 359,890 | 51,33% |
| Resto fuera de detectores | 0,776 | 0,11% |
| **Total** | **701,188** | **100%** |

Suma exacta de las muestras: **89,752009 s = 89,652714 s de detectores +
0,099295 s de resto**. Es compatible por construcción y por registro sobre
`analyze` real, sin reconstruir su algoritmo. La cola focal: p95 1.059,5 ms,
máximo 1.506,8 ms. El resto no es un gran coste oculto del engine global.

Primitivas incluidas en esos componentes: `matchTemplate` **602,685 ms**
(229,12 llamadas/análisis; 85,95% del total), `cvtColor` 29,571 ms,
`resize` 29,226 ms, `minMaxLoc` 2,617 ms, `split` 1,380 ms e `inRange`
0,240 ms. Quedan 35,468 ms fuera de estas primitivas: NumPy, geometría,
calibración, validaciones, objetos y registro Python, mayormente **dentro**
de los detectores. No es overhead sin atribuir a detectores.

A1 focal alternado: **72,984858 s = 70,277711 s de detectores + 2,707147 s**
de memo/agregación y registro (3,71%). De ese resto, 1,458076 s son conversiones
de crops previas a consultar la memo; lo restante incluye igualdad/copias,
iteración y batch. Su media total es 570,2 ms, mediana 522,4 ms.

Como comprobación independiente, cuatro análisis globales con `cProfile` dan
2,925 s inclusivos de engine y 2,448 s en 916 `matchTemplate`.
[Perfil](../artifacts/perception_profile_20261016/detail_profile.txt): no sumar
sus tiempos inclusivos anidados ni mezclarlos con los de la serie anterior.

### Familias, operaciones grandes e irrelevancia contextual

Medias focales por familia, incluyendo LocalCv y especializados asociados:
Pets **292,96 ms (41,8%)**; Combine **94,76 ms (13,5%)**; Socket **60,00 ms
(8,6%)**; Arena **47,35 ms (6,8%)**; global/navegación **42,13 ms (6,0%)**.
MW propiamente dicho cuesta **20,02 ms (2,9%)**. Son agrupaciones de atribución,
no permisos para omitir familias. El apéndice da mediana/p95/máximo de todas.

Los especializados más costosos son Low Tier Pets **92,18 / 84,81 / 137,86 /
190,40 ms** (media/mediana/p95/máximo), Arena **47,35 / 44,92 / 62,90 / 234,53**,
Epic Pets **45,67 / 42,18 / 65,25 / 96,61**, Socket Opal **34,09 / 30,45 /
54,70 / 129,42** y Combine Context **31,41 / 28,82 / 46,61 / 69,98**.
Entre LocalCv destacan la animación Combine, **26,80 ms medios**, y Equipment
Full, **22,51 ms**: ninguno se declara prescindible por pertenecer a otro flow.

La atribución suplementaria de **frame completo** mide, por análisis focal:

| Operación | Llamadas | Media / mediana / p95 / max, ms |
| --- | ---: | --- |
| Arena resize completo | 5 | 14,48 / 16,08 / 23,76 / 47,61 |
| Meteorites normalización completa | 1 | 2,30 / 1,12 / 5,39 / 15,45 |
| Low Tier BGR→HSV completo | 1 | 2,99 / 2,65 / 4,17 / 15,49 |
| Socket Animation BGR→gray completo | 1 | 1,10 / 1,03 / 1,79 / 2,61 |

Suman aproximadamente **20,88 ms** en esa corrida separada. Es trabajo real,
pero mucho menor que el matching. En Arena, el suplemento específico de 32
llamadas detecta cinco resizes completos al mismo target 1356×610 en estos
cuatro frames: **cuatro redundantes**. Su coste duplicado medio es 11,99 ms,
mediana 9,76, p95 29,34, máximo 34,88. Stream: hub 16,19 / board 24,04 ms;
native: hub 3,64 / board 4,10 ms medios. No asumir un coste idéntico entre
alturas 1220 y 1224 ni cambiar el sampling/rounding para ahorrar tiempo.
[Detalle](../artifacts/perception_profile_20261016/detail_operations.json).

Los especializados que devuelven vacío consumen **358,50 ms/análisis focal**.
Vacío no significa que sea seguro no observarlos. Una señal más fuerte para
priorizar es el gate existente: en **128/128** análisis focales, el primer
landmark de Low Tier, Epic, tres Quests, Mailbox y Guild tiene confianza <0,8,
que ya acota todas sus salidas. Después de ese resultado gastan **152,07 ms**
(21,7% del total) sin posibilidad de emitir bajo sus reglas actuales.
Low Tier aporta 91,06 ms; Epic 44,59 ms. El ahorro incluye **matching de
blockers subordinados**, no sólo los 2,99 ms de HSV completo.

Esto sí permite plantear un cortocircuito equivalente; no prueba que Pets,
Quests o Guild estén físicamente ausentes. Los detectores independientes de
BASE, blockers y modales seguirían ejecutándose. En controles extranjeros,
GOLD, Mailbox Processing y Socket Animation emiten en sus respectivos ejemplos:
su ausencia en los frames MW no los convierte en dispensables globalmente.

## Wiring y cachés efectivos — IMPLEMENTATION_CONTRACT

[PerceptionEngine](../bot/perception/engine.py) recorre todos los detectores
inyectados en orden; no recibe contexto ni facts de otro detector y no selecciona
dinámicamente por flow. El resolver corre después, fuera de `analyze`.

[build_default_perception](../bot/perception/__init__.py) inyecta **84 LocalCv y
17 especializados**. Los LocalCv tienen **102 templates/variantes precargados**;
prueban todas las variantes compatibles y calibran el máximo. El matching común
ya recorta **antes** de convertir a gris: proponer ese cambio otra vez sería
LEGACY_STALE. No hay memo de resultados ni de crops en el engine global.

[A1](../bot/flow_registry.py) selecciona 81 LocalCv + 8 especializados, 89 en
total. Su memo local conserva un crop gris exacto por LocalCv; exige igual shape
y `array_equal`, y vuelve a construir el batch con procedencia de la nueva
muestra. Cambiar píxeles obliga a recalcular. Los especializados siempre corren.
La adquisición económica tiene además una memo OCR exacta por fila en el reader;
esa memo no es parte de `PerceptionEngine.analyze` ni cachea saldos o permiso.

Después de adquirir el board, `MonsterWaveSnapshotRuntime` usa el observer
original para reacreditar Yes/No. Esa percepción global sigue siendo trabajo
real, no un gasto eliminado por A1. Se conserva el resultado negativo de
[MW_BOARD_REACCREDITATION_PERFORMANCE](MW_BOARD_REACCREDITATION_PERFORMANCE.md):
la pareja económica no acredita exposición de controles ni autoriza el input.

Stages ya tiene scopes productivos en [stages_wiring](../bot/stages_wiring.py):
panel con familia fuerte, claim focal y retorno Results/Config/Normal de cuatro
detectores. Entradas/salidas y otros owners pueden volver a observación amplia.
`StagesClaimDetector` no forma parte de los 17 especializados globales.

`TradingTabsDetector`, `TradingRowsDetector`, `TreasureContentDetector` y
`GlobalLoadingDetector` tienen capacidad propia, pero no están inyectados en el
engine global. GlobalLoading está restringido al owner MW Yes. Ninguno de los
17 especializados globales ejecuta OCR. Android Ads tiene un observer propio
con Stages + Lobby y métodos de chrome/OCR fuera de este `analyze`; no atribuir
su coste a los 101 ni extrapolar el benchmark al coste total de un anuncio.

## Especializados: gates, trabajo y seguridad

Los costes individuales medidos y sus percentiles están en el apéndice. Esta
tabla describe el trabajo ejecutado por el código, no una lista de familias
autorizadas a desaparecer.

| Detector | Trabajo y gate vigente | Posibilidad y condición semántica |
| --- | --- | --- |
| Stages | Cadena de matching: loading, capas superiores, alert con chrome, paneles, mapa y modos; salida temprana por superficie | Mantener orden superior/exposición y todos los modales; títulos dimmed no autorizan controles. Preprocesar templates inmutables no requiere omitir superficies. |
| Meteorites | Resize del frame completo a 1356×612 antes del landmark main; detail/loading sólo después | Main es gate temprano para las ramas secundarias. Quitar el resize o recortar antes cambia sampling/rounding y exige replay; preservar detección de BASE extranjera. |
| Arena | Varias superficies independientes, short-circuits dentro de cada una; normalizaciones completas repetidas y checks compartidos | Compartir transformaciones deterministas conserva todas las pruebas. No suprimir Previous Rewards, modales, Single Result ni BASE/battle extranjeros. |
| BlackMarketGold | 10 slots, sin gate de contexto | Ausencia del título BM no prueba irrelevancia física; un gate nuevo alteraría facts y requiere demostrar cobertura de consumidores. |
| BlackMarketPurchased | 10 slots × variantes, sin gate de contexto | Igual restricción; Purchased y GOLD son facts distintos para pre/postcondiciones. |
| SocketIncompatibleOpal | 16 slots × 2 templates, sin gate de contexto | Coste candidato a scope contractual futuro; conservar foreign Socket y Full por separado. No omitirlo sólo por nombre del flow. |
| SocketEnhanceAnimation | Gris completo, máscara de periferia oscura, media central; sin gate de landmark | La animación puede ocultar chrome: exigir título Socket perdería la señal que autoriza TapThrough. Cambios de cálculo deben conservar el criterio positivo y UNKNOWN en flash. |
| CombineContext | Vuelve a medir tab y animación; OR por evidencias | Landmark requerido por BASE Combine; conservar ambas vías, incluida animación. Reutilización exacta de medidas es candidata. |
| DailyQuestsProgressReward | Mide title/tab; calcula color ROI aunque min del gate resulte bajo | Detect puede evitar trabajo posterior a un gate insuficiente sin inferir ausencia física; measure diagnóstico requiere conservar su contrato. El reward lo consume el siguiente paso. |
| DailyQuestsRows | Igual title/tab repetidos + gris/brillo ROI | Mismo criterio algebraico; no eliminar fact de rows por enfocarse sólo en Claim. |
| DailyQuestsLoading | Igual title/tab repetidos + HSV/máscara ROI | Mismo criterio; loading no autoriza retries ni acredita completion. |
| MailboxClaimProcessing | Title repetido + HSV/máscara ROI | Gate algebraico candidato; no romper onset, completion o fallback de ClaimAll. |
| GuildAttendance | Guild y Quick Menu repetidos + HSV/media ROI | Quick Menu bloquea facts de attendance; preservarlo aunque la BASE subyacente siga visible. |
| PetEpicAvailability | Summon y blockers repetidos + HSV ROI | Es disponibilidad positiva/negativa bajo gate; no convertir detector omitido en unavailable. |
| PetCombineResult | Un LocalCv repetido; emite dos observaciones | Emite BASE Pet Result y actividad Combine compartida. No eliminar como supuesto fact exclusivo de Pets. |
| PetLowTierCandidate | Combine/prompt y blockers; aun con gate cero convierte frame completo a HSV y analiza 16 slots | Detect puede devolver vacío cuando el mismo gate ya impide toda emisión. Preservar measure, tier, margins y blockers en ramas admitidas. |
| PetMassEvolveConfirmation | Dos LocalCv; margen entre Normal/Rare | Modal/tier positivo: conservar ambos scores y la ambigüedad; reutilizar medidas exactas no cambia policy. |

Los gates algebraicos anteriores sólo ahorran cálculos que ya no pueden producir
una observación con el umbral vigente. Un miss no se promueve a USER_GT ni se usa
para autorizar un input, omitir un blocker independiente o afirmar otra BASE.

## Scopes: conclusión de seguridad

Hay potencial en evitar facts de slots/candidatos sin consumidores dentro de una
operación concreta, como muestran los scopes existentes. Un scope MW construido
sólo con sus positivos no conserva por sí mismo la observación de contextos
extranjeros, contradicciones o modales. El resolver recibe ausencia si un detector
no corre; el scope no añade un tercer valor “no observado”.

Cada scope futuro debe enumerar observaciones consumidas por guard, abort,
precondición, postcondición y siguiente paso, junto con todas sus dependencias
de BASE/capas. Debe conservar cambios inesperados, Quick Menu y blockers globales
relevantes; dos positivos de board no prueban Yes/No expuestos. La reducción de
latencia no autoriza relajar freshness, estabilidad, source, cancelación ni bounds.
No se propone un scope nuevo como primera optimización.

Stages conserva su cadena de capas superiores, alert/body bajo main activity,
dimmed chrome y condiciones de entrada/retorno. Ads conserva activity/focus,
Next ad, Reward granted, terminal chrome, Results y prueba de reward; no es
seguro omitir Stages porque el caller actual se llame MW o porque el título
decorativo sea ilegible. Chat/H&H siguen siendo oclusores con su recovery causal
vigente, no un detector global nuevo inferido por este estudio.

## Cinco candidatos, ordenados por beneficio y riesgo

Fuente aritmética:
[opportunities.json](../artifacts/perception_profile_20261016/opportunities.json),
generada desde las muestras originales, sin sustituir algoritmos. Los costes
son inclusivos y **se solapan entre candidatos**: cortocircuitar Pets también
elimina parte de las medidas duplicadas; una memo caliente reduce lo que puede
ahorrar otra optimización. No sumar las cinco filas.

Para cuantificar campaña se usa un escenario deliberadamente acotado:
**368 análisis globales de reacreditación en 184 boards**, 256,448015 s
históricos de procesamiento, ya reconstruidos por el
[estudio conservado](MW_BOARD_REACCREDITATION_PERFORMANCE.md).
Se multiplica el trabajo potencial medio de los **cuatro frames de board** del
benchmark por 368. Eso es una **cuenta teórica con costes offline**, no una
estimación del ahorro real de esos logs ni de pared de una campaña futura.
Para el resto, `G` es número de llamadas globales y `A` número de llamadas A1
aplicables: ambos deben medirse por detector set, sin sustituirlos por 20.044.

| Prioridad / candidato | Coste original por llamada focal | Frecuencia | Potencial por análisis / escenario 368 | Riesgo semántico / esfuerzo |
| --- | --- | --- | --- | --- |
| **1. Cortocircuitar gates ya existentes en Low Tier y Epic Pets** | 92,18 + 45,67 ms medios; medianas 84,81 + 42,18 | Ambos en cada global; sólo Epic en cada A1. Primer gate cerrado en 128/128 focales | **135,65 ms/global**, 50,93 ms/A1 alternado; boards globales 138,39 ms → **50,93 s teóricos** | Bajo si se conserva exactamente min/umbrales/errores; esfuerzo bajo. Otros cinco gates sumarían trabajo candidato, pero quedan para después. |
| **2. Compartir LocalCv.measure idénticos dentro del mismo análisis** | 26 llamadas duplicadas/global; media 183,40 ms, mediana 170,53, p95 278,09 | Estructural, cada global. A1 alternado: ~11 duplicadas/66,95 ms; A1 repetido caliente: **0 duplicadas** | Techo **183,40 ms/global** antes del coste de compartir; board 184,77 ms → **68,00 s teóricos** | Bajo sobre resultados puros; riesgo técnico medio por compartir instancias/scopes/excepciones. Esfuerzo medio; exige un mecanismo explícito acotado a la invocación. |
| **3. Compartir normalizaciones completas de Arena por análisis** | Arena 47,35 ms medios; 5 resizes completos, cuatro repetidos al mismo target en los cuatro frames suplementarios | Cada global y A1 ejecuta Arena; número de targets/checks puede cambiar en positivos | Trabajo redundante medido **11,99 ms** de media; board stream/native medio 14,07 ms → **5,18 s teóricos** | Bajo si se conserva resize completo, interpolación y fase de muestreo; esfuerzo medio. La ganancia pequeña requiere una comparación propia estable. |
| **4. Evaluar memo exacta de LocalCv global entre frames, como A1** | Los 84 LocalCv cuestan 340,52 ms medios/global; memo A1 existente sí muestra 81 hits en repetidos | Depende de píxeles de cada ROI, no de sequence ni del nombre del contexto. Hit rate productivo **UNKNOWN** | Con todos los crops idénticos, techo 340,52 ms antes de comparar/copiar; board 352,58 ms → **hasta 129,75 s teóricos**, menos overhead. Con 0 hits puede empeorar | Bajo/medio semántico si sólo reutiliza función pura y batch nuevo; riesgo de rendimiento medio. Esfuerzo medio. No cachear facts, snapshot, permisos o especializados por analogía. |
| **5. Evaluar scopes para facts de slots, conservando observación fuerte** | Socket Opal + BM GOLD/Purchased: media 52,98 ms, mediana 47,68, p95 80,74 | Los tres corren en global; ya están ausentes en A1. No se conoce el total global de campaña | Techo bruto 52,98 ms; board 54,79 ms → **20,16 s teóricos**. **Ahorro actualmente aceptable: no demostrado** | Alto sin inventario de consumidores; esfuerzo alto. No adoptar un gate de título ni omitir BASE/Full/modales. |

El ahorro medido de una **implementación nueva** es **ninguno** en las cinco
filas: se midió trabajo original y se identificaron techos. El beneficio de la
memo A1 caliente pertenece al código existente. El ahorro físico nuevo está
**pendiente de validación**, y puede diferir incluso del ahorro de cómputo por
polling, estabilidad, juego, OCR y vencimiento de frames.

Validación necesaria antes de adoptar cada candidato:

1. **Gates Pets:** positivos Normal/Rare y Epic available/unavailable; Combine,
   Summon, resultados y blockers; confianza alrededor de 0,8; gate bajo con
   colores que producirían candidatos; malformed frames y templates que no
   caben; mismas observaciones ordenadas y `measure` diagnóstico intacto.
   Replays focales MW/hub/board + manifiestos Pets afectados y sus tests
   directos. Comparar latencia pareada con negativos y positivos por separado.
2. **Medidas compartidas:** identidad completa de spec, assets/variantes,
   calibración y geometría, orden de emisión, excepción, anidación/reentrada,
   distintos engines/scopes y frames que cambian con el mismo objeto. Replays
   de consumidores de todos los specs compartidos, especialmente Combine,
   Quests, Full y confirmación Normal/Rare. Evaluator incremental de ese conjunto
   si se altera infraestructura perceptiva; ampliarlo sólo por invalidación real.
3. **Arena:** replay Previous Rewards/modal exposure, Survival y Single,
   positivos/negativos en ambas alturas y reference shapes; mismos píxeles
   normalizados y scores. Memo limitada a una invocación, liberada incluso al
   fallar, sin reutilización por identidad de frame entre análisis.
4. **Memo global:** comparación exacta de cada crop leído, shape/dtype y revisión
   de templates/config; aciertos, misses, cambios de un píxel, cambio de source,
   reentrada y límites de memoria. Conservar siempre nueva secuencia/timestamp,
   cobertura y ejecución de especializados. Medir hit rate y coste de misses
   sobre secuencias consecutivas existentes antes de prometer beneficio; las
   secuencias completas nativas de campaña faltan en este estudio.
5. **Scopes slots:** inventariar facts de pre/postcondición y consumidor siguiente,
   aborts/contradicciones y controles expuestos por operación. GOLD/Purchased
   alimentan `RuntimeFacts`; Opal selecciona slots. Un fact no observado no puede
   convertirse silenciosamente en negativo. Exigir equivalencia sobre cambios
   inesperados, todos los blockers/modales relevantes y salida de scope. Si la
   exclusión depende de un hecho físico nuevo, obtener USER_GT antes del código.

Otras ideas pequeñas no lideran el ranking: cachear el resize de templates
Stages sólo ataca **0,315 ms/análisis** en la mezcla completa, y compartir gris
entre variantes de slots sólo una fracción de **1,90 ms** de conversiones Socket
y **0,85 ms** de Purchased. No confundir esos importes con sus costes de matching.
Recortar primero en el helper LocalCv ya está implementado.

## Primera optimización de código propuesta

**Alcance siguiente:** dos cortocircuitos locales en `detect`, Low Tier y Epic
Pets, sin scopes nuevos ni política en los owners. Cuando el primer landmark
existente tenga confianza <0,8, la fórmula actual ya hace imposible emitir
ninguna observación de ese detector. Devolver entonces `()` evita medir los
blockers subordinados y calcular slots/HSV que no podrían cambiar esa salida.
Todos los detectores independientes del engine continúan observando el frame.

En rama admitida, conservar el cálculo completo de blockers, tier, margen y
disponibilidad. Reutilizar el resultado del primer gate para no añadir matching
al camino positivo. Mantener la API diagnóstica `measure` y sus campos,
validaciones y errores; no ocultar errores por geometría incompatible mediante
el retorno temprano. No introducir caché global, framework de contexto ni
asumir ausencia física de Pets por un miss.

El primer patch no beneficia A1 a través de Low Tier, que ya está fuera de ese
scope; **Epic sí beneficia A1**. Ambos benefician reacreditación de board y las
transiciones Gold que llaman al engine global, sin cambiar cada flow.

Aceptación offline: salidas equivalentes en corpus focal y Pets positivos,
regresiones directas afectadas, tratamiento de errores intacto y ahorro pareado
reproducible en negativos sin regresión relevante en positivos. Medir primero
estas dos clases; no añadir los otros gates o una memo compartida hasta revisar
ese resultado. Cualquier comprobación física de throughput/freshness será una
tarea posterior autorizada: este diagnóstico no necesita hardware para cerrar
ni acredita ahorro físico.

## Cierre y preservación

1.100 análisis principales sin discrepancias de firmas ni errores; 32 llamadas
Arena y cuatro análisis `cProfile` suplementarios; 176 iteraciones de atribución
de frame completo sobre cuatro especializados. Sin evaluator global, tests de
producto, capturas o inputs físicos.

El diff de archivos tracked y el staged quedan vacíos. Sólo se añade este
informe visible y artifacts locales ignorados. El documento negativo de board
y el capturador HIL untracked mantienen los SHA256 registrados al comienzo;
los cuatro logs mantienen sus hashes. Evidencia original preservada. No se
implementa ninguna de las optimizaciones del ranking.

## Límites

La mezcla de 16 frames focales es balanceada por selección, no por frecuencia de
campaña. Ocho repeticiones por frame describen coste y dispersión local; p95 no
es una estimación de cola física independiente. Dos llamadas frías por frame
permiten comparar estado de caché, no caracterizar percentiles de arranque.

El corpus elegido representa hub, MW, board y Normal de Stages. No contiene una
secuencia completa nativa de animación de entrada hub→MW, ni todos los paneles
Config/Auto/Results o variantes de Ads de la campaña. No se atribuye el tiempo
de esos contextos a partir de una captura Normal o de fallos reducidos. No se
crean nuevos labels físicos ni se cambia GT por resultados de detectores.

Las métricas históricas no registran detector set/cache hit por cada análisis.
No se conoce cuántas de las 20.044 llamadas ejecutaron cada candidato. No se
extrapolan automáticamente tiempos offline a producción ni se suman tiempos
anidados de análisis, wait, transición, reader y flow. Ninguna optimización
propuesta tiene todavía ahorro benchmark de una implementación ni ahorro físico.
