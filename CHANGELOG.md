# Changelog

Todos los cambios importantes de este proyecto se documentan acá.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es/1.0.0/).

---

## 0.1.2 - 2026-04-05

### Agregado
- `tools/script.py`: módulo de skip automático de ads usando UIAutomator2.
  Detecta si el dispositivo está en una ad verificando el package activo.
  Busca el botón de cierre por árbol de vistas (content-desc y text) con
  keywords: "close", "skip", "dismiss", "continue".
  Scoring por posición (preferencia arriba-derecha) para seleccionar el
  mejor candidato cuando hay múltiples elementos coincidentes.
  Loop con timeout de 90 segundos y pausa entre intentos.

---

## 0.1.1 - 2026-04-04

### Agregado
- `context.py`: clase `Boton` — encapsula coordenadas, outcomes y timeout de cada botón.
  Outcomes posibles: `"ok"` (continuar), `"retry"` (reintentar click), `"abort"` (abortar flow).
- `context.py`: atributo `prioridad` en `Contexto` (default 1). Controla el orden de evaluación
  cuando varios contextos son visibles simultáneamente (popups, confirmaciones).
- `context.py`: `_contextos_por_prioridad` — lista pre-ordenada usada por `detectar_contexto()`
  para evaluar primero los contextos de mayor prioridad.
- `context.py`: `detectar_menu_abierto()` — detecta si algún menú del contexto activo está
  abierto, reutilizando el screenshot de `actualizar_contexto()`.

### Cambiado
- `context.py`: `Contexto` construye objetos `Boton` automáticamente desde `constants.py`.
  Compatible con formato de tupla simple `(x, y)` para botones sin outcomes definidos.
- `context.py`: `actualizar_contexto()` ahora detecta contexto, subcontexto y menú abierto
  en una sola captura.
- `actions.py`: `click_boton()` reemplaza a `navegar_a()` y `esperar_contexto()`.
  Clickea, espera el outcome del botón y maneja reintentos internamente.
- `constants.py`: formato de botones extendido — acepta dict con `coords`, `outcomes` y
  `timeout`, además del formato anterior de tupla simple (retrocompatible).
- `screen.py`: `conectar_dispositivo()` detecta la resolución real del dispositivo con
  `adb wm size` y la almacena en `_resolucion_actual` para escalar durante la sesión.
- `screen.py`: coordenadas y regiones ahora se escalan automáticamente desde `RESOLUCION_BASE`
  a la resolución real del dispositivo en `find_image_on_screen`, `find_all_on_screen`,
  `click_at` y `swipe_from_to`.
- `tools/asset_capture.py`: coordenadas de salida ahora en formato relativo (0.0–1.0).
- `constants.py`: `RESOLUCION` renombrada a `RESOLUCION_BASE`.

### Eliminado
- `actions.py`: `navegar_a()` y `esperar_contexto()` — reemplazadas por `click_boton()`.

---

## 0.1.0 - 2026-04-02

### Agregado
- `screen.py`: clase `ScrcpyStream` — mantiene una conexión activa con el server de scrcpy
  y consume el stream H.264 en un thread de background. Expone `ultimo_frame()` para acceso
  instantáneo al frame más reciente sin bloquear.
- `screen.py`: instancia global `_stream` de `ScrcpyStream`, iniciada por `conectar_dispositivo()`.
- `constants.py`: `SCRCPY_SERVER_PATH` — ruta al jar del server de scrcpy.
- `tools/screencap_batch.py`: herramienta para capturar frames en vivo con SPACE y guardarlos
  en `screencaps/batch/`. Companion de `asset_capture.py` para trabajar sin reconectar al celu.
- `tools/asset_capture.py`: modo carpeta — recibe una carpeta como argumento y procesa las
  imágenes de disco en orden, en lugar de capturar desde el dispositivo.

### Cambiado
- `screen.py`: `capturar_pantalla()` reemplaza la captura vía `adb exec-out screencap -p`
  por lectura del último frame del `ScrcpyStream`. Latencia reducida de ~500ms a ~4ms.
  La interfaz pública es idéntica — el resto del bot no requiere cambios.
- `screen.py`: `conectar_dispositivo()` reemplaza `hd-adb connect` por verificación de
  dispositivo USB con `adb devices` e inicio del stream de scrcpy.
- `screen.py`: `click_at()` y `swipe_from_to()` migrados de `hd-adb` a `adb` estándar.
  Comandos de input sin cambios funcionales.
- `constants.py`: `DISPOSITIVO_ADB` actualizado de IP TCP (`127.0.0.1:5555`) a serial USB
  del dispositivo físico.
- `constants.py`: `RESOLUCION` actualizada de `(960, 540)` (BlueStacks) a `(1224, 2712)`
  (Xiaomi POCO, landscape).
- `tools/asset_capture.py`: `capturar_screencap()` reemplazada por `capturar_desde_dispositivo()`
  usando scrcpy en lugar de `adb screencap + pull`.
- `tools/asset_capture.py`: formato de salida de imagen y región corregido a sintaxis de dict
  (`"imagen":`, `"region":`) lista para pegar directamente en `constants.py`.
- `tools/asset_capture.py` y `tools/screencap_batch.py`: rutas de salida corregidas a
  absolutas relativas a la raíz del proyecto, independientes del directorio de ejecución.
- Todos los assets de `assets/ui/` recapturados en resolución `1224x2712` para el dispositivo físico.
  Los assets originales de `960x540` archivados en `assets/ui/960x540/`.

### Eliminado
- Dependencia de `hd-adb` — reemplazado por `adb` estándar en todos los comandos.
- Dependencia de BlueStacks — el bot corre contra un dispositivo físico por USB.

---

## 0.0.11 - 2026-03-29

### Agregado
- `constants.py`: `MENU_RAPIDO` — estructura unificada con imagen, región y botones
  del menú rápido. Reemplaza `COORDENADAS_MENU_RAPIDO`.
  - `screen.py`: `find_all_on_screen()` — encuentra todas las ocurrencias de un template
  en pantalla con supresión de no-máximos. Retorna lista de (x, y) ordenada por Y ascendente.
- `screen.py`: `swipe_from_to(x1, y1, x2, y2, duration_ms, delay)` — ejecuta un gesto
  de swipe vía ADB. `duration_ms` controla la velocidad (default 300ms).

### Cambiado
- `constants.py`: todos los contextos completados con botones, menus y subcontextos reales.
- `actions.py`: reescrito completamente. Tres funciones atómicas:
  `click_boton`, `click_boton_menu`, `click_boton_menu_rapido`.
  Usan el estado de `context.py` y los datos de `constants.py`.
  No toman screencap — asumen que el contexto ya fue detectado.

### Eliminado
- `constants.py`: campo `verificaciones` de todos los contextos y documentación.
- `constants.py`: `COORDENADAS_MENU_RAPIDO` reemplazado por `MENU_RAPIDO`.
- `context.py`: atributo `verificaciones` de la clase `Contexto`.

---

## 0.0.10 - 2026-03-29

### Agregado
- `constants.py`: claves `menus`, `subcontexto` y `verificaciones` en cada entrada de
  `CONTEXTOS_DEFINIDOS`. Vacías por defecto, con ejemplo comentado de subcontexto en `stage_normal`.
- `constants.py`: `INTERRUPCIONES_GLOBALES` — dict para imprevistos técnicos gestionados por `watchdog.py`. Vacío con ejemplo comentado.
- `context.py`: variables globales `subcontexto_actual` y `menu_abierto`.
- `context.py`: `detectar_subcontexto()` — detecta la variante activa de un contexto reutilizando el screenshot ya tomado.
- `context.py`: `registrar_menu_abierto()` y `registrar_menu_cerrado()` — para que `actions.py` actualice el estado del menú.
- `context.py`: funciones de consulta `obtener_subcontexto()`, `obtener_menu_abierto()`, `hay_menu_abierto()`.
- `tools/debug_context.py`: script one-shot de debugging de detección.
  Toma un screencap, corre todos los contextos y subcontextos definidos y muestra
  una tabla de confianzas en consola (score, threshold, ✔/✘/⚠) y una ventana OpenCV
  con los matches marcados en verde (contexto) y celeste (subcontexto).
  Assets faltantes se reportan sin crashear.

### Cambiado
- `context.py`: `actualizar_contexto()` ahora detecta contexto y subcontexto en una sola captura, y resetea `menu_abierto`.
- `context.py`: clase `Contexto` acepta los nuevos campos `menus`, `subcontexto` y `verificaciones`.
- `constants.py`: `menu_rapido_tipo` es `None` en contextos sin menú rápido (antes ausente).

### Corregido
- `screen.py`: `conectar_dispositivo()` agrega `sleep(1)` después de una conexión
  nueva para evitar race condition entre el connect y el primer comando ADB.
  No aplica cuando ya estaba conectado ("already connected").

---

## 0.0.9 - 2026-03-29

### Agregado
- `context.py`: atributo `verificaciones` en la clase `Contexto` (default `{}`).
  Dict de assets para confirmar que una acción tuvo efecto (ej: que un menú se abrió).
  No participa del loop de detección de contexto — lo consumen los flujos/acciones.
- `constants.py`: campo `verificaciones` documentado en el encabezado de `CONTEXTOS_DEFINIDOS`.
- `constants.py`: ejemplo comentado de `verificaciones` en `stage_normal`
  (`world_map_abierto`) como referencia para completar al capturar los assets.

---

## 0.0.8 - 2026-03-29

### Agregado
- `screen.py`: función `swipe_from_to(x1, y1, x2, y2, duration_ms, delay)` — ejecuta un gesto
  de swipe vía ADB. `duration_ms` controla la velocidad (default 300ms).
- `context.py`: variable global `subcontexto_actual` — almacena el valor de subcontexto
  detectado junto al contexto activo, o `None` si no aplica.
- `context.py`: función `detectar_subcontexto(contexto_nombre, screenshot_img)` — compara
  los templates de cada valor posible del subcontexto usando el screenshot ya capturado,
  sin tomar una nueva captura.
- `context.py`: función `obtener_subcontexto()` — consulta el valor actual de `subcontexto_actual`.
- `constants.py`: campo `subcontexto` en `stage_normal` (tipo `"episodio"`, valores 1-14 a completar)
  y en `tot` (tipo `"torre"`, valores `"fisica"` y `"magica"` a completar).
- `constants.py`: documentación del campo `subcontexto` en el encabezado de `CONTEXTOS_DEFINIDOS`.

### Cambiado
- `context.py`: `detectar_contexto()` ahora retorna `(nombre, screenshot_img)` en lugar de
  solo el nombre, para reutilizar la captura en `detectar_subcontexto` sin tomar dos screenshots.
- `context.py`: `actualizar_contexto()` ahora llama a `detectar_subcontexto` automáticamente
  si el contexto detectado lo requiere, y retorna `(contexto, subcontexto)`.
- `context.py`: atributo `subcontexto` agregado a la clase `Contexto` (default `None`).
  Los contextos sin subcontexto no necesitan declarar el campo.

---

## 0.0.7 - 2026-03-29

### Agregado
- `constants.py`: campo `botones` en cada entrada de `CONTEXTOS_DEFINIDOS` — coordenadas `(x, y)` de botones únicos de cada contexto. Vacío por ahora, se irá completando.
- `constants.py`: `MENU_RAPIDO_OFFSET` — offset `(dx, dy)` por tipo de menú rápido, para manejar el desplazamiento del lobby respecto al default sin duplicar coordenadas.
- `context.py`: atributo `botones` en la clase `Contexto`, leído automáticamente desde `CONTEXTOS_DEFINIDOS`.
- `tools/asset_capture.py`: modo 3 (botones) — click izquierdo sobre cada botón registra su nombre y coordenadas `(x, y)`, imprime la línea lista para pegar en `botones{}` o `COORDENADAS_MENU_RAPIDO`. Click derecho termina el modo. Tecla `S` para saltar cualquier paso.

### Cambiado
- `constants.py`: `COORDENADAS_MENU_RAPIDO` simplificado a un único dict plano (sin claves `"lobby"` y `"default"` duplicadas). El desplazamiento por contexto se maneja con `MENU_RAPIDO_OFFSET`.
- `context.py`: reimporta `CONTEXTOS_DEFINIDOS` desde `constants.py` y construye `contextos_definidos` automáticamente con un dict comprehension.

---

## 0.0.6 - 2026-03-29

### Agregado
- `screen.py`: función `conectar_dispositivo()` — conecta `hd-adb` al dispositivo definido en `DISPOSITIVO_ADB`. Debe llamarse una vez al inicio antes de cualquier captura o click.
- `tools/asset_capture.py`: herramienta interactiva para capturar assets y regiones de búsqueda.
  - Conecta ADB automáticamente al iniciar.
  - Toma un screencap del dispositivo.
  - Primer rectángulo (verde): seleccionás el template, pedís nombre, se guarda en `assets/ui/`.
  - Segundo rectángulo (azul): seleccionás la región de búsqueda, imprime la línea `region=` lista para pegar en `constants.py`.
  - Tecla `R` para nuevo screencap, `Q` para salir.

### Cambiado
- `constants.py`: agrega `CONTEXTOS_DEFINIDOS` — diccionario con todos los datos de detección de cada contexto (imagen, region, threshold, menu_rapido). Es la única fuente de verdad para agregar o modificar contextos.
- `context.py`: ya no define los datos de los contextos inline. Los lee desde `CONTEXTOS_DEFINIDOS` en `constants.py` y construye los objetos `Contexto` automáticamente.
- `tools/asset_capture.py`: ya no tiene `DISPOSITIVO_ADB` hardcodeado — lo importa desde `bot.constants`.
- `screen.py`: `capturar_pantalla()` ahora se comporta distinto según `DEBUG`.
  - `DEBUG=True`: guarda el screencap en disco en `screencaps/` (comportamiento anterior).
  - `DEBUG=False`: captura directo a memoria con `subprocess.PIPE` + `np.frombuffer` + `cv2.imdecode`, sin tocar disco. Retorna `(None, imagen)`.

### Pendiente (no implementado aún)
- `ASSETS_DIR` en `asset_capture.py` todavía está hardcodeado. Moverlo a `constants.py` cuando haya más rutas de assets que centralizar.

---

## 0.0.5 - 2026-03-29

### Agregado
- `screen.py`: función `conectar_dispositivo()` — conecta `hd-adb` al dispositivo definido en `DISPOSITIVO_ADB`. Debe llamarse una vez al inicio antes de cualquier captura o click.
- `tools/asset_capture.py`: herramienta interactiva para capturar assets y regiones de búsqueda.
  - Conecta ADB automáticamente al iniciar.
  - Toma un screencap del dispositivo.
  - Primer rectángulo (verde): seleccionás el template, pedís nombre, se guarda en `assets/ui/`.
  - Segundo rectángulo (azul): seleccionás la región de búsqueda, imprime la línea `region=` lista para pegar en `constants.py`.
  - Tecla `R` para nuevo screencap, `Q` para salir.

### Cambiado
- `screen.py`: `capturar_pantalla()` ahora se comporta distinto según `DEBUG`.
  - `DEBUG=True`: guarda el screencap en disco en `screencaps/` (comportamiento anterior).
  - `DEBUG=False`: captura directo a memoria con `subprocess.PIPE` + `np.frombuffer` + `cv2.imdecode`, sin tocar disco. Retorna `(None, imagen)`.

### Pendiente (no implementado aún)
- Mover rutas de assets y regiones de `context.py` a `constants.py`.

---

## 0.0.4 - 2026-03-29

### Agregado
- `tools/asset_capture.py`: herramienta interactiva para capturar assets y regiones de búsqueda.
  - Toma un screencap del dispositivo automáticamente.
  - Primer rectángulo (verde): seleccionás el template, pedís nombre, se guarda en `assets/ui/`.
  - Segundo rectángulo (azul): seleccionás la región de búsqueda, imprime la línea `region=` lista para pegar en `constants.py`.
  - Tecla `R` para nuevo screencap, `Q` para salir.

### Cambiado
- `screen.py`: `capturar_pantalla()` ahora se comporta distinto según `DEBUG`.
  - `DEBUG=True`: guarda el screencap en disco en `screencaps/` (comportamiento anterior).
  - `DEBUG=False`: captura directo a memoria con `subprocess.PIPE` + `np.frombuffer` + `cv2.imdecode`, sin tocar disco. Retorna `(None, imagen)`.

### Pendiente (no implementado aún)
- Mover rutas de assets y regiones de `context.py` a `constants.py`.

---

## 0.0.3 - 2026-03-29

### Cambiado
- `screen.py`: `capturar_pantalla()` ahora se comporta distinto según `DEBUG`.
- `DEBUG=True`: guarda el screencap en disco en `screencaps/` (comportamiento anterior).
- `DEBUG=False`: captura directo a memoria con `subprocess.PIPE` + `np.frombuffer` + `cv2.imdecode`, sin tocar disco. Retorna `(None, imagen)`.

---

## 0.0.2 - 2026-03-28

### Agregado
- `constants.py`: constantes globales de configuración: `RESOLUCION`, `DISPOSITIVO_ADB`, `DEFAULT_DELAY`, `DEBUG`.
 
### Cambiado
- `screen.py`: `click_at` y `click_if_found` ahora leen `DISPOSITIVO_ADB` y `DEFAULT_DELAY` desde `constants.py` en lugar de tenerlos hardcodeados.
- `screen.py`: el flag `debug` de `find_image_on_screen` ya no es un parámetro de función — ahora lee la constante global `DEBUG` de `constants.py`.
- `screen.py`: el formato de `region` en `find_image_on_screen` se unificó a `(x1, y1, x2, y2)` (coordenadas absolutas de inicio y fin) en lugar de `(x, y, w, h)`.
 
### Corregido
- `screen.py`: `click_if_found` e `is_image_on_screen` estaban desactualizadas — no pasaban `screenshot_img` a `find_image_on_screen`. Ahora capturan pantalla internamente antes de llamar a la función.
- `context.py`: `menu_rapido_disponible()` trataba los objetos `Contexto` como dicts (llamaba a `.get()`). Corregido para acceder por atributo.
- `context.py`: región de `seleccion_de_personaje` tenía aritmética inline (`490-33`, `555-33`). Reemplazada por los valores calculados directamente.
 
---

## 0.0.1 - 2026-03-28

### Agregado
- `screen.py`: captura de pantalla via `hd-adb`, template matching con OpenCV, función `click_at` via ADB.
- `context.py`: clase `Contexto`, detección automática de contexto por imagen, contextos iniciales: `lobby`, `seleccion_de_personaje`, `stage_normal`.
- `actions.py`: función `click_boton_menu_rapido` que resuelve coordenadas según contexto activo.
- `constants.py`: estructura de coordenadas del menú rápido para tipos `lobby` y `default`.
- `auxiliares.py`: herramienta para encontrar la ventana de BlueStacks y calcular coordenadas relativas.
- `show_mouse_position.py`: utilidad para mostrar posición del mouse en tiempo real.
- `main.py`: punto de entrada básico para probar la detección de contexto.

---

## Formato de entradas futuras

Cada versión o sesión de trabajo debería tener una entrada así:

```
## [x.y.z] - YYYY-MM-DD

### Agregado
- Nuevas funciones o archivos.

### Cambiado
- Modificaciones a funcionalidad existente.

### Corregido
- Bugs solucionados.

### Eliminado
- Funciones o archivos removidos.
```
