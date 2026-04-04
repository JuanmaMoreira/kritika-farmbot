# FarmBot — Kritika: The White Knights

Bot de automatización para el juego móvil **Kritika: The White Knights**, corriendo en un dispositivo físico Android conectado por USB. Usa scrcpy para captura de pantalla de alta velocidad y ADB para interacción con el dispositivo.

---

## ¿Qué hace?

- Captura el stream de video del dispositivo en tiempo real vía scrcpy (H.264 sobre socket TCP), con latencia de ~4ms por frame.
- Detecta el contexto actual del juego (lobby, survival, arena, black market, etc.) mediante template matching con OpenCV.
- Maneja prioridades de contexto para resolver correctamente popups y mensajes de confirmación que aparecen sobre otros contextos.
- Ejecuta acciones atómicas (clicks, swipes, navegación por menús) resolviendo automáticamente los outcomes esperados de cada botón.
- Coordenadas y regiones almacenadas en formato relativo (0.0–1.0), escalables a cualquier resolución de dispositivo sin recalibración.

---

## Arquitectura

```
kritika-farmbot/
├── bot/
│   ├── constants.py    # Fuente de verdad: contextos, botones, regiones, outcomes, menú rápido
│   ├── screen.py       # ScrcpyStream, captura de pantalla, template matching, clicks, swipes
│   ├── context.py      # Clases Contexto y Boton, detección de contexto/subcontexto/menú
│   ├── actions.py      # Acciones atómicas: click_boton, click_boton_menu, click_boton_menu_rapido
│   └── flows.py        # Flujos orquestados por funcionalidad del juego
├── assets/
│   └── ui/             # Templates PNG para template matching (resolución base 1224×2712)
│       └── 960x540/    # Templates archivados de la versión BlueStacks
├── screencaps/
│   └── batch/          # Frames capturados con screencap_batch.py para recalibración
├── tools/
│   ├── asset_capture.py      # Captura interactiva de assets, regiones y coordenadas
│   ├── screencap_batch.py    # Captura masiva de frames en vivo con SPACE
│   └── debug_context.py      # Diagnóstico de detección: tabla de confianzas y visualización
├── main.py
├── requirements.txt
├── CHANGELOG.md
└── README.md
```

---

## Capas del sistema

| Capa | Archivo | Responsabilidad |
|---|---|---|
| Datos | `constants.py` | Define qué existe: contextos, botones, regiones, outcomes |
| Pantalla | `screen.py` | Captura frames, busca templates, ejecuta clicks y swipes |
| Estado | `context.py` | Sabe dónde estás: detecta contexto, subcontexto y menú activo |
| Acciones | `actions.py` | Sabe cómo moverte: clickea y espera el outcome del botón |
| Flujos | `flows.py` | Orquesta secuencias completas de acciones por funcionalidad |

---

## Requisitos

- Python 3.10+
- Android físico con depuración USB habilitada
- `adb` disponible en el PATH
- scrcpy v3.3.4 (solo el jar del server, no requiere interfaz gráfica)

### Dependencias Python

```
opencv-python
numpy
av
```

---

## Instalación

```bash
git clone <url-del-repo>
cd kritika-farmbot
pip install -r requirements.txt
```

Configurar en `constants.py`:
```python
DISPOSITIVO_ADB    = "TU_SERIAL_ADB"       # resultado de: adb devices
SCRCPY_SERVER_PATH = r"ruta\a\scrcpy-server"
```

---

## Uso

```bash
# Correr el bot
python main.py

# Capturar frames en vivo para recalibración de assets
python tools/screencap_batch.py

# Capturar assets desde frames guardados
python tools/asset_capture.py screencaps/batch/

# Capturar assets directo desde el dispositivo
python tools/asset_capture.py

# Diagnosticar detección de contextos
python tools/debug_context.py
```

---

## Coordenadas relativas

Todas las coordenadas y regiones en `constants.py` están en formato relativo `(0.0–1.0)` respecto a `RESOLUCION_BASE = (1224, 2712)`. Al conectar el dispositivo, `screen.py` detecta la resolución real y escala automáticamente coordenadas y templates. Cambiar de dispositivo solo requiere recapturar los assets — las coordenadas relativas son reutilizables.

---

## Contextos y prioridades

Cada pantalla reconocible del juego es un `Contexto` con un template de detección y una prioridad numérica. Cuando varios contextos son visibles simultáneamente (popup sobre lobby, confirmación sobre popup), el sistema detecta en orden de prioridad descendente y retorna el de mayor prioridad. Los contextos base tienen prioridad 1, los popups y confirmaciones tienen prioridad 2 o superior.

---

## Notas

- `screencaps/` se crea automáticamente. En modo `DEBUG=True`, cada captura se guarda en disco con timestamp.
- Los assets en `assets/ui/` deben ser capturas reales del juego a la resolución base del dispositivo.
- `debug_recorte.png` se genera automáticamente en modo DEBUG para verificar regiones de búsqueda.
