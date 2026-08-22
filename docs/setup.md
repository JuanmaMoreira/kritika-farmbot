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

Las dependencias preservadas cubren captura/visión legacy, carga de configuración y el AdsManager basado en UIAutomator2. OCR, VLM y frameworks de detección todavía no forman parte del proyecto.

## Configuración local

Crear un archivo `.env` local —nunca versionarlo— con:

```dotenv
DISPOSITIVO_ADB=<serial mostrado por adb devices>
SCRCPY_SERVER_PATH=<ruta local a scrcpy-server.jar>
```

No escribir el serial ni una ruta absoluta dentro del código.

## Verificación de ADB

Conectar el teléfono por USB, aceptar la autorización de depuración y comprobar:

```bash
adb devices
```

El serial configurado debe aparecer con estado `device`. Las pruebas que interactúen con el teléfono son opt-in y no deben formar parte de la suite normal sin hardware.

## Estado de ejecución

No existe todavía un comando de ejecución fiable para el bot completo. Las herramientas legacy en `tools/` y los scripts de `testing/` pueden abrir ventanas, escribir capturas o interactuar con el dispositivo; deben ejecutarse solo de forma deliberada.

El procedimiento de ejecución se documentará cuando la Fase 1 establezca un baseline importable y testeable.
