# Instalación y Primer Uso

## Requisitos
- Python 3.10+
- Dispositivo Android físico con **depuración USB** activada
- `adb` en el PATH
- scrcpy v3.3.4 (solo el archivo `.jar` del server)

## Instalación

1. Clonar el repo
```bash
    git clone https://github.com/JuanmaMoreira/kritika-farmbot.git
    cd kritika-farmbot
```

2. Instalar dependencias Python
```bash
    pip install -r requirements.txt
```

3. Configurar scrcpy
    Descargar scrcpy v3.3.4
    Copiar scrcpy-server.jar a la raíz del proyecto (o actualizar la ruta en constants.py)

4. Conectar el dispositivo Android
    Habilitar depuración USB en el celular
    Conectar el celular por cable USB al PC
    Verificar que el dispositivo esté detectado
```bash
    adb devices
```
    reemplazar el nombre del dispositivo en constants.py en la variable DISPOSITIVO_ADB, o bien en .env


## Cómo ejecutar el bot
```bash
pip install -r requirements.txt
```

## Troubleshooting común

- "No se detecta dispositivo" → Volver a ejecutar adb devices. Si no aparece, reiniciar ADB con adb kill-server && adb start-server.
- Latencia alta en la pantalla → Asegurarse de que scrcpy esté funcionando correctamente y que no haya otras aplicaciones usando el USB.
- Templates no se detectan → Usar las herramientas en la carpeta tools/ (asset_capture.py o debug_context.py).
- Error al importar módulos → Verificar que estás en la raíz del proyecto y que instalaste los requirements.