# Loading 2C — viabilidad contextual, sin integración

> **Informe histórico de fase 2C, anterior a la integración.** La implementación
> vigente de MW Yes está en [MONSTER_WAVE_SKIP](MONSTER_WAVE_SKIP.md). Las métricas
> siguientes son exploratorias, de los episodios indicados, sin validación
> universal. Sus órdenes de reproducción requieren los artifacts locales
> ignorados; el runtime y las regresiones de integración no los requieren.

**Decisión A: viable para una integración focal de progreso en MW Yes bajo el
contrato de admisión descrito aquí.** Hay una secuencia MW independiente con
precisión suficiente en el contexto adquirido. No es aprobación de detección
global ni de WB START; tampoco es integración ni validación end-to-end del flow.

Fecha local2026-10-15; rama `rebuild/stable-baseline`, HEAD `2686f0e`.
El [resultado global2B](GLOBAL_LOADING_EXPERIMENT.md) sigue vigente como fallo
global y sus archivos permanecen intactos. Esta decisión cambia el alcance de
adopción, no el resultado visual del detector ni sus umbrales.

## Preservación y separación de datos

Se inventariaron y verificaron133 archivos previos: todos los artifacts2A/2B,
los cinco archivos experimentales y el capturador2A. SHA-256 y tamaños antes y
después en `artifacts/loading_central_2c_20261015/preservation_before.json` y
`closure.json`. No se modificó ninguno.

El detector conserva el SHA-256
`bcb9331d1f434201fc79576285855e9f5c23e02e6f1d6ac869735447b4042fac`.
Se congeló antes de adquirir la nueva secuencia. No se ajustaron ROI, color,
Hough, confianza, escala ni umbrales después de ver los ejemplos independientes.

Separación:

- Los148 pares de2B y todo2A siguen siendo desarrollo/regresiones conocidas;
  se reutilizan sus resultados aún válidos, no se presentan como nuevo holdout.
- Se revisaron16 imágenes existentes no vistas por el detector en2A/2B. Doce
  son vecinos de la adquisición MW de septiembre ya usada: supplement, no holdout
  independiente. Hay dos negativos MW alrededor de Point/CLEAR de otra
  adquisición de octubre, un negativo Trading de esa adquisición y un positivo
  Arena curado del12 de octubre. El nombre `mw_gold_relief_final.png` no lo
  convierte en MW: visualmente es Trading y se etiqueta como tal.
- Nueva secuencia MW2C, otro personaje (Demon Blade), otro lifetime de fuente,
  adquisición posterior a congelar el detector:18 frames,6 LOADING y12 NO_LOADING.
  Cero hashes compartidos con2A/2B. Una secuencia constituye un episodio, no18
  ensayos independientes.
- Etiquetas por revisión visual del frame completo y ROI a resolución original,
  antes de ejecutar predicciones. Loading visible y CLEAR acreditado por el
  reader son etiquetas distintas. Los10 UNCERTAIN de2B no se reclasificaron ni
  se incluyeron como negativos. No se adquirieron nuevos frames ambiguos de
  visibilidad: en frame8 hay loading visible parcialmente ocluido; en9+ el centro
  está expuesto sin aro, aunque queden notificaciones por encima.

## Adquisición y procedencia

El usuario preparó la confirmación y después autorizó explícitamente:
«toca vos yes para no tener que coordinarnos». Se revisó el preview y una muestra
fresca de la confirmación; se ejecutó **un solo Yes**, sin retry. El dispatcher
local se enclava antes del input y rechaza una segunda ejecución.
`action.json` conserva autorización, secuencia/fuente de antes, geometría desde
frame.shape, inicio y retorno monotónicos. NCC de confirmación.9951 sólo es una
comprobación puntual del popup revisado, independiente del detector de loading.

Captura pasiva reutilizando `ScrcpyFrameSource`:12s,18 PNG completos de2712×1224,
sin crop ni resize de raw; secuencia, source_id, timestamps host monotonic
mapeados desde PTS, UTC de retrieval y SHA-256 por frame. Límite48MB de PNG de
secuencia; retención real30,076,095 bytes. Directorio de adquisición~33.17MB,
incluido preview; carpeta2C completa~35MB con análisis y fuentes.

El `acquisition.json` inicial dice que el usuario operaría Yes; se conserva
intacto y `acquisition_amendment.json` registra el cambio posterior de operación
autorizado. El capturador siguió siendo pasivo; otro script local hizo el único
despacho. No se pulsó OK ni se restauró/navegó el juego. La fuente cerró mediante
su owner al acabar12s; no hubo repetición de operación ni campaña.

## Resultado visual independiente

| Evidencia | TP | FN | FP | TN |
| --- | ---: | ---: | ---: | ---: |
| Nueva secuencia MW completa | 5 | 1 | 0 | 12 |
| Ventana post-Yes antes de CLEAR acreditado | 5 | 1 | 0 | 4 |
| Stills de otra adquisición: MW Point/CLEAR y Trading | 0 | 0 | 0 | 3 |
| Positivo Arena independiente del12 de octubre | 1 | 0 | 0 | 0 |
| Supplement MW antiguo, no holdout | 0 | 0 | 0 | 12 |

La ventana relevante son frames3–12: posteriores al retorno del despacho y antes
del primer CLEAR acreditado en el replay de límites. Frames0–2 son predespacho;
frames13–17 ya son terminales acreditables. La calidad visual se mide antes de
filtrar contexto: el FN del frame8 no se elimina del denominador por ser CLEAR
visualmente. TP5/6 equivale a83.3% de recall en esta muestra, con un único episodio.
No se afirma un límite poblacional a la tasa de FP a partir de0/4 o0/12.

El FN es el spinner atravesado por la notificación de límite sobre el primer
CLEAR visual. Las cinco fases previas de procesamiento se detectan. Este miss
no requiere ajuste para la semántica positiva propuesta: su consecuencia es
no anotar progreso en ese frame, conservando observación legacy y deadline.
Nunca se interpreta como no-efecto ni como permiso de input.

Primera evaluación:16 pares nuevos existentes; después18 nuevos de la secuencia,
reutilizando16 hits sin invalidaciones (34 pares,1.19s). Reproducción final:
34 hits,0 evaluados,0 invalidaciones,0.22s; labels/métricas fuera del cache.
Se reutilizó el evaluator incremental existente, sin infraestructura nueva.

## Límite de Trading y contrato contextual propuesto

Los dos FP globales siguen siendo FP: iconos cyan sobre filas blancas cumplen
núcleo/arco y Hough acepta contornos parciales/descentrados. No se corrigieron
usando esos ejemplos. Su replay con percepción default existente devuelve
`RESOLVED screen.trading` en ambos. Por eso una ventana MW correctamente admitida
y que conserva reconocimiento de contextos ajenos debe **invalidarse** al verlos.
Este rechazo contextual no convierte las imágenes en negativos visuales correctos.

Contrato de operación, no detector universal:

1. Admisión sólo por el owner de MW Yes: autorización vigente, board MW acreditado
   antes del input, fuente identificada y despacho registrado de esa operación.
   Un receipt ADB retornado acredita transporte, nunca consumo/efecto. El modelo
   conservador no admite receipts `not_sent`/`uncertain`; sólo conserva espera
   legacy en esos casos, sin ampliar permisos.
2. Heredar un deadline absoluto del presupuesto de observación del owner. No
   crear otro timeout acumulativo ni reiniciar deadline por progreso.
3. Para adoptar loading: misma fuente/lifetime, secuencia nueva, captura posterior
   al retorno del despacho, edad válida en el mismo reloj y cobertura explícita
   de loading y de las dependencias MW/contextos/bloqueadores usadas. `None` no
   equivale a cobertura. El bound2s del modelo es ilustrativo del caller, no una
   nueva política productiva global.
4. Mantener siempre la evaluación original de postcondiciones y blockers.
   CLEAR/insufficient acreditados terminan la espera; blocker y Point Reward
   vuelven a sus owners existentes. Nunca esperar ausencia del spinner.
   **No exigir cobertura de loading para aceptar un terminal/blocker positivo
   acreditado independientemente**. La cobertura adicional sólo gatea progreso.
5. Contexto ajeno, overlay incompatible, AMBIGUOUS o rotación de fuente invalidan
   la adopción contextual y la pérdida queda latched para esa ventana. UNKNOWN
   aislado permite sólo observación pasiva dentro de la operación ya admitida;
   no resuelve BASE ni autoriza un input. Evidencia stale, futura, duplicada,
   predespacho o sin cobertura produce abstención, no progreso.
6. Positivo estático fresco anota progreso de esta operación. No acredita efecto,
   consumo, destino o readiness. Ausencia/desaparición conserva el comportamiento
   previo y no termina espera ni autoriza repetir Yes.

La señal física puede conservar su nombre experimental, pero la adopción sería
una actividad del owner post-Yes, sin `screen.loading`, registro global ni
activación en otros flows. La integración futura usaría `progress_observed` /
`progress_snapshot`; ese campo no reemplaza la espera pasiva ni suspende retries
por sí solo. MW Yes conserva su política de no-repetición cualquiera sea la señal.

La cobertura del prototype es metadata **modelada**, no telemetría inventada de
la captura: no se ejecutó un observer productivo durante HIL. El wiring futuro
debe declarar sólo capacidades realmente ejecutadas, preservar dependencias del
resolver y validar scopes; no estampar cobertura a partir de observaciones ausentes.

## Terminal, latencia y coste

Replay focal con readers existentes de MW y, en tres límites, con percepción
default intacta:

- Frame7: MW resuelto, sin terminal.
- Frame8: CLEAR visual y loading parcialmente ocluido. La confianza de CLEAR es
  .4458; todavía no es terminal acreditado por el resolver. Default también
  devuelve MW sin overlay. No se fuerza éxito desde la etiqueta humana.
- Frame13: CLEAR confianza.9987; default resuelve MW + popup CLEAR.

El tiempo de captura del primer CLEAR visible es+4.484s desde el retorno de Yes;
el sample13 acreditable es+7.094s. Esa diferencia de2.610s pertenece al reader/
notificaciones/muestreo actuales, no al loading; no se alteró el reader ni se
atribuye ahorro de Session. El contrato acepta un CLEAR acreditado aun con
loading positivo: cubierto en pruebas determinísticas, incluyendo falta de
cobertura del detector opcional. La coincidencia física loading+CLEAR visible
está adquirida; la acreditación automática en ese mismo frame no se afirma.

Primer loading detectado: source+0.594s, retrieval+0.609s respecto al retorno del
despacho. Inicio exacto acotado entre el último predespacho y ese primer positivo;
no es una medición de latencia intrínseca de algoritmo. Fin de visibilidad
entre+4.484 y+4.984s. Cadencia real1.45Hz, mediana gap.687s, máximo1.110s;
objetivo2Hz limitado por PNG/IO, sin muestras fabricadas.

Detector en memoria,200 iteraciones calientes por caso, sin decode/captura:

| Caso | Mediana ms/frame | p95 ms/frame |
| --- | ---: | ---: |
| Loading independiente | 2.572 | 3.503 |
| Loading ocluido, FN | 2.063 | 2.939 |
| Sin loading | .226 | .354 |

Modelo de contrato~.0114ms/inspección, p95.0118ms. No es tiempo del flow real.
Dos muestras consecutivas habrían demorado el primer progreso hasta+1.562s:
**+.953s**, sin FP MW observados que justifiquen esa demora. Mantener detección
estática por frame. Movimiento tampoco demuestra loading por sí solo; las
partículas Socket y los FP estáticos ya documentados siguen siendo límites.

Comparación sintética de scheduling, sin ejecutar acciones:

| Caso | Observaciones legacy/modelo | Análisis legacy/modelo | Nuevos inputs | Terminal |
| --- | --- | --- | ---: | --- |
| Loading sostenido | 4/4 | 4/4 | 0 | Mismo sample,t14 |
| Loading ausente | 4/4 | 4/4 | 0 | Mismo sample,t14 |
| Desaparece sin resultado | 4/4 | 4/4 | 0 | Ninguno; sigue bounded |
| Resultado tardío | 7/7 | 7/7 | 0 | Mismo sample,t17 |

Cada modelo parte de un Yes previamente autorizado/despachado; no hace otro.
Mismo sample terminal significa sin espera/poll/estabilidad adicional; hay coste
visual adicional de unos milisegundos por análisis. No se afirma latencia real
cero ni se extrapolan estas mediciones a Session.

## Validación y cierre

20 tests del prototype offline pasan: admisión, receipt, sostenido, ausente,
desaparición sin resultado, terminal con loading y sin cobertura de loading,
blocker, Point Reward, efecto tardío, UNKNOWN, AMBIGUOUS, fuente perdida, stale,
predespacho, futuro, secuencia duplicada, cancelación y deadline sin renovación.
El modelo no tiene source/acciones/loop de espera. Su diseño se corrigió por el
contrato explícito de prioridad terminal, usando tests sintéticos; éstos son
verificación de contrato, no un holdout físico ni una integración productiva.

Reproducción offline desde raíz:

```powershell
./tools/agent_run.ps1 artifacts.loading_central_2c_20261015.evaluate
./tools/agent_run.ps1 artifacts.loading_central_2c_20261015.contract_metrics
.\.venv\Scripts\python.exe -m pytest artifacts/loading_central_2c_20261015/test_context_replay.py -q -p no:cacheprovider
```

Artifacts: `existing_labels.json`, `independent_labels.json`, fuentes PNG y
`frames.jsonl`, `action.json`, corrección de procedencia, hojas de revisión,
`independent_evaluation.json`, `replay_evaluation.json`, caches, replay de límites
y contexto ajeno, prototype/tests/métricas y verificación de preservación.
No nueva dependencia ni cambio a los cinco archivos2B/capturador2A.

Alcance residual: una sola secuencia MW independiente, un dispositivo/aspecto;
otro personaje aporta variación pero no garantiza otros layouts/fondos. Los FP
globales persisten, un contexto ajeno no reconocido bajo UNKNOWN podría colarse,
y oclusión puede causar abstención/FN. Ninguna de esas limitaciones permite
retry: la utilidad es anotar progreso y continuar pasivamente dentro de límites.
WB START queda pendiente de validación propia. No se requiere repetir MW para
reacreditar esta secuencia ni se propone campaña por rutina.

Único documento nuevo fuera de artifacts: este informe. Flows, políticas de
retry, VerifiedTransition, RuntimeObserver.wait_until y contratos productivos
permanecen intactos. Sin commit/push ni migración productiva. Se detiene2C;
no se inicia integración ni otra fase automáticamente.
