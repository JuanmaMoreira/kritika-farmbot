# Preparación del entorno

Este documento conserva únicamente los pasos vigentes para preparar el entorno durante la transición a 0.2. El runtime legacy no está actualmente validado de extremo a extremo y `python main.py` falla por incompatibilidades conocidas entre módulos.

## Requisitos

- Python 3.10 o superior.
- Dispositivo Android físico con la interfaz del juego en landscape.
- Depuración USB habilitada.
- `adb` disponible en `PATH`.
- Drivers ADB correspondientes al dispositivo.
- `scrcpy-server.jar` compatible con el cliente legacy preservado; el código actual declara protocolo 3.3.4.

## Entorno Python

Desde la raíz del repositorio, crear y activar un entorno virtual con el mecanismo habitual de la plataforma y luego instalar:

```bash
python -m pip install -r requirements.txt
```

Las dependencias preservadas cubren captura/visión legacy, carga de configuración, el AdsManager basado en UIAutomator2 y la suite automatizada con pytest. OCR, VLM y frameworks de detección todavía no forman parte del proyecto.

## Configuración local

Crear un archivo `.env` local —nunca versionarlo— con:

```dotenv
ADB_PATH=adb
DISPOSITIVO_ADB=<serial mostrado por adb devices>
SCRCPY_SERVER_PATH=<ruta local a scrcpy-server.jar>
GAME_PACKAGE=com.gamevil.kritikamobile.android.google.global.normal
```

`.env.example` contiene la lista vigente de variables soportadas por `bot.config.RuntimeConfig`. La nueva configuración solo lee ese archivo cuando el composition root llama explícitamente a `RuntimeConfig.from_env(dotenv_path=".env")`; también puede construirse directamente sin dotenv. Los consumers legacy todavía no fueron migrados y siguen usando sus mecanismos preservados.

No escribir el serial ni una ruta absoluta dentro del código.

## Tests automatizados

La suite normal no requiere teléfono, ADB ni scrcpy-server:

```bash
pytest
```

La configuración de pytest limita la colección a `tests/`. Los scripts bajo `testing/` continúan siendo herramientas manuales ligadas a hardware.

## Verificación de ADB

Conectar el teléfono por USB, aceptar la autorización de depuración y comprobar:

```bash
adb devices
```

El serial configurado debe aparecer con estado `device`. Las pruebas que interactúen con el teléfono son opt-in y no deben formar parte de la suite normal sin hardware.

## Estado de ejecución

No existe todavía un comando de ejecución fiable para el bot completo. Las herramientas legacy en `tools/` y los scripts de `testing/` pueden abrir ventanas, escribir capturas o interactuar con el dispositivo; deben ejecutarse solo de forma deliberada.

El procedimiento de ejecución se documentará cuando la Fase 1 establezca un baseline importable y testeable.
