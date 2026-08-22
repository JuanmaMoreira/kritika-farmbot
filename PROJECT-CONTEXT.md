# PROJECT CONTEXT - Kritika FarmBot

**Versión:** 0.1.2 | **Última actualización:** 2026-04-05

## 1. One-liner
Bot de automatización para **Kritika: The White Knights** en dispositivo Android físico (USB) usando scrcpy + ADB + OpenCV.

## 2. Objetivo principal
Automatizar farming, progresión y actividades repetitivas del juego de forma robusta, manejando popups, prioridades de contexto y flujos complejos sin intervención manual.

## 3. Stack tecnológico (actual)
- **Python**: 3.10+
- **Captura y visión**: scrcpy (H.264 stream ~4ms), OpenCV (template matching), numpy, av
- **Interacción**: ADB (clicks, swipes)
- **Estructura**: capas modulares (constants → screen → context → actions → flows)

## 4. Estructura del proyecto (mapa)
kritika-farmbot/
├── README.md
├── PROJECT-CONTEXT.md
├── ARCHITECTURE.md
├── ROADMAP.md
├── CHANGELOG.md
│
├── docs/
│   ├── index.md
│   └── 01-setup.md
│
├── ai-context/
│   └── full-project-context.md
│
├── bot/
│   ├── __init__.py
│   ├── constants.py
│   ├── screen.py
│   ├── context.py
│   ├── actions.py
│   ├── flows.py
│   ├── ads-manager.py
│   └── logger.py
│
├── tools/
├── assets/
├── screencaps/
├── main.py
├── requirements.txt
└── .gitignore


## 5. Reglas y convenciones importantes
- **constants.py** es la única fuente de verdad.
- Todas las coordenadas y regiones **relativas** (0.0–1.0) para que funcione en cualquier resolución.
- Usar clase `Boton` (con `coords`, `outcomes` y `timeout`) y atributo `prioridad` en cada `Contexto`.
- Outcomes posibles de presionar un `Boton`: `"ok"`, `"retry"`, `"abort"`.
- Los contextos se evalúan en orden de prioridad (mayor primero) para manejar popups.
- Nunca hardcodear coordenadas absolutas ni paths absolutos.
- Todo debe ser idempotente y resistente a popups inesperados.

## 6. Estado actual
- ✅ Sistema de captura con scrcpy + latencia baja
- ✅ Detección de contexto con prioridades y clase `Boton`
- ✅ Acciones atómicas refactorizadas
- ✅ Soporte dispositivo físico USB
- ⏳ Assets y constants.py incompletos (prioridad alta)
- ⏳ Lógica de prioridad y Boton aún por integrar completamente en constants.py

## 7. Cómo trabajar conmigo (instrucciones para IA)
1. Lee siempre primero `PROJECT-CONTEXT.md` y `ROADMAP.md`.
2. Usa **solo** coordenadas relativas y la estructura actual de `constants.py`.
3. Respeta la prioridad de contextos y outcomes de los botones.
4. Propone cambios en orden de prioridad del roadmap.
5. Cuando agregues código nuevo, actualizá `CHANGELOG.md` y este archivo si cambia el estado.