# Contexto actual — Kritika FarmBot

**Estado:** preparación para el rediseño híbrido 0.2
**Última actualización:** 2026-08-22

## Objetivo

Kritika FarmBot busca automatizar actividades repetitivas de **Kritika: The White Knights** sobre un dispositivo Android físico. La automatización debe reconocer el estado del juego, ejecutar flows deterministas y realizar la interacción final mediante ADB.

## Por qué se rediseña

El enfoque legacy depende de una colección grande de templates, regiones, botones y coordenadas mantenidos manualmente. Ese modelo se volvió frágil y costoso ante cambios de UI, resoluciones diferentes y contenido nuevo. La versión 0.2 adoptará una percepción híbrida que permita conservar detectores locales rápidos sin exigir que cada situación posible esté codificada como un template específico.

## Estado real legacy

El estado previo al rediseño está preservado en el tag Git `legacy-pre-hybrid`.

La implementación existente contiene:

- captura H.264 mediante el server de scrcpy y decodificación con PyAV;
- almacenamiento del último frame como array BGR compatible con OpenCV;
- template matching y crops con OpenCV;
- un catálogo de 75 contextos en `bot/constants.py`;
- modelos `Contexto` y `Boton`;
- taps y swipes mediante ADB;
- un flow de Tower of Tribulations (TOT);
- un AdsManager standalone basado en UIAutomator2;
- herramientas manuales para capturar frames y templates.

## Qué funciona o conserva valor

- El pipeline conceptual `scrcpy → frame NumPy/OpenCV` es reutilizable.
- Las primitivas ADB son válidas como mecanismo final de interacción.
- OpenCV sigue siendo útil para preprocesamiento y detectores locales conocidos.
- La taxonomía de contextos, controles y actividades conserva conocimiento de dominio.
- El flow TOT conserva intención y reglas de negocio, aunque su implementación no sea reutilizable directamente.
- `bot/ads_manager.py` está aislado del flujo visual normal y conserva una estrategia distinta para anuncios externos.
- Las herramientas de adquisición de capturas pueden evolucionar hacia herramientas de dataset.

## Qué está roto o incompleto

- `python main.py` falla durante imports: `bot/flows.py` solicita funciones eliminadas de `bot/actions.py`.
- La geometría mezcla coordenadas relativas con bloques absolutos legacy, especialmente TOT.
- Los frames históricos son landscape `2712×1224`, mientras el runtime usa `adb wm size` como `(1224, 2712)` para escalar.
- El schema de botones está migrado solo parcialmente y no todos los consumidores aceptan el formato nuevo.
- Los 75 contextos tienen la misma prioridad efectiva.
- No hay outcomes reales configurados.
- Faltan templates activos utilizados por TOT; solo existen variantes históricas `960x540`.
- No hay loop global de percepción, resolución y decisión.
- No hay tests automatizados ni baseline sin hardware.

No se reparará el runtime legacy como paso previo al rediseño. Sus problemas se abordarán únicamente cuando una fase futura extraiga una pieza reutilizable o migre un caso de uso.

## Decisiones cerradas para 0.2

### Plataforma y geometría

- La interfaz soportada es landscape.
- Deben admitirse resoluciones variables.
- La geometría debe derivarse de las dimensiones reales de cada frame (`frame.shape`), no de una resolución fija obtenida con `adb wm size`.
- Las coordenadas normalizadas deben permanecer en `[0,1]`.

### Captura y dispositivo

- scrcpy seguirá proporcionando los frames.
- ADB seguirá ejecutando las acciones finales sobre el dispositivo.
- Captura, percepción e interacción deberán quedar separadas y testeables de forma independiente.

### Percepción

- OpenCV no se considera legacy por sí mismo.
- Los detectores locales rápidos atenderán estados o elementos conocidos cuando aporten valor.
- OCR se utilizará para valores dinámicos requeridos por los flows, como stamina o recursos.
- El VLM será un fallback infrecuente para situaciones desconocidas.
- El fallback VLM será provider-agnostic: podrá usar un proveedor externo o un modelo local sin contaminar las demás capas.
- La percepción producirá observaciones semánticas, no decisiones de navegación.

### Estado y negocio

- Un `ContextResolver` consumirá observaciones semánticas y resolverá el estado del juego.
- Los flows conservarán lógica e intención de negocio mayormente deterministas.
- Los flows no deberán ejecutar template matching ni comandos ADB directos.
- Las interrupciones y prioridades se representarán semánticamente, no únicamente por orden de templates.

### AdsManager

- `bot/ads_manager.py` seguirá formando parte del proyecto.
- UIAutomator2 se mantiene separado de la percepción normal del juego.
- En 0.2 actuará como subsistema de interrupción externa: detecta/gestiona un anuncio y devuelve el control al juego.

## Assets y datos preservados

- Los assets runtime activos bajo `assets/ui/` están disponibles para versionado selectivo.
- Los 28 assets de `assets/ui/960x540/` se conservan localmente como referencia y material histórico, pero no son assets runtime activos ni se versionan en el repositorio normal.
- Existen 173 capturas landscape en `screencaps/`, aproximadamente 527 MiB en total.
- Las capturas son un dataset legacy potencialmente valioso. Permanecen intactas e ignoradas por Git; todavía no tienen manifest ni labels formales.
- El catálogo monolítico de `bot/constants.py` se conserva por su conocimiento histórico, pero no será el modelo de configuración de 0.2.

## Tests y estado del rediseño

Los archivos actuales de `testing/` son scripts manuales ligados a hardware; no constituyen una suite automatizada. Los primeros tests sin teléfono forman parte de la Fase 1.

La arquitectura híbrida todavía no está implementada. La Fase 0 solo preserva el legacy, establece fuentes documentales confiables y prepara el repositorio para comenzar el trabajo incremental.
