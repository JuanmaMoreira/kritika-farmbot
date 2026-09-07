# Character Identity mínima v1

Implementada sobre `main@454d11129d7d9b7c15b550bcae817f3c711ff139`, pendiente de revisión; sin commit ni push. Identidad observacional y no fatal para Run Session. No cambia intención, orden ni policy de gameplay.

## Reconstrucción y diseño elegido

`CharacterContext` ya contenía `name` y `name_confidence`; `SessionRunner._character_context` ya aislaba excepciones del factory. La composition root `ProductiveRuntime.run_session` construía el runner sin ese factory. Los eventos de inicio de flow, business y cierre de personaje ya transportaban `context.name`. `build_session_report` ignoraba ese dato y forzaba `Character N`; Tk presentaba el renderer sin reconocer ni clasificar identidad.

V1 usa `LobbyNameRecognizer` en `bot/character_identity.py`, con `RapidOcrEngine` existente: CPU, modelos locales, inicialización lazy, reconocimiento sin detector ni clasificador OCR. Lee la ROI común `(0.080, 0.020, 0.190, 0.062)` del nombre personal del HUD. Geometría derivada de `frame.shape` mediante `relative_region_to_pixels`, sin resize ni preprocessing adicional. El backend recibe una copia del recorte para proteger el frame compartido.

Pipeline: `RuntimeSnapshot Lobby limpio → OCR personal_name → lookup exacto / variante cerrada validada → CharacterIdentity → CharacterContext(name=class_name, name_confidence=score) → eventos/resultados → SessionReport → GUI/CLI`.

## Lookup, Unicode y confianza

El mapping inmutable `PERSONAL_NAME_CLASSES` preserva únicamente las 28 asociaciones autoritativas del usuario; el manifest y tests conservan también los nombres completos. Primero se consulta la clave íntegra, con Unicode y capitalización exactos. Sólo si falta se consulta `KNOWN_LOBBY_NAME_OCR_VARIANTS`, una tabla inmutable separada de cuatro outputs completos observados para tres nombres. No hay strip, normalización Unicode, transliteración, casefold, sustitución general de caracteres, comparación parcial ni fuzzy matching. `Drakennn15` y `Drakennn17` conservan tres `n`; `DRAKEN四R` y `DRAKEN四BD` son claves diferentes.

Ambas ramas exigen una única línea OCR con score **≥ 0,95** y string completo conocido, exclusivamente bajo `RESOLVED + screen.lobby + overlays vacíos`. El fallback cerrado no puede saltarse esos guards ni aumentar el score. UNKNOWN, AMBIGUOUS, otro contexto, metadata multiline, texto extra/desconocido, confidence insuficiente y excepciones devuelven ausencia de identidad. La ausencia se adapta a `CharacterContext()` y el report muestra `Character N`. El nombre personal no se agrega a eventos/logs: sólo se propaga la clase necesaria para presentación.

El score del backend es evidencia de reconocimiento, **no una probabilidad calibrada** de identidad. Los errores conocidos también pueden tener scores altos; el umbral solo no los resuelve. No se adopta NCC closed-set: los márgenes previos pequeños entre nombres cercanos no justifican agregar templates ni adjudicar un nombre por top-1.

La reevaluación de los nueve raws confirmó exactamente estas variantes, sin necesitar reconocimiento visual de los glifos:

| Output OCR completo | Nombre Unicode canónico | Clase | Raws / scores observados |
| --- | --- | --- | --- |
| `DRAKEN-BK` | `DRAKEN一BK` | Berserker | 3: 0,96229; 0,96383; 0,96239 |
| `DRAKEN-DB` | `DRAKEN二DB` | Demon Blade | 1: **0,91536**, rechazado por score |
| `DRAKENDB` | `DRAKEN二DB` | Demon Blade | 2: 0,98155; 0,98154 |
| `DRAKEN=BB` | `DRAKEN三BB` | Burst Breaker | 3: 0,97420; 0,97228; 0,96989 |

Los sufijos BK/DB/BB forman parte de las claves completas; nunca se usan aisladamente para asignar clase. Por ejemplo, `DRAKEN=BK`, `DRAKEN-BB`, `DRAKENBK`, sufijos contaminados o texto adicional quedan fuera. La variante `DRAKEN-DB` está documentada por un único raw y no tiene positivo observado por encima del umbral: se incluye como output conocido, pero su único caso real sigue rechazado. El raw es `20260907T000649_367351Z_draken2db_seq1.png`; sus hashes y ruta completa permanecen en el manifest.

El resultado conserva siempre el nombre Unicode autoritativo y el score OCR original. No hay templates ni scoring parcial; no aplica margen NCC. El menor score aceptado entre los 84 raws es **0,96229**, 0,01229 por encima del umbral. Los 25 nombres exactos anteriores conservan sus 75/75 lecturas sin usar la tabla de variantes.

## Lifecycle e integración

El factory se invoca una vez por personaje después de la primera comprobación de precondición y antes del primer `flow.started`/`flow.run`. Antes se invocaba al entrar al personaje, cuando no existía una observación inicial reutilizable. Se conserva exactamente la secuencia de precondiciones, observaciones, waits, navegación, flows, postcondiciones y advances existente.

Durante Run Session, `_current_clean_context` conserva temporalmente el snapshot limpio que ya obtuvo para su caller. Limpia el anterior **antes de cada probe**, incluso si éste falla; actualiza el candidato con el frame settled de su wait normal. El factory consume y libera ese candidato. El recognizer se crea dentro del seam protegido, se reutiliza sólo durante esa sesión y no conserva identidad del personaje anterior. Un `finally` desactiva la adquisición y libera el snapshot al terminar o fallar la sesión. No existe captura nueva, lectura periódica, retry OCR ni input de identidad.

Limitación deliberada: si la primera precondición termina en Pets/Guild/u otro contexto, o su recovery no entrega candidato, se mantiene `Character N`. Esto incluye un plan que empieza en Lobby pero cuya primera precondición navega directamente a Pets/Guild. No se regresa a Lobby para obtener identidad, ni se busca otra oportunidad durante ese personaje. El plan default empieza con precondición Lobby y sí consume su HUD.

`session.character.started` conserva su posición anterior a la precondición y lleva `character_name=None`; no se retrasa ni republica. `flow.started`, business events y `session.character.completed` usan la clase cuando se obtuvo. No se agregan eventos ni se reescriben eventos históricos. El campo `name` del resultado representa clase, no nombre personal ni índice.

SessionReport toma `character_context.name` cuando existe, con fallback `Character N`, sin repetir lookup o umbrales. Confía en el contexto suministrado; también respeta nombres provistos por callers legacy. GUI sigue consumiendo el report/model y renderer; no hay OCR en Tk. El indicador de progreso conserva `índice / total`. Run Flow Once/Run Selected Flows conservan sus contratos y no adquieren identidad ni generan un report de sesión.

## Evidencia y validación

`datasets/character_identity_manifest.json` conserva las 84 rutas raw, SHA-256, ground truth personal/clase y split por personaje: primer frame de calibración, otros dos de validación. Son frames separados de una misma adquisición, **no sesiones independientes**. No se entrenó un matcher. La partición se conserva para trazabilidad; las variantes se verificaron en los nueve raws de la familia según el pedido, por lo que esta mejora no representa una prueba ciega sobre variantes nunca vistas.

| Conjunto | Correctas | Fallback | Clase incorrecta |
| --- | ---: | ---: | ---: |
| Calibración | 27/28 | 1 | 0 |
| Validación | 56/56 | 0 | 0 |
| Total | 83/84 (98,8 %) | 1 | 0 |

Delta respecto de OCR exacto: **75 → 83 correctas**, **9 → 1 fallbacks**, **0 → 0 incorrectas**. Los 28 personajes tienen al menos dos positivos; 27 obtienen 3/3. Berserker y Burst Breaker pasan 3/3, Demon Blade 2/3. No se declara 84/84: el score 0,91536 impide aceptar el raw restante bajo el contrato acordado. Todos los 84 frames resuelven Lobby limpio con la percepción productiva. La ROI está fuera del chat observado `[0.44, 0.12, 0.85, 0.21]`, documentado con evidencia real en `datasets/socket_inventory_relief_semantic_manifest.json`; no se promovió un landmark que dependiera de contenido ocluido.

Se reevaluó el recognizer con **404 frames curados existentes**: 388 contextos incompatibles rechazados y 16 Lobby sin ground truth personal, reportados como no puntuables para identidad. En esos 16 Lobby hay cuatro lecturas exactas, once por variantes (diez `DRAKEN=BB` y una `DRAKENDB`) y un fallback por texto contaminado `3Drakenn25`; las once nuevas etiquetas son resultados observados, no aciertos verificados contra ground truth personal. Se añadieron **18 negativos de contexto** disponibles y no duplicados desde los manifests de portal, Quick Menu de World Boss y sentinel de Character Select: todos rechazados. Los 406 negativos de contexto combinados no producen identidad. No se inventó ground truth de nombres para los 16 Lobby ni se afirmó generalización a nombres desconocidos arbitrarios. La evaluación usa 38.962 pares detector/frame: 37.576 hits y 1.386 pares nuevos, sin invalidaciones ni reconstrucción completa de cache.

Los **18 recortes / 558.308 bytes** existentes pasan **18/18** en tests y en la evaluación: dos frames de validación por caso crítico, incluidos Latin, nombres de tres `n`, `一/二/三`, `四R/四BD` y `Drakenn22`. Viven en `tests/fixtures/identity_name`, con hashes y referencia al raw; los tests reales usan RapidOCR. No son assets runtime. No se recortó ni purgó evidencia en esta mejora: los 84 raws y los 18 fixtures permanecen intactos. El reporte completo regenerable queda en `artifacts/identity_name_evaluation.json`, ahora con rama exacta/variante, resultados por nombre y fixtures.

Tests deterministas cubren el mapping completo, las cuatro variantes y su Unicode canónico exacto, confusables, nombres cercanos/desconocidos, sufijos contaminados, coincidencias parciales, thresholds, multiline, guards de contexto, errores de ejecución/inicialización, no mutación del frame, no reutilización de candidato viejo, factory una vez, eventos/resultados, SessionReport y GUI. Comparaciones con baseline verifican igual orden/cantidad de observaciones, llamadas de flows, pre/postcondiciones y advances con éxito exacto, variantes, desconocido y excepción del OCR. Los tests GUI verifican render desde modelo y controller sin OCR en Tk. La mejora no modifica lifecycle ni código de input, flows o Rotation.

```powershell
./tools/agent_run.ps1 tools.identity_name_evaluation --corpus
./tools/agent_run.ps1 pytest -q tests/test_character_identity.py tests/test_session.py tests/test_session_report.py tests/test_productive_runtime.py tests/test_gui_controller.py tests/test_gui_functional.py tests/test_structured_observability.py tests/test_failure_evidence.py
./tools/agent_run.ps1 pytest -q
git diff --check
```

Validación final tras el fallback cerrado: **314 tests dirigidos verdes** y **1730/1730 tests hardware-free verdes en 242,86 s**. Delta de esta mejora: 60 casos netos adicionales frente a los 1670 previos; 133 sobre el baseline `454d111`. `git diff --check` limpio. Sin pruebas físicas, commit ni push; los cuatro scripts raíz ajenos permanecen preservados.

La opción `--curate` regenera manifest y recortes desde los raws preservados. No borra evidencia. La evaluación verifica los hashes raw antes de usar sus labels. Los tests de fixtures no necesitan raws, dispositivo, red ni escritorio.

## Límites y follow-ups

El muestreo productivo consiste en un frame ya observado, una vez por personaje; no agrega consenso temporal ni capturas para aumentar cobertura. Los pares curados evitan validar únicamente sobre un frame, pero no prueban generalización a otra resolución, temporada/render ni a nombres desconocidos arbitrarios que OCR pudiera confundir con uno conocido o con una variante. La tabla es específica del roster autoritativo y no una regla reutilizable para otros nombres. La baja confianza del primer raw de Demon Blade conserva fallback.

Llegar a 84/84 requeriría resolver la baja confianza del raw restante mediante evidencia o un diseño posterior explícito; no se baja el umbral ni se agrega preprocessing, retry o template para forzar ese número. Smokes físicos quedan para el usuario desde GUI después de revisión y eventual commit. Eligibility, Arena, búsqueda de personaje, perfiles complejos, rediseño de Character Select y Rotation identity-aware no comenzaron.
