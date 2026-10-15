# Loading central — promoción 2B detenida

> **Informe histórico de fase 2B.** La promoción global sigue rechazada. La
> adopción contextual posterior, exclusivamente en MW Yes, está descrita en
> [el contrato vigente](MONSTER_WAVE_SKIP.md). Las afirmaciones de estado que
> siguen corresponden al cierre de 2B. La reproducción offline requiere el
> corpus local ignorado; el runtime no depende de ese corpus ni del manifest.

**Estado: EXPERIMENTAL, no aprobado para runtime.** Evaluación offline de
2026-10-15 sobre `rebuild/stable-baseline`, HEAD `2686f0e`. El gate encontró dos
falsos positivos confirmados en Trading Center. Por la condición explícita del
encargo 2B, se detuvo la integración en MW sin modificar sus transiciones.

## Detector y contrato propuesto

`bot/perception/global_loading.py` conserva el algoritmo de fase 2A: prefiltro
HSV H75–105, S≥100,V≥80, fracción≥.028 en ROI(.47,.43,.53,.58), seguido de
Hough sobre ROI(.44,.40,.56,.60), núcleo cyan y arco cyan. Geometría usa
`frame.shape` y `relative_region_to_pixels`; sólo se reescala la ROI a una
altura de análisis equivalente a600, manteniendo aspecto. No se modificaron
umbrales después de observar el holdout ni se exige persistencia de dos frames.

La API experimental emite únicamente `activity.global_loading` con región y
fuente LOCAL_CV. Su grado fijo .90 no es una probabilidad calibrada. La intención
semántica es evidencia visual positiva de loading; **los falsos positivos
encontrados impiden considerar satisfecha esa intención en producción**.
No emitir observación no acredita ausencia, consumo, efecto ni readiness.
No produce `screen.loading`, resuelve BASE, autoriza inputs ni retries.

No se exportó desde el catálogo ni se añadió a `build_default_perception`,
scopes, observers o factories. Importar el módulo es inerte: no hay hardware,
capturas, IO, threads ni conexión a flows.

## Evidencia y separación

[Manifest reproducible](../datasets/global_loading_manifest.json):148 pares
detector/frame, referencias a originales existentes y SHA-256 verificados.
No se copiaron ni adquirieron imágenes del teléfono.

| Split | LOADING | NO_LOADING | UNCERTAIN | Resultado |
| --- | ---: | ---: | ---: | --- |
| Desarrollo fase2A | 21 | 69 | 9 | 21TP,0FN,69TN,0FP |
| Negativos adicionales de adquisiciones distintas | 0 | 36 | 1 | 34TN,2FP |
| Supplement Combine, misma adquisición que2A | 0 | 12 | 0 | 12TN,0FP |

Todos los frames de2A son **desarrollo**, incluidos aquellos usados para
templates o geometría. No se presentan como holdout positivo. Los adicionales
provienen de Socket Inventory Relief, Lobby20260823, Inventory Relief,
Pet Combine, Treasure, Trading y Equipment Sell. Se excluyeron hashes repetidos
frente a2A y entre candidatos. Los frames de cada grupo están correlacionados;
36 negativos no equivalen a36 episodios independientes. No hay holdout positivo
independiente en esta fase.

Las etiquetas se revisaron visualmente antes de ejecutar el detector; no se
dedujeron de predicciones. El flash blanco de Socket carece de visibilidad para
afirmar ausencia y permanece UNCERTAIN. Los nueve ambiguos de2A también se
preservan fuera de las matrices. Otros Socket Success/dark-stage, textos claros,
modals, efectos Lobby y Combine son negativos visibles sin loading.

## Fallo causal y gate

Falsos positivos:

- `screencaps/semantic/trading-center/general-bottom/01.png`
- `screencaps/semantic/trading-center/general-mid/05.png`

Son dos frames del mismo contexto visual: íconos de materiales y Sapphire sobre
filas blancas. Hough aproxima círculos en el contorno de los iconos; sus pixels
cyan cumplen núcleo/arco, aunque el círculo esté desplazado y parcialmente
cortado por el borde de la ROI. El prefiltro encuentra cyan suficiente.
No hay animación loading en las imágenes revisadas.

Por ejemplo, a escala de análisis el candidato(x112.5,y14.5,r28.6) tiene
fracción cyan de núcleo.5234 y de arco.0522, ambas superiores a los límites.
Otro candidato(x112.5,y93.5,r23) también supera ambos límites. La condición
actual admite círculos parciales; esto demuestra una insuficiencia de identidad
geométrica, no un error de etiqueta ni una razón para subir confianza.

El 2/36 de FP observado es5.56% en este slice negativo correlacionado, no una
estimación de precisión de Session. El algoritmo ya falla un requisito relevante
de la señal propuesta. No se intentó corregirlo con excepciones por pantalla,
gates MW o nuevos thresholds derivados del holdout.

El evaluator termina con error deliberado ante cualquier FP confirmado y deja
el informe escrito para revisión. Un eventual ajuste necesitaría desarrollo
separado y nuevos negativos reservados; estos casos pasan a regresiones conocidas.

## Coste y validación

200 iteraciones calientes por caso, sin captura, lectura PNG ni resolución:

| Frame | Mediana ms/frame | p95 ms/frame |
| --- | ---: | ---: |
| Loading MW | 2.170 | 2.866 |
| Negativo difícil Combine | 1.265 | 1.576 |
| Negativo quieto CLEAR | .236 | .251 |

La diferencia entre casos refleja que el prefiltro evita Hough cuando no hay
cyan suficiente. Son mediciones locales de detector, sin ahorro de Session ni
inferencia de latencia MW.

Evaluación final incremental:148 pares evaluados en8.11s;148 invalidaciones del
cache anterior por marcar el módulo experimental en su docstring. No cambiaron
umbrales ni resultados. El fingerprint existente incluye el archivo fuente
completo; no se creó infraestructura de cache nueva.

Validación dirigida:6 tests pasan para actividad positiva real y escalado,
propagación de sequence/timestamp por PerceptionEngine, actividad sin autoridad
de pantalla, no-observación sin autoridad negativa, blanco sin cyan y exclusión
del detector de percepción default. Warning ambiental de permisos de
`.pytest_cache`; no afectó el resultado. `git diff --check` sin errores.

Reproducción desde raíz:

```powershell
./tools/agent_run.ps1 tools.global_loading_evaluation
.\.venv\Scripts\python.exe -m pytest tests/test_global_loading_experimental.py -q
```

La primera orden debe fallar el gate mientras persistan los dos FP. Usa el
evaluator incremental existente; labels/decisión se recalculan fuera del cache.
El corpus local de fase2A debe conservarse para esas referencias del manifest.

## Alcance final

Nuevos archivos: detector experimental, manifest, evaluator, tests directos y
este informe. Artifacts derivados locales en
`artifacts/loading_central_2b_20261015`: `evaluation.json`, cache,
`false_positives.json`, ROIs anotadas, hojas de revisión y fingerprint congelado.
Tamaño aproximado1.69MB antes de este cierre; ninguna adquisición nueva.

No se promovió contrato funcional ni se tocó VerifiedTransition, MW Yes, WB
START, otros flows, RuntimeObserver.wait_until, cancelación, freshness, scopes
productivos, estabilidad, deadlines o postcondiciones. Por eso no corresponde
medir un camino MW cambiado ni agregar regresiones de una integración ausente.
Las regresiones MW solicitadas quedan pendientes junto con esa integración;
no se ejecutaron suites de gameplay ajenas a este experimento.

El archivo no versionado `tools/loading_central_acquisition.py` ya estaba al
inicio, pertenece a fase2A y se preservó intacto. Sin commit, push ni hardware.
Se detiene fase2B en el gate perceptivo, conforme al encargo.
