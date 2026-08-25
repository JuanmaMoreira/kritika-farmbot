# Preparación del entorno

Este documento conserva únicamente los pasos vigentes para preparar el entorno durante la transición a 0.2. El runtime legacy no está actualmente validado de extremo a extremo y `python main.py` falla por incompatibilidades conocidas entre módulos.

## Requisitos

- Python 3.10 o superior.
- Dispositivo Android físico con la interfaz del juego en landscape.
- Depuración USB habilitada.
- `adb` disponible en `PATH` o configurado mediante `ADB_PATH`.
- Drivers ADB correspondientes al dispositivo.
- `scrcpy-server.jar` compatible con `ScrcpyFrameSource`; el código actual declara protocolo 3.3.4.

## Entorno Python

Desde la raíz del repositorio, crear y activar un entorno virtual con el mecanismo habitual de la plataforma y luego instalar:

```bash
python -m pip install -r requirements.txt
```

Las dependencias cubren captura/visión, carga de configuración, el AdsManager basado en UIAutomator2 y la suite automatizada con pytest. OCR, VLM y frameworks de detección todavía no forman parte del proyecto.

## Configuración local

Crear un archivo `.env` local —nunca versionarlo— con:

```dotenv
ADB_PATH=adb
DISPOSITIVO_ADB=<serial mostrado por adb devices>
SCRCPY_SERVER_PATH=<ruta local a scrcpy-server.jar>
GAME_PACKAGE=com.gamevil.kritikamobile.android.google.global.normal
```

`.env.example` contiene la lista vigente de variables soportadas por `bot.config.RuntimeConfig`. La configuración solo lee ese archivo cuando un composition root llama explícitamente a `RuntimeConfig.from_env(dotenv_path=".env")`; también puede construirse directamente sin dotenv. Las herramientas de captura 0.2 usan este mecanismo. Los consumers legacy del bot completo no fueron migrados y ya no tienen un mecanismo de captura/input funcional.

No escribir el serial ni una ruta absoluta dentro del código.

El directorio local `.tools/` puede contener la distribución de scrcpy y su ADB asociado. Es una decisión deliberada para tooling de desarrollo, permanece ignorado por Git y nunca debe versionarse.

## Tests automatizados

La suite normal no requiere teléfono, ADB ni scrcpy-server:

```bash
pytest
```

En Windows, cuando `python`/`pytest` no estén expuestos en `PATH`, usar el intérprete del entorno local del checkout evita depender de launchers globales:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest
```

La configuración de pytest limita la colección a `tests/`. El antiguo directorio manual `testing/` fue retirado; las pruebas físicas son herramientas opt-in explícitas bajo `tools/`.

## Smoke test de captura 0.2

Con el dispositivo configurado y conectado, la captura real puede validarse deliberadamente mediante:

```bash
python tools/smoke_capture.py
```

La herramienta comprueba ADB, inicia scrcpy-server 3.3.4, valida cinco frames BGR landscape y verifica el cleanup del forward al salir. No guarda imágenes, no ejecuta gameplay y no envía taps ni swipes. No forma parte de `pytest` y puede interrumpirse con Ctrl+C; el context manager mantiene el cleanup.

## Verificación de ADB

Conectar el teléfono por USB, aceptar la autorización de depuración y comprobar:

```bash
adb devices
```

El serial configurado debe aparecer con estado `device`. Las pruebas que interactúen con el teléfono son opt-in y no deben formar parte de la suite normal sin hardware.

## Herramientas de adquisición

`python tools/screencap_batch.py` muestra el stream 0.2 y guarda únicamente los frames elegidos con SPACE. `python tools/asset_capture.py` cura templates, regiones y puntos desde el dispositivo o una carpeta de capturas. Ambas cargan `.env` dentro de `main()`, usan `ScrcpyFrameSource` y pueden abrir ventanas/escribir artefactos, por lo que su uso es deliberado.

Perception Workbench debe invocarse como módulo desde la raíz para que el package `bot` sea resoluble. En el entorno local Windows:

```powershell
& '.\.venv\Scripts\python.exe' -m tools.perception_workbench
```

La herramienta sólo observa input físico mediante `HumanInputObserver`; no envía taps, swipes ni keyevents.

## Estado de ejecución

No existe todavía un comando de ejecución fiable para el bot completo. `tools/smoke_capture.py` valida únicamente transporte y captura 0.2. El entry point y los módulos legacy de contexto, acciones y flows conservan imports de la antigua API de `bot.screen`; se reconstruirán sobre contratos semánticos en fases futuras.
