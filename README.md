# Kritika FarmBot

Bot de automatización para **Kritika: The White Knights** en dispositivo Android físico conectado por USB.

Utiliza **scrcpy** para captura de pantalla de muy baja latencia + **OpenCV** para template matching, y maneja popups y contextos del juego de forma robusta.

---

## Requisitos

- Python 3.10+
- Dispositivo Android físico con **Depuración USB** activada
- `adb` en el PATH
- scrcpy v3.3.4 (solo el archivo `scrcpy-server.jar`)

---

## Instalación rápida

```bash
git clone https://github.com/JuanmaMoreira/kritika-farmbot.git
cd kritika-farmbot
pip install -r requirements.txt
```

---

## Configurá en bot/constants.py:

- DISPOSITIVO_ADB (resultado de adb devices)
- SCRCPY_SERVER_PATH (ruta al scrcpy-server.jar)

Más detalles → docs/01-setup.md

---

## Cómo ejecutar

```bash
python main.py
```

---

## Estructura y documentación interna

- `PROJECT-CONTEXT.md` → Contexto completo del proyecto (ideal para IAs)
- `ROADMAP.md` → Plan de desarrollo actual
- `ARCHITECTURE.md` → Detalle técnico de capas y decisiones
- `docs/01-setup.md` → Instalación y troubleshooting
- `docs/index.md` → Índice de documentación

---

## Notas importantes

- Todas las coordenadas son relativas (0.0–1.0) → funciona en diferentes resoluciones.
- `bot/constants.py` es la única fuente de verdad para contextos, botones y prioridades.
- El módulo `bot/ads-manager.py` maneja anuncios de forma independiente con uiautomator2.

---

## Próximos pasos

Ver `ROADMAP.md`