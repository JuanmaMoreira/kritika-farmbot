# Loading — estudio retrospectivo del núcleo estático

> **Informe histórico previo a 2D.** Se conservó el algoritmo sin exigir núcleo
> estático adicional. El alcance productivo actual es exclusivamente
> [MW Yes contextual](MONSTER_WAVE_SKIP.md). Las métricas retrospectivas no son
> validación independiente ni universal; reproducir este estudio requiere los
> artifacts locales ignorados, que no son dependencias del runtime.

**Recomendación para MW Yes: conservar el detector contextual actual.** El
núcleo es una característica real, estable y barata de reconocer cuando está
visible, pero la variante ensayada no mejora los resultados MW ni recupera la
oclusión conocida. No se modifica el detector ni se integra en producción.

`USER_GT`: el pequeño círculo central permanece estático mientras gira el arco
exterior. Modalidad de investigación de `kritika-dev-workflow`; sin hardware,
gameplay, commit/push ni ampliación a otros flows. HEAD `2686f0e`.

## Evidencia y métodos

Se reutilizaron182 imágenes únicas por SHA de2A/2B/2C:28 LOADING,144 NO_LOADING
y10 UNCERTAIN. Una imagen2A de loading se usa como plantilla y se excluye de
la matriz principal:27 positivos y144 negativos evaluados; los inciertos quedan
fuera de ella. Hay fases correlacionadas y derivados de una misma fuente.

**No hay holdout nuevo.** La secuencia2C fue independiente del detector anterior,
pero ya era conocida al diseñar este experimento; aquí es evidencia reutilizada.
Se preservan los labels, las oclusiones, los dos FP globales y sus resultados.
No se probaron barridos de umbrales ni se ajustó nada para hacer pasar Trading.

Comparación estática por frame:

1. **Actual, intacto:** prefiltro cyan/luminosidad y Hough con núcleo/arco cyan.
   Ya comprueba cyan en el interior de un círculo; no comprueba invariancia
   temporal ni la forma del pequeño núcleo. Se reutilizan resultados válidos
   de2B/2C y se vuelve a medir únicamente coste local.
2. **Núcleo independiente:** plantilla BGR de12×12 a escala equivalente a altura
   de frame600, extraída del centro de `2A/mw_yes_action/frame-0004.png`.
   Incluye punto brillante y halo, no el aro exterior. NCC≥.85, búsqueda±2px
   alrededor del centro de pantalla. No requiere dos frames ni memoria temporal.
3. **Núcleo combinado:** núcleo positivo AND detector actual; se evalúa primero
   el núcleo para poder evitar el trabajo exterior ante un negativo.

La geometría se deriva de frame.shape; sólo se recortan/reescalan ROIs offline,
sin alterar originales. Las constantes describen escala de análisis, no una
resolución fija del dispositivo. No se promueven assets ni un detector nuevo.

## Tamaño, posición y estabilidad

En los28 positivos revisados,27 conservan un soporte cyan brillante medible
en el núcleo; el caso restante es el tapado por la notificación de2C.

El soporte medido usa H75–105,V≥200 dentro de un disco de radio6 a escala600.
Su diámetro circular equivalente es2.99–3.57px a esa escala, mediana3.39:
aproximadamente **6.1–7.3px en frames de1224px de alto**, o .50–.60% de la altura.
Es un tamaño fotométrico dependiente del umbral, no el diámetro intrínseco
garantizado del dibujo. La plantilla12×12 abarca además el halo:~24.5px de lado
en ese frame, por lo que no debe describirse como sólo el punto blanco.

La posición es aproximadamente(x/w,y/h)=(.50,.50). Los centroides medidos varían
<.4px a escala600 entre positivos con soporte visible; el pequeño offset respecto
del centro incluye redondeo y muestreo. No es garantía para otros layouts.

En los tramos MW sin oclusión:

| Tramo | Pares consecutivos | MAD núcleo,0–255 | MAD aro,0–255 |
| --- | ---: | ---: | ---: |
| 2A frames3–9 | 6 | 0.00 | 27.60 |
| 2C frames3–7 | 4 | 0.00 | 28.10 |
| 2C entrada de notificación,7→8 | 1 | 70.08 | 66.19 |

Son diferencias BGR en patches decodificados y normalizados; cero significa que
esas muestras del núcleo son iguales a esa escala, no inmovilidad demostrada de
todos los pixels durante todos los instantes. El contraste V medio entre disco
central r<3 y annulus8≤r<12 es59.63–139.47, mediana125.96, en los27 positivos
con núcleo brillante visible. Los fondos transparentes afectan apariencia y
contraste aun cuando la animación central conserve su posición.

## Calidad comparada

| Método | TP | FN | FP | TN |
| --- | ---: | ---: | ---: | ---: |
| Actual | 26 | 1 | 2 | 142 |
| Núcleo independiente | 25 | 2 | 0 | 144 |
| Núcleo AND actual | 25 | 2 | 0 | 144 |

La imagen usada como plantilla y los10 inciertos se excluyen de esta tabla.
Los cambios son retrospectivos sobre datos vistos, no validación independiente.

En MW2C los tres métodos dan **5TP,1FN,0FP,12TN**. En MW2A los tres dan
8TP,0FN,0FP,20TN (descriptivo, incluye el frame plantilla; no una validación).
No cambia la primera detección ni se añade espera de dos muestras.

### Oclusión y FP conocidos

En `2C/mw_independent/frame-0008.png` la notificación cruza también el núcleo:
su contraste baja a1.54 unidades V, no queda soporte cyan conV≥200 y NCC=.560.
Los tres métodos fallan allí. La estabilidad del núcleo no implica visibilidad
ni robustece una región que también está ocluida. Los límites de lectura de CLEAR
descritos en [2C](LOADING_CONTEXT_VIABILITY_2C.md) se conservan intactos.

Los dos FP de Trading dan NCC=.290 para el núcleo en el centro y se rechazan
con las variantes nuevas. Sin embargo, una ablación diagnóstica que exige al
detector actual el mismo centrado±2px **también rechaza ambos**, sin plantilla
de núcleo. Esa ablación da24TP,3FN,0FP,144TN en el conjunto: no se afina ni se
propone adoptar su tolerancia. Demuestra que eliminar estos dos FP no prueba
una mejora específica de identidad debida al núcleo; la localización explica
al menos parte del efecto.

La plantilla introduce otro FN en `tests/fixtures/arena_phase_a/loading.png`,
con núcleo visible, contraste126.63 y NCC=.632. Es otro derivado curado de la
fuente de loading ya usada en2A. La sensibilidad de apariencia/remuestreo es una
limitación observada de esta plantilla; no se ajusta el umbral para corregirlo.
No se extrapola esa limitación a todo método posible de núcleo.

Además, un desafío **sintético**, separado de las matrices reales, pega sólo el
núcleo estático en un fondo vacío: núcleo independiente emite positivo y el
detector exterior lo rechaza. Una coincidencia de núcleo puede existir sin aro
ni animación. El0FP en los144 negativos reutilizados no demuestra que el núcleo
por sí solo acredite loading.

## Coste

200 iteraciones calientes por caso, sin captura/decode/IO; medidas aproximadas
y dependientes del scheduling de la máquina:

| Caso | Actual,mediana ms | Núcleo solo | Núcleo primero AND actual |
| --- | ---: | ---: | ---: |
| Positivo2A | 1.948 | .038 | 2.077 |
| FN ocluido2C | 1.770 | .040 | .038 |
| Negativo MW sin loading | .210 | .036 | .034 |

El núcleo es barato (~.04ms), pero no basta como señal independiente. Como
prefiltro reduce trabajo en estos negativos y añade trabajo en los positivos;
no mejora la sensibilidad ni la precisión observadas **dentro de MW**.
No se atribuyen ahorros de Session ni cambios de latencia terminal a estos
benchmarks aislados. El combinado no introduce capturas, estabilidad, polling ni
timeouts; aun así sería una dependencia visual nueva a validar antes de adoptarla.

## Decisión y preservación

Mantener para MW Yes la propuesta contextual2C: opt-in por operación autorizada
y despachada, source/freshness/cobertura compatibles, deadline heredado, terminales
y blockers siempre evaluados, ausencia sin autoridad de no-efecto o retry.
No cambiar ahora el detector vigente. El núcleo queda como dato descriptivo y
posible prefiltro futuro, sin evidencia independiente para sustituir geometría
ni justificar una promoción adicional. No se propone nueva adquisición en este
encargo ni se inicia otra fase.

Cambios: un informe y tres scripts/tests task-local en
`artifacts/loading_core_20261015`: `compare.py`, `measure_stability.py`,
`test_core_study.py`; métricas `comparison.json`, `stability.json`, plantillas/
ampliaciones diagnósticas y manifests de preservación. Ningún raw fue copiado o
modificado. Los resultados actuales se reutilizaron de148+34 pares previos.

Cinco tests focales pasan: escalado.5×/1×/1.25×, núcleo aislado insuficiente y
pérdida observada de contraste por oclusión. No se ejecuta suite de flows porque
no hay cambios productivos. Reproducción desde raíz:

```powershell
./tools/agent_run.ps1 artifacts.loading_core_20261015.compare
./tools/agent_run.ps1 artifacts.loading_core_20261015.measure_stability
.\.venv\Scripts\python.exe -m pytest artifacts/loading_core_20261015/test_core_study.py -q -p no:cacheprovider
```

Los193 archivos preservados de2A/2B/2C y los cambios no publicados se verifican
por SHA en `preservation_before.json`/`closure.json`; permanecen intactos.
Artifacts nuevos~.45MB. Sin hardware, gameplay, integración productiva,
commit/push ni cambios a políticas de retry. Se detiene el estudio.
